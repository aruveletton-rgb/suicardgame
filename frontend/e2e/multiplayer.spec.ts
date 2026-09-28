import { expect, test, type Page } from '@playwright/test';

type StoredSession = {
  room_code: string;
  player_id: string;
  reconnect_token: string;
  session_id: string;
};

async function sessionFrom(page: Page): Promise<StoredSession> {
  return page.evaluate(() => JSON.parse(localStorage.getItem('suicardgame.session.v1') ?? '{}'));
}

async function setTestState(
  page: Page,
  host: StoredSession,
  hands: Record<string, string[]>,
  currentPlayerId: string,
  discardAssetKey: string,
) {
  const deckAssetKeys = [
    'uno_red_1',
    'uno_yellow_2',
    'uno_green_3',
    'uno_blue_4',
    'uno_red_6',
    'uno_yellow_7',
    'uno_green_8',
    'uno_blue_9',
    'uno_red_2',
    'uno_yellow_3',
    'uno_green_4',
    'uno_blue_5',
  ];
  const result = await page.evaluate(
    async ({ roomCode, playerId, sessionId, handsPayload, currentId, discard, deck }) => {
      const response = await fetch(`/api/v1/rooms/${roomCode}/commands`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${sessionId}`,
        },
        body: JSON.stringify({
          action_id: crypto.randomUUID(),
          player_id: playerId,
          command_type: 'TEST_SET_STATE',
          payload: {
            hands: handsPayload,
            current_player_id: currentId,
            discard_asset_key: discard,
            deck_asset_keys: deck,
          },
        }),
      });
      return { status: response.status, body: await response.json() };
    },
    {
      roomCode: host.room_code,
      playerId: host.player_id,
      sessionId: host.session_id,
      handsPayload: hands,
      currentId: currentPlayerId,
      discard: discardAssetKey,
      deck: deckAssetKeys,
    },
  );
  expect(result.status, JSON.stringify(result.body)).toBe(200);
}

async function selectCard(page: Page, kind: string) {
  const card = page.locator(`[data-testid="hand-card"][data-card-kind="${kind}"]`).first();
  await expect(card).toBeVisible();
  await card.click();
}

async function supportFirstCard(page: Page, kind: string) {
  await page.getByRole('button', { name: '多选牌', exact: true }).click();
  const card = page.locator(`[data-testid="hand-card"][data-card-kind="${kind}"]`).first();
  await expect(card).toBeVisible();
  await card.click();
}

async function passSuiReaction(hostPage: Page, guestPage: Page) {
  await expect(guestPage.getByTestId('pending-response-pass')).toBeVisible();
  await guestPage.getByTestId('pending-response-pass').click();
  await expect(hostPage.getByTestId('pending-response-pass')).toBeVisible();
  await hostPage.getByTestId('pending-response-pass').click();
}

async function declineHasSui(page: Page) {
  await expect(page.getByTestId('pending-response-decline_challenge')).toBeVisible();
  await page.getByTestId('pending-response-decline_challenge').click();
}

test('two players complete realtime UNO, pending actions, special card, and reconnect flow', async ({ browser }) => {
  const hostContext = await browser.newContext();
  const guestContext = await browser.newContext();
  const hostPage = await hostContext.newPage();
  const guestPage = await guestContext.newPage();
  const pageErrors: string[] = [];
  const consoleErrors: string[] = [];
  hostPage.on('pageerror', (error) => pageErrors.push(`host: ${error.message}`));
  guestPage.on('pageerror', (error) => pageErrors.push(`guest: ${error.message}`));
  hostPage.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(`host: ${message.text()}`);
  });
  guestPage.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(`guest: ${message.text()}`);
  });

  await hostPage.goto('/');
  await hostPage.getByLabel('昵称').fill('Host');
  await hostPage.getByTestId('create-room').click();
  const roomCode = (await hostPage.getByTestId('room-code').textContent())?.trim() ?? '';
  expect(roomCode).toHaveLength(6);

  await guestPage.goto('/');
  await guestPage.getByLabel('昵称').fill('Guest');
  await guestPage.getByLabel('房间号').fill(roomCode);
  await guestPage.getByTestId('join-room').click();
  await expect(guestPage.getByTestId('room-code')).toHaveText(roomCode);

  await hostPage.getByTestId('ready').click();
  await guestPage.getByTestId('ready').click();
  await expect(hostPage.locator('.seat').filter({ hasText: 'Host' })).toContainText('已准备');
  await expect(hostPage.locator('.seat').filter({ hasText: 'Guest' })).toContainText('已准备');
  await expect(hostPage.getByTestId('start-game')).toBeEnabled();
  await hostPage.getByTestId('start-game').click();
  await expect(hostPage.getByTestId('hand-card').first()).toBeVisible();

  const host = await sessionFrom(hostPage);
  const guest = await sessionFrom(guestPage);

  await setTestState(
    hostPage,
    host,
    {
      [host.player_id]: ['uno_wild_draw_four', 'uno_red_7', 'sui_ling'],
      [guest.player_id]: ['uno_blue_2', 'uno_green_3'],
    },
    host.player_id,
    'uno_red_5',
  );

  await selectCard(hostPage, 'wild_draw_four');
  await hostPage.getByRole('button', { name: '蓝色', exact: true }).click();
  await hostPage.getByTestId('play-selected').click();
  await expect(guestPage.getByTestId('pending-action')).toContainText('+4 质疑');
  await guestPage.getByTestId('pending-response-decline_challenge').click();
  await declineHasSui(guestPage);
  await expect(guestPage.getByTestId('pending-action')).toHaveCount(0);

  await hostPage.getByTestId('draw-card').click();
  await declineHasSui(guestPage);
  await expect(guestPage.getByTestId('draw-card')).toBeEnabled();

  await setTestState(
    hostPage,
    host,
    {
      [host.player_id]: ['uno_red_7', 'uno_blue_9'],
      [guest.player_id]: ['uno_blue_2', 'uno_green_3'],
    },
    host.player_id,
    'uno_red_5',
  );
  await selectCard(hostPage, 'number');
  await hostPage.getByTestId('play-selected').click();
  await expect(guestPage.getByTestId('catch-uno')).toBeVisible();
  await guestPage.getByTestId('catch-uno').click();
  await expect(hostPage.getByTestId('hand-card')).toHaveCount(3);

  await setTestState(
    hostPage,
    host,
    {
      [host.player_id]: ['uno_red_7', 'uno_blue_9'],
      [guest.player_id]: ['uno_blue_2', 'uno_green_3'],
    },
    host.player_id,
    'uno_red_5',
  );
  await hostPage.getByRole('button', { name: '随出牌宣告 UNO', exact: true }).click();
  await selectCard(hostPage, 'number');
  await hostPage.getByTestId('play-selected').click();
  await expect(guestPage.getByTestId('catch-uno')).toHaveCount(0);

  await setTestState(
    hostPage,
    host,
    {
      [host.player_id]: ['sui_ling'],
      [guest.player_id]: ['uno_blue_2', 'uno_green_3', 'uno_yellow_4'],
    },
    host.player_id,
    'uno_red_5',
  );
  await selectCard(hostPage, 'ling');
  await hostPage.getByTestId('play-selected').click();
  await passSuiReaction(hostPage, guestPage);
  await expect(hostPage.getByTestId('hand-card')).toHaveCount(3);

  await setTestState(
    hostPage,
    host,
    {
      [host.player_id]: ['sui_nian', 'uno_red_7'],
      [guest.player_id]: ['uno_blue_2', 'uno_green_3'],
    },
    host.player_id,
    'uno_red_5',
  );
  await selectCard(hostPage, 'nian');
  await hostPage.getByTestId('play-selected').click();
  await expect(hostPage.getByTestId('special-prompt-card')).toContainText('年牌');
  await selectCard(hostPage, 'number');
  await hostPage.getByTestId('pending-response-discard_card').click();

  await setTestState(
    hostPage,
    host,
    {
      [host.player_id]: ['sui_sui_xiang'],
      [guest.player_id]: ['uno_blue_2'],
    },
    host.player_id,
    'uno_red_5',
  );
  await selectCard(hostPage, 'sui_xiang');
  await hostPage.getByTestId('play-selected').click();
  await expect(hostPage.getByTestId('special-prompt-card')).toContainText('岁相牌');
  await hostPage.getByTestId('pending-response-draw_four').click();
  await supportFirstCard(guestPage, 'number');
  await guestPage.getByTestId('pending-response-submit_cards').click();

  await setTestState(
    hostPage,
    host,
    {
      [host.player_id]: ['sui_chongyue', 'uno_red_1'],
      [guest.player_id]: ['uno_red_2', 'uno_yellow_2', 'uno_green_2', 'uno_blue_2'],
    },
    host.player_id,
    'uno_red_5',
  );
  await selectCard(hostPage, 'chongyue');
  await hostPage.getByTestId('play-selected').click();
  await passSuiReaction(hostPage, guestPage);
  await expect(guestPage.getByTestId('special-prompt-card')).toContainText('重岳牌');
  await guestPage.getByTestId('pending-response-decline_challenge').click();

  await setTestState(
    hostPage,
    host,
    {
      [host.player_id]: ['sui_wang'],
      [guest.player_id]: ['uno_blue_2'],
    },
    guest.player_id,
    'uno_red_5',
  );
  await selectCard(hostPage, 'wang');
  await hostPage.getByRole('group', { name: '目标' }).getByRole('button', { name: 'Guest', exact: true }).click();
  await hostPage.getByTestId('play-selected').click();
  await passSuiReaction(hostPage, guestPage);
  await expect(hostPage.getByTestId('special-prompt-card')).toContainText('望牌');
  await hostPage.getByTestId('pending-response-control_pass').click();

  await setTestState(
    hostPage,
    host,
    {
      [host.player_id]: ['sui_fuzhou'],
      [guest.player_id]: ['uno_red_2'],
    },
    host.player_id,
    'uno_red_5',
  );
  await selectCard(hostPage, 'fuzhou');
  await hostPage.getByTestId('play-selected').click();
  await expect(guestPage.getByTestId('special-prompt-card')).toContainText('符咒牌');
  await selectCard(guestPage, 'number');
  await guestPage.getByTestId('pending-response-give_card').click();

  await guestPage.reload();
  await expect(guestPage.getByTestId('room-code')).toHaveText(roomCode);
  await expect(guestPage.getByText('已恢复上次牌局')).toBeVisible();

  await setTestState(
    hostPage,
    host,
    {
      [host.player_id]: ['uno_red_7', 'uno_red_8', 'uno_red_9'],
      [guest.player_id]: ['uno_blue_2', 'uno_blue_3', 'uno_blue_4'],
    },
    guest.player_id,
    'uno_blue_5',
  );
  await selectCard(guestPage, 'number');
  await guestPage.getByTestId('play-selected').click();
  await hostPage.getByTestId('draw-card').click();
  await selectCard(guestPage, 'number');
  await guestPage.getByTestId('play-selected').click();

  expect(pageErrors).toEqual([]);
  expect(consoleErrors).toEqual([]);
  await hostContext.close();
  await guestContext.close();
});
