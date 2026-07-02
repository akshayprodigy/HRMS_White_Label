# Attendance Edit + Time Rules + Month Seed — Design

Date: 2026-07-02
Status: Approved (user, in-session)

## Problem

1. Employees forget to punch in/out. The existing correction-request flow
   cannot set punch times (new records hardcode 09:00; punch-out is never
   touched), so HR has no remedy today.
2. Nothing evaluates lateness/early exit, and there are no org-level time
   rules HR can configure.
3. Local stacks have no realistic historical data to exercise attendance,
   timesheets, flags, or payroll.

## Decisions (user-confirmed)

- **Direct edit** by HR/admin (no second approval step), with mandatory
  reason and full audit trail.
- HR/admin can also **create** a record for a fully-missed day.
- Edits are allowed **only before payroll's attendance lock** covers the
  date; after that the API refuses (409 naming the run).
- Late/early detection is **flag & report only** — no automatic pay impact.

## 1) HR/Admin direct attendance edit

### Backend
- New permission `attendance edit`; seeded to HR + admin roles
  (superuser bypasses).
- `PATCH /api/v1/hr/attendance/{id}` — body: `punch_in_time?`,
  `punch_out_time?`, `reason` (required, min 5 chars). Validates
  punch_out > punch_in; payroll-lock rule below.
- `POST /api/v1/hr/attendance/manual` — body: `user_id`, `work_date`,
  `punch_in_time`, `punch_out_time?`, `reason`. 409 if a record already
  exists for user+work_date; `mode='manual'`.
- Payroll-lock rule: refuse if any PayrollRun covering `work_date`'s
  month is at/past `ATTENDANCE_LOCKED`.
- Migration: add nullable `edited_by_id` (FK user), `edited_at` to
  `attendance`. Audit log records old→new + reason
  (`EDIT_ATTENDANCE` / `CREATE_MANUAL_ATTENDANCE`).

### Frontend (Attendance Control)
- Per-row "Edit times" (HR/admin/super admin) → modal: punch-in,
  punch-out, reason. Rows with `edited_at` show an "edited" badge.
- "+ Add missed punch" → employee, date, times, reason.
- 409s surface as toasts naming the payroll run.

## 2) Time rules (flag & report)

### Settings (SystemSetting KV; admin/HR editable via new endpoints)
- `attendance.default_start_time` (default "09:30"),
  `attendance.default_end_time` ("18:00") — fallback when no shift.
- `attendance.late_grace_minutes` (10), `attendance.early_exit_grace_minutes` (10)
  — org defaults; shift-assigned employees use the shift's own
  `grace_in/out_minutes`.
- `attendance.enable_late_flags` ("1") — master toggle.
- `GET/PUT /api/v1/hr/time-rules` (HR/admin permission `attendance edit`).

### Evaluation (read-time; no schema change)
- Late: `punch_in > (shift start ?? default) + grace`.
- Early exit: `punch_out < (shift end ?? default) − grace`.
- Shift-aware via existing `shift_resolver`, incl. overnight shifts.
- HR attendance list responses gain additive fields:
  `late_minutes`, `early_exit_minutes` (null when not applicable).

### UI (Attendance Control)
- "Late 23m" / "Early out 41m" chips on rows; Late/Early filter.
- New "Time Rules" tab (admin/HR gated) to edit the settings.

## 3) Month seed (`scripts/seed_month_data.py`)

- Local-guarded (`ERP_LOCAL_SEED=1` + `--yes-local`), idempotent.
- 3 shift templates covering 24h: Morning 09:00–17:30, Evening
  14:00–22:30, Night 22:00–06:30 (overnight); assigned across test users
  (t1 morning, t2 evening, t3 night, employee@ morning).
- ~30 days back of attendance per non-admin user: jittered punches,
  deliberate late entries, early exits, and a few missing punch-outs;
  weekends + seeded holidays skipped.
- Demo project + tasks; daily time entries roughly matching attendance.
- A few leave requests (approved/pending) woven in.

## Out of scope

- Employee-initiated punch-time corrections (existing request flow
  unchanged).
- Automatic half-day/LOP consequences from lateness.
- Geofence checks on manual HR edits (HR asserts the times).

## Verification

Playwright as hr@gmail.com: fix a seeded missing punch-out (badge
appears); add a missed day; late chips visible and filterable; change a
time-rule setting and see flags recompute; lock attendance in a payroll
run and confirm edits for that period are refused. Audit log entries
visible as admin.
