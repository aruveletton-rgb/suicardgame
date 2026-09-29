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

async function createStartedRoom(page: Page): Promise<{ host: Session; guest: Session }> {
  await page.goto('/');
  await page.getByTestId('nickname').fill('Production Card QA');
  await page.getByTestId('create-room').click();
  await expect(page.getByTestId('room-code')).toHaveText(/^[A-Z0-9]{6}$/);
  const host = await sessionFrom(page);
  const guest = await page.evaluate(async (roomCode) => {
    const response = await fetch(`/api/v1/rooms/${roomCode}/join`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nickname: 'Production Guest' }),
    });
    return response.json();
  }, host.room_code) as Session;
  await command(page, host, 'READY', { ready: true });
  await command(page, guest, 'READY', { ready: true });
  await expect(page.getByTestId('start-game')).toBeEnabled();
  await page.getByTestId('start-game').click();
  await expect(page.getByTestId('hand-card').first()).toBeVisible();
  return { host, guest };
}

test('production dist renders real CardView colors and states across hand table and shop', async ({ page }) => {
  await page.setViewportSize({ width: 1366, height: 768 });
  const { host, guest } = await createStartedRoom(page);
  await command(page, host, 'TEST_SET_STATE', {
    hands: {
      [host.player_id]: [
        'uno_red_3', 'uno_yellow_skip', 'uno_green_draw_two', 'uno_blue_reverse',
        'uno_red_0', 'uno_yellow_1', 'uno_green_2', 'uno_blue_3',
        'uno_wild', 'uno_wild_draw_four',
      ],
      [guest.player_id]: ['uno_red_1'],
    },
    current_player_id: host.player_id,
    discard_asset_key: 'uno_blue_reverse',
    deck_asset_keys: ['uno_red_4', 'uno_yellow_5', 'uno_green_6', 'uno_blue_7'],
  });
  await page.reload();
  await expect(page.getByTestId('hand-card')).toHaveCount(10);

  const expectedBackgrounds: Record<string, string> = {
    red: 'rgb(187, 57, 60)',
    yellow: 'rgb(208, 165, 36)',
    green: 'rgb(37, 128, 96)',
    blue: 'rgb(45, 104, 157)',
  };
  for (const [color, backgroundColor] of Object.entries(expectedBackgrounds)) {
    const face = page.locator(`[data-testid="hand-card"] .product-uno--${color}`).first();
    await expect(face).toBeVisible();
    const style = await face.evaluate((element) => {
      const computed = getComputedStyle(element);
      return { backgroundColor: computed.backgroundColor, backgroundImage: computed.backgroundImage };
    });
    expect(style.backgroundColor, `${color} background`).toBe(backgroundColor);
    expect(style.backgroundImage, `${color} texture`).not.toBe('none');
  }
  for (const kind of ['wild', 'wild-draw-four']) {
    const face = page.locator(`[data-testid="hand-card"] .product-uno--${kind}`).first();
    await expect(face).toBeVisible();
    await expect.poll(() => face.evaluate((element) => getComputedStyle(element).backgroundImage)).toContain('gradient');
  }

  await expect(page.locator('[data-testid="hand-card"] .product-uno--yellow.product-uno--skip')).toHaveCount(1);
  await expect(page.locator('[data-testid="hand-card"] .product-uno--green.product-uno--draw-two')).toHaveCount(1);
  await expect(page.locator('[data-testid="hand-card"] .product-uno--blue.product-uno--reverse')).toHaveCount(1);
  await expect(page.locator('.piles .product-card--table .product-uno--blue.product-uno--reverse')).toHaveCount(1);

  const illegalCard = page.locator('[data-testid="hand-card"][data-card-color="red"][data-card-value="3"]');
  await illegalCard.click();
  await expect(illegalCard.locator('figure')).toHaveClass(/is-selected/);
  await page.getByTestId('play-selected').click();
  await expect(page.getByTestId('error-banner')).toBeVisible();
  await expect(illegalCard).toBeVisible();
  await page.locator('[data-testid="hand-card"][data-card-kind="wild"]').click();
  await expect(page.locator('[data-testid="hand-card"][data-card-kind="wild"] figure')).toHaveClass(/is-selected/);

  const shop = page.getByRole('region', { name: '坎诺特商店' });
  await expect(shop).toBeVisible();
  await shop.getByRole('button', { name: /展开商品/ }).click();
  const goods = shop.locator('.shop-row .card-button');
  await expect(goods.first()).toBeVisible();
  await expect(goods.locator('.product-card--thumbnail').first()).toBeVisible();
  const goodOptions = await goods.evaluateAll((buttons) => buttons.map((button, index) => ({
    index,
    assetKey: button.querySelector('figure')?.getAttribute('data-asset-key') ?? '',
  })));
  const matchingGood = goodOptions.find(({ assetKey }) => /^uno_(red|yellow|green|blue)_/.test(assetKey)) ?? goodOptions[0];
  expect(matchingGood).toBeTruthy();
  const goodAssetKey = matchingGood.assetKey;
  const good = goods.nth(matchingGood.index);
  const goodBefore = await page.locator(`.hand-zone figure[data-asset-key="${goodAssetKey}"]`).count();
  await good.click();
  await expect(good.locator('figure')).toHaveClass(/is-selected/);
  await expect(shop.getByRole('button', { name: '确认交换' })).toBeDisabled();

  await page.getByRole('button', { name: '支付牌', exact: true }).click();
  const color = goodAssetKey.match(/^uno_(red|yellow|green|blue)_/)?.[1];
  const payment = color
    ? page.locator(`[data-testid="hand-card"][data-card-color="${color}"]`).first()
    : page.locator('[data-testid="hand-card"]').first();
  await payment.click();
  await expect(payment.locator('figure')).toHaveClass(/is-selected/);
  await expect(shop.getByRole('button', { name: '确认交换' })).toBeEnabled();
  await shop.getByRole('button', { name: '确认交换' }).click();
  await expect(page.locator(`.hand-zone figure[data-asset-key="${goodAssetKey}"]`)).toHaveCount(goodBefore + 1);

  await page.screenshot({ path: '../artifacts/acceptance/production-card-render-1366x768.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await shop.scrollIntoViewIfNeeded();
  await page.screenshot({ path: '../artifacts/acceptance/production-card-render-mobile-390x844.png', fullPage: true });
});
