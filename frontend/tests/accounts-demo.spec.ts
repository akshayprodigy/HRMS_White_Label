import { test, expect, Page } from '@playwright/test';

// Read-only browser walkthrough of the Accounts demo path, logged in as the
// real Accounts user. Asserts the seeded queues render with their action
// buttons — it never CLICKS approve/verify, so the demo data is preserved.

const BASE = 'http://localhost:5173';
const PAYCOMP = 'Payroll & Compensation';

async function loginAsAccounts(page: Page) {
  const errors: string[] = [];
  page.on('console', (m) => {
    if (m.type() === 'error' && !/Failed to load resource/i.test(m.text())) errors.push(m.text());
  });
  page.on('pageerror', (e) => errors.push(String(e)));
  (page as any)._errors = errors;

  await page.goto(BASE + '/');
  await page.getByPlaceholder('E001 or name@company.com').fill('accounts@gmail.com');
  await page.getByPlaceholder('••••••••').fill('test@12345');
  await page.getByRole('button', { name: 'Sign In', exact: true }).click();
  await page.waitForTimeout(2000);
  // Attendance is already marked server-side; dismiss the modal if it shows.
  for (const label of ['Work From Office', 'Remote/WFH', 'Mark Attendance']) {
    const b = page.getByRole('button', { name: new RegExp(label, 'i') });
    if (await b.count() && await b.first().isVisible().catch(() => false)) {
      await b.first().click().catch(() => {});
      const confirm = page.getByRole('button', { name: /Sign In Work Mode|Confirm|Check In/i });
      if (await confirm.count() && await confirm.first().isVisible().catch(() => false)) {
        await confirm.first().click().catch(() => {});
      }
      break;
    }
  }
  await expect(page.getByRole('heading', { name: /My Workspace/i }).first()).toBeVisible({ timeout: 30_000 });
}

async function openTab(page: Page, group: string, item: string) {
  const itemBtn = page.getByRole('button', { name: item, exact: true });
  if (!(await itemBtn.first().isVisible().catch(() => false))) {
    await page.getByRole('button', { name: `${group} section` }).first().click();
    await page.waitForTimeout(400);
  }
  await itemBtn.first().click();
  await page.waitForTimeout(900);
}

test.describe('Accounts demo — read-only', () => {
  test.beforeEach(async ({ page }) => { await loginAsAccounts(page); });

  test('Accounts Payroll Approval shows a finalized run to approve', async ({ page }) => {
    await openTab(page, PAYCOMP, 'Accounts Approval');
    await expect(page.getByRole('heading', { name: /Accounts.*Payroll Approval/i }).first()).toBeVisible();
    const main = page.getByRole('main');
    // The seeded Aug 2026 finalized run appears in "Awaiting Approval".
    await expect(main.getByText(/Aug 2026/i).first()).toBeVisible();
    await expect(main.getByRole('button', { name: /Approve for Payment/i }).first()).toBeVisible();
    // Drill-down: expand the run → per-employee sheet with a Net Pay column.
    await main.getByRole('button', { name: /Aug 2026/i }).first().click();
    await expect(main.getByText(/Employee-wise breakdown/i)).toBeVisible();
    await expect(main.getByText(/Demo Employee/i).first()).toBeVisible();
    await expect(main.getByRole('button', { name: /Download sheet/i })).toBeVisible();
    // Editable: pencil opens the reason-gated edit modal.
    await main.getByRole('button', { name: /Edit this line/i }).first().click();
    const editDlg = page.getByRole('dialog');
    await expect(editDlg.getByText(/Edit payroll line/i)).toBeVisible();
    await expect(editDlg.getByText(/Reason/i).first()).toBeVisible();
    await editDlg.getByRole('button', { name: /Cancel/i }).click();
  });

  test('Salary Structure is accessible to Accounts with min/max % config', async ({ page }) => {
    await openTab(page, PAYCOMP, 'Salary Structure');
    await expect(page.getByRole('heading', { name: /Salary Structure/i }).first()).toBeVisible();
    const main = page.getByRole('main');
    await main.getByRole('button', { name: /^Components$/i }).click();
    await page.waitForTimeout(400);
    await main.getByRole('button', { name: /Add Component/i }).click();
    const dlg = page.getByRole('dialog');
    // Switch to percent-of-basic → the Min %/Max % bound fields appear.
    await dlg.getByRole('combobox').nth(1).selectOption('percent_of_basic');
    await expect(dlg.getByText(/Min %/i)).toBeVisible();
    await expect(dlg.getByText(/Max %/i)).toBeVisible();
    await dlg.getByRole('button', { name: /Cancel/i }).click();
  });

  test('Accounts Payouts: all three queues show seeded items', async ({ page }) => {
    await openTab(page, PAYCOMP, 'Accounts Payouts');
    await expect(page.getByRole('heading', { name: /Accounts.*Payout Verification/i }).first()).toBeVisible();
    const main = page.getByRole('main');
    // Expenses tab (default)
    await expect(main.getByText(/Client visit reimbursement/i)).toBeVisible();
    await expect(main.getByRole('button', { name: /Verify for Payout/i }).first()).toBeVisible();
    // Drill-down: expand the claim → line items appear.
    await main.getByRole('button', { name: /Client visit reimbursement/i }).click();
    await expect(main.getByText(/Intercity cab/i)).toBeVisible();
    await expect(main.getByText(/Client lunch/i)).toBeVisible();
    // Travel tab
    await main.getByRole('button', { name: /Travel Advances/i }).click();
    await page.waitForTimeout(400);
    await expect(main.getByText(/Vendor site audit/i)).toBeVisible();
    // Salary Advances tab
    await main.getByRole('button', { name: /Salary Advances/i }).click();
    await page.waitForTimeout(400);
    await expect(main.getByText(/Demo HR/i)).toBeVisible();
    await expect(main.getByRole('button', { name: /Verify Disbursement/i }).first()).toBeVisible();
  });
});
