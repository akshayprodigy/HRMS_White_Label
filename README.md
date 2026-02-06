# United Exploration ERP (Monorepo)

This repo is a scaffolded monorepo with:

- Backend: FastAPI + SQLAlchemy 2 + Alembic + Pydantic v2
- Frontend: React + Vite + React Router + TanStack Query + Material UI

Implemented backend modules:

- Auth: JWT access token + refresh token (httpOnly cookie)
- RBAC: roles + permissions, enforced server-side
- Admin API: manage users / roles / permissions
- Core API: organizations / sites / projects / cost centers
- HR API: employees / attendance / employee documents / employee assets
- Inventory API: items / UOMs / warehouses / GRNs / issues / project consumption report
- Projects API: DPR (Daily Progress Report) entry + metrics
- Projects API: finance postings (revenues + direct expenses) + profitability rollups
- Audit logging: request-scoped `X-Request-Id` + DB-backed audit logs for create/update/delete

## Features covered

- Authentication: JWT access token + refresh token rotation (httpOnly cookie)
- Authorization: server-side RBAC with permission codes; permission-gated frontend navigation
- Admin: manage users, roles, permissions; view audit logs; run leave-credit job
- Auditability: `X-Request-Id` correlation + DB-backed audit log rows for create/update/delete
- Core master data: organizations, sites, projects, cost centers
- HR: employees, attendance (labor cost input), leave types/policies/balances/requests, holiday calendar, employee documents, employee assets
- Inventory: UOMs, items, warehouses, GRNs (receipts), material issues, project-wise consumption report
- Projects: DPR entry + metrics, finance postings (revenues + direct expenses), profitability rollups (revenue vs labor/materials/expenses)
- Frontend pages: login, dashboard, admin users, audit logs, core CRUD pages, HR pages (employees + leave flows), inventory pages (masters + GRNs/issues + consumption), projects pages (DPR + profitability)
- Dev workflow: Docker Compose (MariaDB + backend), Alembic migrations, DB-gated integration tests

## Prereqs

- Docker + Docker Compose
- Node.js 18+ (or 20+ recommended)

## Local development

### 1) Start MariaDB + backend (Docker Compose)

Docker Desktop (or another Docker daemon) must be running.

1. Create a local env file:

   - `cp .env.example .env`

   Set at least:

   - `JWT_SECRET_KEY` (required for login/refresh)

2. Start services:

   - `docker compose up -d db`
   - `docker compose up --build -d backend`

3. Run migrations:

   - `docker compose exec backend alembic upgrade head`

4. (Optional) Bootstrap an initial admin user:

   - Run (pass env vars at exec time):
     - `docker compose exec -e BOOTSTRAP_ADMIN_EMAIL=admin@example.com -e BOOTSTRAP_ADMIN_PASSWORD='...' backend python -m app.scripts.bootstrap_admin`

5. Verify:

   - Backend health: http://localhost:8000/api/v1/health

### 2) Start frontend (Vite)

1. Install deps:

   - `cd frontend`
   - `npm install`

2. Run dev server:

   - `npm run dev`

Open http://localhost:5173

Notes:

- The Vite dev server proxies `/api` to `http://localhost:8000`.
- JWT access tokens are stored in `localStorage`; refresh token is stored as an httpOnly cookie.

## Production deployment (Hostinger VPS / any Linux VM)

This repo includes a production Docker Compose stack:

- MariaDB (`db`) with a named volume
- FastAPI backend (`backend`) using Gunicorn + Uvicorn workers and auto-running Alembic migrations on startup
- React frontend (`frontend`) built and served by Nginx
- Caddy (`caddy`) as the public reverse proxy with automatic HTTPS (Let’s Encrypt)

### Quick start

1. On the VPS, copy the env template and set values:

   - `cp .env.prod.example .env`
   - Set at least: `DOMAIN`, `JWT_SECRET_KEY`, `DB_PASSWORD`, `DB_ROOT_PASSWORD`, `CORS_ORIGINS`

2. Ensure DNS is pointing to your VPS:

   - Create an `A` record for your `DOMAIN` → VPS public IP

3. Start the production stack:

   - `docker compose -f docker-compose.prod.yml up -d --build`

4. Bootstrap the first admin (one-time):

   - `BOOTSTRAP_ADMIN_EMAIL=admin@yourdomain.com BOOTSTRAP_ADMIN_PASSWORD='...' make prod-bootstrap-admin`

5. Verify:

   - `https://<DOMAIN>` (frontend)
   - `https://<DOMAIN>/api/v1/health` (backend health)

### Updates / maintenance

- Pull latest code: `git pull`
- Rebuild/restart: `docker compose -f docker-compose.prod.yml up -d --build`
- View logs: `make prod-logs`
- Stop: `make prod-down`

### Notes

- In production, don’t publish the DB port (the production compose does not expose `3306`).
- Keep `.env` private and never commit it.
- If you serve frontend + API on the same domain, `REFRESH_COOKIE_SAMESITE=lax` and `REFRESH_COOKIE_SECURE=true` are recommended.

## API documentation

Base URL: `http://localhost:8000/api/v1`

### Public

- `GET /health` → `{ "status": "ok" }`
- `GET /db/ping` → `{ "status": "ok" }` (requires DB connection)

### Auth (`/auth`)

- `POST /auth/login`
   - Body: `{ "email": "user@example.com", "password": "..." }`
   - Response: `{ access_token, expires_in, user, permissions }`
   - Also sets refresh cookie `refresh_token` (httpOnly)

- `POST /auth/refresh`
   - Uses refresh cookie and returns a fresh access token

- `POST /auth/logout`
   - Revokes refresh token (if present) and clears cookie

- `GET /auth/me` (requires `Authorization: Bearer <access_token>`)

### Admin (`/admin`) — all endpoints require permissions

- Users (`admin.users.read` / `admin.users.write`)
   - `GET /admin/users`
   - `POST /admin/users`
   - `GET /admin/users/{user_id}`
   - `PUT /admin/users/{user_id}`
   - `DELETE /admin/users/{user_id}`
   - `PUT /admin/users/{user_id}/roles`

- Roles (`admin.roles.read` / `admin.roles.write`)
   - `GET /admin/roles`
   - `POST /admin/roles`
   - `PUT /admin/roles/{role_id}`
   - `DELETE /admin/roles/{role_id}`

- Permissions (`admin.permissions.read` / `admin.permissions.write`)
   - `GET /admin/permissions`
   - `POST /admin/permissions`
   - `PUT /admin/permissions/{permission_id}`
   - `DELETE /admin/permissions/{permission_id}`

- Audit logs (`admin.audit_logs.read`)
   - `GET /admin/audit-logs`
   - Query params (all optional): `entity_type`, `entity_id`, `action`, `actor_user_id`, `request_id`, `created_from`, `created_to`, `limit`, `offset`

- Jobs (`admin.jobs.leave_credit`)
   - `POST /admin/jobs/leave-credit`
      - Body: `{ "year": 2026, "month": 2, "policy_id": null, "leave_type_id": null }`
   - `POST /admin/jobs/leave-credit/current-month`

### Core (`/core`) — all endpoints require permissions

- Organizations (`core.organizations.read` / `core.organizations.write`)
   - `GET /core/organizations`
   - `POST /core/organizations`
   - `GET /core/organizations/{org_id}`
   - `PUT /core/organizations/{org_id}`
   - `DELETE /core/organizations/{org_id}`

- Sites (`core.sites.read` / `core.sites.write`)
   - `GET /core/sites`
   - `POST /core/sites`
   - `GET /core/sites/{site_id}`
   - `PUT /core/sites/{site_id}`
   - `DELETE /core/sites/{site_id}`

- Projects (`core.projects.read` / `core.projects.write`)
   - `GET /core/projects`
   - `POST /core/projects`
   - `GET /core/projects/{project_id}`
   - `PUT /core/projects/{project_id}`
   - `DELETE /core/projects/{project_id}`

- Cost centers (`core.cost_centers.read` / `core.cost_centers.write`)
   - `GET /core/cost-centers`
   - `POST /core/cost-centers`
   - `GET /core/cost-centers/{cost_center_id}`
   - `PUT /core/cost-centers/{cost_center_id}`
   - `DELETE /core/cost-centers/{cost_center_id}`

### HR (`/hr`) — all endpoints require permissions

- Employees (`hr.employees.read` / `hr.employees.write`)
   - `GET /hr/employees`
   - `POST /hr/employees`
   - `GET /hr/employees/{employee_id}`
   - `PUT /hr/employees/{employee_id}`
   - `DELETE /hr/employees/{employee_id}`

- Attendance (`hr.attendance.read` / `hr.attendance.write`)
   - `GET /hr/attendance?project_id=123&employee_id=456&date_from=2026-01-01&date_to=2026-01-31`
   - `POST /hr/attendance`

- Employee documents (`hr.employee_documents.read` / `hr.employee_documents.write`)
   - `GET /hr/employees/{employee_id}/documents`
   - `POST /hr/employees/{employee_id}/documents`
   - `DELETE /hr/employees/{employee_id}/documents/{document_id}`

- Employee assets (`hr.employee_assets.read` / `hr.employee_assets.write`)
   - `GET /hr/employees/{employee_id}/assets`
   - `POST /hr/employees/{employee_id}/assets`
   - `PUT /hr/employees/{employee_id}/assets/{asset_id}`
   - `DELETE /hr/employees/{employee_id}/assets/{asset_id}`

- Leave types (`hr.leave_types.read` / `hr.leave_types.write`)
   - `GET /hr/leave-types`
   - `POST /hr/leave-types`
   - `PUT /hr/leave-types/{leave_type_id}`
   - `DELETE /hr/leave-types/{leave_type_id}`

- Leave policies (`hr.leave_policies.read` / `hr.leave_policies.write`)
   - `GET /hr/leave-policies`
   - `POST /hr/leave-policies`
   - `PUT /hr/leave-policies/{policy_id}`
   - `DELETE /hr/leave-policies/{policy_id}`

- Leave balances (`hr.leave_balances.read`)
   - `GET /hr/leave-balances/employees/{employee_id}`

- Leave requests
   - List (`hr.leave_requests.read`)
      - `GET /hr/leave-requests?status=applied&employee_id=123`
   - Apply (`hr.leave_requests.apply`)
      - `POST /hr/leave-requests/apply`
   - Approve (`hr.leave_requests.approve`)
      - `POST /hr/leave-requests/{request_id}/approve`
   - Reject (`hr.leave_requests.reject`)
      - `POST /hr/leave-requests/{request_id}/reject`
   - Cancel (`hr.leave_requests.cancel`)
      - `POST /hr/leave-requests/{request_id}/cancel`

- Holiday calendar (`hr.holiday_calendars.read` / `hr.holiday_calendars.write`)
   - `GET /hr/holidays?date_from=2026-02-01&date_to=2026-02-28`
   - `POST /hr/holidays`
   - `DELETE /hr/holidays/{holiday_id}`

### Inventory (`/inventory`) — all endpoints require permissions

- UOMs (`inventory.uoms.read` / `inventory.uoms.write`)
   - `GET /inventory/uoms`
   - `POST /inventory/uoms`
   - `PUT /inventory/uoms/{uom_id}`
   - `DELETE /inventory/uoms/{uom_id}`

- Warehouses (`inventory.warehouses.read` / `inventory.warehouses.write`)
   - `GET /inventory/warehouses`
   - `POST /inventory/warehouses`
   - `PUT /inventory/warehouses/{warehouse_id}`
   - `DELETE /inventory/warehouses/{warehouse_id}`

- Items (`inventory.items.read` / `inventory.items.write`)
   - `GET /inventory/items`
   - `POST /inventory/items`
   - `PUT /inventory/items/{item_id}`
   - `DELETE /inventory/items/{item_id}`

- GRNs (`inventory.grns.read` / `inventory.grns.write`)
   - `GET /inventory/grns`
   - `POST /inventory/grns`

- Material issues (`inventory.issues.read` / `inventory.issues.write`)
   - `GET /inventory/issues`
   - `POST /inventory/issues`

- Reports
   - Project-wise consumption (`inventory.reports.project_consumption.read`)
      - `GET /inventory/reports/project-consumption?date_from=2026-01-01&date_to=2026-01-31&project_id=123`

### Projects (`/projects`) — all endpoints require permissions

- DPR (Daily Progress Report)
   - Create/list (`projects.dprs.write` / `projects.dprs.read`)
      - `POST /projects/dprs`
      - `GET /projects/dprs?project_id=123&date_from=2026-01-01&date_to=2026-01-31&include_lines=true`
   - Metrics (`projects.dprs.metrics.read`)
      - `GET /projects/dprs/{dpr_id}/metrics`
      - `GET /projects/dprs/metrics?project_id=123&date_from=2026-01-01&date_to=2026-01-31`

- Finance (manual postings)
   - Direct expenses (`projects.finance.read` / `projects.finance.write`)
      - `GET /projects/{project_id}/direct-expenses?date_from=2026-01-01&date_to=2026-01-31`
      - `POST /projects/{project_id}/direct-expenses`
   - Revenues (`projects.finance.read` / `projects.finance.write`)
      - `GET /projects/{project_id}/revenues?date_from=2026-01-01&date_to=2026-01-31`
      - `POST /projects/{project_id}/revenues`

- Profitability (`projects.profitability.read`)
   - `GET /projects/{project_id}/profitability?date_from=2026-01-01&date_to=2026-01-31`

### Request IDs

Every response includes `X-Request-Id`. You can pass your own `X-Request-Id` header and it will be echoed back.

Audit logs captured during API calls include this request id, so you can correlate an API call to its audit rows.

## Curl examples

Login (store refresh cookie + extract access token):

```bash
curl -s -c cookies.txt \
   -H 'Content-Type: application/json' \
   -d '{"email":"admin@example.com","password":"..."}' \
   http://localhost:8000/api/v1/auth/login | tee /tmp/login.json

ACCESS_TOKEN=$(python3 -c 'import json; print(json.load(open("/tmp/login.json"))["access_token"])')

# If your system uses `python` instead of `python3`, use:
# ACCESS_TOKEN=$(python -c 'import json; print(json.load(open("/tmp/login.json"))["access_token"])')
```

Call a protected endpoint:

```bash
curl -H "Authorization: Bearer $ACCESS_TOKEN" \
   http://localhost:8000/api/v1/admin/users
```

Refresh access token (uses cookie):

```bash
curl -s -b cookies.txt -c cookies.txt \
   -X POST http://localhost:8000/api/v1/auth/refresh
```

Query audit logs by request id:

```bash
curl -H "Authorization: Bearer $ACCESS_TOKEN" \
   "http://localhost:8000/api/v1/admin/audit-logs?request_id=<X-Request-Id>"
```

Create an employee:

```bash
curl -H "Authorization: Bearer $ACCESS_TOKEN" \
    -H 'Content-Type: application/json' \
    -d '{"employee_code":"EMP-001","first_name":"Alex","employment_type":"full_time","employment_status":"active","joining_date":"2026-01-01"}' \
    http://localhost:8000/api/v1/hr/employees

```

Post attendance (labor cost input):

```bash
curl -H "Authorization: Bearer $ACCESS_TOKEN" \
   -H 'Content-Type: application/json' \
   -d '{"employee_id":1,"project_id":123,"work_date":"2026-01-06","hours":8,"hourly_rate":100,"notes":null}' \
   http://localhost:8000/api/v1/hr/attendance
```

Post a project revenue:

```bash
curl -H "Authorization: Bearer $ACCESS_TOKEN" \
   -H 'Content-Type: application/json' \
   -d '{"revenue_date":"2026-01-07","category":"Contract","description":null,"amount":10000,"client":null,"reference_no":null,"notes":null}' \
   http://localhost:8000/api/v1/projects/123/revenues
```

Post a direct expense:

```bash
curl -H "Authorization: Bearer $ACCESS_TOKEN" \
   -H 'Content-Type: application/json' \
   -d '{"expense_date":"2026-01-06","category":"Fuel","description":null,"amount":200,"vendor":null,"reference_no":null,"notes":null}' \
   http://localhost:8000/api/v1/projects/123/direct-expenses
```

Fetch profitability rollup:

```bash
curl -H "Authorization: Bearer $ACCESS_TOKEN" \
   "http://localhost:8000/api/v1/projects/123/profitability?date_from=2026-01-01&date_to=2026-01-31"
```
```

## Linting / formatting

### Backend

- `cd backend`
- `python -m pip install -r requirements-dev.txt`
- `ruff check .`
- `ruff format .`
- `pytest`

Integration DB tests (requires MariaDB running):

- The integration suite will automatically run `alembic upgrade head` against your configured database.

Example:

```bash
cd backend
RUN_DB_TESTS=1 \
   DB_HOST=localhost DB_PORT=3306 DB_NAME=unitederp DB_USER=unitederp DB_PASSWORD=unitederp \
   DATABASE_URL='mysql+pymysql://unitederp:unitederp@localhost:3306/unitederp' \
   pytest
```

### Frontend

- `cd frontend`
- `npm run lint`
- `npm run format`
