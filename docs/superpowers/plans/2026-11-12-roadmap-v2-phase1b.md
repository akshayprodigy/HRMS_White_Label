# Roadmap v2 — Phase 1B (Self-service, Auto-fill, Live Ops, Pay Linkage) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish Phase 1 of the roadmap spec (§1.3 auto-fill, §1.5 employee self-service, §1.6 live operations board, §1.7 pay linkage) on top of the Phase 1A scheduling core.

**Architecture:** Same layering as 1A. New models get their own files and migrations (linear chain). Business rules live in pure functions (tested without DB); routers are thin and live in new `roster_*.py` modules mounted under `/roster`. Every roster write goes through `services/roster.py` (`upsert_entry`, `record_change`, `notify*`) so history, publish-rights and notifications stay consistent. Scope checks reuse `manageable_subset` / `publishable_subset` / `approvable_subset`.

**Tech Stack:** FastAPI + async SQLAlchemy 2.0 + MariaDB + Alembic; React/TS + shadcn/ui with PRE-COMPILED Tailwind.

Spec: `docs/superpowers/specs/2026-11-12-roadmap-v2-shift-ops-and-competitive-gaps.md` §1.3 (auto-fill), §1.5, §1.6, §1.7.
Branch: `feature/roadmap-v2-phase1b`, stacked on `feature/roadmap-v2-phase1`. Migration head at start: `d4e5f6a7b8c9`.

**Product decisions taken:**
- Spec open decision #2 (open-shift fill): **scheduler confirms by default**; each open shift has an `auto_confirm` flag (default False) that confirms the first eligible claimant automatically.
- Swaps are approved by someone with `can_approve_changes` rights over **both** employees (roster admin, or delegate covering both). The two parties can never approve their own swap unless roster admin.
- Shift times are **wall-clock**, compared as UTC, exactly as attendance does today (`shift_resolver.late_in_minutes(..., tz=utc)`, `_attribute_punch`). No org timezone is introduced in this phase (tracked follow-up). The ICS feed emits **floating** local times (no `Z`, no `TZID`) so calendar apps show the wall-clock shift time.
- Comp-off for working a week-off is behind a new time rule `attendance.weekoff_comp_off_enabled` (default `0`).
- Shift handover notes (§1.6, optional) are deferred.

**Out of scope (Phase 2):** schedule lock window, emergency override, coverage-gap engine, emergency leave.

## Environment (all tasks)

- **Docker project** `erp-united-exploration-dev`: backend container `erp-united-exploration-dev-backend-1` (code at `/app`, uvicorn --reload, API http://localhost:8005), frontend `erp-united-exploration-dev-frontend-1` (http://localhost:5173), DB `erp-united-exploration-dev-db-1` (MariaDB).
- **Tests:** `docker exec erp-united-exploration-dev-backend-1 python -m pytest tests/<file> -q`. Tests in `backend/tests/` have NO conftest: copy the fixture pattern from `backend/tests/test_roster_publish.py` (real DB via `app.db.session.SessionLocal`, per-module fixture creating users/employees/templates with a `uuid4().hex[:8]` suffix, yielding plain ids, deleting everything in `finally`; client via `create_app()` + `app.dependency_overrides[deps.verify_attendance] = lambda: None` + `httpx.AsyncClient(transport=ASGITransport(app=app))`; login helper posting form `username`/`password` to `/api/v1/auth/login`). Delete test shift templates with `tests/_cleanup.py: purge_shift_templates(db, ids)` (removes all FK-referencing rows first); teardown must leave zero rows behind. Use far-future dates (2030/2031) unless the logic is "today"-relative, in which case freeze `now` by passing it as a parameter to the pure function under test.
- **Migrations:** run `docker exec erp-united-exploration-dev-backend-1 alembic heads` first; chain is LINEAR so `down_revision` = the single current head. MariaDB DDL is non-transactional. Verify `alembic upgrade head` → `alembic downgrade -1` → `alembic upgrade head`. Revision ids must be unique 12-hex strings (grep `backend/alembic/versions` before choosing).
- **Models** must be imported in `backend/app/models/__init__.py` (follow how `schedule_delegation` / `rotation_pattern` are registered — check `app/db/base*.py` too).
- **Routers:** add new `roster_*.py` modules and mount them in `backend/app/api/v1/api.py` under prefix `/roster` with `dependencies=[Depends(deps.verify_attendance)]`, BEFORE the main `roster.router` (static paths must precede `/{id}` style routes). Exception: the public ICS route (Task 5) is mounted with NO auth/attendance dependency.
- **Errors:** raise `HTTPException(status, "message")` — the app wraps them into `{"error":{"code","message"}}`. Use 400 for invalid state transitions/windows, 403 for scope, 404 for not found, 409 for conflicts/races. Lock rows being decided with `select(...).with_for_update()` (see `_lock_cr` in `endpoints/roster.py`). Use `roster_common.commit_or_409`.
- **Roster writes:** `roster_svc.upsert_entry(db, ..., status=RosterStatus.PUBLISHED, overwrite=True)`, then `roster_svc.record_change(...)` with a reason, then `roster_svc.notify_schedule_changed(db, {user_id: {dates}})`. Read these functions before using them.
- **Notifications:** `roster_svc.notify(db, user_id, title, message, resource_type, resource_id)` / `notify_many(db, rows)` (best-effort, savepoint).
- **Frontend:**
  - NO Tailwind build. A class works only if its selector literally exists in `frontend/src/index.css`. Check every class you use with `cd frontend && python3 /private/tmp/claude-501/-Users-akshayghosh-ReactNative-InnoCoreLabs-HRMS-White-Label/994b71d9-53c3-43ba-bd64-b7c371023999/scratchpad/twcheck.py <files...>` (whole-selector check). "Used elsewhere in src" is NOT proof. Missing utilities: add them inside the existing `@layer utilities { }` block at the END of index.css, written as Tailwind v4 would compile them.
  - shadcn/ui in `frontend/src/components/ui`. API paths in `frontend/src/api/endpoints.ts` (`ENDPOINTS.ROSTER`), client in `frontend/src/api/client.ts`. Error text via `errMsg` and dates via `todayIso` / `parseServerDate` from `frontend/src/components/schedule-delegations-utils.ts`.
  - Navigation is state-driven (no router): new page = import + `case` in `App.tsx renderContent()` + title in `getPageTitle()` + `MenuItem` in `components/sidebar.tsx`.
  - Type check: `docker exec erp-united-exploration-dev-frontend-1 sh -c 'cd /app && npx -y -p typescript@5.6.3 tsc --noEmit -p . 2>&1 | grep "error TS" | wc -l'` — baseline **166**; introduce no new errors (and zero errors in files you touch).
- **Logins** (password `test@12345`): `admin@gmail.com` (superuser), `hr@gmail.com`, `employee@gmail.com` (manager `pm@gmail.com`), `pm@gmail.com`.
- **Commits:** one or more per task, message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Never push.

## File map

| File | Responsibility |
|---|---|
| `backend/app/models/availability.py` (new) | `EmployeeAvailability` |
| `backend/app/services/availability.py` (new) | pure `expand_availability`, DB `availability_by_day` |
| `backend/app/api/v1/endpoints/roster_availability.py` (new) | `/roster/availability` |
| `backend/app/models/shift_swap.py` (new) | `ShiftSwapRequest` |
| `backend/app/services/swaps.py` (new) | swap cell exchange (pure) + apply + rule check |
| `backend/app/api/v1/endpoints/roster_swaps.py` (new) | `/roster/swaps` |
| `backend/app/models/open_shift.py` (new) | `OpenShift`, `OpenShiftClaim`, `ShiftDropRequest` |
| `backend/app/services/open_shifts.py` (new) | eligibility + confirm logic |
| `backend/app/api/v1/endpoints/roster_open_shifts.py` (new) | `/roster/open-shifts`, `/roster/drops` |
| `backend/app/models/calendar_feed.py` (new) | `CalendarFeedToken` |
| `backend/app/services/ics.py` (new) | pure ICS rendering |
| `backend/app/api/v1/endpoints/calendar_feed.py` (new) | token mgmt under `/roster/my/calendar-feed` + public `/calendar/{token}.ics` |
| `backend/app/services/autofill.py` (new) | pure greedy auto-fill |
| `backend/app/api/v1/endpoints/roster_autofill.py` (new) | `/roster/autofill/preview` |
| `backend/app/models/no_show.py` (new) | `NoShowAlert` |
| `backend/app/services/live_ops.py` (new) | pure status classifier + board loader + no-show job |
| `backend/app/api/v1/endpoints/roster_live.py` (new) | `/roster/live` |
| `backend/app/services/scheduler.py` | register no-show + nightly OT jobs |
| `backend/app/services/overtime.py`, `endpoints/overtime.py`, `endpoints/attendance.py` | pay linkage |
| `backend/app/services/time_rules.py` | `schedule.no_show_minutes`, `attendance.weekoff_comp_off_enabled` |
| `frontend/src/components/my-schedule/*` (new) | employee self-service panels |
| `frontend/src/components/roster/*` (new files) | scheduler requests view, open-shift dialogs, auto-fill dialog, availability overlay |
| `frontend/src/components/live-board.tsx` (new) | live ops page |

---

### Task 1: Availability & preferences (backend)

**Files:** Create `models/availability.py`, `schemas/availability.py`, `services/availability.py`, `endpoints/roster_availability.py`, migration, `tests/test_availability.py`. Modify `models/__init__.py`, `api.py`, `endpoints/roster_rules.py` (insights), `schemas/roster.py` if the violation schema needs a new code.

**Model** `employee_availability`:

```python
class AvailabilityKind(str, enum.Enum):
    UNAVAILABLE = "unavailable"
    PREFERRED = "preferred"

class EmployeeAvailability(Base):
    __tablename__ = "employee_availability"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = Column(String(16), nullable=False)          # AvailabilityKind value
    weekday = Column(Integer, nullable=True)           # 0=Mon..6=Sun, recurring
    specific_date = Column(Date, nullable=True)        # one-off
    shift_template_id = Column(Integer, ForeignKey("shift_template.id", ondelete="CASCADE"), nullable=True)
    valid_from = Column(Date, nullable=True)           # bounds for recurring rules
    valid_to = Column(Date, nullable=True)
    note = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
```
(Check the real table names of User and ShiftTemplate before writing FKs.)

Semantics: exactly one of `weekday` / `specific_date`. `unavailable` + no template = whole day unavailable; `unavailable` + template = unavailable for that shift only; `preferred` requires a template ("I prefer shift X on Mondays"). `valid_from <= valid_to` when both set; `valid_*` only allowed with `weekday`. Max 50 rules per user (400). Validate the template exists and is active (422/400).

**Pure service:**

```python
@dataclass
class AvailabilityDay:
    unavailable_all_day: bool = False
    unavailable_templates: set[int] = field(default_factory=set)
    preferred_templates: set[int] = field(default_factory=set)

    def blocks(self, template_id: Optional[int]) -> bool:
        return self.unavailable_all_day or (template_id is not None and template_id in self.unavailable_templates)

def expand_availability(rules, start: date, end: date) -> dict[tuple[int, date], AvailabilityDay]:
    """rules: objects with user_id, kind, weekday, specific_date, shift_template_id, valid_from, valid_to.
    Only (user, day) pairs with at least one rule appear in the result."""

async def availability_by_day(db, user_ids, start, end) -> dict[tuple[int, date], AvailabilityDay]
```

**Endpoints** (`/roster/availability`):
- `GET /my` → own rules; `POST /my`; `PATCH /my/{id}`; `DELETE /my/{id}` (404 if not own).
- `GET /?start=&end=&department=` → for schedulers: rules of employees in `manageable_subset` (roster admin: all active), returned raw with `user_id` and `employee_name`; window ≤ 62 days (400).

**Insights integration:** in `/roster/insights` add violations with code `unavailable` (severity same as other warnings, message e.g. "Scheduled on a day marked unavailable") for every working cell (draft or published) whose `AvailabilityDay.blocks(template_id)` is true. Reuse the batch loaders; one extra query.

**Tests:** pure `expand_availability` (weekday recurring with/without bounds, specific date, template-specific vs whole day, preferred); API: CRUD own, cannot touch others' rule (404), validation errors (both weekday+date, preferred without template, >50 rules), scheduler list is scoped (delegate sees only scope), insights returns `unavailable` violation.

- [ ] Write failing tests → implement → tests pass → migration up/down/up → commit `feat(roster): employee availability & preferences`.

---

### Task 2: Shift swaps (backend)

**Files:** Create `models/shift_swap.py`, `schemas/shift_swap.py`, `services/swaps.py`, `endpoints/roster_swaps.py`, migration, `tests/test_shift_swaps.py`. Modify `models/__init__.py`, `api.py`, `services/roster.py` (approver helper).

**Concept:** a swap exchanges the two employees' *effective published cells* on one or two dates. `requester_date` = the requester's shift they want to hand over; `counterparty_date` (optional, default = same date) = the counterparty's shift they take in return. For each distinct date `d` in `{requester_date, counterparty_date}`, A's cell on `d` and B's cell on `d` are exchanged. (Same day → straight exchange. Different days with B off on D1 and A off on D2 → the classic "you cover my Monday, I cover your Thursday".)

A *cell* = `(shift_template_id | None, is_week_off)` resolved with `effective_shifts_for_range` from `services/effective_shift.py` (published roster → assignment → none). Applying writes explicit PUBLISHED `RosterEntry` rows for both employees on each date (even if previously blank), so the result is unambiguous.

**Model** `shift_swap_request`: `id`, `requester_id`, `counterparty_id` (FK user), `requester_date`, `counterparty_date` (Date, not null — store the same date when not given), `reason` String(500), `status` String(20) (`pending_peer` | `pending_approval` | `approved` | `rejected` | `declined` | `cancelled`), `peer_responded_at`, `decided_by_id`, `decided_at`, `decision_note` String(500), `created_at`. Index `(counterparty_id, status)`, `(requester_id, status)`.

**Pure helper (services/swaps.py):**

```python
Cell = tuple[Optional[int], bool]   # (template_id, is_week_off)

def swapped_cells(a_cells: dict[date, Cell], b_cells: dict[date, Cell], dates: list[date]) -> tuple[dict[date, Cell], dict[date, Cell]]:
    """Return (new_a, new_b) for the given dates: values exchanged."""
```

**Validation on create** (400 unless stated): requester ≠ counterparty; counterparty is an active employee; both dates ≥ today (UTC) and ≤ today+90; |counterparty_date − requester_date| ≤ 14 days; requester's cell on `requester_date` is a PUBLISHED working shift (a published `RosterEntry` with a template — the requester must have a real rostered shift to hand over); the swap must change something (cells not identical); no other pending swap involving either party on either date (409); neither party on approved leave on a date where they would end up working (409, message names the date) — use `roster_svc.approved_leave_days`.

**Rule check (warnings, never blocking):** `async def swap_warnings(db, swap) -> list[Violation]` — build each employee's spans for `[min_date−7, max_date+7]` from published cells with the swapped cells substituted, run `schedule_rules.check_rules` with `get_schedule_rules(db)` and availability `blocks` (Task 1), and return only violations touching either swapped date range or either employee. Expose it via `GET /roster/swaps/{id}/check` and include in the decide response.

**Flow & endpoints** (`/roster/swaps`):
- `GET /candidates?date=YYYY-MM-DD` → active employees in the requester's department (excluding self) with their effective cell that date: `[{user_id, name, shift_template_id, shift_name, is_week_off}]`.
- `POST /` `{counterparty_id, requester_date, counterparty_date?, reason}` → `pending_peer`; notify counterparty.
- `GET /my` → swaps where I'm requester or counterparty (newest first, limit 100), with names and the cells involved.
- `POST /{id}/accept` (counterparty only, status `pending_peer`) → `pending_approval`; re-validate (dates still future, cells unchanged since create — if the requester's cell changed, 409 "schedule changed"); notify requester and approvers (`schedule_approver_ids`).
- `POST /{id}/decline` (counterparty, `pending_peer`) → `declined`; notify requester.
- `POST /{id}/cancel` (requester, `pending_peer`/`pending_approval`) → `cancelled`.
- `GET /` (approver queue) → `pending_approval` swaps where the caller `can_approve_changes_for` both employees (batch with `approvable_subset`).
- `POST /{id}/decide` `{action: approve|reject, note?}` → row-lock; status must be `pending_approval`; caller must be able to approve changes for **both** employees (403); parties cannot decide unless roster admin (403); on approve re-validate (dates not past, leave) then apply: `upsert_entry` PUBLISHED overwrite for each changed (employee, date), `record_change(... reason=f"Shift swap #{id}")`, `notify_schedule_changed`, notify both parties; on reject notify both.

**Approver helper** in `services/roster.py`:

```python
async def schedule_approver_ids(db, employee_user_ids: set[int]) -> set[int]:
    """Users who may approve changes for ALL given employees: active delegations with
    can_approve_changes whose scope covers all of them; if none, roster admins
    (users with is_roster_admin semantics — superusers + HR/Super Admin roles)."""
```

**Tests:** pure `swapped_cells`; API: full happy path (create → accept → approve → both employees' published entries exchanged, history rows with reason, notifications), different-day classic swap, decline, cancel, counterparty-only accept (403 for others), self-approval blocked, approver lacking scope over one party (403), past date (400), requester without a published shift (400), duplicate pending (409), leave conflict (409), double decide (409/400, not 500), `/check` returns a rest violation when the swap creates one.

- [ ] TDD → migration → commit `feat(roster): shift swap requests`.

---

### Task 3: Open shifts (backend)

**Files:** Create `models/open_shift.py` (`OpenShift`, `OpenShiftClaim`; `ShiftDropRequest` is added in Task 4 in the same file), `schemas/open_shift.py`, `services/open_shifts.py`, `endpoints/roster_open_shifts.py`, migration, `tests/test_open_shifts.py`.

**Models:**
- `open_shift`: `id`, `work_date` (Date, index), `shift_template_id` (FK), `department` String nullable, `location` String nullable, `slots` Integer (1..50), `filled` Integer default 0, `note` String(255), `status` String(16) (`open` | `filled` | `cancelled`), `auto_confirm` Boolean default False, `created_by_id` (FK user), `source_drop_id` Integer nullable (Task 4), `created_at`.
- `open_shift_claim`: `id`, `open_shift_id` (FK cascade), `user_id`, `status` (`pending` | `approved` | `rejected` | `withdrawn`), `decided_by_id`, `decided_at`, `created_at`; unique `(open_shift_id, user_id)`.

**Eligibility** — `async def eligible_reason(db, shift: OpenShift, user_id) -> Optional[str]` returns `None` if eligible, else a human reason:
1. active employee; matches `department` / `location` when set (Employee fields);
2. the shift's creator can publish for the user (`can_publish_for`), or the creator is roster admin;
3. `work_date >= today`;
4. user's effective cell that day (`effective_shift_on`) is not a working shift (week-off or none);
5. not on approved leave that day; not `availability.blocks(template)`.
Batch version `eligible_user_ids(db, shift, candidate_ids)` for listing.

**Endpoints** (`/roster/open-shifts`):
- `POST /` (scheduler) `{work_date, shift_template_id, department?, location?, slots, note?, auto_confirm}` — caller must have a non-empty `publishable_subset` among active employees matching the department/location filter (else 403); template active; date ≥ today. Notify eligible employees (`notify_many`, cap 500).
- `GET /?start=&end=&status=` (scheduler) → open shifts the caller created, or all if roster admin, each with claims (name, status, eligibility reason now).
- `GET /available` (employee) → `open` shifts in [today, today+60] where the caller is eligible, with `my_claim_status`.
- `POST /{id}/claim` → creates `pending` claim (400 if ineligible, with reason; 409 if already claimed or not open). If `auto_confirm` → immediately confirm (same code path as approve, actor = creator for history `changed_by_id`).
- `POST /claims/{cid}/withdraw` (claimant, pending) → `withdrawn`.
- `POST /claims/{cid}/decide` `{action: approve|reject}` — caller must `can_publish_for` claimant (or creator / roster admin); not own claim unless admin; lock the open shift row (`with_for_update`) then:
  - approve: re-check eligibility (400 with reason), `slots - filled > 0` (409 "already filled"), upsert PUBLISHED entry for claimant (template, `overwrite=True`), `record_change(reason=f"Open shift #{id}")`, `filled += 1`, `status = filled` when full and auto-reject remaining pending claims (notify them); notify claimant.
  - reject: notify claimant.
- `POST /{id}/cancel` (creator or roster admin) → `cancelled`, pending claims rejected + notified. Already-approved claims keep their entries.

**Tests:** create (scope 403 for non-scheduler), eligibility each rule, claim → approve → entry published + history + filled count, slot exhaustion auto-rejects others, double approve race (two concurrent approvals on last slot → exactly one wins, other 409), auto_confirm path, withdraw, cancel, reject.

- [ ] TDD → migration → commit `feat(roster): open shifts with claims`.

---

### Task 4: Give-away (drop shift) requests (backend)

**Files:** Modify `models/open_shift.py` (+ `ShiftDropRequest`), `schemas/open_shift.py`, `endpoints/roster_open_shifts.py` (new router prefix `/roster/drops` in the same module or a sibling), migration, `tests/test_shift_drops.py`.

**Model** `shift_drop_request`: `id`, `user_id`, `work_date`, `shift_template_id` (snapshot), `reason` String(500) (required, ≥3 chars), `status` (`pending` | `approved` | `rejected` | `cancelled`), `post_open_shift` Boolean (set on approve), `open_shift_id` nullable, `decided_by_id`, `decided_at`, `decision_note`, `created_at`.

**Endpoints:**
- `POST /roster/drops` `{work_date, reason}` → own PUBLISHED working entry on a date ≥ today required (400); one pending per (user, date) (409); notify `schedule_approver_ids({user})`.
- `GET /roster/drops/my`; `POST /roster/drops/{id}/cancel` (owner, pending).
- `GET /roster/drops` → pending drops the caller `can_approve_changes_for`.
- `POST /roster/drops/{id}/decide` `{action, note?, post_open_shift: bool = true}` → lock; approver must `can_approve_changes_for` the user, not self unless admin. Approve: if the entry changed since request (template differs) → 409; set the user's cell to PUBLISHED week-off (`is_week_off=True`, template cleared), `record_change(reason=f"Shift give-away #{id}: {reason}")`, notify. If `post_open_shift` → create an `OpenShift` (slots 1, same template/date, department = user's department, `created_by_id` = approver, `source_drop_id`) using the Task 3 service function (so eligible employees are notified). Reject → notify.

**Tests:** happy path with and without open shift, ownership, past date, non-published entry, approver scope, self-approval, stale entry 409.

- [ ] TDD → migration → commit `feat(roster): shift give-away requests`.

---

### Task 5: ICS calendar feed (backend)

**Files:** Create `models/calendar_feed.py`, `services/ics.py`, `endpoints/calendar_feed.py`, migration, `tests/test_calendar_feed.py`. Modify `api.py`.

**Model** `calendar_feed_token`: `id`, `user_id` (unique, FK cascade), `token_hash` String(64) unique (sha256 hex of the raw token), `created_at`, `last_used_at` nullable.

**Pure renderer** `render_ics(events, *, cal_name: str, now: datetime) -> str`:
- `events`: list of `IcsEvent(uid, start: datetime, end: datetime, summary, description)` with NAIVE wall-clock datetimes → emitted as floating `DTSTART:20300105T090000`.
- `BEGIN:VCALENDAR`, `VERSION:2.0`, `PRODID:-//HRMS//Roster//EN`, `CALSCALE:GREGORIAN`, `X-WR-CALNAME`, each `VEVENT` with `UID`, `DTSTAMP` (UTC `Z`), `DTSTART`, `DTEND`, `SUMMARY`, `DESCRIPTION`.
- RFC 5545: CRLF line endings, escape `\\`, `;`, `,`, newline (`\n`), fold lines > 75 octets (continuation lines start with a single space; do not split a UTF-8 multibyte char).
- Overnight shifts: `end` on the next day.

**Endpoints:**
- Authenticated (mounted under `/roster`, attendance-gated like the others): `GET /roster/my/calendar-feed` → `{active: bool, created_at}`; `POST /roster/my/calendar-feed` → rotates: `secrets.token_urlsafe(32)`, store hash, return `{url}` built from `request.base_url` + `/api/v1/calendar/{token}.ics` (only time the raw token is shown); `DELETE /roster/my/calendar-feed` → delete row (204).
- Public router `calendar_feed.public_router` mounted at `/calendar` with NO dependencies: `GET /calendar/{token}.ics` → hash lookup (constant-time not needed since lookup is by hash); 404 if missing or the user is inactive; events = the user's PUBLISHED working entries with a template for `[today−30, today+90]` (one query + templates); `UID = f"roster-{entry.id}@hrms"`; `SUMMARY = template.name`; update `last_used_at` (best-effort). Response `text/calendar; charset=utf-8`, header `Cache-Control: private, max-age=900`.

**Tests:** pure: escaping, folding (75 octets, multibyte), overnight end date, CRLF; API: create → fetch feed without auth → contains published shift, excludes drafts and week-offs; rotate invalidates old token (404); delete → 404; inactive user → 404.

- [ ] TDD → migration → commit `feat(roster): personal ICS calendar feed`.

---

### Task 6: Employee self-service UI

**Files:** Create `frontend/src/components/my-schedule/` with `my-schedule-api.ts` (types + calls), `availability-panel.tsx`, `swap-panel.tsx` (+ `swap-dialog.tsx`), `open-shifts-panel.tsx`, `giveaway-dialog.tsx`, `calendar-feed-card.tsx`. Modify `frontend/src/components/my-shift-view.tsx` (mount the panels — e.g. a tab strip "Week | Availability | Swaps | Open shifts | Calendar" below the existing week view), `frontend/src/api/endpoints.ts`, `index.css` (only if a needed utility is missing).

Behaviour:
- **Availability:** list own rules (human text: "Unavailable every Tue", "Prefers Night on Sat (from 1 Mar)"), add dialog (kind, recurring weekday vs specific date, optional shift, optional bounds, note), delete with confirm.
- **Swaps:** from a day in the existing week strip that has a published shift, "Swap" opens `swap-dialog`: pick colleague from `/roster/swaps/candidates?date=` (shows their shift that day), optional different return date (then candidate list shows their shift on that date too), reason. List incoming (Accept/Decline) and outgoing (Cancel) with status badges.
- **Give away:** from a future published shift day, "Give away" → reason → POST `/roster/drops`; list own drop requests with status + Cancel.
- **Open shifts:** list `/roster/open-shifts/available` (date, shift, dept, note, my claim status) with Claim / Withdraw.
- **Calendar:** shows active state; "Create link"/"Regenerate" → shows URL once with a Copy button (`navigator.clipboard.writeText`, fall back to selecting the input) and instructions ("Subscribe by URL in Google Calendar / Outlook / Apple Calendar"); "Turn off".
- All errors shown with `errMsg`; busy states on buttons; a11y labels; refresh lists after each action.

- [ ] Implement → twcheck all touched files → tsc (no new errors) → commit `feat(my-shift): availability, swaps, give-away, open shifts, calendar feed`.

---

### Task 7: Scheduler UI — requests, open shifts, availability overlay

**Files:** Create `frontend/src/components/roster/requests-view.tsx` (swap approvals with `/check` warnings, drop approvals with "post as open shift" checkbox default on), `open-shifts-panel.tsx` (list + claims decide + cancel) and `open-shift-dialog.tsx` (create), `use-availability.ts`. Modify `roster-planner.tsx` (view toggle becomes Planner | Requests | Delegations — Requests visible to anyone who can manage; badge with pending count; availability overlay: a small marker/tooltip on cells where the employee is unavailable or prefers a shift, using `GET /roster/availability` for the visible window+department), `roster-api.ts`, `endpoints.ts`.

Also: in the coverage strip, an "under" cell gets a "Post open shift" action prefilled with that date/template/department.

- [ ] Implement → twcheck → tsc → commit `feat(roster): scheduler requests view, open shifts, availability overlay`.

---

### Task 8: Auto-fill suggestions

**Files:** Create `backend/app/services/autofill.py`, `endpoints/roster_autofill.py`, `tests/test_autofill.py`, `frontend/src/components/roster/autofill-dialog.tsx`. Modify `api.py`, `schemas/roster.py`, `roster-planner.tsx`, `roster-api.ts`, `endpoints.ts`.

**Pure algorithm:**

```python
@dataclass(frozen=True)
class Slot:              # one requirement instance
    day: date
    template_id: int
    department: Optional[str]
    location: Optional[str]
    need: int            # min_headcount minus already-assigned

@dataclass(frozen=True)
class Suggestion:
    user_id: int
    day: date
    template_id: int
    score: float
    reasons: tuple[str, ...]   # e.g. ("preferred shift", "fewest nights")

def suggest(*, employees, days, templates, slots, existing_cells, leave_days, availability, rules, window_start) -> tuple[list[Suggestion], list[Slot]]:
```
- `employees`: objects with `user_id`, `department`, `location`.
- `existing_cells`: `{(user_id, day): (template_id|None, is_week_off)}` (draft + published) — never overwritten; a user with any cell that day is not a candidate.
- Process days ascending, and within a day slots ordered by template start time. For each slot pick `need` candidates: matching dept/location (None = any), no cell that day, not on leave, `not availability.blocks(template)`, and adding the span does not create a NEW rule violation (run `schedule_rules.check_rules` on the candidate's spans incl. already-suggested ones; compare violation counts before/after).
- Score (higher better): `+3` preferred template that day; `−1 × shifts assigned to the candidate in the window so far` (fair load); for overnight templates `−1 × nights so far`; for Sat/Sun `−1 × weekend shifts so far`. Ties → lower user_id. Deterministic.
- Returns suggestions and the residual unfilled slots.

**Endpoint** `POST /roster/autofill/preview` `{start, end, department?}` (≤ 31 days, 400): employees = `manageable_subset` active employees (filtered by department); slots from active coverage requirements matching the window weekdays (reuse `visible_requirements` / insights loaders), `need` = `min_headcount` − current matching working cells. Returns `{suggestions: [{employee_id, employee_name, work_date, shift_template_id, shift_name, reasons}], unfilled: [{work_date, shift_template_id, shift_name, department, missing}]}`.

**Apply:** frontend posts accepted suggestions to the existing `POST /roster/bulk` as **draft** entries without overwrite (read the bulk schema for the exact payload); show the bulk result (written/skipped).

**UI:** "Auto-fill" button next to "Copy previous" (only when the caller can manage); dialog: runs preview for the current window + department, groups by day, each row with checkbox (default checked) and reasons, unfilled list at the bottom, "Apply N as drafts".

**Tests:** pure: fills need exactly; skips leave/unavailable/existing cells; respects min rest (night then early next day not suggested); fairness spreads nights across employees; preferred wins ties; deterministic; API: scope (delegate only gets own scope), window cap.

- [ ] TDD → commit `feat(roster): auto-fill suggestions`.

---

### Task 9: Live operations board + no-show detection

**Files:** Create `models/no_show.py`, `services/live_ops.py`, `endpoints/roster_live.py`, migration, `tests/test_live_ops.py`, `frontend/src/components/live-board.tsx`. Modify `services/time_rules.py` (`schedule.no_show_minutes` default `"30"`, cap 240, 0 = off — add to `TIME_RULE_DEFAULTS` and `SCHEDULE_INT_CAPS`; show it in the Scheduling rules card in `workforce/time-rules-tab.tsx`), `services/scheduler.py` (job), `api.py`, `App.tsx`, `sidebar.tsx`, `endpoints.ts`.

**Pure classifier:**

```python
class LiveStatus(str, enum.Enum):
    OFF = "off"; ON_LEAVE = "on_leave"; UPCOMING = "upcoming"; NOT_ARRIVED = "not_arrived"
    NO_SHOW = "no_show"; ON_SHIFT = "on_shift"; COMPLETED = "completed"

def classify(*, now: datetime, start: Optional[datetime], end: Optional[datetime], grace_in: int,
             punch_in: Optional[datetime], punch_out: Optional[datetime], on_leave: bool,
             no_show_minutes: int) -> tuple[LiveStatus, int]:   # (status, late_minutes)
```
Rules: no shift → OFF (or ON_SHIFT/COMPLETED if punched anyway); on_leave → ON_LEAVE; punched in & not out → ON_SHIFT (late_minutes = max(0, punch_in − (start+grace))); punched out → COMPLETED; no punch: now < start → UPCOMING; start ≤ now < start+no_show (or no_show==0) → NOT_ARRIVED; ≥ start+no_show and now < end → NO_SHOW; after end with no punch → NO_SHOW. All datetimes UTC-aware; shift `start`/`end` built from `work_date` + template times with tz=UTC (overnight end +1 day) — same convention as `shift_resolver`.

**Board loader** `async def live_board(db, user_ids, now) -> list[LiveRow]`: for each user consider the shift of `today` and an overnight shift of `yesterday` that is still running (`now < end`); pick the running/most relevant one; batch-load effective shifts (`effective_shifts_for_range`), `Attendance` rows for those work_dates, approved leave days, names/department/location. Return rows `{user_id, name, department, location, work_date, shift_name, start, end, status, late_minutes, punch_in, punch_out}`.

**Endpoint** `GET /roster/live?department=&location=` → `manageable_subset` active employees (roster admin: all active), filters applied; response `{now, counts: {status: n}, rows}`; cap 2000 employees (400 with message asking to filter).

**No-show job:** model `no_show_alert` (`id`, `user_id`, `work_date`, `shift_template_id`, `created_at`; unique `(user_id, work_date)`). `async def no_show_job(session) -> dict` — if `schedule.no_show_minutes` is 0 return `{"skipped": "disabled"}`; else compute board for all active employees with a working shift today/overnight-yesterday; for each `NO_SHOW` with no alert yet: insert alert (IntegrityError → skip, savepoint), notify the employee ("You haven't punched in for {shift} at {HH:MM}") and their schedulers = employee's manager (`Employee`/`User` manager field — check which exists) ∪ users with an active delegation covering them ∪ (roster admins only if that set is empty). Register `JobSpec(name="roster_no_show_alerts", display_name="Roster no-show alerts", default_cadence_cron="*/5 * * * *", fn=no_show_job)`. Board marks rows that have an alert.

**UI** `live-board.tsx` (sidebar "Live Board", group "Time & Attendance", same roles as `roster-planner`): summary chips per status (click to filter), department/location filters, table (name, shift, start–end, status badge, late minutes, punch in/out), auto-refresh every 60 s with "updated HH:MM:SS", manual refresh, empty state.

**Tests:** pure classify table-driven (each branch, overnight from yesterday, grace boundary, no_show 0); loader with DB rows; job creates one alert per user/day (idempotent on rerun), notifies manager, disabled when 0; endpoint scoped.

- [ ] TDD → migration → commit `feat(roster): live operations board and no-show alerts`.

---

### Task 10: Pay linkage

**Files:** Modify `backend/app/services/overtime.py`, `backend/app/api/v1/endpoints/overtime.py`, `backend/app/api/v1/endpoints/attendance.py`, `backend/app/services/time_rules.py`, `backend/app/services/scheduler.py`; tests in `backend/tests/test_overtime.py` (extend) and new `tests/test_pay_linkage.py`.

Current gaps (verified):
- `_resolve_one` (endpoints/overtime.py ~662) uses the `Attendance.shift_template_id` snapshot; `classify_day_type` only knows `shift.weekly_offs`, so a **published roster week-off** worked is classified WEEKDAY (no `weekly_off_multiplier`), and a roster change after punch is ignored.
- Comp-off (`_maybe_create_comp_off_accrual`, attendance.py ~259) is only for holidays.
- OT/night entries are only created by manual `POST /overtime/recompute`.

Changes:
1. `classify_day_type(work_date, shift, holiday_dates, *, is_week_off: Optional[bool] = None)` — when `is_week_off` is given it overrides the `weekly_offs` check (holiday still wins). Existing callers unchanged.
2. In `_resolve_one`: `eff = await effective_shift_on(db, user_id, work_date)`. Baseline shift = `eff.shift` when `eff.source == "roster"` (published roster is authoritative), else the snapshot shift, else `eff.shift`. Pass `is_week_off=eff.is_week_off` to `classify_day_type`. Rule picking (`_pick_ot_rule` / `_pick_night_rule`) uses the baseline shift's id. To avoid N queries in `recompute`, add an optional `eff: Optional[EffectiveShift]` parameter and batch with `effective_shifts_for_range` in the recompute loop.
3. Extract the body of `POST /overtime/recompute` into `async def recompute_range(db, start, end, user_ids=None, requested_by_id=None) -> RecomputeResult-like dict` (endpoint calls it; behaviour unchanged). Register a nightly job `overtime_recompute_yesterday` (`"30 1 * * *"`) that recomputes yesterday (UTC) for rows with `punch_out_time` set. If `requested_by_id` is required downstream, use `None`-safe handling (read the code; for auto-approved entries no approver is needed).
4. Week-off comp-off: time rule `attendance.weekoff_comp_off_enabled` (default `"0"`, validated `0|1`, shown in Time Rules UI next to the absence-LOP toggle — find where that toggle is rendered). In `_maybe_create_comp_off_accrual`: when no holiday matches and the rule is on and `effective_shift_on(...).is_week_off`, create the accrual with `holiday_name="Week-off work"` using the same threshold/approval flow.
5. Night allowance stays punch-window based (already correct); only rule selection changes via (2).

**Tests:** `classify_day_type` override; OT on a rostered week-off uses `weekly_off_multiplier`; roster shift changed after punch → baseline from roster; recompute endpoint parity (existing tests stay green); nightly job function processes yesterday only; comp-off on week-off when enabled, not when disabled, holiday path unchanged.

- [ ] TDD → commit `feat(payroll): roster-aware OT day type, week-off comp-off, nightly OT recompute`.

---

### Task 11: Phase verification (controller, not a subagent task)

1. Full backend suite: `docker exec erp-united-exploration-dev-backend-1 python -m pytest tests app/tests -q --ignore=tests/test_admin_auth.py --ignore=tests/test_leave_flows.py` — only the 2 known `test_hr_employees` failures allowed.
2. tsc count ≤ 166, zero errors in touched files; twcheck on all new/modified TSX.
3. Migration chain: single head; downgrade to `d4e5f6a7b8c9` and back up.
4. API E2E QA agent (multi-role scenarios for every endpoint above, against the live stack, own date range) + browser E2E QA agent (Playwright: employee self-service, scheduler requests, open shifts, auto-fill, live board) → fix findings → re-run.
5. Final whole-branch code review → fix → update memory `roadmap-v2.md`.
