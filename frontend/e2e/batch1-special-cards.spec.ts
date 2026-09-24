import { expect, test, type Page } from '@playwright/test';

type StoredSession = {
  room_code: string;
  player_id: string;
  reconnect_token: string;
  session_id: string;
};

type JoinedPlayer = StoredSession & {
  seat_index: number;
  is_host: boolean;
};

const TEXT = {
  nickname: '\u6635\u79f0',
  cardCountSuffix: '\u5f20',
  yiHint: '\u5f03\u7f6e\u4e24\u5f20\u6570\u5b57\u724c\uff0c\u70b9\u6570\u4e4b\u548c\u5fc5\u987b\u4e3a 8',
  yiOtherDraw: '\u5176\u4ed6\u73a9\u5bb6\u5404\u6478 1 \u5f20',
  yiError: '\u6613\u724c\u9700\u8981\u9009\u62e9\u4e24\u5f20\u6570\u5b57\u724c\uff0c\u4e14\u70b9\u6570\u4e4b\u548c\u5fc5\u987b\u4e3a 8',
  yiSuccess: '\u6613\u724c\u751f\u6548\uff1a\u5176\u4ed6\u73a9\u5bb6\u5404\u6478 1 \u5f20\u3002',
  lingLowHand: '\u4f4e\u4e8e\u5f53\u524d\u6700\u5927\u624b\u724c\u6570',
  lingNoTarget: '\u4e0d\u9700\u8981\u76ee\u6807\u6216\u9644\u52a0\u9009\u62e9',
  lingSuccess: '\u4ee4\u724c\u751f\u6548\uff1a\u6240\u6709\u73a9\u5bb6\u624b\u724c\u6570\u8865\u9f50\u81f3\u5f53\u524d\u6700\u5927\u503c\u3002',
};

async function sessionFrom(page: Page): Promise<StoredSession> {
  return page.evaluate(() => JSON.parse(localStorage.getItem('suicardgame.session.v1') ?? '{}'));
}

async function joinByApi(page: Page, roomCode: string, nickname: string): Promise<JoinedPlayer> {
  return page.evaluate(
    async ({ code, name }) => {
      const response = await fetch(`/api/v1/rooms/${code}/join`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ nickname: name }),
      });
      if (!response.ok) throw new Error(`join failed: ${response.status}`);
      return response.json();
    },
    { code: roomCode, name: nickname },
  );
}

async function commandByApi(page: Page, session: StoredSession, commandType: string, payload: Record<string, unknown> = {}) {
  const result = await page.evaluate(
    async ({ roomCode, playerId, sessionId, type, commandPayload }) => {
      const response = await fetch(`/api/v1/rooms/${roomCode}/commands`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${sessionId}`,
        },
        body: JSON.stringify({
          action_id: crypto.randomUUID(),
          player_id: playerId,
          command_type: type,
          payload: commandPayload,
        }),
      });
      return { status: response.status };
    },
    {
      roomCode: session.room_code,
      playerId: session.player_id,
      sessionId: session.session_id,
      type: commandType,
      commandPayload: payload,
    },
  );
  expect(result.status).toBe(200);
}

async function setTestState(
  page: Page,
  host: StoredSession,
  hands: Record<string, string[]>,
  currentPlayerId: string,
) {
  await commandByApi(page, host, 'TEST_SET_STATE', {
    hands,
    current_player_id: currentPlayerId,
    discard_asset_key: 'uno_red_5',
    deck_asset_keys: [
      'uno_blue_1',
      'uno_green_2',
      'uno_yellow_3',
      'uno_red_4',
      'uno_blue_6',
      'uno_yellow_7',
      'uno_green_8',
      'uno_red_9',
      'uno_blue_4',
      'uno_green_5',
      'uno_yellow_6',
      'uno_red_7',
    ],
  });
}

async function createStartedRoom(page: Page) {
  await page.goto('/');
  await page.getByLabel(TEXT.nickname).fill('Host');
  await page.getByTestId('create-room').click();
  const roomCode = (await page.getByTestId('room-code').textContent())?.trim() ?? '';
  expect(roomCode).toHaveLength(6);

  const guestA = await joinByApi(page, roomCode, 'Guest A');
  const guestB = await joinByApi(page, roomCode, 'Guest B');
  await expect(page.locator('.seat')).toHaveCount(3);

  const host = await sessionFrom(page);
  await commandByApi(page, guestA, 'READY', { ready: true });
  await commandByApi(page, guestB, 'READY', { ready: true });
  await page.getByTestId('start-game').click();
  await expect(page.getByTestId('hand-card').first()).toBeVisible();
  return { host, guestA, guestB };
}

async function selectCard(page: Page, kind: string) {
  const card = page.locator(`[data-testid="hand-card"][data-card-kind="${kind}"]`).first();
  await expect(card).toBeVisible();
  await card.click();
}

async function toggleNumberSupport(page: Page, value: number) {
  const item = page
    .locator('.hand-item')
    .filter({ has: page.locator(`[data-testid="hand-card"][data-card-category="number"][data-card-value="${value}"]`) })
    .first();
  await expect(item).toBeVisible();
  const checkbox = item.locator('.support-choice input');
  if (await checkbox.isChecked()) {
    await checkbox.uncheck();
  } else {
    await checkbox.check();
  }
}

async function expectSeatCount(page: Page, nickname: string, count: number) {
  await expect(page.locator('.seat').filter({ hasText: nickname })).toContainText(`${count} ${TEXT.cardCountSuffix}`);
}

test('yi shows guidance, rejects invalid support, applies valid sum-eight effect, and keeps other hands private', async ({ page }) => {
  const { host, guestA, guestB } = await createStartedRoom(page);
  await setTestState(
    page,
    host,
    {
      [host.player_id]: ['sui_yi', 'uno_red_3', 'uno_blue_6', 'uno_blue_5', 'uno_yellow_9'],
      [guestA.player_id]: ['uno_green_1'],
      [guestB.player_id]: ['uno_yellow_2'],
    },
    host.player_id,
  );

  await selectCard(page, 'yi');
  await expect(page.getByTestId('batch1-special-hint')).toContainText(TEXT.yiHint);
  await expect(page.getByTestId('batch1-special-hint')).toContainText(TEXT.yiOtherDraw);

  await toggleNumberSupport(page, 3);
  await toggleNumberSupport(page, 6);
  await page.getByTestId('play-selected').click();
  await expect(page.getByTestId('error-banner')).toContainText(TEXT.yiError);
  await expectSeatCount(page, 'Guest A', 1);
  await expectSeatCount(page, 'Guest B', 1);

  await toggleNumberSupport(page, 6);
  await toggleNumberSupport(page, 5);
  await page.getByTestId('play-selected').click();
  await expect(page.locator('.status-strip')).toContainText(TEXT.yiSuccess);
  await expectSeatCount(page, 'Guest A', 2);
  await expectSeatCount(page, 'Guest B', 2);
  await expect(page.getByTestId('hand-card')).toHaveCount(2);
  await expect(page.locator('.players-rail')).not.toContainText('uno_');
});

test('ling shows no-target guidance, equalizes to snapshot max, and keeps other hands private', async ({ page }) => {
  const { host, guestA, guestB } = await createStartedRoom(page);
  await setTestState(
    page,
    host,
    {
      [host.player_id]: ['sui_ling', 'uno_red_1'],
      [guestA.player_id]: ['uno_red_2', 'uno_blue_3', 'uno_green_4', 'uno_yellow_5'],
      [guestB.player_id]: ['uno_green_1'],
    },
    host.player_id,
  );

  await selectCard(page, 'ling');
  await expect(page.getByTestId('batch1-special-hint')).toContainText(TEXT.lingLowHand);
  await expect(page.getByTestId('batch1-special-hint')).toContainText(TEXT.lingNoTarget);
  await page.getByTestId('play-selected').click();
  await expect(page.locator('.status-strip')).toContainText(TEXT.lingSuccess);
  await expectSeatCount(page, 'Guest A', 4);
  await expectSeatCount(page, 'Guest B', 4);
  await expect(page.getByTestId('hand-card')).toHaveCount(4);
  await expect(page.locator('.players-rail')).not.toContainText('uno_');
});
