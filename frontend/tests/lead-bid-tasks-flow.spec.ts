/// <reference types="node" />
import { expect, test } from '@playwright/test';

async function ensureAttendanceUnlocked(page: any) {
  const attendanceHeading = page.getByRole('heading', { name: /Secure Check-In/i });

  const shellReady = page
    .getByRole('button', { name: /My Workspace/i })
    .or(page.getByRole('button', { name: /Employee Management/i }))
    .or(page.getByRole('button', { name: /System Administration/i }))
    .or(page.getByRole('button', { name: /Business Development/i }))
    .or(page.getByRole('button', { name: /Project Deliverables/i }))
    .or(page.getByRole('button', { name: /Bid Requests/i }));

  await expect(shellReady.first()).toBeVisible({ timeout: 60_000 });

  const deadline = Date.now() + 60_000;
  while (Date.now() < deadline) {
    const visible = await attendanceHeading.isVisible().catch(() => false);
    if (!visible) return;

    await page.getByRole('button', { name: /Remote\/WFH/i }).click();

    const signInWorkMode = page.getByRole('button', { name: /Sign In Work Mode/i });
    await expect(signInWorkMode).toBeEnabled({ timeout: 60_000 });

    const markResponsePromise = page.waitForResponse(
      (resp: any) => resp.url().includes('/api/v1/attendance/mark'),
      { timeout: 60_000 },
    );

    await signInWorkMode.click();
    const markResp = await markResponsePromise;

    if (!markResp.ok()) {
      throw new Error(`Attendance mark failed: HTTP ${markResp.status()} ${await markResp.text()}`);
    }

    await expect(attendanceHeading).toBeHidden({ timeout: 60_000 });
    return;
  }

  await expect(attendanceHeading).toBeHidden({ timeout: 1_000 });
}

async function uiLogin(page: any, email: string, password: string) {
  await page.goto('/');
  await page.getByPlaceholder('E001 or name@company.com').fill(email);
  await page.getByPlaceholder('••••••••').fill(password);
  await page.getByRole('button', { name: 'Sign In' }).click();
  await ensureAttendanceUnlocked(page);
}

async function apiLogin(request: any, email: string, password: string): Promise<string> {
  const resp = await request.post('/api/v1/auth/login', {
    form: { username: email, password },
  });
  if (!resp.ok()) {
    throw new Error(`API login failed: HTTP ${resp.status()} ${await resp.text()}`);
  }
  const data = await resp.json();
  const token = data?.access_token;
  if (!token) throw new Error('API login missing access_token');
  return token;
}

async function apiEnsureAttendance(request: any, token: string) {
  const headers = { Authorization: `Bearer ${token}` };
  const today = await request.get('/api/v1/attendance/today', { headers });
  if (!today.ok()) {
    throw new Error(`attendance/today failed: HTTP ${today.status()} ${await today.text()}`);
  }

  const isMarked = Boolean((await today.json())?.is_marked);
  if (isMarked) return;

  const mark = await request.post('/api/v1/attendance/mark', {
    headers,
    data: { mode: 'remote', remarks: 'e2e lead bid task flow' },
  });
  if (!mark.ok()) {
    throw new Error(`attendance/mark failed: HTTP ${mark.status()} ${await mark.text()}`);
  }
}

async function apiCreateLead(request: any, token: string, payload: any) {
  const headers = { Authorization: `Bearer ${token}` };
  const resp = await request.post('/api/v1/bd/leads', { headers, data: payload });
  if (!resp.ok()) {
    throw new Error(`create lead failed: HTTP ${resp.status()} ${await resp.text()}`);
  }
  return resp.json();
}

async function apiCreateEstimate(request: any, token: string, leadId: number, payload: any) {
  const headers = { Authorization: `Bearer ${token}` };
  const resp = await request.post(`/api/v1/bd/leads/${leadId}/estimates`, {
    headers,
    data: payload,
  });
  if (!resp.ok()) {
    throw new Error(`create estimate failed: HTTP ${resp.status()} ${await resp.text()}`);
  }
  return resp.json();
}

test('BD creates bid tasks, PM submits estimate, BD requests revision, PM resubmits', async ({ browser, request }, testInfo) => {
  test.setTimeout(240_000);

  const bdEmail = process.env.E2E_BD_EMAIL || 'bd@gmail.com';
  const bdPassword = process.env.E2E_BD_PASSWORD || 'test@12345';
  const pmEmail = process.env.E2E_PM_EMAIL || 'pm@gmail.com';
  const pmPassword = process.env.E2E_PM_PASSWORD || 'test@12345';

  const suffix = `${Date.now()}`;
  const sanitizedProject = `${testInfo.project.name}`.replace(/[^a-z0-9]/gi, '');
  const projectTag = sanitizedProject.slice(-5).toUpperCase().padStart(5, 'X');
  const rand = Math.random().toString(36).slice(2, 6).toUpperCase();

  const leadCode = `BT${projectTag}${rand}${suffix.slice(-7)}`;
  const leadTitle = `E2E Bid Tasks Lead ${suffix}`;

  const bidTaskTitle = `Clarify scope + delivery plan ${suffix}`;
  const revisionNotes = `Please revise QA + integration effort (${suffix})`;

  // --- Seed: Lead + at least one estimate version (for version dropdown) ---
  const bdToken = await apiLogin(request, bdEmail, bdPassword);
  await apiEnsureAttendance(request, bdToken);

  const lead = await apiCreateLead(request, bdToken, {
    lead_id: leadCode,
    title: leadTitle,
    account_name: `E2E Account ${suffix}`,
    estimated_value: 15000,
    probability_percent: 60,
  });
  if (typeof lead?.id !== 'number') throw new Error('Seed lead missing id');

  const estimate = await apiCreateEstimate(request, bdToken, lead.id, {
    name: `E2E Estimate ${suffix}`,
    currency: 'INR',
    contingency_percent: 5,
    margin_percent: 25,
    scope_included: 'E2E scope included',
    scope_excluded: 'E2E scope excluded',
    assumptions: 'E2E assumptions',
    phases: [
      {
        phase_name: 'Discovery',
        start_offset_days: 0,
        duration_days: 3,
        description: 'E2E phase',
      },
    ],
    resource_lines: [
      {
        role_name: 'Engineer',
        quantity: 1,
        hours: 8,
        rate: 10,
        cost_decimal: 80,
      },
    ],
  });
  if (typeof estimate?.id !== 'number') throw new Error('Seed estimate missing id');

  // --- BD UI: Create bid task and assign PM ---
  const bdContext = await browser.newContext();
  const bdPage = await bdContext.newPage();
  await uiLogin(bdPage, bdEmail, bdPassword);

  await bdPage.getByRole('button', { name: /Business Development/i }).click();

  const leadSearch = bdPage.getByPlaceholder(/Search leads/i);
  if (await leadSearch.count()) {
    await leadSearch.fill(leadCode);
  }

  await bdPage.getByText(leadTitle).scrollIntoViewIfNeeded();
  await bdPage.getByText(leadTitle).click();

  // Create bid task
  const panel = bdPage.getByText('Bid Tasks & PM Estimates');
  await expect(panel).toBeVisible({ timeout: 60_000 });

  await bdPage.getByRole('button', { name: /New Bid Task/i }).click();

  await bdPage.getByPlaceholder('e.g. Scope clarification + initial delivery plan').fill(bidTaskTitle);
  await bdPage.getByRole('button', { name: /^Create$/ }).click();

  await expect(bdPage.getByText(bidTaskTitle)).toBeVisible({ timeout: 60_000 });

  // Assign PM
  const taskCard = bdPage
    .locator('div')
    .filter({ hasText: bidTaskTitle })
    .filter({ has: bdPage.getByRole('button', { name: /Assign PMs/i }) })
    .first();
  await taskCard.getByRole('button', { name: /Assign PMs/i }).click();

  await expect(bdPage.getByRole('heading', { name: /Assign PMs/i })).toBeVisible({ timeout: 60_000 });
  const assignDialog = bdPage.getByRole('dialog');
  const pmRow = assignDialog.locator('label', { hasText: /Demo PM/i });
  await expect(pmRow).toBeVisible({ timeout: 60_000 });
  await pmRow.locator('input[type="checkbox"]').check();

  const assignResponsePromise = bdPage.waitForResponse(
    (resp: any) =>
      resp.request().method() === 'POST' &&
      resp.url().includes('/api/v1/bd/leads/') &&
      resp.url().includes('/bid-tasks/') &&
      resp.url().endsWith('/assign'),
    { timeout: 60_000 },
  );
  await assignDialog.getByRole('button', { name: /^Assign$/ }).click();
  const assignResp = await assignResponsePromise;
  if (!assignResp.ok()) {
    throw new Error(`Assign PM failed: HTTP ${assignResp.status()} ${await assignResp.text()}`);
  }

  await expect(assignDialog).toBeHidden({ timeout: 60_000 });

  // Wait until PM chip appears
  await expect(taskCard.getByText(/Demo PM/i).first()).toBeVisible({ timeout: 60_000 });

  // --- PM UI: Open bid request, add lines, submit ---
  const pmContext = await browser.newContext();
  const pmPage = await pmContext.newPage();
  await uiLogin(pmPage, pmEmail, pmPassword);

  await pmPage.getByRole('button', { name: /Bid Requests/i }).click();
  await expect(
    pmPage.locator('main').getByRole('heading', { name: /My Bid Requests/i }).first(),
  ).toBeVisible({ timeout: 60_000 });

  // Select our request
  const pmSearch = pmPage.getByPlaceholder(/Search leads or tasks/i);
  if (await pmSearch.count()) {
    await pmSearch.fill(leadCode);
  }

  const pmRequestCard = pmPage
    .locator('button')
    .filter({ hasText: leadTitle })
    .filter({ hasText: bidTaskTitle })
    .first();
  await expect(pmRequestCard).toBeVisible({ timeout: 60_000 });
  await pmRequestCard.click();

  // Add a line item
  const lineItemsCard = pmPage.getByText('Line Items').locator('xpath=ancestor::div[contains(@class,"p-6")]').first();
  await lineItemsCard.getByRole('button', { name: /^Add$/ }).click();

  const titleInput = pmPage.getByPlaceholder(/e\.g\. API integration \+ validation/i).first();
  await titleInput.fill('Integration + QA');

  const lineItemCard = titleInput.locator('xpath=ancestor::div[contains(@class,"rounded-xl")]').first();
  const numberInputs = lineItemCard.locator('input[type="number"]');
  await numberInputs.nth(0).fill('12');
  await numberInputs.nth(1).fill('600');

  // Notes
  await pmPage.getByPlaceholder(/Add context, assumptions, and delivery approach/i).fill(
    'Initial estimate based on current scope.',
  );

  await pmPage.getByRole('button', { name: /Submit to BD/i }).click();

  // Confirm submitted state
  await expect(pmPage.getByText(/This revision is submitted/i)).toBeVisible({ timeout: 60_000 });

  // --- BD UI: View breakdown and request revision ---
  await bdPage.getByRole('button', { name: /Refresh/i }).click();

  // In Latest Submissions, open breakdown and request revision
  const viewBreakdown = bdPage.getByRole('button', { name: /View Breakdown/i }).first();
  await expect(viewBreakdown).toBeVisible({ timeout: 60_000 });
  await viewBreakdown.click();

  await expect(bdPage.getByRole('heading', { name: /PM Submission Details/i })).toBeVisible({ timeout: 60_000 });
  await expect(bdPage.getByText('Integration + QA')).toBeVisible({ timeout: 60_000 });

  await bdPage.getByRole('button', { name: /Request Revision/i }).click();
  await expect(bdPage.getByRole('heading', { name: /Request Revision/i })).toBeVisible({ timeout: 60_000 });
  await bdPage.getByPlaceholder(/Please re-check integration effort/i).fill(revisionNotes);

  const requestRevisionResponse = bdPage.waitForResponse(
    (resp: any) =>
      resp.request().method() === 'POST' &&
      resp.url().includes('/api/v1/bd/bid-task-reviews/') &&
      resp.url().endsWith('/request-revision'),
    { timeout: 60_000 },
  );
  await bdPage.getByRole('button', { name: /Send Request/i }).click();
  const revResp = await requestRevisionResponse;
  if (!revResp.ok()) {
    throw new Error(`Request revision failed: HTTP ${revResp.status()} ${await revResp.text()}`);
  }

  // --- PM UI: See BD notes and resubmit revised estimate ---
  await pmPage.getByRole('button', { name: /Refresh/i }).click();

  const revisedCard = pmPage
    .locator('button')
    .filter({ hasText: leadTitle })
    .filter({ hasText: bidTaskTitle })
    .filter({ hasText: /Rev\s*#2/i })
    .first();
  await expect(revisedCard).toBeVisible({ timeout: 60_000 });
  await revisedCard.click();

  await expect(pmPage.getByText(/BD Notes/i)).toBeVisible({ timeout: 60_000 });
  await expect(pmPage.getByText(revisionNotes)).toBeVisible({ timeout: 60_000 });

  // Revise numbers
  const titleInput2 = pmPage.getByPlaceholder(/e\.g\. API integration \+ validation/i).first();
  const lineItemCard2 = titleInput2.locator('xpath=ancestor::div[contains(@class,"rounded-xl")]').first();
  const numberInputs2 = lineItemCard2.locator('input[type="number"]');
  await numberInputs2.nth(0).fill('14');
  await numberInputs2.nth(1).fill('700');

  await pmPage.getByRole('button', { name: /Submit to BD/i }).click();
  await expect(pmPage.getByText(/This revision is submitted/i)).toBeVisible({ timeout: 60_000 });

  await bdContext.close();
  await pmContext.close();
});
