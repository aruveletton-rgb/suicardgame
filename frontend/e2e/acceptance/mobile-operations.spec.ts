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
  const hostContext = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const guestContext = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const hostPage = await hostContext.newPage();
  const guestPage = await guestContext.newPage();

  await hostPage.goto('/');
  await hostPage.getByLabel('昵称').fill('Mobile Host');
  await hostPage.getByTestId('create-room').click();
  await expect(hostPage.getByTestId('room-code')).toHaveText(/^[A-Z0-9]{6}$/);
  const host = await storedSession(hostPage);

  await guestPage.goto('/');
  await guestPage.getByLabel('昵称').fill('Mobile Guest');
  await guestPage.getByLabel('房间号').fill(host.room_code);
  await guestPage.getByTestId('join-room').click();
  await expect(guestPage.getByTestId('room-code')).toHaveText(host.room_code);
  const guest = await storedSession(guestPage);

  await hostPage.getByTestId('ready').click();
  await expect(guestPage.locator('.product-roster__seat').filter({ hasText: 'Mobile Host' })).toContainText('已准备');
  await guestPage.getByTestId('ready').click();
  await expect(hostPage.getByTestId('start-game')).toBeEnabled();
  await hostPage.getByTestId('start-game').click();
  await expect(hostPage.getByTestId('hand-card').first()).toBeVisible();

  return { hostContext, guestContext, hostPage, guestPage, host, guest };
}

async function setState(
  page: Page,
  host: Session,
  guest: Session,
  hostHand: string[],
  guestHand: string[],
  discardAssetKey = 'uno_red_5',
  currentPlayerId = host.player_id,
) {
  await command(page, host, 'TEST_SET_STATE', {
    hands: { [host.player_id]: hostHand, [guest.player_id]: guestHand },
    current_player_id: currentPlayerId,
    discard_asset_key: discardAssetKey,
    deck_asset_keys: [
      'uno_red_0', 'uno_yellow_1', 'uno_green_2', 'uno_blue_3',
      'uno_red_4', 'uno_yellow_5', 'uno_green_6', 'uno_blue_7',
    ],
  });
}

async function selectPrimary(page: Page, kind: string) {
  await page.getByRole('button', { name: '主牌', exact: true }).click();
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

test('mobile portrait and landscape complete contextual actions and pause recovery through UI', async ({ browser }) => {
  test.setTimeout(120_000);
  const room = await createStartedRoom(browser);
  const { hostContext, guestContext, hostPage, guestPage, host, guest } = room;
  try {
    await setState(
      hostPage,
      host,
      guest,
      ['sui_yi', 'uno_red_3', 'uno_blue_5', 'uno_green_6'],
      ['uno_yellow_2'],
    );
    await selectPrimary(hostPage, 'yi');
    await hostPage.getByRole('button', { name: '多选牌', exact: true }).click();
    await hostPage.locator('[data-testid="hand-card"][data-card-value="3"]').click();
    await hostPage.locator('[data-testid="hand-card"][data-card-value="5"]').click();
    await expect(hostPage.locator('.selection-summary')).toContainText('多选 2 张');
    await hostPage.getByRole('button', { name: '确认出牌 / 发动' }).scrollIntoViewIfNeeded();
    await hostPage.screenshot({ path: '../artifacts/acceptance/mobile-portrait-multiselect-390x844.png' });
    await hostPage.getByRole('button', { name: '确认出牌 / 发动' }).click();
    await passSuiReaction(hostPage, guestPage);
    await expect(hostPage.getByTestId('pending-action')).toHaveCount(0);

    await setState(hostPage, host, guest, ['uno_wild', 'uno_red_7'], ['uno_blue_2'], 'uno_yellow_4');
    await selectPrimary(hostPage, 'wild');
    await hostPage.getByRole('button', { name: '蓝色', exact: true }).click();
    await hostPage.getByRole('button', { name: '确认出牌 / 发动' }).click();
    await expect(hostPage.locator('.turn-panel')).toContainText('颜色 蓝色');

    await setState(
      hostPage,
      host,
      guest,
      ['sui_wang', 'uno_red_7'],
      ['uno_blue_2', 'uno_green_3'],
      'uno_red_5',
      guest.player_id,
    );
    await selectPrimary(hostPage, 'wang');
    await hostPage.getByRole('group', { name: '目标' }).getByRole('button', { name: 'Mobile Guest', exact: true }).click();
    await expect(hostPage.getByRole('group', { name: '目标' }).getByRole('button', { name: 'Mobile Guest', exact: true })).toHaveAttribute('aria-pressed', 'true');
    await hostPage.getByRole('button', { name: '确认出牌 / 发动' }).click();
    await expect.poll(async () => {
      const errorBanner = hostPage.getByTestId('error-banner');
      return {
        error: await errorBanner.count() ? (await errorBanner.textContent()) ?? '' : '',
        pending: await hostPage.getByTestId('pending-action').count(),
      };
    }).toEqual({ error: '', pending: 1 });
    await passSuiReaction(hostPage, guestPage);
    await expect(hostPage.getByTestId('pending-response-control_pass')).toBeVisible();
    await hostPage.getByTestId('pending-response-control_pass').click();

    await hostPage.setViewportSize({ width: 844, height: 390 });
    await guestPage.setViewportSize({ width: 844, height: 390 });
    await setState(
      hostPage,
      host,
      guest,
      [
        'uno_red_1', 'uno_red_9', 'uno_yellow_2', 'uno_yellow_8',
        'uno_green_3', 'uno_green_7', 'uno_blue_4', 'uno_blue_6',
      ],
      ['uno_red_2'],
      'uno_yellow_4',
    );
    const firstGood = hostPage.locator('.shop-row .card-button').first();
    await hostPage.locator('.shop-toggle').click();
    await expect(firstGood).toBeVisible();
    const goodAsset = await firstGood.locator('figure').getAttribute('data-asset-key');
    expect(goodAsset).toBeTruthy();
    const goodCountBefore = await hostPage.locator(`.hand-zone figure[data-asset-key="${goodAsset}"]`).count();
    await firstGood.click();
    await hostPage.getByRole('button', { name: '支付牌', exact: true }).click();
    const colorMatch = goodAsset?.match(/^uno_(red|yellow|green|blue)_/);
    const paymentCandidates = hostPage.locator(`[data-testid="hand-card"][data-card-color="${colorMatch?.[1] ?? 'red'}"]`);
    let paymentCard = paymentCandidates.first();
    if (await paymentCard.locator('figure').getAttribute('data-asset-key') === goodAsset && await paymentCandidates.count() > 1) {
      paymentCard = paymentCandidates.nth(1);
    }
    await paymentCard.click();
    await expect(hostPage.getByRole('button', { name: '确认交换' })).toBeEnabled();
    await hostPage.getByRole('button', { name: '确认交换' }).scrollIntoViewIfNeeded();
    await hostPage.screenshot({ path: '../artifacts/acceptance/mobile-landscape-shop-844x390.png' });
    await hostPage.getByRole('button', { name: '确认交换' }).click();
    await expect(hostPage.locator(`.hand-zone figure[data-asset-key="${goodAsset}"]`)).toHaveCount(goodCountBefore + 1);

    await setState(hostPage, host, guest, ['sui_nian', 'uno_red_7'], ['uno_blue_2']);
    await selectPrimary(hostPage, 'nian');
    await hostPage.getByRole('button', { name: '确认出牌 / 发动' }).click();
    await expect(hostPage.getByTestId('special-prompt-card')).toContainText('年牌');
    const pausePanel = hostPage.getByRole('alert', { name: '牌局已暂停' });
    await expect(pausePanel).toBeVisible({ timeout: 36_000 });
    await expect(pausePanel).toContainText('年牌弃牌步骤');
    await expect(pausePanel).not.toContainText('NIAN_TURN_END_DISCARD');
    await pausePanel.scrollIntoViewIfNeeded();
    await hostPage.screenshot({ path: '../artifacts/acceptance/mobile-landscape-pause-844x390.png' });

    await hostPage.setViewportSize({ width: 390, height: 844 });
    await expect(hostPage.getByRole('button', { name: '继续等待并重置时限' })).toBeVisible();
    await hostPage.screenshot({ path: '../artifacts/acceptance/mobile-portrait-pause-390x844.png' });
    await hostPage.getByRole('button', { name: '继续等待并重置时限' }).click();
    await expect(pausePanel).toHaveCount(0);
    await expect(hostPage.getByTestId('pending-response-discard_card')).toBeVisible();
    await expect(hostPage.getByTestId('prompt-countdown')).not.toHaveText('0s');
  } finally {
    await hostContext.close();
    await guestContext.close();
  }
});
