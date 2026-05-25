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

test('HR can view payroll run for employee with LOP', async ({ page }) => {
  test.setTimeout(120_000);

  // Login as admin/HR
  const email = 'employee@gmail.com';
  const password = 'test@12345';

  await page.goto('/');

  // Login
  await page.getByPlaceholder('E001 or name@company.com').fill(email);
  await page.getByPlaceholder('••••••••').fill(password);
  await page.getByRole('button', { name: 'Sign In' }).click();

  // Attendance gate (modal)
  await ensureAttendanceUnlocked(page);

  // Check visibility of Admin/HR button
  console.log('Checking Admin button visibility...');
  const adminBtn = page.getByRole('button', { name: /Admin/i });
  if (await adminBtn.isVisible()) {
    await adminBtn.click();
    await page.getByText(/Payroll/i).first().click();
  } else {
    console.log('Admin button NOT visible. Trying HR...');
    const hrBtn = page.getByRole('button', { name: /HR/i });
    if (await hrBtn.isVisible()) {
      await hrBtn.click();
      await page.getByText(/Payroll/i).first().click();
    } else {
      console.log('Neither Admin nor HR button visible.');
    }
  }

  // Select March 2026
  await page.locator('select').first().selectOption({ label: 'March' });
  await page.locator('select').last().selectOption({ label: '2026' });
  
  // Wait for data to load
  const row = page.locator('tr').filter({ hasText: 'employee@gmail.com' });
  await expect(row).toBeVisible({ timeout: 15000 });
  
  // Verify pro-rated values
  await expect(row).toContainText('46,774.19'); 
  await expect(row).toContainText('2'); // LOP days
});
