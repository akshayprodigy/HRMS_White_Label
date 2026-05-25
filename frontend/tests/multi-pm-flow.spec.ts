/// <reference types="node" />
import { expect, test } from '@playwright/test';

function escapeRegex(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

async function ensureAttendanceUnlocked(page: any) {
  const attendanceHeading = page.getByRole('heading', { name: /Secure Check-In/i });

  // Wait for the authenticated shell to mount (sidebar buttons).
  const shellReady = page
    .getByRole('button', { name: /My Workspace/i })
    .or(page.getByRole('button', { name: /Admin Panel/i }))
    .or(page.getByRole('button', { name: /Employee Management/i }));
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

async function login(page: any, email: string, password: string) {
  await page.goto('/');
  await page.getByPlaceholder('E001 or name@company.com').fill(email);
  await page.getByPlaceholder('••••••••').fill(password);
  await page.getByRole('button', { name: 'Sign In' }).click();
  await ensureAttendanceUnlocked(page);
}

async function logout(page: any) {
  await page.evaluate(() => {
    localStorage.removeItem('token');
    localStorage.removeItem('refresh_token');
    // Some views may cache other state.
    localStorage.removeItem('impersonator');
  });
  await page.goto('/');
}

test('HR/PM multi-project assignment; employee can time tasks from both PMs', async ({ page }) => {
  test.setTimeout(900_000);

  const suffix = `${Date.now()}`;
  const short = suffix.slice(-6);
  const password = 'test@12345';

  const pm1 = { fullName: `E2E PM1 ${suffix}`, email: `e2e.pm1.${suffix}@gmail.com` };
  const pm2 = { fullName: `E2E PM2 ${suffix}`, email: `e2e.pm2.${suffix}@gmail.com` };
  const empA = { fullName: `E2E EMP A ${suffix}`, email: `e2e.empa.${suffix}@gmail.com` };
  const empB = { fullName: `E2E EMP B ${suffix}`, email: `e2e.empb.${suffix}@gmail.com` };

  const project1Name = `E2E Project A ${suffix}`;
  const project2Name = `E2E Project B ${suffix}`;
  const task1Title = `E2E Task A1 ${suffix}`;
  const task2Title = `E2E Task B1 ${suffix}`;
  const milestoneTitle = `E2E Milestone ${suffix}`;

  // 1) HR: create 4 employee records (and create the linked users in the same form)
  await login(page, 'hr@gmail.com', password);

  await page.getByRole('button', { name: /Employee Management/i }).click();
  await expect(page.getByRole('button', { name: /Add Employee/i })).toBeVisible({ timeout: 60_000 });

  const createEmployeeRecord = async (
    user: { fullName: string; email: string },
    employeeId: string,
    designation: string
  ) => {
    await page.getByPlaceholder('Search by ID, Name, or Role...').fill('');
    await page.getByRole('button', { name: /Add Employee/i }).click();
    const dialog = page.getByRole('dialog');
    await expect(dialog.getByText(/Onboard New Employee/i)).toBeVisible({ timeout: 60_000 });

    // Switch to "New" user mode.
    await dialog.getByRole('button', { name: /^New$/i }).click();

    await dialog.getByPlaceholder('Full name').fill(user.fullName);
    await dialog.getByPlaceholder('name@company.com').fill(user.email);
    await dialog.getByPlaceholder('Password').fill(password);

    await dialog.getByPlaceholder('e.g. EMP-001').fill(employeeId);
    await expect(dialog.getByPlaceholder('e.g. EMP-001')).toHaveValue(employeeId);

    // Department select
    await dialog.getByText('Select Dept', { exact: true }).click();
    await page.getByRole('option', { name: 'Engineering', exact: true }).click();
    await expect(dialog.getByText('Select Dept', { exact: true })).toBeHidden({ timeout: 60_000 });

    await dialog.getByPlaceholder('e.g. Software Engineer').fill(designation);
    await expect(dialog.getByPlaceholder('e.g. Software Engineer')).toHaveValue(designation);

    // Required by backend schema (date) and helps avoid silent UI validation issues.
    await dialog.locator('input[type="date"]').fill('2024-01-01');
    await dialog.locator('input[type="number"]').fill('100000');
    await dialog.getByPlaceholder('AC-XXXXXXXXXX').fill('000111222333');

    const createEmployeeRespPromise = page.waitForResponse(
      (resp: any) =>
        resp.url().includes('/api/v1/hr/employees/with-user') &&
        resp.request().method() === 'POST',
      { timeout: 60_000 }
    );
    await dialog.getByRole('button', { name: /Create Record/i }).click();
    const createResp = await createEmployeeRespPromise;
    if (!createResp.ok()) {
      let bodyText = '';
      try {
        bodyText = await createResp.text();
      } catch {
        bodyText = '<unreadable response body>';
      }
      throw new Error(`Create employee failed: HTTP ${createResp.status()} ${bodyText}`);
    }
    await expect(dialog).toBeHidden({ timeout: 60_000 });

    // Employee list is paginated and not ordered; filter via the search box.
    const listRespPromise = page.waitForResponse(
      (resp: any) => resp.url().includes('/api/v1/hr/employees') && resp.request().method() === 'GET',
      { timeout: 60_000 }
    );
    await page.getByPlaceholder('Search by ID, Name, or Role...').fill(employeeId);
    await listRespPromise;
    await expect(page.getByText(employeeId)).toBeVisible({ timeout: 60_000 });
  };

  // `employee.employee_id` is limited to 20 chars in DB.
  await createEmployeeRecord(pm1, `PM1-${short}`, 'Project Manager');
  await createEmployeeRecord(pm2, `PM2-${short}`, 'Project Manager');
  await createEmployeeRecord(empA, `EA-${short}`, 'Engineer');
  await createEmployeeRecord(empB, `EB-${short}`, 'Engineer');

  // 3) HR: assign PM role to pm1 and pm2
  const assignRoleToEmployee = async (employeeId: string, roleName: string) => {
    await page.getByPlaceholder('Search by ID, Name, or Role...').fill(employeeId);
    const row = page.locator('tr', { hasText: employeeId });
    await expect(row).toBeVisible({ timeout: 60_000 });

    await row.getByTitle('Manage Roles').click();
    const dialog = page.getByRole('dialog');
    await expect(dialog.getByText(/Manage Roles/i)).toBeVisible({ timeout: 60_000 });

    const checkbox = dialog.getByLabel(roleName, { exact: true });
    await expect(checkbox).toBeVisible({ timeout: 60_000 });
    if (!(await checkbox.isChecked())) {
      await checkbox.check();
    }

    const updateRespPromise = page.waitForResponse(
      (resp: any) =>
        resp.url().includes('/api/v1/hr/employees/') &&
        resp.url().includes('/roles') &&
        resp.request().method() === 'PATCH',
      { timeout: 60_000 }
    );
    await dialog.getByRole('button', { name: /Save Roles/i }).click();
    const updateResp = await updateRespPromise;
    if (!updateResp.ok()) {
      let bodyText = '';
      try {
        bodyText = await updateResp.text();
      } catch {
        bodyText = '<unreadable response body>';
      }
      throw new Error(`Update roles failed: HTTP ${updateResp.status()} ${bodyText}`);
    }
    await expect(dialog).toBeHidden({ timeout: 60_000 });
  };

  await assignRoleToEmployee(`PM1-${short}`, 'PM');
  await assignRoleToEmployee(`PM2-${short}`, 'PM');

  // 4) PM1: create project + assign a task to empA
  await logout(page);
  await login(page, pm1.email, password);

  await page.getByRole('button', { name: /Project Deliverables/i }).click();
  await expect(page.getByRole('button', { name: /Create Project/i })).toBeVisible({ timeout: 60_000 });

  await page.getByRole('button', { name: /Create Project/i }).click();
  const projectModal1 = page.locator('div.fixed.inset-0').filter({ hasText: 'Create New Project' });
  await expect(projectModal1).toBeVisible({ timeout: 60_000 });
  await projectModal1.locator('input[name="name"]').fill(project1Name);
  await projectModal1.locator('input[name="client"]').fill('E2E Client A');
  await projectModal1.locator('input[name="budget"]').fill('1000');
  await projectModal1.locator('input[name="end"]').fill('2026-12-31');

  const createProjectResp1 = page.waitForResponse(
    (resp: any) =>
      resp.url().includes('/api/v1/projects') &&
      resp.request().method() === 'POST' &&
      (resp.status() < 300 || resp.status() >= 400),
    { timeout: 60_000 }
  );
  await projectModal1.getByRole('button', { name: /^Create Project$/i }).click();
  const createResp1 = await createProjectResp1;
  if (!createResp1.ok()) {
    let bodyText = '';
    try {
      bodyText = await createResp1.text();
    } catch {
      bodyText = '<unreadable response body>';
    }
    throw new Error(`Create project failed: HTTP ${createResp1.status()} ${bodyText}`);
  }
  await expect(projectModal1).toBeHidden({ timeout: 60_000 });

  // The portfolio should show the new project (reload to avoid stale state).
  await page.reload();
  await ensureAttendanceUnlocked(page);
  await page.getByRole('button', { name: /Project Deliverables/i }).click();
  await page.getByPlaceholder('Search projects, clients or managers...').fill(project1Name);
  await expect(page.getByText(project1Name)).toBeVisible({ timeout: 60_000 });
  await page.getByRole('table').getByText(project1Name, { exact: true }).click();
  await expect(page.getByRole('button', { name: /Back to Project List/i })).toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole('heading', { name: new RegExp(escapeRegex(project1Name), 'i') })).toBeVisible({ timeout: 60_000 });

  // Create a task assigned to empA (email entered in Resource Allocation)
  const execBoard1 = page.getByRole('button', { name: /Execution Board/i });
  await expect(execBoard1).toBeVisible({ timeout: 60_000 });
  await execBoard1.click();
  await page.getByRole('button', { name: /Create Task/i }).click();
  await page.getByPlaceholder('e.g. Database Schema Migration').fill(task1Title);
  await page.locator('select[name="priority"]').selectOption('Medium');
  await page.locator('select[name="status"]').selectOption('To Do');
  await page.getByPlaceholder('e.g. Alex Thompson').fill(empA.email);
  await page.getByRole('button', { name: /Allocate Task/i }).click();

  // 5) PM2: create project + assign a task to empA (cross-PM)
  await logout(page);
  await login(page, pm2.email, password);

  await page.getByRole('button', { name: /Project Deliverables/i }).click();
  await expect(page.getByRole('button', { name: /Create Project/i })).toBeVisible({ timeout: 60_000 });

  await page.getByRole('button', { name: /Create Project/i }).click();
  const projectModal2 = page.locator('div.fixed.inset-0').filter({ hasText: 'Create New Project' });
  await expect(projectModal2).toBeVisible({ timeout: 60_000 });
  await projectModal2.locator('input[name="name"]').fill(project2Name);
  await projectModal2.locator('input[name="client"]').fill('E2E Client B');
  await projectModal2.locator('input[name="budget"]').fill('2000');
  await projectModal2.locator('input[name="end"]').fill('2026-12-31');

  const createProjectResp2 = page.waitForResponse(
    (resp: any) =>
      resp.url().includes('/api/v1/projects') &&
      resp.request().method() === 'POST' &&
      (resp.status() < 300 || resp.status() >= 400),
    { timeout: 60_000 }
  );
  await projectModal2.getByRole('button', { name: /^Create Project$/i }).click();
  const createResp2 = await createProjectResp2;
  if (!createResp2.ok()) {
    let bodyText = '';
    try {
      bodyText = await createResp2.text();
    } catch {
      bodyText = '<unreadable response body>';
    }
    throw new Error(`Create project failed: HTTP ${createResp2.status()} ${bodyText}`);
  }
  await expect(projectModal2).toBeHidden({ timeout: 60_000 });

  await page.reload();
  await ensureAttendanceUnlocked(page);
  await page.getByRole('button', { name: /Project Deliverables/i }).click();
  await page.getByPlaceholder('Search projects, clients or managers...').fill(project2Name);
  await expect(page.getByText(project2Name)).toBeVisible({ timeout: 60_000 });
  await page.getByRole('table').getByText(project2Name, { exact: true }).click();
  await expect(page.getByRole('button', { name: /Back to Project List/i })).toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole('heading', { name: new RegExp(escapeRegex(project2Name), 'i') })).toBeVisible({ timeout: 60_000 });

  const execBoard2 = page.getByRole('button', { name: /Execution Board/i });
  await expect(execBoard2).toBeVisible({ timeout: 60_000 });
  await execBoard2.click();
  await page.getByRole('button', { name: /Create Task/i }).click();
  await page.getByPlaceholder('e.g. Database Schema Migration').fill(task2Title);
  await page.locator('select[name="priority"]').selectOption('Medium');
  await page.locator('select[name="status"]').selectOption('To Do');
  await page.getByPlaceholder('e.g. Alex Thompson').fill(empA.email);
  await page.getByRole('button', { name: /Allocate Task/i }).click();

  // 6) Employee A: verify tasks exist and start timers on both tasks
  await logout(page);
  await login(page, empA.email, password);

  await page.getByRole('button', { name: /My Worklog/i }).click();

  // TimerCard uses native <select> elements.
  const selects = page.locator('select');
  await expect(selects.first()).toBeVisible({ timeout: 60_000 });

  const projectSelect = selects.nth(0);
  const taskSelect = selects.nth(1);

  // Project 1 task
  await projectSelect.selectOption({ label: project1Name });
  await taskSelect.selectOption({ label: task1Title });
  await page.getByRole('button', { name: /Start Session/i }).click();
  await expect(page.getByText('ACTIVE', { exact: true })).toBeVisible({ timeout: 60_000 });
  await page.getByRole('button', { name: /Stop & Sync/i }).click();
  await expect(page.getByText('STANDBY', { exact: true })).toBeVisible({ timeout: 60_000 });

  // Project 2 task
  await projectSelect.selectOption({ label: project2Name });
  await taskSelect.selectOption({ label: task2Title });
  await page.getByRole('button', { name: /Start Session/i }).click();
  await expect(page.getByText('ACTIVE', { exact: true })).toBeVisible({ timeout: 60_000 });
  await page.getByRole('button', { name: /Stop & Sync/i }).click();
  await expect(page.getByText('STANDBY', { exact: true })).toBeVisible({ timeout: 60_000 });

  // 7) Employee A: create a deliverable (milestone/subtask) inside an assigned task
  await page.getByRole('button', { name: /My Tasks/i }).click();
  await expect(page.getByText(/Operational Deliverables/i)).toBeVisible({ timeout: 60_000 });

  await page.getByText(task1Title, { exact: true }).first().click();
  await expect(page.getByPlaceholder('Add an update to this deliverable...')).toBeVisible({
    timeout: 60_000,
  });

  await page.getByLabel('Add milestone', { exact: true }).click();
  await page.getByPlaceholder('Milestone title').fill(milestoneTitle);

  const createMilestoneResp = page.waitForResponse(
    (resp: any) =>
      resp.url().includes('/api/v1/tasks/') &&
      resp.url().includes('/subtasks') &&
      resp.request().method() === 'POST',
    { timeout: 60_000 }
  );
  await page.getByRole('button', { name: /Create Milestone/i }).click();
  const milestoneResp = await createMilestoneResp;
  if (!milestoneResp.ok()) {
    let bodyText = '';
    try {
      bodyText = await milestoneResp.text();
    } catch {
      bodyText = '<unreadable response body>';
    }
    throw new Error(`Create milestone failed: HTTP ${milestoneResp.status()} ${bodyText}`);
  }
  await expect(page.getByText(milestoneTitle, { exact: true })).toBeVisible({ timeout: 60_000 });
});
