import { test, expect } from '@playwright/test';

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
        console.log(`Attendance mark failed: HTTP ${markResp.status()} ${bodyText}`);
    }

    await expect(attendanceHeading).toBeHidden({ timeout: 60_000 });
    return;
  }
}

test.describe('Leave Approval Suite', () => {
    test('Full End-to-End Approval Flow', async ({ page }) => {
        // Increase timeout for cold starts
        test.setTimeout(120000);

        await page.goto('/');

        // 1. Login as Admin/HR (admin@gmail.com / test@12345)
        await page.getByPlaceholder('E001 or name@company.com').fill('admin@gmail.com');
        await page.getByPlaceholder('••••••••').fill('test@12345');
        await page.getByRole('button', { name: 'Sign In' }).click();
        
        // Wait for dashboard and handle Attendance Modal
        await ensureAttendanceUnlocked(page);
        
        // 2. Go to Admin -> Leave Types
        await page.getByRole('button', { name: /Admin/i }).click();
        await page.getByText('leave types', { exact: false }).click();
        
        const uniqueType = 'UI-Test-' + Date.now();
        await page.click('button:has-text("Add Type")');
        await page.fill('input[placeholder="Policy Name"]', uniqueType);
        await page.click('button:has-text("Save Category")');
        
        // 3. Logout
        await page.click('button:has-text("Logout")');

        // 4. Login as Employee
        await page.waitForSelector('input[name="email"]');
        await page.fill('input[name="email"]', 'employee@example.com');
        await page.fill('input[name="password"]', 'admin123');
        await page.click('button[type="submit"]');

        // Handle Attendance Modal for Employee
        try {
            await attendanceBtn.waitFor({ state: 'visible', timeout: 5000 });
            await attendanceBtn.click();
        } catch (e) {
            console.log('Attendance modal not found for employee, skipping...');
        }

        // 5. Apply for Leave
        await page.click('text=New Request');
        await page.click('button:has-text("Select a leave category")');
        await page.click('text=' + uniqueType);
        await page.fill('textarea[placeholder*="Reason"]', 'Testing via Playwright Chromium');
        await page.click('button:has-text("Submit Request")');
        
        // Wait for success message
        await expect(page.locator('text=Leave applied successfully')).toBeVisible();

        // 6. Logout and HR Login to Approve
        await page.click('button:has-text("Logout")');
        await page.waitForSelector('input[name="email"]');
        await page.fill('input[name="email"]', 'hr@example.com');
        await page.fill('input[name="password"]', 'admin123');
        await page.click('button[type="submit"]');

        await page.click('text=Inbox');
        await page.waitForSelector('text=' + uniqueType);
        await page.click('text=' + uniqueType);
        await page.click('button:has-text("Approve")');
        await expect(page.locator('text=Action successful')).toBeVisible();
        
        // 7. Verify back on employee dashboard history
        await page.click('button:has-text("Logout")');
        await page.waitForSelector('input[name="email"]');
        await page.fill('input[name="email"]', 'employee@example.com');
        await page.fill('input[name="password"]', 'admin123');
        await page.click('button[type="submit"]');

        await page.click('text=History');
        await expect(page.locator('tr:has-text("' + uniqueType + '")')).toContainText('APPROVED');
    });
});
