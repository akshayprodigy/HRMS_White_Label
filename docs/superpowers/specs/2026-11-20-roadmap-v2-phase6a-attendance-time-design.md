# Roadmap v2 — Phase 6A: Attendance & Time — Design

Date: 2026-11-20 · Branch: `feature/roadmap-v2-phase6` (off main = Phase 5 tip 971f12a)
Parent roadmap: `2026-11-12-roadmap-v2-shift-ops-and-competitive-gaps.md` (Phase 6 backlog, "Attendance & time" slice)

## Goal

Fix time-of-day correctness for non-UTC orgs, unify holiday handling, let employees work off-site legitimately, and report shift coverage.

## User decisions (2026-11-20)

1. **One org timezone** (IANA, default `Asia/Kolkata`) via a single helper; per-location timezones are a later Platform item that plugs into the same helper.
2. **Optional holidays:** employees pick up to N per year (time rule), each pick needs approval, approved picks count as holidays for that employee.
3. **On-duty / client-visit / WFH:** punching is still required, but geofence flags are relaxed on approved dates; if the employee forgets to punch, the approved request alone counts as present (no LOP, no no-show).

## Current state (verified 2026-11-20)

- Shift wall-clock times are combined with dates as **UTC** (`services/late_mark.py:53`, `services/reports.py:328`, `services/schedule_rules.py:49`, `endpoints/calendar_feed.py:128`, Live Board / no-show in `services/live_ops.py`). For IST staff, late marks and no-shows are off by 5h30.
- About 77 `date.today()` / UTC-date calls in business code define "today" as the server's UTC date.
- `HolidayCalendar(name, date, location, is_optional)` exists, but it is read four different ways:
  - `services/punch.py:263`: only `"All"`/`"HQ"`;
  - `services/absence_lop.load_holidays`: matched by the employee's location, non-optional only;
  - `services/overtime.classify_day`: a caller-supplied `holiday_dates`;
  - `services/reports.py`: the muster `is_holiday`.
  Nobody can actually pick an optional holiday.
- The muster roll and OT report already exist in `services/report_catalog.py`. A shift-coverage report does not.
- `CoverageRequirement(department, location, shift_template_id, weekday, min_headcount, max_headcount)` exists (Phase 1A).

## 1. Org timezone

**`services/org_time.py`** (new). The DB keeps storing UTC.
- `org_tz(db, user=None) -> ZoneInfo`: reads the time rule `org.timezone`, cached per request/job. The `user` argument is reserved for per-location timezones later.
- `local_today(tz) -> date`, `local_date(dt_utc, tz) -> date`, `local_now(tz)`.
- `shift_window(work_date, start_time, end_time, tz) -> (start_utc, end_utc)`: handles cross-midnight shifts, and is DST-safe through `zoneinfo` (fold=0; for a nonexistent local time, shift forward).
- The time rule `org.timezone` is validated against `zoneinfo.available_timezones()` in `services/time_rules.py` and shown on the Time Rules tab.

**Call-site migration:**
- Every `datetime.combine(<date>, <shift time>)` in services and endpoints becomes `shift_window`. This covers late mark, reports, schedule rules, the ICS feed, live ops, no-show and roster insights.
- Every business-logic `date.today()` / `datetime.now(utc).date()` becomes `local_today(...)`. This covers assets, exit, timesheets, tax, statutory, roster, revisions, payroll, reports, asset requests and maintenance, and the scheduler jobs.
- Work-date resolution for punches with no shift uses `local_date`.
- Biometric: when a device's `utc_offset_minutes` is unset, the default comes from the org timezone's current offset. The `biometric.default_utc_offset_minutes` rule stays as an explicit override.
- **Guard test:** a test scans `backend/app/services` and `backend/app/api` and fails on any new bare `date.today()` or on `datetime.combine` applied to a `start_time`/`end_time` without `shift_window`. An allow-list file holds the justified exceptions.

**Frontend:**
- A public `GET /api/v1/meta/org-time` returns `{timezone, utc_offset_minutes, today}`.
- `frontend/src/lib/org-time.ts` (`orgToday()`, `formatOrgTime()`) is used by the Live Board, roster times and the asset date defaults, replacing `serverSafeToday()`.
- The Expo app gets an equivalent helper.

**Compatibility:**
- Existing rows are not recomputed. Late/no-show flags written before the cutover stay as they are, and `DEPLOYMENT.md` documents the cutover.
- `org.timezone=UTC` must reproduce today's behaviour exactly; a parity test covers late mark, no-show and work-date resolution.

## 2. Holidays

**`services/holidays.py`** (new) — the only holiday reader:
- `holidays_for(db, user_ids, start, end) -> dict[user_id, dict[date, HolidayInfo]]`. A holiday applies to a user when it is
  - a mandatory holiday whose `location` is `All` or matches `Employee.location` (case-insensitive, whitespace-trimmed), or
  - an optional holiday the user has an **approved** pick for.
- `is_holiday(db, user_id, d) -> HolidayInfo | None`, a single-day convenience wrapper.
- Callers migrated: punch comp-off (drops the `"HQ"` hard-code), `absence_lop`, overtime day classification, muster/report rows, live ops / no-show.

**Optional holiday picks:**
- **Table** `optional_holiday_pick`: id, holiday_id FK, user_id FK, year, status (`pending|approved|rejected|cancelled`), reason, decided_by_id, decided_at, decision_note, created_at. There may be only one active (pending or approved) pick per (holiday, user); the service enforces this under a locking read on the user row.
- **Quota:** the time rule `holidays.optional_quota_per_year` (default 2, range 0–20). Pending and approved picks both count against it.
- **Eligibility:** the holiday has `is_optional=True`, its location is `All` or the user's location, and it falls on or after `local_today()`.
- **Approval:** chain engine entity_type `optional_holiday` (`instantiate_for_entity(commit=False)`), with a direct manager/HR decision when no chain applies (the same pattern as asset requests).
- **Cancellation:** allowed by the employee until the holiday date; HR can cancel at any time.
- **Locked payroll periods:** approving or cancelling a pick in a period whose attendance is locked returns 409 with a clear message.
- **Endpoints** `/holidays`: `GET /my` (applicable mandatory + optional holidays with pick status, plus quota used/remaining), `POST /picks`, `POST /picks/{id}/cancel`, `GET /picks` (approver/HR scoped), `POST /picks/{id}/decide`. They are not attendance-gated, and every mutation is wrapped in `@guard_conflicts`.
- **HR:** the existing `/hr/holidays` CRUD gains a location filter and a `POST /hr/holidays/import` CSV route (name, date, location, is_optional; duplicates skipped).

**UI:**
- Web: an employee Holidays panel (profile area), approver queue entries on the existing approvals page, and HR holiday-calendar location filter + import.
- Expo: a Holidays screen with pick and cancel.

## 3. On-duty / client-visit / WFH requests

**Table** `work_location_request`:
- id, user_id, kind (`on_duty|client_visit|wfh`), start_date, end_date, day_portion (`full|first_half|second_half`; half-day only allowed when start=end), place (string, required for on_duty/client_visit), purpose (text), status (`pending|approved|rejected|cancelled`), decided_by_id, decided_at, decision_note, created_at.
- Overlapping pending or approved requests for the same user are rejected with 409. The range is limited to 31 days. Back-dating is limited by the rule `attendance.work_location_backdate_days` (default 7).
- Approval uses chain entity_type `work_location` with direct fallback. Cancellation is allowed until start_date, or by HR at any time; the same locked-period guard as picks applies.

**`services/work_location.py`:** `approved_portion(db, user_id, d) -> 'full'|'first_half'|'second_half'|None` plus a batch variant for ranges.

**Effects of an approved request:**
- **Punch (in and out):** the coordinates are still stored. Instead of any geofence-related flag (outside-fence / no-fence), the punch is flagged `geo_flag = 'approved_remote'`, so it doesn't land in the geo review queue. Mock-location and liveness rules are unchanged.
- **Absence→LOP:** a day with no punches counts as present for a full-day request (0 LOP) and half present for a half-day request (0.5 LOP).
- **No-show job / Live Board:** no alert while a full-day request covers the shift. The Live Board shows an "On duty"/"WFH" badge.
- **Muster:** a distinct code (`OD` / `WFH`) when there are no punches. When punches exist, normal present/hours logic applies and the code carries a suffix marker.
- **Hours/OT:** always come from real punches; a request never invents hours.

**Endpoints** `/work-location-requests`: `POST /`, `GET /my`, `POST /{id}/cancel`, `GET /` (approver/HR scoped, filters), `POST /{id}/decide`. Not attendance-gated; `@guard_conflicts` on every mutation.

**UI:**
- Web: an employee request form + list, the approver queue, and a "Remote today" filter on Attendance Control.
- Expo: a request form + "My requests" list.

## 4. Shift-coverage report

- Report catalogue entry `shift_coverage`, with filters for date range (≤ 62 days), department and location.
- One row per (date, shift template, department, location), giving:
  - **required:** min and max from the active `CoverageRequirement` matching the weekday (or any weekday);
  - **scheduled:** the published roster entries;
  - **attended:** distinct users with an attendance row whose work_date and shift match;
  - **result:** fill % = attended / min, and status `understaffed|met|over`.
- Shift windows and "today" use the org timezone. Export goes through the existing CSV/XLSX report pipeline.

## Out of scope (later Phase 6 slices)

Per-location timezones, a WFH monthly cap, the travel-request link to client visits, holiday calendar per entity, payroll changes beyond the existing LOP/OT readers.

## Migrations

One migration chained onto `e5a7c9b1d3f2`, creating `optional_holiday_pick` and `work_location_request` with indexes on (user_id, status) and (start_date, end_date). Seed nothing; the time rules use code defaults. The downgrade drops both tables.

## Testing & verification

- **Unit tests:**
  - org_time: IST/UTC parity, cross-midnight, a DST zone such as `Europe/London`;
  - the guard scan test;
  - holidays_for location matching + approved picks;
  - quota/eligibility/overlap/back-date rules;
  - approved_portion effect on absence_lop, no-show and muster codes;
  - the coverage report math.
- **Concurrency tests:** duplicate pick/request creation, and decide vs cancel races (expected outcome 409, never 500).
- **Full backend suite:** green except the 2 known `test_hr_employees` failures.
- **Migration:** down/up round-trip on the dev DB, using a dump first.
- **Web type check:** tsc count must not rise above 164.
- **Mobile:** Jest green, plus an Android release smoke test of the new screens.
- **QA agents:** API E2E agent (scratchpad), browser QA agent, final whole-branch review.
- **Docs:** a `DEPLOYMENT.md` section on the timezone cutover and the new rules.
