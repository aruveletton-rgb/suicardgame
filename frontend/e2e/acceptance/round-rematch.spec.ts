import { expect, test, type Browser, type Page } from '@playwright/test';

type Session = {
  room_code: string;
  player_id: string;
  session_id: string;
};

async function storedSession(page: Page): Promise<Session> {
  await expect.poll(async () => {
    const raw = await page.evaluate(() => localStorage.getItem('suicardgame.session.v1'));
    return raw ? (JSON.parse(raw) as Partial<Session>).player_id ?? '' : '';
  }).not.toBe('');
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

async function createStartedRoom(browser: Browser) {
  const hostContext = await browser.newContext({ viewport: { width: 1366, height: 768 } });
  const guestContext = await browser.newContext({ viewport: { width: 1366, height: 768 } });
  const hostPage = await hostContext.newPage();
  const guestPage = await guestContext.newPage();

  await hostPage.goto('/');
  await hostPage.getByLabel('昵称').fill('Host');
  await hostPage.getByTestId('create-room').click();
  await expect(hostPage.getByTestId('room-code')).toHaveText(/^[A-Z0-9]{6}$/);
  const host = await storedSession(hostPage);

  await guestPage.goto('/');
  await guestPage.getByLabel('昵称').fill('Guest');
  await guestPage.getByLabel('房间号').fill(host.room_code);
  await guestPage.getByTestId('join-room').click();
  await expect(guestPage.getByTestId('room-code')).toHaveText(host.room_code);
  const guest = await storedSession(guestPage);

  await hostPage.getByTestId('ready').click();
  await expect(guestPage.locator('.product-roster__seat').filter({ hasText: 'Host' })).toContainText('已准备');
  await guestPage.getByTestId('ready').click();
  await expect(hostPage.getByTestId('start-game')).toBeEnabled();
  await hostPage.getByTestId('start-game').click();
  await expect(hostPage.getByTestId('hand-card').first()).toBeVisible();
  await expect(guestPage.getByTestId('hand-card').first()).toBeVisible();

  return { hostContext, guestContext, hostPage, guestPage, host, guest };
}

test('winner rematches through UI and every seated player must ready again', async ({ browser }) => {
  const room = await createStartedRoom(browser);
  const { hostContext, guestContext, hostPage, guestPage, host, guest } = room;
  try {
    await command(hostPage, host, 'TEST_SET_STATE', {
      hands: {
        [host.player_id]: ['uno_red_7'],
        [guest.player_id]: ['uno_blue_2', 'uno_green_3'],
      },
      current_player_id: host.player_id,
      discard_asset_key: 'uno_red_5',
      deck_asset_keys: ['uno_yellow_1', 'uno_blue_4'],
    });

    await hostPage.locator('[data-testid="hand-card"][data-card-color="red"]').click();
    await hostPage.getByTestId('play-selected').click();

    await expect(hostPage.getByTestId('game-result')).toContainText('Host 获胜');
    await expect(guestPage.getByTestId('game-result')).toContainText('Host 获胜');
    await expect(hostPage.getByTestId('game-result')).toContainText('Host');
    await expect(hostPage.getByTestId('game-result')).toContainText('0 张');

    await hostPage.getByRole('button', { name: '再来一局' }).click();
    await expect(hostPage.getByTestId('game-result')).toHaveCount(0);
    await expect(guestPage.getByTestId('game-result')).toHaveCount(0);
    await expect(hostPage.getByTestId('start-game')).toBeDisabled();
    await expect(hostPage.locator('.product-roster__seat').filter({ hasText: 'Host' })).toContainText('未准备');
    await expect(hostPage.locator('.product-roster__seat').filter({ hasText: 'Guest' })).toContainText('未准备');

    await hostPage.getByTestId('ready').click();
    await expect(guestPage.locator('.product-roster__seat').filter({ hasText: 'Host' })).toContainText('已准备');
    await guestPage.getByTestId('ready').click();
    await expect(hostPage.locator('.product-roster__seat').filter({ hasText: 'Guest' })).toContainText('已准备');
    await expect(hostPage.getByTestId('start-game')).toBeEnabled();
    await hostPage.getByTestId('start-game').click();
    await expect(hostPage.getByTestId('hand-card')).toHaveCount(7);
    await expect(guestPage.getByTestId('hand-card')).toHaveCount(7);
  } finally {
    await hostContext.close();
    await guestContext.close();
  }
});
