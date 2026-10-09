import { expect, test, type Browser, type BrowserContext, type Page } from '@playwright/test';

type Session = {
  room_code: string;
  player_id: string;
  reconnect_token: string;
  session_id: string;
  seat_index?: number;
  is_host?: boolean;
};

const SESSION_KEY = 'suicardgame.session.v1';

async function storedSession(page: Page): Promise<Session> {
  return page.evaluate((key) => JSON.parse(localStorage.getItem(key) ?? '{}'), SESSION_KEY);
}

async function joinByApi(page: Page, roomCode: string, nickname: string): Promise<Session> {
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

async function commandByApi(
  page: Page,
  commandType: string,
  payload: Record<string, unknown> = {},
): Promise<{ status: number; body: Record<string, unknown> }> {
  const session = await storedSession(page);
  return page.evaluate(
    async ({ current, type, commandPayload }) => {
      const response = await fetch(`/api/v1/rooms/${current.room_code}/commands`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${current.session_id}`,
        },
        body: JSON.stringify({
          action_id: crypto.randomUUID(),
          player_id: current.player_id,
          command_type: type,
          payload: commandPayload,
        }),
      });
      return { status: response.status, body: await response.json() };
    },
    { current: session, type: commandType, commandPayload: payload },
  );
}

async function attachSession(browser: Browser, session: Session): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext();
  await context.addInitScript(
    ({ key, value }) => {
      if (!localStorage.getItem(key)) localStorage.setItem(key, JSON.stringify(value));
    },
    { key: SESSION_KEY, value: session },
  );
  const page = await context.newPage();
  await page.goto('/');
  await expect(page.getByTestId('room-code')).toHaveText(session.room_code);
  return { context, page };
}

async function openFixture(
  hostPage: Page,
  responderIds: string[],
  privateOptions: Record<string, string[]>,
  timeoutSeconds: number,
): Promise<string> {
  const response = await commandByApi(hostPage, 'TEST_OPEN_RESPONSE_WINDOW', {
    responder_ids: responderIds,
    resolution_policy: 'first_wins',
    timeout_seconds: timeoutSeconds,
    private_options_by_responder: privateOptions,
  });
  expect(response.status, JSON.stringify(response.body)).toBe(200);
  return response.body.prompt_id as string;
}

test('generic response window supports isolated three-context competition, timeout, reconnect, reset, and DOM privacy', async ({ browser }) => {
  test.setTimeout(120_000);
  const hostContext = await browser.newContext();
  const hostPage = await hostContext.newPage();
  await hostPage.goto('/');
  await hostPage.getByLabel('昵称').fill('Host');
  await hostPage.getByTestId('create-room').click();
  await expect(hostPage.getByTestId('room-code')).toHaveText(/^[A-Z0-9]{6}$/);
  const host = await storedSession(hostPage);
  expect(host.room_code).toHaveLength(6);

  const initialA = await joinByApi(hostPage, host.room_code, 'Responder A');
  const initialB = await joinByApi(hostPage, host.room_code, 'Responder B');
  const attachedA = await attachSession(browser, initialA);
  const attachedB = await attachSession(browser, initialB);
  let responderAContext = attachedA.context;
  let responderAPage = attachedA.page;
  const responderBContext = attachedB.context;
  const responderBPage = attachedB.page;
  const responderA = await storedSession(responderAPage);
  const responderB = await storedSession(responderBPage);

  expect(new Set([hostContext, responderAContext, responderBContext]).size).toBe(3);
  expect(new Set([host.session_id, responderA.session_id, responderB.session_id]).size).toBe(3);
  expect((await commandByApi(hostPage, 'READY', { ready: true })).status).toBe(200);
  expect((await commandByApi(responderAPage, 'READY', { ready: true })).status).toBe(200);
  expect((await commandByApi(responderBPage, 'READY', { ready: true })).status).toBe(200);
  await expect(hostPage.getByTestId('start-game')).toBeEnabled();
  await hostPage.getByTestId('start-game').click();
  await expect(hostPage.getByTestId('hand-card').first()).toBeVisible();
  await expect(responderAPage.getByTestId('hand-card').first()).toBeVisible();
  await expect(responderBPage.getByTestId('hand-card').first()).toBeVisible();

  const optionA = 'private_a_accept';
  const optionB = 'private_b_accept';
  const firstPromptId = await openFixture(
    hostPage,
    [responderA.player_id, responderB.player_id],
    {
      [responderA.player_id]: [optionA, 'decline'],
      [responderB.player_id]: [optionB, 'decline'],
    },
    10,
  );
  await expect(hostPage.getByTestId('special-prompt-card')).toHaveText('需要响应');
  await expect(responderAPage.getByTestId('pending-response-private_a_accept')).toBeVisible();
  await expect(responderBPage.getByTestId('pending-response-private_b_accept')).toBeVisible();
  await expect(hostPage.locator(`[data-testid="pending-response-${optionA}"]`)).toHaveCount(0);
  await expect(hostPage.locator(`[data-testid="pending-response-${optionB}"]`)).toHaveCount(0);
  await expect(responderAPage.locator(`[data-testid="pending-response-${optionB}"]`)).toHaveCount(0);
  await expect(responderBPage.locator(`[data-testid="pending-response-${optionA}"]`)).toHaveCount(0);
  await expect(hostPage.locator('.players-rail [data-card-kind]')).toHaveCount(0);
  await expect(responderAPage.locator('.players-rail [data-card-kind]')).toHaveCount(0);

  await responderAPage.getByTestId('pending-response-private_a_accept').click();
  await expect(hostPage.getByTestId('prompt-status')).toHaveText('已处理');
  await expect(responderAPage.getByTestId('prompt-status')).toHaveText('已处理');
  await expect(responderBPage.getByTestId('prompt-status')).toHaveText('已处理');
  await expect(responderBPage.getByTestId('pending-response-private_b_accept')).toHaveCount(0);
  const duplicate = await commandByApi(responderBPage, 'RESPOND_TO_PROMPT', {
    prompt_id: firstPromptId,
    response: optionB,
  });
  expect(duplicate.status).toBe(400);
  await expect(responderBPage.getByTestId('prompt-status')).toHaveText('已处理');

  const timeoutPromptId = await openFixture(
    hostPage,
    [responderA.player_id, responderB.player_id],
    {
      [responderA.player_id]: ['timeout_a', 'decline'],
      [responderB.player_id]: ['timeout_b', 'decline'],
    },
    1,
  );
  await expect(responderAPage.getByTestId('prompt-countdown')).toBeVisible();
  await expect(hostPage.getByTestId('prompt-status')).toHaveText('已过期', { timeout: 10_000 });
  await expect(responderAPage.getByTestId('prompt-status')).toHaveText('已过期');
  await expect(responderBPage.getByTestId('prompt-status')).toHaveText('已过期');
  await expect(responderAPage.getByTestId('pending-response-timeout_a')).toHaveCount(0);
  const late = await commandByApi(responderAPage, 'RESPOND_TO_PROMPT', {
    prompt_id: timeoutPromptId,
    response: 'timeout_a',
  });
  expect(late.status).toBe(400);
  await expect(responderAPage.getByTestId('prompt-status')).toHaveText('已过期');

  const reconnectPromptId = await openFixture(
    hostPage,
    [responderA.player_id],
    { [responderA.player_id]: ['reconnect_accept', 'decline'] },
    10,
  );
  await expect(responderAPage.getByTestId('pending-response-reconnect_accept')).toBeVisible();
  const reconnectSeed = await storedSession(responderAPage);
  await responderAContext.close();
  const reattachedA = await attachSession(browser, reconnectSeed);
  responderAContext = reattachedA.context;
  responderAPage = reattachedA.page;
  await expect(responderAPage.getByTestId('pending-response-reconnect_accept')).toBeVisible();
  await expect(responderBPage.getByTestId('pending-response-reconnect_accept')).toHaveCount(0);
  await responderAPage.getByTestId('pending-response-reconnect_accept').click();
  await expect(responderAPage.getByTestId('prompt-status')).toHaveText('已处理');
  await responderAPage.reload();
  await expect(responderAPage.getByTestId('prompt-status')).toHaveText('已处理');
  await expect(responderAPage.getByTestId('pending-response-reconnect_accept')).toHaveCount(0);
  const staleResolved = await commandByApi(responderAPage, 'RESPOND_TO_PROMPT', {
    prompt_id: reconnectPromptId,
    response: 'reconnect_accept',
  });
  expect(staleResolved.status).toBe(400);

  const currentA = await storedSession(responderAPage);
  const resetPromptId = await openFixture(
    hostPage,
    [currentA.player_id, responderB.player_id],
    {
      [currentA.player_id]: ['reset_a', 'decline'],
      [responderB.player_id]: ['reset_b', 'decline'],
    },
    10,
  );
  await expect(responderAPage.getByTestId('pending-response-reset_a')).toBeVisible();
  hostPage.once('dialog', (dialog) => dialog.accept());
  await hostPage.getByTitle('结束本局并回到大厅').click();
  await expect(hostPage.getByTestId('pending-action')).toHaveCount(0);
  await expect(responderAPage.getByTestId('pending-action')).toHaveCount(0);
  await expect(responderBPage.getByTestId('pending-action')).toHaveCount(0);
  const oldAfterReset = await commandByApi(responderAPage, 'RESPOND_TO_PROMPT', {
    prompt_id: resetPromptId,
    response: 'reset_a',
  });
  expect(oldAfterReset.status).toBe(400);
  await expect(responderAPage.getByTestId('pending-action')).toHaveCount(0);

  for (const page of [hostPage, responderAPage, responderBPage]) {
    await expect(page.locator('body')).not.toContainText('重岳牌');
    await expect(page.locator('body')).not.toContainText('岁相牌');
    await expect(page.locator('body')).not.toContainText('符咒牌');
  }

  await responderAContext.close();
  await responderBContext.close();
  await hostContext.close();
});
