# Roadmap v2 — Phase 0 Implementation Plan

Spec: `docs/superpowers/specs/2026-11-12-roadmap-v2-shift-ops-and-competitive-gaps.md` (Phase 0)
Branch: `feature/roadmap-v2-phase0` (from `feature/workforce-expansion`)
Execution: subagent-driven (one implementer per task, spec review then code-quality review).

## Environment (all tasks)

- Stack runs in Docker project `erp-united-exploration-dev`; backend container `erp-united-exploration-dev-backend-1` (code volume-mounted from `./backend` at `/app`, uvicorn --reload), API at http://localhost:8005, frontend at http://localhost:5173, MariaDB container `erp-united-exploration-dev-db-1`.
- Run tests: `docker exec erp-united-exploration-dev-backend-1 python -m pytest tests/<file> -q` (DB-backed tests hit the dev MariaDB).
- Migrations: `docker exec erp-united-exploration-dev-backend-1 alembic heads` / `alembic upgrade head`. Chain is LINEAR — a new migration's `down_revision` must be the current single head. MariaDB DDL is non-transactional; downgrade must drop tables directly.
- Logins (password `test@12345`): `admin@gmail.com` (super admin), `hr@gmail.com`, `pay.*@test.com`.
- Frontend: Tailwind is PRE-COMPILED — only reuse utility classes already used elsewhere; novel classes silently no-op. shadcn/ui components in `frontend/src/components/ui`. Routing = `activeTab` switch in `App.tsx`; API paths in `frontend/src/api/endpoints.ts`.
- Commit each task separately; end commit messages with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

---

## Task 1 — Roster drives the effective shift

**Problem:** `RosterEntry` (W7) is display-only. Attendance resolves shifts via `_effective_shift_on` in `backend/app/api/v1/endpoints/attendance.py` (~line 222), which reads only `EmployeeShiftAssignment`. `hr.py` imports that helper for manual attendance creation.

**Build:**
1. New `backend/app/services/effective_shift.py`:
   - `@dataclass(frozen=True) class EffectiveShift: shift: Optional[ShiftTemplate]; is_week_off: bool; source: str  # "roster" | "assignment" | "none"`
   - `async def effective_shift_on(db, user_id: int, on_date: date) -> EffectiveShift`
   - `async def effective_shifts_for_range(db, user_ids: list[int], start: date, end: date) -> dict[tuple[int, date], EffectiveShift]` — batched: one query for roster entries in window, one for assignments overlapping window (with templates eager-loaded); no per-day queries. Returns an entry for every (user_id, date) in range.
   - Precedence for a (user, date):
     1. `RosterEntry` with `status == PUBLISHED` for that user/date:
        - `is_week_off=True` → `EffectiveShift(None, True, "roster")`
        - `shift_template_id` set → that template, `is_week_off=False`, source "roster"
        - neither (blank cell) → fall through
        - DRAFT entries are ignored entirely.
     2. Active `EmployeeShiftAssignment` (same query semantics as today: effective_from <= d, effective_to NULL or >= d, latest effective_from wins) → template; `is_week_off = d.weekday() in (template.weekly_offs or [])` (Mon=0..Sun=6); source "assignment".
     3. Otherwise `EffectiveShift(None, False, "none")` (caller applies org default).
   - Note: `RosterEntry.employee_id` and `EmployeeShiftAssignment.employee_id` are both **User ids**.
2. `attendance.py::_effective_shift_on` becomes a thin wrapper returning `(await effective_shift_on(...)).shift` — keep its name/signature (hr.py imports it). A roster week-off therefore yields no shift for that day (punch is flagged `no_shift`, as unscheduled).
3. Update the precedence docstring in `backend/app/models/roster.py` (it currently says roster is display-only) to describe the new behavior: published roster overrides assignment for attendance; drafts ignored.
4. Tests `backend/tests/test_effective_shift.py` (DB-backed, clean up rows you create): published roster shift overrides assignment; roster week-off → None + week_off; blank roster cell falls back to assignment; draft roster ignored; assignment weekly_offs sets is_week_off; no data → source "none"; range function agrees with single-day function across a mixed 7-day window.
5. Existing tests `tests/test_shift_resolver.py` and attendance tests must still pass.

**Out of scope:** payroll changes, roster UI changes, overtime.

---

## Task 2 — Payroll LOP: half-day fix + unexplained-absence LOP (toggle)

**Location:** `generate_draft` loop in `backend/app/api/v1/endpoints/payroll.py` (~lines 430–462), which today sums unpaid-leave days + late-mark LOP.

**Build:**
1. **Half-day bug:** for an unpaid leave with `is_half_day`, the LOP is `overlap_days * 0.5` (currently hard-set to 0.5 regardless of span).
2. **Settings** in `backend/app/services/time_rules.py::TIME_RULE_DEFAULTS`:
   - `attendance.absence_lop_enabled` default `"0"` — "Count unexplained absences on scheduled working days as LOP in payroll (1/0)"
   - `attendance.default_weekly_offs` default `"6"` — "Comma-separated weekdays off for employees with no shift (Mon=0..Sun=6)"
   - Expose both in the existing Time Rules UI `frontend/src/components/workforce/time-rules-tab.tsx` following its current pattern (toggle + text input).
3. New `backend/app/services/absence_lop.py`:
   - `async def absence_days_for_period(db, employees, start: date, end: date, today: date) -> dict[int, float]` keyed by **user_id**.
   - A day d is counted for an employee when ALL hold:
     - `max(start, employee.date_of_joining) <= d <= min(end, today - 1 day)` (never count today/future; also stop at the employee's exit/last-working date if the Employee/exit-management model records one — find it; if none exists, skip that bound and note it in your report).
     - Not a holiday: `HolidayCalendar` row on d with `is_optional == False` and `location` in `("All", employee.location or "HQ")`.
     - Not a week-off: use Task 1's `effective_shifts_for_range`; if source "none", week-off iff `d.weekday()` in the parsed `attendance.default_weekly_offs`.
     - No attendance: no `Attendance` row for the user with `work_date == d` (fallback: `captured_at` date when `work_date` is NULL).
     - Leave coverage: an APPROVED `LeaveRequest` (any type) covering d → full day excused; if that leave `is_half_day` → 0.5 counts as absent? **No** — half-day leave + no punch = 0.5 absent. Full-day leave = 0 absent.
   - Batched queries only (no per-day DB calls).
4. In `generate_draft`: if `attendance.absence_lop_enabled` is truthy (`"1","true","yes","on"`) **and** `run.run_type != "off_cycle"`, add `absence_days[emp.user_id]` to `lop_days`. When the toggle is off, output must be byte-identical to before (except the half-day fix).
5. If `PayrollLine` already has a JSON breakdown/metadata field, record `absence_lop_days` there; otherwise do NOT add a migration — just fold into `lop_days`.
6. Tests `backend/tests/test_absence_lop.py`: working day with no punch counted; punched day not counted; holiday, roster week-off, shift weekly_off, default weekly-off excluded; full-day approved leave excluded; half-day leave + no punch = 0.5; days before joining and today/future excluded. Plus a unit test for the half-day multi-day LOP math (extract a small pure helper if needed).

**Out of scope:** UI for absence reports, regularization.

---

## Task 3 — Attendance regularization requests (backend)

Employees can't currently request a fix for a missed/wrong punch; only HR edits directly via `PATCH /hr/attendance/{id}` and manual create in `backend/app/api/v1/endpoints/hr.py` (~2270–2420), guarded by `_assert_attendance_editable` (refuses once a payroll run for that month is past DRAFT).

**Build:**
1. Move `_assert_attendance_editable` into `backend/app/services/attendance_lock.py` (`assert_attendance_editable`); hr.py imports it from there (no behavior change).
2. Model `AttendanceRegularization` (`backend/app/models/attendance_regularization.py`, table `attendance_regularization`, registered in `models/__init__.py`): id, user_id (FK user, CASCADE, indexed), work_date (indexed), attendance_id (FK attendance, SET NULL, nullable), requested_punch_in (DateTime tz, required), requested_punch_out (nullable), reason (Text, required), status (String16: pending/approved/rejected/cancelled, default pending, indexed), decided_by_id (FK user SET NULL), decided_at, decision_note, created_at.
3. Alembic migration chained on the current single head (check `alembic heads`); downgrade drops the table.
4. Schemas + endpoints in a new router `backend/app/api/v1/endpoints/attendance_regularization.py`, mounted at `/attendance/regularizations` (register like other routers):
   - `POST /` (any employee, for self): work_date not in future; punch_out > punch_in if given; `assert_attendance_editable(work_date)`; 409 if a pending request exists for same user+date; links `attendance_id` if a row exists for that work_date.
   - `GET /my` — own requests, newest first.
   - `GET /` — approver queue, `?status=pending` default. Users with `ATTENDANCE_EDIT` permission see all; otherwise only requests from users whose `User.manager_id == current_user.id`; others get an empty list.
   - `POST /{id}/decide` body `{approve: bool, note?: str}` — only pending; approver must be ATTENDANCE_EDIT holder or the requester's manager; requester can never decide own (reuse `services/self_approval.py` if it fits). On approve: re-check `assert_attendance_editable`; if attendance row exists → update `captured_at`/`punch_out_time`, set `edited_by_id`/`edited_at`; else create `Attendance(mode="regularized", work_date, shift snapshot via _effective_shift_on, edited_by...)` mirroring hr.py's manual-create. Audit via `log_audit` (action `APPROVE_ATTENDANCE_REGULARIZATION` / `REJECT_...`) with old/new values.
   - `POST /{id}/cancel` — requester only, pending only.
   - Best-effort notifications (requester's manager on create; requester on decision) using the existing notifications service pattern, if one exists that's a one-liner to call; skip otherwise and note it.
5. Tests `backend/tests/test_attendance_regularization.py` (API-level using existing conftest client/auth helpers): create, duplicate 409, future-date 422, manager approve creates/updates attendance, self-approve blocked, non-manager non-HR cannot decide, cancel, locked-month 409.

---

## Task 4 — Attendance regularization UI

1. `frontend/src/api/endpoints.ts`: add regularization endpoints.
2. Employee side: where employees see their own attendance history (find it — likely `attendance-modal.tsx` / dashboard / `mobile/screens/mobile-attendance.tsx`), add "Request correction" (dialog: date, punch-in, punch-out optional, reason) + "My correction requests" list with status and cancel for pending.
3. Approver side: a "Regularization requests" view for HR/managers — prefer adding a tab to an existing attendance review workspace (e.g. `attendance-flagged-review.tsx` or the attendance tabbed workspace) rather than a new sidebar item; approve/reject with note.
4. Reuse existing shadcn components and existing Tailwind classes only.
5. Verify in the running app (http://localhost:5173) — employee creates, manager/HR approves, attendance reflects. Add a Playwright smoke case to the existing suite if the suite pattern makes it cheap.

---

## Final

- Whole-branch review, full backend test run, live payroll parity check: with `absence_lop_enabled=0` a draft for the seeded month matches pre-change totals; enabling it adds LOP only for seeded unexplained absences.
- Update memory (roadmap-v2) with Phase 0 status.
