import { expect, test, type Page } from '@playwright/test';

type Session = {
  room_code: string;
  player_id: string;
  session_id: string;
};

async function sessionFrom(page: Page): Promise<Session> {
  return page.evaluate(() => JSON.parse(localStorage.getItem('suicardgame.session.v1') ?? '{}'));
}

async function command(page: Page, session: Session, commandType: string, payload: Record<string, unknown> = {}) {
  const status = await page.evaluate(async ({ session, commandType, payload }) => {
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
    return response.status;
  }, { session, commandType, payload });
  expect(status).toBe(200);
}

async function createStartedRoom(page: Page) {
  await page.goto('/');
  await page.getByLabel('昵称').fill('Host');
  await page.getByTestId('create-room').click();
  await expect(page.getByTestId('room-code')).toHaveText(/^[A-Z0-9]{6}$/);
  await expect.poll(
    () => page.evaluate(() => {
      const raw = localStorage.getItem('suicardgame.session.v1');
      if (!raw) return '';
      try {
        return (JSON.parse(raw) as { player_id?: string }).player_id ?? '';
      } catch {
        return '';
      }
    }),
    { message: '等待创建房间后的本机会话写入完成' },
  ).not.toBe('');
  const host = await sessionFrom(page);
  const guest = await page.evaluate(async ({ roomCode }) => {
    const response = await fetch(`/api/v1/rooms/${roomCode}/join`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nickname: 'Guest' }),
    });
    return response.json();
  }, { roomCode: host.room_code }) as Session;
  await command(page, host, 'READY', { ready: true });
  await command(page, guest, 'READY', { ready: true });
  await page.getByTestId('start-game').click();
  await expect(page.getByTestId('hand-card').first()).toBeVisible();
  return { host, guest };
}

test('portrait and landscape keep color, multi-select, shop payment, and core actions reachable', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 640 });
  const { host, guest } = await createStartedRoom(page);
  await command(page, host, 'TEST_SET_STATE', {
    hands: {
      [host.player_id]: ['uno_wild', 'uno_red_3', 'uno_blue_5', 'sui_yi'],
      [guest.player_id]: ['uno_green_2'],
    },
    current_player_id: host.player_id,
    discard_asset_key: 'uno_yellow_4',
    deck_asset_keys: ['uno_red_1', 'uno_blue_2', 'uno_green_3'],
  });

  await page.getByRole('button', { name: '主牌', exact: true }).click();
  await page.locator('[data-testid="hand-card"][data-card-kind="wild"]').click();
  await expect(page.getByRole('group', { name: '上下文操作区' })).toBeVisible();
  await page.getByRole('button', { name: '蓝色' }).click();
  await expect(page.getByRole('button', { name: '蓝色' })).toHaveAttribute('aria-pressed', 'true');

  await page.getByRole('button', { name: '多选牌', exact: true }).click();
  await page.locator('[data-testid="hand-card"][data-card-value="3"]').click();
  await page.locator('[data-testid="hand-card"][data-card-value="5"]').click();
  await expect(page.locator('.selection-summary')).toContainText('多选 2 张');

  const shopToggle = page.locator('.shop-toggle');
  await expect(shopToggle).toBeVisible();
  await shopToggle.click();
  await page.locator('.shop-row .card-button').first().click();
  await page.getByRole('button', { name: '支付牌', exact: true }).click();
  await page.locator('[data-testid="hand-card"][data-card-value="3"]').click();
  await expect(page.getByRole('button', { name: '确认交换' })).toBeEnabled();

  await page.setViewportSize({ width: 844, height: 390 });
  await expect(page.getByRole('button', { name: '确认出牌 / 发动' })).toBeVisible();
  await expect(page.getByRole('button', { name: '支付牌', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '确认交换' })).toBeVisible();
  await expect(page.getByRole('button', { name: '蓝色' })).toHaveAttribute('aria-pressed', 'true');
});
