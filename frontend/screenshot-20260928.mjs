import { chromium } from 'playwright';
import { mkdir } from 'node:fs/promises';

const api = 'http://127.0.0.1:8122/api/v1';
const web = 'http://127.0.0.1:5174';
const output = '../artifacts/screenshots/20260928';

async function json(path, init) {
  const response = await fetch(`${api}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  });
  const body = await response.json();
  if (!response.ok) throw new Error(`${response.status}: ${JSON.stringify(body)}`);
  return body;
}

async function command(session, commandType, payload = {}, actionId = `${commandType}-${Date.now()}-${Math.random()}`) {
  return json(`/rooms/${session.room_code}/commands`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${session.session_id}` },
    body: JSON.stringify({ action_id: actionId, player_id: session.player_id, command_type: commandType, payload }),
  });
}

async function pageFor(browser, session, viewport) {
  const context = await browser.newContext({ viewport });
  await context.addInitScript((saved) => localStorage.setItem('suicardgame.session.v1', JSON.stringify(saved)), session);
  const page = await context.newPage();
  await page.goto(web, { waitUntil: 'networkidle' });
  await page.getByTestId('room-code').waitFor();
  return { context, page };
}

async function storedSession(page) {
  return page.evaluate(() => JSON.parse(localStorage.getItem('suicardgame.session.v1')));
}

await mkdir(output, { recursive: true });
const browser = await chromium.launch({ headless: true });
const entry = await browser.newPage({ viewport: { width: 1366, height: 768 } });
await entry.goto(web, { waitUntil: 'networkidle' });
await entry.screenshot({ path: `${output}/01-home-desktop.png` });
await entry.close();

const lobbyHost = await json('/rooms', { method: 'POST', body: JSON.stringify({ nickname: '演示房主' }) });
const lobbyGuest = await json(`/rooms/${lobbyHost.room_code}/join`, { method: 'POST', body: JSON.stringify({ nickname: '演示玩家' }) });
const lobby = await pageFor(browser, lobbyHost, { width: 1366, height: 768 });
await lobby.page.screenshot({ path: `${output}/02-lobby-desktop.png` });
await lobby.context.close();

const host = await json('/rooms', { method: 'POST', body: JSON.stringify({ nickname: '终端房主' }) });
const guest = await json(`/rooms/${host.room_code}/join`, { method: 'POST', body: JSON.stringify({ nickname: '终端玩家' }) });
await command(guest, 'READY', { ready: true }, 'ready-guest');
await command(host, 'READY', { ready: true }, 'ready-host');
await command(host, 'START_GAME', { seed: 904 }, 'start-game');
const hostDesktop = await pageFor(browser, host, { width: 1366, height: 768 });
const guestMobile = await pageFor(browser, guest, { width: 390, height: 844 });
await hostDesktop.page.screenshot({ path: `${output}/03-table-desktop.png` });
await guestMobile.page.screenshot({ path: `${output}/04-table-portrait.png` });

await hostDesktop.page.setViewportSize({ width: 844, height: 390 });
await hostDesktop.page.screenshot({ path: `${output}/05-table-landscape.png` });
await hostDesktop.page.setViewportSize({ width: 1366, height: 768 });

const currentHost = await storedSession(hostDesktop.page);
await command(currentHost, 'TEST_OPEN_RESPONSE_WINDOW', {
  responder_ids: [guest.player_id],
  resolution_policy: 'first_wins',
  timeout_seconds: 30,
  private_options_by_responder: { [guest.player_id]: ['accept', 'decline'] },
}, 'open-response');

await hostDesktop.page.getByRole('button', { name: /图鉴/ }).first().click();
await hostDesktop.page.screenshot({ path: `${output}/06-rules-drawer.png` });
await hostDesktop.page.getByRole('button', { name: /关闭图鉴/ }).click();

const shopToggle = hostDesktop.page.getByRole('button', { name: /展开/ });
if (await shopToggle.count()) {
  await shopToggle.click();
  await hostDesktop.page.screenshot({ path: `${output}/07-shop-open.png` });
}

await guestMobile.page.screenshot({ path: `${output}/08-response-prompt.png` });

const freshHost = await storedSession(hostDesktop.page);
await command(freshHost, 'TEST_SET_STATE', {
  current_player_id: host.player_id,
  discard_asset_key: 'uno_red_5',
  hands: { [host.player_id]: ['uno_red_7'], [guest.player_id]: ['uno_blue_2'] },
  deck_asset_keys: ['uno_green_1'],
}, 'finish-state');
await hostDesktop.page.getByTestId('hand-card').first().waitFor();
await hostDesktop.page.getByTestId('hand-card').first().click();
await hostDesktop.page.getByTestId('play-selected').click();
await hostDesktop.page.waitForTimeout(250);
await hostDesktop.page.screenshot({ path: `${output}/09-result.png` });

await guestMobile.context.close();
await hostDesktop.context.close();
await browser.close();
console.log(`screenshots written to ${output}`);
