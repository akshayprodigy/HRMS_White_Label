# Deployment Guide - Hostinger KVM 4

This project is optimized for production deployment on a VPS like Hostinger KVM 4 (4 vCPU / 16GB RAM).

## Prerequisites
1. Ubuntu 22.04 or 24.04 (recommended)
2. Docker and Docker Compose installed
   ```bash
   curl -fsSL https://get.docker.com -o get-docker.sh
   sudo sh get-docker.sh
   ```

## Setup Instructions

### 1. Clone the repository
```bash
git clone <your-repo-url>
cd erp-united-exploration
```

### 2. Configure Environment Variables
Copy the production environment template and fill in the values.
```bash
cp backend/production.env.example .env
# Edit .env with your secrets
nano .env
```
**Required Variables:**
- `SECRET_KEY`: Generate a secure random string (e.g., `openssl rand -hex 32`)
- `DB_PASSWORD`: Secure password for MariaDB
- `BACKEND_CORS_ORIGINS`: List of allowed origins, e.g., `["https://erp.yourdomain.com"]`

### 3. Build and Start Production Stack
```bash
sudo docker compose -f docker-compose.prod.yml up -d --build
```
This command will:
1. Build the frontend into a static bundle served by Nginx.
2. Build the backend using Gunicorn with optimized worker counts for your CPU.
3. Automatically run database migrations via Alembic.
4. Start a MariaDB 11 instance.

### 4. Seed Initial Data
```bash
# Run one-time seeding for roles/permissions and initial users
sudo docker compose -f docker-compose.prod.yml exec -T -e PYTHONPATH=/app backend python scripts/seed_admin.py
sudo docker compose -f docker-compose.prod.yml exec -T -e PYTHONPATH=/app backend python scripts/create_admin.py
sudo docker compose -f docker-compose.prod.yml exec -T -e PYTHONPATH=/app backend python scripts/seed_hr_permissions.py
```

### 5. Verify Services
- API Health Check: `http://<your-ip>/api/v1/health`
- Frontend: `http://<your-ip>/`

## Production testing (recommended approach)

Running a full automated test suite directly against a live production database is risky because tests create/modify data (leads, estimates, projects, tasks, approvals). Instead:

1) Local “prod-like” validation (before pushing to VPS)
- Use the prod build (Nginx + Gunicorn) locally without needing real TLS certs:
  - Start: `docker compose -f docker-compose.prod.yml -f docker-compose.prod.local.yml up -d --build`
  - Frontend: `http://localhost:8088/`
  - API health: `http://localhost:8088/api/v1/health`

2) Staging validation (preferred for complete testing)
- Deploy the same `docker-compose.prod.yml` stack to a staging VPS/domain.
- Use staging DB.
- Run end-to-end smoke tests (see below) and any load testing.

3) Production validation (safe smoke checks only)
- Verify health endpoint and login.
- Verify key read-only screens load (projects list, tasks list, approvals inbox).

### Optional: run seeds + smoke tests during redeploy

The repo includes `deploy/hostinger_prod_redeploy.sh`.

- Safe default: it redeploys only.
- Enable system seeding (fresh production install; does NOT create demo users):
  - `RUN_SYSTEM_SEEDS=1 ./deploy/hostinger_prod_redeploy.sh`
- Enable demo provisioning (fresh install / staging only):
  - `RUN_SEEDS=1 ./deploy/hostinger_prod_redeploy.sh`
- Enable API smoke test run (staging only unless you accept test data in prod):
  - `RUN_SMOKE_TESTS=1 ./deploy/hostinger_prod_redeploy.sh`

- Enable production-safe read-only smoke tests (recommended for production):
  - `RUN_READONLY_SMOKE_TESTS=1 SMOKE_USERNAME='<email>' SMOKE_PASSWORD='<password>' ./deploy/hostinger_prod_redeploy.sh`

### Redeploy when VPS is not a git checkout

If the VPS folder does not contain `.git`, `deploy/hostinger_prod_redeploy.sh` will **not** be able to `git pull`.
In that case, sync code from your local machine to the VPS first (without overwriting production `.env`), then redeploy.

Recommended one-command workflow from your local machine:

```bash
chmod +x deploy/rsync_and_redeploy_prod.sh
REMOTE_HOST='root@<your-vps-ip>' REMOTE_DIR='/root/erp-united-exploration' ./deploy/rsync_and_redeploy_prod.sh
```

Fresh install tip (safe for production):

```bash
REMOTE_HOST='root@<your-vps-ip>' \
REMOTE_DIR='/root/erp-united-exploration' \
RUN_SYSTEM_SEEDS=1 \
RUN_READONLY_SMOKE_TESTS=1 \
SMOKE_USERNAME='<email>' SMOKE_PASSWORD='<password>' \
./deploy/rsync_and_redeploy_prod.sh
```

Notes:
- The sync step intentionally excludes `.env` so production secrets stay on the server.
- The redeploy step uses `docker compose -f docker-compose.prod.yml down` + `up -d --build`.

Smoke tests run `backend/happy_path_test.py` inside the backend container using:
- `SMOKE_BASE_URL` (default `http://backend:8000/api/v1`)
- `ERP_PASSWORD` (default `test@12345`, used by demo users)

Read-only smoke tests run `backend/readonly_smoke_test.py` and will:
- login
- ensure attendance is marked for that user (only write)
- call a small set of GET endpoints to confirm core flows are reachable

### 6. Troubleshooting
- **Redeploy after changes**: If you updated code and the server still shows old UI behavior, rebuild and restart the stack.
  ```bash
  chmod +x deploy/hostinger_prod_redeploy.sh
  ./deploy/hostinger_prod_redeploy.sh
  ```
  After redeploy, do a hard refresh in the browser (`Ctrl+Shift+R` / `Cmd+Shift+R`).

- **No visible scrollbars**: On macOS/iOS/Chrome, scrollbars can be hidden by OS settings even when scrolling works. Try scrolling (trackpad two-finger / mouse wheel) inside the modal content.

- **Port 80 Conflict**: If the host has an existing Nginx service, stop it before starting Docker.
  ```bash
  sudo systemctl stop nginx && sudo systemctl disable nginx
  ```
- **Migration Issues**: If database migrations fail due to existing tables, resolve the schema state in Alembic.
  ```bash
  # If you must inspect the DB, run the command inside the db container.
  sudo docker compose -f docker-compose.prod.yml exec db mariadb -u"${DB_USER}" -p"${DB_PASSWORD}" "${DB_NAME}" -e 'SHOW TABLES;'
  ```

### 7. SSL Certificate Renewal
Certbot is configured to renew certificates automatically. However, you need to reload Nginx after renewal to apply the new certificates.
Add this hook to your renewal config on the host:
```bash
echo 'renew_hook = docker exec erp-united-exploration-frontend-1 nginx -s reload' | sudo tee -a /etc/letsencrypt/cli.ini
```

### 8. Post-Deployment (Recommended)
- **SSL**: Set up Certbot (Let's Encrypt) to enable HTTPS.
- **Firewall**: Ensure only ports 80 and 443 are open (and 22 for SSH).
  ```bash
  sudo ufw allow 80/tcp
  sudo ufw allow 443/tcp
  sudo ufw enable
  ```

## Production Architecture
- **Web Server**: Gunicorn with Uvicorn workers (async/await support).
- **Process Management**: Docker restart policies ensure services come back up after crashes or reboots.
- **Reverse Proxy**: Nginx handles static file delivery and routes API requests to the backend.
  - Upload size: attendance selfies are up to 3 MB and leave attachments up to 10 MB; `client_max_body_size` (50m in `frontend/nginx.conf`) must stay at or above the largest of these on any proxy in front of the backend.
  - Selfie storage: `ATTENDANCE_SELFIE_DIR` (default `/app/uploads/attendance-selfies`) must be on a persistent volume; the daily `attendance_selfie_purge` job removes unattached uploads (48h) and selfies past `attendance.selfie_retention_days`.
- **Database**: MariaDB with persistent volume mapped to the host.
- **Security**: 
  - Attendance Gating: Policy-level check for workspace access.
  - RBAC: Role-based access control enforced at the API router level.
  - JWT: Secure token-based authentication.

## Biometric devices (ZKTeco / eSSL ADMS push)

Devices push attendance to `http(s)://<your-host>/iclock/cdata` using the ADMS ("iClock" / PUSH SDK) protocol. Nginx routes `/iclock` to the backend (`frontend/nginx.conf`).

- **Device settings** (on the device: *Comm → Cloud Server / ADMS*):
  - Set **Server address** to your public host name or IP and **Server port** to `80`, or to `443` only if the firmware supports HTTPS.
  - Turn the **domain name** option on if you use a host name.
  - No path setting is needed: devices always call `/iclock/...`.
- **Plain HTTP on port 80:** most ZKTeco / eSSL firmware cannot follow redirects or use HTTPS. `nginx.conf` therefore serves `/iclock` over plain HTTP on port 80, while every other path still redirects to HTTPS. Don't remove that location block.
- **Approval:** a device's first call registers it as **pending**. Its taps are stored but not applied until HR approves it under *Time & Attendance → Biometric Devices*. Approving back-fills the held taps.
  - Taps arrive as device PINs. Map them to employees on the **Mapping** tab; *Auto-map* matches PIN = employee code.
  - Set each device's **UTC offset** to the device clock. New devices default to the time rule `biometric.default_utc_offset_minutes` (330 = IST).
- **No password:** the protocol has no real authentication; a device is identified by its serial number only. Protections:
  - HR approval, and a per-device **IP allow-list**. For ACTIVE devices the allow-list is the main defence: with an empty list anyone who knows the serial can send forged punches. Set it to the office's public IP (the Devices tab warns on active devices without one).
  - Caps: 50 pending devices in total, 5 per source IP, 20,000 held taps per pending device.
  - `limit_req` in nginx, at 120 requests/minute per IP with `burst=60`, a 2 MiB body limit (`client_max_body_size 2m`) and a 30s `proxy_read_timeout` on `/iclock`. `frontend/nginx.local.conf` carries the same blocks.
  - Pending devices never approved are removed after 7 idle days (or 60 days in total) by the daily `biometric_pending_device_expiry` job.
- **Real client IP:** the allow-list relies on nginx overwriting `X-Forwarded-For` with `$remote_addr`.
  - Keep the backend port (8000) **unpublished** in production. `docker-compose.prod.yml` publishes only 80/443. A private-network peer that can reach the backend directly could otherwise claim any IP.
  - If you put another proxy or load balancer in front of nginx, configure `set_real_ip_from <proxy-ip>; real_ip_header X-Forwarded-For; real_ip_recursive on;` in nginx. Without it every device appears with the proxy's IP, and allow-lists and rate limits stop working per device.
- **Check "Last IP" after first connect:** once a device has connected, look at its **Last IP** on the Devices tab. If it shows a docker gateway or proxy IP instead of the office's public IP, the real client IP is being lost, and allow-lists and rate limits won't work per device (see the `set_real_ip_from` note above).
- **Time rules:** `biometric.dedupe_seconds` (taps from the same PIN closer than this are treated as duplicates) and `biometric.offline_minutes` (offline threshold, 5-1440, default 30) are set under time rules.
- **Offline alerts:** `biometric_device_offline_alerts` runs every 10 minutes and alerts HR once when an approved device has been silent for longer than `biometric.offline_minutes` (default 30). It needs `ENABLE_SCHEDULER=1`. The scheduler should run in only one process: with several Gunicorn workers, enable it on a single worker or container to avoid duplicate runs. Duplicates are harmless for these jobs but waste work.
- **Other vendors:** any device without ADMS push can export a CSV/XLSX file. HR imports it on the **Import** tab: preview first, then import. Re-importing the same file is safe. The import route allows uploads up to 6 MB (`/api/v1/biometric/import` in nginx).

## Asset management

The asset register, allocations, maintenance log, employee asset requests and warranty/AMC alerts live under *Administration → Asset Management*. Employees see their assets and raise requests under *Profile → My Assets*.

- **Rebuild the backend image.** The QR labels use `segno` (pure Python, added to `backend/requirements.txt`). An image built before this release will fail on `/assets/{id}/qr.svg`.
- **Migration `e5a7c9b1d3f2`** (run `alembic upgrade head` as usual):
  - Creates the `asset`, `asset_category`, `asset_maintenance` and `asset_request` tables, and links `employee_asset` (now the allocation history) to `asset`.
  - **Backfills** one register entry per existing `employee_asset` row and one category per distinct asset type, matching names case-insensitively. Allocated rows stay allocated, lost rows stay lost, and returned rows become *in stock*.
  - Seeds the **`asset manage`** permission and grants it to **HR** and **Super Admin**. Grant it to any other role (for example an IT role) that should run the register. Users without it can't see the allocate/return buttons on an employee's Assets tab.
  - MariaDB DDL is not transactional. If the upgrade fails partway, drop the four new tables and the new `employee_asset` columns (`asset_id`, `allocated_by_id`, `returned_condition`, `returned_to_id`) before retrying. **Take a backup first**, as for any release.
- **Asset request approvals:**
  - **Default:** without further setup, requests wait for anyone holding `asset manage` to approve or reject them on the **Requests** tab.
  - **Multi-step approval:** create an approval chain with entity type `asset_request` (*Approval Chains*). New requests then route through it, and approvers act from their approval queue.
  - **Attendance gate:** the approval-chain screens are attendance-gated, so a non-superuser approver must be punched in to act.
- **Expiry alerts:**
  - The daily `asset_expiry_alerts` job (03:30 UTC, i.e. 09:00 IST) notifies `asset manage` holders about warranties and AMCs expiring within `assets.expiry_alert_days` (time rule, default 30, range 1-365, on the *Assets* card under Time Rules).
  - Each expiry date is alerted once. Changing the date, for example after an AMC renewal, re-arms the alert.
  - Requires `ENABLE_SCHEDULER=1`, as for the other jobs.
- **Exit:** HR's *Final release* is blocked while the employee still holds an allocated asset. Return the asset, or mark it lost, first. Starting exit clearance adds a "Return assets: …" checklist item for the IT department.
- **Dates:** "today" is the org-local date from the `org.timezone` time rule (see *Attendance & time* below). Asset forms leave issue/return dates to the server unless HR changes them.
- **Phones:** the web app's mobile layout (screens under 768px) doesn't include My Assets or Asset Management yet. Use a desktop browser, or the white-label mobile app once its asset screens ship.

## Attendance & time (Phase 6A)

Org timezone, location-wise and optional holidays, on-duty / client-visit / WFH requests, and the Shift Coverage report.

### HARD go-live step: set the org timezone before you deploy

All "today", shift-window, late-mark and no-show logic now runs in one org timezone, the time rule **`org.timezone`** (*Time Rules*). The database stays UTC.

- **If the rule is absent, it defaults to `Asia/Kolkata`.** An existing install that ran on UTC therefore **changes behaviour the moment the new code starts**.
- **Before deploying**, insert the rule explicitly:
  - `UTC` keeps the old behaviour until HR is ready to switch;
  - the real zone (e.g. `Asia/Kolkata`) switches immediately.
- **Biometric devices in IST on an install you set to `UTC`:** if you set `org.timezone=UTC` and `biometric.default_utc_offset_minutes` was never set explicitly, **also set `biometric.default_utc_offset_minutes=330`**. A blank value now follows the org timezone (UTC, offset 0), whereas the previous default was 330 (IST). Without this, newly registered devices and imports would be read 5.5 hours off. Devices that already have an explicit `utc_offset_minutes` are unaffected.
- **What changes at cutover:**
  - Late / no-show flags recorded before the cutover were computed in UTC and are not rewritten.
  - **Do not re-run `late_mark.process_month` for months closed before the cutover.** It would re-interpret old punches in the new timezone.
  - Shift template times (e.g. 09:00-18:00) are read as org-local wall clock. On a UTC install that had templates entered as UTC times, review the templates when you switch.
  - Biometric devices with an explicit `utc_offset_minutes` keep it. Devices left blank follow `biometric.default_utc_offset_minutes`, and a blank value there now means "follow the org timezone".
- Changing `org.timezone` later shows a warning in *Time Rules*. The same rules apply: it re-interprets everything from then on, and closed months must not be re-processed.

### Migration `a6b8d0f2c4e7`

Creates the `optional_holiday_pick` and `work_location_request` tables. Run `alembic upgrade head` as usual, with a backup first.

### Holidays now follow the employee's location

- A holiday applies to employees whose location matches it (case and spacing ignored) or when its location is **All**.
- **HQ-only holidays now apply only to employees whose location is HQ.** Employees with a blank location fall back to the time rule **`holidays.default_location`** (default `HQ`).
- **Before go-live:** review holiday locations in *Holiday Management*. Its location list shows employee counts per location and warns when a holiday matches nobody.
- **Optional holidays:**
  - Employees pick them under *Leave → Holiday Calendar* or *Profile → My Holidays*, and on mobile under *More → Holidays*.
  - Limit per year: time rule **`holidays.optional_quota_per_year`** (default 2, range 0-20). Pending picks count toward the limit until decided.
  - **A pick is not taken until a person other than the requester approves it.**
  - **Who decides:** the employee's reporting manager. If there is no manager, HR (holders of `hr employee write`) and superusers are notified and decide. HR and superusers can always decide any pick. If the manager is inactive, it goes to HR instead.
  - **`leave approve` grants nothing beyond being a manager:** holders list and decide only their own direct reports. Read-only HR (`hr employee read`) can list but not decide. Admin assigns managers.
  - **Chains:** if an approval chain with entity type `optional_holiday` exists, picks route through it instead, and the requester is always excluded from every step. A chain that would approve automatically, finds no approver (including a step whose only approvers are the requester or inactive users) falls back to the manager / HR path above. The requester can never act on their own pick, directly or through the chain.
  - **Editing a holiday (HR):** when a holiday becomes mandatory, an approved pick is cancelled only if the mandatory holiday applies to that employee's location; otherwise it stays approved and an audit row is written. The edit is refused with 409 if such a pick falls in a payroll-locked month.

### CSV holiday import

*Holiday Management → Import CSV*, requires `hr employee write`.

```
name,date,location,is_optional
Diwali,2026-11-08,All,false
Onam,2026-08-26,Kochi,true
```

- Dates are `YYYY-MM-DD` with a year from 2000 to 2100. `is_optional` accepts `true/false/1/0/yes/no`.
- At most 1 MB and 1000 rows.
- Rows already in the calendar (same date, location and name, ignoring case and spacing) are skipped.
- Invalid rows are reported with their row number and the valid rows are still imported.

### On-duty / client-visit / WFH requests

- Employees file them under *My Shift → My Work Location Requests* on the web, and under *More → Work location* on mobile.
- **A request is not taken until a person approves it.** Routing is the same as for optional holidays, with chain entity type `work_location`: the reporting manager decides (no manager or inactive manager: HR with `hr employee write` and superusers, who can always decide); `leave approve` holders only decide their own direct reports; the chain path excludes the requester. On mobile, managers decide under *Approvals → Team requests*.
- While pending, a request changes nothing. Once approved:
  - the geofence is relaxed for that day (the punch is marked `approved_remote`, shown as **Remote** in *Flagged Review*);
  - without a punch the day counts as present, with no LOP and no no-show;
  - the muster roll shows `OD` / `WFH` (`OD/2`, `WFH/2` for half days, `P·OD` / `P·WFH` when the employee also punched).
- A request overlapping **approved** leave is refused, both when it is filed and when it is approved.
- Requests may be back-dated up to the time rule **`attendance.work_location_backdate_days`** (default 7, range 0-60), never into a payroll-locked month. Mock-location punches stay blocked even with an approved request.

### Shift Coverage report

*Reports → Shift Coverage* (permission `report attendance`, at most 62 days per run). It shows required vs scheduled vs attended headcount per shift per day.
- "Scheduled" counts **published** roster entries only. Orgs that never publish rosters will see 0 scheduled.
- HR, CEO and Admin see every department. Department heads **and deputies** see only the departments they head or deputise. Other users see no rows.
- Org-wide requirements (no department) are shown to those scoped viewers as org-wide headcounts (aggregates only, no names).

## Delegation of Powers (D1)

Several managers per employee, posts with holders, acting covers and a "who would act" check, under *Administration → Delegation of Powers*. **Live approvals are unchanged:** leave, expenses and every other request still route exactly as before. The new resolver is only used by the Check tab until the next release (D2).

### Before you upgrade: backup and stop the backend

- **Take a database backup**, then **stop the backend** (all workers) before `alembic upgrade head`, and start it again afterwards.
- The migration copies each user's `manager_id` into a reporting assignment. A manager edited in HR **while the migration runs** is missed by that copy, and the new code would later revert it to the old value.

### Migration `b7d9f1a3c5e8`

- Creates `manager_kind`, `manager_assignment`, `post`, `post_holder` and `acting_assignment`.
- Seeds three manager kinds: `reporting` (system), `functional` and `project`.
- Copies every `user.manager_id` (except a user who is their own manager) into one `reporting` assignment starting 2000-01-01 with the note "Copied from reporting manager".
- Adds the **`dop manage`** permission and grants it to **Super Admin**.
- **Half-failure:** MariaDB DDL is not transactional. If the upgrade fails partway, drop whichever of `acting_assignment`, `manager_assignment`, `post_holder`, `post`, `manager_kind` exist, and delete the `dop manage` permission and its `role_permissions` rows if they were inserted. `alembic_version` stays at `a6b8d0f2c4e7`. Then retry.
- **Downgrade drops the tables, so all assignment, post and acting history is lost.** `user.manager_id` keeps its current (mirrored) values.

### Access

- *Administration → Delegation of Powers* needs `dop manage`, which only Super Admin has. The sidebar entry is shown to Super Admin only; grant `dop manage` to another role for API access, not for the menu.

### `manager_id` is now a mirror

- `user.manager_id` follows the reporting assignments. **Do not edit it with SQL or scripts:** the next sync reverts it. Change managers in HR, in admin, or in the Managers tab.
- It is updated when a manager or assignment is edited, when an employee's department or location changes (a manager from a department or location assignment can appear or drop away), when a post's holder changes, and by the daily job.
- Every change not made by editing an assignment directly is audited as `dop.manager.sync` (reason, total, up to 200 changes).
- **Daily job `dop_manager_mirror`** (18:40 UTC) applies assignments and post holders that start or end that day. It needs **`ENABLE_SCHEDULER=1`** on one process. Without it, a dated assignment or holder change that starts or ends by date is not applied to `manager_id` until the next edit or a manual run from the scheduler screen; live approvals keep using the old manager until then. If the job fails, the run is recorded as failed in the scheduler screen.

### What HR will notice

- Setting a manager that would create a reporting loop, or naming an inactive person as manager, is refused (422). Existing loops from old data never block unrelated edits.
- Changing an employee's department or location may change their manager, or clear it, when a department or location assignment applies.
- An explicit "no manager" clears the manager, unless a department, location or company assignment applies; that manager then applies.
- **Deleting an employee, user or department is refused (409)** while they are the manager in a live or future assignment, hold a post, are in an acting cover, or (for a department) have live assignments or a head post. The message says what to reassign first. Ended history does not block.
- The employee bulk import's `Manager Email` column applies to new users only, as before.

### Not used yet

Acting covers, posts and the other manager kinds (`functional`, `project`) can be recorded now but no live approval reads them until D2. Out-of-office cover still works through the existing delegation screens.

## Resource Usage (Hostinger KVM 4)
- **CPU**: 4 vCPU allows ~9 Gunicorn workers. Each worker handles dozens of concurrent requests.
- **RAM**: 16 GB is extremely generous for this stack. MariaDB can be tuned for high performance with this headroom.
- **Disk**: 200 GB NVMe provides fast I/O for database operations.
