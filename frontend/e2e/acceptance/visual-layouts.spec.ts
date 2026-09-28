import { expect, test, type Page } from '@playwright/test';

type Session = {
  room_code: string;
  player_id: string;
  session_id: string;
};

async function storedSession(page: Page): Promise<Session> {
  return page.evaluate(() => JSON.parse(localStorage.getItem('suicardgame.session.v1') ?? '{}'));
}

async function command(page: Page, session: Session, commandType: string, payload: Record<string, unknown> = {}) {
  const result = await page.evaluate(async ({ session, commandType, payload }) => {
    const response = await fetch(`/api/v1/rooms/${session.room_code}/commands`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${session.session_id}` },
      body: JSON.stringify({
        action_id: crypto.randomUUID(),
        player_id: session.player_id,
        command_type: commandType,
        payload,
      }),
    });
    return { status: response.status, body: await response.json() };
  }, { session, commandType, payload });
  expect(result.status, JSON.stringify(result.body)).toBe(200);
}

async function createFivePlayerRoom(page: Page) {
  await page.goto('/');
  await page.getByLabel('昵称').fill('Host');
  await page.getByTestId('create-room').click();
  await expect(page.getByTestId('room-code')).toHaveText(/^[A-Z0-9]{6}$/);
  await expect.poll(async () => (await storedSession(page)).player_id).toBeTruthy();
  const host = await storedSession(page);
  const guests: Session[] = [];
  for (let index = 1; index <= 4; index += 1) {
    const guest = await page.evaluate(async ({ roomCode, index }) => {
      const response = await fetch(`/api/v1/rooms/${roomCode}/join`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ nickname: `Guest ${index}` }),
      });
      return response.json();
    }, { roomCode: host.room_code, index }) as Session;
    guests.push(guest);
  }
  for (const player of [host, ...guests]) await command(page, player, 'READY', { ready: true });
  await expect(page.locator('.product-roster__seat')).toHaveCount(5);
  await expect(page.getByTestId('start-game')).toBeEnabled();
  await page.getByTestId('start-game').click();
  await expect(page.getByTestId('hand-card').first()).toBeVisible();
  return { host, guests };
}

test('captures current desktop, portrait, and landscape layouts', async ({ page }) => {
  test.setTimeout(90_000);
  await page.setViewportSize({ width: 1366, height: 768 });
  const { host, guests } = await createFivePlayerRoom(page);

  const desktopHand = [
    'uno_red_0', 'uno_red_1', 'uno_red_2', 'uno_red_3', 'uno_red_4',
    'uno_yellow_0', 'uno_yellow_1', 'uno_yellow_2', 'uno_yellow_3', 'uno_yellow_4',
    'uno_green_0', 'uno_green_1', 'uno_green_2', 'uno_green_3', 'uno_green_4',
    'uno_blue_0', 'uno_blue_1', 'uno_blue_2', 'uno_blue_3', 'uno_blue_4',
    'uno_red_skip', 'uno_yellow_reverse', 'uno_green_draw_two', 'uno_wild', 'sui_yi',
  ];
  await command(page, host, 'TEST_SET_STATE', {
    hands: {
      [host.player_id]: desktopHand,
      [guests[0].player_id]: ['uno_green_6'],
      [guests[1].player_id]: ['uno_blue_6'],
      [guests[2].player_id]: ['uno_yellow_6'],
      [guests[3].player_id]: ['uno_red_6'],
    },
    current_player_id: host.player_id,
    discard_asset_key: 'uno_yellow_4',
    deck_asset_keys: ['uno_red_7', 'uno_blue_7', 'uno_green_7', 'uno_yellow_7'],
  });
  await expect(page.getByTestId('hand-card')).toHaveCount(25);
  await expect(page.locator('.shop-area')).toBeVisible();
  await expect(page.locator('.shop-row .card-button').first()).toBeVisible();
  await page.screenshot({ path: '../artifacts/acceptance/layout-desktop-1366x768.png' });

  await command(page, host, 'TEST_SET_STATE', {
    hands: {
      [host.player_id]: ['uno_wild', 'uno_red_3', 'uno_blue_5', 'sui_yi', 'uno_green_6', 'uno_yellow_7', 'uno_red_8'],
      [guests[0].player_id]: ['uno_green_6'],
      [guests[1].player_id]: ['uno_blue_6'],
      [guests[2].player_id]: ['uno_yellow_6'],
      [guests[3].player_id]: ['uno_red_6'],
    },
    current_player_id: host.player_id,
    discard_asset_key: 'uno_yellow_4',
    deck_asset_keys: ['uno_red_1', 'uno_blue_2', 'uno_green_3'],
  });

  await page.setViewportSize({ width: 360, height: 640 });
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'auto' }));
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0);
  await page.screenshot({ path: '../artifacts/acceptance/layout-portrait-360x640-top.png' });
  await page.getByRole('button', { name: '主牌', exact: true }).click();
  await page.locator('[data-testid="hand-card"][data-card-kind="wild"]').click();
  await page.getByRole('button', { name: '蓝色', exact: true }).click();
  await page.getByRole('button', { name: '多选牌', exact: true }).click();
  await page.locator('[data-testid="hand-card"][data-card-value="3"]').click();
  await page.locator('[data-testid="hand-card"][data-card-value="5"]').click();
  await page.locator('.shop-toggle').click();
  await expect(page.getByRole('button', { name: '确认出牌 / 发动' })).toBeVisible();
  await page.screenshot({ path: '../artifacts/acceptance/layout-portrait-360x640.png' });

  await page.setViewportSize({ width: 844, height: 390 });
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'auto' }));
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0);
  await page.screenshot({ path: '../artifacts/acceptance/layout-landscape-844x390-top.png' });
  await expect(page.getByRole('button', { name: '蓝色', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('.selection-summary')).toContainText('多选 2 张');
  await page.screenshot({ path: '../artifacts/acceptance/layout-landscape-844x390.png' });
});
