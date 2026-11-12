import { test, expect, Page } from '@playwright/test';

// Employee requests an attendance correction (My Shift page); the employee's
// manager approves it from Approvals Center -> "attendance fixes".
// Needs the dev seed: employee@gmail.com reports to pm@gmail.com.

const BASE = 'http://localhost:5173';

async function login(page: Page, user: string) {
  await page.goto(BASE + '/');
  await page.getByPlaceholder('E001 or name@company.com').fill(user);
  await page.getByPlaceholder('••••••••').fill('test@12345');
  await page.getByRole('button', { name: 'Sign In', exact: true }).click();
  await page.waitForTimeout(3000);
  const wfh = page.getByRole('button', { name: /Remote\/WFH/i });
  if (await wfh.count() && await wfh.first().isVisible().catch(() => false)) {
    await wfh.first().click();
    await page.getByRole('button', { name: /Sign In Work Mode/i }).click();
  }
  await expect(page.getByRole('button', { name: /My Workspace/i })).toBeVisible({ timeout: 30_000 });
}

test('employee requests a correction, manager approves it', async ({ page }) => {
  const reason = `smoke ${Date.now()}`;
  await login(page, 'employee@gmail.com');
  await page.getByRole('button', { name: /My Work section/i }).first().click().catch(() => {});
  await page.getByRole('button', { name: 'My Shift', exact: true }).first().click();
  await page.getByRole('button', { name: /Request correction/i }).first().click();
  // Date defaults to yesterday; pick a distinct older date to avoid duplicate-pending 409s.
  await page.locator('input[type="date"]').fill(
    new Date(Date.now() - 20 * 864e5).toISOString().slice(0, 10),
  );
  await page.getByLabel('Punch-in time').fill('09:30');
  await page.getByLabel('Punch-out time').fill('18:00');
  await page.getByPlaceholder(/Forgot to punch/).fill(reason);
  await page.getByRole('button', { name: 'Submit Request' }).click();
  await expect(page.getByText(reason)).toBeVisible();

  await page.evaluate(() => localStorage.clear());
  await login(page, 'pm@gmail.com');
  await page.getByRole('button', { name: /Approvals & Spend section/i }).first().click().catch(() => {});
  await page.getByRole('button', { name: /Approvals Center/ }).first().click();
  await page.getByRole('button', { name: /attendance fixes/i }).click();
  await expect(page.getByText(reason)).toBeVisible();
  await page.getByText(reason).locator('xpath=ancestor::div[contains(@class,"rounded-xl")][1]')
    .getByRole('button', { name: /^Approve/ }).click();
  await expect(page.getByText(reason)).toHaveCount(0);
});
