// 本地 8080 真实 UI 对局模拟：多个浏览器上下文 = 多个玩家，只通过点击界面操作。
// 公共牌桌信息（弃牌顶、当前颜色、当前玩家）读取自 GET /state，与玩家屏幕可见信息一致；
// 手牌只从各自页面 DOM 读取。不读取、不打印任何 token。
import { chromium } from 'playwright';
import { mkdirSync, readFileSync, statSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';

const BASE = process.env.BASE ?? 'http://127.0.0.1:8080';
const OUT = process.env.OUT ?? 'temp/v14-local-play-v2';
const OUT_PATH = resolve(OUT);
const ROOM_DATA_DIR = process.env.ROOM_DATA_DIR ?? `${OUT}/rooms`;
const ROOM_DATA_PATH = resolve(ROOM_DATA_DIR);
const SHOTS = `${OUT_PATH}/shots`;
mkdirSync(SHOTS, { recursive: true });

const DEFAULT_ROOMS = [
  { names: ['房主A', '玩家B', '玩家C'], games: 6, reloadTestGame: 3 },
  { names: ['房主D', '玩家E'], games: 4, reloadTestGame: null },
];
const ROOMS = process.env.ROOMS ? JSON.parse(process.env.ROOMS) : DEFAULT_ROOMS;
if (process.env.EXTENDED_RUN === '1') {
  ROOMS.push(
    { names: ['四人房主', '四人B', '四人C', '四人D'], games: 1, reloadTestGame: null },
    { names: ['五人房主', '五人B', '五人C', '五人D', '五人E'], games: 1, reloadTestGame: null },
  );
}
const MAX_ACTIONS_PER_GAME = 500;
const STALL_MS = 45000;
const COLOR_LABEL = { red: '红色', yellow: '黄色', green: '绿色', blue: '蓝色' };

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const rand = () => Math.random();
const log = (...a) => console.log(new Date().toISOString().slice(11, 19), ...a);

const results = { started_at: new Date().toISOString(), games: [], findings: [], console_errors: [], page_errors: [], http_errors: [], banner_language_counts: { chinese: 0, english: 0 }, shop_attempts: { buy: 0, refresh: 0 } };
const errorTexts = new Map();
function noteError(text, ctx) {
  const key = text.trim();
  if (!key) return;
  const cur = errorTexts.get(key) ?? { count: 0, contexts: [] };
  cur.count += 1;
  if (/[\u3400-\u9fff]/.test(key)) results.banner_language_counts.chinese += 1;
  else results.banner_language_counts.english += 1;
  if (cur.contexts.length < 5) cur.contexts.push(ctx);
  errorTexts.set(key, cur);
}
function finding(kind, detail) {
  results.findings.push({ at: new Date().toISOString(), kind, detail });
  log('FINDING', kind, JSON.stringify(detail));
}

async function getState(code) {
  const res = await fetch(`${BASE}/api/v1/rooms/${code}/state`);
  return res.json();
}
function roomSnapshotStats(code) {
  const path = resolve(ROOM_DATA_PATH, `${code}.json`);
  try {
    const snapshot = JSON.parse(readFileSync(path, 'utf8'));
    const result = { room: code, processed_actions: Object.keys(snapshot.processed_actions ?? {}).length, file_bytes: statSync(path).size };
    if (result.processed_actions > 256 || result.file_bytes >= 50 * 1024) finding('room_snapshot_limit', result);
    return result;
  } catch {
    finding('room_snapshot_unavailable', { room: code });
    return { room: code, processed_actions: null, file_bytes: null };
  }
}
async function waitVersionChange(code, from, ms = 6000) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) {
    const s = await getState(code);
    if (s.state_version !== from) return { state: s, ms: Date.now() - t0 };
    await sleep(120);
  }
  return null;
}

async function newPlayer(browser, name) {
  const context = await browser.newContext({ viewport: { width: 1366, height: 820 } });
  const page = await context.newPage();
  page.on('dialog', (d) => d.accept().catch(() => {}));
  page.on('console', (m) => { if (m.type() === 'error') results.console_errors.push({ player: name, text: m.text().slice(0, 300) }); });
  page.on('pageerror', (e) => results.page_errors.push({ player: name, text: String(e).slice(0, 300) }));
  page.on('response', (r) => {
    if (r.url().includes('/api/') && r.status() >= 400) results.http_errors.push({ player: name, status: r.status(), path: new URL(r.url()).pathname });
  });
  await page.goto(BASE);
  await page.getByTestId('nickname').fill(name);
  return { name, context, page, playerId: null };
}
async function playerIdOf(p) {
  return p.page.evaluate(() => JSON.parse(localStorage.getItem('suicardgame.session.v1') ?? '{}').player_id ?? null);
}
async function errorBanner(page) {
  const el = page.getByTestId('error-banner');
  return (await el.count()) ? (await el.textContent()) ?? '' : '';
}

async function readyAllAndStart(players, code) {
  for (let attempt = 0; attempt < 6; attempt += 1) {
    const s = await getState(code);
    for (const p of players) {
      const me = s.players.find((x) => x.player_id === p.playerId);
      if (me && !me.ready) {
        await p.page.getByTestId('ready').click({ timeout: 5000 });
        await sleep(250);
      }
    }
    const s2 = await getState(code);
    if (s2.players.every((x) => x.ready && x.online)) break;
    await sleep(500);
  }
  const host = players[0];
  await host.page.getByTestId('start-game').click({ timeout: 8000 });
  for (const p of players) await p.page.getByTestId('hand-card').first().waitFor({ timeout: 10000 });
}

function legalNormal(card, top, color) {
  if (card.category === 'sui' || card.category === 'field') return false;
  if (card.category === 'wild') return true;
  if (!top) return true;
  if (color && card.color === color) return true;
  if (card.category === 'number' && top.category === 'number' && String(top.value) === card.value) return true;
  if (card.category === 'action' && top.category === 'action' && card.kind === top.kind) return true;
  return false;
}
async function readHand(page) {
  return page.$$eval('[data-testid="hand-card"]', (els) => els.map((e, i) => ({
    i, kind: e.dataset.cardKind, category: e.dataset.cardCategory, color: e.dataset.cardColor, value: e.dataset.cardValue,
    legal: Boolean(e.querySelector('.is-legal')),
  })));
}
async function pickRole(page, label) {
  await page.locator('.hand-rack__toolbar button', { hasText: new RegExp(`^${label}$`) }).click({ timeout: 3000 });
}
async function clickHand(page, i) {
  await page.getByTestId('hand-card').nth(i).click({ timeout: 3000 });
}
async function setUnoToggle(page, want) {
  const btn = page.locator('button', { hasText: '随出牌宣告 UNO' });
  const pressed = (await btn.getAttribute('aria-pressed')) === 'true';
  if (pressed !== want) await btn.click({ timeout: 3000 });
}
function mostColor(hand) {
  const counts = {};
  for (const c of hand) if (COLOR_LABEL[c.color]) counts[c.color] = (counts[c.color] ?? 0) + 1;
  return Object.entries(counts).sort((a, b) => b[1] - a[1])[0]?.[0] ?? 'red';
}
async function chooseColor(page, color) {
  const btn = page.locator('.color-choice button', { hasText: COLOR_LABEL[color] });
  if (await btn.count()) await btn.click({ timeout: 3000 });
}

// 一次 UI 操作，返回是否推进了 state_version
async function attempt(game, p, code, label, fn) {
  const before = await getState(code);
  const bannerBefore = await errorBanner(p.page);
  try {
    await fn();
  } catch (e) {
    game.ui_failures.push({ player: p.name, label, error: String(e).split('\n')[0].slice(0, 200) });
    return false;
  }
  const changed = await waitVersionChange(code, before.state_version);
  if (changed) {
    game.latencies.push(changed.ms);
    return true;
  }
  const banner = await errorBanner(p.page);
  noteError(banner || '(无错误提示但状态未推进)', `${label} by ${p.name}`);
  if (banner === bannerBefore && banner) game.repeated_banner += 1;
  return false;
}

async function trySui(game, p, code, hand, card, others) {
  const kind = card.kind;
  game.sui_attempts[kind] = game.sui_attempts[kind] ?? { tried: 0, ok: 0 };
  game.sui_attempts[kind].tried += 1;
  const ok = await attempt(game, p, code, `ACTIVATE ${kind}`, async () => {
    await pickRole(p.page, '主牌');
    await clickHand(p.page, card.i);
    if (kind === 'ji' || kind === 'shu') await chooseColor(p.page, mostColor(hand.filter((c) => c.i !== card.i)));
    if (kind === 'wang' || kind === 'zuole') {
      const t = p.page.locator('.target-choice button').filter({ hasNotText: '（自己）' }).first();
      if (await t.count()) await t.click({ timeout: 3000 });
    }
    if (kind === 'yi') {
      const nums = hand.filter((c) => c.category === 'number');
      let pair = null;
      for (const a of nums) for (const b of nums) if (!pair && a.i < b.i && Number(a.value) + Number(b.value) === 8) pair = [a, b];
      if (!pair) throw new Error('no yi pair');
      await pickRole(p.page, '多选牌');
      for (const c of pair) await clickHand(p.page, c.i);
    }
    if (kind === 'yu') {
      const picked = [];
      for (const c of hand) if (c.i !== card.i && COLOR_LABEL[c.color] && !picked.some((x) => x.color === c.color)) picked.push(c);
      if (picked.length < 4) throw new Error('no yu payment');
      await pickRole(p.page, '多选牌');
      for (const c of picked.slice(0, 4)) await clickHand(p.page, c.i);
    }
    await p.page.getByTestId('play-selected').click({ timeout: 3000 });
  });
  if (ok) game.sui_attempts[kind].ok += 1;
  return ok;
}

async function takeTurn(game, p, code, state, players) {
  const g = state.active_game;
  const hand = await readHand(p.page);
  const others = players.filter((x) => x !== p);
  if (!game.shop_players?.includes(p.playerId)) {
    game.shop_players ??= [];
    game.shop_players.push(p.playerId);
    const refresh = p.page.locator('.shop-actions button').filter({ hasText: '刷新' });
    if (await refresh.count() && await refresh.isEnabled().catch(() => false)) {
      game.shop_refresh_attempts += 1;
      results.shop_attempts.refresh += 1;
      await attempt(game, p, code, 'SHOP_REFRESH', () => refresh.click({ timeout: 3000 }));
    }
    const goods = p.page.locator('.shop-row .card-button');
    if (await goods.count()) {
      game.shop_buy_attempts += 1;
      results.shop_attempts.buy += 1;
      await attempt(game, p, code, 'SHOP_BUY', async () => {
        await goods.first().click({ timeout: 3000 });
        await pickRole(p.page, '支付牌');
        await clickHand(p.page, 0);
        await p.page.locator('.shop-confirm button').click({ timeout: 3000 });
      });
    }
  }
  const suiCards = hand.filter((c) => c.category === 'sui');
  if (suiCards.length && rand() < 0.45) {
    const card = suiCards[Math.floor(rand() * suiCards.length)];
    if (await trySui(game, p, code, hand, card, others)) { game.sui_activations += 1; return; }
  }
  const legal = hand.filter((c) => legalNormal(c, g.top_discard, g.current_color));
  legal.sort((a, b) => (a.category === 'wild') - (b.category === 'wild') || (a.kind === 'wild_draw_four') - (b.kind === 'wild_draw_four'));
  for (const card of legal.slice(0, 2)) {
    const declare = hand.length === 2 && rand() < 0.8;
    const ok = await attempt(game, p, code, `PLAY ${card.kind}/${card.color}/${card.value}`, async () => {
      await pickRole(p.page, '主牌');
      await clickHand(p.page, card.i);
      if (card.category === 'wild') await chooseColor(p.page, mostColor(hand.filter((c) => c.i !== card.i)));
      await setUnoToggle(p.page, declare);
      await p.page.getByTestId('play-selected').click({ timeout: 3000 });
    });
    if (ok) {
      game.plays += 1;
      if (hand.length === 2) game.uno_toggle_used += declare ? 1 : 0;
      return;
    }
  }
  const ok = await attempt(game, p, code, 'DRAW', async () => {
    await setUnoToggle(p.page, false);
    await p.page.getByTestId('draw-card').click({ timeout: 3000 });
  });
  if (ok) game.draws += 1;
  else game.turn_failures += 1;
}

const NO_CARD_PREF = ['decline_challenge', 'accept', 'decline', 'pass', 'control_pass', 'stop', 'draw_four', 'challenge'];
const SINGLE_CARD = ['discard_card', 'give_card', 'evade', 'control_play'];
async function respondPrompt(game, p, code, buttons) {
  const kinds = buttons;
  game.prompts_seen.add(kinds.join('|'));
  let order = [...NO_CARD_PREF.filter((k) => kinds.includes(k)), ...SINGLE_CARD.filter((k) => kinds.includes(k)), ...kinds];
  if (kinds.includes('challenge') && rand() < 0.3) order = ['challenge', ...order];
  order = [...new Set(order)];
  const hand = await readHand(p.page);
  for (const resp of order.slice(0, 3)) {
    const needsSingle = SINGLE_CARD.includes(resp) || resp === 'use_xi';
    const needsMulti = ['submit_cards', 'chi', 'peng', 'gang', 'restart'].includes(resp);
    // 界面没有标出哪些牌合法，真实玩家只能逐张尝试：岁牌优先，其次其余手牌，最多试 4 张
    const highlighted = hand.filter((c) => c.legal);
    const candidates = needsSingle || needsMulti
      ? resp === 'discard_card' && highlighted.length === 0
        ? hand.slice(0, 4).map((card) => ({ ...card, legal: true }))
        : highlighted.slice(0, 4)
      : [null];
    if ((needsSingle || needsMulti) && candidates.length === 0) continue;
    for (const card of candidates) {
      const ok = await attempt(game, p, code, `RESPOND ${resp}`, async () => {
        if (card) {
          await pickRole(p.page, needsSingle ? '主牌' : '多选牌');
          await clickHand(p.page, card.i);
        }
        await p.page.getByTestId(`pending-response-${resp}`).click({ timeout: 3000 });
      });
      if (ok) {
        game.prompt_responses += 1;
        return true;
      }
      if (card && !card.legal) game.blind_card_retries += 1;
      if (!(await p.page.getByTestId(`pending-response-${resp}`).count())) break;
    }
  }
  return false;
}

async function enabledResponses(page) {
  return page.$$eval('[data-testid^="pending-response-"]', (els) => els.filter((e) => !e.disabled).map((e) => e.dataset.testid.replace('pending-response-', '')));
}

async function playOneGame(players, code, gameNo, reloadTest) {
  const t0 = Date.now();
  const game = {
    game_no: gameNo, room: code, players: players.map((p) => p.name), plays: 0, draws: 0, sui_activations: 0,
    sui_attempts: {}, prompt_responses: 0, prompts_seen: new Set(), uno_toggle_used: 0, uno_declare_clicks: 0, uno_catch_clicks: 0,
    pauses: 0, latencies: [], ui_failures: [], turn_failures: 0, repeated_banner: 0, dom_mismatch: 0, end: null, winner: null,
    actions: 0, reload_test: null, hand_counts_end: null, blind_card_retries: 0, shop_buy_attempts: 0, shop_refresh_attempts: 0,
  };
  let lastVersion = -1;
  let lastProgress = Date.now();
  let noPromptUiSince = null;
  let promptReloads = 0;
  let reloadDone = !reloadTest;
  while (game.actions < MAX_ACTIONS_PER_GAME) {
    const s = await getState(code);
    if (JSON.stringify(s).includes('"hand":')) finding('public_state_hand_leak', { code });
    if (s.state_version !== lastVersion) { lastVersion = s.state_version; lastProgress = Date.now(); }
    if (s.phase === 'ROUND_RESULT') {
      const g = s.active_game;
      game.end = g.status;
      game.end_reason = g.special_state?.end_reason ?? null;
      game.winner = s.players.find((x) => x.player_id === g.winner_player_id)?.nickname ?? null;
      game.hand_counts_end = Object.fromEntries(s.players.map((x) => [x.nickname, x.hand_count]));
      game.result_ui = await players[0].page.evaluate(() => {
        const panel = document.querySelector('[data-testid="game-result"]');
        const turnPanel = document.querySelector('.turn-panel');
        const panelBox = panel?.getBoundingClientRect();
        return {
          visible: Boolean(panel && panelBox && panelBox.width && panelBox.height),
          inside_viewport: Boolean(panelBox && panelBox.left >= 0 && panelBox.top >= 0 && panelBox.right <= innerWidth && panelBox.bottom <= innerHeight),
          countdown_visible: Boolean(turnPanel?.textContent?.includes('回合')),
          end_reason_visible: panel?.textContent?.includes('牌库耗尽，按手牌数判胜') ?? false,
        };
      });
      if (!game.result_ui.visible || !game.result_ui.inside_viewport) finding('result_panel_not_visible', { game: gameNo, ...game.result_ui });
      if (game.result_ui.countdown_visible) finding('result_countdown_visible', { game: gameNo });
      if (game.end_reason === 'deck_exhausted' && !game.result_ui.end_reason_visible) finding('deck_exhausted_reason_missing', { game: gameNo });
      if (g.status === 'FINISHED' && game.winner && game.hand_counts_end[game.winner] !== 0) game.end = 'FINISHED_BY_HAND_COUNT';
      break;
    }
    if (Date.now() - lastProgress > STALL_MS) {
      finding('game_stalled', { game: gameNo, state_version: s.state_version, current: s.active_game?.current_player_id ? 'set' : 'none', pending: s.active_game?.pending_action?.kind ?? null, pause: s.active_game?.pause_state?.step_kind ?? null });
      await players[0].page.screenshot({ path: `${SHOTS}/stall-game${gameNo}.png` });
      await players[0].page.locator('button', { hasText: '重置' }).click({ timeout: 3000 }).catch(() => {});
      await sleep(1500);
      game.end = 'STALLED_RESET';
      break;
    }
    const g = s.active_game;
    if (!g) { await sleep(300); continue; }
    if (g.pause_state) {
      game.pauses += 1;
      finding('pause_triggered', { game: gameNo, step_kind: g.pause_state.step_kind });
      let completed = false;
      for (const p of players) {
        const responses = await enabledResponses(p.page);
        if (responses.length && await respondPrompt(game, p, code, responses)) {
          game.actions += 1;
          completed = true;
          break;
        }
      }
      if (completed) continue;
      await attempt(game, players[0], code, 'CONTINUE_WAITING', () => players[0].page.locator('button', { hasText: '继续等待并重置时限' }).click({ timeout: 3000 }));
      game.actions += 1;
      continue;
    }
    // 中途刷新页面，验证断线重连
    if (!reloadDone && game.plays + game.draws >= 6) {
      reloadDone = true;
      const p = players[1];
      const handBefore = s.players.find((x) => x.player_id === p.playerId)?.hand_count;
      await p.page.reload();
      let restored = false;
      try { await p.page.getByTestId('hand-card').first().waitFor({ timeout: 10000 }); restored = true; } catch {}
      await sleep(800);
      const domCount = await p.page.getByTestId('hand-card').count();
      const s2 = await getState(code);
      const online = s2.players.find((x) => x.player_id === p.playerId)?.online;
      game.reload_test = { player: p.name, restored, online, hand_before: handBefore, dom_hand_after: domCount, server_hand_after: s2.players.find((x) => x.player_id === p.playerId)?.hand_count };
      if (!restored || !online) finding('reconnect_failed', game.reload_test);
      continue;
    }
    // 1) 任何玩家有可用的响应按钮 -> 先响应
    let acted = false;
    for (const p of players) {
      const resp = await enabledResponses(p.page);
      if (resp.length) {
        const responded = await respondPrompt(game, p, code, resp);
        if (responded) {
          acted = true;
          noPromptUiSince = null;
          promptReloads = 0;
          game.actions += 1;
        }
        break;
      }
    }
    if (acted) continue;
    if (g.pending_action?.status === 'open') {
      noPromptUiSince ??= Date.now();
      if (Date.now() - noPromptUiSince > 5000 && promptReloads < 2) {
        const page = players[promptReloads % players.length].page;
        await page.reload();
        await sleep(700);
        promptReloads += 1;
        noPromptUiSince = Date.now();
      }
    }
    // 2) UNO 宣告 / 抓取
    for (const p of players) {
      const declare = p.page.getByTestId('declare-uno');
      if (await declare.count() && rand() < 0.6) {
        if (await attempt(game, p, code, 'DECLARE_UNO', () => declare.click({ timeout: 2000 }))) game.uno_declare_clicks += 1;
        acted = true; break;
      }
      const catchBtn = p.page.getByTestId('catch-uno');
      if (await catchBtn.count() && rand() < 0.6) {
        if (await attempt(game, p, code, 'CATCH_UNO', () => catchBtn.click({ timeout: 2000 }))) game.uno_catch_clicks += 1;
        acted = true; break;
      }
    }
    if (acted) { game.actions += 1; continue; }
    // 3) 当前玩家行动
    if (g.pending_action && g.pending_action.status === 'open') { await sleep(400); continue; }
    const cur = players.find((p) => p.playerId === g.current_player_id);
    if (!cur) { await sleep(300); continue; }
    const expected = s.players.find((x) => x.player_id === cur.playerId)?.hand_count;
    let synced = false;
    for (let i = 0; i < 15; i += 1) {
      const n = await cur.page.getByTestId('hand-card').count();
      const drawEnabled = await cur.page.getByTestId('draw-card').isEnabled().catch(() => false);
      if (n === expected && drawEnabled) { synced = true; break; }
      await sleep(200);
    }
    if (!synced) { game.dom_mismatch += 1; continue; }
    await takeTurn(game, cur, code, s, players);
    game.actions += 1;
    await sleep(80 + Math.floor(rand() * 200));
  }
  if (!game.end) {
    game.end = 'ACTION_CAP_RESET';
    finding('action_cap_reached', { game: gameNo });
    await players[0].page.locator('button', { hasText: '重置' }).click({ timeout: 3000 }).catch(() => {});
    await sleep(1500);
  }
  game.duration_s = Math.round((Date.now() - t0) / 1000);
  game.prompts_seen = [...game.prompts_seen];
  const lat = [...game.latencies].sort((a, b) => a - b);
  game.latency_ms = { n: lat.length, p50: lat[Math.floor(lat.length / 2)] ?? null, p95: lat[Math.floor(lat.length * 0.95)] ?? null, max: lat.at(-1) ?? null };
  delete game.latencies;
  await players[0].page.screenshot({ path: `${SHOTS}/game${String(gameNo).padStart(2, '0')}-end-host.png` });
  results.games.push(game);
  log(`game ${gameNo} end=${game.end} winner=${game.winner} plays=${game.plays} draws=${game.draws} sui=${game.sui_activations} prompts=${game.prompt_responses} ${game.duration_s}s`);
  return game;
}

async function backToLobby(players, code, gameNo) {
  const host = players[0];
  const s = await getState(code);
  if (s.phase === 'ROUND_RESULT') {
    await host.page.getByRole('button', { name: '再来一局' }).click({ timeout: 5000 });
  }
  const t0 = Date.now();
  while (Date.now() - t0 < 10000) {
    const s2 = await getState(code);
    if (s2.phase === 'LOBBY') return;
    await sleep(200);
  }
  finding('rematch_not_lobby', { game: gameNo, phase: (await getState(code)).phase });
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  let gameNo = 0;
  try {
    for (const roomCfg of ROOMS) {
      const players = [];
      for (const n of roomCfg.names) players.push(await newPlayer(browser, n));
      await players[0].page.getByTestId('create-room').click();
      await players[0].page.getByTestId('room-code').waitFor({ timeout: 8000 });
      const code = (await players[0].page.getByTestId('room-code').textContent()).trim();
      for (const p of players.slice(1)) {
        await p.page.getByTestId('join-code').fill(code);
        await p.page.getByTestId('join-room').click();
        await p.page.getByTestId('room-code').waitFor({ timeout: 8000 });
      }
      for (const p of players) p.playerId = await playerIdOf(p);
      log(`room ${code} players=${roomCfg.names.join(',')}`);
      for (let k = 1; k <= roomCfg.games; k += 1) {
        gameNo += 1;
        await readyAllAndStart(players, code);
        const startState = await getState(code);
        const startCounts = startState.players.map((x) => x.hand_count);
        if (!startCounts.every((n) => n === 7)) finding('unexpected_start_hand', { game: gameNo, startCounts });
        await playOneGame(players, code, gameNo, roomCfg.reloadTestGame === k);
        await backToLobby(players, code, gameNo);
      }
      results.room_snapshots ??= [];
      results.room_snapshots.push(roomSnapshotStats(code));
      for (const p of players) await p.context.close();
    }
  } catch (e) {
    finding('driver_exception', { game: gameNo, error: String(e).split('\n').slice(0, 3).join(' | ') });
  } finally {
    await browser.close();
    results.finished_at = new Date().toISOString();
    results.error_banners = Object.fromEntries(errorTexts);
    const roomA = results.games.filter((game) => game.players.length === 3);
    if (roomA.length >= 6 && roomA[0].latency_ms.p50 && roomA[5].latency_ms.p50 > roomA[0].latency_ms.p50 * 1.5) {
      finding('room_a_latency_p50_rise', { game1_p50: roomA[0].latency_ms.p50, game6_p50: roomA[5].latency_ms.p50 });
    }
    results.summary = {
      games: results.games.length,
      finding_count: results.findings.length,
      english_banners: results.banner_language_counts.english,
      blind_card_retries: results.games.reduce((sum, game) => sum + game.blind_card_retries, 0),
      stalls: results.findings.filter((item) => item.kind === 'game_stalled').length,
      console_errors: results.console_errors.length,
      page_errors: results.page_errors.length,
      http_errors: results.http_errors.length,
    };
    writeFileSync(`${OUT_PATH}/results.json`, JSON.stringify(results, null, 2));
    log(`done games=${results.games.length} findings=${results.findings.length}`);
  }
}

main();
