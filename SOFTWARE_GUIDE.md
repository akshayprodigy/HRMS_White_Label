# ERP United — Software User Guide

Last updated: 2026-02-23

This document explains how to use the ERP United application end-to-end: creating users/employees, managing attendance, BD lead → bid/estimate → project conversion, assigning work, logging time, applying for leave, approvals, and HR/payroll workflows.

> Note on access: Most modules are **attendance-gated**. After login, users must mark attendance for the day before they can use projects, leave, HR, BD, timesheets, tasks, approvals, notifications, and reports.

---

## 1) Getting started

### 1.1 Login
1. Open the web app.
2. Sign in using your email and password.

The system determines your permissions via role(s). Your sidebar menu changes based on your role.

### 1.2 Attendance gate (mandatory)
After login, if you have not marked attendance today, the app will block most actions.

To mark attendance:
1. Open **My Workspace**.
2. Use the attendance prompt/modal to submit today’s attendance.
3. Once attendance is marked, the rest of the system becomes available.

Why this exists:
- It enforces daily compliance (attendance must be recorded before work/approvals/timesheets).

### 1.3 Common roles
Typical roles you will see:
- **Super Admin**: system-wide administration.
- **HR**: employee directory, attendance control, leave approvals, payroll bureau, onboarding, policies, recruitment, HR analytics.
- **PM**: project delivery, tasks, cost changes, approvals.
- **Employee**: worklog/timer, timesheet, my tasks, my leave, policy acknowledgements.
- **BD (Business Developer)**: leads/pipeline, estimates, proposal generation, converting won leads into projects.
- **CEO / DOP**: high-level visibility and specific approval queues (e.g., cost adjudication threshold approvals).

### 1.4 Quickstart by role (recommended)

Employee (daily flow)
1. Login → mark attendance.
2. Go to **My Workspace** and use **Project Deliverable Tracker** (timer) to log work.
3. Stop timer to save the session to the database.
4. Use **My Timesheet** to review the week/month and add manual entries if needed.
5. Use **My Tasks** to update task status and add comments.
6. Use **My Leave** to request leave and track approvals.

HR (daily flow)
1. Login → mark attendance.
2. Use **Employee Management** for employee directory, template export, and bulk upload.
3. Use **Attendance Control** for attendance logs and correction actions.
4. Use **Leave Approvals** to process leave inbox.
5. Use **Holiday Calendar** and **Policy Center** to publish operational policies/holidays.
6. Use **Payroll Bureau** to run payroll stages.

BD (pipeline to project)
1. Create lead → maintain activities.
2. Create estimate version(s) → submit for approval.
3. Mark lead as WON → **Convert to Project** (creates project + baseline + milestones + PM membership).

PM (delivery)
1. Ensure you are a project member/manager (usually via BD conversion).
2. Use **Project Deliverables** to review milestones and costing.
3. Use **Approvals** / **Cost Adjudication** to action approval items assigned to you.

DOP/CEO (approvals)
1. Use **Approvals** for unified inbox items.
2. Use **Cost Adjudication** for project cost variance approvals.

### 1.5 What is API-backed vs “demo UI” (important)

This repo includes some screens that are fully API-backed, and some that are presentational/prototype UI.

Generally API-backed today:
- Attendance marking (gate) and attendance listing/corrections
- Timesheet timer (start/pause/resume/stop), timesheet summaries, manual time entry
- Leave balances, leave apply, leave approvals inbox + action
- HR employees list/create/bulk-upload + template download
- BD leads + estimates + approvals + convert-to-project
- Projects list, milestones, cost baseline, cost change requests, cost approval inbox + action
- Tasks list/detail/status/comments/subtasks (creation exists in API but UI is not wired yet)

Common demo/prototype UI patterns you may see:
- Buttons like “Create Project” / “Create Deliverable” that update only local UI state.
- “My Worklog” screen shows a timer and manual log entry, but it is not the authoritative worklog persistence flow.

---

## 2) Navigation map (what each menu does)

The left sidebar shows these core modules (names as shown in the UI):

### 2.1 My Workspace (everyone)
A starting dashboard for your day. If you haven’t marked attendance, you’ll be prompted.

### 2.2 HR Intelligence (HR / Super Admin / CEO)
HR summary dashboard (headcount, attendance trends, HR operations overview).

### 2.3 Employee Management (HR / Super Admin / CEO)
HR directory for viewing employees and performing bulk upload + template export.

### 2.4 Attendance Control (HR / Super Admin / CEO)
HR attendance logs and correction workflows.

### 2.5 Leave Approvals (HR / PM / Super Admin / CEO)
Manager/HR approval inbox for leave requests.

### 2.6 Payroll Bureau (HR / Super Admin / CEO)
Multi-step payroll run workflow, from draft to publish.

### 2.7 Recruitment (HR / Super Admin / CEO)
Requisition and hiring pipeline management.

### 2.8 Onboarding (HR / Super Admin / CEO)
Onboarding task flows and policy assignments.

### 2.9 Holiday Calendar (HR / Super Admin / CEO)
Add/list holidays used by attendance/leave planning.

### 2.10 Enterprise Analytics (HR / Super Admin / CEO)
HR reports and broader enterprise analytics.

### 2.11 My Worklog (everyone)
Prototype worklog screen.

Operational reality:
- The authoritative timer that persists time is on **My Workspace** (Dashboard) in the “Project Deliverable Tracker”.
- The authoritative history view is **My Timesheet**.

### 2.12 My Timesheet (everyone)
Your time entries (timer sessions and manual entries) and daily summaries.

### 2.13 My Tasks (everyone)
Tasks assigned to you across projects.

Note:
- Viewing tasks, updating status, adding comments, and toggling subtasks are API-backed.
- The “Create Deliverable” button is currently a UI placeholder (task creation is not wired in the UI yet).

### 2.14 My Leave (everyone)
Leave balances, leave application, status tracking, cancellation.

### 2.15 Policy Center (everyone)
Policies must be acknowledged by employees.

### 2.16 Project Deliverables (PM / Employee / HR / DOP / Super Admin / BD / CEO)
Project portfolio, milestones, costing/baseline, cost change requests, and delivery visibility.

> Important: The current UI includes some “create/edit” dialogs that are placeholders (demo UI). The production-backed project creation flow is **BD Convert to Project** (see section 5).

API-backed in Project Deliverables today:
- Project portfolio list (filtered by project membership for non-admins)
- Milestones list/create
- Cost baseline read and cost change request submission

Demo/prototype in Project Deliverables today:
- “Create Project” modal does not persist a project (authoritative creation is BD conversion).

### 2.17 Cost Adjudication (PM / DOP / Super Admin / CEO)
Approval queue for project cost change requests.

### 2.18 Business Development (BD / Super Admin / CEO)
Lead/pipeline management, estimate versioning, proposal generation, estimate approvals, and converting won leads to projects.

### 2.19 Profile (everyone)
Your profile details.

### 2.20 Admin Panel (Super Admin only)
Manage users, roles, permissions, and (optionally) impersonation for support.

---

## 3) Core concepts (how the system behaves)

### 3.1 Permissions (RBAC)
Permissions control actions like:
- HR employee read/write
- Employee time read/write
- BD convert lead to project
- Project write
- Approval actions

If you can see a module but cannot perform an action, you may be missing the required permission.

### 3.2 Approvals and audit logs
Some actions create approval items (multi-step) and audit logs:
- Leave approvals (Manager → HR)
- Recruitment requisition approvals
- Project cost change approvals
- BD estimate approvals

Audit logging records critical actions (who did what, when, and from where).

### 3.3 Time rules
- Exactly **one active timer** per employee at a time.
- Daily maximum is enforced (currently 9 hours/day by system rule).

---

## 4) How to create a User and Employee (HR onboarding flow)

There are two related records:
- **User**: login account (email/password + roles).
- **Employee**: HR profile (employee ID, department, designation, salary details, etc.).

### 4.1 Step A — Create a login user (Super Admin)
1. Go to **Admin Panel**.
2. Create a **User** with:
   - Email
   - Full name
   - Password
   - Active status
3. Assign role(s) (e.g., Employee, PM, HR, BD).

Result:
- The person can now log in.

### 4.2 Step B — Create the employee profile (HR)
Option 1 — Single employee creation (API-backed):
1. Go to **Employee Management**.
2. Use the employee creation workflow (if present in UI) to create the employee record.

Option 2 — Bulk create employee profiles (recommended)
1. Go to **Employee Management**.
2. Click **Export Template** to download `employee_template.xlsx`.
3. Fill the sheet.
4. Click **Bulk Upload** and upload the completed Excel file.

Important bulk upload rule:
- The Excel upload **expects the User already exists** (matched by `User Email`). If the user does not exist, that row fails.

Template columns (current):
- `User Email`
- `Employee ID`
- `Department`
- `Designation`
- `Joining Date (YYYY-MM-DD)`
- `Salary`
- `Bank Account`
- `PF Number`
- `PAN Number`

After upload:
- HR can search/filter employees by department, status, role, or keyword.

---

## 5) How BD creates bids/leads and converts them to projects

In ERP United, the primary “project creation” path is:

**Lead → Estimate Versions → Approval → Lead WON → Convert to Project**

### 5.1 Create and manage a Lead (BD)
1. Go to **Business Development**.
2. Create a new lead with:
   - Title / opportunity name
   - Account / customer info
   - Notes and pipeline stage
3. Add activities to record calls, meetings, or updates.

### 5.2 Create an Estimate (bid) for the Lead
1. Open the lead.
2. Create an **Estimate Version**.
3. Add phases/line items and pricing.
4. Save your version.

Best practice:
- Keep estimates versioned. You can compare versions later.

### 5.3 Submit estimate for approvals
1. Submit the estimate version.
2. Approvers review via approval inbox.
3. Once approved, the estimate becomes eligible for conversion.

### 5.4 Generate a Proposal
1. Open an approved estimate version.
2. Generate proposal.
3. Download/share proposal with the client.

### 5.5 Mark lead as WON
Once the customer agrees (commercially), move the lead to **WON**.

### 5.6 Convert WON lead to Project
1. From the won lead, select **Convert to Project**.
2. Provide:
   - Project code
   - Start date
   - Project Manager (user)
3. Convert.

What conversion creates automatically:
- A **Project** record linked to the lead
- A **Project Manager membership** (manager) in the project team
- A **Cost Baseline** created from the approved estimate total
- **Milestones** created from estimate phases

Result:
- The project appears in **Project Deliverables**.

---

## 6) How to create a project (operational reality)

There are two ways you may see “create project” in the UI:

### 6.1 Production-backed method (recommended): BD convert to project
Use section 5.6. This is the authoritative project creation method.

### 6.2 UI create modal (demo / placeholder)
The project list screen contains a create modal used for UI prototyping.
It currently updates only the local UI state and is not persisted.

If you need fully API-backed “create project from PM/Admin”, that endpoint/workflow should be implemented as a new vertical slice.

---

## 7) How to assign a project to an employee (team membership)

### 7.1 What “assignment” means
In the backend, project visibility and some actions are controlled via **Project Membership** (row-level filtering):
- Non-admin users only see projects where they are members.

### 7.2 Current supported assignment paths
- During **BD Convert to Project**, you assign a **Project Manager** (manager membership is created automatically).

### 7.3 Assigning additional team members
The data model supports team membership (project members), but the current UI does not yet expose a full “add/remove members” workflow with persistence.

Operational workaround (for now):
- Use task assignment and time logging against the project once membership is present.
- If you need to add members today, a Super Admin can add project members via an admin workflow/API extension (future feature) or via controlled scripts.

---

## 8) Tasks: assigning work to employees

### 8.1 PM creates tasks (project work breakdown)
1. Go to **My Tasks** or project delivery screens.
2. (Current UI limitation) The **Create Deliverable** button is not wired to the backend yet.

What works today:
- PM/authorized users can create tasks via the backend API (`POST /api/v1/tasks/`) or controlled internal scripts.
- Employees and creators can update status, comment, and toggle subtasks via the UI.

Notes:
- The backend enforces project membership checks for some task operations.

### 8.2 Employee works tasks
1. Go to **My Tasks**.
2. Open a task.
3. Update status as you work (To Do → In Progress → Review → Done).
4. Add comments when needed.

---

## 9) Timesheets: how employees log time

There are two supported time entry methods:
- **Timer sessions** (recommended)
- **Manual time entries** (back-entry)

### 9.1 Start a timer
1. Go to **My Workspace**.
2. In **Project Deliverable Tracker**, select a project and enter notes (used as task/description).
3. Click **Start**.

Rules:
- You can only have **one active timer**.
- If a timer is active, you must stop it before starting another.

### 9.2 Pause/resume/stop
- **Pause**: temporarily stops counting time but keeps the session active.
- **Resume**: continues counting time.
- **Stop**: finalizes the session and generates a time entry.

Expected outcome when you stop:
- The session is saved server-side and appears in **My Timesheet**.

### 9.3 Manual entry (back-entry)
1. Go to **My Timesheet**.
2. Choose **Log Manual Time**.
3. Provide:
   - Project
   - Start time and end time
   - Manual reason (required)

Limits:
- The system enforces a daily max (currently 9 hours/day) and may reject entries exceeding the limit.

---

## 10) Leave: how an employee applies for leave

### 10.1 Check balances
1. Go to **My Leave**.
2. Review your leave balances by type (e.g., Annual Leave, Sick Leave).

### 10.2 Apply for leave
1. Go to **My Leave**.
2. Click **Apply**.
3. Provide:
   - Leave type
   - Start date and end date
   - Reason
4. Submit.

System behavior:
- Overlapping leave requests are rejected.
- If you don’t have enough available balance, the request is rejected.

### 10.3 Approval chain (typical)
- Step 1: **Manager/PM** approval
- Step 2: **HR** final approval

You can track status in **My Leave**.

### 10.4 Cancel a leave request
If allowed by policy/status:
1. Open your leave request.
2. Choose **Cancel**.

---

## 11) Leave approvals (PM/HR)

### 11.1 PM approval
1. Go to **Leave Approvals**.
2. Open the inbox.
3. Review the request and history.
4. Approve/reject with a comment.

### 11.2 HR final approval
1. Go to **Leave Approvals**.
2. Approve/reject second-step requests.

Approval actions generate:
- Notifications to the requester
- Audit logs

---

## 12) Project costing: baseline, cost change, and cost adjudication

### 12.1 Cost baseline
A cost baseline represents the approved budget reference.

How it’s set:
- Automatically set when converting a lead to a project (from the approved estimate).
- Can be updated via cost baseline endpoints if permitted.

### 12.2 Cost change request
When project scope/budget changes:
1. Open the project.
2. Submit a **Cost Change** request with:
   - Proposed amount
   - Reason / impact

### 12.3 Approval threshold
- Small changes can go through PM approval (if authorized).
- Large changes require DOP approval.

### 12.4 Cost Adjudication inbox
1. Open **Cost Adjudication**.
2. Approve/reject cost change requests.

---

## 13) HR operations

### 13.1 Attendance Control
HR can:
- View today’s attendance logs.
- Create and act on attendance correction requests.

### 13.2 Holiday Calendar
HR can:
- Add holidays.
- Remove holidays.

### 13.3 Policies and Policy Center
HR can:
- Publish policies.
- Track acknowledgements.

Employees can:
- View policies.
- Acknowledge policies.

### 13.4 Onboarding
HR can:
- View onboarding processes.
- Mark onboarding tasks complete.

### 13.5 Recruitment
HR can:
- Create recruitment requisitions.
- Submit for approval.
- Manage applicants and interviews.

---

## 14) Payroll Bureau (HR)

Payroll is a staged workflow designed to enforce data integrity:
1. Create payroll run
2. Lock attendance
3. Lock leaves
4. Generate draft
5. Finalize
6. Publish

Employees can view:
- My Payslips

---

## 15) Approvals and Notifications (everyone)

### 15.1 Approvals
The approvals inbox aggregates cross-module approvals.
Use it to:
- Review items assigned to you
- Take action (approve/reject/request clarification)

### 15.2 Notifications
Notifications alert users when:
- A request is approved/rejected
- An approval is assigned
- Key HR/payroll events happen

---

## 16) Reports (management)

Reports include:
- Attendance
- Leave
- Utilization
- Project costs
- Executive summaries

Access is controlled by role and permissions.

---

## 17) Troubleshooting

### 17.1 “Attendance required”
- Mark attendance for today, then retry.

### 17.2 “Active timer exists”
- Stop the current timer before starting another.

### 17.2.1 “Where is the timer?”
- Use **My Workspace** → “Project Deliverable Tracker”.
- **My Worklog** is currently a prototype screen.

### 17.3 “Insufficient leave balance”
- Choose fewer days or a different leave type, or ask HR to review your balance policy.

### 17.4 “I can’t see a project”
- You may not be a member of that project.
- If you are not Super Admin/DOP, project visibility is filtered to your memberships.

---

## 18) Appendix: API reference (for admins/support)

The app uses API prefix `/api/v1`.

Common endpoints (high level):
- Auth: `/auth/login`, `/auth/me`, `/auth/refresh`
- Attendance: `/attendance/mark`, `/attendance/today`
- HR employees: `/hr/employees`, `/hr/employees/template`, `/hr/employees/bulk-upload`
- BD: `/bd/leads`, `/bd/leads/{id}/estimates`, `/bd/leads/{id}/convert-to-project`
- Projects list: `/admin/projects` (membership-filtered for non-admin users)
- Projects: `/projects/{id}/milestones`, `/projects/{id}/cost-baseline`, `/projects/{id}/cost-change`, `/projects/cost-approvals/inbox`
- Timesheets: `/timesheets/timer/start|pause|resume|stop`, `/timesheets/my`, `/timesheets/time-entries/manual`
- Leave: `/leave/balances`, `/leave/apply`, `/leave/approvals/inbox`

