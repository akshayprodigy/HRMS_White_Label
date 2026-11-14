# Roadmap v2 — Phase 4 (Biometric Integration) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Attendance from ZKTeco / eSSL (and compatible) biometric devices via the ADMS "iClock" push protocol, plus a CSV/Excel import for any other vendor. All taps flow into the existing attendance pipeline (shift resolver, late marks, OT, comp-off), and HR can see device health.

**Architecture:**
- **Raw first:** every tap, from a device or an import, is stored as an immutable `BiometricPunch` row (idempotent by a dedupe key). A separate *apply* step folds raw taps into `Attendance` with the **first-in / last-out** rule per employee per resolved work day. It reuses `services/punch.py` (`_attribute_punch`, `record_punch_in`, and a punch-out finaliser extracted from `record_punch_out`), so overnight shifts, comp-off and audit behave exactly as for app punches.
- **Device trust:** unknown serials are auto-registered as `pending`. Their taps are stored but not applied until HR approves the device, then they are back-filled. An optional per-device IP allow-list adds protection. A `disabled` device's traffic is acknowledged and dropped.
- **Merged sources:** device and app punches share the same `Attendance` row for a work day: earliest in, latest out. HR-edited rows (`edited_by_id` set) are never overwritten. Raw taps for a payroll-locked day are kept as `locked`.
- **Protocol surface:** `/iclock/cdata`, `/iclock/getrequest`, `/iclock/devicecmd` mounted at the app root (not under `/api/v1`), plain-text responses, no auth beyond the serial lookup.

**Tech Stack:** FastAPI + async SQLAlchemy + MariaDB + Alembic; pandas/openpyxl (already in requirements) for import; React + shadcn/ui frontend.

Branch: `feature/roadmap-v2-phase4`, stacked on `feature/roadmap-v2-phase3`. Migration head at start: `e5b9c3d7a1f4` (verify with `alembic heads`).

**Product decisions (user-approved 2026-11-14):**
1. **Pairing:** first-in / last-out per employee per resolved work day (overnight-aware). Breaks are ignored. Taps within `biometric.dedupe_seconds` (default 120) of the punch-in are duplicates and never become a punch-out.
2. **Unknown devices:** pending until HR approves. On approval, all held taps are applied.
3. **Mixed sources:** device + app punches merge into the same row (earliest in / latest out). `Attendance.mode` keeps whatever created the row; each raw tap records its source.

**Time handling:** ADMS sends device-local wall-clock time with no zone. Each device has `utc_offset_minutes`; new devices get it from the time rule `biometric.default_utc_offset_minutes` (default `330`, IST). Stored `punch_time` is a true UTC instant, the same as app punches. The import takes an explicit offset (default the same rule).

## Environment (all tasks)

- Backend environment, tests, migrations and commit rules: read "Environment (all tasks)" in `docs/superpowers/plans/2026-11-12-roadmap-v2-phase1b.md`.
  - Containers, and pytest on the real dev DB with clean teardown (fixture pattern from `backend/tests/test_roster_publish.py`; teardown leaves zero rows).
  - Linear migrations, verified up/down/up.
  - Commit trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`; never push.
- Run tests with `docker exec erp-united-exploration-dev-backend-1 python -m pytest tests/<file> -q -p no:cacheprovider`.
- The full suite excludes the known-broken `tests/test_admin_auth.py` and `tests/test_leave_flows.py`. Its only known failures are the 2 in `test_hr_employees.py`.
- Locking helpers live in `backend/app/api/v1/endpoints/roster_common.py`: `lock_row`, `lock_row_retry`, `commit_or_409`, `retry_on_lock`, `lock_user_rows`.
- Payroll lock: `app/services/attendance_lock.assert_attendance_editable(db, work_date, fresh=True)` raises HTTPException 409 when the day is locked. See how `endpoints/attendance_offline.py` (~line 232) maps that to `payroll_locked`.
- Time rules live in `app/services/time_rules.py`: a `DEFAULTS` dict (key → (default, description)) plus validation in the update function (see `attendance.offline_max_hours` ~line 65 / 193). The web Time Rules tab is `frontend/src/components/workforce/time-rules-tab.tsx`.
- Permission seeding follows `backend/alembic/versions/d8e9f0a1b2c3_grant_attendance_edit.py`.
- Notifications: use `roster_svc.notify_many(db, rows)` (`app/services/roster.py` ~959), which is best-effort.
- Scheduler jobs: `register_job(JobSpec(...))` in `app/services/scheduler.py`. Job functions must `session.commit()` themselves. See `_job_roster_no_show_alerts` for the pattern.
- Employee code is `Employee.employee_id` (string), in `app/models/employee.py:28`.
- Frontend rules (no Tailwind build, check every class against index.css, state-driven nav via `App.tsx` + `sidebar.tsx` + `endpoints.ts`, tsc baseline **164**): see the Phase 1B environment section. Class checker: write a tiny script that greps each class selector in `frontend/src/index.css`. The old `twcheck.py` scratch file is gone.

## File map

| Path | Responsibility |
|---|---|
| `backend/app/models/biometric.py` | `BiometricDevice`, `BiometricDeviceUser`, `BiometricUserMap`, `BiometricPunch` |
| `backend/alembic/versions/f1a2b3c4d5e6_biometric.py` | tables + `biometric manage` perm → HR, Super Admin (pick an unused 12-hex id) |
| `backend/app/services/adms_protocol.py` | pure parsing/formatting of iClock requests/responses (no DB) |
| `backend/app/services/biometric.py` | device lookup/registration, user resolution, store raw taps, **apply** (first-in/last-out), back-fill |
| `backend/app/services/punch.py` | extract `finalize_punch_out(...)` from `record_punch_out` (no behaviour change) |
| `backend/app/api/v1/endpoints/iclock.py` | `/iclock/*` device endpoints (mounted at app root) |
| `backend/app/api/v1/endpoints/biometric.py` | HR API under `/api/v1/biometric` (devices, device users, mappings, punches, reprocess, import) |
| `backend/app/services/biometric_import.py` | CSV/XLSX parse + validate + preview/commit |
| `backend/app/services/scheduler.py` | `biometric_device_offline_alerts` job |
| `backend/scripts/adms_simulator.py` | CLI that emulates a device (handshake, ATTLOG/OPERLOG push, heartbeats) for QA |
| `frontend/nginx.conf`, `frontend/nginx.local.conf`, `frontend/vite.config.ts` | proxy `/iclock` to backend |
| `frontend/src/components/biometric/*` | Biometric Devices page (devices, mapping, punch log, import) |

---

### Task 1: Models, migration, permission

**Files:**
- Create: `backend/app/models/biometric.py`
- Create: `backend/alembic/versions/<new>_biometric.py`
- Modify: `backend/app/models/__init__.py` (register models, the same way `location.py` models are registered)
- Test: `backend/tests/test_biometric_models.py`

Models (all timestamps tz-aware UTC, following `app/models/location.py` style):

```python
class BiometricDeviceStatus:
    PENDING = "pending"; ACTIVE = "active"; DISABLED = "disabled"

class BiometricDevice(Base):
    __tablename__ = "biometric_device"
    id: int PK
    serial: str(64) unique, not null           # ADMS SN
    name: str(120) nullable                    # HR label
    status: str(16) default "pending", index
    utc_offset_minutes: int not null           # device clock = UTC + offset
    ip_allowlist: str(500) nullable            # comma-separated IPs/CIDRs; empty = any
    location_note: str(200) nullable
    last_seen_at: datetime nullable, index
    last_ip: str(64) nullable
    firmware: str(120) nullable                # from handshake/INFO if sent
    attlog_stamp: str(32) nullable             # last ATTLOG Stamp the device reported
    operlog_stamp: str(32) nullable
    offline_alerted_at: datetime nullable
    approved_by_id: FK user nullable; approved_at: datetime nullable
    created_at: datetime server_default now

class BiometricDeviceUser(Base):              # users enrolled on a device (from OPERLOG "USER" lines)
    __tablename__ = "biometric_device_user"
    id PK; device_id FK biometric_device ON DELETE CASCADE
    pin: str(32) not null; name: str(120) nullable; updated_at
    UniqueConstraint(device_id, pin)

class BiometricUserMap(Base):                 # device PIN -> employee user
    __tablename__ = "biometric_user_map"
    id PK
    device_id: FK nullable ON DELETE CASCADE   # NULL = applies to every device
    pin: str(32) not null
    user_id: FK user ON DELETE CASCADE, index
    created_by_id FK user nullable; created_at
    UniqueConstraint(device_id, pin)           # MariaDB treats NULLs as distinct -> enforce
                                               # "one global row per pin" in the service + a
                                               # generated column `device_key = COALESCE(device_id,0)`
                                               # with UniqueConstraint(device_key, pin)

class BiometricPunchState:
    PENDING_DEVICE = "pending_device"; UNMAPPED = "unmapped"; APPLIED = "applied"
    DUPLICATE = "duplicate"; LOCKED = "locked"; EDITED = "edited"; ERROR = "error"; IGNORED = "ignored"

class BiometricPunch(Base):
    __tablename__ = "biometric_punch"
    id PK
    dedupe_key: str(64) unique not null        # sha256 hex of f"{source_key}|{pin}|{punch_time.isoformat()}"
    source: str(16) not null                   # "adms" | "import"
    device_id: FK nullable ON DELETE SET NULL, index
    import_batch: str(36) nullable, index      # uuid4 per import commit
    pin: str(32) not null, index
    punch_time: datetime not null, index       # true UTC instant
    device_status: str(8) nullable             # raw in/out key from device (kept for audit only)
    verify_type: str(8) nullable
    raw: str(500) nullable                     # original line (truncated)
    user_id: FK user nullable, index
    state: str(16) not null, index
    attendance_id: FK attendance nullable ON DELETE SET NULL
    error: str(255) nullable
    created_at; applied_at nullable
    Index(user_id, punch_time)
```

Migration: create the 4 tables. Seed permission `biometric manage` (module `attendance`, follow `d8e9f0a1b2c3_grant_attendance_edit.py` for the permission and role-grant SQL) to roles HR and Super Admin. Downgrade drops the tables and the permission rows. Use the generated column via `sa.Computed("COALESCE(device_id, 0)")` for `device_key`.

- [ ] **Step 1:** Write `tests/test_biometric_models.py`:
  - insert a device, a global map and a device-specific map for the same pin, and assert both exist;
  - assert a second global map for the same pin raises `IntegrityError`;
  - assert a duplicate `dedupe_key` raises `IntegrityError`;
  - clean up in `finally`.
- [ ] **Step 2:** Run it and confirm it fails (the tables don't exist yet).
- [ ] **Step 3:** Write the models, register them, and write the migration (`down_revision` = current head). Then run `alembic upgrade head`.
- [ ] **Step 4:** Run the tests until they PASS. Then run `alembic downgrade -1 && alembic upgrade head` and confirm it is clean.
- [ ] **Step 5:** Commit `feat(biometric): device, mapping and raw punch models`.

### Task 2: ADMS protocol (pure)

**Files:**
- Create: `backend/app/services/adms_protocol.py`
- Test: `backend/tests/test_adms_protocol.py`

The iClock / ADMS push protocol (ZKTeco "PUSH SDK", used by eSSL too) works like this:
- **Handshake:** `GET /iclock/cdata?SN=<sn>&options=all[&pushver=..&language=..]`. The response is text/plain options (below).
- **Data upload:** `POST /iclock/cdata?SN=<sn>&table=<TABLE>&Stamp=<n>`. The body is newline-separated records. The response is `OK: <n>` (the number of records accepted).
  - `ATTLOG` lines are tab-separated: `PIN \t YYYY-MM-DD HH:MM:SS \t status \t verify \t workcode \t reserved...`. There are usually 2–7+ fields, and trailing fields may be missing.
  - `OPERLOG` lines start with a tag. `USER PIN=12\tName=Ravi\tPri=0\tPasswd=\tCard=\tGrp=1` is an enrolled user. `OPLOG ...` and `FP PIN=...` are operator events and fingerprint templates, which we ignore (never store biometric templates).
  - Other tables (`ATTPHOTO`, `BIODATA`, ...) are acknowledged and ignored.
- **Heartbeat / command poll:** `GET /iclock/getrequest?SN=<sn>`. Respond `OK` (we send no commands).
- **Command results:** `POST /iclock/devicecmd?SN=<sn>`. Respond `OK`.

```python
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

@dataclass(frozen=True)
class AttLog:
    pin: str
    local_time: datetime          # naive, device wall clock
    status: str | None
    verify: str | None
    raw: str

@dataclass(frozen=True)
class DeviceUser:
    pin: str
    name: str | None

MAX_LINES = 5000                   # per request; extra lines are ignored (device resends)

def parse_attlog(body: str) -> tuple[list[AttLog], list[str]]:
    """Returns (records, errors). Skips blank lines. PIN must be 1-32 chars of
    [A-Za-z0-9_-]; time must parse as '%Y-%m-%d %H:%M:%S'. Bad lines go to
    errors (as 'line N: reason'), never raise."""

def parse_operlog_users(body: str) -> list[DeviceUser]:
    """Only lines starting with 'USER '. key=value pairs split on TAB;
    PIN required (same validation); Name optional, stripped, max 120."""

def to_utc(local: datetime, utc_offset_minutes: int) -> datetime:
    return (local - timedelta(minutes=utc_offset_minutes)).replace(tzinfo=timezone.utc)

def handshake_response(sn: str, attlog_stamp: str | None, operlog_stamp: str | None,
                       utc_offset_minutes: int) -> str:
    """Text the device stores as its upload config. Exactly these lines, \n-joined, trailing \n:
    GET OPTION FROM: {sn}
    ATTLOGStamp={attlog_stamp or 'None'}
    OPERLOGStamp={operlog_stamp or 'None'}
    ATTPHOTOStamp=None
    ErrorDelay=30
    Delay=10
    TransTimes=00:00;14:05
    TransInterval=1
    TransFlag=TransData AttLog OpLog
    TimeZone={utc_offset_minutes/60 formatted without trailing .0, e.g. 5.5 or 8}
    Realtime=1
    Encrypt=None"""

def ok_count(n: int) -> str: return f"OK: {n}"
```

- [ ] **Step 1:** Write the tests:
  - a 3-line ATTLOG with a 7-field line, a 2-field line and a blank line gives 2 records;
  - a bad date line and a bad PIN (`"a b"`) go to errors;
  - more than `MAX_LINES` lines are truncated;
  - OPERLOG with USER, FP and OPLOG lines gives only the users, and a missing Name gives `None`;
  - `to_utc(2026-11-14 09:30, 330)` gives `04:00Z`;
  - the handshake text matches exactly, including `TimeZone=5.5` and `TimeZone=8`;
  - CRLF line endings are handled.
- [ ] **Step 2:** Run the tests and confirm they FAIL. **Step 3:** Implement. **Step 4:** Run until PASS.
- [ ] **Step 5:** Commit `feat(biometric): ADMS protocol parsing`.

### Task 3: Apply engine (first-in / last-out) + punch-out finaliser

**Files:**
- Modify: `backend/app/services/punch.py`. Extract the code that runs after the open record is found in `record_punch_out` (set `punch_out_time`, the punch-out geo fields when given, the comp-off accrual savepoint and the audit) into `async def finalize_punch_out(db, user, attendance, at, *, ip=None, lat=None, lng=None, accuracy=None, is_mock=False, selfie_name=None, liveness_passed=None, liveness_score=None, is_offline=False, client_uuid=None) -> Attendance`. `record_punch_out` calls it, so behaviour is identical (the existing punch tests must still pass unchanged).
- Create: `backend/app/services/biometric.py`
- Test: `backend/tests/test_biometric_apply.py`

```python
DEFAULT_DEDUPE_SECONDS = 120

async def resolve_user_id(db, device_id: int | None, pin: str) -> int | None:
    """Device-specific BiometricUserMap first, then the global (device_id NULL) one."""

async def store_taps(db, *, source: str, device: BiometricDevice | None, taps: list[tuple[str, datetime, str|None, str|None, str]],
                     import_batch: str | None = None) -> tuple[int, list[BiometricPunch]]:
    """taps = (pin, utc_time, status, verify, raw). Insert with INSERT IGNORE semantics on
    dedupe_key (source_key = device.serial or 'import'), so re-sent batches are no-ops.
    Initial state: PENDING_DEVICE if device and device.status != active, else UNMAPPED if no
    user resolves, else a transient state that apply_punch turns into its final state.
    Returns (number newly inserted, the new rows)."""

async def apply_punch(db, bp: BiometricPunch, *, dedupe_seconds: int) -> None:
    """Fold one raw tap into Attendance. Sets bp.state / attendance_id / applied_at / error.
       1. user = db.get(User, bp.user_id); inactive user -> IGNORED (error='inactive user').
       2. work_date = (await punch._attribute_punch(db, user.id, bp.punch_time))[0]
       3. assert_attendance_editable(db, work_date, fresh=True); a 409 -> LOCKED.
       4. row = Attendance for (user, work_date) FOR UPDATE (punch._fresh_one(..., fresh=True)).
       5. no row -> punch.record_punch_in(db, user, mode="biometric", captured_at=bp.punch_time,
          fresh=True, remarks=f"device {serial}" / "import") -> APPLIED.
          Biometric taps carry no GPS: pass geo_bypass=True (see below).
       6. row.edited_by_id is not None -> EDITED (never overwrite HR corrections).
       7. else merge:
            new_in  = min(row.captured_at, t)
            new_out = max(row.punch_out_time or row.captured_at, t)
            if t < row.captured_at: row.captured_at = t   (keep work_date; re-run attribution only if
                                     the work_date for t differs -> then treat t as a new row, i.e. step 5)
            if new_out - new_in < dedupe_seconds: DUPLICATE (nothing else changes)
            elif row.punch_out_time is None or new_out > row.punch_out_time:
                 await punch.finalize_punch_out(db, user, row, new_out) if row.punch_out_time is None
                 else just set row.punch_out_time = new_out (finalise already ran; re-run the comp-off
                 helper the same way finalize does so the accrual reflects the longer day) -> APPLIED
            else: DUPLICATE (absorbed inside [in, out])
    """

async def apply_pending(db, *, user_id: int | None = None, device_id: int | None = None,
                        pin: str | None = None, limit: int = 2000) -> dict[str, int]:
    """Back-fill: re-resolve user_id for UNMAPPED / PENDING_DEVICE rows matching the filter
    (only for active devices or import rows) and apply them in punch_time order, each in its own
    savepoint (a failure -> ERROR with message, never aborts the batch). Returns counts per state."""
```

Geo bypass: add a keyword `geo_bypass: bool = False` to `record_punch_in`. When it is true, skip the geofence evaluation and the selfie requirement. Only `services/biometric.py` passes it. The device is fixed hardware, and HR approves each device.

Order-independence is the key property: applying the same set of taps in any order must give the same `captured_at` / `punch_out_time`.

- [ ] **Step 1:** Write the tests. Use a real DB user with a day shift `09:00–18:00` (created via `ShiftTemplate` + `EmployeeShiftAssignment`, like `test_selfie_offline.py`), a night shift `22:00–06:00`, and far-future dates (2031):
  - taps `09:02, 09:03, 13:00, 18:05` give in `09:02` and out `18:05`, with state APPLIED for 3 and DUPLICATE for the `09:03` tap;
  - the same taps applied in reverse order give the same in/out;
  - night shift taps `22:01` (day D) and `06:04` (D+1) give one row with work_date D;
  - an existing app punch-in at `09:10` (via `record_punch_in` mode `"web"`) plus device taps `09:00` and `18:00` give in `09:00`, out `18:00`, with `mode` staying `"web"`;
  - a row with `edited_by_id` set gives EDITED and the row is unchanged;
  - with a locked payroll day (monkeypatch `assert_attendance_editable` to raise 409) the state is LOCKED;
  - an unmapped pin gives UNMAPPED; adding a map then calling `apply_pending(pin=...)` gives APPLIED;
  - a pending device's taps give PENDING_DEVICE; setting the device active then calling `apply_pending(device_id=...)` gives APPLIED;
  - `store_taps` twice with the same taps inserts 0 the second time;
  - a single tap gives in only (`punch_out_time` None);
  - existing `tests/test_selfie_offline.py` and the attendance tests still pass.
- [ ] **Step 2:** Run the tests and confirm they FAIL. **Step 3:** Implement (the `finalize_punch_out` extraction first, then run the existing punch tests, then `biometric.py`). **Step 4:** Run until PASS.
- [ ] **Step 5:** Commit `feat(biometric): apply engine (first-in/last-out) + punch-out finaliser`.

### Task 4: `/iclock` device endpoints + proxy + simulator

**Files:**
- Create: `backend/app/api/v1/endpoints/iclock.py` (an `APIRouter()` with no prefix; mount it in `app/main.py` / `create_app` at the root as `app.include_router(iclock.router, prefix="/iclock", include_in_schema=False)`. Find where the v1 router is included and add it next to it.)
- Modify: `frontend/nginx.conf`, `frontend/nginx.local.conf`: add a `location /iclock { ... }` block copied from the `/api` block (same `proxy_pass`, plus `client_max_body_size 2m`). Modify `frontend/vite.config.ts`: add an `/iclock` proxy entry like `/api`.
- Create: `backend/scripts/adms_simulator.py`
- Test: `backend/tests/test_iclock.py`

Behaviour:
- **Every request:** read `SN` from the query string. If it is missing or invalid (not 1-64 chars of `[A-Za-z0-9_-]`), return 400 text `ERROR`. Get the client IP from `request.client.host`. When the request came from a trusted proxy (`X-Forwarded-For` present and `request.client.host` is a private or loopback address), use the first `X-Forwarded-For` entry instead.
- **Device lookup** in `biometric.get_or_register_device(db, sn, ip)`:
  - Look up the device by serial.
  - If it is unknown, create it as `pending` with `utc_offset_minutes` taken from the time rule `biometric.default_utc_offset_minutes`, and notify users holding `biometric manage` (or HR) once ("New biometric device <SN> is waiting for approval").
  - Update `last_seen_at` and `last_ip`. If `offline_alerted_at` was set, clear it and notify "back online".
  - Concurrency: two first calls from the same serial racing must yield one device. Insert inside a savepoint, and on IntegrityError re-select.
- **IP allow-list:** if `ip_allowlist` is non-empty and the IP is not in any of its entries (use `ipaddress.ip_network(entry, strict=False)`), return 403 text `ERROR`, update nothing else, and log a warning.
- **Disabled device:** return `OK` for everything, store nothing, but still update `last_seen_at`.
- `GET /iclock/cdata` (handshake) returns `handshake_response(...)` as text/plain.
- `POST /iclock/cdata?table=ATTLOG&Stamp=n`:
  - Read the body. If it exceeds 1 MB, return 413.
  - Parse it with `parse_attlog`, then `store_taps` (with the UTC conversion using the device offset).
  - If the device is active, `apply_punch` each new row, each in its own savepoint.
  - Set `device.attlog_stamp = Stamp` when it is given.
  - Commit with `commit_or_409`; on a 409, retry once via `retry_on_lock`.
  - Respond `OK: <number of records parsed>`. Parsed records that were duplicates still count, so the device does not resend.
- `POST /iclock/cdata?table=OPERLOG`: upsert `BiometricDeviceUser` for each parsed user, set `operlog_stamp`, and respond `OK: <lines>`.
- Any other table: respond `OK: 0`.
- `GET /iclock/getrequest` returns `OK`. `POST /iclock/devicecmd` returns `OK`.
- All responses are `PlainTextResponse` with status 200, except the 400/403/413 cases.

Simulator (`python scripts/adms_simulator.py --base http://localhost:8005 --sn SIM001 [--pins 101,102] [--date 2031-01-06] [--offset 330]`) uses httpx to:
1. do the handshake and print the response;
2. POST an OPERLOG with USER lines for the pins;
3. POST an ATTLOG with an in and an out tap per pin, `09:0x` and `18:0x` local;
4. GET getrequest.

It prints each response. `--repeat` re-sends the same ATTLOG to show idempotency.

- [ ] **Step 1:** Write the tests (httpx `AsyncClient` with `ASGITransport` on `create_app()`, text bodies):
  - the handshake from an unknown SN creates a pending device and returns text containing `GET OPTION FROM: <sn>`;
  - an ATTLOG to the pending device returns `OK: 2` with rows in PENDING_DEVICE and no Attendance created;
  - approve the device (set active in the DB) and add a global map for the pin, then a new ATTLOG creates Attendance with mode `biometric`;
  - re-POSTing the same body returns `OK: 2` and adds no new rows;
  - the IP allow-list `10.0.0.0/8` with a test client from a different IP returns 403 (set `X-Forwarded-For` with a loopback client);
  - a disabled device returns `OK` and stores nothing;
  - a bad SN returns 400;
  - a body over 1 MB returns 413;
  - an OPERLOG upserts device users and an FP line stores nothing;
  - two concurrent handshakes for the same new SN create one device.
- [ ] **Step 2:** Run the tests and confirm they FAIL. **Step 3:** Implement. **Step 4:** Run until PASS. Then run the simulator against the live stack and paste its output into the report.
- [ ] **Step 5:** Commit `feat(biometric): ADMS iclock endpoints, proxy and device simulator`.

### Task 5: HR API — devices, device users, mappings, punch log, reprocess

**Files:**
- Create: `backend/app/api/v1/endpoints/biometric.py`. Mount it in `backend/app/api/v1/api.py` at prefix `/biometric`, tag `biometric`. It is **not** attendance-gated: HR may manage devices without punching in (same as tracking settings).
- Test: `backend/tests/test_biometric_api.py`

Auth: every route requires `biometric manage` (superusers pass). Copy the permission-dependency pattern used for `attendance edit` (grep `require_permission` / `has_permission` in endpoints).

Endpoints:
- `GET /biometric/devices` returns a list. Each entry has: id, serial, name, status, utc_offset_minutes, ip_allowlist, location_note, last_seen_at, last_ip, firmware, `health` computed as `online` (seen within `biometric.offline_minutes`), `offline`, `never` or `disabled`, `pending_punches` (count of PENDING_DEVICE), `unmapped_pins` (distinct count of UNMAPPED) and `enrolled_users` (count).
- `PATCH /biometric/devices/{id}`: name, utc_offset_minutes (-720..840), ip_allowlist (validate every entry with `ip_network`), location_note.
- `POST /biometric/devices/{id}/approve`: pending/disabled → active. Set `approved_by` / `approved_at`, run `apply_pending(device_id=id)`, audit, and return the counts.
- `POST /biometric/devices/{id}/disable`: → disabled, audit.
- `DELETE /biometric/devices/{id}`: allowed only when the device has no APPLIED punches (else 409). Use it to remove junk pending registrations.
- `GET /biometric/devices/{id}/users` lists enrolled device users with the current mapping and a `suggested_user_id`. The suggestion comes from an exact match of `Employee.employee_id == pin`, else a case-insensitive full-name match against active users. Only suggest when it is unique.
- `GET /biometric/mappings?device_id=&q=` lists mappings with user name and employee code.
- `PUT /biometric/mappings` takes `{device_id: int|null, pin, user_id}`. It upserts (409 if the pin is already mapped to a different user at the same scope, unless `replace: true`), then calls `apply_pending(pin=pin, device_id=device_id)` and returns the counts.
- `DELETE /biometric/mappings/{id}`. Already-applied attendance is not reverted; the docstring says so.
- `POST /biometric/mappings/auto` takes `{device_id}`. It creates device-specific mappings for every enrolled user whose suggestion is unique and that isn't mapped yet, then back-fills. Returns the created count and the counts.
- `GET /biometric/punches?state=&device_id=&pin=&user_id=&from=&to=&limit=&offset=` returns the paged raw log, newest first, with device serial and user name.
- `POST /biometric/punches/reprocess` takes `{state: "error"|"unmapped"|"locked", device_id?}`. It re-runs `apply_pending` for those states (LOCKED rows are re-tried here, for when payroll was unlocked).
- Every write is audited via `AuditLog` (action `BIOMETRIC_*`).

- [ ] **Step 1:** Write the tests:
  - employee and pm get 403 on every route; HR gets 200;
  - approve back-fills the pending taps;
  - mapping upsert back-fills unmapped taps; a conflicting mapping returns 409, and `replace` works;
  - auto-map by employee code;
  - the health values (seed `last_seen_at` now / 2h ago / null);
  - an invalid ip_allowlist returns 422 or 400;
  - deleting a device with applied punches returns 409;
  - the punch log filters and paging work;
  - reprocess retries LOCKED once the monkeypatched lock is lifted;
  - teardown removes devices, maps, punches and attendance.
- [ ] **Step 2:** Run the tests and confirm they FAIL. **Step 3:** Implement. **Step 4:** Run until PASS.
- [ ] **Step 5:** Commit `feat(biometric): HR device, mapping and punch log API`.

### Task 6: CSV / Excel punch import

**Files:**
- Create: `backend/app/services/biometric_import.py`
- Modify: `backend/app/api/v1/endpoints/biometric.py`. Add `POST /biometric/import/preview` and `POST /biometric/import/commit` (multipart `file` plus form fields `utc_offset_minutes` (default from the rule) and `identify_by` = `employee_code` | `pin`).
- Test: `backend/tests/test_biometric_import.py`

Format:
- File types are `.csv` (UTF-8, BOM tolerated) and `.xlsx`. The maximum is 5 MB and 20,000 data rows.
- Headers are matched case-insensitively with spaces and underscores normalised. Accepted columns:
  - `employee_code` or `pin`: one is required, matching `identify_by`.
  - **Time:** either `timestamp`, or `date` + `time`.
  - `device_serial`: optional. It is informational, and must be a known device if given.
- Accepted timestamp formats: ISO 8601 (an offset, if present, wins over the form offset), `YYYY-MM-DD HH:MM[:SS]`, `DD-MM-YYYY HH:MM[:SS]`, `DD/MM/YYYY HH:MM[:SS]`, and Excel datetime cells.
- **Identity:** with `identify_by=employee_code`, the employee is resolved via `Employee.employee_id` directly, and the stored `pin` is the code itself. With `identify_by=pin`, the employee is resolved through `BiometricUserMap` (the global map, or the device map when `device_serial` is given).

`preview`:
- Parse, validate and resolve, but write nothing.
- Return `{rows, valid, invalid, unknown_people, duplicates_in_file, already_imported, date_range, errors: [{row, message}] (first 200), sample: first 20 normalised rows}`.

`commit`:
- Re-parse, which is stateless.
- Reject with 400 if `invalid > 0` and the form field `skip_invalid` is not `true`.
- Otherwise call `store_taps(source="import", import_batch=uuid4)` for valid rows and `apply_punch` each new row, each in its own savepoint. Taps for unknown people are stored as UNMAPPED.
- Return `{import_batch, inserted, by_state}`.
- Audit as `BIOMETRIC_IMPORT`.

- [ ] **Step 1:** Write the tests:
  - a CSV by employee code with mixed formats gives a preview with correct counts and a commit that creates attendance with first-in/last-out;
  - an XLSX built with openpyxl in the test with datetime cells works;
  - re-importing the same file gives `already_imported` equal to the row count and inserts 0;
  - bad rows are reported with row numbers, and committing without `skip_invalid` returns 400;
  - `identify_by=pin` with a global map works;
  - an unknown employee code / unmapped pin is counted in preview as `unknown_people` (not `invalid`), and commit stores it as UNMAPPED, so a later mapping back-fills it;
  - 20,001 rows returns 400 and a 5 MB+ file returns 413;
  - an ISO timestamp offset overrides the form offset;
  - the permission check works.
- [ ] **Step 2:** Run the tests and confirm they FAIL. **Step 3:** Implement. **Step 4:** Run until PASS.
- [ ] **Step 5:** Commit `feat(biometric): CSV/Excel punch import with preview`.

### Task 7: Device health job + time rules

**Files:**
- Modify: `backend/app/services/time_rules.py`. Add these rules, with validation in the update function, following `attendance.offline_max_hours`:
  - `biometric.offline_minutes` (default `"30"`, integer 5–1440): "A device is offline when it has not called in for this many minutes".
  - `biometric.default_utc_offset_minutes` (default `"330"`, integer -720..840): "Clock offset given to newly registered biometric devices".
  - `biometric.dedupe_seconds` (default `"120"`, integer 0–3600): "Taps this close to the first punch are treated as duplicates".

  Wire the dedupe and offset rules into Tasks 3–6 wherever a default constant was used.
- Modify: `backend/app/services/scheduler.py`. Add the job `biometric_device_offline_alerts`, every 10 minutes. For active devices with `last_seen_at` older than the threshold (or never seen, but created more than the threshold ago) and `offline_alerted_at IS NULL`, notify HR and `biometric manage` holders ("Biometric device <name/serial> offline since <time>") and set `offline_alerted_at`. The job commits itself. "Back online" is handled in Task 4.
- Modify: `frontend/src/components/workforce/time-rules-tab.tsx`. Add a "Biometric devices" card for the three rules, matching the existing cards (separate `Card`, same classes).
- Test: `backend/tests/test_biometric_health.py`

- [ ] **Step 1:** Write the tests:
  - the job alerts once for a stale device, not again on the next run, and again after the device comes back (`offline_alerted_at` cleared by a handshake) and goes stale again;
  - pending and disabled devices are never alerted;
  - rule validation rejects out-of-range values;
  - restore the rule values in teardown.
- [ ] **Step 2:** Run the tests and confirm they FAIL. **Step 3:** Implement. **Step 4:** Run until PASS. Then run it through `POST /api/v1/admin/jobs/biometric_device_offline_alerts/run-now`.
- [ ] **Step 5:** Commit `feat(biometric): device offline alerts and biometric time rules`.

### Task 8: Web UI — Biometric Devices page

**Files:**
- Create: `frontend/src/components/biometric/biometric-devices.tsx` (page shell with tabs), `devices-tab.tsx`, `mapping-tab.tsx`, `punch-log-tab.tsx`, `import-tab.tsx`, `biometric-utils.ts` (health badge, time formatting)
- Modify: `frontend/src/api/endpoints.ts` (`ENDPOINTS.BIOMETRIC`), `frontend/src/App.tsx` (case `biometric-devices` + title), `frontend/src/components/sidebar.tsx` (menu item under Attendance Control, visible to admins / HR with `biometric manage`, mirroring how Field Team is gated)

UI:
- **Devices tab:** a table with columns Name/Serial, Status, Health badge (online green, offline red, never grey, disabled muted), Last seen (relative + exact on hover), Last IP, Pending taps, Unmapped PINs and Enrolled users.
  - Row actions: Approve (pending/disabled; shows a toast with the back-fill counts), Disable (inline confirm, no `window.confirm`), Edit dialog (name, UTC offset as a select of common offsets plus custom minutes, IP allow-list, location note), and Delete (only for a device with no applied punches; show the API's 409 text).
  - Empty state explains how to point a device at the server: "Device menu → Comm → Cloud Server / ADMS: server address = this server's host, port 80/443, path /iclock". It shows the computed `window.location.host`.
- **Mapping tab:** a device selector with an "All devices (global)" option. For a device it lists enrolled device users (PIN, device name, mapped employee or suggestion), with a "Map" combobox (employee search via the existing employee list endpoint used elsewhere, e.g. in the tracking-settings employee search), an "Auto-map suggestions" button and Unmap. The global view lists mappings with an "Add mapping" form (PIN + employee).
- **Punch log tab:** filters (state, device, PIN or employee, date range) and a paged table (time in local display + device, PIN, employee, state badge, error). Also a "Reprocess" button for the error / unmapped / locked states.
- **Import tab:** a file input (csv/xlsx), identify-by select, UTC offset, and "Preview". It shows the summary counts plus the first errors and sample rows, then "Import" (with a "skip invalid rows" checkbox when invalid > 0). Show the result counts by state. A template download link is not possible in the artifact viewer, but it is fine in the app: generate the CSV via a Blob in the browser.
- Attendance source: where attendance rows list `mode` (grep `mode` in `frontend/src/components/attendance*`), show "Biometric" for `mode === 'biometric'`.

- [ ] **Step 1:** Build the components.
  - Type-check with tsc (baseline 164, no new errors, zero in touched files).
  - Run the class check against `index.css`.
  - Write a Playwright script in the scratchpad that logs in as hr, opens the page, and screenshots each tab, before and after seeding via the simulator (Task 4). Approve the device, map a PIN, verify the attendance row appears, and run an import preview + commit with a small CSV. Look at the screenshots.
- [ ] **Step 2:** Commit `feat(web): biometric devices, mapping, punch log and import`.

### Task 9: Phase verification (controller)

1. Backend full suite (only the 2 known `test_hr_employees` failures), migration chain up/down/up (dump the dev DB first and restore after), and web tsc ≤ 164.
2. An API E2E agent covering `/iclock/*` (simulator plus raw httpx: malformed bodies, huge bodies, unknown/disabled/pending devices, IP allow-list, resend idempotency, concurrent pushes from two devices for the same employee, overnight shift taps, payroll-locked day, HR-edited row) and `/api/v1/biometric/*` (auth matrix, mapping races, import edge cases). The agent hunts for any 5xx.
3. A browser QA agent on the Biometric Devices page, plus the Time Rules card and the attendance "Biometric" label.
4. Fix the findings and re-run. Then a final whole-branch review → fix → memory update.
5. A deployment note in `DEPLOYMENT.md`:
   - Production nginx must route `/iclock` to the backend.
   - Devices need plain HTTP on port 80, or HTTPS only on firmware that supports it.
   - The server address/port settings on ZKTeco/eSSL devices.
   - The first device call appears as pending until HR approves it.
