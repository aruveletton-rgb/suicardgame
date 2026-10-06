// Real browser readability audit. Game states are reached through the visible controls.
import { chromium } from 'playwright';
import { mkdirSync, writeFileSync } from 'node:fs';

const BASE = process.env.BASE ?? 'http://127.0.0.1:8080';
const OUT = process.env.OUT ?? 'temp/v14-local-play-v2/readability/after';
const SHOTS = `${OUT}/screenshots`;
const VIEWPORTS = [
  { name: 'desktop', width: 1366, height: 820 },
  { name: 'mobile-portrait', width: 375, height: 812 },
  { name: 'mobile-landscape', width: 812, height: 375 },
];
const GAME_TIMEOUT_MS = Number(process.env.GAME_TIMEOUT_MS ?? 420000);
mkdirSync(SHOTS, { recursive: true });
const results = { started_at: new Date().toISOString(), base: BASE, screens: [], violations: [] };
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const capturedStages = new Set();

async function state(code) {
  const response = await fetch(`${BASE}/api/v1/rooms/${code}/state`);
  return response.json();
}

async function snapshotStage(page, name) {
  if (capturedStages.has(name)) return;
  capturedStages.add(name);
  for (const viewport of VIEWPORTS) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.evaluate(() => window.scrollTo(0, 0));
    await sleep(120);
    const shot = `${SHOTS}/${name}-${viewport.name}.png`;
    await page.screenshot({ path: shot, fullPage: false });
    const measured = await page.evaluate(() => {
      const parse = (v) => { const m = v.match(/rgba?\(([^)]+)\)/); const c = m?.[1].match(/[\d.]+/g)?.map(Number); return c?.length >= 3 ? [c[0],c[1],c[2],c[3] ?? 1] : null; };
      const lum = (c) => c.slice(0, 3).map((x) => { const n = x / 255; return n <= .04045 ? n / 12.92 : ((n + .055) / 1.055) ** 2.4; }).reduce((a, n, i) => a + n * [.2126, .7152, .0722][i], 0);
      const blend = (f, b) => { const a = f[3] + b[3] * (1 - f[3]); return a ? [0,1,2].map(i => (f[i]*f[3]+b[i]*b[3]*(1-f[3]))/a).concat(a) : [0,0,0,0]; };
      const selector = (el) => `${el.tagName.toLowerCase()}${el.id ? `#${el.id}` : ''}${[...el.classList].map(x => `.${x}`).join('')}`;
      const violations = [];
      const texts = [];
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      while (walker.nextNode()) {
        const node = walker.currentNode, text = node.textContent?.trim();
        if (!text) continue;
        const range = document.createRange(); range.selectNodeContents(node);
        const rect = range.getBoundingClientRect(), el = node.parentElement;
        if (!rect.width || !rect.height || !el || rect.right <= 0 || rect.bottom <= 0 || rect.left >= innerWidth || rect.top >= innerHeight) continue;
        const style = getComputedStyle(el);
        let opacity = 1, hidden = false;
        for (let cur = el; cur; cur = cur.parentElement) {
          const cs = getComputedStyle(cur);
          opacity *= Number(cs.opacity);
          if (cs.visibility === 'hidden' || cs.display === 'none') hidden = true;
        }
        if (hidden || opacity === 0) continue;
        const size = Number.parseFloat(style.fontSize), bold = Number.parseInt(style.fontWeight, 10) >= 700;
        const threshold = size >= 24 || (size >= 18.66 && bold) ? 3 : 4.5;
        let bg = [0,0,0,0], unresolved = false, foundBackground = false;
        for (let cur = el; cur; cur = cur.parentElement) {
          const cs = getComputedStyle(cur);
          const color = parse(cs.backgroundColor);
          if (cs.backgroundImage !== 'none') unresolved = true;
          if (color && color[3] > 0) {
            color[3] *= Number(cs.opacity);
            bg = blend(color, [0,0,0,0]);
            foundBackground = true;
            break;
          }
        }
        if (!foundBackground || bg[3] < 1) unresolved = true;
        if (!foundBackground) bg = [255,255,255,1];
        else if (bg[3] < 1) bg = blend(bg, [20,28,29,1]);
        const fgRaw = parse(style.color) ?? [0,0,0,1];
        const fg = blend([...fgRaw.slice(0,3), (fgRaw[3] ?? 1) * opacity], bg);
        const contrast = (Math.max(lum(fg),lum(bg))+.05)/(Math.min(lum(fg),lum(bg))+.05);
        const cardText = Boolean(el.closest('.product-card'));
        const floor = cardText ? 10 : 12;
        const disabled = Boolean(el.closest('button:disabled'));
        const fail = [];
        if (size < floor) fail.push(`font>=${floor}px`);
        if (contrast < threshold) fail.push(`contrast>=${threshold}:1`);
        if (unresolved) fail.push('bg_unresolved');
        if (disabled && contrast < 4.5) fail.push('disabled contrast>=4.5:1');
        const metric = {
          selector: selector(el), text: text.slice(0, 90), size,
          text_color: style.color,
          effective_background: `rgb(${bg.slice(0, 3).map((n) => Math.round(n)).join(', ')})`,
          contrast: Number(contrast.toFixed(2)), threshold, bg_unresolved: unresolved,
        };
        texts.push(metric);
        if (fail.length) violations.push({ ...metric, violation: fail });
      }
      const box = (el) => { const r = el.getBoundingClientRect(); return { x:r.x,y:r.y,right:r.right,bottom:r.bottom,width:r.width,height:r.height }; };
      const result = document.querySelector('[data-testid="game-result"]');
      const hand = [...document.querySelectorAll('.hand-zone .hand-item')].map(box);
      const handItems = [...document.querySelectorAll('.hand-zone .hand-item')];
      const handCornersVisible = handItems.every((item, index) => {
        const corner = item.querySelector('.product-uno__corner, .product-sui__mark');
        if (!corner) return true;
        const r = corner.getBoundingClientRect();
        if (!r.width || !r.height) return false;
        const x = r.left + r.width / 2, y = r.top + r.height / 2;
        return !handItems.slice(index + 1).some((later) => {
          const z = Number.parseInt(getComputedStyle(later).zIndex, 10);
          const ownZ = Number.parseInt(getComputedStyle(item).zIndex, 10);
          const laterPaintsAbove = Number.isNaN(z) ? Number.isNaN(ownZ) || z >= ownZ : Number.isNaN(ownZ) || z >= ownZ;
          const other = later.getBoundingClientRect();
          return laterPaintsAbove && x >= other.left && x <= other.right && y >= other.top && y <= other.bottom;
        });
      });
      const shop = [...document.querySelectorAll('.shop-row .product-card--thumbnail')]
        .filter((el) => { const style = getComputedStyle(el), r = el.getBoundingClientRect(); return style.display !== 'none' && style.visibility !== 'hidden' && r.width > 0 && r.height > 0; })
        .map(box);
      const overlap = (a,b) => a.x < b.right && a.right > b.x && a.y < b.bottom && a.bottom > b.y;
      const shopOverlap = shop.some((a,i) => shop.slice(i+1).some(b => overlap(a,b)));
      const shopArea = document.querySelector('.shop-area')?.getBoundingClientRect();
      const shopClipped = Boolean(shopArea && shop.some(card => card.x < shopArea.left || card.right > shopArea.right || card.y < shopArea.top || card.bottom > shopArea.bottom));
      const handStrip = hand.length ? Math.min(...hand.map((item,i) => i === hand.length - 1 ? item.width : Math.min(item.width, hand[i+1].x - item.x))) : null;
      const resultBox = result ? box(result) : null;
      const resultVisible = !result || (resultBox.x >= 0 && resultBox.y >= 0 && resultBox.right <= innerWidth && resultBox.bottom <= innerHeight);
      const keyButtons = [...document.querySelectorAll('[data-testid="draw-card"],[data-testid="play-selected"],[data-testid^="pending-response-"]')].filter(el => getComputedStyle(el).display !== 'none').map(el => ({ text:el.textContent.trim(),height:el.getBoundingClientRect().height }));
      const layout = { result_panel_inside_viewport: resultVisible, hand_min_visible_strip_px: handStrip, hand_corners_visible: handCornersVisible, shop_thumbnails_overlap: shopOverlap, shop_thumbnails_clipped: shopClipped, shop_thumbnail_count: shop.length, key_button_heights: keyButtons };
      if (!resultVisible) violations.push({ selector: '[data-testid="game-result"]', text: 'result panel outside viewport or requires scrolling', size: null, contrast: null, threshold: 'inside viewport', violation: ['result_layout'] });
      if (handStrip !== null && handStrip < 40) violations.push({ selector: '.hand-zone .hand-item', text: 'visible card strip under 40px', size: null, contrast: null, threshold: '40px', violation: ['hand_overlap'] });
      if (hand.length && !handCornersVisible) violations.push({ selector: '.hand-zone .hand-item .product-uno__corner,.hand-zone .hand-item .product-sui__mark', text: 'hand card corner index is covered', size: null, contrast: null, threshold: 'visible', violation: ['hand_corner_covered'] });
      if (shopOverlap) violations.push({ selector: '.shop-row .product-card--thumbnail', text: 'shop thumbnails overlap', size: null, contrast: null, threshold: 'no overlap', violation: ['shop_overlap'] });
      if (shopClipped) violations.push({ selector: '.shop-row .product-card--thumbnail', text: 'shop thumbnails are clipped by the shop area', size: null, contrast: null, threshold: 'inside shop area', violation: ['shop_clipped'] });
      if (innerWidth <= 812 && keyButtons.some(x => x.height < 44)) violations.push({ selector: '[data-testid="draw-card"],[data-testid="play-selected"],[data-testid^="pending-response-"]', text: 'mobile operation button under 44px', size: null, contrast: null, threshold: '44px', violation: ['button_height'] });
      return { violations, layout };
    });
    results.screens.push({ name, viewport: viewport.name, screenshot: shot, layout: measured.layout, texts: measured.texts });
    results.violations.push(...measured.violations.map((v) => ({ screen: name, viewport: viewport.name, ...v })));
  }
}

async function player(browser, name) {
  const context = await browser.newContext({ viewport: VIEWPORTS[0] });
  const page = await context.newPage();
  page.on('dialog', (dialog) => dialog.accept());
  await page.goto(BASE);
  await page.getByTestId('nickname').fill(name);
  return { context, page };
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  try {
    const host = await player(browser, '可读性房主');
    const guest = await player(browser, '可读性玩家');
    await host.page.getByTestId('create-room').click();
    await host.page.getByTestId('room-code').waitFor({ timeout: 10000 });
    const code = (await host.page.getByTestId('room-code').textContent()).trim();
    await snapshotStage(host.page, 'room-ready');
    await guest.page.getByTestId('join-code').fill(code);
    await guest.page.getByTestId('join-room').click();
    await guest.page.getByTestId('room-code').waitFor({ timeout: 10000 });
    await snapshotStage(host.page, 'lobby');
    await host.page.getByTestId('ready').click(); await guest.page.getByTestId('ready').click();
    await host.page.getByTestId('start-game').click();
    await host.page.getByTestId('hand-card').first().waitFor({ timeout: 15000 });
    await snapshotStage(host.page, 'own-turn');
    const players = [host, guest];
    const started = Date.now();
    let lastVersion = -1;
    while (Date.now() - started < GAME_TIMEOUT_MS) {
      const s = await state(code), game = s.active_game;
      if (s.state_version !== lastVersion) lastVersion = s.state_version;
      if (s.phase === 'ROUND_RESULT') { await snapshotStage(host.page, 'result'); break; }
      if (game?.pause_state) {
        await snapshotStage(host.page, 'pause');
        await host.page.getByRole('button', { name: '结束本局' }).click();
        await sleep(250);
        continue;
      }
      if (game?.pending_action?.status === 'open') {
        let captured = false;
        for (const p of players) {
          const buttons = p.page.locator('[data-testid^="pending-response-"]:not(:disabled)');
          if (await buttons.count()) {
            if (!captured) { await snapshotStage(p.page, 'response-window'); captured = true; }
            const button = buttons.first();
            const response = (await button.getAttribute('data-testid')).replace('pending-response-', '');
            if (['give_card','discard_card','control_play','evade'].includes(response)) {
              const legalIndex = await p.page.$$eval('[data-testid="hand-card"]', (els) => els.findIndex((el) => el.querySelector('.is-legal')));
              const mustChooseAny = response === 'discard_card' && legalIndex < 0;
              if (legalIndex >= 0 || mustChooseAny) {
                await p.page.getByTestId('hand-card').nth(legalIndex >= 0 ? legalIndex : 0).click().catch(() => {});
              } else {
                continue;
              }
            }
            await button.click().catch(() => {});
            await sleep(200);
            break;
          }
        }
        await sleep(200); continue;
      }
      const sessionPlayer = await Promise.all(players.map((p) => p.page.evaluate(() => JSON.parse(localStorage.getItem('suicardgame.session.v1') ?? '{}').player_id)));
      const current = players[sessionPlayer.findIndex((id) => id === game?.current_player_id)];
      if (!current) { await sleep(250); continue; }
      const canDraw = await current.page.getByTestId('draw-card').isEnabled().catch(() => false);
      if (!canDraw) { await sleep(250); continue; }
      const card = await current.page.$$eval('[data-testid="hand-card"]', (els) => els.findIndex((el) => el.querySelector('.is-legal')));
      if (card >= 0) {
        await current.page.locator('.hand-rack__toolbar button').filter({ hasText: /^主牌$/ }).click();
        await current.page.getByTestId('hand-card').nth(card).click();
        const play = current.page.getByTestId('play-selected');
        if (await play.isEnabled()) await play.click({ timeout: 800 }).catch(() => {});
        else await current.page.getByTestId('draw-card').click({ timeout: 800 }).catch(() => {});
      } else await current.page.getByTestId('draw-card').click({ timeout: 800 }).catch(() => {});
      await sleep(180);
    }
  } finally {
    await browser.close();
    results.finished_at = new Date().toISOString();
    results.summary = {
      violation_count: results.violations.filter((item) => item.violation.some((v) => v !== 'bg_unresolved')).length,
      unresolved_background_count: results.violations.filter((item) => item.violation.length === 1 && item.violation[0] === 'bg_unresolved').length,
      screen_count: results.screens.length,
    };
    writeFileSync(`${OUT}/readability.json`, JSON.stringify(results, null, 2));
    console.log(JSON.stringify(results.summary));
  }
}

main();
