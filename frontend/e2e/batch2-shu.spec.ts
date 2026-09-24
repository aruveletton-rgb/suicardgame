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
  shuHint: '\u9009\u62e9\u4e00\u79cd\u989c\u8272\uff0c\u5c06\u4f60\u624b\u4e2d\u8be5\u989c\u8272\u7684\u6240\u6709\u724c\u5e73\u5747\u5206\u7ed9\u5176\u4ed6\u73a9\u5bb6\uff1b\u82e5\u6709\u5269\u4f59\uff0c\u4ea4\u7ed9\u624b\u724c\u6700\u5c11\u7684\u73a9\u5bb6\u4e4b\u4e00\u3002',
  shuTooFew: '\u9ecd\u724c\u9009\u62e9\u7684\u989c\u8272\u6570\u91cf\u4e0d\u8db3',
  shuNeedRemainder: '\u9ecd\u724c\u6709\u4f59\u724c\u4e14\u5e76\u5217\u6700\u5c11\uff0c\u8bf7\u9009\u62e9\u4f59\u724c\u63a5\u6536\u73a9\u5bb6',
  shuSuccess: '\u9ecd\u724c\u751f\u6548\uff1a\u5df2\u5c06\u6240\u9009\u989c\u8272\u724c\u5206\u7ed9\u5176\u4ed6\u73a9\u5bb6\u3002',
  remainderLabel: '\u4f59\u724c\u7ed9',
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

async function createStartedRoom(page: Page, playerCount = 3) {
  await page.goto('/');
  await page.getByLabel(TEXT.nickname).fill('Host');
  await page.getByTestId('create-room').click();
  const roomCode = (await page.getByTestId('room-code').textContent())?.trim() ?? '';
  expect(roomCode).toHaveLength(6);

  const guests: JoinedPlayer[] = [];
  for (let index = 1; index < playerCount; index += 1) {
    guests.push(await joinByApi(page, roomCode, `Guest ${String.fromCharCode(64 + index)}`));
  }
  await expect(page.locator('.seat')).toHaveCount(playerCount);

  const host = await sessionFrom(page);
  for (const guest of guests) {
    await commandByApi(page, guest, 'READY', { ready: true });
  }
  await page.getByTestId('start-game').click();
  await expect(page.getByTestId('hand-card').first()).toBeVisible();
  return { host, guests };
}

async function selectCard(page: Page, kind: string) {
  const card = page.locator(`[data-testid="hand-card"][data-card-kind="${kind}"]`).first();
  await expect(card).toBeVisible();
  await card.click();
}

async function chooseColor(page: Page, color: string) {
  await page.getByLabel('\u989c\u8272').selectOption(color);
}

async function expectSeatCount(page: Page, nickname: string, count: number) {
  await expect(page.locator('.seat').filter({ hasText: nickname })).toContainText(`${count} ${TEXT.cardCountSuffix}`);
}

type PublicStateSummary = {
  stateVersion: number;
  phase: string;
  currentPlayerId: string;
  direction: number;
  discardCount: number;
  status: string;
  winnerPlayerId: string | null;
  unoPendingPlayerId: string | null;
  players: Array<{ playerId: string; nickname: string; handCount: number }>;
};

async function publicStateSummary(page: Page, roomCode: string): Promise<PublicStateSummary> {
  return page.evaluate(async (code) => {
    const response = await fetch(`/api/v1/rooms/${code}/state`);
    if (!response.ok) throw new Error(`state failed: ${response.status}`);
    const state = await response.json();
    return {
      stateVersion: state.state_version,
      phase: state.phase,
      currentPlayerId: state.active_game.current_player_id,
      direction: state.active_game.direction,
      discardCount: state.active_game.discard_count,
      status: state.active_game.status,
      winnerPlayerId: state.active_game.winner_player_id,
      unoPendingPlayerId: state.active_game.uno.pending_player_id,
      players: state.players.map((player: Record<string, unknown>) => ({
        playerId: player.player_id,
        nickname: player.nickname,
        handCount: player.hand_count,
      })),
    };
  }, roomCode);
}

function handCount(summary: PublicStateSummary, nickname: string): number {
  const player = summary.players.find((item) => item.nickname === nickname);
  if (!player) throw new Error(`missing player: ${nickname}`);
  return player.handCount;
}

test('shu three-player even distribution has no remainder and keeps other hands private', async ({ page }) => {
  const { host, guests } = await createStartedRoom(page);
  const [guestA, guestB] = guests;
  await setTestState(
    page,
    host,
    {
      [host.player_id]: ['sui_shu', 'uno_red_1', 'uno_red_2', 'uno_red_3', 'uno_red_4', 'uno_blue_9'],
      [guestA.player_id]: ['uno_green_1'],
      [guestB.player_id]: ['uno_yellow_2'],
    },
    host.player_id,
  );

  const before = await publicStateSummary(page, host.room_code);
  expect(before.players).toHaveLength(3);
  expect(before.currentPlayerId).toBe(host.player_id);
  expect(handCount(before, 'Host')).toBe(6);
  expect(handCount(before, 'Guest A')).toBe(1);
  expect(handCount(before, 'Guest B')).toBe(1);

  await selectCard(page, 'shu');
  await expect(page.getByTestId('batch1-special-hint')).toContainText(TEXT.shuHint);
  await expect(page.getByLabel('\u989c\u8272')).toBeVisible();
  await chooseColor(page, 'red');
  await expect(page.getByLabel(TEXT.remainderLabel)).toHaveCount(0);
  await page.getByTestId('play-selected').click();
  await expect(page.locator('.status-strip')).toContainText(TEXT.shuSuccess);
  await expectSeatCount(page, 'Guest A', 3);
  await expectSeatCount(page, 'Guest B', 3);
  await expect(page.getByTestId('hand-card')).toHaveCount(1);
  await expect(page.locator('.players-rail')).not.toContainText('uno_');

  const after = await publicStateSummary(page, host.room_code);
  expect(after.players).toHaveLength(3);
  expect(after.stateVersion).toBe(before.stateVersion + 1);
  expect(after.currentPlayerId).toBe(guestA.player_id);
  expect(after.discardCount).toBe(before.discardCount + 1);
  expect(handCount(after, 'Host')).toBe(1);
  expect(handCount(after, 'Guest A')).toBe(3);
  expect(handCount(after, 'Guest B')).toBe(3);
});

test('shu three-player unique-fewest remainder is automatic without a selector', async ({ page }) => {
  const { host, guests } = await createStartedRoom(page);
  const [guestA, guestB] = guests;
  await setTestState(
    page,
    host,
    {
      [host.player_id]: ['sui_shu', 'uno_red_1', 'uno_red_2', 'uno_red_3', 'uno_red_4', 'uno_red_6', 'uno_blue_9'],
      [guestA.player_id]: ['uno_green_1'],
      [guestB.player_id]: ['uno_yellow_2', 'uno_blue_2', 'uno_green_3'],
    },
    host.player_id,
  );

  const before = await publicStateSummary(page, host.room_code);
  expect(before.players).toHaveLength(3);
  expect(handCount(before, 'Guest A')).toBe(1);
  expect(handCount(before, 'Guest B')).toBe(3);

  await selectCard(page, 'shu');
  await chooseColor(page, 'red');
  await expect(page.getByLabel(TEXT.remainderLabel)).toHaveCount(0);
  await page.getByTestId('play-selected').click();
  await expect(page.locator('.status-strip')).toContainText(TEXT.shuSuccess);
  await expectSeatCount(page, 'Guest A', 4);
  await expectSeatCount(page, 'Guest B', 5);
  await expect(page.getByTestId('hand-card')).toHaveCount(1);
  await expect(page.locator('.players-rail')).not.toContainText('uno_');

  const after = await publicStateSummary(page, host.room_code);
  expect(after.players).toHaveLength(3);
  expect(after.stateVersion).toBe(before.stateVersion + 1);
  expect(after.currentPlayerId).toBe(guestA.player_id);
  expect(after.discardCount).toBe(before.discardCount + 1);
  expect(handCount(after, 'Host')).toBe(1);
  expect(handCount(after, 'Guest A')).toBe(4);
  expect(handCount(after, 'Guest B')).toBe(5);
});

test('shu three-player tied-fewest selector offers only legal recipients and settles once', async ({ page }) => {
  const { host, guests } = await createStartedRoom(page);
  const [guestA, guestB] = guests;
  await setTestState(
    page,
    host,
    {
      [host.player_id]: ['sui_shu', 'uno_red_1', 'uno_red_2', 'uno_red_3', 'uno_red_4', 'uno_red_6', 'uno_blue_9'],
      [guestA.player_id]: ['uno_green_1'],
      [guestB.player_id]: ['uno_yellow_2'],
    },
    host.player_id,
  );

  const before = await publicStateSummary(page, host.room_code);
  expect(before.players).toHaveLength(3);
  expect(before.currentPlayerId).toBe(host.player_id);
  expect(handCount(before, 'Host')).toBe(7);
  expect(handCount(before, 'Guest A')).toBe(1);
  expect(handCount(before, 'Guest B')).toBe(1);

  await selectCard(page, 'shu');
  await chooseColor(page, 'red');
  const recipientSelect = page.getByLabel(TEXT.remainderLabel);
  await expect(recipientSelect).toBeVisible();
  await expect(recipientSelect).toContainText('Guest A');
  await expect(recipientSelect).toContainText('Guest B');
  await expect(recipientSelect).not.toContainText('Host');

  await page.getByTestId('play-selected').click();
  await expect(page.getByTestId('error-banner')).toContainText(TEXT.shuNeedRemainder);

  await recipientSelect.selectOption({ label: 'Guest B' });
  await page.getByTestId('play-selected').click();
  await expect(page.locator('.status-strip')).toContainText(TEXT.shuSuccess);
  await expectSeatCount(page, 'Guest A', 3);
  await expectSeatCount(page, 'Guest B', 4);
  await expect(page.getByTestId('hand-card')).toHaveCount(1);
  await expect(page.locator('.players-rail')).not.toContainText('uno_');

  const after = await publicStateSummary(page, host.room_code);
  expect(after.players).toHaveLength(3);
  expect(after.stateVersion).toBe(before.stateVersion + 1);
  expect(after.currentPlayerId).toBe(guestA.player_id);
  expect(after.discardCount).toBe(before.discardCount + 1);
  expect(handCount(after, 'Host')).toBe(1);
  expect(handCount(after, 'Guest A')).toBe(3);
  expect(handCount(after, 'Guest B')).toBe(4);
});

test('shu three-player invalid inputs preserve hand counts turn direction and discard count', async ({ page }) => {
  const { host, guests } = await createStartedRoom(page);
  const [guestA, guestB] = guests;
  await setTestState(
    page,
    host,
    {
      [host.player_id]: ['sui_shu', 'uno_red_1', 'uno_blue_9'],
      [guestA.player_id]: ['uno_green_1'],
      [guestB.player_id]: ['uno_yellow_2'],
    },
    host.player_id,
  );

  const insufficientBefore = await publicStateSummary(page, host.room_code);
  expect(insufficientBefore.players).toHaveLength(3);
  await selectCard(page, 'shu');
  const colorSelect = page.getByLabel('\u989c\u8272');
  await expect(colorSelect.locator('option')).toHaveCount(4);
  await expect(colorSelect).not.toContainText('invalid');
  await chooseColor(page, 'red');
  await page.getByTestId('play-selected').click();
  await expect(page.getByTestId('error-banner')).toContainText(TEXT.shuTooFew);
  expect(await publicStateSummary(page, host.room_code)).toEqual(insufficientBefore);

  await setTestState(
    page,
    host,
    {
      [host.player_id]: ['sui_shu', 'uno_red_1', 'uno_red_2', 'uno_red_3', 'uno_red_4', 'uno_red_6', 'uno_blue_9'],
      [guestA.player_id]: ['uno_green_1'],
      [guestB.player_id]: ['uno_yellow_2'],
    },
    host.player_id,
  );
  const tiedBefore = await publicStateSummary(page, host.room_code);
  await selectCard(page, 'shu');
  await chooseColor(page, 'red');
  const recipientSelect = page.getByLabel(TEXT.remainderLabel);
  await expect(recipientSelect).toBeVisible();
  await expect(recipientSelect).toContainText('Guest A');
  await expect(recipientSelect).toContainText('Guest B');
  await expect(recipientSelect).not.toContainText('Host');
  await page.getByTestId('play-selected').click();
  await expect(page.getByTestId('error-banner')).toContainText(TEXT.shuNeedRemainder);
  expect(await publicStateSummary(page, host.room_code)).toEqual(tiedBefore);
  await expect(page.locator('.players-rail')).not.toContainText('uno_');
});

test('shu one-card lifecycle exposes the existing UNO declaration state and advances once', async ({ page }) => {
  const { host, guests } = await createStartedRoom(page);
  const [guestA, guestB] = guests;
  await setTestState(
    page,
    host,
    {
      [host.player_id]: ['sui_shu', 'uno_red_1', 'uno_red_2', 'uno_red_3', 'uno_red_4', 'uno_blue_9'],
      [guestA.player_id]: ['uno_green_1'],
      [guestB.player_id]: ['uno_yellow_2'],
    },
    host.player_id,
  );

  const before = await publicStateSummary(page, host.room_code);
  expect(before.players).toHaveLength(3);
  await selectCard(page, 'shu');
  await chooseColor(page, 'red');
  await page.getByTestId('play-selected').click();
  await expect(page.locator('.status-strip')).toContainText(TEXT.shuSuccess);
  await expect(page.getByTestId('declare-uno')).toBeVisible();
  await expect(page.getByTestId('hand-card')).toHaveCount(1);
  await expect(page.locator('.players-rail')).not.toContainText('uno_');

  const after = await publicStateSummary(page, host.room_code);
  expect(after.stateVersion).toBe(before.stateVersion + 1);
  expect(after.phase).toBe('IN_GAME');
  expect(after.status).toBe('ACTIVE');
  expect(after.currentPlayerId).toBe(guestA.player_id);
  expect(after.unoPendingPlayerId).toBe(host.player_id);
  expect(after.winnerPlayerId).toBeNull();
  expect(handCount(after, 'Host')).toBe(1);
  expect(after.discardCount).toBe(before.discardCount + 1);
});

test('shu empty-hand lifecycle shows one winner and rejects a post-game old action', async ({ page }) => {
  const { host, guests } = await createStartedRoom(page);
  const [guestA, guestB] = guests;
  await setTestState(
    page,
    host,
    {
      [host.player_id]: ['sui_shu', 'uno_red_1', 'uno_red_2', 'uno_red_3', 'uno_red_4'],
      [guestA.player_id]: ['uno_green_1'],
      [guestB.player_id]: ['uno_yellow_2'],
    },
    host.player_id,
  );

  const before = await publicStateSummary(page, host.room_code);
  expect(before.players).toHaveLength(3);
  await selectCard(page, 'shu');
  await chooseColor(page, 'red');
  await page.getByTestId('play-selected').click();
  await expect(page.locator('.status-strip')).toContainText(TEXT.shuSuccess);
  await expect(page.locator('.winner-banner')).toHaveText('胜者：Host');
  await expect(page.locator('.winner-banner')).toHaveCount(1);
  await expect(page.getByTestId('hand-card')).toHaveCount(0);
  await expect(page.getByTestId('play-selected')).toBeDisabled();

  const finished = await publicStateSummary(page, host.room_code);
  expect(finished.stateVersion).toBe(before.stateVersion + 1);
  expect(finished.phase).toBe('ROUND_RESULT');
  expect(finished.status).toBe('FINISHED');
  expect(finished.winnerPlayerId).toBe(host.player_id);
  expect(finished.currentPlayerId).toBe(host.player_id);
  expect(handCount(finished, 'Host')).toBe(0);
  expect(finished.discardCount).toBe(before.discardCount + 1);

  await page.getByTestId('draw-card').click();
  await expect(page.getByTestId('error-banner')).toContainText('已经结束或重置');
  expect(await publicStateSummary(page, host.room_code)).toEqual(finished);
  await expect(page.locator('.winner-banner')).toHaveCount(1);
});
