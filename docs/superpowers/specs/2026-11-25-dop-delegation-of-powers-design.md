# Delegation of Powers (DOP) — Design

Date: 2026-11-25 · Branch: `feature/dop-approvals` (off main e4079c2) · Status: awaiting user review

## Goal

Admin decides who verifies, recommends and approves every request, by person, post, role or manager relationship. Large organisations with several managers per employee get one clear, predictable answer to "who acts on this?".

## User decisions

1. Approvers can be set by **person, post/position** or role (2026-11-25).
2. An employee can have **several managers** of different kinds, each with **subdomains**; acting/provisional managers, heads of department and **verifiers** exist (2026-11-25).
3. Whether the original holder may still act while someone acts for them is **an admin choice per acting assignment**, changeable at any time (2026-11-25).
4. **Admin can approve or cancel anything**, with a mandatory note that goes to the audit log (2026-11-25).
5. Requests have no effect until a person approves them; nothing auto-approves (2026-11-23).
6. With no rule: reporting manager, then HR. Rule scope: department and amount bands (2026-11-23).

## Today

- `User.manager_id` is the only manager link (used in ~27 files).
- Generic chains (`approval_chain*`, `endpoints/approval_chains.py`): expense, travel, shift change, salary revision, asset request, optional holiday, work location. Approver types: reporting manager, dept head, role, specific user, finance, functional head, CEO, MD. `dept_head` resolves to **every** holder of the DEPT_HEAD role org-wide.
- Legacy engine (`ApprovalItem`/`ApprovalStep`): leave, comp-off, overtime, requisition, estimate, and salary revision without a chain.
- Own decide logic: attendance regularization, roster swaps / drops / open-shift claims, resignation, salary advance.
- Out-of-office cover (`ApproverDelegation`) and SLA escalation exist. Either the delegator or the delegate can act.
- `Designation` is a job title, not a seat; `Department` has head and deputy.

## 1. Data model

**Manager kinds** `manager_kind`: id, code, name, sort_order, is_active, is_system. Seeded: `reporting` (system), `functional`, `project`. Admin can add or rename kinds; system kinds cannot be deleted.

**Subdomains** are a fixed code list, each mapped from request types: `leave`, `attendance` (regularization, work location, optional holiday, overtime, comp-off), `roster` (shift change, swaps, drops, claims), `expense` (expense, travel, salary advance), `asset`, `pay` (salary revision), `people` (requisition, resignation), `business` (estimate).

**Manager assignments** `manager_assignment`: id, manager_kind_id, scope_type (`user|department|location|company`), scope_user_id / scope_department_id / scope_location (text), manager_user_id **or** manager_post_id (exactly one), starts_on, ends_on (NULL = open), note, created_by_id, created_at, ended_by_id, ended_at.
- Child `manager_assignment_subdomain` (assignment_id, subdomain); no rows = all subdomains.
- **One answer:** two assignments with the same kind and scope may not overlap in dates for the same subdomain (409). "All" and a named subdomain at the same scope may coexist: the named one wins.
- A "team" is expressed by assigning to selected employees in bulk; there is no separate team table.

**Posts** `post`: id, code, title, department_id, location, parent_post_id, is_active. `post_holder`: post_id, user_id, starts_on, ends_on, with at most one holder on any date. Vacant posts are allowed. Department head is the existing `Department.head_user_id` / deputy; a post may be flagged `heads_department_id` (unique), in which case its holder is the head.

**Acting assignments** `acting_assignment`: id, covers_user_id **or** covers_post_id, acting_user_id, subdomains (child table, as above), starts_on, ends_on, `original_can_act` (bool, default false), only_when_on_leave (bool), reason, created_by_id, revoked_at / revoked_by_id.
- Replaces `ApproverDelegation`. Existing rows are migrated with `original_can_act=true`, which keeps today's behaviour. Self-service out-of-office stays and creates these rows with the same default.
- Acting does not chain: if A covers B and B covers C, A does not act for C.
- Overlapping covers for the same user/post and subdomain are refused (409). A cycle is harmless because covers do not chain.

**Rules** extend the existing tables:
- `approval_chain` gains `location`, `priority` and `status` (`draft|live|retired`); it keeps department, dates and bands. Editing a live rule creates a new version (`version_of_id`); in-flight requests keep the version they started on.
- `approval_chain_step` gains `job` (`verify|recommend|approve|inform`, default approve), `fallback_type` and `fallback_ref`. Approver types gain `manager_kind` (ref = kind code), `post` (ref = post id) and `dept_head_of_requester`. The old `dept_head` type remains readable and the builder no longer offers it; the migration report lists rules that use it.
- A live rule needs at least one `approve` step. `auto_approve_below_paise` is removed from the builder and ignored.

**Runtime** `chained_approval_step_instance` gains job, acting_for_user_id, via_post_id and resolution_json (why this person). Instance statuses gain `returned` (sent back by a verifier).

## 2. Resolver

`services/dop/resolver.py`, the only place that answers "who acts". Pure core over pre-loaded data, so it is unit-testable.

`resolve(step, requester, request_type, on_date, context) -> Resolution(user_ids, via, explanation)`

1. **Base person(s):**
   - person: that user;
   - post: holder on the date;
   - manager kind: the most specific matching assignment (user > department > location > company), named subdomain before "all";
   - reporting manager: kind `reporting`;
   - department head: head of the requester's department, else deputy;
   - role: active users holding it.
2. **Acting:** if a cover is live for that person (or their post) and subdomain, use the acting user, plus the original when `original_can_act`.
3. **Filter:** drop inactive users and the requester.
4. **Fallback:** if empty, use the step's fallback, then HR (`hr employee write`). If still empty, the request is **blocked and flagged to admin**; it is never approved or skipped.
5. **Repeat approver:** someone who already approved earlier in the same request is not asked again; the step is recorded as satisfied by their earlier approval. A person who **verified** cannot also approve: that step goes to its fallback.

Resolution happens **when a step becomes current**, not at submission, so a handover mid-request reaches the new holder. Acting covers are re-checked at action time: a cover that ended loses the right to act.

When a covered post or person changes while a step is pending, pending step rows are re-resolved by the change itself (same transaction) and the new approver is notified.

## 3. Step jobs

| Job | Actions | Effect |
|---|---|---|
| verify | Verify, Send back (note required) | Moves on, or returns the request to the requester, who can edit and resubmit; resubmission restarts at the first step |
| recommend | Recommend / Not recommended (note) | Recorded; moves on either way |
| approve | Approve, Reject (note required) | As today, with any/all for parallel steps |
| inform | None | Notification when the step is reached; does not wait |

A verifier or recommender never finalises a request. Finance verification of paid claims (`accounts-verify`) keeps its separate duty-separation rule.

## 4. Admin override

Permission `dop override`, granted to Super Admin only.

- **Actions on any request in any state:** approve, reject, cancel (including already approved), reassign the current step, end or change an acting cover.
- **Note is mandatory**, 10–500 characters after trimming; the server rejects anything shorter (422).
- Confirmation dialog shows the effect ("2 days go back to the leave balance").
- Each action writes an AuditLog row `dop.override.<action>` (admin, request type and id, previous state, new state, current approver bypassed, note, IP) and notifies the requester and the bypassed approver. The audit row is written in the **same transaction** as the change.
- Approve and cancel call the request type's own service functions, so balances, rosters, assets and payroll inputs change exactly as through the normal path. No direct status edits.
- **Safety limits that still apply:**
  - admin cannot override **their own** request; another admin must;
  - a payroll-locked period is refused (409) with the reason. The existing unlock process is used first.
  - paid or otherwise irreversible records (e.g. reimbursed expense, applied salary revision) are refused with an explanation of the correct reversal path.

## 5. Adapters

Each request type registers one adapter (`services/dop/adapters/`): subdomain, amount, department, summary, `on_approved`, `on_rejected`, `on_cancelled`, `on_returned`, `can_override_cancel`. The engine never imports a feature's model directly; `_entity_summary` in `approval_chains.py` moves into adapters.

## 6. Screens (web)

*Administration → Delegation of Powers*, permission `dop manage` (Super Admin; grantable):
1. **Managers:** grid by employee with one column per kind; bulk assign to selected employees, department, location or company; "missing manager" filter; CSV import; history.
2. **Posts:** list and parent/child tree, holder, vacancy, acting holder, history.
3. **Acting:** create and end covers, with the "original can also act" switch.
4. **Rules:** per request type; step builder with job, approver, fallback, amount band; draft → Check → make live.
5. **Check:** choose employee, request type, amount and date; shows each step, the person and the explanation. "Check all employees" lists anyone whose route is blocked; a rule with blocked routes can go live only after the admin acknowledges the list.
6. **Override log:** filterable, exportable.

**Approvals inbox:** one list on the web Approvals Center and the Expo app for every request type, with job-specific buttons and "acting for" labels. Override actions appear on the web only. Request detail shows the route and who acted in which capacity.

## 7. Delivery slices

Each is planned, built, tested and merged separately.

- **D1 Foundation:** manager kinds, assignments, posts, acting, resolver, Managers / Posts / Acting / Check screens.
  - `User.manager_id` rows are copied to `reporting` assignments. `manager_id` remains as a **synced mirror** of the user-scoped or inherited reporting manager, so existing readers keep working; HR edits of the manager go through the assignment service.
  - Live approvals do not use the new resolver yet: behaviour is unchanged.
- **D2 Rules and inbox:** jobs, fallbacks, versions, rule builder, adapters, override and the unified inbox for the seven chain types. Includes the direct-path (no chain) cases.
- **D3 Attendance and overtime:** regularization, overtime, comp-off.
- **D4 Leave:** moved off the legacy engine. In-flight legacy requests finish on the legacy path. Ledger parity tests on seed data before and after.
- **D5 Remaining:** requisition, estimate, swaps / drops / claims, resignation, salary advance. Legacy engine becomes read-only history.

With no configured rule, every type keeps its current route (D2–D5 each seed a default rule equal to the present behaviour), so an upgrade changes nothing until admin edits a rule.

**Out of scope:** bank-detail and document verification, payroll run approvals (Accounts gate), biometric device approval, per-entity rules, AI suggestions.

## 8. Error handling and concurrency

- All mutations use `retry_on_lock` / `guard_conflicts`. Lock order: instance → step rows → entity.
- Never read an ORM user after `expire_all` or a rollback; use `plain_actor` (6A lesson).
- Decide vs cancel vs override races: exactly one wins, others get 409, never 500.
- Resolver failure at step advance does not undo the recorded decision: the instance becomes `blocked`, admin is alerted, and Check shows why.

## 9. Testing

- **Resolver table tests:** scope precedence, subdomain precedence, acting (with and without original), vacant post, inactive user, requester excluded, verifier ≠ approver, fallback chain, blocked.
- **Parity:** for every type, default-rule route equals the current route on seed data.
- **Override:** note required, own request refused, locked period refused, audit row present and atomic, effects reversed.
- **Concurrency**, migration down/up on a cloned database with real rows, API end-to-end, browser, and Android checks for each slice.
- Full backend suite run **live before each merge**.

## Assumptions to confirm

1. Admin cannot override their own request; another admin must.
2. Override does not bypass a payroll lock or reverse money already paid.
3. "Admin" means Super Admin; the two permissions can be granted to other roles later.
4. Cancelling an approved request gives back its effects (leave balance, roster, asset reservation).
