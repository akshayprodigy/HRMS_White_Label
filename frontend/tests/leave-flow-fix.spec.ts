import { test, expect } from '@playwright/test';

async function ensureAttendanceUnlocked(page: any) {
  const attendanceHeading = page.getByRole('heading', { name: /Secure Check-In/i });

  // Wait for the authenticated shell to mount (sidebar buttons).
  try {
    await expect(page.getByRole('button', { name: /My Workspace/i })).toBeVisible({ timeout: 30000 });
  } catch (e) {
    console.log('My Workspace button not visible, might still be on login page');
    return;
  }

  // Poll for attendance modal
  const deadline = Date.now() + 30000;
  while (Date.now() < deadline) {
    const visible = await attendanceHeading.isVisible().catch(() => false);
    if (!visible) {
      await page.waitForTimeout(1000);
      const stillNotVisible = !(await attendanceHeading.isVisible().catch(() => false));
      if (stillNotVisible) return;
    }

    await page.getByRole('button', { name: /Remote\/WFH/i }).click();

    const signInWorkMode = page.getByRole('button', { name: /Sign In Work Mode/i });
    await expect(signInWorkMode).toBeEnabled({ timeout: 10000 });

    const markResponsePromise = page.waitForResponse(
      (resp: any) => resp.url().includes('/api/v1/attendance/mark'),
      { timeout: 10000 }
    );

    await signInWorkMode.click();
    const markResp = await markResponsePromise;

    if (!markResp.ok()) {
        console.log(`Attendance mark failed: HTTP ${markResp.status()}`);
    }

    await expect(attendanceHeading).toBeHidden({ timeout: 10000 });
    return;
  }
}

async function login(page: any, email: string, pass: string) {
    await page.goto('/');
    await page.getByPlaceholder('E001 or name@company.com').fill(email);
    await page.getByPlaceholder('••••••••').fill(pass);
    await page.getByRole('button', { name: 'Sign In' }).click();
    await ensureAttendanceUnlocked(page);
}

test.describe('Leave Approval Suite', () => {
    test.setTimeout(180000);

    test('Full End-to-End Approval Flow', async ({ page }) => {
        const adminEmail = 'admin@gmail.com';
        const empEmail = 'employee@gmail.com';
        const commonPass = 'test@12345';
        const uniqueType = 'UI-' + Math.floor(Math.random() * 10000);

        // 1. Setup Leave Type as Admin
        await login(page, adminEmail, commonPass);
        
        await page.getByRole('button', { name: /Admin/i }).click();
        
        const leaveLink = page.getByRole('link', { name: /leave/i }).or(page.getByText(/leave management/i));
        await leaveLink.first().click();
        
        await page.getByRole('button', { name: /Add Category/i }).or(page.getByText(/Add Type/i)).click();
        await page.locator('input[name="name"]').fill(uniqueType);
        await page.locator('input[name="total_days"]').fill('12');
        await page.getByRole('button', { name: /Save|Create/i }).click();
        
        // 2. Logout
        await page.locator('button i.bi-box-arrow-right').or(page.getByRole('button', { name: /Logout|Sign Out/i })).click();

        // 3. Apply as Employee
        await login(page, empEmail, commonPass);
        
        await page.getByRole('button', { name: /My Workspace/i }).click();
        await page.getByRole('button', { name: /Apply Leave/i }).click();
        
        await page.locator('select').first().selectOption({ label: uniqueType });
        await page.locator('textarea').first().fill('Testing Leave Flow via Playwright');
        await page.getByRole('button', { name: /Submit|Apply/i }).click();
        
        // 4. Logout
        await page.locator('button i.bi-box-arrow-right').or(page.getByRole('button', { name: /Logout|Sign Out/i })).click();

        // 5. Approve as Admin
        await login(page, adminEmail, commonPass);
        
        await page.getByRole('button', { name: /Approvals|Inbox/i }).click();
        const requestRow = page.locator('tr').filter({ hasText: uniqueType });
        await requestRow.getByRole('button', { name: /Approve/i }).first().click();
        
        // 6. Verify as Employee
        await page.locator('button i.bi-box-arrow-right').or(page.getByRole('button', { name: /Logout|Sign Out/i })).click();
        await login(page, empEmail, commonPass);
        
        await page.getByRole('button', { name: /My Workspace/i }).click();
        await expect(page.locator('tr').filter({ hasText: uniqueType })).toContainText(/APPROVED/i, { ignoreCase: true });
    });
});
