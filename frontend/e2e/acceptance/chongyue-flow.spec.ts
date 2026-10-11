import { expect, test, type Browser, type Page } from '@playwright/test';
import { mkdirSync } from 'node:fs';
import { resolve } from 'node:path';

type Session = { room_code: string; player_id: string; session_id: string };
const evidence = resolve('../audit/20261011_chongyue_fixes');
const colors = ['red', 'yellow', 'green', 'blue'];

async function command(page: Page, session: Session, commandType: string, payload: Record<string, unknown> = {}) {
  const result = await page.evaluate(async ({ session, commandType, payload }) => {
    const response = await fetch(`/api/v1/rooms/${session.room_code}/commands`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${session.session_id}` },
      body: JSON.stringify({ action_id: crypto.randomUUID(), player_id: session.player_id, command_type: commandType, payload }),
    });
    return { status: response.status, body: await response.json() };
  }, { session, commandType, payload });
  expect(result.status, JSON.stringify(result.body)).toBe(200);
}

async function createRoom(browser: Browser, mobile = false) {
  const contexts = await Promise.all([0, 1, 2].map(() => browser.newContext({
    viewport: mobile ? { width: 390, height: 844 } : { width: 1366, height: 768 },
  })));
  const pages = await Promise.all(contexts.map((context) => context.newPage()));
  const errors: string[] = [];
  const sessions: Session[] = [];
  for (const [index, page] of pages.entries()) {
    page.on('pageerror', (error) => errors.push(error.message));
    page.on('console', (message) => { if (message.type() === 'error') errors.push(message.text()); });
    await page.goto('/');
    await page.getByLabel('昵称').fill(['Chong Host', 'Chong Guest A', 'Chong Guest B'][index]);
    if (index === 0) await page.getByTestId('create-room').click();
    else {
      await page.getByLabel('房间号').fill(sessions[0].room_code);
      await page.getByTestId('join-room').click();
    }
    await expect(page.getByTestId('room-code')).toHaveText(/^[A-Z0-9]{6}$/);
    sessions.push(await page.evaluate(() => JSON.parse(localStorage.getItem('suicardgame.session.v1') ?? '{}')));
    await page.getByTestId('ready').click();
  }
  await expect(pages[0].getByTestId('start-game')).toBeEnabled();
  await pages[0].getByTestId('start-game').click();
  await expect(pages[0].getByTestId('hand-card').first()).toBeVisible();
  return { contexts, pages, sessions, errors };
}

async function activate(pages: Page[], sourceIndex = 0, direction = 1) {
  const source = pages[sourceIndex];
  await source.locator('[data-testid="hand-card"][data-card-kind="chongyue"]').click();
  await source.getByTestId('play-selected').click();
  for (let offset = 1; offset <= pages.length; offset += 1) {
    const index = (sourceIndex + offset * direction + pages.length * 2) % pages.length;
    await expect(pages[index].getByTestId('pending-response-pass')).toBeVisible();
    await pages[index].getByTestId('pending-response-pass').click();
  }
}

async function submitColors(page: Page, choices = colors) {
  await expect(page.getByTestId('pending-response-submit_cards')).toBeVisible();
  await expect(page.getByRole('button', { name: '多选牌', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByTestId('pending-response-submit_cards')).toBeDisabled();
  for (const color of choices) {
    const card = page.locator(`[data-testid="hand-card"][data-card-color="${color}"]`).first();
    await expect(card.locator('figure')).toHaveClass(/is-support-candidate/);
    await card.click();
  }
  await expect(page.getByTestId('pending-response-submit_cards')).toBeEnabled();
  await page.getByTestId('pending-response-submit_cards').click();
}

async function drawOnce(page: Page, before: number) {
  const draw = page.getByTestId('pending-response-draw_one');
  await expect(draw).toBeEnabled();
  await draw.click();
  await expect(page.getByTestId('hand-card')).toHaveCount(before + 1);
}

async function assertLayout(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
  const panel = page.getByTestId('chongyue-panel');
  await expect(panel).toBeVisible();
  for (const row of await panel.getByTestId('chongyue-player').all()) {
    const box = await row.boundingBox();
    expect(box?.width).toBeLessThanOrEqual((page.viewportSize()?.width ?? 0) - 8);
  }
}

test('Chongyue manually reveals and draws each card, then successful challenge stops later seats', async ({ browser }) => {
  test.setTimeout(150_000);
  const { contexts, pages, sessions, errors } = await createRoom(browser);
  const [host, first, later] = pages;
  try {
    await command(host, sessions[0], 'TEST_SET_STATE', {
      hands: {
        [sessions[0].player_id]: ['sui_chongyue', 'uno_red_1', 'uno_yellow_1'],
        [sessions[1].player_id]: ['uno_red_2', 'uno_red_3', 'uno_yellow_2'],
        [sessions[2].player_id]: ['uno_red_9'],
      },
      current_player_id: sessions[0].player_id,
      discard_asset_key: 'uno_red_5',
      deck_asset_keys: ['uno_blue_8', 'uno_green_8', 'uno_blue_4', 'uno_green_4', 'uno_red_4', 'uno_wild'],
    });
    await activate(pages);
    await expect(host.getByTestId('hand-card')).toHaveCount(2);
    await expect(later.getByTestId('hand-card')).toHaveCount(1);
    await expect(first.getByTestId('prompt-countdown')).toHaveText(/1[67]\d[s]/);
    await first.locator('[data-testid="hand-card"][data-card-color="red"]').first().click();
    await expect(first.locator('[data-testid="hand-card"][data-card-color="red"]').nth(1)).toBeDisabled();
    await expect(first.getByTestId('pending-response-submit_cards')).toBeDisabled();
    await first.locator('[data-testid="hand-card"][data-card-color="yellow"]').click();
    await first.getByTestId('pending-response-submit_cards').click();
    const firstRow = first.getByTestId('chongyue-player').filter({ hasText: 'Chong Guest A' });
    await expect(firstRow.locator('figure')).toHaveCount(2);
    await expect(firstRow.getByTestId('chongyue-progress')).toHaveAttribute('value', '2');
    await drawOnce(first, 3);
    await expect(firstRow.locator('[data-asset-key="uno_wild"]')).toBeVisible();
    await expect(firstRow.getByTestId('chongyue-progress')).toHaveAttribute('value', '2');
    await drawOnce(first, 4);
    await expect(firstRow.getByTestId('chongyue-progress')).toHaveAttribute('value', '2');
    await drawOnce(first, 5);
    await expect(firstRow.getByTestId('chongyue-progress')).toHaveAttribute('value', '3');
    await drawOnce(first, 6);
    await expect(firstRow.locator('figure')).toHaveCount(6);
    await expect(firstRow.getByTestId('chongyue-progress')).toHaveAttribute('value', '4');
    await assertLayout(first);
    mkdirSync(evidence, { recursive: true });
    await first.screenshot({ path: resolve(evidence, 'frontend-chongyue-desktop.png'), fullPage: true });
    await first.getByTestId('pending-response-challenge').click();
    await expect(host.getByTestId('hand-card')).toHaveCount(2);
    await submitColors(host, ['red', 'yellow']);
    await drawOnce(host, 2);
    await drawOnce(host, 3);
    await expect(host.getByTestId('pending-action')).toHaveCount(0);
    await expect(host.getByRole('button', { name: '主牌', exact: true })).toHaveAttribute('aria-pressed', 'true');
    await expect(first.getByTestId('chongyue-result')).toContainText('质疑成功');
    await expect(later.getByTestId('hand-card')).toHaveCount(1);
    expect(errors).toEqual([]);
  } finally {
    await command(host, sessions[0], 'CLOSE_ROOM').catch(() => undefined);
    await Promise.all(contexts.map((context) => context.close()));
  }
});

test('Chongyue mobile source shows four cards before failed challenge and next player remains usable', async ({ browser }) => {
  test.setTimeout(150_000);
  const { contexts, pages, sessions, errors } = await createRoom(browser, true);
  const [host, first, later] = pages;
  try {
    await command(host, sessions[0], 'TEST_SET_STATE', {
      hands: {
        [sessions[0].player_id]: ['sui_chongyue', 'uno_red_1', 'uno_yellow_1', 'uno_green_1', 'uno_blue_1', 'uno_red_9'],
        [sessions[1].player_id]: ['uno_red_2', 'uno_yellow_2', 'uno_green_2', 'uno_blue_2'],
        [sessions[2].player_id]: ['uno_red_3', 'uno_yellow_3', 'uno_green_3', 'uno_blue_3'],
      },
      current_player_id: sessions[0].player_id,
      discard_asset_key: 'uno_red_5',
      deck_asset_keys: ['uno_red_6', 'uno_yellow_6', 'uno_green_6', 'uno_blue_6'],
    });
    await activate(pages);
    await submitColors(first);
    await first.getByTestId('pending-response-challenge').click();
    await expect(first.getByTestId('hand-card')).toHaveCount(4);
    await submitColors(host);
    await expect(first.getByTestId('hand-card')).toHaveCount(8);
    await expect(later.getByTestId('pending-response-submit_cards')).toBeVisible();
    await expect(later.getByTestId('chongyue-result')).toContainText('质疑失败');
    await expect(later.getByTestId('chongyue-player').filter({ hasText: 'Chong Host' }).locator('figure')).toHaveCount(4);
    await assertLayout(later);
    mkdirSync(evidence, { recursive: true });
    await later.screenshot({ path: resolve(evidence, 'frontend-chongyue-mobile.png'), fullPage: true });
    await submitColors(later);
    await later.getByTestId('pending-response-decline_challenge').click();
    await expect(host.getByTestId('pending-action')).toHaveCount(0);
    await expect(host.getByTestId('chongyue-result')).toContainText('质疑失败');
    expect(errors).toEqual([]);
  } finally {
    await command(host, sessions[0], 'CLOSE_ROOM').catch(() => undefined);
    await Promise.all(contexts.map((context) => context.close()));
  }
});

test('Chongyue reverse order starts from next player and retains disclosed cards on reconnect', async ({ browser }) => {
  test.setTimeout(150_000);
  const { contexts, pages, sessions, errors } = await createRoom(browser);
  const [host, reverseFirst, source] = pages;
  try {
    await command(host, sessions[0], 'TEST_SET_STATE', {
      hands: {
        [sessions[0].player_id]: ['uno_red_1', 'uno_yellow_1', 'uno_green_1', 'uno_blue_1'],
        [sessions[1].player_id]: ['uno_red_2', 'uno_yellow_2', 'uno_green_2', 'uno_blue_2'],
        [sessions[2].player_id]: ['sui_chongyue', 'uno_red_3', 'uno_yellow_3', 'uno_green_3', 'uno_blue_3'],
      },
      current_player_id: sessions[2].player_id,
      direction: -1,
      discard_asset_key: 'uno_red_5',
      deck_asset_keys: ['uno_red_6'],
    });
    await activate(pages, 2, -1);
    await expect(reverseFirst.getByTestId('pending-response-submit_cards')).toBeVisible();
    await expect(host.getByTestId('pending-response-submit_cards')).toHaveCount(0);
    const order = await reverseFirst.getByTestId('chongyue-player').evaluateAll((rows) => rows.map((row) => row.getAttribute('data-player-id')));
    expect(order).toEqual([sessions[1].player_id, sessions[0].player_id, sessions[2].player_id]);
    await submitColors(reverseFirst);
    await reverseFirst.reload();
    await expect(reverseFirst.getByTestId('chongyue-player').filter({ hasText: 'Chong Guest A' }).locator('figure')).toHaveCount(4);
    await reverseFirst.getByTestId('pending-response-decline_challenge').click();
    await submitColors(host);
    await host.getByTestId('pending-response-decline_challenge').click();
    await submitColors(source);
    await expect(source.getByTestId('pending-action')).toHaveCount(0);
    expect(errors).toEqual([]);
  } finally {
    await command(host, sessions[0], 'CLOSE_ROOM').catch(() => undefined);
    await Promise.all(contexts.map((context) => context.close()));
  }
});

test('Chongyue rejected submission preserves support selection for a usable retry', async ({ browser }) => {
  test.setTimeout(120_000);
  const { contexts, pages, sessions, errors } = await createRoom(browser);
  const [host, first] = pages;
  try {
    await command(host, sessions[0], 'TEST_SET_STATE', {
      hands: Object.fromEntries(sessions.map((session, index) => [session.player_id, [
        ...(index === 0 ? ['sui_chongyue'] : []),
        `uno_red_${index + 1}`, `uno_yellow_${index + 1}`, `uno_green_${index + 1}`, `uno_blue_${index + 1}`,
      ]])),
      current_player_id: sessions[0].player_id,
      discard_asset_key: 'uno_red_5',
      deck_asset_keys: ['uno_red_6'],
    });
    await activate(pages);
    await first.evaluate(() => {
      const send = WebSocket.prototype.send;
      WebSocket.prototype.send = function (data) {
        if (typeof data === 'string') {
          const packet = JSON.parse(data);
          if (packet.command_type === 'RESPOND_TO_PROMPT' && packet.payload.response === 'submit_cards') {
            packet.payload.card_ids.pop();
            data = JSON.stringify(packet);
            WebSocket.prototype.send = send;
          }
        }
        send.call(this, data);
      };
    });
    await submitColors(first);
    await expect(first.getByTestId('error-banner')).toBeVisible();
    await expect(first.getByRole('button', { name: '多选牌', exact: true })).toHaveAttribute('aria-pressed', 'true');
    await expect(first.locator('.selection-summary')).toContainText('多选 4 张');
    await expect(first.getByTestId('pending-response-submit_cards')).toBeEnabled();
    await first.getByTestId('pending-response-submit_cards').click();
    await expect(first.getByTestId('pending-response-challenge')).toBeVisible();
    await expect(first.getByTestId('error-banner')).toHaveCount(0);
    await expect(first.getByTestId('chongyue-player').filter({ hasText: 'Chong Guest A' }).locator('figure')).toHaveCount(4);
    expect(errors).toEqual([]);
  } finally {
    await command(host, sessions[0], 'CLOSE_ROOM').catch(() => undefined);
    await Promise.all(contexts.map((context) => context.close()));
  }
});
