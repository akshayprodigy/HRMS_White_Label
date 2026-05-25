/// <reference types="node" />
import { expect, test } from '@playwright/test';

// Reuse login helper for consistency
async function ensureAttendanceUnlocked(page: any) {
  // Wait for page to load
  await page.waitForLoadState('networkidle');
  
  const attendanceHeading = page.getByRole('heading', { name: /Secure Check-In/i });
  const dashboardMarker = page.getByText(/Workspace/i).or(page.getByText(/Intelligence/i)).or(page.getByText(/Control/i));
  
  // Wait for either the attendance modal or the dashboard to appear
  await expect(attendanceHeading.or(dashboardMarker).first()).toBeVisible({ timeout: 30_000 });

  if (await attendanceHeading.isVisible()) {
    await page.getByRole('button', { name: /Remote\/WFH/i }).click();
    await page.getByRole('button', { name: /Sign In Work Mode/i }).click();
    await expect(attendanceHeading).toBeHidden({ timeout: 20_000 });
  }
}

async function login(page: any, email: string, password: string) {
  await page.goto('/');
  await page.getByPlaceholder('E001 or name@company.com').fill(email);
  await page.getByPlaceholder('••••••••').fill(password);
  await page.getByRole('button', { name: 'Sign In' }).click();
  await ensureAttendanceUnlocked(page);
}

test('HR full lifecycle: Leave -> Approval', async ({ page }) => {
  test.setTimeout(900_000);
  const password = 'test@12345';
  const employeeEmail = 'employee@gmail.com';
  const managerEmail = 'pm@gmail.com'; 
  const hrEmail = 'hr@gmail.com';

  // 1. Login as employee
  await login(page, employeeEmail, password);
  
  // 2. MARK ATTENDANCE (Dashboard button)
  // attendance unlocked by login already, if prompt was there. 
  // Let's explicitly check if we need to click "Sign In" on dashboard if not already done.
  const dashboardSignIn = page.getByRole('button', { name: /Sign In/i }).filter({ hasText: /Work Mode/i });
  if (await dashboardSignIn.isVisible()) {
      await dashboardSignIn.click();
  }

  // 3. Apply for 'Annual Leave'
  await page.getByRole('button', { name: /My Leave/i }).click();
  await page.getByRole('button', { name: /Request Leave/i }).click();

  const leaveModal = page.locator('div[role="dialog"]');
  await expect(leaveModal.locator('button:has-text("Select Type")')).toBeVisible({ timeout: 15_000 });
  await leaveModal.locator('button:has-text("Select Type")').click();
  
  // Select 'Annual Leave' from portal-based dropdown
  await page.getByRole('option', { name: /Annual Leave/i }).click();

  const today = new Date();
  const startDate = new Date(today.getTime() + 86400000 * 5).toISOString().split('T')[0];
  const endDate = new Date(today.getTime() + 86400000 * 6).toISOString().split('T')[0];
  
  await leaveModal.locator('input[type="date"]').first().fill(startDate);
  await leaveModal.locator('input[type="date"]').last().fill(endDate);
  // Add emergency contact since it might be required or looked for
  await leaveModal.getByPlaceholder(/\+91-XXXXX-XXXXX/).fill('+91-9876543210');
  await leaveModal.locator('textarea').fill('Annual health checkup E2E test');
  
  await page.getByRole('button', { name: "Submit Request", exact: true }).click();
  // Wait for submission to complete. Check for the toast or for the dialog to be hidden
  await expect(page.getByText(/submitted successfully/i)).toBeVisible({ timeout: 15_000 });
  await expect(leaveModal).toBeHidden({ timeout: 10_000 });

  // Switch to History tab to see the pending request
  await page.getByRole('button', { name: /Historical Records/i }).click();
  await expect(page.getByText(/Pending/i).first()).toBeVisible({ timeout: 10_000 });

  // 4. Login as manager (pm@gmail.com)
  await page.evaluate(() => localStorage.clear());
  await login(page, managerEmail, password);
  
  // 5. Approve the leave in Inbox
  // pm@gmail.com should see "Leave Approvals" just like HR if they have manager permissions
  await page.getByRole('button', { name: /Leave Approvals/i }).click();
  await expect(page.getByText(/ID:/i).first()).toBeVisible({ timeout: 20_000 });
  await page.getByRole('button', { name: /Approve/i }).first().click();

  // 6. Login as HR (hr@gmail.com)
  await page.evaluate(() => localStorage.clear());
  await login(page, hrEmail, password);
  
  // 7. Final approve the leave
  await page.getByRole('button', { name: /Leave Approvals/i }).click();
  await expect(page.getByText(/ID:/i).count()).toBeGreaterThan(0);
  await page.getByRole('button', { name: /Approve/i }).first().click();
  
  await expect(page.getByText(/Approved/i).first()).toBeVisible({ timeout: 10_000 });
});
