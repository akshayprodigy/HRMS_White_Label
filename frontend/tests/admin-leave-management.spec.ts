import { test, expect } from '@playwright/test';

test.describe('Admin Leave Type Management', () => {
    const adminUser = {
        email: 'admin@gmail.com', // Corrected email
        password: 'test@12345'
    };

    const newLeaveType = {
        name: 'SPECIAL_TEST_LEAVE',
        description: 'Auto-test category with unpaid allowed'
    };

    test.beforeEach(async ({ page }) => {
        // Login as Super Admin
        await page.goto('/auth');
        
        // Use placeholder selectors which are more reliable in this codebase
        await page.locator('input[placeholder="E001 or name@company.com"]').fill(adminUser.email);
        await page.locator('input[placeholder="••••••••"]').fill(adminUser.password);
        
        await page.click('button:has-text("Sign In")');

        const startTime = Date.now();
        while (Date.now() - startTime < 30000) {
            const url = page.url();
            console.log(`Current URL: ${url}`);
            
            if (url.includes('/dashboard')) break;
            
            // Re-attempt click if we're still on auth
            if (url.includes('/auth') && Date.now() - startTime > 10000) {
                 if (await page.locator('button:has-text("Sign In")').isVisible()) {
                     await page.click('button:has-text("Sign In")');
                 }
            }

            // Handle attendance modal if it appears
            if (await page.locator('text=Attendance Required').isVisible({ timeout: 2000 }).catch(() => false)) {
                const markButton = page.locator('button:has-text("Mark Attendance")');
                if (await markButton.isVisible()) {
                    await markButton.click();
                }
            }
            
            await page.waitForTimeout(2000);
        }

        await expect(page).toHaveURL(/.*dashboard.*/, { timeout: 5000 });

        // Go to Admin Page
        await page.click('a:has-text("Admin")');
        await expect(page.locator('h1')).toContainText('System Administration');
    });

    test('should CRUD a leave type through the admin panel', async ({ page }) => {
        // Navigate to Leave Types sub-tab
        await page.click('button:has-text("leave-types")');
        await expect(page.locator('h2')).toContainText('Leave Management');

        // 1. Create - Check if it already exists from a previous failed run and delete if it does
        const existingRow = page.locator(`tr:has-text("${newLeaveType.name}")`);
        if (await existingRow.count() > 0) {
            await existingRow.locator('button').filter({ hasText: '' }).last().click(); // Trash icon
            page.once('dialog', dialog => dialog.accept());
            await expect(existingRow).not.toBeVisible();
        }

        // Add New
        await page.click('button:has-text("Add Leave Type")');
        await page.fill('placeholder="e.g. Annual Leave, Sick Leave"', newLeaveType.name);
        await page.fill('placeholder="Brief policy explanation..."', newLeaveType.description);
        
        // Toggle Unpaid Allowed
        const unpaidSwitch = page.locator('button[role="switch"]');
        await unpaidSwitch.click();
        
        await page.click('button:has-text("Create Leave Type")');
        await expect(page.locator('text=Leave type created successfully')).toBeVisible();

        // 2. Verify in Table
        const newRow = page.locator(`tr:has-text("${newLeaveType.name}")`);
        await expect(newRow).toBeVisible();
        await expect(newRow.locator('text=Yes')).toBeVisible(); // Unpaid Allowed badge

        // 3. Edit
        await newRow.locator('button').filter({ hasText: '' }).first().click(); // Edit icon
        await page.fill('placeholder="e.g. Annual Leave, Sick Leave"', newLeaveType.name + '_MODIFIED');
        await page.click('button:has-text("Update Policy")');
        await expect(page.locator('text=Leave type updated successfully')).toBeVisible();

        // 4. Delete
        const modifiedRow = page.locator(`tr:has-text("${newLeaveType.name}_MODIFIED")`);
        await expect(modifiedRow).toBeVisible();
        await modifiedRow.locator('button').filter({ hasText: '' }).last().click(); // Trash icon
        page.once('dialog', dialog => dialog.accept());
        await expect(modifiedRow).not.toBeVisible();
    });

    test('should reflect dynamic leave types in employee application modal', async ({ page }) => {
        const UNIQUE_TYPE = 'DYNAMIC_UI_TEST_LEAVE_' + Date.now();
        
        // Switch to Leave Types tab
        await page.click('button:has-text("leave-types")');
        
        // Create a unique leave type
        await page.click('button:has-text("Add Leave Type")');
        await page.fill('placeholder="e.g. Annual Leave, Sick Leave"', UNIQUE_TYPE);
        await page.click('button:has-text("Create Leave Type")');
        await expect(page.locator('text=Leave type created successfully')).toBeVisible();

        // Go to Leave View (as Admin, we can also apply for ourselves or switch user)
        await page.click('a:has-text("My Leave")');
        await page.click('button:has-text("Apply Leave")');

        // Look for the unique type in the dropdown selector
        const selectTrigger = page.locator('button:has-text("Select Type")');
        await selectTrigger.click();
        
        const option = page.locator(`[role="option"]:has-text("${UNIQUE_TYPE}")`);
        await expect(option).toBeVisible();
        
        // Clean up
        await page.keyboard.press('Escape'); // Close modal
        await page.click('a:has-text("Admin")');
        await page.click('button:has-text("leave-types")');
        const row = page.locator(`tr:has-text("${UNIQUE_TYPE}")`);
        await row.locator('button').filter({ hasText: '' }).last().click();
        page.once('dialog', dialog => dialog.accept());
        await expect(row).not.toBeVisible();
    });
});
