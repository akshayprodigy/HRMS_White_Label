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
  const wfh = page.getByRole('button', { name: /Remote\/WFH/i });
  const home = page.getByRole('button', { name: /My Workspace/i });
  await expect(wfh.or(home).first()).toBeVisible({ timeout: 30_000 });
  if (await wfh.first().isVisible()) {
    await wfh.first().click();
    await page.getByRole('button', { name: /Sign In Work Mode/i }).click();
  }
  await expect(home).toBeVisible({ timeout: 30_000 });
}

async function openSidebarItem(page: Page, group: RegExp, item: string | RegExp) {
  const btn = page.getByRole('button', { name: item, exact: typeof item === 'string' }).first();
  if (!(await btn.isVisible())) {
    await page.getByRole('button', { name: group }).first().click();
  }
  await btn.click();
}

test('employee requests a correction, manager approves it', async ({ page, browser }) => {
  const reason = `smoke ${Date.now()}`;
  // Random day 10-60 days back to avoid duplicate-pending 409s across runs.
  const daysBack = 10 + Math.floor(Math.random() * 51);
  const day = new Date(Date.now() - daysBack * 864e5).toISOString().slice(0, 10);

  await login(page, 'employee@gmail.com');
  await openSidebarItem(page, /My Work section/i, 'My Shift');
  await page.getByRole('button', { name: /Request correction/i }).first().click();
  await page.locator('input[type="date"]').fill(day);
  await page.getByLabel('Punch-in time').fill('09:30');
  await page.getByLabel('Punch-out time').fill('18:00');
  await page.getByPlaceholder(/Forgot to punch/).fill(reason);
  await page.getByRole('button', { name: 'Submit Request' }).click();
  const mine = page.getByTestId('regularization-row').filter({ hasText: reason });
  await expect(mine).toBeVisible();
  await expect(mine).toContainText(/pending/i);

  // Manager in a fresh browser context (separate storage).
  const ctx = await browser.newContext({
    permissions: ['geolocation'],
    geolocation: { latitude: 28.6139, longitude: 77.209 },
  });
  const mgr = await ctx.newPage();
  await login(mgr, 'pm@gmail.com');
  await openSidebarItem(mgr, /Approvals & Spend section/i, /Approvals Center/);
  await mgr.getByRole('button', { name: /attendance fixes/i }).click();
  const row = mgr.getByTestId('regularization-row').filter({ hasText: reason });
  await expect(row).toBeVisible();
  await row.getByRole('button', { name: /^Approve/ }).click();
  await expect(row).toHaveCount(0);
  await ctx.close();

  // Employee's own list now shows Approved.
  await page.reload();
  await openSidebarItem(page, /My Work section/i, 'My Shift');
  await expect(
    page.getByTestId('regularization-row').filter({ hasText: reason }),
  ).toContainText(/approved/i);
});
