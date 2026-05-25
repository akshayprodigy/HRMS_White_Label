import { test, expect } from '@playwright/test';

// Payroll UI E2E test: Employee with LOP, HR/Admin payroll view

test.describe('Payroll UI - Pro-rated Salary Calculation', () => {
  test('Admin can view payroll run for employee with LOP', async ({ page }) => {
    // 1. Login as Admin
    await page.goto('http://localhost:5173/login');
    await page.fill('input[placeholder="E001 or name@company.com"]', 'admin@gmail.com');
    await page.fill('input[placeholder="••••••••"]', 'test@12345');
    await page.click('button:has-text("Sign In")');
    // Attendance gating: mark attendance if required
    if (await page.locator('button:has-text("Mark Attendance")').isVisible()) {
      await page.click('button:has-text("Mark Attendance")');
      await expect(page.locator('text=Attendance marked successfully')).toBeVisible();
    }

    // Wait for dashboard to be visible
    await expect(page).toHaveURL(/dashboard/);

    // 2. Navigate to Payroll section
    await page.click('nav >> text=Payroll');
    await expect(page).toHaveURL(/payroll/);

    // 3. Select March 2026 payroll run
    await page.selectOption('select[name="month"]', '3');
    await page.selectOption('select[name="year"]', '2026');
    await page.click('button:has-text("View Payroll")');

    // 4. Find employee row and check pro-rated salary
    const row = page.locator('tr', { hasText: 'employee@example.com' });
    await expect(row).toContainText('46,774.19'); // Gross pay for 29/31 days
    await expect(row).toContainText('2'); // LOP days
    await expect(row).toContainText('50,000'); // Base salary

    // 5. Optionally, open details modal
    await row.locator('button:has-text("Details")').click();
    await expect(page.locator('.modal')).toContainText('LOP Days: 2');
    await expect(page.locator('.modal')).toContainText('Gross Pay: 46,774.19');
  });
});
