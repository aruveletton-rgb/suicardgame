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

async function createStartedRoom(page: Page, seed?: number): Promise<{ host: Session; guest: Session }> {
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
  if (seed === undefined) {
    await page.getByTestId('start-game').click();
  } else {
    await command(page, host, 'START_GAME', { seed });
  }
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
  const handCountBeforeIllegalSelection = await page.getByTestId('hand-card').count();
  await illegalCard.click();
  await expect(illegalCard.locator('figure')).toHaveClass(/is-selected/);
  await expect(page.getByTestId('play-selected')).toBeDisabled();
  await expect(page.locator('.special-hint[role="status"]')).toHaveText('这张牌当前不能打出');
  await expect(page.getByTestId('hand-card')).toHaveCount(handCountBeforeIllegalSelection);
  await expect(page.locator('.piles .product-card--table[data-asset-key="uno_blue_reverse"]')).toHaveCount(1);
  const legalMatchingCard = page.locator('[data-testid="hand-card"][data-card-color="blue"][data-card-kind="reverse"]');
  await legalMatchingCard.click();
  await expect(legalMatchingCard.locator('figure')).toHaveClass(/is-selected/);
  await expect(page.getByTestId('play-selected')).toBeEnabled();
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

for (const viewport of [
  { width: 1920, height: 1080 }, { width: 1366, height: 768 }, { width: 1060, height: 720 },
  { width: 390, height: 844 }, { width: 844, height: 390 },
]) {
  test(`shop card faces remain upright and unobscured at ${viewport.width}x${viewport.height}`, async ({ page }, testInfo) => {
    const pageErrors: string[] = [];
    page.on('pageerror', () => pageErrors.push('pageerror'));
    await page.setViewportSize(viewport);
    await createStartedRoom(page, 5);
    const shop = page.getByRole('region', { name: '坎诺特商店' });
    const toggle = shop.locator('.shop-toggle');
    if (await toggle.isVisible() && await toggle.getAttribute('aria-expanded') === 'false') await toggle.click();
    const goods = shop.locator('.shop-row .card-button');
    await expect(goods).toHaveCount(8);
    await expect(goods.last()).toBeVisible();
    await shop.screenshot({ path: testInfo.outputPath('shop.png') });

    const geometry = await goods.evaluateAll((buttons) => buttons.map((button) => {
      const shopRect = button.closest('.shop-area')!.getBoundingClientRect();
      const figure = button.querySelector('figure')!;
      const face = figure.firstElementChild!;
      const faceRect = face.getBoundingClientRect();
      const caption = figure.querySelector('figcaption')!;
      const captionRect = caption.getBoundingClientRect();
      const cornerRect = face.querySelector('.product-uno__corner--bottom')?.getBoundingClientRect();
      return {
        ratio: faceRect.height / faceRect.width,
        captionBelowFace: captionRect.top >= faceRect.bottom - 1,
        captionFits: caption.scrollWidth <= caption.clientWidth + 1,
        withinShopVertically: faceRect.top >= shopRect.top && captionRect.bottom <= shopRect.bottom + 1,
        cornerAreaFraction: cornerRect ? cornerRect.width * cornerRect.height / (faceRect.width * faceRect.height) : null,
        cornerAtBottomRight: cornerRect ? cornerRect.top > faceRect.top + faceRect.height / 2 && cornerRect.left + cornerRect.width / 2 > faceRect.left + faceRect.width / 2 : null,
      };
    }));
    for (const card of geometry) {
      expect.soft(card.ratio, 'shop face keeps its portrait card proportions').toBeGreaterThan(1.45);
      expect.soft(card.ratio).toBeLessThan(1.55);
      expect.soft(card.captionBelowFace, 'caption does not consume or overlap the card face').toBe(true);
      expect.soft(card.captionFits, '商品 labels fit without truncation').toBe(true);
      expect.soft(card.withinShopVertically, 'goods and labels stay inside the shop region').toBe(true);
      if (card.cornerAreaFraction !== null) {
        expect.soft(card.cornerAreaFraction, 'corner badge must not cover the center glyph').toBeLessThan(0.15);
        expect.soft(card.cornerAtBottomRight, 'bottom badge stays in its own corner').toBe(true);
      }
    }
    await goods.last().scrollIntoViewIfNeeded();
    await expect(goods.last()).toBeInViewport({ ratio: 0.99 });
    await shop.getByRole('button', { name: '确认交换' }).scrollIntoViewIfNeeded();
    await expect(shop.getByRole('button', { name: '确认交换' })).toBeInViewport({ ratio: 0.99 });
    expect(pageErrors).toEqual([]);
  });
}
