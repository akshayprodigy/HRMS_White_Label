# Roadmap v2 — Phase 1A (Scheduling Core) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Turn the existing roster planner (W7) into a 24×7 scheduling tool. This covers four pieces:
- HR-granted scheduling delegation
- reusable rotation patterns
- work-rule and coverage validation
- a real draft → publish lifecycle with change history after publish

**Architecture:** Build on `RosterEntry` / `services/roster.py` / `endpoints/roster.py` / `roster-planner.tsx`. Per Phase 0, published roster entries already drive attendance. Scope checks stay centralized in `services/roster.py`. New validation lives in pure functions (`services/schedule_rules.py`) fed by batched queries.

**Tech Stack:** FastAPI + async SQLAlchemy 2.0 + MariaDB + Alembic (linear chain); React/TS + shadcn/ui with pre-compiled Tailwind.

Spec: `docs/superpowers/specs/2026-11-12-roadmap-v2-shift-ops-and-competitive-gaps.md` (§1.1–1.4)
Branch: `feature/roadmap-v2-phase1`, stacked on `feature/roadmap-v2-phase0` (unmerged). Migration head at start: `d8e9f0a1b2c3`.

**Deferred to Phase 1B (separate plan):**
- shift swaps, open shifts, availability/preferences
- auto-fill
- ICS feed, live ops board, no-show detection
- pay linkage
- schedule lock window / emergency override (Phase 2)

**Product decisions taken (spec "open decisions" #1):**
- A delegation grant has a `can_publish` flag, default **False**.
- A delegate without it can only save drafts and **request** a publish, which HR approves.

## Environment (all tasks)

- **Docker project** `erp-united-exploration-dev`:
  - Backend container `erp-united-exploration-dev-backend-1`, code volume-mounted at `/app` with uvicorn --reload.
  - API at http://localhost:8005, FE at http://localhost:5173.
  - DB container `erp-united-exploration-dev-db-1` (MariaDB).
- **Tests:** `docker exec erp-united-exploration-dev-backend-1 python -m pytest tests/<file> -q`. DB-backed tests hit the dev DB and MUST clean up the rows they create (delete by id in `finally`/fixture teardown).
- **Migrations:**
  - Check `alembic heads`; the chain is LINEAR, so `down_revision` = current single head.
  - MariaDB DDL is non-transactional, so downgrade drops directly.
  - Verify upgrade → downgrade -1 → upgrade.
- **Logins** (password `test@12345`):
  - `admin@gmail.com` (superuser)
  - `hr@gmail.com` (HR role, holds `roster manage`? verify; if not, treat HR via `is_roster_admin`)
  - `employee@gmail.com` (manager `pm@gmail.com`)
  - `pm@gmail.com`
- **Frontend:**
  - Tailwind is PRE-COMPILED, so reuse only utility classes already present in `frontend/src`. Novel classes silently no-op.
  - shadcn/ui is in `frontend/src/components/ui`; `Card, Button, Badge, cn` come from `./ui-elements`.
  - API paths go in `frontend/src/api/endpoints.ts` (`ENDPOINTS.ROSTER`).
  - TypeScript check: `cd frontend && npx -y -p typescript@5.6.3 tsc --noEmit -p .`. There are ~167 pre-existing errors; introduce **no new** ones (compare the count before/after).
- **Audit:** `from app.api.v1.endpoints.hr import log_audit` (as roster.py does). It commits.
- **Notifications:** best-effort `Notification` row inside `async with db.begin_nested()` + try/except. Copy the pattern from `backend/app/api/v1/endpoints/attendance_regularization.py` (`_notify`).
- **Id spaces:** `RosterEntry.employee_id` is a **User id**.
- **Commits:** commit each task separately. End messages with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## File map

| File | Responsibility |
|---|---|
| `backend/app/models/schedule_delegation.py` (new) | `ScheduleDelegation` grant |
| `backend/app/models/rotation_pattern.py` (new) | `RotationPattern` (N-day cycle) |
| `backend/app/models/coverage_requirement.py` (new) | `CoverageRequirement` headcount rows |
| `backend/app/models/roster.py` (modify) | add `RosterEntryHistory`, `RosterPublishRequest` |
| `backend/app/services/roster.py` (modify) | scope = admin ∪ dept head ∪ active delegation; publish capability |
| `backend/app/services/schedule_rules.py` (new) | pure rule checks + coverage computation |
| `backend/app/api/v1/endpoints/schedule_delegations.py` (new) | `/roster/delegations` CRUD |
| `backend/app/api/v1/endpoints/roster.py` (modify) | rotations, insights, publish, copy, history |
| `frontend/src/components/schedule-delegations.tsx` (new) | HR grant/revoke screen |
| `frontend/src/components/roster-planner.tsx` (modify) | rotation apply, coverage row, violation badges, draft/publish, copy week |

---

## Task 1 — Scheduling delegation (backend)

**Model** `backend/app/models/schedule_delegation.py`, table `schedule_delegation`, registered in `models/__init__.py`:

```python
class DelegationScope:
    EMPLOYEES = "employees"    # explicit list in employee_ids (User ids)
    DEPARTMENT = "department"  # scope_value = Department.name
    LOCATION = "location"      # scope_value = Employee.location
    TEAM = "team"              # direct reports of grantee (User.manager_id == grantee_id)

class ScheduleDelegation(Base):
    id: int PK
    grantee_id: int FK user.id CASCADE, indexed
    scope_type: str(16) not null
    scope_value: Optional[str(100)]          # dept / location name
    employee_ids: list JSON default list     # for scope_type employees
    can_publish: bool default False
    can_approve_changes: bool default False  # decide RosterChangeRequests in scope
    valid_from: date not null
    valid_to: Optional[date]                 # NULL = open-ended
    revoked_at: Optional[datetime tz]
    granted_by_id: Optional[int] FK user SET NULL
    note: Optional[str(255)]
    created_at: datetime tz default now
```

**Migration:** `down_revision="d8e9f0a1b2c3"`. Downgrade drops the table.

**Service changes** in `backend/app/services/roster.py`. Keep the existing function names and signatures, since endpoints already call them.
- `async def active_delegations(db, user, on: date | None = None) -> list[ScheduleDelegation]`:
  - grantee == user
  - not revoked
  - valid_from <= on <= valid_to (or valid_to NULL)
  - `on` defaults to UTC today
- `async def delegated_user_ids(db, user) -> set[int]`: union over active delegations.
  - employees → `employee_ids`
  - department → active Employees with `department == scope_value`
  - location → active Employees with `location == scope_value`
  - team → Users with `manager_id == user.id`
  - Batched: one query per delegation at most; no per-employee queries.
- `scoped_employees`: admin → all (unchanged). Otherwise return the union of head-of departments plus delegated user ids. The previous early return `[]` must now consider delegations.
- `scope_department_names` remains for back-compat. In `endpoints/roster.py::get_plan`, replace the "no departments ⇒ 403" check: 403 only when `scoped_employees` is empty AND the user is not admin. Message: "You have no roster scope."
- `can_manage_employee`: admin OR head-of OR the employee's user id is in `delegated_user_ids`.
- `async def can_publish_for(db, user, employee_user_id) -> bool`:
  - admin → True
  - department head of employee → True (heads keep today's ability to publish)
  - otherwise True only if an active delegation covering the employee has `can_publish`
- `async def can_approve_changes_for(db, user, employee_user_id) -> bool`: same shape using `can_approve_changes`. Wire it into `decide_change_request` and `scoped_change_requests` (currently head/admin only) so delegates with that flag can act.

**API** `backend/app/api/v1/endpoints/schedule_delegations.py`. Mount it in `api/v1/api.py` at `/roster/delegations` BEFORE the roster router. Admin-only (`roster_svc.is_roster_admin`, else 403), except `GET /my`.
- `GET /?include_inactive=false`: list with grantee name, granted_by name, and computed `covered_count` (len of the delegation's resolved user ids).
- `POST /`: validate scope.
  - employees: non-empty list, all ids exist.
  - department: Department name exists.
  - location: at least one Employee with that location.
  - team: scope_value must be null.
  - `valid_to >= valid_from`.
  - Grantee must be an active user.
  - Audit `schedule_delegation.grant`.
  - Notify the grantee.
- `PATCH /{id}`: update flags, validity, note. Audit.
- `POST /{id}/revoke`: set `revoked_at`. Audit. Notify the grantee. Idempotent: 409 if already revoked.
- `GET /my`: the current user's active delegations (any user).
- `GET /preview?scope_type=&scope_value=&employee_ids=`: returns `[{user_id, full_name, department}]` that a grant would cover (UI helper, admin-only).

**Schemas** in `backend/app/schemas/schedule_delegation.py`: `DelegationCreate`, `DelegationUpdate`, `DelegationRead`.

**Tests** `backend/tests/test_schedule_delegation.py`. DB-backed; create your own users/employees or reuse seeded ones; clean up.
- A department delegation makes `can_manage_employee` true for that department's employee and false for others.
- An employees-list delegation covers exactly the listed users.
- A team delegation covers direct reports.
- An expired, future, or revoked delegation grants nothing.
- `can_publish_for` false for a delegate without the flag and true with it. Admin is always true.
- `scoped_employees` for a pure delegate (no department head) is non-empty.
- API: a non-admin POST is 403; the create/revoke happy path works; double revoke is 409.
- `tests/test_roster*.py` (existing) still pass.

---

## Task 2 — Delegation UI (HR)

- `frontend/src/components/schedule-delegations.tsx`:
  - Table of grants with grantee, scope (human readable), flags as Badges, validity, status (active/expired/revoked), and covered count.
  - "Grant scheduling access" dialog:
    - grantee (searchable user select; reuse an existing employee/user picker component if one exists, otherwise a `<select>` populated from the existing users/employees list endpoint)
    - scope type
    - scope value / employee multi-select
    - can_publish / can_approve_changes checkboxes
    - valid from/to
    - note
  - A live "covers N employees" preview via `/preview`.
  - Revoke with an inline confirm (no `window.confirm`).
- Placement: add it as a tab/section inside the Roster Planner page, visible only when `grid.is_admin`. Use a top-level toggle "Planner | Delegations", not a new sidebar item.
- In `roster-planner.tsx`, a non-admin delegate (no departments headed) must now load the grid instead of seeing the 403 message.
- Endpoints: `ENDPOINTS.ROSTER.DELEGATIONS`, `DELEGATION_DETAIL(id)`, `DELEGATION_REVOKE(id)`, `DELEGATIONS_MY`, `DELEGATION_PREVIEW`.
- Verify live: as admin, grant `employee@gmail.com` a department delegation. Then log in as employee@gmail.com and check that Roster Planner shows only that department.

---

## Task 3 — Rotation patterns (backend)

**Model** `backend/app/models/rotation_pattern.py`, table `rotation_pattern`:

```python
class RotationPattern(Base):
    id: int PK
    name: str(80) unique not null
    description: Optional[str(255)]
    # cycle[i] = shift_template_id or None (None = week-off). len 1..56.
    cycle: list JSON not null
    is_active: bool default True
    created_by_id: Optional[int] FK user SET NULL
    created_at: datetime tz default now
```

Migration chained on Task 1's revision. Validate every non-null id in `cycle` is an existing active `ShiftTemplate` (422 otherwise).

**Pure expansion** in `services/roster.py`:

```python
def expand_rotation(
    cycle: list[Optional[int]], anchor: date, start: date, end: date,
    offset: int = 0,
) -> list[tuple[date, Optional[int], bool]]:
    """Day d gets cycle[((d - anchor).days + offset) % len(cycle)].
    Returns (date, template_id, is_week_off) for every day in [start, end];
    None in the cycle => (d, None, True)."""
```

`offset` lets a team be staggered (e.g. crew A offset 0, crew B offset 4 on a 4-on-4-off).

**API** in `endpoints/roster.py`:
- `GET /roster/rotations`: any roster-scoped user.
- `POST /roster/rotations`, `PATCH /roster/rotations/{id}`, `DELETE /roster/rotations/{id}` (soft: `is_active=False`): admin only. Audit each.
- `POST /roster/rotations/{id}/apply` body:
  ```json
  {"employee_ids": [..] | null, "department": str | null, "start": date, "end": date,
   "anchor": date, "offsets": {"<user_id>": int} | null, "default_offset": 0,
   "overwrite": true, "status": "draft" | "published"}
  ```
  - Same scope filtering and result shape as `bulk_plan` (`RosterBulkResult`). Out-of-scope ids are reported, not written.
  - Range ≤ 62 days.
  - `status` defaults to `"draft"`.
  - If `status == "published"` and the caller lacks `can_publish_for` an employee, write that employee's cells as **draft** and append a message to `result.errors` saying so (count per employee, not per cell).
  - Reuse `upsert_entry`.
- Apply the same publish-capability downgrade to the existing `POST /roster/bulk`, `POST /roster/entries` and `PATCH /roster/entries/{id}` (status "published" → "draft" for callers without publish rights). Note: `POST /roster/entries` currently hard-codes PUBLISHED. Give `RosterEntryInput` an optional `status` (default `"published"` for back-compat), then apply the downgrade.

**Tests** `backend/tests/test_rotation_pattern.py`:
- Pure: 4-on-4-off with anchor → correct days; offset staggers; dates before the anchor wrap correctly (negative modulo); a None slot yields week-off; a 2-2-3 (14-day) pattern.
- API: create validates template ids (422 on bad id); apply writes drafts by default; a delegate without `can_publish` asking for published gets drafts plus an error message; an out-of-scope employee is reported.
- Cleanup of roster rows and patterns.

---

## Task 4 — Work rules + coverage (backend)

**Org-level work-rule settings** go in `services/time_rules.py::TIME_RULE_DEFAULTS`, following the existing pattern and validation style:
- `schedule.min_rest_hours` "11": minimum rest between consecutive shifts (hours, 0 = off)
- `schedule.max_consecutive_days` "6": max consecutive working days (0 = off)
- `schedule.max_consecutive_nights` "4": max consecutive overnight shifts (0 = off)
- `schedule.max_weekly_hours` "48": max scheduled hours per Mon–Sun week (0 = off)

`set_time_rules` must reject non-integer / negative values for these keys with ValueError, mapped to 422 as with weekly offs.

**Coverage model** `backend/app/models/coverage_requirement.py`, table `coverage_requirement`, migration chained:

```python
class CoverageRequirement(Base):
    id: int PK
    department: Optional[str(100)]    # NULL = all departments
    location: Optional[str(100)]      # NULL = all locations
    shift_template_id: int FK shift_template CASCADE not null
    weekday: Optional[int]            # 0..6; NULL = every day
    min_headcount: int not null (>=0)
    max_headcount: Optional[int]      # NULL = no cap
    is_active: bool default True
    created_at: datetime tz default now
```

**Pure rules** in `backend/app/services/schedule_rules.py`. No DB in the pure functions.

```python
@dataclass(frozen=True)
class ShiftSpan:          # one scheduled working day
    user_id: int
    work_date: date
    template_id: int
    start: datetime        # naive, work_date + start_time
    end: datetime          # +1 day if overnight
    hours: float           # (end-start) - break_minutes/60
    is_overnight: bool

@dataclass(frozen=True)
class Violation:
    user_id: int
    work_date: date
    rule: str   # "min_rest" | "max_consecutive_days" | "max_consecutive_nights" | "max_weekly_hours" | "on_leave" | "holiday"
    message: str

def build_spans(cells, templates) -> list[ShiftSpan]: ...
def check_rules(spans: list[ShiftSpan], rules: dict[str, int]) -> list[Violation]: ...
def check_leave_conflicts(spans, approved_leave_days: set[tuple[int, date]]) -> list[Violation]: ...
def compute_coverage(spans, requirements, emp_meta: dict[int, tuple[dept, location]], dates) -> list[CoverageCell]: ...
```

Rule semantics:
- **min_rest:** for consecutive spans of the same user (sorted by start), `next.start - prev.end < min_rest_hours`. Report on `next.work_date`.
- **max_consecutive_days:** run length of working dates (spans) > N. Report on the first date exceeding.
- **max_consecutive_nights:** same, over overnight spans only.
- **max_weekly_hours:** sum of `hours` per user per ISO week (Mon–Sun) > N. Report on the last span of that week.
- **on_leave:** a span on a date the user has APPROVED leave (full-day only; half-day is not a conflict).
- **holiday:** not a violation. Skip it; keep the rule string out of the enum.
- Rules with value 0 are disabled.

`CoverageCell(date, shift_template_id, department, location, required_min, required_max, scheduled, status)`:
- status is `"under"` if scheduled < min, `"over"` if max is set and scheduled > max, else `"ok"`.
- A requirement matches an employee if `department` is null or equal, and `location` is null or equal. `weekday` is null or equals `date.weekday()`.
- `scheduled` counts spans with that template on that date among employees matching the requirement's department/location.

**API** in `endpoints/roster.py`:
- `GET /roster/insights?start&end&department=`: same scope and range limits as `/plan`. Returns `{violations: [...], coverage: [...]}`.
  - Uses the planner's own view: **draft and published** entries both count (planners validate drafts before publishing), then the assignment fallback for empty cells (reuse `build_grid` cell logic or `effective_shifts_for_range` plus a drafts overlay).
  - To catch rest/consecutive breaches at the window edges, load spans for `start - 7 days` .. `end + 1 day`. Only return violations whose date is in [start, end].
  - Batched: roster, assignments, templates, approved leaves, requirements, and employees each at most one query.
- Coverage requirements CRUD: `GET/POST/PATCH/DELETE /roster/coverage-requirements`. Admin only for writes; scoped users may read.

**Tests** `backend/tests/test_schedule_rules.py`:
- Pure tests for every rule, including:
  - overnight 22:00–06:00 followed by 14:00 the next day → rest 8h < 11 → violation
  - 7 straight days with max 6 → one violation on day 7
  - nights run
  - weekly hours with break deduction
  - rules set to 0 are disabled
  - half-day leave is not a conflict
- Coverage: under/ok/over; a weekday-specific requirement; a department filter.
- One API test for `/roster/insights` creating 2 draft roster rows that break min-rest, asserting the violation appears; plus a 422 for a bad `schedule.min_rest_hours`.

---

## Task 5 — Publish lifecycle + change history (backend)

**Models** (add to `backend/app/models/roster.py`, one migration chained):

```python
class RosterEntryHistory(Base):          # table roster_entry_history
    id PK
    employee_id int FK user CASCADE indexed
    work_date date indexed
    roster_entry_id Optional[int] FK roster_entry SET NULL
    old_shift_template_id Optional[int]  (no FK; templates may be deleted)
    old_is_week_off bool
    new_shift_template_id Optional[int]
    new_is_week_off bool
    action str(16)    # "update" | "delete" | "publish"
    reason Optional[str(500)]
    changed_by_id Optional[int] FK user SET NULL
    changed_at datetime tz default now

class RosterPublishRequest(Base):        # table roster_publish_request
    id PK
    requested_by_id int FK user CASCADE indexed
    start date; end date
    department Optional[str(100)]
    employee_ids JSON default list       # resolved in-scope user ids at request time
    note Optional[str(500)]
    status str(16) default "pending" indexed   # pending/approved/rejected/cancelled
    decided_by_id Optional FK user SET NULL; decided_at; decision_note Optional[str(500)]
    created_at
```

**Behavior:**
1. **Edits to a PUBLISHED entry** go through `PATCH /entries/{id}`, `DELETE /entries/{id}`, `POST /entries` (overwrite), bulk/rotation apply with overwrite, and change-request approval.
   - Write a `RosterEntryHistory` row (action update/delete) **only when the shift or week-off actually changes**.
   - `PATCH` and `DELETE` of a published entry require a `reason`: a body field on PATCH, a `?reason=` query on DELETE. Return 422 "reason required to change a published schedule" if missing or empty.
   - Bulk/rotation overwrite of published cells uses reason `"bulk re-plan"`. Change-request approval uses the request's reason.
   - Notify the affected employee (one notification per employee per request, not per cell): "Your schedule changed for <dates>".
   - Put the history-writing in one helper in `services/roster.py`: `record_change(db, entry, old_tpl, old_off, action, reason, actor_id)`.
   - Edits to DRAFT entries record nothing.
2. **`POST /roster/publish`** body `{start, end, department?, employee_ids?}`, range ≤ 62 days.
   - For the in-scope employees the caller `can_publish_for`, flip DRAFT → PUBLISHED.
   - Write history rows with action `"publish"` (old = previously published values: none, since a draft had no published state; record new values only).
   - Notify each affected employee once: "Your schedule for <start>–<end> is published".
   - Returns `{published: n, employees: k, not_permitted: [user_ids]}`.
   - Audit `roster.publish`.
3. **Publish requests** for delegates without publish rights:
   - `POST /roster/publish-requests` `{start, end, department?, employee_ids?, note?}`. Stores in-scope ids. 409 if an identical pending one exists (same requester, start, end). Notify roster admins (users with `roster manage` or superuser; cap at 20 notifications).
   - `GET /roster/publish-requests?status=pending`: admin sees all; others see their own.
   - `POST /roster/publish-requests/{id}/decide` `{approve: bool, note?}`: admin only, `with_for_update` row lock. Reject requires a note. Approve runs the same publish routine as #2 restricted to the stored ids and window, as the admin. Notify the requester.
   - `POST /roster/publish-requests/{id}/cancel`: requester only, pending only.
4. **`POST /roster/copy`** body `{source_start, source_end, target_start, department?, employee_ids?, overwrite: false}`:
   - Copies each in-scope employee's roster cells (draft + published), offset by `target_start - source_start`, into the target window as **draft**. Source span ≤ 31 days.
   - Returns `RosterBulkResult`.
5. **`GET /roster/history?employee_id=&start=&end=`**: scoped history list with names, newest first. Employees may query their own via `GET /roster/my/history`.

**Tests** `backend/tests/test_roster_publish.py`:
- PATCH of a published entry without a reason → 422; with a reason → a history row plus a notification.
- A draft edit has no history.
- Publish flips only permitted employees' drafts; delegate without the flag → `not_permitted`.
- Publish-request flow: create, duplicate 409, reject without note 422, approve publishes, cancel.
- Copy week offsets dates and writes drafts.
- `/roster/my` still hides drafts (regression).
- Cleanup.

---

## Task 6 — Planner UI: drafts, publish, rotation, copy, history

In `frontend/src/components/roster-planner.tsx`. Split new pieces into sibling files if the component would exceed ~700 lines, e.g. `frontend/src/components/roster/rotation-dialog.tsx` and `roster/publish-bar.tsx`.

1. **Draft visuals:** draft cells get a dashed border plus a "Draft" Badge/marker (reuse existing classes such as `border-dashed`; check it exists in the compiled CSS by grepping `frontend/src` / the built CSS first).
   - A header bar shows "N draft changes in this view".
   - Buttons: **Publish** (if the user can publish) or **Request publish** (if not; derive from the publish response or add `can_publish: bool` to `RosterGridResponse`, computed as "can publish for every in-scope row").
   - Add the `can_publish` field to the backend `RosterGridResponse` / `build_grid` in this task.
2. **Edit mode toggle:** "Save edits as: Draft | Published". The default is Draft. Published is disabled when the user can't publish.
   - Editing a published cell prompts for a reason in an inline dialog (required, min 3 chars), then sends it.
3. **Rotation:** a "Rotations" dialog to list/create patterns (admin) and apply them.
   - Cycle builder: add days, each a template select or "Off".
   - Presets that fill the builder: "4-on-4-off", "2-2-3 (Panama)", "Weekly A→B→C", using the first two/three active templates.
   - Apply form: employees (current filtered rows, checkboxes), anchor date, per-employee offset (number input, default 0), status.
   - Show the result counts and errors via toast.
4. **Copy previous week/period** button: copies the previous window of the same length into the current one as drafts.
5. **Publish requests queue** (admins): a small panel listing pending requests with approve/reject (note required for reject).
6. **History:** clicking a cell's "history" icon (or the employee name) opens a dialog with `/roster/history` for that employee in the window.
- Keep the existing pattern dialog working.
- Verify live:
  - Create drafts, check that employee@gmail.com's My Shift does not show them, then publish and check they appear plus a notification.
  - Edit a published cell with a reason, then check the history.

---

## Task 7 — Planner UI: coverage + rule violations + settings

1. Fetch `/roster/insights` alongside `/plan` (same window/department, refetch after every edit; guard stale responses with a request id like `regularization-requests.tsx` does).
2. **Coverage strip:** under the grid header, one row per shift template that has requirements. Each date cell shows `scheduled/min` coloured by status (under = red, ok = green, over = amber), reusing existing badge colour classes.
3. **Violations:** cells with violations get a warning icon plus a tooltip/title listing messages. A collapsible "N rule warnings" list appears above the grid. Warnings never block saving.
4. **Coverage requirements editor** (admin): a dialog CRUD (department, location, shift, weekday or "every day", min, max).
5. **Work-rule settings:** add the four `schedule.*` keys to `frontend/src/components/workforce/time-rules-tab.tsx` as number inputs in a "Scheduling rules" card, sharing the existing single Save button.
- Verify live: set min rest 11; schedule a night shift then a morning shift the next day for one employee as draft; the warning appears. Add a requirement min 2 and see the red coverage cell.

---

## Final

- Whole-branch review (superpowers:code-reviewer).
- Full backend suite (expect the pre-existing test_hr_employees failures only; exclude test_admin_auth / test_leave_flows, which were already broken).
- tsc error count not increased.
- Live smoke as admin + delegate + employee.
- Update memory `roadmap-v2.md` with Phase 1A status and write the Phase 1B plan next.
