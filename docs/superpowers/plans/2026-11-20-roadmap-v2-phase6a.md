# Roadmap v2 — Phase 6A (Attendance & Time) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Read shift times in the org's timezone, give every module one holiday rule with employee-picked optional holidays, let employees work on-duty / client-visit / WFH with approval, and add a shift-coverage report.

**Architecture:** `services/org_time.py` is the single source of the org timezone. The DB stays UTC; only the shift wall-clock → UTC conversion and the "today" boundary change. `services/holidays.py` is the single holiday reader, used by punch, absence-LOP, live ops, tracking, OT and the muster. Two new request tables, `optional_holiday_pick` and `work_location_request`, both route through the F4 approval-chain engine and fall back to direct approval by the manager/HR. `services/work_location.py` answers "is this user approved remote on date d", for the punch geofence step and the absence/no-show/muster logic.

**Tech Stack:** FastAPI + async SQLAlchemy + MariaDB 11.8 + Alembic; Python `zoneinfo`; React + shadcn/ui (web); Expo SDK 58 / RN (mobile).

Spec: `docs/superpowers/specs/2026-11-20-roadmap-v2-phase6a-attendance-time-design.md` (read it first).
Branch: `feature/roadmap-v2-phase6` (off main = 971f12a). Migration head at start: `e5a7c9b1d3f2`; verify with `alembic heads`.

## Environment (all tasks)

- Same as Phase 5. Read "Environment (all tasks)" in `docs/superpowers/plans/2026-11-19-roadmap-v2-phase5.md` **and** in `docs/superpowers/plans/2026-11-12-roadmap-v2-phase1b.md`. Key points:
  - Tests: `docker exec erp-united-exploration-dev-backend-1 python -m pytest tests/<file> -q -p no:cacheprovider`, run against the real dev DB. Teardown must leave zero rows. Test users use `@test.com` emails.
  - Locking: `lock_row`, `lock_row_retry`, `commit_or_409` and `guard_conflicts` live in `backend/app/api/v1/endpoints/roster_common.py`. Every mutating route gets `@guard_conflicts`. With `from __future__ import annotations`, wrap the handler in an inner closure instead (see `asset_requests.py`).
  - Dev DB is MariaDB with RR + `innodb_snapshot_isolation=1`: a stale read followed by UPDATE raises 1020. Lock before reading rows you will change, or use `lock_row_retry`.
  - Do not downgrade past your own migration revision.
  - Commit with the trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Never push.
- Frontend: no Tailwind build, so check every class against `frontend/src/index.css`. tsc baseline is **164**: `docker exec erp-united-exploration-dev-frontend-1 sh -c 'cd /app && npx -y -p typescript@5.6.3 tsc --noEmit -p . 2>&1 | grep -c "error TS"'`.
- Mobile: `cd mobile && npm run check` (tsc + jest; baseline 445 tests green). Follow `mobile/src/features/leave/*` for the structure of a request feature.
- Approval chain engine (`backend/app/api/v1/endpoints/approval_chains.py`):
  - `instantiate_for_entity(..., commit=False)` (~687) raises 400 when no chain exists, so **check for an active chain first**; see how `asset_requests.py` does it.
  - Entity summaries are in `_entity_summary` (~848).
  - Finalisation branches are in the `if instance.entity_type == ...` ladder (~1125); add new branches next to `ASSET_REQUEST` (~1180).
  - Entity type constants are in `backend/app/models/approval_chain.py::ChainEntityType`.
- Time rules: `TIME_RULE_DEFAULTS` + validation in `backend/app/services/time_rules.py` (pattern: `attendance.offline_max_hours`, ~65/213). Web tab: `frontend/src/components/workforce/time-rules-tab.tsx`.

## Time rules added in this phase

| Key | Default | Validation |
|---|---|---|
| `org.timezone` | `Asia/Kolkata` | must be in `zoneinfo.available_timezones()` |
| `holidays.optional_quota_per_year` | `2` | int 0–20 |
| `attendance.work_location_backdate_days` | `7` | int 0–60 |

## File map

| Path | Responsibility |
|---|---|
| `backend/app/services/org_time.py` | org tz lookup + local date/now + `shift_window` (new) |
| `backend/app/api/v1/endpoints/meta.py` | public `GET /meta/org-time` (new) |
| `backend/tests/test_org_time.py`, `test_org_time_guard.py`, `org_time_allowlist.txt` | helpers, UTC parity, guard scan |
| `backend/app/services/holidays.py` | single holiday reader (new) |
| `backend/app/models/optional_holiday.py`, `backend/app/models/work_location.py` | new models |
| `backend/alembic/versions/a6b8d0f2c4e7_phase6a_holidays_work_location.py` | both tables |
| `backend/app/services/optional_holidays.py`, `backend/app/api/v1/endpoints/holidays.py` | picks service + `/holidays` API |
| `backend/app/services/work_location.py`, `backend/app/api/v1/endpoints/work_location.py` | requests service + `/work-location-requests` API |
| `backend/app/services/punch.py`, `absence_lop.py`, `live_ops.py`, `location_tracking.py`, `reports.py`, `endpoints/overtime.py` | callers migrated |
| `backend/app/services/report_catalog.py`, `reports.py` | `shift_coverage` report |
| `frontend/src/lib/org-time.ts`, `frontend/src/components/holidays/*`, `frontend/src/components/work-location/*` | web |
| `mobile/src/lib/org-time.ts`, `mobile/src/features/holidays/*`, `mobile/src/features/work-location/*` | mobile |

---

### Task 1: `org_time` service, time rule, meta endpoint

**Files:**
- Create: `backend/app/services/org_time.py`, `backend/app/api/v1/endpoints/meta.py`, `backend/tests/test_org_time.py`
- Modify: `backend/app/services/time_rules.py` (rule + validation), `backend/app/api/v1/api.py` (mount `/meta`), `frontend/src/components/workforce/time-rules-tab.tsx` (timezone field as a text input with a datalist of common zones)

- [ ] **Step 1: Write failing tests** in `backend/tests/test_org_time.py`:

```python
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo
from app.services.org_time import shift_window, local_date, local_today_for

IST = ZoneInfo("Asia/Kolkata")
LON = ZoneInfo("Europe/London")

def test_day_shift_ist():
    s, e = shift_window(date(2026, 11, 20), time(9, 0), time(18, 0), IST)
    assert s == datetime(2026, 11, 20, 3, 30, tzinfo=timezone.utc)
    assert e == datetime(2026, 11, 20, 12, 30, tzinfo=timezone.utc)

def test_cross_midnight_ist():
    s, e = shift_window(date(2026, 11, 20), time(22, 0), time(6, 0), IST)
    assert s == datetime(2026, 11, 20, 16, 30, tzinfo=timezone.utc)
    assert e == datetime(2026, 11, 21, 0, 30, tzinfo=timezone.utc)

def test_utc_parity():
    s, e = shift_window(date(2026, 11, 20), time(9, 0), time(18, 0), timezone.utc)
    assert (s, e) == (datetime(2026, 11, 20, 9, tzinfo=timezone.utc),
                      datetime(2026, 11, 20, 18, tzinfo=timezone.utc))

def test_dst_gap_moves_forward():
    # 2026-03-29 01:30 does not exist in London (clocks jump 01:00 -> 02:00)
    s, _ = shift_window(date(2026, 3, 29), time(1, 30), time(9, 0), LON)
    assert s == datetime(2026, 3, 29, 1, 0, tzinfo=timezone.utc)  # == 02:00 BST

def test_local_date_boundary():
    assert local_date(datetime(2026, 11, 20, 19, 0, tzinfo=timezone.utc), IST) == date(2026, 11, 21)
    assert local_date(datetime(2026, 11, 20, 19, 0), IST) == date(2026, 11, 21)  # naive == UTC

def test_local_today_for_now():
    now = datetime(2026, 11, 20, 20, 0, tzinfo=timezone.utc)
    assert local_today_for(IST, now=now) == date(2026, 11, 21)
```

Plus async tests:
- `org_tz(db)` returns `Asia/Kolkata` by default and `UTC` once the rule is set; restore the rule in teardown.
- Setting the rule to `Mars/Base` through the time-rules update path is rejected with 400/422.
- `GET /api/v1/meta/org-time` without auth returns `{"timezone", "utc_offset_minutes", "today"}`.

- [ ] **Step 2: Run** `pytest tests/test_org_time.py`. Expected: ImportError / FAIL.

- [ ] **Step 3: Implement** `backend/app/services/org_time.py`:

```python
"""Org timezone: the ONLY place shift wall-clock times and "today" are
interpreted. Storage stays UTC. org.timezone=UTC reproduces pre-6A behaviour."""
from __future__ import annotations
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from typing import Optional
from zoneinfo import ZoneInfo, available_timezones

DEFAULT_TZ = "Asia/Kolkata"
RULE_KEY = "org.timezone"

def tz_from_name(name: Optional[str]) -> tzinfo:
    name = (name or "").strip() or DEFAULT_TZ
    if name.upper() == "UTC":
        return timezone.utc
    if name not in available_timezones():
        return ZoneInfo(DEFAULT_TZ)
    return ZoneInfo(name)

async def org_tz(db, user=None) -> tzinfo:
    """`user` reserved for per-location timezones (later Platform slice)."""
    from app.services.time_rules import get_time_rules
    rules = await get_time_rules(db)
    return tz_from_name(rules.get(RULE_KEY, DEFAULT_TZ))

def _aware(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt

def local_date(dt: datetime, tz: tzinfo) -> date:
    return _aware(dt).astimezone(tz).date()

def local_now(tz: tzinfo, now: Optional[datetime] = None) -> datetime:
    return _aware(now or datetime.now(timezone.utc)).astimezone(tz)

def local_today_for(tz: tzinfo, now: Optional[datetime] = None) -> date:
    return local_now(tz, now).date()

async def local_today(db) -> date:
    return local_today_for(await org_tz(db))

def _to_utc(d: date, t: time, tz: tzinfo) -> datetime:
    local = datetime.combine(d, t).replace(tzinfo=tz, fold=0)
    # Nonexistent local time (DST gap): round-trip check, shift forward.
    back = local.astimezone(timezone.utc).astimezone(tz)
    if back.replace(tzinfo=None) != local.replace(tzinfo=None):
        local = (local + timedelta(hours=1)).replace(minute=0, second=0)
    return local.astimezone(timezone.utc)

def shift_window(work_date: date, start: time, end: time, tz: tzinfo) -> tuple[datetime, datetime]:
    s = _to_utc(work_date, start, tz)
    end_date = work_date + timedelta(days=1) if end <= start else work_date
    return s, _to_utc(end_date, end, tz)

def utc_offset_minutes(tz: tzinfo, now: Optional[datetime] = None) -> int:
    off = local_now(tz, now).utcoffset() or timedelta(0)
    return int(off.total_seconds() // 60)
```

(If `test_dst_gap_moves_forward` shows the round-trip trick differs on this Python version, fix `_to_utc` until the test passes. Keep the behaviour of shifting to the next valid wall time.)

`meta.py`: `router = APIRouter()`, then `GET /org-time` with no auth dependency, returning `{"timezone": name, "utc_offset_minutes": utc_offset_minutes(tz), "today": local_today_for(tz).isoformat()}`. Mount it in `api.py` with `prefix="/meta", tags=["meta"]`.

Time rule: add `"org.timezone": ("Asia/Kolkata", "IANA timezone used to read shift times and 'today' (UTC = legacy behaviour)")`, and validation that raises the same error type as `offline_max_hours` when the value isn't `UTC` and isn't in `available_timezones()`.

- [ ] **Step 4: Run tests.** Expected: PASS. Then run the web tsc check (must stay ≤164).
- [ ] **Step 5: Commit** `feat(time): org timezone service, rule and /meta/org-time`.

---

### Task 2: Shift windows and punch work-date use the org timezone

Convert every place that turns a shift `start_time`/`end_time` into a datetime, and the punch work-date resolver.

**Files (modify):**
- `backend/app/services/late_mark.py:53`
- `backend/app/services/reports.py:328,336`
- `backend/app/services/schedule_rules.py:49,51`
- `backend/app/api/v1/endpoints/calendar_feed.py:128-129` (emit UTC `...Z` stamps from `shift_window`)
- `backend/app/services/live_ops.py` (every shift start/end computation; `grep -n "start_time\|end_time" services/live_ops.py`)
- `backend/app/api/v1/endpoints/attendance_bulk.py:44,109` (bulk mark: the entered times and the day start are org-local)
- `backend/app/api/v1/endpoints/hr.py:2221` (HR-entered times are org-local)
- `backend/app/services/punch.py::_attribute_punch` (~211): compute `punch_date` with `local_date(punch_ts, tz)` and pass `tz=tz` to `resolve_work_date`
- `backend/app/services/biometric.py` (~562/658/763): when neither the device nor the rule `biometric.default_utc_offset_minutes` is explicitly set, use `utc_offset_minutes(await org_tz(db))`. Keep 330 as the final fallback.
- Leave alone: `biometric_import.py:274` (already offset-aware; check it), `roster_publish.py:408-410` (calendar-day bounds of `changed_at`; convert with the local-midnight → UTC rule `_to_utc(d, time(0), tz)`), `timesheets.py:694` (same treatment as roster_publish), `bd.py:1886` (BD module, out of scope — add it to the allow-list with a reason).
- Pure functions that currently take only dates/times gain a `tz` parameter. Callers obtain `tz = await org_tz(db)` once per request or job, not per row.

**Test:** `backend/tests/test_org_time_parity.py`
- With rule `org.timezone=UTC`: late-mark minutes for a 09:00 shift and a punch at 09:20Z are 20 (old behaviour). With `Asia/Kolkata`, a punch at 03:50Z gives 20 and a punch at 09:20Z gives 350.
- Punch attribution: with IST, a punch at 2026-11-20 20:00Z (01:30 IST on the 21st) with no shift gets work_date 2026-11-21; with UTC it gets 2026-11-20.
- Overnight shift 22:00–06:00 IST: a punch at 00:45Z on the 21st (06:15 IST) is attributed to work_date 20th.
- No-show: with IST and a 09:00 shift with `schedule.no_show_minutes=30`, the job at 04:10Z flags it and at 03:50Z does not. Call `no_show_job` with an injected `now` if it takes one; otherwise add an optional `now` parameter.

- [ ] Step 1: write the parity tests (they fail with IST because the code still uses UTC).
- [ ] Step 2: run, confirm FAIL.
- [ ] Step 3: convert each listed site.
- [ ] Step 4: run the parity tests plus `tests/test_late_mark*.py tests/test_live_ops*.py tests/test_punch*.py tests/test_schedule_rules*.py tests/test_calendar_feed*.py tests/test_attendance_bulk*.py tests/test_biometric*.py tests/test_reports*.py`.
  - Existing tests that hard-code UTC expectations: set `org.timezone=UTC` in their fixture (restore it on teardown) rather than rewriting their expected values.
  - Note each such fixture change in the commit message.
- [ ] Step 5: commit `fix(time): read shift times and punch dates in the org timezone`.

---

### Task 3: "Today" is org-local everywhere + guard test

**Files (modify)**, every hit of `date.today()` / `datetime.now(timezone.utc).date()` in business code (list taken on 2026-11-20; re-run the grep):

```
services: emergency_leave.py:44 assets.py:112,119,142,143,177,248 safety_profile.py:180
  approver_delegation.py:22 open_shifts.py:37 scheduler.py:277,390,584,855 roster.py:127,265,327
endpoints: statutory.py:154,889 asset_requests.py:66 tax.py:505,587,735,1252,1263,1329
  asset_maintenance.py:83,87,212 roster_on_call.py:42 attendance.py:256,377 payroll.py:98,479
  revisions.py:841 hr.py:495,861,3056,3807,3937,4376 reports.py:41,691 approval_chains.py:653
  roster_swaps.py:42 roster_publish.py:404 dashboard.py:77,332,353,405,460,554
  schedule_delegations.py:97 assets.py:166,337,417,454,518 timesheets.py:710,762,826,971,1038
  tracking.py:180,258 attendance_bulk.py:71 exit_management.py:159,245,361,483,732
  roster_autofill.py:80 roster.py:424,450
```

Rules:
- Async code with `db` in scope: `today = await local_today(db)`.
- Pure helpers that take `today` as an argument stay pure, and their caller passes `local_today`.
- Pydantic default factories (e.g. `default_factory=date.today`): drop the default and fill it in the endpoint from `local_today(db)`. The schema field becomes `Optional[date] = None`.
- Tax and statutory "financial year" calculations use `local_today` too, because the FY boundary is local.
- `datetime.now(timezone.utc)` used as an **instant** (timestamps, comparisons with stored UTC) is correct. Leave it.
- Also scan for SQL-side UTC day bucketing: `func.date(Attendance.captured_at)` / `func.time(...)`. The guard regex doesn't catch these, so add `func\.date\(|func\.time\(` to the guard over the attendance columns. Bucket by `work_date` or by local-day bounds.
- After converting, try removing the `org_tz_utc` pin (`backend/tests/_tz.py`) from `test_pay_linkage` and `test_shift_swaps`. They were pinned for UTC "today" assumptions; keep a pin only where a test genuinely asserts UTC behaviour.
- Assets frontend: `serverSafeToday()` in `frontend/src/components/assets/*` becomes `orgToday()` from Task 10. Do not change the frontend in this task.

**Create:**
- `backend/tests/test_org_time_guard.py`: walks `backend/app/services` and `backend/app/api`. Fails on any line matching `date\.today\(\)|\.now\([^)]*\)\.date\(\)|utcnow\(\)\.date\(\)`, or on `datetime\.combine\([^)]*(start_time|end_time)`, unless `path:line-fragment` appears in the allow-list.
- `backend/tests/org_time_allowlist.txt`: one entry per line, with a `# reason`. Keep the allow-list short: `org_time.py` itself, `bd.py` and anything else clearly not about attendance or HR.

- [ ] Step 1: write the guard test; run it and confirm it FAILS, listing the sites.
- [ ] Step 2: convert the sites file by file, running that file's tests after each file.
- [ ] Step 3: guard test PASSES. Run the full backend suite. Expected: green except the 2 known `test_hr_employees` failures. If date-relative tests flake around UTC midnight vs IST midnight, pin them to `org.timezone=UTC` in their fixture.
- [ ] Step 4: commit `fix(time): business 'today' uses the org timezone; guard test`.

---

### Task 4: Single holiday reader

**Create** `backend/app/services/holidays.py`:

```python
"""The ONLY reader of HolidayCalendar for attendance/pay decisions.
A holiday applies to a user when:
  * mandatory (is_optional False) and location is 'All' or equals the
    employee's location (case-insensitive, trimmed), or
  * optional and the user has an APPROVED OptionalHolidayPick for it
    (picks wired in Task 6; until then optional holidays never apply)."""
from dataclasses import dataclass
from datetime import date

@dataclass(frozen=True)
class HolidayInfo:
    holiday_id: int
    name: str
    is_optional: bool

def norm_loc(loc: str | None) -> str:
    return " ".join((loc or "").split()).casefold()

ALL = "all"

def applies(holiday_location: str | None, employee_location: str | None) -> bool:
    h = norm_loc(holiday_location)
    return h == ALL or (h != "" and h == norm_loc(employee_location))

async def holidays_for(db, user_ids, start: date, end: date) -> dict[int, dict[date, HolidayInfo]]:
    """One query for holidays in range, one for employee locations
    (Employee.user_id -> Employee.location), one for approved picks.
    Users with no Employee row get only 'All' holidays."""

async def is_holiday(db, user_id: int, d: date) -> HolidayInfo | None:
    return (await holidays_for(db, [user_id], d, d)).get(user_id, {}).get(d)
```

**Migrate callers:**
- `absence_lop.py`:
  - Replace `load_holidays` with `holidays_for`.
  - Change `is_non_working_day(eff, d, location, holidays, default_offs, ...)` to `is_non_working_day(eff, d, user_holidays: set[date] | dict, default_offs, ...)`, where the caller passes that user's dict and the function checks `d in user_holidays`.
  - Update `count_absent_days` the same way.
  - Keep `load_holidays` only if something outside these callers still uses it; otherwise delete it.
- `live_ops.py:212-231` and `location_tracking.py:119-130`: same change.
- `punch.py::_maybe_create_comp_off_accrual` (~263): `info = await is_holiday(db, user.id, work_date)`. Drop the `["All","HQ"]` filter.
- `endpoints/overtime.py:749`: build `holiday_dates` for the user from `holidays_for`.
- `reports.py` muster (`is_holiday` ~224/254/493): fill from `holidays_for`.
- Any remaining `select(HolidayCalendar)` outside `holidays.py` and the HR CRUD in `hr.py` must be migrated. Add a grep assertion to `test_holidays.py`.

**Test** `backend/tests/test_holidays.py` (real DB, clean teardown):
- Employees at "Mumbai", " mumbai " and "Pune".
- Holidays: All/mandatory, Mumbai/mandatory, Pune/mandatory, All/optional.
- Expect: Mumbai employees get All+Mumbai; Pune employees get All+Pune; nobody gets the optional one; a user with no Employee row gets All only; an HQ-only holiday no longer applies to non-HQ staff (a regression of the old punch behaviour, which is intended).
- `is_non_working_day` unit tests updated to the new signature.

- [ ] Steps: failing tests → implement → migrate callers → run `test_holidays.py`, `test_absence_lop*.py`, `test_live_ops*.py`, `test_location_tracking*.py`, `test_overtime*.py`, `test_reports*.py`, `test_punch*.py`, then the full suite.
- [ ] Commit `refactor(holidays): single location-aware holiday reader`.

---

### Task 5: Models + migration for picks and work-location requests

**Create** `backend/app/models/optional_holiday.py`:

```python
class PickStatus:
    PENDING = "pending"; APPROVED = "approved"; REJECTED = "rejected"; CANCELLED = "cancelled"
    ACTIVE = (PENDING, APPROVED)

class OptionalHolidayPick(Base):
    __tablename__ = "optional_holiday_pick"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    holiday_id: Mapped[int] = mapped_column(ForeignKey("holidaycalendar.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=PickStatus.PENDING, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text)
    decided_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("user.id", ondelete="SET NULL"))
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    __table_args__ = (Index("ix_ohp_user_year_status", "user_id", "year", "status"),)
```

**Create** `backend/app/models/work_location.py`:

```python
class WorkLocationKind:
    ON_DUTY = "on_duty"; CLIENT_VISIT = "client_visit"; WFH = "wfh"
    ALL = (ON_DUTY, CLIENT_VISIT, WFH); NEEDS_PLACE = (ON_DUTY, CLIENT_VISIT)

class DayPortion:
    FULL = "full"; FIRST_HALF = "first_half"; SECOND_HALF = "second_half"

class WorkLocationStatus:  # same values as PickStatus
    PENDING = "pending"; APPROVED = "approved"; REJECTED = "rejected"; CANCELLED = "cancelled"
    ACTIVE = (PENDING, APPROVED)

class WorkLocationRequest(Base):
    __tablename__ = "work_location_request"
    id, user_id (FK user CASCADE), kind String(16), start_date Date, end_date Date,
    day_portion String(16) default "full", place String(200) nullable, purpose Text not null,
    status String(16) default pending, decided_by_id, decided_at, decision_note, created_at
    __table_args__ = (Index("ix_wlr_user_status", "user_id", "status"),
                      Index("ix_wlr_dates", "start_date", "end_date"))
```

- Check the actual holiday table name: `HolidayCalendar` has no `__tablename__`, so check `app/db/base_class.py` for the generated name (likely `holidaycalendar`).
- Add `OPTIONAL_HOLIDAY = "optional_holiday"` and `WORK_LOCATION = "work_location"` to `ChainEntityType`. Check whether `ApprovalChain.entity_type` / `ApprovalInstance.entity_type` have a DB enum or check constraint; widen it in the migration if so (String(32) needs no change).
- Register both models in `models/__init__.py` (imports + `__all__`).

**Migration:** `backend/alembic/versions/a6b8d0f2c4e7_phase6a_holidays_work_location.py`, `down_revision = "e5a7c9b1d3f2"`. It creates both tables; the downgrade drops them (indexes first if MariaDB complains about FK-backing indexes, as in earlier migrations).

**Test** `backend/tests/test_phase6a_models.py`: insert and read back both rows; cascade on user delete.

- [ ] Steps: test → models → migration → `alembic upgrade head`, `downgrade -1`, `upgrade head` (take a dump first: `mariadb-dump` into the session scratchpad) → tests pass.
- [ ] Commit `feat(db): optional holiday picks and work-location requests tables`.

---

### Task 6: Optional holiday picks — service + API + chain + HR import

**Create** `backend/app/services/optional_holidays.py`:
- `async def quota(db) -> int`, from the rule `holidays.optional_quota_per_year` (added in this task with validation 0–20).
- `async def create_pick(db, *, user, holiday_id, reason) -> OptionalHolidayPick`. In order:
  1. lock the user row (`lock_row` on `User`);
  2. load the holiday, which must be `is_optional`, else 422 "not an optional holiday";
  3. check location (`holidays.applies`), else 422;
  4. check date ≥ `await local_today(db)`, else 422 "date has passed";
  5. reject if there is already an active pick for (user, holiday) — 409;
  6. count active picks for (user, holiday.date.year); ≥ quota → 409 "optional holiday quota (N) used";
  7. insert as pending.
- `async def finalize(db, pick, *, approved: bool, actor, note)`. Only a pending pick can be decided (else 409). On approve, check `_attendance_locked(db, user_id, date)`; if locked → 409 "payroll period locked". Reuse the existing helper that guards attendance edits in locked periods (grep `locked` in `services/punch.py` / `attendance_regularization.py`).
- `async def cancel(db, pick, *, actor, is_hr: bool)`. The employee's own pick can be cancelled only while active and the date ≥ local today. HR can cancel any active pick; an approved pick in a locked period → 409.
- Audit rows are written directly (`AuditLog`, no commit). The service must not import from `app/api`.
- Notify the employee on decide via `roster_svc.notify_many`, with `resource_type="optional_holiday"`.

**Approval routing (in the endpoint):** if an active chain exists for `ChainEntityType.OPTIONAL_HOLIDAY`, call `instantiate_for_entity(..., commit=False)`. Otherwise the pick waits for the direct approver, who is the employee's reporting manager or anyone with `leave approve` / HR. Mirror `asset_requests.py`'s `_can_decide`.
- Add a `_entity_summary` branch: "Optional holiday: <name> <date>".
- Add an `act_on_instance` branch: approved → `finalize(approved=True)`, rejected → `finalize(approved=False)`.

**Create** `backend/app/api/v1/endpoints/holidays.py` (`prefix="/holidays"`, not attendance-gated, `@guard_conflicts` on every mutation):
- `GET /my?year=` returns `{quota, used, remaining, holidays: [{id, name, date, location, is_optional, pick: {id,status}|null}]}`. It lists the mandatory holidays applicable to the user plus the eligible optional ones.
- `POST /picks {holiday_id, reason?}` → 201.
- `POST /picks/{id}/cancel`.
- `GET /picks?status=&year=` is scoped: HR sees all, a manager sees reports, anyone else gets 403.
- `POST /picks/{id}/decide {approve: bool, note?}` is direct-path only; when a chain instance exists → 409 "decide via approvals".

**HR additions in `hr.py`:**
- `GET /hr/holidays?location=` already exists; add `year`.
- New `POST /hr/holidays/import` takes a multipart CSV with header `name,date,location,is_optional`, dates `YYYY-MM-DD`, `is_optional` in {true,false,1,0,yes,no}. Rows identical on (date, location, name) are skipped. Response `{created, skipped, errors: [{row, error}]}`. Maximum 1000 rows, 1 MB.

**Wire `holidays_for` (Task 4)** to include approved picks: optional holidays apply only when an approved pick exists for that user.

**Tests** `backend/tests/test_optional_holidays.py`:
- quota (2 → third pick 409; a cancelled pick frees quota);
- wrong location 422; past date 422; mandatory holiday 422; duplicate 409;
- direct approve by manager → `holidays_for` includes it → `absence_lop` treats it as non-working;
- reject; employee cancel before date; employee cancel after date 409;
- chain path: create an `optional_holiday` chain → pick creates an instance → acting through `act_on_instance` approves it;
- concurrency: two parallel creates for the last quota slot → one 201, one 409, never 500 (use `asyncio.gather` with two sessions, as in `test_asset_requests.py`);
- CSV import: created/skipped/errors counts.

- [ ] Steps: TDD per bullet → implement → run tests → commit `feat(holidays): optional holiday picks with quota and approvals; CSV import`.

---

### Task 7: Work-location requests — service + API + chain

**Create** `backend/app/services/work_location.py`:
- `async def create(db, *, user, kind, start_date, end_date, day_portion, place, purpose)`. Validation:
  - `kind in ALL`;
  - `end_date >= start_date`, span ≤ 31 days;
  - half-day only when start == end;
  - `place` required and ≤200 chars for `NEEDS_PLACE`;
  - `purpose` 1–1000 chars;
  - `start_date >= local_today - attendance.work_location_backdate_days` (rule, default 7, 0–60);
  - all of these → 422.
  - Then lock the user row and reject an overlap with any active request of the same user. Two half-days on the same date with opposite halves are allowed; anything else overlapping → 409.
- `finalize` and `cancel` follow the same rules as Task 6. The locked-period check applies to every date in the range. Cancelling is allowed while `start_date >= local_today`, or by HR at any time.
- `async def approved_portions(db, user_ids, start, end) -> dict[int, dict[date, str]]` maps each date to `full|first_half|second_half`. An approved first_half plus an approved second_half on the same date → `full`.
- `async def approved_portion(db, user_id, d) -> str | None`.

**Routing:** same as Task 6, with `ChainEntityType.WORK_LOCATION`. Summary: "WFH 20–22 Nov" / "Client visit: Acme, 20 Nov (first half)". Add an `act_on_instance` branch.

**Create** `backend/app/api/v1/endpoints/work_location.py` (`prefix="/work-location-requests"`, not attendance-gated, `@guard_conflicts`):
- `POST /`;
- `GET /my?status=`;
- `POST /{id}/cancel`;
- `GET /?status=&kind=&from=&to=&user_id=`, scoped like Task 6;
- `POST /{id}/decide`.

Notify the employee on decide (`resource_type="work_location"`).

**Tests** `backend/tests/test_work_location.py`:
- each validation (422);
- overlap 409, opposite halves allowed;
- back-date limit;
- direct approve → `approved_portion` returns full;
- halves merge to full;
- chain path;
- cancel rules;
- locked period 409;
- parallel overlapping creates → one 201, one 409.

- [ ] Steps: TDD → implement → commit `feat(attendance): on-duty / client-visit / WFH requests`.

---

### Task 8: Effects of approved work-location requests

**Punch (`services/punch.py`, punch-in ~475 and punch-out ~671):**
- Before `evaluate_punch`, call `portion = await approved_portion(db, user.id, work_date_guess)`, where `work_date_guess` = `local_date(now, tz)`. For punch-out, use the open row's `work_date`.
- If `portion` is set (any portion; an approved half-day counts as remote for the whole day's punches):
  - call `evaluate_punch(..., enforcement_mode=EnforcementMode.ALLOW_WITH_FLAG, ...)`, so a strict fence never rejects;
  - then, if the resulting flag is `OUTSIDE_GEOFENCE` or `LOW_ACCURACY` (or the no-fence case), set the stored flag to `"approved_remote"`;
  - keep `MOCK_LOCATION` as is (a mock location is still suspicious);
  - skip `_notify_geo_flag` for `approved_remote`.
- Add `APPROVED_REMOTE = "approved_remote"` to `GeoFlag`.
- Check the frontend flag filters (`frontend/src/components/attendance-flagged-review.tsx`, `endpoints/attendance.py:417`) so `approved_remote` is **excluded** from the flagged-review queue by default.

**Absence / no-show / muster:**
- `absence_lop.count_absent_days`: takes `remote: dict[date,str]` for the user. A day with no punch and no leave counts 0 when `remote[d] == 'full'` and 0.5 when it is a half portion. A half portion combined with half leave → 0. Load it with `approved_portions` in the batch loader.
- `live_ops.py` no-show job and Live Board: no no-show alert when a full-day approved request covers the date. Board rows get `remote_kind` (`on_duty|client_visit|wfh|null`); add it to the response schema.
- `reports.py` muster: no punch + full remote → code `OD` (on_duty/client_visit) or `WFH`; half remote + no punch → `OD/2` / `WFH/2`. With punches, normal present logic applies. Add the codes to the legend docstring and to any legend the frontend renders.
- `location_tracking.py`: unchanged (tracking still follows the roster window).

**Tests** `backend/tests/test_work_location_effects.py`:
- Strict fence + punch 5 km away + approved WFH → 200 with `geo_flag == "approved_remote"`; the same without approval → strict rejection.
- Mock location with approval → `mock_location`.
- absence_lop: full → 0, half → 0.5, half + half leave → 0.
- No-show job skips a full-remote user and still flags a half-remote user with no punch.
- Muster codes.

- [ ] Steps: TDD → implement → run the effects tests plus the punch/absence/live_ops/reports tests → commit `feat(attendance): approved remote work relaxes geofence and counts as present`.

---

### Task 9: Shift-coverage report

- **Add** `shift_coverage` to `backend/app/services/report_catalog.py`, mirroring `ot_report`'s entry: params `start`, `end` (≤62 days, else 422), `department?`, `location?`, and the same permission as `muster_roll`.
- **Implement** `build_shift_coverage(db, start, end, department, location)` in `backend/app/services/reports.py`, returning rows `{date, shift_template_id, shift_name, department, location, required_min, required_max, scheduled, attended, fill_pct, status}`:
  - **Requirements:** active `CoverageRequirement` rows. A row applies to a date when `weekday is None or weekday == d.weekday()`. When several match the same (template, dept, location), the most specific wins: weekday-specific beats generic.
  - **Scheduled:** count of **published** `RosterEntry` rows for (date, template), excluding week-offs and filtered by employee department/location. Check the roster model for the published flag/status field (Phase 1A).
  - **Attended:** distinct `Attendance.user_id` with `work_date == d` and `shift_template_id == template`, within the same department/location filter.
  - **Result:** `fill_pct = round(100*attended/required_min)` when required_min > 0, else null. `status`: no requirement → `"no_requirement"`; attended < min → `understaffed`; max set and attended > max → `over`; else `met`.
  - Future dates (> local today) have `attended = null` and `fill_pct` computed from `scheduled`. Status is `understaffed_plan` when scheduled < min, otherwise `planned_ok` (or `no_requirement`). The full set of statuses is exactly: `understaffed`, `met`, `over`, `no_requirement`, `understaffed_plan`, `planned_ok`.
  - Run 4 batched queries in total, not per date.
- **Export** through the existing report export path; check how `ot_report` is exported.

**Tests** `backend/tests/test_shift_coverage_report.py`: one template, a requirement of min 2 / max 3, rosters and attendance for 3 dates giving understaffed / met / over; a weekday-specific override; department filter; range > 62 → 422; a future date → plan statuses.

- [ ] Commit `feat(reports): shift coverage report`.

---

### Task 10: Web UI

**10a — org time helper:**
- `frontend/src/lib/org-time.ts` fetches `/meta/org-time` once (module-level promise cache) and exposes:
  - `orgTimezone()`;
  - `orgToday(): string` (YYYY-MM-DD, computed client-side with `Intl.DateTimeFormat('en-CA', {timeZone})`);
  - `formatOrgTime(isoUtc, opts)`;
  - `useOrgTime()` hook.
- Replace `serverSafeToday()` in `components/assets/*` with `orgToday()`, and delete the helper if unused.
- Live Board and roster time displays (`grep -rn "toLocaleTimeString\|getHours" frontend/src/components/roster frontend/src/components/workforce`) format with `formatOrgTime`.
- Remove every hard-coded "UTC" label and `timeZone:'UTC'` formatting found in Task 2 review:
  - `live-board.tsx` (~130-147, 318, 507, 589);
  - `field-team.tsx` (~88, 250);
  - `my-schedule/running-late-card.tsx:107` (`eta_hhmm` is now org-local).
- `workforce/edit-punch-modal.tsx`: pre-fill org-local time instead of `iso.slice(0,16)` on the UTC string. Naive input is now read as org-local by the backend.

**10b — holidays:**
- `components/holidays/my-holidays-panel.tsx`, shown in `profile-view.tsx` (and in `leave-view.tsx` if that is where employees look for holidays; check the current usage of `Holiday` there). It shows a year selector, quota chip ("1 of 2 optional used"), the list of mandatory + optional holidays, a "Pick" button with an optional reason, the pick status badge, and "Cancel".
- `holiday-management.tsx` (HR) gains a location filter, a year filter and a CSV import dialog showing created/skipped/errors.
- `approvals-view.tsx`: an "Optional holidays" section listing pending direct-path picks with approve/reject. Chain-routed picks already show through the existing chain inbox via `_entity_summary`; check that they do.

**10c — work location:**
- `components/work-location/request-dialog.tsx`: kind select, date range, portion (enabled only when start == end), place (required for OD/client visit), purpose.
- `components/work-location/my-requests.tsx`: list with status and cancel. Add an entry point next to the attendance regularization UI (find where employees request regularization).
- Approver section in `approvals-view.tsx`.
- Attendance Control (`components/workforce/attendance-tab.tsx`): a "Remote" badge, plus a filter for `approved_remote`.
- Live Board shows the `remote_kind` badge.
- Muster legend shows `OD`, `WFH`, `OD/2`, `WFH/2`.
- Note: the Remote badge/filter live in Flagged Review (`attendance-flagged-review.tsx`), since `attendance-tab.tsx` has no per-punch rows.

**10d — reports + rules:**
- `shift_coverage` appears in `reports-catalog.tsx` automatically if the catalogue is server-driven; verify. Colour the status column: understaffed red, over amber, met green, using existing badge classes.
- Time Rules tab: `org.timezone`, `holidays.optional_quota_per_year`, `attendance.work_location_backdate_days`.
- `frontend/src/api/endpoints.ts`: add all the new endpoints.
- Header bell `resolveTab` for `optional_holiday` and `work_location` event resource types.

Checks after each sub-task: tsc ≤164, and that every new class exists in `index.css`. Smoke-test with the Playwright scripts from earlier phases (pattern: Phase 5 session scratchpad `pw/`; write new ones in this session's scratchpad).

- [ ] Commits: `feat(web): org time helper`, `feat(web): holidays panel, picks, import`, `feat(web): work-location requests`, `feat(web): coverage report + rules`.

---

### Task 11: Mobile (Expo)

- `mobile/src/lib/org-time.ts`: same API as the web helper. Add the fetch to the existing API client in `mobile/src/api`.
- `mobile/src/features/holidays/`: hooks (`useMyHolidays`, `usePickHoliday`, `useCancelPick`), a screen listing holidays with pick/cancel and the quota chip. Route `mobile/app/holidays.tsx`, reached from the More tab.
- `mobile/src/features/work-location/`: a request form (kind, dates, portion, place, purpose) and a My requests list with cancel. Route `mobile/app/work-location.tsx`, reached from the More tab and from a "Working remotely?" link on the Punch tab.
- `mobile/src/features/punch/RunningLateCard.tsx:29`: drop the "UTC" label, since `eta_hhmm` is now org-local. Audit other `timeZone: 'UTC'` uses in mobile.
- Punch tab: when today has an approved request, show a banner ("Approved WFH today — location check relaxed").
- Push: tapping an `optional_holiday` / `work_location` notification opens the relevant screen (`mobile/src/features/push` route map).
- Jest tests for hooks and form validation, following `features/leave` tests. `npm run check` green.
- Android release smoke on the Pixel_9 emulator: build with `-PreactNativeArchitectures=arm64-v8a`; do not touch other projects' emulators or containers.

- [ ] Commit `feat(mobile): holidays and remote-work requests`.

---

### Task 12: Verification, docs, final review

- [ ] Full backend suite. Expected: green except the 2 known `test_hr_employees` failures. Note the known timing flake `test_approval_concurrency::test_benign_writer`.
- [ ] Migration round-trip `a6b8d0f2c4e7` down/up (dump first).
- [ ] Web tsc ≤164; `vite build` OK. Mobile `npm run check` green.
- [ ] API E2E agent (session scratchpad `e2e_api6/run.py`, pattern from Phase 5's `e2e_api5`). Cover:
  - timezone parity (late mark, no-show, work date);
  - holiday location matching, pick quota/decide/cancel/races;
  - work-location CRUD, races, effects on punch/LOP/no-show/muster;
  - coverage report;
  - 0 × 5xx expected.
- [ ] Browser QA agent: employee picks a holiday, manager approves, HR imports a CSV; employee files WFH, approver approves, punch from outside the fence shows "Remote"; coverage report export; time rules.
- [ ] `DEPLOYMENT.md` "Phase 6A" section:
  - **HARD go-live step, timezone cutover.** The rule defaults to Asia/Kolkata when absent, so an existing install flips on deploy. Before deploying, set `org.timezone` explicitly; use `UTC` to keep the old behaviour until HR is ready.
    - Late/no-show flags from before the cutover used UTC.
    - `late_mark.process_month` re-run on a pre-cutover month re-interprets old punches in the new timezone, so don't re-run closed months.
    - Biometric devices with an explicit `utc_offset_minutes` keep it; a blank `biometric.default_utc_offset_minutes` follows the org timezone.
  - HQ-only holidays now apply only to employees whose location is HQ — review holiday locations;
  - the new rules;
  - the CSV import format.
- [ ] Final whole-branch review (superpowers:code-reviewer) → fix → commit.
- [ ] Update memory `roadmap-v2.md`.
