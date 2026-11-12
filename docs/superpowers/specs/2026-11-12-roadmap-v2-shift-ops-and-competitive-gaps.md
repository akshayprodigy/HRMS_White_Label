# Roadmap v2 — 24×7 Shift Operations, Emergency Handling & Competitive Gaps

Date: 2026-11-12 · Branch base: `feature/workforce-expansion` (migration head `y3z4a5b6c7d8`)

## Scope decisions

| Item | Decision |
|---|---|
| Employee computer monitoring | **Dropped for now** |
| Call tracking | **Dropped for now** |
| Native mobile app | **In** (React Native, white-label builds) |
| Live location tracking | **In** (ships with mobile app) |
| Biometric integration | **In** |
| Asset management upgrade | **In** |
| 24×7 shift operations + delegated scheduling | **In (new, client-requested)** |
| Emergency / last-minute leave & rescheduling | **In (new, client-requested)** |

## What already exists (build on, don't rebuild)

- `ShiftTemplate` with `is_overnight`, grace, break, full/half-day hours, weekly offs
- `shift_resolver` attributes cross-midnight punches correctly
- `EmployeeShiftAssignment` (effective-dated default shift), `ShiftChangeRequest`
- `RosterEntry` (per employee per date) + `RosterChangeRequest`, roster planner grid (week/month, apply pattern)
- Roster scope = HR / Super Admin / department head only (`services/roster.py: can_manage_employee`)
- **Roster is display-only** — does not feed attendance or payroll
- Leave types, HR leave-on-behalf, late marks, overtime rules, night allowance rules, comp-off model, geofence punch, approval chain engine (F4), notifications

---

## Phase 0 — Close the loop on existing claims (~1–1.5 wks)

Must ship first; every later phase depends on attendance + roster being the source of truth for pay.

1. **Roster → shift resolver.** Precedence: `RosterEntry` for the date → `EmployeeShiftAssignment` → org default. Week-off in roster = week-off for attendance.
2. **Absence → LOP** with a policy toggle in Time Rules: scheduled working day + no punch + no approved leave/on-duty/holiday ⇒ LOP (or "pending regularization" until payroll lock).
3. **Half-day LOP bug** (multi-day half-day counted as 0.5 total).
4. **Attendance regularization review:** missed-punch / wrong-punch request → approval → corrected record; cutoff tied to payroll attendance lock.
5. Regression: monthly payroll parity on seed data before/after.

## Phase 1 — 24×7 Shift Operations & Scheduling (~3–4 wks)

### 1.1 Shift design
- Multiple shifts per day per location/department (A/B/C 8-h, 2×12-h, general, split shifts).
- **Rotation patterns** as reusable objects: weekly rotation (A→B→C), 4-on-4-off, 2-2-3 (Panama), custom N-day cycle with an anchor date.
- **Work rules (per org / per department):** minimum rest between shifts (e.g. 11 h), max consecutive days, max consecutive nights, max weekly hours, mandatory weekly off.
- Shift attributes: location, required skill/role, paid break, shift differential / night allowance link.

### 1.2 Staffing requirements (coverage)
- Per location × department × shift × day-type: required headcount, optionally by role/skill.
- Grid shows coverage per shift: understaffed (red) / ok (green) / overstaffed (amber).

### 1.3 Scheduler (HR / admin / delegated scheduler)
- Drag-and-drop grid (employees × days), filter by department/location/shift.
- Copy previous week/period, apply rotation pattern to a team, bulk edit.
- **Auto-fill suggestion** respecting approved leave, holidays, week-offs, availability, rest rules, skill, fair distribution of nights/weekends.
- Live validation: rule violations shown inline (rest gap, OT breach, double-booking, on leave).
- **Draft → Publish** lifecycle: drafts invisible to employees; publish notifies affected employees; edits after publish are tracked as changes with reason; schedule version history.
- Schedule lock N days before the period starts (configurable).

### 1.4 Delegated scheduling (HR grants scheduling rights)
- New `ScheduleDelegation` grant: grantee user, scope (explicit employee list | team | department | location), permissions (`edit_draft`, `publish`, `approve_swaps`, `emergency_override`), validity window, granted_by, audit.
- Option: delegated scheduler's publish requires HR approval (per-grant flag).
- Replace department-head-only check in `can_manage_employee` with: HR/admin ∪ department head ∪ active delegation covering the employee.
- HR screen: list/grant/revoke delegations; "who can schedule whom" view.

### 1.5 Employee self-service
- My schedule (week/month), ICS calendar feed.
- **Availability & preferences** (unavailable days, preferred shift) — used by auto-fill.
- **Shift swap:** employee proposes swap with colleague → colleague accepts → scheduler approves (auto-validate rules both sides).
- **Open shifts:** scheduler publishes unfilled shifts; eligible employees request/claim; scheduler confirms (or auto-confirm first eligible).
- Give-away / drop-shift request.

### 1.6 Live operations board
- "On shift now" per location: scheduled vs punched-in, late, not yet arrived, on break.
- **No-show detection:** shift start + X min with no punch ⇒ alert scheduler (feeds Phase 2 gap filling).
- Shift handover note (optional, per shift).

### 1.7 Pay linkage
- Night shift allowance / shift differential from roster (existing night-allowance rules).
- Holiday working ⇒ comp-off or holiday pay per policy.
- OT computed against rostered shift, not just a fixed day.

## Phase 2 — Emergency & Last-Minute Operations (~2–3 wks)

### 2.1 Emergency / short-notice leave
- "Emergency" flag (or leave type) allowing same-day and back-dated application; documents can be attached later (e.g. medical certificate within N days, else converts to LOP).
- Applying immediately marks the rostered shift **uncovered** and alerts the scheduler.
- Late-reporting / "running late" notice from the employee for today's shift.

### 2.2 Coverage gap engine
- Triggers: emergency leave approved, no-show, last-minute shift drop, sick call.
- **Replacement suggestions** ranked by: available, not on leave, rest-gap respected, OT cap not breached, skill match, fewest hours this period.
- **Broadcast open shift** to eligible staff (push / SMS / WhatsApp); first accept → scheduler confirms → roster updated, both parties notified, OT/comp-off recorded.

### 2.3 Emergency rescheduling
- Scheduler with `emergency_override` can change a published schedule inside the lock window with mandatory reason; employee notified and must acknowledge.
- Call-back / short-notice compensation rule (allowance or comp-off).
- **On-call / standby roster** with on-call allowance.

### 2.4 Approvals that don't stall
- Approval SLA + auto-escalation (no action in N hours → next approver / HR).
- **Out-of-office delegation:** approver on leave ⇒ approvals route to their delegate automatically.
- One-tap approve/reject from push notification (mobile app).
- Bulk approve for HR.

### 2.5 Emergency communication & safety
- Emergency broadcast to all / by location / by on-shift (office closed, weather, incident) with read acknowledgement tracking.
- "Mark me safe" check-in during incidents with live dashboard.
- Employee emergency contacts + blood group on profile, quick-dial from manager view.
- Night shift compliance (India): women night-shift consent record, transport/cab requirement flag on roster.

### 2.6 Attendance fallbacks
- Biometric/network down: supervisor bulk-marks attendance for a shift with reason (audited).
- Offline punch in mobile app, synced later with original timestamp + location.

## Phase 3 — Native Mobile App, React Native (~5–6 wks; can run parallel to Phase 1/2 backend)

- Port existing mobile web screens (home, attendance, leave, payslip, approvals) to the same APIs.
- **White-label builds:** per-tenant name, icon, colors, API base URL from config; scripted build per client.
- Geofence punch + **selfie with liveness** (face match optional, phase 2).
- **Live location tracking** (opt-in per employee/role, only during rostered shift): periodic pings, map trail, "field team now" view, geofence exit alerts, battery-aware.
- Push notifications (FCM/APNs) with action buttons (approve/reject, accept open shift).
- Offline punch queue.
- My schedule, swaps, open shifts, emergency leave, running-late, mark-safe, payslip/Form16 download, documents.

## Phase 4 — Biometric Integration (~1.5–2 wks)

- ADMS / iClock push endpoint (eSSL, ZKTeco and compatibles) — device registration with serial + secret.
- Device user-ID ↔ employee mapping screen.
- CSV/Excel punch import fallback for other vendors.
- All punches flow into the same attendance pipeline (shift resolver, late marks, OT).
- Device health: last-seen, offline alert.

## Phase 5 — Asset Management (~1–1.5 wks)

- Asset master: category, model, serial, purchase date/cost, vendor, warranty expiry, location, QR tag, status (in stock / allocated / repair / retired / lost).
- Allocation/return history (current `employee_asset` becomes the allocation log).
- Employee asset requests via approval engine.
- Maintenance log, warranty/AMC expiry alerts, straight-line depreciation.
- Exit clearance blocked until assets returned (link to exit management).

## Phase 6 — Day-to-Day Essentials Backlog (prioritise per client demand)

**Attendance & time**
- On-duty / client visit / WFH requests
- Location-wise holiday calendars + optional/restricted holidays
- Muster roll and shift coverage reports; OT report

**Employee services**
- HR helpdesk / tickets (queries, grievances, POSH-sensitive category) with SLA
- Announcements / notice board, policy acknowledgement tracking
- Document expiry alerts (ID, visa, contract, licences/certifications)
- Training & certification records (feeds skill-based scheduling)
- Travel requests

**Payroll leftovers (from payroll roadmap P1/P2)**
- Incentive / bonus input feed, reimbursements into payroll
- Leave encashment, F&F payout incl. gratuity
- Loans with EMI recovery (extends salary advance)
- Contractual path off legacy flat-10% TDS

**Platform**
- Excel bulk import (employees, attendance, opening leave balances, salary)
- WhatsApp notifications channel
- Multi-location / multi-entity, per-location time zone
- Shops & Establishment registers

---

## Sequencing (single dev estimate ≈ 16–20 weeks)

```
Phase 0  ██                       (must be first)
Phase 1    ████████
Phase 2            ██████
Phase 3    ████████████           (parallel track: mobile)
Phase 4                  ████     (pull earlier if a client has devices)
Phase 5                      ███
Phase 6  continuous backlog
```

Each phase: own migrations chained linearly from current head, verified against the live stack, committed separately (same cadence as the workforce expansion).

## Open product decisions

1. Delegated schedulers: may they publish directly, or must HR approve publishes? (Proposed: per-grant flag, default = HR approval.)
2. Open-shift fill: first-come auto-confirm, or scheduler always confirms?
3. Broadcast channel cost: push only, or also SMS/WhatsApp (paid)?
4. Live location: which roles are tracked by default (field staff only)?
5. Emergency leave without documents: convert to LOP after how many days?
