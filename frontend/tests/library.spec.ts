import { test, expect } from '@playwright/test'

test('library page renders', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByText('PaperDesk')).toBeVisible()
  await expect(page.getByText('Import PDF')).toBeVisible()
})
