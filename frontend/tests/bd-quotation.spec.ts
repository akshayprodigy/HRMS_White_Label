/// <reference types="node" />
import { expect, test } from '@playwright/test';
import fs from 'fs/promises';

async function ensureAttendanceUnlocked(page: any) {
  const attendanceHeading = page.getByRole('heading', { name: /Secure Check-In/i });

  // Wait for the authenticated shell to mount (sidebar buttons).
  const shellReady = page
    .getByRole('button', { name: /My Workspace/i })
    .or(page.getByRole('button', { name: /Employee Management/i }))
    .or(page.getByRole('button', { name: /System Administration/i }));

  await expect(shellReady.first()).toBeVisible({ timeout: 60_000 });

  // Poll for the modal; it can appear slightly after login.
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

  await expect(attendanceHeading).toBeHidden({ timeout: 1_000 });
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
    data: { mode: 'remote', remarks: 'bd quotation e2e' },
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
  const data = await resp.json();
  if (typeof data?.id !== 'number') throw new Error('create lead missing id');
  return data;
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
  const data = await resp.json();
  if (typeof data?.id !== 'number') throw new Error('create estimate missing id');
  return data;
}

test('BD can generate and download a quotation PDF', async ({ page, request }, testInfo) => {
  test.setTimeout(180_000);

  const email = process.env.E2E_BD_EMAIL || 'bd@gmail.com';
  const password = process.env.E2E_BD_PASSWORD || 'test@12345';

  // Seed a unique lead + estimate via API to make the UI flow deterministic.
  const suffix = `${Date.now()}`;
  // Lead.lead_id is String(20) in the backend; also tests run in parallel across projects.
  const sanitizedProject = `${testInfo.project.name}`.replace(/[^a-z0-9]/gi, '');
  const projectTag = sanitizedProject.slice(-5).toUpperCase().padStart(5, 'X');
  const rand = Math.random().toString(36).slice(2, 6).toUpperCase();
  const leadId = `EQ${projectTag}${rand}${suffix.slice(-7)}`;
  const leadTitle = `E2E Quotation Lead ${suffix}`;

  const token = await apiLogin(request, email, password);
  await apiEnsureAttendance(request, token);

  const lead = await apiCreateLead(request, token, {
    lead_id: leadId,
    title: leadTitle,
    account_name: `E2E Account ${suffix}`,
    estimated_value: 12345,
    probability_percent: 10,
  });

  await apiCreateEstimate(request, token, lead.id, {
    name: `E2E Estimate ${suffix}`,
    currency: 'INR',
    contingency_percent: 5,
    margin_percent: 10,
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

  // UI login
  await page.goto('/');
  await page.getByPlaceholder('E001 or name@company.com').fill(email);
  await page.getByPlaceholder('••••••••').fill(password);
  await page.getByRole('button', { name: 'Sign In' }).click();

  await ensureAttendanceUnlocked(page);

  // Navigate to Business Development
  await page.getByRole('button', { name: /Business Development/i }).click();
  await expect(page.getByRole('button', { name: /New Lead/i })).toBeVisible({ timeout: 60_000 });

  // Open the seeded lead
  const search = page.getByPlaceholder(/Search leads/i);
  if (await search.count()) {
    await search.fill(leadId);
  }
  await page.getByText(leadTitle).scrollIntoViewIfNeeded();
  await page.getByText(leadTitle).click();

  // Go to estimate workspace
  await page.getByRole('button', { name: /^Estimates$/i }).click();
  await expect(page.getByRole('heading', { name: /Estimate Workspace/i })).toBeVisible({
    timeout: 60_000,
  });

  // Generate quotation and assert a PDF download happens
  const downloadPromise = page.waitForEvent('download', { timeout: 120_000 });
  await page.getByRole('button', { name: /Generate Quotation PDF/i }).click();
  const download = await downloadPromise;

  const suggested = download.suggestedFilename();
  expect(suggested.toLowerCase()).toMatch(/\.pdf$/);

  const outPath = testInfo.outputPath(suggested);
  await download.saveAs(outPath);

  const buf = await fs.readFile(outPath);
  expect(buf.subarray(0, 4).toString('utf8')).toBe('%PDF');
});
