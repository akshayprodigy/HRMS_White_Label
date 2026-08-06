import { test, expect, Page } from '@playwright/test';

// UI smoke tests for the workforce-expansion features (F1-F6, W1-W13).
// Real login + sidebar navigation. The sidebar groups items under collapsible
// section headers ("<Group> section"), so navigation expands the group first.

const BASE = 'http://localhost:5173';

async function login(page: Page) {
  const errors: string[] = [];
  const failed: string[] = [];
  // Real JS errors are hard failures; network resource 404s are collected
  // separately (reported, not failed — a missing avatar shouldn't fail a
  // smoke test of the buttons/flows).
  page.on('console', (m) => {
    if (m.type() === 'error' && !/Failed to load resource/i.test(m.text())) errors.push(m.text());
  });
  page.on('pageerror', (e) => errors.push(String(e)));
  page.on('response', (r) => { if (r.status() === 404) failed.push(`${r.status()} ${r.url()}`); });
  (page as any)._errors = errors;
  (page as any)._failed = failed;

  await page.goto(BASE + '/');
  await page.getByPlaceholder('E001 or name@company.com').fill('admin@gmail.com');
  await page.getByPlaceholder('••••••••').fill('test@12345');
  await page.getByRole('button', { name: 'Sign In', exact: true }).click();

  await page.waitForTimeout(2000);
  // Attendance gate modal may appear — dismiss best-effort.
  for (const label of ['Remote/WFH', 'Work From Office', 'Mark Attendance']) {
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
  // Logged in => the always-present "My Workspace" nav button is visible.
  await expect(page.getByRole('button', { name: /My Workspace/i })).toBeVisible({ timeout: 30_000 });
}

// Expand the collapsible sidebar group, then click the item.
async function openTab(page: Page, group: string, item: string) {
  const itemBtn = page.getByRole('button', { name: item, exact: true });
  if (!(await itemBtn.first().isVisible().catch(() => false))) {
    await page.getByRole('button', { name: `${group} section` }).first().click();
    await page.waitForTimeout(400);
  }
  await itemBtn.first().click();
  await page.waitForTimeout(900);
}

function assertNoConsoleErrors(page: Page) {
  const errs: string[] = ((page as any)._errors || []).filter((e: string) =>
    // Ignore noise + pre-existing React dev-warnings from the shared shadcn
    // Dialog (forwardRef on Primitive.div.SlotClone) — modals still work.
    !/favicon|ResizeObserver|net::ERR_ABORTED|Download the React DevTools|cannot be given refs|forwardRef|SlotClone/i.test(e));
  const url404 = [...new Set((page as any)._failed || [])];
  if (url404.length) console.log('  [404s]', url404.join(', '));
  expect(errs, `JS errors:\n${errs.join('\n')}`).toEqual([]);
}

const PAYCOMP = 'Payroll & Compensation';
const TIMEATT = 'Time & Attendance';
const PEOPLE = 'People';

test.describe('Workforce expansion — UI smoke', () => {
  test.beforeEach(async ({ page }) => { await login(page); });

  test('F2 Employment Types: screen + add modal', async ({ page }) => {
    await openTab(page, PAYCOMP, 'Employment Types');
    await expect(page.getByRole('heading', { name: /Employment Types/i }).first()).toBeVisible();
    await expect(page.getByText(/permanent/i).first()).toBeVisible();
    await page.getByRole('button', { name: /Add Type/i }).click();
    await expect(page.getByText(/New Employment Type/i)).toBeVisible();
    await page.getByRole('button', { name: /Cancel/i }).click();
    assertNoConsoleErrors(page);
  });

  test('F3 Salary Structure: components + templates tabs', async ({ page }) => {
    await openTab(page, PAYCOMP, 'Salary Structure');
    await expect(page.getByRole('heading', { name: /Salary Structure/i }).first()).toBeVisible();
    await page.getByRole('button', { name: 'Components', exact: true }).click();
    await page.waitForTimeout(500);
    await expect(page.getByText(/Basic/i).first()).toBeVisible();
    await page.getByRole('button', { name: 'Templates', exact: true }).click();
    assertNoConsoleErrors(page);
  });

  test('W1 Leave Policy Matrix: grid renders', async ({ page }) => {
    await openTab(page, PAYCOMP, 'Leave Policy Matrix');
    await expect(page.getByRole('heading', { name: /Leave Policy Matrix/i }).first()).toBeVisible();
    await expect(page.locator('table tbody button').first()).toBeVisible();
    assertNoConsoleErrors(page);
  });

  test('W9 Late-Mark Rules: rules + process tabs', async ({ page }) => {
    await openTab(page, TIMEATT, 'Late-Mark Rules');
    await expect(page.getByRole('heading', { name: /Late-Mark Rules/i }).first()).toBeVisible();
    await expect(page.getByText(/Default late policy/i)).toBeVisible();
    await page.getByRole('button', { name: /Process & Deductions/i }).click();
    await page.waitForTimeout(500);
    await expect(page.getByRole('button', { name: /Process Month/i }).first()).toBeVisible();
    assertNoConsoleErrors(page);
  });

  test('F1 Department Heads: screen + assign modal', async ({ page }) => {
    await openTab(page, PEOPLE, 'Department Heads');
    await expect(page.getByRole('heading', { name: /Department Heads/i }).first()).toBeVisible();
    await page.getByRole('button', { name: /Assign/i }).first().click();
    await page.waitForTimeout(500);
    await expect(page.getByText(/Functional Head/i).first()).toBeVisible();
    await page.getByRole('button', { name: /Cancel/i }).click();
    assertNoConsoleErrors(page);
  });

  test('F6 Accounts Payroll Approval screen', async ({ page }) => {
    await openTab(page, PAYCOMP, 'Accounts Approval');
    await expect(page.getByRole('heading', { name: /Accounts.*Payroll Approval/i }).first()).toBeVisible();
    assertNoConsoleErrors(page);
  });

  test('W13 Accounts Payouts: three tabs', async ({ page }) => {
    await openTab(page, PAYCOMP, 'Accounts Payouts');
    await expect(page.getByRole('heading', { name: /Accounts.*Payout Verification/i }).first()).toBeVisible();
    const main = page.getByRole('main');
    await main.getByRole('button', { name: /Travel Advances/i }).click();
    await page.waitForTimeout(300);
    await main.getByRole('button', { name: /Salary Advances/i }).click();
    assertNoConsoleErrors(page);
  });

  test('W2 File Leave on behalf tab', async ({ page }) => {
    await openTab(page, TIMEATT, 'Leave Approvals');
    const fileTab = page.getByRole('tab', { name: /File Leave/i });
    if (await fileTab.count()) await fileTab.click();
    else await page.getByRole('button', { name: /^File Leave$/i }).click();
    await page.waitForTimeout(600);
    await expect(page.getByText(/File Leave on Behalf/i)).toBeVisible();
    assertNoConsoleErrors(page);
  });

  test('Payroll Bureau loads', async ({ page }) => {
    await openTab(page, PAYCOMP, 'Payroll Bureau');
    await page.waitForTimeout(800);
    await expect(page.getByText(/Payroll/i).first()).toBeVisible();
    assertNoConsoleErrors(page);
  });

  test('W10a Letter Templates: manage + editor + generate view', async ({ page }) => {
    await openTab(page, PEOPLE, 'Letter Templates');
    await expect(page.getByRole('heading', { name: /Letter Templates/i }).first()).toBeVisible();
    const main = page.getByRole('main');
    // Editor opens with the placeholder palette
    await main.getByRole('button', { name: /New Template/i }).click();
    await expect(page.getByText(/New Template/i).first()).toBeVisible();
    await expect(page.getByRole('button', { name: '{{employee_name}}', exact: true })).toBeVisible();
    await page.getByRole('button', { name: /Cancel/i }).click();
    // Generate view renders template picker + preview panel
    await main.getByRole('button', { name: /Generate Letter/i }).click();
    await page.waitForTimeout(400);
    await expect(
      page.getByText(/Select a template and employee, then click Preview/i)
    ).toBeVisible();
    assertNoConsoleErrors(page);
  });

  test('W7 Roster Planner: grid + apply-pattern dialog', async ({ page }) => {
    await openTab(page, TIMEATT, 'Roster Planner');
    await expect(page.getByRole('heading', { name: /Roster Planner/i }).first()).toBeVisible();
    const main = page.getByRole('main');
    // Grid header + at least one employee row (admin sees all)
    await expect(main.getByText('Employee', { exact: true })).toBeVisible();
    await page.waitForTimeout(600);
    // Apply-pattern dialog opens with weekday rows
    await main.getByRole('button', { name: /Apply Pattern/i }).click();
    const dlg = page.getByRole('dialog');
    await expect(dlg.getByText(/Apply weekday pattern/i)).toBeVisible();
    await expect(dlg.getByText('Mon', { exact: true })).toBeVisible();
    await dlg.getByRole('button', { name: /Cancel/i }).click();
    assertNoConsoleErrors(page);
  });

  test('W10b Celebrations report: filters + tables + counts', async ({ page }) => {
    await openTab(page, PEOPLE, 'Celebrations');
    await expect(page.getByRole('heading', { name: /Celebrations.*Events/i }).first()).toBeVisible();
    // Set a full-year range and apply so the seeded anniversaries surface
    const main = page.getByRole('main');
    await main.locator('input[type=date]').first().fill('2026-01-01');
    await main.locator('input[type=date]').nth(1).fill('2026-12-31');
    await main.getByRole('button', { name: /Apply/i }).click();
    await page.waitForTimeout(900);
    await expect(page.getByText(/Work Anniversaries/i).first()).toBeVisible();
    await expect(page.getByRole('button', { name: /Generate All/i }).first()).toBeVisible();
    assertNoConsoleErrors(page);
  });
});
