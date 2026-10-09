import { expect, test } from '@playwright/test';

test('invite entry remembers nickname, sends avatar, and renders five safe lobby seats', async ({ context, page }) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  await page.addInitScript(() => localStorage.setItem('suicardgame.nickname.v1', '本机玩家'));
  await page.goto('/?room=ABC123');

  await expect(page.getByTestId('entry-panel')).toBeVisible();
  await expect(page.getByTestId('nickname')).toHaveValue('本机玩家');
  await expect(page.getByTestId('join-code')).toHaveValue('ABC123');

  await page.getByRole('button', { name: '选择望头像' }).click();
  await page.getByTestId('create-room').click();
  await expect(page.getByTestId('room-code')).toHaveText(/^[A-Z0-9]{6}$/);
  await expect(page.locator('.product-roster__seat')).toHaveCount(5);
  await expect(page.locator('.product-invite-link__qr svg')).toBeVisible();

  const session = await page.evaluate(() => JSON.parse(localStorage.getItem('suicardgame.session.v1') ?? '{}'));
  expect(session.avatar_id).toBe('wang');

  await page.getByRole('button', { name: '复制邀请链接' }).click();
  const inviteUrl = await page.evaluate(() => navigator.clipboard.readText());
  const parsed = new URL(inviteUrl);
  expect([...parsed.searchParams.keys()]).toEqual(['room']);
  expect(parsed.searchParams.get('room')).toBe(session.room_code);
  expect(inviteUrl).not.toContain(session.session_id);
  expect(inviteUrl).not.toContain(session.reconnect_token);
});

test('rules gallery exposes structured rules and the untouched source image', async ({ page }) => {
  await page.goto('/');
  await page.getByTestId('nickname').fill('图鉴验收');
  await page.getByTestId('create-room').click();
  await page.getByTitle('打开规则图鉴').click();

  await expect(page.getByTestId('rules-gallery')).toBeVisible();
  await expect(page.getByTestId('rules-gallery')).toContainText('“有岁”质疑');
  await expect(page.getByTestId('rules-gallery')).toContainText('杠＞碰＞吃');
  await expect(page.getByTestId('rules-gallery')).toContainText('中止本局');

  const wangRule = page.locator('#rule-sui_wang');
  await expect(wangRule).toContainText('控制链允许合法岁牌与 +4');
  await wangRule.getByRole('button', { name: '查看原图' }).click();
  await expect(page.getByRole('dialog', { name: '望牌完整原图' })).toBeVisible();
  await expect(page.getByRole('dialog', { name: '望牌完整原图' }).locator('img')).toHaveAttribute('src', /15aefb709c02084fbf08600c51e42d85\.jpg$/);
});
