import { expect, test } from '@playwright/test';

test('all thirteen character card crops render in the current rules gallery', async ({ page }) => {
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto('/');
  await page.getByTestId('nickname').fill('Gallery QA');
  await page.getByTestId('create-room').click();
  await expect(page.getByTestId('room-code')).toHaveText(/^[A-Z0-9]{6}$/);
  await page.getByTitle('打开规则图鉴').click();

  const gallery = page.getByTestId('rules-gallery');
  const cards = gallery.locator('.product-rules__cards > article');
  const cropImages = cards.locator('.product-sui img');
  await expect(gallery).toBeVisible();
  await expect(cards).toHaveCount(13);
  await expect(cropImages).toHaveCount(13);
  await expect.poll(async () => cropImages.evaluateAll((images) => images.every((image) => {
    const element = image as HTMLImageElement;
    return element.complete && element.naturalWidth > 0 && element.naturalHeight > 0;
  }))).toBe(true);

  const scroll = gallery.locator('.product-rules__scroll');
  await scroll.evaluate((element) => element.scrollTo({ top: 0, behavior: 'auto' }));
  await page.screenshot({ path: '../artifacts/acceptance/card-gallery-crops-top-1920x1080.png' });
  await scroll.evaluate((element) => element.scrollTo({ top: element.scrollHeight / 2, behavior: 'auto' }));
  await page.screenshot({ path: '../artifacts/acceptance/card-gallery-crops-middle-1920x1080.png' });
  await scroll.evaluate((element) => element.scrollTo({ top: element.scrollHeight, behavior: 'auto' }));
  await page.screenshot({ path: '../artifacts/acceptance/card-gallery-crops-bottom-1920x1080.png' });
});
