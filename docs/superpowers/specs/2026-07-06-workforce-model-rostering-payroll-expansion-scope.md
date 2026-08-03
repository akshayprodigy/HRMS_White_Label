# Scope of Work — Workforce Model, Rostering & Payroll Expansion

**Date:** 2026-07-06
**Product:** ERP United / HRMS White-Label
**Status:** Draft for approval
**Author:** Engineering (scoping)

---

## 1. Purpose

This document scopes a set of new capabilities requested for the HRMS, added **on top of the already-developed platform**. It maps every requirement to what already exists in the codebase, defines the delta to build (backend + frontend), lists acceptance criteria, and proposes a phased delivery plan.

The guiding finding from a codebase audit: **most of these requests already have working foundations.** Of 13 workstreams, only 3 are truly greenfield (roster grid, late-mark rules engine, custom letter-template upload). The rest are extensions of existing models and services. There are two **cross-cutting gaps** — the concept of a "functional head," and a first-class **"Accounts" finance role** — that several features depend on, so both are built first as foundations.

## 2. Locked architecture decisions

Confirmed with the product owner before scoping:

| Decision | Choice |
|---|---|
| **Employment types** | **Configurable type master.** HR defines each type in Settings; each type carries its own payroll profile, leave policy, and salary template. Not a hardcoded enum. |
| **Salary structure** | **Structured component + template master.** An earnings/deductions component master plus salary templates that Accounts define per type (or per employee). Replaces reliance on flat salary columns. |
| **Functional head** | **Head (and optional deputy) on Department / Functional Area.** The head governs their team's roster, revisions, and approvals. |
| **Rostering** | **Full weekly/monthly roster planner** built now (not phased down to a lighter version). |
| **Accounts role & scope** | New **Accounts** persona is the **final payment gate for all outflows** — payroll, expense reimbursements, salary advances, and travel claims. Designed as a foundation so every outflow routes through it. |
| **Payment execution** | **Status-flag only** — Accounts marks "payment done" (with a note) after approving; the system does **not** generate a bank file or move money. The actual bank transfer happens outside the system. |
| **Tax-config ownership** | **Accounts owns income-tax / TDS** config (rates, slabs, min/max, caps). **HR retains PF / ESI / PT** and the salary-structure caps (HRA %, component min/max). |

## 3. Current-state audit (what already exists)

Verbatim summary of the audit, so the delta is honest:

- **Employment type:** `Employee.employment_type` exists (`permanent`/`contractual`/`advisor`) and **payroll already branches on it** — contractual/advisor get flat 10% TDS with no PF/ESI/PT. `probation_end_date` + `confirmation_date` fields exist. No on/off-payroll flag, no per-type leave, no structured salary per type.
- **Salary:** Flat columns on `Employee` (`salary`, `hra`, `conveyance_allowance`, `other_allowance`, `voluntary_pf`). Point-in-time structured snapshots exist only inside `SalaryRevision`. No component/template master.
- **Statutory caps:** The modern engine (`app/services/payroll_engine.py::compute_statutory`) **already caps PF at the ₹15k ceiling and ESI at ₹21k**, effective-dated in `StatutoryConfig`. The **legacy** `salary_calculator.py` (still used for contractors + earnings breakdown) is **uncapped**.
- **Payroll run:** Batch over **all active employees only** (`generate_draft` in `endpoints/payroll.py`). Stages: DRAFT → ATTENDANCE_LOCKED → LEAVES_LOCKED → DRAFT_GENERATED → FINALIZED → PUBLISHED. Lines editable **only in DRAFT_GENERATED**, only 4 fields (arrear/incentive/guest_house/tds), **no reason field, no audit log** on the edit.
- **Government forms:** Form 16 (per-employee **and** bulk via optional `employee_ids`, per-FY) **exists**. Form 24Q per-quarter Annexure I **exists**; Annexure II (year-end) helper exists but is **not wired**.
- **Leave:** Apply is hardcoded to `current_user`; **model already separates** `employee_id` (subject) from `created_by_user_id` (filer) — on-behalf is modeled but never wired. Approval chain (manager → HR) is **hardcoded** in `apply_leave`, on the **legacy** approval engine. **No separation-of-duties guard** (an HR can approve their own leave). Rich `LeaveType` policy fields exist but entitlement is a single global quota, not per employment-type. Cancellation is **owner-only** and only for SUBMITTED/DRAFT — approved leave cannot be cancelled/reversed by anyone.
- **Shifts:** `ShiftTemplate` (fixed defs, grace, weekly-offs) + `EmployeeShiftAssignment` (date-ranged) + bulk assign **exist**. Employee `ShiftChangeRequest` **exists** and routes through the generic chain engine (Reporting Manager → HR). **No roster** (explicitly out of scope in current code), **no functional-head scoping** (global permissions only). `shift_resolver.py` computes late-in/early-out minutes.
- **Unscheduled login:** Punches with no shift / outside window **are detected and persisted** as `Attendance.attribution_flag` and shown in an HR review list — but **no push notification** fires (only geofence flags notify).
- **Late marks:** Lateness is **measured** (grace configurable via `SystemSetting`) but **display-only** — not persisted, no counter, **no CL→PL→LOP escalation, no payroll link**. The only pay reduction today is LOP from approved unpaid leave.
- **Approvals:** **Two engines.** A **generic, admin-configurable** chain engine (`approval_chain.py` + `approval_engine.py`) with amount-band routing, `skip_if_same_person` (separation of duties), and CRUD in Settings — but wired **only** to expense/travel/shift-change. A **legacy** hardcoded engine (`approval.py` + `approvals.py`) still powers **leave, overtime, and salary revision** with no SoD guard. Approver types today: `reporting_manager`, `dept_head`, `role`, `specific_user`, `finance` — **no `functional_head`, `ceo`, or `md`.**
- **Notifications/email:** In-app + **real SMTP email** + SMS all wired; email auto-enables when `SMTP_HOST` is set. Delivery driven by the scheduler. Notifications carry `resource_type`+`resource_id` breadcrumbs but **no first-class deep-link/action-URL**.
- **Letters:** 8 letter types (offer, appointment, confirmation, experience, relieving, promotion, salary-revision, Form16-Part-B) **hardcoded** in reportlab. PDFs regenerated on download from stored JSON field values. **No custom-template upload.**
- **Scheduler:** Real APScheduler cron **exists but is OFF by default** (`ENABLE_SCHEDULER=False`). 6 jobs registered. **No birthday/anniversary reminder job.** A celebrations calculator (`GET /hr/celebrations/upcoming`) already finds birthdays/anniversaries but is pull-only.
- **Salary revision:** Snapshots, arrears, auto-letter, bulk cycles **exist**. Flow today: **HR authors the new value → one manager approves → apply**. No "functional head enters the value" step, no distinct CEO/MD stage.
- **Accounts / finance role:** **Does not exist** today — no Accounts persona and no finance/payment gate. Payroll finalize → publish is **HR-only**; `SalaryDisbursement` (partial payouts + `held_reason`) and a bank-details service exist but have **no Accounts sign-off**. Expense, salary-advance, and travel each have their own approval flow but **no final payment gate**. All tax/statutory config is HR/admin-owned today (no split between HR and Accounts).

## 4. Cross-cutting foundations (Phase 0)

These unblock multiple workstreams and must land first.

### F1 — Functional Head & team model
- **Data:** Add `head_user_id` (+ optional `deputy_head_user_id`) to `Department` and/or `FunctionalArea`. Add a `Functional Head` role. Decide the canonical "function" grouping (recommend: Department, since `Employee.department` already exists as the team key — confirm during planning).
- **Service:** `resolve_team(head_user)` → employees in the head's function; `resolve_head(employee)` → the governing head. Reused by rostering, revision, approvals, notifications.
- **Settings UI:** HR assigns head/deputy per department/function.
- **Acceptance:** Given a department with an assigned head, the service returns exactly that department's active employees; a head with no assignment resolves to none (never all).

### F2 — Employment Type master
- **Data:** New `EmploymentType` master (name, code, `is_on_payroll` flag, active) with references to: a **payroll profile** (statutory applicability — PF/ESI/PT/TDS on/off, flat-TDS %), a **leave policy set**, and a **default salary template** (F3). Migrate the existing 3 string values into seeded rows; keep `Employee.employment_type` as an FK (with a compatibility shim for the string during migration).
- **Settings UI:** HR CRUD for types and their attached profiles.
- **Acceptance:** Creating a "Consultant (off-payroll)" type with PF/ESI off and 10% flat TDS makes any employee of that type compute exactly that way in payroll, with no code change.

### F3 — Salary structure: component + template master
- **Data:** `SalaryComponent` master (code, name, kind=earning/deduction, taxable flag, statutory basis, calc method = fixed / %-of-basic / %-of-gross / slab, **cap fields**: percent + max-amount cap). `SalaryTemplate` = ordered set of components with default values, attachable to an employment type or an individual employee. Employee salary becomes a template instance + overrides; retain flat columns as a read-model/compat during transition.
- **Engine:** Extend `payroll_engine`/`salary_calculator` to compute from the component set, honouring per-component caps (this also delivers **W4** deduction caps natively). Keep statutory (PF/ESI/PT/TDS) as system components so the existing capped `compute_statutory` remains the source of truth.
- **Acceptance:** Accounts can define a distinct structure per type; a component with a percent + max-cap deducts `min(percent×base, cap)`; payroll output matches the current engine for existing permanent employees (regression-locked).

### F4 — Approval engine unification + separation of duties
- **Add approver types** to the generic engine: `functional_head`, `ceo`, `md` (resolve via F1 + role lookup).
- **Migrate leave, overtime, and salary revision** off the legacy hardcoded engine onto the generic configurable chain engine, so all requisitions gain: admin-configurable chains (in Settings), amount/band routing where relevant, and **`skip_if_same_person`** (an approver can never approve their own requisition — delivers **W3**).
- **Acceptance:** An HR who files a leave request is skipped as an approver and it routes to another HR/approver; approval chains for each requisition type are editable in Settings; existing in-flight approvals migrate cleanly.

### F5 — Notification deep-links + scheduler enablement
- Add a first-class `action_url`/deep-link to `Notification` + delivery templates; populate it for every event type that opens a screen.
- Safely enable the scheduler in the target environment (`ENABLE_SCHEDULER`), with the notification sweep/send/digest jobs plus the new reminder job (W10b).
- **Acceptance:** A roster/leave/revision notification (in-app + email) contains a working deep link that opens the exact relevant screen; scheduler runs the delivery + reminder jobs on cadence.

### F6 — Accounts role & finance-approval layer
- **Role:** New **Accounts** role (RBAC) with a **finance-scoped** app surface (payroll review, tax config, a payment queue) — not full HR access.
- **Approver type:** Add `accounts` to the approval engine (F4) so Accounts can be a configured step or terminal payment gate on any outflow.
- **Tax-config ownership:** Move **income-tax / TDS** configuration (rates, slabs, min/max, caps in `StatutoryConfig`/tax engine) to an **Accounts** permission; **HR keeps PF / ESI / PT** + salary-structure caps (F3). Both remain effective-dated and feed the existing capped engine.
- **Payment model:** "Payment done" is a **status flag** (on `SalaryDisbursement` and on each approved outflow) — Accounts marks paid **with a note**; **no bank file, no money movement** in-system.
- **Acceptance:** An Accounts user logs into a finance-scoped app, can edit TDS/income-tax config (but **not** PF/ESI/PT or salary structure), appears as an available approver, and marking "paid" records who/when + note.
- **Depends on:** F4 (approver types + configurable chains), RBAC.

## 5. Workstreams

Each is scoped as: **Exists → Build (backend / frontend) → Acceptance → Depends on.**

### W1 — Employment types applied across payroll, leave & salary
- **Exists:** payroll already branches on `employment_type`.
- **Build (BE):** Wire F2 type → payroll profile (statutory on/off, flat-TDS), F3 salary template, and per-type **leave entitlement** (auto-seed `LeaveBalanceLedger` from the type's leave policy on join/confirmation). Probation as a first-class status (`EmployeeStatus.probation` + probation→confirmation transition already has `confirmation_date`).
- **Build (FE):** Employee create/edit shows type; type Settings screens (F2); per-type leave & salary template config.
- **Acceptance:** Full-time / Provisional / Consultant / Off-payroll each get correct payroll, leave options, and salary structure with zero code branching.
- **Depends on:** F2, F3.

### W2 — HR applies leave on behalf of an employee
- **Exists:** model already separates subject vs filer.
- **Build (BE):** `employee_id` param on the apply endpoint, permission-gated to HR; sets `created_by_user_id=HR`, `employee_id=subject`; validations key on the subject; routes through the (F4) chain **excluding the filing HR** as approver.
- **Build (FE):** HR "Apply leave for employee" action in Leave Approvals / Employee record.
- **Acceptance:** HR files leave for employee X; it debits X's balance and routes to a *different* approver.
- **Depends on:** F4 (for correct SoD routing).

### W3 — Separation of duties (no self-approval)
- Delivered by **F4** (`skip_if_same_person` applied to all requisition types). No separate build; add regression tests per requisition type.

### W4 — Deduction caps (percent + max limit, HR-configurable)
- **Exists:** PF/ESI ceilings in `compute_statutory`.
- **Build:** Delivered structurally by **F3** (per-component percent + max-amount cap). Additionally: surface statutory caps as **HR-editable** `StatutoryConfig` in Settings, and apply caps on the **legacy contractor path** (or retire it in favour of the unified engine).
- **Acceptance:** HR sets a cap for any deduction in Settings; payroll honours `min(percent×base, cap)`; no uncapped path remains.
- **Depends on:** F3.

### W5 — Single-employee / off-cycle payroll + editable lines with reason & audit
- **Exists:** batch run; 4 editable fields (no reason/audit).
- **Build (BE):** (a) `employee_ids` on the run/generate so payroll can target one employee or a subset (off-cycle run type, coexisting with the monthly batch); (b) add a **reason/note** field to line edits and **`log_audit`** on every override; optionally widen overridable fields with reason capture.
- **Build (FE):** "Run payroll for selected employee(s)" flow; editable line with mandatory reason; audit visible on the line.
- **Acceptance:** HR runs payroll for a single missed employee; every manual edit records who/what/why and appears in the audit trail.
- **Depends on:** none hard (independent of F-layer, but should respect F3 components).

### W6 — Government forms surfacing (Form 16, Form 24Q) per year/period, all & per-employee
- **Exists:** Form 16 per-employee + bulk; Form 24Q Annexure I per quarter.
- **Build (BE):** wire Form 24Q **Annexure II** (year-end) into the generate endpoint; add any other required forms during planning.
- **Build (FE):** an HR "Statutory forms" screen — pick form + FY/quarter/period, generate for all or a selected employee, download. Employee self-service Form 16 download.
- **Acceptance:** HR generates Form 16 for one employee or everyone for a chosen FY; Form 24Q for any quarter incl. Q4 Annexure II.
- **Depends on:** none.

### W7 — Full weekly/monthly roster planner (functional-head scoped) — *greenfield*
- **Exists:** shift templates, date-ranged assignments, bulk assign, employee change requests, shift resolver.
- **Build (BE):** a **Roster** model (per employee, per day, referencing a shift template or off), with publish/draft states; functional-head-scoped shift-template definitions (a head defines shifts for their function only, via F1 scoping); roster generation/edit APIs (per day/week/month, bulk, copy-forward); HR + head + employee-request edit paths (employee changes still route through the existing change-request → approval flow, now to the **functional head** then HR); cancellation of leave/roster entries by the functional head.
- **Build (FE):** roster grid (week/month), publish, drag/bulk edit, per-cell change; head view scoped to their team; HR view across all; employee view + "request change."
- **Acceptance:** A functional head defines shifts for their function and maps a monthly/weekly roster for their team; HR, head, and (via request) employees can change it; changes notify affected parties with deep links.
- **Depends on:** F1, F5.

### W8 — Unscheduled-login notifications
- **Exists:** detection + `attribution_flag` persisted.
- **Build (BE):** on punch with `NO_SHIFT`/`OUTSIDE_WINDOW`, fire a notification to **HR + the functional head** (mirroring the existing geo-flag notifier), with a deep link and an action to "assign this person to a slot."
- **Build (FE):** notification action → slot-assignment shortcut; HR/head can accommodate the person into a slot.
- **Acceptance:** An unscheduled login pushes a notification to HR and the head; they can add the person to a slot from it.
- **Depends on:** F1, F5, W7 (slot assignment target).

### W9 — Late-mark rules engine → CL→PL→LOP → payroll — *greenfield*
- **Exists:** late-minutes computed (display-only); LOP-from-unpaid-leave in payroll.
- **Build (BE):** a **configurable late policy** (HR Settings): grace threshold (e.g. 15 min past slot), late-mark definition, and an escalation ladder (X lates → deduct CL, then PL, then LOP/pay cut). Persist a per-employee late counter/ledger per period; a period-close step that converts accumulated lates into leave debits, then LOP, feeding the payroll engine. Payroll remains **editable with reason** (W5) so HR can override.
- **Build (FE):** late-policy Settings; late/attendance report; payroll shows late-driven deductions with the ability to edit + note.
- **Acceptance:** With a "15-min, 3-lates" policy, a 4th late in a period deducts a CL (then PL, then pay cut when balances exhaust) and reflects in payroll, overridable by HR with a note.
- **Depends on:** F3/W5 (payroll edit+audit), shift start times (W7 data), leave ledger.
- **Note:** overlaps the existing payroll roadmap item "absence→LOP" — align with that.

### W10a — Custom letter-template upload & send — *greenfield*
- **Exists:** 8 hardcoded reportlab letters; `EmployeeLetter` store; regenerate-on-download.
- **Build (BE):** a **letter-template store** (upload DOCX/HTML with merge fields, stored like existing policy/document media), a templating/merge engine (employee + salary + date fields), and a "generate from template → send" path (in-app + email via existing delivery).
- **Build (FE):** HR template library (upload/manage), pick template + employee(s) → preview → send/download.
- **Acceptance:** HR uploads a custom letter template with merge fields, generates it for an employee, and sends it from the system.
- **Depends on:** F5 (send/email).

### W10b — Birthday/anniversary reminders + event report + auto-letters
- **Exists:** celebrations calculator (pull-only); scheduler (off).
- **Build (BE):** a scheduler **reminder job** using the existing celebrations logic → notifications/emails to HR (and optionally the person); an **event report** (list events by date range/year); optional auto-send of a greeting letter template (W10a) for the event; reminders configurable from the employee DB (which events, lead time, recipients).
- **Build (FE):** HR event/reminder Settings + a report screen listing upcoming/passed birthdays & anniversaries by date.
- **Acceptance:** HR sees a dated event report and receives reminders; optional auto-letters send on the day.
- **Depends on:** F5, W10a (for auto-letters).

### W11 — Multi-stage salary revision (functional-head-authored → CEO/MD → HR commit)
- **Exists:** revision snapshots, arrears, auto-letter, bulk cycles; single-manager approval.
- **Build (BE):** rework the revision flow onto the unified engine (F4): **(1)** HR selects employees (per function or a hand-picked list) and routes to the **functional head**; **(2)** the head *enters the new value* (a data-entry step, not just approve) and submits; **(3)** routes to **CEO/MD** for approval; **(4)** back to HR; **(5)** HR approval commits it as a new effective-dated salary → next payroll (reusing existing arrears/apply plumbing). Notifications at each hop with deep links.
- **Build (FE):** HR "start revision cycle → select employees → send to head"; head "enter values" screen; CEO/MD approval queue; HR commit; status tracking through all stages.
- **Acceptance:** A revision moves HR→head(enter value)→CEO/MD(approve)→HR(commit)→payroll, with notifications and audit at each step; the head cannot approve their own, CEO/MD sign-off is mandatory before commit.
- **Depends on:** F1, F4.

### W12 — Payroll → Accounts verification → payment
- **Exists:** staged payroll run (… → FINALIZED → PUBLISHED); `SalaryDisbursement` with partial payouts + `held_reason`; bank-details service.
- **Build (BE):** insert an **Accounts-verification stage** after HR **FINALIZE** and before **PUBLISH/payment**, implemented as a payroll-run approval on the unified engine (HR finalize → Accounts). Accounts can **approve** (→ publish payslips + disbursement becomes payable) or **reject back to HR with a reason** (reopens to DRAFT_GENERATED for edit + re-finalize). Payment is a **status flag** — Accounts marks "payment done" with a note; no bank file.
- **Build (FE):** Accounts "Payroll to verify" queue → review the computed run (incl. the audited HR line edits from W5) → approve / reject-with-reason → payment screen to mark paid.
- **Acceptance:** A finalized run cannot be published or paid until Accounts approves; Accounts can bounce it back to HR with a reason; "payment done" records who/when/note; no payment ever precedes Accounts sign-off.
- **Depends on:** F4, F6, W5 (audited editable lines).

### W13 — Accounts as final payment gate for all outflows
- **Exists:** expense, salary-advance, and travel each have approval flows (expense/travel already ride the generic engine).
- **Build (BE):** add a **terminal `accounts` payment step** to the expense, salary-advance, and travel chains — after their existing approvals the claim lands in an **Accounts payment queue**, where Accounts marks it **paid** (status flag + note). Salary advance (currently on its own flow) is migrated/extended onto the generic engine to share the gate.
- **Build (FE):** a unified Accounts **payment queue** across payroll, reimbursements, advances, and travel; mark-paid with note; paid history.
- **Acceptance:** Every outflow (payroll, reimbursement, advance, travel) requires an Accounts "mark paid" after its approvals; nothing shows as paid without an Accounts action + note.
- **Depends on:** F4, F6.

## 6. Recommended phasing

Sequenced by dependency and value. Each phase is independently shippable.

- **Phase 0 — Foundations:** F1 Functional Head · F2 Employment-Type master · F3 Salary component/template master · F4 Approval unification + SoD · F5 Deep-links + scheduler · **F6 Accounts role + finance-approval layer**.
- **Phase 1 — HR flexibility, payroll & Accounts (fast value):** W2 HR-apply-on-behalf · W3 SoD (from F4) · W5 single-employee + editable/audited payroll · W4 deduction caps · W6 government forms surfacing · **W12 payroll→Accounts→payment** · **W13 Accounts gate for all outflows**.
- **Phase 2 — Types applied & revision:** W1 employment types across payroll/leave/salary · W11 multi-stage salary revision.
- **Phase 3 — Rostering & attendance rules (largest):** W7 roster planner · W8 unscheduled-login notifications · W9 late-mark engine.
- **Phase 4 — Documents & engagement:** W10a custom letter templates · W10b reminders + event report + auto-letters.

## 7. Risks & watch-items

- **Two-engine approval migration (F4)** is the highest-risk foundation — leave/OT/revision must migrate without breaking in-flight approvals. Needs a migration plan + regression tests before Phase 1.
- **Salary re-platforming (F3)** must be regression-locked so existing permanent-employee payroll output is byte-for-byte unchanged; keep flat columns as a compat read-model during transition.
- **Legacy uncapped calculator** (`salary_calculator.py`) should be retired or fully capped to avoid two sources of truth.
- **Scheduler enablement (F5)** must be environment-safe (single-worker locking already exists) to avoid duplicate emails.
- **Roster planner (W7)** is the biggest single build; confirm the "function = department" grouping early so F1 aligns.
- **Accounts gate on all outflows (W13)** broadens surface — it requires migrating salary-advance onto the generic engine and adding a terminal payment step to expense/travel. Keeping payment as a **status flag** (no bank file/gateway) is the deliberate scope-container here; don't let it grow into payment-execution this round.

## 8. Out of scope (this round)

- Shift auto-rotation algorithms (heads map rosters manually; auto-rotation deferred).
- Payroll for jurisdictions beyond the current India statutory set (PF/ESI/PT/TDS).
- Mobile-native roster editing (web-responsive only unless specified).
- **Live bank / payment-gateway integration** — this round, payment is a **status flag** (mark-paid + note) with the bank transfer done outside the system; a bank-file or gateway integration is a later phase.

## 9. Next steps

1. User reviews and approves this scope.
2. Each phase (starting Phase 0) gets its own detailed implementation plan (spec → plan → build) via the standard planning flow.
3. Confirm the "function = department vs. functional-area" grouping and the exact late-mark escalation ladder during Phase 0 planning.
