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

async function createStartedThreePlayerRoom(browser: Browser) {
  const contexts = await Promise.all([0, 1, 2].map(() => browser.newContext({ viewport: { width: 1366, height: 768 } })));
  const pages = await Promise.all(contexts.map((context) => context.newPage()));

  await pages[0].goto('/');
  await pages[0].getByLabel('昵称').fill('Multi Host');
  await pages[0].getByTestId('create-room').click();
  await expect(pages[0].getByTestId('room-code')).toHaveText(/^[A-Z0-9]{6}$/);
  const host = await storedSession(pages[0]);

  for (const [index, nickname] of [[1, 'Multi Guest A'], [2, 'Multi Guest B']] as const) {
    await pages[index].goto('/');
    await pages[index].getByLabel('昵称').fill(nickname);
    await pages[index].getByLabel('房间号').fill(host.room_code);
    await pages[index].getByTestId('join-room').click();
    await expect(pages[index].getByTestId('room-code')).toHaveText(host.room_code);
  }
  const guests = [await storedSession(pages[1]), await storedSession(pages[2])];

  await pages[0].getByTestId('ready').click();
  await expect(pages[1].locator('.product-roster__seat').filter({ hasText: 'Multi Host' })).toContainText('已准备');
  await pages[1].getByTestId('ready').click();
  await expect(pages[2].locator('.product-roster__seat').filter({ hasText: 'Multi Guest A' })).toContainText('已准备');
  await pages[2].getByTestId('ready').click();
  await expect(pages[0].getByTestId('start-game')).toBeEnabled();
  await pages[0].getByTestId('start-game').click();
  await expect(pages[0].getByTestId('hand-card').first()).toBeVisible();

  return { contexts, pages, host, guests };
}

async function setHands(
  page: Page,
  host: Session,
  guests: Session[],
  hands: string[][],
  actionStack?: { kind: 'draw_two' | 'wild_draw_four' | 'skip'; count: number },
) {
  await command(page, host, 'TEST_SET_STATE', {
    hands: Object.fromEntries([host, ...guests].map((session, index) => [session.player_id, hands[index]])),
    current_player_id: host.player_id,
    discard_asset_key: 'uno_green_5',
    deck_asset_keys: ['uno_red_0', 'uno_blue_1'],
    ...(actionStack ? { action_stack: actionStack } : {}),
  });
}

async function passSuiActivationReactions(pages: Page[]) {
  for (let pass = 0; pass < pages.length; pass += 1) {
    let responderIndex = -1;
    await expect.poll(async () => {
      for (let index = 0; index < pages.length; index += 1) {
        if (await pages[index].getByTestId('pending-response-pass').isVisible().catch(() => false)) {
          responderIndex = index;
          return index;
        }
      }
      return -1;
    }).not.toBe(-1);
    await pages[responderIndex].getByTestId('pending-response-pass').click();
  }
}

test('Yi and Yu selection guides support mode and only marks valid payment cards', async ({ browser }) => {
  test.setTimeout(180_000);
  const room = await createStartedThreePlayerRoom(browser);
  const { contexts, pages, host, guests } = room;
  const hostPage = pages[0];

  try {
    await setHands(hostPage, host, guests, [
      ['sui_yi', 'sui_yu', 'uno_red_3', 'uno_blue_5', 'uno_green_2', 'uno_yellow_7'],
      ['uno_red_2'],
      ['uno_blue_3'],
    ]);

    await hostPage.locator('[data-testid="hand-card"][data-card-kind="yi"]').click();
    await expect(hostPage.getByRole('button', { name: '多选牌', exact: true })).toHaveAttribute('aria-pressed', 'true');
    await expect(hostPage.getByTestId('selection-guidance')).toContainText('点数和为 8');

    const redThree = hostPage.locator('[data-testid="hand-card"][data-card-color="red"][data-card-value="3"]');
    const blueFive = hostPage.locator('[data-testid="hand-card"][data-card-color="blue"][data-card-value="5"]');
    await expect(redThree.locator('figure')).toHaveClass(/is-support-candidate/);
    await expect(redThree.locator('figure')).not.toHaveClass(/is-legal/);
    await redThree.click();
    await expect(blueFive.locator('figure')).toHaveClass(/is-support-candidate/);
    await blueFive.click();
    await expect(hostPage.getByTestId('play-selected')).toBeEnabled();

    await hostPage.getByRole('button', { name: '主牌', exact: true }).click();
    await hostPage.locator('[data-testid="hand-card"][data-card-kind="yu"]').click();
    await expect(hostPage.getByRole('button', { name: '多选牌', exact: true })).toHaveAttribute('aria-pressed', 'true');
    await expect(hostPage.locator('.selection-summary')).toContainText('多选 0 张');
    await expect(hostPage.getByTestId('selection-guidance')).toContainText('四色');

    for (const color of ['red', 'blue', 'green', 'yellow']) {
      const card = hostPage.locator(`[data-testid="hand-card"][data-card-color="${color}"]`).first();
      await expect(card.locator('figure')).toHaveClass(/is-support-candidate/);
      await card.click();
    }
    await expect(hostPage.getByTestId('play-selected')).toBeEnabled();
  } finally {
    await command(hostPage, host, 'CLOSE_ROOM').catch(() => undefined);
    await Promise.all(contexts.map((context) => context.close()));
  }
});

test('Yu response selects one unused color and guides the next responder', async ({ browser }) => {
  test.setTimeout(180_000);
  const room = await createStartedThreePlayerRoom(browser);
  const { contexts, pages, host, guests } = room;
  const hostPage = pages[0];
  const firstPage = pages[1];
  const secondPage = pages[2];

  try {
    await setHands(hostPage, host, guests, [
      ['sui_yu', 'uno_red_3', 'uno_blue_5', 'uno_green_2', 'uno_yellow_7'],
      ['uno_red_2', 'uno_blue_4'],
      ['uno_red_6', 'uno_blue_8'],
    ]);
    await hostPage.locator('[data-testid="hand-card"][data-card-kind="yu"]').click();
    for (const color of ['red', 'blue', 'green', 'yellow']) {
      await hostPage.locator(`[data-testid="hand-card"][data-card-color="${color}"]`).first().click();
    }
    await hostPage.getByTestId('play-selected').click();

    await expect(firstPage.getByTestId('pending-response-submit_cards')).toBeVisible();
    await expect(firstPage.getByRole('button', { name: '多选牌', exact: true })).toHaveAttribute('aria-pressed', 'true');
    await expect(firstPage.getByTestId('selection-guidance')).toContainText('未使用颜色');
    const firstRed = firstPage.locator('[data-testid="hand-card"][data-card-color="red"]');
    await expect(firstRed.first().locator('figure')).toHaveClass(/is-support-candidate/);
    await firstRed.first().click();
    await firstPage.getByTestId('pending-response-submit_cards').click();

    await expect(secondPage.getByTestId('pending-response-submit_cards')).toBeVisible();
    const secondRed = secondPage.locator('[data-testid="hand-card"][data-card-color="red"]').first();
    const secondBlue = secondPage.locator('[data-testid="hand-card"][data-card-color="blue"]').first();
    await expect(secondRed).toBeDisabled();
    await expect(secondRed.locator('figure')).not.toHaveClass(/is-support-candidate/);
    await expect(secondBlue.locator('figure')).toHaveClass(/is-support-candidate/);
    await secondBlue.click();
    await secondPage.getByTestId('pending-response-submit_cards').click();
    await expect(secondPage.getByTestId('pending-action')).toHaveCount(0);
  } finally {
    await command(hostPage, host, 'CLOSE_ROOM').catch(() => undefined);
    await Promise.all(contexts.map((context) => context.close()));
  }
});

test('an out-of-turn Wang card is not highlighted while an action stack is active', async ({ browser }) => {
  const room = await createStartedThreePlayerRoom(browser);
  const { contexts, pages, host, guests } = room;
  const hostPage = pages[0];
  const outOfTurnPage = pages[1];

  try {
    await setHands(hostPage, host, guests, [
      ['uno_red_draw_two'],
      ['sui_wang', 'uno_blue_2'],
      ['uno_green_3'],
    ], { kind: 'draw_two', count: 2 });

    const wang = outOfTurnPage.locator('[data-testid="hand-card"][data-card-kind="wang"]');
    await expect(wang.locator('figure')).not.toHaveClass(/is-legal/);
    await wang.click();
    await expect(outOfTurnPage.getByTestId('play-selected')).toBeDisabled();
  } finally {
    await command(hostPage, host, 'CLOSE_ROOM').catch(() => undefined);
    await Promise.all(contexts.map((context) => context.close()));
  }
});

test('Wang stack response highlights matching cards and exposes acceptance', async ({ browser }) => {
  test.setTimeout(180_000);
  const room = await createStartedThreePlayerRoom(browser);
  const { contexts, pages, host, guests } = room;
  const hostPage = pages[0];
  const targetPage = pages[1];
  const nextPage = pages[2];
  const target = guests[0];

  try {
    await command(hostPage, host, 'TEST_SET_STATE', {
      hands: {
        [host.player_id]: ['sui_wang', 'uno_red_draw_two', 'uno_blue_draw_two', 'uno_yellow_3'],
        [guests[0].player_id]: ['uno_blue_draw_two', 'uno_blue_4'],
        [guests[1].player_id]: ['uno_green_7'],
      },
      current_player_id: target.player_id,
      discard_asset_key: 'uno_red_5',
      deck_asset_keys: ['uno_green_1', 'uno_yellow_2', 'uno_blue_6'],
    });

    await hostPage.locator('[data-testid="hand-card"][data-card-kind="wang"]').click();
    await hostPage.getByRole('group', { name: '目标' }).getByRole('button', { name: 'Multi Guest A', exact: true }).click();
    await hostPage.getByTestId('play-selected').click();
    await passSuiActivationReactions(pages);
    await expect(hostPage.getByTestId('pending-response-control_play')).toBeVisible();

    await hostPage.locator('[data-testid="hand-card"][data-card-kind="draw_two"][data-card-color="red"]').click();
    await hostPage.getByTestId('pending-response-control_play').click();
    await expect(hostPage.getByTestId('pending-response-control_accept_stack')).toBeEnabled();
    await expect(hostPage.getByTestId('accept-stack')).toHaveCount(0);

    const matching = hostPage.locator('[data-testid="hand-card"][data-card-kind="draw_two"][data-card-color="blue"]');
    const unrelated = hostPage.locator('[data-testid="hand-card"][data-card-kind="number"]');
    await expect(matching).toBeEnabled();
    await expect(matching.locator('figure')).toHaveClass(/is-legal/);
    await expect(unrelated).toBeDisabled();
    await expect(unrelated.locator('figure')).not.toHaveClass(/is-legal/);
    await expect(targetPage.getByTestId('hand-card')).toHaveCount(2);
    await expect(nextPage.locator('.turn-panel')).toContainText('当前：Multi Guest B');

    await hostPage.getByTestId('pending-response-control_accept_stack').click();
    await expect(targetPage.getByTestId('hand-card')).toHaveCount(2);
    await expect(nextPage.getByTestId('hand-card')).toHaveCount(3);
    await expect(hostPage.getByTestId('pending-response-control_accept_stack')).toHaveCount(0);
    await expect(hostPage.getByTestId('pending-response-control_play')).toBeVisible();
  } finally {
    await command(hostPage, host, 'CLOSE_ROOM').catch(() => undefined);
    await Promise.all(contexts.map((context) => context.close()));
  }
});
