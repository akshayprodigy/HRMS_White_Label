# Local Docker Desktop Stack

Production-like local stack for end-to-end testing on Docker Desktop.
Independent of the real deploy: does **not** touch
`docker-compose.prod.yml`, `docker-compose.prod.local.yml`, or the
`rsync_and_redeploy_prod.sh` deploy path. Same MariaDB 11, same
backend + frontend Dockerfiles as production.

## Prerequisites

- Docker Desktop 4.x with Compose v2
- Free host ports **3406**, **4001**, **4180** (change in
  `docker-compose.local.yml` if any collide with your other stacks)

## Quick start

```bash
# One-time: create your local env file (gitignored)
cp .env.local.example .env.local

# Build + run (first run pulls MariaDB + builds two images: ~2-4 min)
docker compose -f docker-compose.local.yml up -d --build

# Seed local test data (idempotent, refuses to touch a non-local DB)
docker compose -f docker-compose.local.yml exec -T \
    -e ERP_LOCAL_SEED=1 -e PYTHONPATH=/app \
    backend python -m scripts.seed_local --yes-local

# Tear down
docker compose -f docker-compose.local.yml down

# Nuke everything including the DB volume
docker compose -f docker-compose.local.yml down -v
```

## What's running

| Service   | Host port | Container port | Notes                              |
|-----------|-----------|----------------|------------------------------------|
| db        | 3406      | 3306           | MariaDB 11, named volume           |
| backend   | 4001      | 8000           | gunicorn + uvicorn worker (`-w 1`) |
| frontend  | 4180      | 80             | nginx serving the Vite prod build  |
| migrate   | (init)    | —              | One-shot: `alembic upgrade head`   |

Open in your browser:

- **App:**    http://localhost:4180
- **API:**    http://localhost:4001/api/v1/health
- **Docs:**   http://localhost:4001/docs  (Swagger UI)
- **DB:**     `mysql -h 127.0.0.1 -P 3406 -u erp_user -perp_password erp_local`

## Default login

The seed creates one admin and three test employees.

| Email               | Password         | Role       |
|---------------------|------------------|------------|
| admin@example.com   | LocalAdmin!2026  | Super Admin |
| t1@example.com      | Local!2026       | Employee (Engineering) |
| t2@example.com      | Local!2026       | Employee (HR) |
| t3@example.com      | Local!2026       | Employee (Ops) |

Change either value in `.env.local` (`LOCAL_ADMIN_EMAIL`,
`LOCAL_ADMIN_PASSWORD`) before running the seed if you want different
credentials.

## Testing geo-punch on localhost

The mobile PWA punch flow uses `navigator.geolocation`. Browsers only
expose it in **secure contexts** — which locally means:

- `http://localhost:*` — treated as secure by every modern browser.
  **No TLS needed for local testing.** Geolocation, service workers,
  and PWA install prompts all work.
- Any other IP or hostname needs HTTPS to hit the same APIs.

The seed creates a fence **"HQ Kolkata Test"** at
`22.5726, 88.3639` with a 500 m radius. To simulate being inside it
from your laptop:

1. Open http://localhost:4180 and log in.
2. Chrome / Edge: DevTools → **⋮** (top-right of DevTools) → **More
   tools → Sensors** → **Location** → **Custom location** →
   `22.5726, 88.3639`.
3. Safari: Develop menu → **Location** → **Custom Location…**.
4. The Attendance screen should show *"Inside HQ Kolkata Test ✓"* and
   enable the Punch button.
5. Move the coordinates outside the radius (e.g. `22.60, 88.40`) to
   see the "outside — nearest office" state and the STRICT rejection
   from the backend when you tap Punch.

Note: the admin@example.com login has **no fence assigned**, so it can
punch from anywhere. Assign the test fence to a tester via HR → Geo
Assignments if you want to see STRICT rejection in action.

## Env & secrets

`.env.local` is gitignored (`.env.*` in the root `.gitignore`); only
`.env.local.example` is committed. Keep it that way.

Email/SMS provider defaults:

- `SMTP_HOST` and `MSG91_AUTH_KEY` are **unset** by default.
- The backend's `configure_providers_from_env()` sees them missing
  and installs `LogEmailProvider` + `LogSMSProvider`. **No real
  emails or SMS are ever sent locally.**
- Uncomment the SMTP/MSG91 blocks in `.env.local` only if you want to
  test real delivery.

## Migrations & alembic

- `alembic upgrade head` runs once in the dedicated `migrate` service
  before the backend starts serving — idempotent on re-up.
- Head after seeding: **`j7e8f9g0h1i2`** (Section M B4 — involuntary
  attrition flag; the notifications-delivery head `i6d7e8f9g0h1` is
  reached mid-chain).
- Confirm current revision:

  ```bash
  docker compose -f docker-compose.local.yml exec -T backend \
      python -m alembic current
  ```

## Scheduler (APScheduler)

**Wired in Section P.** `create_app()` now boots the APScheduler loop
on startup when `ENABLE_SCHEDULER=1` (set on the backend service in
`docker-compose.local.yml`). All six registered jobs (notification
sweep/send every minute, digest flush hourly, scheduled reports
hourly, due revisions daily, ESIC continuation monthly) run
autonomously in this stack. With the flag unset (the default), the
old behavior applies: jobs only run via the admin "Run now" button.

Two safeguards make the in-process loop safe:

1. **Single gunicorn worker (`-w 1`).** One worker means exactly one
   scheduler loop, not N. If you enable `ENABLE_SCHEDULER` in another
   deployment, keep the worker count at 1 (or move the scheduler to a
   dedicated process).
2. **The `is_running` row-lock on `ScheduledJob`.** A
   `SELECT ... FOR UPDATE` against MariaDB prevents any job from
   running twice concurrently — covering both cron fires and manual
   "Run now" triggers.

Verify it's live:

```bash
docker compose -f docker-compose.local.yml logs backend | grep "scheduler started"
# then after a minute, last_run_at fills in for the minutely jobs:
# GET /api/v1/admin/jobs → sweep_notifications_for_delivery.last_run_at != null
```

## Tail logs

```bash
# Everything
docker compose -f docker-compose.local.yml logs -f

# Just backend
docker compose -f docker-compose.local.yml logs -f backend

# Just migrations (shows alembic upgrade output)
docker compose -f docker-compose.local.yml logs migrate
```

## Verification results

The full acceptance sequence was run against a fresh volume:

- ✅ **db** healthy after ~10s
- ✅ **migrate** reached head `j7e8f9g0h1i2` (11 chained upgrades from
  the y6...g2 baseline)
- ✅ **backend** healthy at `/api/v1/health` (`{"status":"ok"}`)
- ✅ **frontend** serves at http://localhost:4180 (200 OK)
- ✅ **PWA manifest** served at `/manifest.webmanifest` (200 OK)
- ✅ **Login** with admin@example.com works
- ✅ **/auth/me** returns full profile
- ✅ **Punch in** at `22.5726, 88.3639` accepted
- ✅ **/reports/summary** returns compliance data:
  `{"attendance_compliance":[{"date":"2026-07-01","total_employees":4,"present_count":1,"compliance_percentage":25.0}], ...}`

## What was fixed to get here

Three pre-existing issues surfaced when the app was booted on a fresh
MariaDB. Each was fixed minimally:

1. **11 alembic migrations used Postgres-only `'{}'::json` /
   `'[]'::json` cast defaults on JSON columns.** MariaDB rejects the
   cast syntax. Fix: dropped the `server_default` — every affected
   ORM model already sets `default=dict` / `default=list` at the
   Python layer, so insert behavior is unchanged. Files touched:
   `d1y2z3a4b5c6_add_tax_form16_gratuity.py`,
   `e2z3a4b5c6d7_add_saved_report.py`,
   `f3a4b5c6d7e8_add_performance_management.py`,
   `g4b5c6d7e8f9_add_approval_chain_and_expense.py`,
   `i6d7e8f9g0h1_notification_delivery.py`.

2. **`Employee.user` relationship had ambiguous FK paths** (both
   `user_id` and `bank_verified_by_id` reference `user`). SQLAlchemy
   raised `AmbiguousForeignKeysError` the first time the mapper was
   configured. Fix: added `foreign_keys=[user_id]` to the
   relationship — that's the semantically-correct primary owning FK.
   One line in `backend/app/models/employee.py`.

3. **Login email `admin@localhost` / `admin@local.test` was rejected
   by pydantic's `EmailStr` validator** (`.test` is on the
   reserved-TLD block list). Fix: default local admin email is now
   `admin@example.com`, testers are `t1@example.com` etc.

None of these are logic/feature changes — they are DB-syntax,
mapping-clarification, and email-format fixes that a fresh install
on MariaDB 11 needs.

## Restarting after code changes

```bash
# App code changes → rebuild the backend image
docker compose -f docker-compose.local.yml build backend
docker compose -f docker-compose.local.yml up -d backend

# Frontend changes
docker compose -f docker-compose.local.yml build frontend
docker compose -f docker-compose.local.yml up -d frontend

# Migration added → rebuild migrate + backend, then restart
docker compose -f docker-compose.local.yml build migrate backend
docker compose -f docker-compose.local.yml up -d
```
