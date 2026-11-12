# Roadmap v2 — Phase 2 (Emergency & Last-Minute Operations) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement spec §2 (emergency leave, coverage-gap engine, emergency rescheduling, on-call, approvals that don't stall, emergency broadcast & safety, attendance fallbacks) on top of the Phase 1 scheduling stack.

**Architecture:** Same layering as Phase 1: new models in their own files + linear migrations, business rules in pure functions with unit tests, thin routers, roster writes only through `services/roster.py` (`upsert_entry`, `record_change`, `notify*`), scope via `manageable_subset` / `publishable_subset` / `approvable_subset`, races handled with `lock_row` / `lock_user_rows` / `guard_conflicts` / `commit_or_409` (`endpoints/roster_common.py`). Each task is a vertical slice (backend + UI + tests).

Spec: `docs/superpowers/specs/2026-11-12-roadmap-v2-shift-ops-and-competitive-gaps.md` §2.
Branch: `feature/roadmap-v2-phase2`, stacked on `feature/roadmap-v2-phase1b`. Migration head at start: `d5a7c9e1b3f2`.

**Product decisions taken (spec open decisions #3, #5 and gaps):**
- Broadcast channels: in-app + email + SMS through the existing `notifications_delivery` providers (SMS only sends when an SMS provider is configured). WhatsApp and mobile push are deferred to Phase 3 (no device-token infra yet). Emergency broadcasts bypass quiet hours.
- Emergency leave without proof: converts to LOP after `leave.emergency_proof_days` (default **3**, 0 = no proof required) days past the leave end date.
- Emergency leave may be applied same-day or back-dated up to `leave.emergency_backdate_days` (default **3**).
- Schedule lock window `schedule.lock_days` (default **0 = off**). Inside the window, published cells can only be changed by roster admins or delegates with the new `can_emergency_override` flag; reason mandatory; employee must acknowledge.
- Call-back compensation policy `schedule.callback_compensation` = `none` | `comp_off` | `allowance` (default `none`), allowance amount `schedule.callback_allowance_amount`.
- Approval SLA `approvals.sla_hours` (default **48**, 0 = off). Escalation: overdue step → approver's manager if any, else HR role; notified.
- Offline punch is **not** built (deliberate design decision recorded in `frontend/public/sw.js`; revisit in the Phase 3 native app). One-tap approve from push is Phase 3.

## Environment (all tasks)

Identical to Phase 1B (`docs/superpowers/plans/2026-11-12-roadmap-v2-phase1b.md` "Environment (all tasks)") — read it. Key points:
- Docker project `erp-united-exploration-dev` (backend `-backend-1` port 8005 /app auto-reload; frontend `-frontend-1` 5173; db `-db-1`).
- Tests: `docker exec erp-united-exploration-dev-backend-1 python -m pytest tests/<file> -q -p no:cacheprovider`; real dev DB; fixtures like `tests/test_open_shifts.py` (uuid suffix, `create_app()` + `dependency_overrides[deps.verify_attendance]`), teardown leaves zero rows (`tests/_cleanup.py`). Never notify/alter real users from tests (scope jobs with `user_ids=` params).
- Migrations: linear; `down_revision` = current head; verify up → downgrade -1 → up. MariaDB DDL non-transactional. `LeaveStatus` is a DB Enum (adding values needs ALTER) — prefer new boolean/date columns over new enum values.
- Time rules live in `services/time_rules.py` (`TIME_RULE_DEFAULTS`, validation in `set_time_rules`); UI in `frontend/src/components/workforce/time-rules-tab.tsx`.
- Rich notifications (email/SMS) via `services/notifications_delivery.notify(...)` + `EVENT_CATEGORY_MAP` entry + template seed in `services/notifications_seed.py`; in-app-only via `roster_svc.notify_many`.
- Jobs: `services/scheduler.py` `register_job(JobSpec(...))`; job fns accept injectable `now` / `user_ids` for tests.
- Frontend: NO Tailwind build — check classes with `cd frontend && python3 /private/tmp/claude-501/-Users-akshayghosh-ReactNative-InnoCoreLabs-HRMS-White-Label/994b71d9-53c3-43ba-bd64-b7c371023999/scratchpad/twcheck.py <files>` and add missing utilities inside `@layer utilities` at the end of `frontend/src/index.css`. tsc baseline **164** (no new errors). Navigation: `App.tsx` renderContent + getPageTitle + `sidebar.tsx` MenuItem. Reuse `errMsg`/`todayIso`/`parseServerDate` (`schedule-delegations-utils.ts`), `InlineConfirm` (`my-schedule/inline-confirm.tsx`).
- Browser verification with Playwright helpers in `/private/tmp/claude-501/-Users-akshayghosh-ReactNative-InnoCoreLabs-HRMS-White-Label/994b71d9-53c3-43ba-bd64-b7c371023999/scratchpad/e2e_ui/` (`lib.js`, prior `t*.js` + seed/clean scripts). Look at screenshots. Clean up all data.
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Never push.

---

### Task 0: Leave approval consistency + leave notifications (pre-existing bugs)

- `POST /approvals/{id}/action` (`endpoints/approvals.py`) approves leave without debiting `LeaveBalanceLedger`, unlike `POST /leave/approvals/{item_id}/action` (`endpoints/leave.py`). Extract one service `services/leave_approval.py: apply_leave_decision(db, item, leave, actor, approve: bool, comment)` (step advance, final status, ledger debit exactly once, audit) and call it from both endpoints (keep the admin-override behaviour of approvals.py). Test: approving via either endpoint debits once; double approval cannot double-debit.
- Notify via `notifications_delivery.notify`: approver(s) on apply / on-behalf (event `leave_submitted` / `approval_pending`), requester on final approve/reject (`leave_approved` / `leave_rejected`). Templates already seeded for some — add missing seeds.
- [ ] TDD → commit `fix(leave): single approval path with ledger debit; leave notifications`.

### Task 1: Emergency leave

- `LeaveRequest` new columns: `is_emergency` (bool, default False), `proof_due_date` (Date, nullable), `proof_submitted_at` (DateTime, nullable), `converted_to_lop_at` (DateTime, nullable). Time rules `leave.emergency_backdate_days` (default 3, 0..31), `leave.emergency_proof_days` (default 3, 0..60).
- `POST /leave/apply` and `/apply-on-behalf` accept `is_emergency`. Non-emergency requests keep current rules. Emergency: `start_date` ≥ today − backdate_days (400 otherwise); `requires_medical_cert_after` attachment check is deferred (sets `proof_due_date = end_date + proof_days` when proof is required — i.e. when the leave type's cert threshold applies or proof_days > 0 and no attachment yet).
- On submit (not only approval): mark the employee's PUBLISHED working roster cells in [start, end] ∩ [today, ∞) as uncovered by creating coverage gaps (Task 3 service `open_gap(...)`, source `emergency_leave`) and alert schedulers (`schedule_approver_ids`) — Task 1 depends on Task 3's model; implement Task 3 first if convenient, otherwise create the gap service skeleton here.
- `POST /leave/{id}/proof` (owner or HR) uploads/links an attachment (reuse `/leave/attachments` upload) → sets `attachment_url`, `proof_submitted_at`.
- Job `emergency_leave_proof_check` (daily): approved emergency leaves with `proof_due_date < today`, no proof, not yet converted → `converted_to_lop_at = now`; refund ledger `used` for paid types; payroll treats converted leave days as LOP (find where unpaid leave → LOP in `payroll.py` ~450 and include converted leaves); notify employee + HR. Idempotent.
- UI: employee leave form "Emergency (same-day/back-dated)" toggle; "Proof due by <date>" badge + upload action in leave history; HR leave view shows emergency badge, proof status, LOP-converted state.
- [ ] TDD → migration → commit `feat(leave): emergency leave with proof follow-up and LOP conversion`.

### Task 2: "Running late" notice

- Model `late_notice` (`user_id`, `work_date`, `expected_at` DateTime UTC, `reason` String(255), `created_at`; unique (user_id, work_date) — re-posting updates).
- `POST /roster/my/running-late {minutes_late | expected_at, reason}` for today's (or running overnight) shift only; notifies the employee's schedulers (`live_ops._alert_recipients`). `GET /roster/my/running-late`.
- Live board: row gains `late_notice_eta`; a NO_SHOW before `expected_at + no_show_minutes` shows as `running_late` (new LiveStatus) and the no-show job doesn't alert until then.
- UI: My Shift today card "Running late" button (minutes picker + reason); Live Board shows "Running late · ETA HH:MM UTC".
- [ ] TDD → migration → commit `feat(roster): running-late notices`.

### Task 3: Coverage gap engine

- Model `coverage_gap` (`work_date`, `shift_template_id`, `department`, `location`, `absent_user_id` nullable, `source` String(20): `emergency_leave|no_show|drop|sick_call|manual`, `source_id` nullable, `status` `open|filled|dismissed`, `open_shift_id` nullable, `filled_by_user_id`, `resolved_by_id`, `resolved_at`, `note`, `created_at`; unique (absent_user_id, work_date, source) where absent_user_id not null — handle in code).
- Service `services/coverage_gaps.py`: `open_gap(db, *, work_date, shift_template_id, department, location, absent_user_id, source, source_id)` (idempotent, notifies schedulers in-app), `suggest_replacements(db, gap, limit=10)` ranking eligible employees — same eligibility as open shifts (`open_shifts.eligibility_matrix`) plus rest/consecutive/weekly rules (reuse `autofill._breaks_rules`), monthly OT cap headroom (`OvertimeRule.monthly_ot_cap_minutes` vs approved OT minutes this month), fewest scheduled hours in the pay period; returns score + reasons.
- Triggers: Task 1 (emergency leave), no-show job (`live_ops.no_show_job` → `open_gap(source='no_show')` for the alerted row), approved give-away with `post_open_shift` false (source `drop`), manual (`POST /roster/gaps` with sick_call/manual).
- Endpoints `/roster/gaps`: list (scoped by department/scope; filters status/date), `GET /{id}/suggestions`, `POST /{id}/assign {user_id}` (publishes the cell for the replacement with history reason `Coverage gap #id`, notifies replacement + absentee's schedulers; re-validates eligibility; locks), `POST /{id}/broadcast {auto_confirm}` (creates an open shift via `create_open_shift(..., exclude_user_ids={absent})`, links `open_shift_id`; when that open shift fills, mark the gap filled — hook in `confirm_claim`), `POST /{id}/dismiss {note}`.
- UI: planner Requests view gets a "Coverage gaps" section (badge count) with suggestions drawer (ranked list + reasons) → Assign / Broadcast / Dismiss; Live Board no-show rows link to their gap.
- [ ] TDD → migration → commit `feat(roster): coverage gap engine with replacement suggestions`.

### Task 4: Lock window + emergency rescheduling + acknowledgement + call-back compensation

- Time rules `schedule.lock_days` (0..30, default 0), `schedule.callback_compensation` (`none|comp_off|allowance`), `schedule.callback_allowance_amount` (≥0, default 0).
- `ScheduleDelegation.can_emergency_override` (bool, default False) + schema/endpoint/UI checkbox.
- Enforcement in every roster write path that changes a PUBLISHED cell dated within [today, today+lock_days] (entries PATCH/DELETE/POST, bulk, rotation apply, copy, publish of drafts over live cells, swaps/drops/open-shift/gap assignment approvals): allowed only for roster admins or delegates with `can_emergency_override` for that employee; reason required; history row flagged `is_emergency=True` (new column on `roster_entry_history`). Self-service flows initiated by employees (swap/drop approved by an approver with override rights) follow the approver's rights. Centralise in `services/roster.py` (`lock_guard(db, actor, cells)`).
- Acknowledgement: model `schedule_change_ack` (`history_id`, `user_id`, `acknowledged_at` nullable, `created_at`); created for each emergency change; `GET /roster/my/acks` (pending), `POST /roster/my/acks/{id}`; schedulers see unacknowledged changes in Requests view.
- Call-back: when an emergency change turns an employee's off/week-off cell into a working shift, record compensation per policy: `comp_off` → `CompOffAccrual` (holiday_name "Call-back", reuse approval flow from `attendance._maybe_create_comp_off_accrual` — extract a helper), `allowance` → `ShiftAllowanceEntry(kind='callback')` (Task 5 table — implement Task 5 first or create the table here).
- UI: planner shows lock-window shading on cells; reason dialog marks "Emergency change"; My Shift shows "Schedule changed — Acknowledge" banner.
- [ ] TDD → migration → commit `feat(roster): lock window, emergency override, change acknowledgement, call-back compensation`.

### Task 5: On-call / standby roster + allowance payroll injection

- Models: `on_call_rule` (`name` unique, `payout_model` flat_per_day|hourly, `flat_amount`, `hourly_rate`, `is_active`), `on_call_assignment` (`user_id`, `work_date`, `start_time`, `end_time`, `is_overnight`, `rule_id`, `note`, `created_by_id`; unique (user_id, work_date)), `shift_allowance_entry` (`user_id`, `work_date`, `kind` on_call|callback, `amount`, `minutes`, `rule_id`, `source_id`, `payroll_run_id` FK SET NULL, `computed_at`; unique (user_id, work_date, kind)).
- Endpoints: `/roster/on-call/rules` CRUD (roster admin), `/roster/on-call` list/create/delete for managed employees (window ≤ 62 days), `GET /roster/my/on-call`. Allowance computation: on create/delete keep `shift_allowance_entry(kind='on_call')` in sync for dates ≥ today; never touch entries with `payroll_run_id`.
- Payroll: inject `shift_allowance_entry` (payroll_run_id NULL, work_date in month) in `generate_draft` like night allowance — new `PayrollLine.allowances` keys `on_call` and `callback`; add to gross; stamp `payroll_run_id`; include in the line editor gross rebuild (~1056) so manual edits don't drop them. Parity test: a payroll run with no on-call/callback entries produces identical lines.
- UI: planner "On-call" row/strip per employee (toggle per day with rule select) or a dedicated On-call panel; My Shift shows on-call days.
- [ ] TDD → migration → commit `feat(roster): on-call roster and allowances in payroll`.

### Task 6: Approvals that don't stall

- SLA: set `ApprovalItem.due_date` at creation (all creators of ApprovalItem — find them) = now + `approvals.sla_hours`; for chain engine use `ChainedApprovalStepInstance` created/updated time + SLA (add `due_at` column).
- Job `approval_escalation` (hourly): pending steps past due → escalate: legacy steps with `approver_id` → set `approver_id` to that approver's manager if active, else clear `approver_id` and set `role_id`=HR; chain steps → reassign `approver_user_id` similarly; record `escalated_at`/`escalated_from_id` (new columns), notify new approver + original. Idempotent; escalate at most once per SLA period.
- Out-of-office: model `approver_delegation` (`user_id`, `delegate_id`, `starts_on`, `ends_on`, `note`, `created_at`, `revoked_at`); active OOO when today in range, OR automatically when the approver has APPROVED leave today and an OOO delegation exists with no dates (standing delegate). Inbox queries (legacy `/approvals/inbox`, `/leave/approvals/inbox`, chain `/approval-chains/my-queue`) include items assigned to users who have delegated to me; action endpoints accept delegate acting (audit `acting_for_user_id`); SoD still applies to the delegate.
- Bulk: `POST /approvals/bulk-action {items: [{kind: 'legacy'|'chain', id}], action, comment}` → per-item result list using the same services (Task 0's leave service for leave).
- UI: approvals-view: overdue badge, multi-select + bulk approve/reject; profile "Out of office" card (delegate picker, dates).
- [ ] TDD → migration → commit `feat(approvals): SLA escalation, out-of-office delegation, bulk actions`.

### Task 7: Emergency broadcast & "mark me safe"

- Permission `broadcast send` (migration grants to HR + Super Admin, same pattern as `d8e9f0a1b2c3_grant_attendance_edit.py`).
- Models `broadcast` (`title`, `message`, `severity` info|warning|critical, `audience` all|location|department|on_shift, `audience_value`, `requires_ack`, `safety_check`, `created_by_id`, `created_at`, `closed_at`), `broadcast_recipient` (`broadcast_id`, `user_id`, `read_at`, `acked_at`, `safety_status` safe|need_help|null, `safety_note`, `responded_at`; unique (broadcast_id, user_id)).
- Audience resolution: all active employees; by `Employee.location`; by department; on_shift = rows of `live_ops.live_board` with status on_shift/not_arrived/running_late now.
- Send via `notifications_delivery.notify` (event `emergency_broadcast`, category `emergency` — add to EVENT_CATEGORY_MAP and seeds; emergency category bypasses quiet hours and user opt-outs for in-app+email+SMS — implement the override in the delivery layer narrowly for this category).
- Endpoints: `POST /broadcasts`, `GET /broadcasts` (sender view), `GET /broadcasts/{id}` (dashboard counts + recipient list with filters), `POST /broadcasts/{id}/close`, `GET /broadcasts/my` (active), `POST /broadcasts/{id}/ack`, `POST /broadcasts/{id}/safety {status, note}`.
- UI: admin "Emergency broadcast" page (compose + history + live dashboard auto-refresh); app-wide banner/modal for unacked active broadcasts with Acknowledge / I'm safe / Need help.
- [ ] TDD → migration → commit `feat(safety): emergency broadcasts with acknowledgement and mark-safe`.

### Task 8: Emergency profile data + night-shift compliance

- Employee columns `gender` (String(16) nullable: female|male|other|undisclosed), `blood_group` (String(4) nullable, validated A+|A-|B+|B-|AB+|AB-|O+|O-); model `employee_emergency_contact` (`user_id`, `name`, `relation`, `phone`, `is_primary`, `created_at`; max 3 per user).
- Endpoints: self `/me/emergency-contacts` CRUD + `/me/safety-profile` (gender, blood group); HR can edit for any employee; managers/schedulers can read for their scope (`GET /roster/team-contacts?department=` — name, phone, emergency contacts, blood group).
- Night-shift consent (India): model `night_shift_consent` (`user_id`, `consent_given`, `valid_from`, `valid_to`, `recorded_by_id`, `document_url`, `note`, `created_at`); HR records. Roster insights violation `night_consent_missing` when a female employee is scheduled on an overnight template (or a template overlapping 22:00–06:00) without active consent. `RosterEntry.transport_required` (bool) settable from the planner cell (scheduler) and shown on Live Board / My Shift.
- UI: profile "Emergency info" card; HR employee view; manager Team contacts panel (phone shown as text, `tel:` link beside it); planner cell transport toggle + consent violation icon.
- [ ] TDD → migration → commit `feat(safety): emergency contacts, blood group, night-shift consent and transport flag`.

### Task 9: Attendance fallback — supervisor bulk mark

- `POST /attendance/bulk-mark {work_date, user_ids[], punch_in_time, punch_out_time?, reason ≥ 5}` — allowed for `attendance edit` holders (any employee) or schedulers for their `manageable_subset` (only for dates within [today−2, today]); per-user results (created / skipped existing / out of scope / locked by payroll via `assert_attendance_editable`); mode `manual_bulk`, `edited_by_id`; audit each (`BULK_MARK_ATTENDANCE` with reason). Shift attribution consistent with manual entry (`hr.py create_manual_attendance`).
- UI: Live Board multi-select rows (not_arrived/no_show) → "Mark present (system outage)" dialog with times + reason; result summary.
- [ ] TDD → commit `feat(attendance): supervisor bulk mark for outages`.

### Task 10: Phase verification (controller)

1. Full backend suite (only the 2 known `test_hr_employees` failures allowed), tsc ≤ 164, migration chain up/down/up.
2. API E2E agent + browser E2E agent across all Phase 2 features (multi-role), fix findings, re-run.
3. Final whole-branch review → fix → memory update → continue to Phase 3.
