# ERP United

A production-ready ERP platform.

## Software Guide

See [SOFTWARE_GUIDE.md](SOFTWARE_GUIDE.md) for an end-to-end user walkthrough (HR, BD, projects, tasks, timesheets, leave, approvals, payroll).

## Features Implemented

### 🛡️ Core Infrastructure & Security
- **Authentication**: JWT-based secure login with Refresh Token rotation strategy.
- **RBAC (Role-Based Access Control)**: Granular permissions for Employee, PM, HR, Admin, CEO, and Super Admin.
- **Audit Logging**: Backend infrastructure to record critical system actions and approvals.
- **Unified Approvals Engine**: Centralized state-machine for cross-module authorizations (Leaves, Payroll, Timesheets).
- **Notification System**: Real-time alert center for workflow updates and system announcements.

### 👥 Human Resources (HRM)
- **Employee Management**: Full lifecycle tracking from onboarding to offboarding, including bulk template uploads.
- **Payroll Bureau**: Multi-stage automated payroll processing (Attendance Lock -> Leave Lock -> Draft -> Final -> Publish).
- **Attendance & Geo-Control**: Mandatory attendance gating with geolocation tracking and manual correction workflows.
- **Leave Bureau**: Balance-driven leave application system with multi-level approval hierarchies.
- **Policy Center**: Digital repository for corporate policies with mandatory employee acknowledgement tracking.

## Payroll Bureau (HR) — UI Flow

Prereqs:
- Attendance is **marked for today** (attendance gating applies to payroll routes).
- Permissions (RBAC):
	- View dashboard/lines: `hr payroll view`
	- Start run + lock attendance/leaves + generate draft: `hr payroll run`
	- Finalize + publish: `hr payroll approve`
- Ensure each active employee has `salary` set (otherwise payroll lines will compute as `0`).

Operational flow:
1. Open **Payroll Bureau** → loads the payroll dashboard.
2. Select **Month** and **Year** → click **Start New Run**.
3. Step 1 (**Initialized**) → click **Next: Lock Attendance**.
4. Step 2 (**Attendance Locked**) → click **Next: Lock Leaves**.
5. Step 3 (**Leaves Locked**) → click **Generate Draft** (computes draft payroll lines).
6. Step 4 (**Review Draft Lines**) → verify payable/LOP days + totals → click **Finalize & Approve**.
7. Step 5 (**Payroll Finalized**) → click **Publish Payslips**.

Notes:
- Draft computation currently prorates by month days and applies LOP for overlapping **approved unpaid** leaves.
- If you refresh/resume a run from the dashboard, the UI loads existing draft lines automatically once the run is in draft-generated (or later) state.

### ⏱️ Operations & Project Management
- **Timesheet Control**: Hybrid submission system with live precision timers and manual back-entry support.
- **Project Portfolio**: Unified view of project health, milestones, and resource allocation.
- **Task Orchestration**: Nested subtask management with status tracking and collaborator assignments.

### 📊 Enterprise Intelligence
- **Operational Analytics**: Real-time dashboards for management (Attendance trends, Leave rates, Resource utilization).
- **Financial Tracking**: Live project cost variance monitoring vs. baselined budgets.
- **Automated Reporting**: Export-ready summaries for workforce compliance and project efficiency.

## Quick Start

Run the entire stack with one command:

```bash
make up
```

If you previously ran the production stack locally, stop it first (it expects real SSL certs under `/etc/letsencrypt`):

```bash
make down-prod
```

Wait for the containers to start, then run migrations:

```bash
make migrate
```

Access the application:
- Frontend: [http://localhost:5173](http://localhost:5173)
- API Docs: [http://localhost:8001/docs](http://localhost:8001/docs)
- Health Check: [http://localhost:8001/api/v1/health](http://localhost:8001/api/v1/health)

## Development Commands

We use a `Makefile` for common tasks:

- `make build`: Build docker images
- `make up`: Start the development stack
- `make down`: Stop the development stack
- `make logs`: Tail docker logs
- `make migrate`: Run database migrations
- `make test`: Run backend tests
- `make ui-test`: Run UI tests (Playwright) in a visible browser
- `make shell`: Open a shell in the backend container

## UI Tests (Playwright)

Run all UI tests via the single script entrypoint (starts Docker, migrates, seeds, then runs Playwright in a visible browser):

```bash
make ui-test
```

Optional overrides:

```bash
E2E_EMAIL=employee@gmail.com E2E_PASSWORD=test@12345 E2E_SLOWMO=250 make ui-test
```

## Production

To run in production mode with Nginx:

```bash
make up-prod
```

## Structure

- `backend/`: FastAPI application.
- `frontend/`: React Vite application (TypeScript).
- `docker-compose.yml`: Development configuration.
- `docker-compose.prod.yml`: Production configuration with Nginx.
