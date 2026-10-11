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
  return result.body;
}

async function createStartedRoom(browser: Browser) {
  const hostContext = await browser.newContext({ viewport: { width: 1366, height: 768 } });
  const guestContext = await browser.newContext({ viewport: { width: 1366, height: 768 } });
  const hostPage = await hostContext.newPage();
  const guestPage = await guestContext.newPage();

  await hostPage.goto('/');
  await hostPage.getByLabel('昵称').fill('Draw Host');
  await hostPage.getByTestId('create-room').click();
  await expect(hostPage.getByTestId('room-code')).toHaveText(/^[A-Z0-9]{6}$/);
  const host = await storedSession(hostPage);

  await guestPage.goto('/');
  await guestPage.getByLabel('昵称').fill('Draw Guest');
  await guestPage.getByLabel('房间号').fill(host.room_code);
  await guestPage.getByTestId('join-room').click();
  await expect(guestPage.getByTestId('room-code')).toHaveText(host.room_code);
  const guest = await storedSession(guestPage);

  await hostPage.getByTestId('ready').click();
  await expect(guestPage.locator('.product-roster__seat').filter({ hasText: 'Draw Host' })).toContainText('已准备');
  await guestPage.getByTestId('ready').click();
  await expect(hostPage.getByTestId('start-game')).toBeEnabled();
  await hostPage.getByTestId('start-game').click();
  await expect(hostPage.getByTestId('hand-card')).toHaveCount(7);

  return { hostContext, guestContext, hostPage, guestPage, host, guest };
}

test('ordinary draw takes one card at a time and disables after a playable card', async ({ browser }) => {
  test.setTimeout(120_000);
  const room = await createStartedRoom(browser);
  const { hostContext, guestContext, hostPage, guestPage, host, guest } = room;

  try {
    await command(hostPage, host, 'TEST_SET_STATE', {
      hands: {
        [host.player_id]: ['uno_green_1'],
        [guest.player_id]: ['uno_yellow_2'],
      },
      current_player_id: host.player_id,
      discard_asset_key: 'uno_red_5',
      deck_asset_keys: ['uno_red_1', 'uno_blue_2', 'uno_green_3'],
    });
    await expect(hostPage.getByTestId('hand-card')).toHaveCount(1);

    const draw = hostPage.getByTestId('draw-card');
    await expect(draw).toBeEnabled();
    await draw.click();
    await expect(hostPage.getByTestId('hand-card')).toHaveCount(2);
    await expect(draw).toBeEnabled();

    await draw.click();
    await expect(hostPage.getByTestId('hand-card')).toHaveCount(3);
    await expect(draw).toBeEnabled();

    await draw.click();
    await expect(hostPage.getByTestId('hand-card')).toHaveCount(4);
    await expect(hostPage.locator('[data-testid="hand-card"][data-card-color="red"][data-card-value="1"] figure')).toHaveClass(/is-legal/);
    await expect(draw).toBeDisabled();
    await expect(hostPage.locator('.turn-panel')).toContainText('当前：Draw Host');

    const playable = hostPage.locator('[data-testid="hand-card"][data-card-color="red"][data-card-value="1"]');
    await playable.click();
    await expect(hostPage.getByTestId('play-selected')).toBeEnabled();
    await hostPage.getByTestId('play-selected').click();
    await expect(hostPage.locator('.turn-panel')).toContainText('当前：Draw Guest');
  } finally {
    await command(hostPage, host, 'CLOSE_ROOM').catch(() => undefined);
    await hostContext.close();
    await guestContext.close();
  }
});

test('draw-two stack only enables matching cards and acceptance keeps the responder turn', async ({ browser }) => {
  test.setTimeout(120_000);
  const room = await createStartedRoom(browser);
  const { hostContext, guestContext, hostPage, guestPage, host, guest } = room;

  try {
    await command(hostPage, host, 'TEST_SET_STATE', {
      hands: {
        [host.player_id]: ['uno_blue_draw_two', 'uno_blue_4'],
        [guest.player_id]: ['uno_yellow_5'],
      },
      current_player_id: host.player_id,
      discard_asset_key: 'uno_red_draw_two',
      deck_asset_keys: ['uno_red_0', 'uno_green_3', 'uno_yellow_7', 'uno_red_8'],
      action_stack: { kind: 'draw_two', count: 2 },
    });

    const matching = hostPage.locator('[data-testid="hand-card"][data-card-kind="draw_two"][data-card-color="blue"]');
    const unrelated = hostPage.locator('[data-testid="hand-card"][data-card-value="4"]');
    await expect(matching).toHaveCount(1);
    await expect(matching.locator('figure')).toHaveClass(/is-legal/);
    await expect(unrelated.locator('figure')).not.toHaveClass(/is-legal/);
    await expect(hostPage.getByTestId('draw-card')).toHaveCount(0);
    await expect(hostPage.getByTestId('accept-stack')).toHaveText('接受并摸 2 张');

    await matching.click();
    await hostPage.getByTestId('play-selected').click();
    await expect(guestPage.getByTestId('accept-stack')).toHaveText('接受并摸 4 张');
    await guestPage.getByTestId('accept-stack').click();

    await expect(guestPage.getByTestId('hand-card')).toHaveCount(5);
    await expect(guestPage.locator('.turn-panel')).toContainText('当前：Draw Guest');
    await expect(guestPage.getByTestId('draw-card')).toBeEnabled();
  } finally {
    await command(hostPage, host, 'CLOSE_ROOM').catch(() => undefined);
    await hostContext.close();
    await guestContext.close();
  }
});

test('wild draw-four stack asks for a color before stacking', async ({ browser }) => {
  test.setTimeout(120_000);
  const room = await createStartedRoom(browser);
  const { hostContext, guestContext, hostPage, guestPage, host, guest } = room;

  try {
    await command(hostPage, host, 'TEST_SET_STATE', {
      hands: {
        [host.player_id]: ['uno_wild_draw_four', 'uno_red_2'],
        [guest.player_id]: ['uno_blue_5'],
      },
      current_player_id: host.player_id,
      discard_asset_key: 'uno_red_draw_two',
      deck_asset_keys: ['uno_blue_0', 'uno_green_3', 'uno_yellow_7', 'uno_blue_8'],
      action_stack: { kind: 'wild_draw_four', count: 4 },
    });

    const matching = hostPage.locator('[data-testid="hand-card"][data-card-kind="wild_draw_four"]');
    const unrelated = hostPage.locator('[data-testid="hand-card"][data-card-color="red"]');
    await expect(matching.locator('figure')).toHaveClass(/is-legal/);
    await expect(unrelated.locator('figure')).not.toHaveClass(/is-legal/);
    await matching.click();
    await hostPage.getByRole('button', { name: '蓝色', exact: true }).click();
    await hostPage.getByTestId('play-selected').click();
    await expect(guestPage.getByTestId('accept-stack')).toHaveText('接受并摸 8 张');
  } finally {
    await command(hostPage, host, 'CLOSE_ROOM').catch(() => undefined);
    await hostContext.close();
    await guestContext.close();
  }
});
