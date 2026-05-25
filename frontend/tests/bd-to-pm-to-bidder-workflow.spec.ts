/// <reference types="node" />
import { expect, test } from '@playwright/test';

async function ensureAttendanceUnlocked(page: any) {
  const attendanceHeading = page.getByRole('heading', { name: /Secure Check-In/i });

  const shellReady = page
    .getByRole('button', { name: /My Workspace/i })
    .or(page.getByRole('button', { name: /Employee Management/i }))
    .or(page.getByRole('button', { name: /System Administration/i }))
    .or(page.getByRole('button', { name: /Business Development/i }))
    .or(page.getByRole('button', { name: /Project Deliverables/i }));

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
      { timeout: 60_000 }
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
    data: { mode: 'remote', remarks: 'e2e workflow' },
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

async function apiSubmitEstimate(request: any, token: string, versionId: number) {
  const headers = { Authorization: `Bearer ${token}` };
  const resp = await request.post(`/api/v1/bd/estimates/${versionId}/submit`, { headers });
  if (!resp.ok()) {
    throw new Error(`submit estimate failed: HTTP ${resp.status()} ${await resp.text()}`);
  }
  return resp.json();
}

async function apiGetLeadApprovals(request: any, token: string, leadId: number) {
  const headers = { Authorization: `Bearer ${token}` };
  const resp = await request.get(`/api/v1/bd/leads/${leadId}/estimate-approvals`, { headers });
  if (!resp.ok()) {
    throw new Error(`get lead approvals failed: HTTP ${resp.status()} ${await resp.text()}`);
  }
  return resp.json();
}

async function apiApproveAllSteps(request: any, token: string, approvalItemId: number) {
  const headers = { Authorization: `Bearer ${token}` };

  for (let i = 0; i < 5; i++) {
    const action = await request.post(`/api/v1/approvals/${approvalItemId}/action`, {
      headers,
      data: { status: 'approved', comment: 'e2e approve' },
    });

    if (!action.ok()) {
      const body = await action.text();
      // If we somehow hit a non-actionable state, bubble up a useful error.
      throw new Error(`approve action failed: HTTP ${action.status()} ${body}`);
    }

    const item = await action.json();
    const status = String(item?.status || '').toLowerCase();
    if (status === 'approved') return item;
  }

  throw new Error('approval did not reach APPROVED within 5 steps');
}

async function apiSetLeadWon(request: any, token: string, leadId: number) {
  const headers = { Authorization: `Bearer ${token}` };
  const resp = await request.patch(`/api/v1/bd/leads/${leadId}`, {
    headers,
    data: { stage: 'won' },
  });
  if (!resp.ok()) {
    throw new Error(`set lead WON failed: HTTP ${resp.status()} ${await resp.text()}`);
  }
  return resp.json();
}

async function apiCompleteTask(request: any, token: string, taskId: number) {
  const headers = { Authorization: `Bearer ${token}` };
  const resp = await request.patch(`/api/v1/tasks/${taskId}/status?status_in=completed`, { headers });
  if (!resp.ok()) {
    throw new Error(`complete task failed: HTTP ${resp.status()} ${await resp.text()}`);
  }
  return resp.json();
}

test('BD assigns bid to PM; PM sends details pack; bidder finalizes', async ({ browser, request }, testInfo) => {
  test.setTimeout(240_000);

  const bdEmail = process.env.E2E_BD_EMAIL || 'bd@gmail.com';
  const bdPassword = process.env.E2E_BD_PASSWORD || 'test@12345';
  const pmEmail = process.env.E2E_PM_EMAIL || 'pm@gmail.com';
  const pmPassword = process.env.E2E_PM_PASSWORD || 'test@12345';
  const bidderEmail = process.env.E2E_BIDDER_EMAIL || 'employee@gmail.com';
  const bidderPassword = process.env.E2E_BIDDER_PASSWORD || 'test@12345';
  const ceoEmail = process.env.E2E_APPROVER_EMAIL || 'ceo@gmail.com';
  const ceoPassword = process.env.E2E_APPROVER_PASSWORD || 'test@12345';

  const suffix = `${Date.now()}`;
  const sanitizedProject = `${testInfo.project.name}`.replace(/[^a-z0-9]/gi, '');
  const projectTag = sanitizedProject.slice(-5).toUpperCase().padStart(5, 'X');
  const rand = Math.random().toString(36).slice(2, 6).toUpperCase();

  // Lead.lead_id is String(20) in the backend.
  const leadId = `WP${projectTag}${rand}${suffix.slice(-7)}`;
  const leadTitle = `E2E Workflow Lead ${suffix}`;
  const taskTitle = `Send Details Pack ${suffix}`;

  // --- Seed backend state: Lead + Estimate + Approval + WON ---
  const bdToken = await apiLogin(request, bdEmail, bdPassword);
  await apiEnsureAttendance(request, bdToken);

  const lead = await apiCreateLead(request, bdToken, {
    lead_id: leadId,
    title: leadTitle,
    account_name: `E2E Account ${suffix}`,
    estimated_value: 25000,
    probability_percent: 70,
  });
  if (typeof lead?.id !== 'number') throw new Error('Seed lead missing id');

  const estimate = await apiCreateEstimate(request, bdToken, lead.id, {
    name: `E2E Estimate ${suffix}`,
    currency: 'INR',
    contingency_percent: 5,
    margin_percent: 30, // avoid CEO step by default
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
        hours: 10,
        rate: 10,
        cost_decimal: 100,
      },
    ],
  });
  if (typeof estimate?.id !== 'number') throw new Error('Seed estimate missing id');

  await apiSubmitEstimate(request, bdToken, estimate.id);

  const approvals = await apiGetLeadApprovals(request, bdToken, lead.id);
  const pending = Array.isArray(approvals)
    ? approvals.find((a: any) => String(a?.status || '').toLowerCase() === 'pending')
    : null;
  if (typeof pending?.id !== 'number') throw new Error('No pending approval item found');

  const ceoToken = await apiLogin(request, ceoEmail, ceoPassword);
  await apiEnsureAttendance(request, ceoToken);
  await apiApproveAllSteps(request, ceoToken, pending.id);

  await apiSetLeadWon(request, bdToken, lead.id);

  // --- BD converts lead to project, assigning PM ---
  const bdContext = await browser.newContext();
  const bdPage = await bdContext.newPage();
  await uiLogin(bdPage, bdEmail, bdPassword);

  await bdPage.getByRole('button', { name: /Business Development/i }).click();
  await expect(bdPage.getByRole('button', { name: /New Lead/i })).toBeVisible({ timeout: 60_000 });

  const leadSearch = bdPage.getByPlaceholder(/Search leads/i);
  if (await leadSearch.count()) {
    await leadSearch.fill(leadId);
  }
  await bdPage.getByText(leadTitle).scrollIntoViewIfNeeded();
  await bdPage.getByText(leadTitle).click();

  const convertButton = bdPage.getByRole('button', { name: /Convert to Project/i });
  await expect(convertButton).toBeVisible({ timeout: 60_000 });
  await convertButton.click();

  const pmSelect = bdPage.getByTitle('Select PM');
  await expect(pmSelect).toBeVisible({ timeout: 60_000 });
  await pmSelect.selectOption({ label: 'Demo PM' });

  const convertRespPromise = bdPage.waitForResponse(
    (resp: any) => resp.url().includes(`/api/v1/bd/leads/${lead.id}/convert-to-project`) && resp.request().method() === 'POST',
    { timeout: 60_000 }
  );
  await bdPage.getByRole('button', { name: /Convert Now/i }).click();
  const convertResp = await convertRespPromise;
  expect(convertResp.ok()).toBeTruthy();
  const project = await convertResp.json();
  const projectId = project?.id;
  if (typeof projectId !== 'number') throw new Error('Convert-to-project response missing project id');
  const projectName = String(project?.name || leadTitle);

  await bdContext.close();

  // --- PM adds bidder to project, creates "details pack" task ---
  const pmContext = await browser.newContext();
  const pmPage = await pmContext.newPage();
  await uiLogin(pmPage, pmEmail, pmPassword);

  await pmPage.getByRole('button', { name: /Project Deliverables/i }).click();
  await expect(pmPage.getByPlaceholder('Search projects, clients or managers...')).toBeVisible({ timeout: 60_000 });

  await pmPage.getByPlaceholder('Search projects, clients or managers...').fill(projectName);
  const projectRow = pmPage.locator('tbody tr').filter({ hasText: projectName }).first();
  await expect(projectRow).toBeVisible({ timeout: 60_000 });
  await projectRow.click();
  await expect(pmPage.getByRole('heading', { name: projectName })).toBeVisible({ timeout: 60_000 });

  // Go to Team tab
  await pmPage.getByRole('button', { name: /Resource Matrix/i }).click();
  await expect(pmPage.getByRole('heading', { name: /Project Resource Matrix/i })).toBeVisible({ timeout: 60_000 });
  await pmPage.getByRole('button', { name: /Add Member/i }).click();

  const memberSearch = pmPage.getByPlaceholder(/SEARCH EMPLOYEES/i);
  await memberSearch.fill('Demo');
  await pmPage.getByText(/Demo Employee/i).click();

  await pmPage.getByRole('button', { name: /Add\s+\d+\s+Selected Members/i }).click();
  await expect(pmPage.getByText(/Demo Employee/i)).toBeVisible({ timeout: 60_000 });

  // Create task assigned to Demo Employee
  await pmPage.getByRole('button', { name: /Execution Board/i }).click();
  await pmPage.getByRole('button', { name: /Create Task/i }).click();

  await pmPage.locator('input[name="title"]').fill(taskTitle);

  // Allocation dropdown is a <select> with an option containing the user name.
  await pmPage.locator('select[name="assigned"]').selectOption({ label: 'Demo Employee' });

  const createTaskRespPromise = pmPage.waitForResponse(
    (resp: any) => resp.url().includes('/api/v1/tasks/') && resp.request().method() === 'POST',
    { timeout: 60_000 }
  );
  await pmPage.getByRole('button', { name: /Allocate Task/i }).click();
  const taskResp = await createTaskRespPromise;
  expect(taskResp.ok()).toBeTruthy();
  const createdTask = await taskResp.json();
  const createdTaskId = createdTask?.id;
  if (typeof createdTaskId !== 'number') throw new Error('Task create response missing id');

  await pmContext.close();

  // --- Bidder (employee) completes milestones + finalizes task ---
  const bidderContext = await browser.newContext();
  const bidderPage = await bidderContext.newPage();
  await uiLogin(bidderPage, bidderEmail, bidderPassword);

  await bidderPage.getByRole('button', { name: /My Tasks/i }).click();
  await expect(bidderPage.getByRole('heading', { name: /Operational Deliverables/i })).toBeVisible({ timeout: 60_000 });

  await bidderPage.getByPlaceholder(/Search operational tasks/i).fill(taskTitle);
  await expect(bidderPage.getByRole('heading', { name: taskTitle })).toBeVisible({ timeout: 60_000 });
  await bidderPage.getByRole('heading', { name: taskTitle }).click();

  // Add a milestone inside the deliverable (TaskDetailModal)
  await expect(bidderPage.getByText(/Milestone Pipeline/i)).toBeVisible({ timeout: 60_000 });
  await bidderPage.getByLabel('Add milestone').click();

  await bidderPage.getByPlaceholder(/Milestone title/i).fill('Finalize project');
  await bidderPage.getByRole('button', { name: /Create Milestone/i }).click();

  // Mark it complete by toggling the checkbox inside the milestone card.
  const milestoneCard = bidderPage.locator('div').filter({ has: bidderPage.getByText('Finalize project') }).first();
  await expect(milestoneCard).toBeVisible({ timeout: 60_000 });
  await milestoneCard.locator('div').first().click();

  // Finalize the task via API (UI wiring for status changes is not present yet).
  const bidderToken = await apiLogin(request, bidderEmail, bidderPassword);
  await apiEnsureAttendance(request, bidderToken);
  await apiCompleteTask(request, bidderToken, createdTaskId);

  // Reload to ensure the tasks list reflects server-side status changes.
  await bidderPage.reload();
  await ensureAttendanceUnlocked(bidderPage);

  await bidderPage.getByRole('button', { name: /My Tasks/i }).click();
  await expect(bidderPage.getByRole('heading', { name: /Operational Deliverables/i })).toBeVisible({ timeout: 60_000 });
  await bidderPage.getByPlaceholder(/Search operational tasks/i).fill(taskTitle);

  const taskHeading = bidderPage.getByRole('heading', { name: taskTitle });
  await expect(taskHeading).toBeVisible({ timeout: 60_000 });
  const taskCard = bidderPage.locator('div', { has: taskHeading }).first();
  await expect(taskCard.getByText(/^completed$/i)).toBeVisible({ timeout: 60_000 });

  await bidderContext.close();
});
