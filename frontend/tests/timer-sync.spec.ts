/// <reference types="node" />
import { expect, test } from '@playwright/test';

async function ensureAttendanceUnlocked(page: any) {
  const attendanceHeading = page.getByRole('heading', { name: /Secure Check-In/i });

  // Wait for the authenticated shell to mount (sidebar buttons).
  await expect(page.getByRole('button', { name: /My Workspace/i })).toBeVisible({ timeout: 60_000 });

  // The attendance modal can appear slightly after login due to async attendance checks.
  // Poll for a short window and, if present, complete it and verify the API call succeeds.
  const deadline = Date.now() + 60_000;
  while (Date.now() < deadline) {
    const visible = await attendanceHeading.isVisible().catch(() => false);
    if (!visible) return;

    await page.getByRole('button', { name: /Remote\/WFH/i }).click();

    const signInWorkMode = page.getByRole('button', { name: /Sign In Work Mode/i });
    await expect(signInWorkMode).toBeEnabled({ timeout: 60_000 });

    const markResponsePromise = page.waitForResponse(
      (resp: any) => resp.url().includes('/api/v1/attendance/mark'),
      { timeout: 60_000 }
    );

    await signInWorkMode.click();
    const markResp = await markResponsePromise;

    if (!markResp.ok()) {
      let bodyText = '';
      try {
        bodyText = await markResp.text();
      } catch {
        bodyText = '<unreadable response body>';
      }
      throw new Error(`Attendance mark failed: HTTP ${markResp.status()} ${bodyText}`);
    }

    await expect(attendanceHeading).toBeHidden({ timeout: 60_000 });
    return;
  }

  // If we got here, the modal never stabilized during the polling window.
  await expect(attendanceHeading).toBeHidden({ timeout: 1_000 });
}

test('Unified timer syncs between My Worklog and My Workspace', async ({ page }) => {
  test.setTimeout(120_000);

  const email = process.env.E2E_EMAIL || 'employee@gmail.com';
  const password = process.env.E2E_PASSWORD || 'test@12345';

  await page.goto('/');

  // Login
  await page.getByPlaceholder('E001 or name@company.com').fill(email);
  await page.getByPlaceholder('••••••••').fill(password);
  await page.getByRole('button', { name: 'Sign In' }).click();

  // Attendance gate (modal) — must be cleared before navigation.
  await ensureAttendanceUnlocked(page);

  // Go to Worklog and start a session
  // (Re-check in case modal appeared late)
  await ensureAttendanceUnlocked(page);
  await page.getByRole('button', { name: /My Worklog/i }).click();

  const selects = page.locator('select');
  await expect(selects.first()).toBeVisible();

  const taskSelect = selects.nth(1);
  if ((await taskSelect.count()) > 0) {
    // pick first real task option
    await taskSelect.selectOption({ index: 1 });
  }

  await page.getByRole('button', { name: /Start Session/i }).click();
  await expect(page.getByText('ACTIVE', { exact: true })).toBeVisible();

  // Switch to Workspace (Dashboard) and pause
  await page.getByRole('button', { name: /My Workspace/i }).click();
  await expect(page.getByText('ACTIVE', { exact: true })).toBeVisible();

  await page.getByRole('button', { name: /Pause Session/i }).click();
  await expect(page.getByText('PAUSED', { exact: true })).toBeVisible();

  // Back to Worklog and resume
  await page.getByRole('button', { name: /My Worklog/i }).click();
  await expect(page.getByText('PAUSED', { exact: true })).toBeVisible();

  await page.getByRole('button', { name: /^Resume$/i }).click();
  await expect(page.getByText('ACTIVE', { exact: true })).toBeVisible();

  // Stop from Worklog and ensure standby
  await page.getByRole('button', { name: /Stop & Sync/i }).click();
  await expect(page.getByText('STANDBY', { exact: true })).toBeVisible();

  // Confirm sync back on Workspace too
  await page.getByRole('button', { name: /My Workspace/i }).click();
  await expect(page.getByText('STANDBY', { exact: true })).toBeVisible();
});
