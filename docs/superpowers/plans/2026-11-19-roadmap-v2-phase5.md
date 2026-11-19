# Roadmap v2 — Phase 5 (Asset Management) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A real asset register: every company asset (laptop, phone, licence, vehicle…) has a master record with purchase and warranty data, a QR tag, a status and a full allocation history. Employees request assets through an approval flow, HR logs maintenance, the system alerts before warranty/AMC expiry, book value is depreciated straight-line, and an employee cannot be released at exit while still holding assets.

**Architecture:**
- **Master + log:** a new `asset` table is the register (one row per physical/licensed item). The existing `employee_asset` table becomes the **allocation log**: one row per hand-over. It gains a nullable `asset_id` FK, plus `returned_condition` and `returned_to_id`. An asset has at most one open allocation (`employee_asset.status == "allocated"`). That rule is enforced in the service under a row lock on the asset.
- **One service owns state:** `app/services/assets.py` performs every status change (allocate, return, mark lost, send to repair, retire, reinstate) and writes the allocation log. Endpoints, the legacy `hr.py` asset routes, request fulfilment and exit all call it. No other code sets `Asset.status`.
- **Requests:** `asset_request` rows. On submit, if HR has configured an active approval chain for entity type `asset_request`, the F4 chain engine routes it (`instantiate_for_entity`). Otherwise the request waits for anyone holding `asset manage`. Approved requests are *fulfilled* by allocating a specific in-stock asset.
- **Derived, not stored:** book value/depreciation is computed on read by a pure function. Expiry alerts are a daily scheduler job that notifies once per expiry date.
- **Exit:** `final_release` refuses while the employee has open allocations. Exit details show outstanding assets.

**Tech Stack:** FastAPI + async SQLAlchemy + MariaDB + Alembic; `segno` (pure-Python QR, new dependency) for SVG QR labels; React + shadcn/ui frontend.

Branch: `feature/roadmap-v2-phase5`, created from `main` after `main` was fast-forwarded to the Phase 4 tip `e879371` (2026-11-19). Migration head at start: `c4e8a2f6b1d9` (verify with `alembic heads`).

**Product decisions (defaults chosen 2026-11-19; change before the task that uses them if the user objects):**
1. **Lost settles the allocation.** An allocation marked `lost` counts as resolved for exit. Recovering the cost from F&F is a Phase 6 payroll item.
2. **Approval routing:** use the `asset_request` approval chain if HR configured one; otherwise `asset manage` holders approve directly. Never 400 because no chain exists (unlike expenses).
3. **Depreciation:** straight-line, monthly, `salvage_value_paise` default 0, `useful_life_months` from the asset (falls back to its category, then 36). Computed on read; nothing stored.
4. **Alerts:** warranty and AMC expiry within `assets.expiry_alert_days` (time rule, default 30). Notifies each `asset manage` holder **once per expiry date**: it re-alerts only if the expiry date changes, e.g. after an AMC renewal.
5. **Permission:** new `asset manage` → HR, Super Admin. Every employee can view their own assets and requests and create requests. No new read permission.
6. **Backfill:** existing `employee_asset` rows each get an `asset` master row, so the register is complete on day one.
7. **Money in paise** (int), matching expenses/payroll.

## Environment (all tasks)

- Backend environment, tests, migrations and commit rules: read "Environment (all tasks)" in `docs/superpowers/plans/2026-11-12-roadmap-v2-phase1b.md`.
  - Containers, and pytest on the real dev DB with clean teardown (fixture pattern from `backend/tests/test_roster_publish.py`; teardown leaves zero rows).
  - Linear migrations, verified up/down/up.
  - Commit trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`; never push.
- Run tests with `docker exec erp-united-exploration-dev-backend-1 python -m pytest tests/<file> -q -p no:cacheprovider`. The full suite excludes `tests/test_admin_auth.py` and `tests/test_leave_flows.py`. Its only known failures are the 2 in `test_hr_employees.py`.
- **Test users must use `@test.com` emails.** An invalid email such as `@x.test` makes `GET /hr/employees` return 500 for everyone (known bug).
- Locking helpers live in `backend/app/api/v1/endpoints/roster_common.py`: `lock_row`, `lock_row_retry`, `commit_or_409`.
- Audit: `from app.api.v1.endpoints.hr import log_audit` (signature `log_audit(db, user_id, action, resource_type, resource_id, details, request)`; `request` may be `None`).
- Notifications: `roster_svc.notify_many(db, rows)` (`app/services/roster.py`), best-effort. Set `resource_type`, `resource_id` and `event_type` so the header bell can deep-link.
- Time rules: `TIME_RULE_DEFAULTS` in `app/services/time_rules.py` (key → (default, description)) plus validation in the update function (pattern: `attendance.offline_max_hours`). Web tab: `frontend/src/components/workforce/time-rules-tab.tsx`.
- Permission seeding follows `backend/alembic/versions/d8e9f0a1b2c3_grant_attendance_edit.py` (insert-if-absent + `INSERT IGNORE` grants; `FROM DUAL`).
- Scheduler: `register_job(JobSpec(...))` in `app/services/scheduler.py`. Job functions must `session.commit()` themselves. See `_job_biometric_device_offline_alerts` for the nearest pattern.
- Approval chain engine: `instantiate_for_entity(...)` (`endpoints/approval_chains.py:686`) raises 400 when no chain exists. Entity summaries live in `_entity_summary` (~842). Finalisation branches per entity type are in `act_on_instance` (~1014, the `if instance.entity_type == ...` ladder).
- Frontend rules (no Tailwind build, check every class against index.css, state-driven nav via `App.tsx` + `sidebar.tsx` + `endpoints.ts`, tsc baseline **164** via `npx -y -p typescript@5.6.3 tsc --noEmit -p .`): see the Phase 1B environment section. Before using a Tailwind class, check the exact selector exists in `frontend/src/index.css`, with a whole-selector regex; brackets are escaped, e.g. `\.text-\\\[10px\\\]`. Missing utilities go inside `@layer utilities { }` at the end of index.css. Mirror `frontend/src/components/biometric/*` for page structure.
- Mobile app: **out of scope** for Phase 5 (follow-up: My Assets + request in `mobile/`).

## File map

| Path | Responsibility |
|---|---|
| `backend/app/models/asset.py` | `AssetCategory`, `Asset`, `AssetMaintenance`, `AssetRequest` + status constants |
| `backend/app/models/employee_asset.py` | + `asset_id`, `returned_condition`, `returned_to_id`, `allocated_by_id` (allocation log) |
| `backend/alembic/versions/<new>_asset_management.py` | tables, columns, backfill, `asset manage` perm (pick an unused 12-hex id) |
| `backend/app/services/asset_depreciation.py` | pure straight-line book value (no DB) |
| `backend/app/services/assets.py` | tag generation, all status transitions, allocation log, open-allocation queries |
| `backend/app/api/v1/endpoints/assets.py` | `/api/v1/assets`: categories, register CRUD, allocate/return/lost/repair/retire, history, QR, maintenance, summary |
| `backend/app/api/v1/endpoints/asset_requests.py` | `/api/v1/asset-requests`: employee submit/list/cancel, approver queue, decide, fulfil |
| `backend/app/api/v1/endpoints/hr.py` | legacy `/hr/employees/{id}/assets` + `/hr/assets/{id}` routed through the service |
| `backend/app/api/v1/endpoints/approval_chains.py` | `asset_request` summary + finalisation branch |
| `backend/app/models/approval_chain.py` | `ChainEntityType.ASSET_REQUEST` |
| `backend/app/api/v1/endpoints/exit_management.py` + `schemas/exit_management.py` | release block + `outstanding_assets` |
| `backend/app/services/scheduler.py`, `time_rules.py` | `asset_expiry_alerts` job, `assets.expiry_alert_days` |
| `frontend/src/components/assets/*` | Asset Management page (Register, Requests, Maintenance, Expiring) |
| `frontend/src/components/profile-view.tsx` | My Assets: request button + my requests |
| `frontend/src/components/employee-management.tsx` | Assets tab: allocate from stock, return with condition; exit release warning |

---

### Task 1: Models, migration, permission, backfill

**Files:**
- Create: `backend/app/models/asset.py`
- Modify: `backend/app/models/employee_asset.py`, `backend/app/models/__init__.py` (register the 4 models + add to `__all__`), `backend/app/models/approval_chain.py` (`ASSET_REQUEST = "asset_request"`)
- Create: `backend/alembic/versions/<new>_asset_management.py` (down_revision `c4e8a2f6b1d9`)
- Test: `backend/tests/test_asset_models.py`

Models (timestamps tz-aware UTC, plain-string status constants like `ResignationStatus`):

```python
class AssetStatus:
    IN_STOCK = "in_stock"; ALLOCATED = "allocated"; IN_REPAIR = "in_repair"
    RETIRED = "retired"; LOST = "lost"

class AssetCategory(Base):
    __tablename__ = "asset_category"
    id: int PK
    name: str(80) unique, not null
    code: str(10) unique, not null             # tag prefix, e.g. "LAP"; upper-case A-Z0-9
    default_useful_life_months: int nullable   # depreciation fallback
    is_active: bool default True
    created_at

class Asset(Base):
    __tablename__ = "asset"
    id: int PK
    asset_tag: str(32) unique, not null        # "LAP-000042"; encoded in the QR
    category_id: FK asset_category.id RESTRICT, index, not null
    name: str(150) not null                    # e.g. "Dell Latitude 5440"
    model: str(150) nullable
    serial_no: str(100) nullable, index        # NOT unique (licences / legacy data)
    status: str(16) default "in_stock", index
    location_id: FK location.id SET NULL nullable
    vendor: str(150) nullable
    invoice_no: str(64) nullable
    purchase_date: date nullable
    purchase_cost_paise: int nullable (>= 0)
    salvage_value_paise: int not null default 0
    useful_life_months: int nullable
    warranty_expiry: date nullable, index
    amc_vendor: str(150) nullable
    amc_expiry: date nullable, index
    warranty_alert_for: date nullable          # expiry date last alerted (dedupe)
    amc_alert_for: date nullable
    notes: text nullable
    created_by_id: FK user.id SET NULL
    created_at, updated_at

class AssetMaintenance(Base):
    __tablename__ = "asset_maintenance"
    id PK; asset_id FK asset.id CASCADE index
    kind: str(16)                               # "repair" | "service" | "amc_visit" | "upgrade"
    description: text not null
    vendor: str(150) nullable
    cost_paise: int not null default 0
    started_on: date not null
    completed_on: date nullable
    created_by_id FK user SET NULL; created_at

class AssetRequestStatus:
    PENDING = "pending"; APPROVED = "approved"; REJECTED = "rejected"
    FULFILLED = "fulfilled"; CANCELLED = "cancelled"

class AssetRequest(Base):
    __tablename__ = "asset_request"
    id PK
    employee_id FK employee.id CASCADE index
    category_id FK asset_category.id RESTRICT
    reason: text not null
    needed_by: date nullable
    status: str(16) default "pending", index
    approval_instance_id: FK chained_approval_instance.id SET NULL nullable
    decided_by_id FK user SET NULL; decided_at; decision_note: str(500) nullable
    fulfilled_asset_id FK asset.id SET NULL nullable
    allocation_id FK employee_asset.id SET NULL nullable
    created_at
```

`employee_asset` additions: `asset_id` (FK asset.id, RESTRICT, nullable, index), `allocated_by_id` (FK user SET NULL), `returned_condition` (str(50) nullable), `returned_to_id` (FK user SET NULL). Keep every existing column.

Migration, in this order:
1. Create `asset_category`, `asset`, `asset_maintenance`, `asset_request`.
2. Add the `employee_asset` columns + FK + index.
3. **Backfill** with `bind = op.get_bind()` in Python:
   - For each distinct `asset_type` in `employee_asset`, insert a category. Name = the type. Code = the first 3 alphanumerics upper-cased; on a collision, append a digit.
   - For each `employee_asset` row, insert an `asset`:
     - `name` = model, `serial_no`, `category_id`, `asset_tag` = `f"{code}-{id:06d}"` using the new asset id. Insert, then update the tag.
     - Status: allocation `allocated` → `allocated`, `lost` → `lost`, `returned` → `in_stock`.
   - Then set `employee_asset.asset_id`.
   - Use sqlalchemy `text()` with bound params, not f-strings, for values.
4. Seed the `asset manage` permission and grant it to HR + Super Admin (d8e9f0a1b2c3 pattern).

Downgrade: drop the grants, drop the `employee_asset` FK/index/columns, drop the 4 tables (MariaDB: drop FKs before their indexes). The backfilled data is discarded, which is acceptable because the allocation rows survive.

- [ ] **Step 1:** Write `test_asset_models.py`:
  - Create a category + asset + maintenance + request + an `employee_asset` with `asset_id`.
  - Assert the relationships load and `asset_tag` is unique (a duplicate raises `IntegrityError`).
  - Teardown deletes everything created.
- [ ] **Step 2:** Run → FAIL (import error).
- [ ] **Step 3:** Implement the models + `__init__` registration + `ChainEntityType.ASSET_REQUEST`.
- [ ] **Step 4:** Write the migration. Run `alembic upgrade head`, `downgrade -1`, `upgrade head`.
  - Before running it, insert 2 legacy `employee_asset` rows with no `asset_id` on the dev DB.
  - Check the backfill created 2 `asset` rows with matching statuses, then delete the test rows.
- [ ] **Step 5:** Run the test → PASS. `alembic heads` shows a single head.
- [ ] **Step 6:** Commit `feat(assets): asset register models, migration, backfill, asset manage perm`.

### Task 2: Depreciation (pure)

**Files:**
- Create: `backend/app/services/asset_depreciation.py`
- Test: `backend/tests/test_asset_depreciation.py`

```python
from dataclasses import dataclass
from datetime import date
from typing import Optional

DEFAULT_LIFE_MONTHS = 36

@dataclass(frozen=True)
class BookValue:
    cost_paise: int
    salvage_paise: int
    life_months: int
    months_elapsed: int
    accumulated_paise: int
    book_value_paise: int
    fully_depreciated: bool

def months_between(start: date, on: date) -> int:
    """Whole months elapsed; a month counts once its day-of-month is reached."""
    if on < start:
        return 0
    m = (on.year - start.year) * 12 + (on.month - start.month)
    if on.day < start.day:
        m -= 1
    return max(m, 0)

def book_value(*, cost_paise: Optional[int], salvage_paise: int,
               purchase_date: Optional[date], life_months: Optional[int],
               on: date) -> Optional[BookValue]:
    if cost_paise is None or purchase_date is None:
        return None
    life = life_months if life_months and life_months > 0 else DEFAULT_LIFE_MONTHS
    salvage = min(max(salvage_paise, 0), cost_paise)
    elapsed = months_between(purchase_date, on)
    depreciable = cost_paise - salvage
    acc = depreciable if elapsed >= life else (depreciable * elapsed) // life
    return BookValue(cost_paise, salvage, life, elapsed, acc,
                     cost_paise - acc, elapsed >= life)
```

Resolving the life: the caller passes `asset.useful_life_months or category.default_useful_life_months` (the function falls back to 36).

- [ ] **Step 1:** Write the tests:
  - Cost 120000_00, salvage 0, life 12, bought 2026-01-15:
    - on 2026-01-14 → elapsed 0, book = cost
    - on 2026-02-15 → elapsed 1, acc 10000_00
    - on 2027-01-15 → fully depreciated, book 0
    - on 2030-01-01 → still 0, never negative
  - Salvage 20000_00 → the floor is the salvage.
  - Salvage > cost → clamped.
  - `life_months=None` → 36.
  - Missing cost or date → `None`.
  - Integer paise only (no floats in the output).
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat(assets): straight-line depreciation`.

### Task 3: Asset service (state machine + allocation log)

**Files:**
- Create: `backend/app/services/assets.py`
- Test: `backend/tests/test_asset_service.py`

Public API (all `async`, all take `db` and the acting `User`; none commit; the caller commits with `commit_or_409`):

```python
class AssetStateError(ValueError): ...      # endpoint maps to 409

async def next_asset_tag(db, category) -> str          # f"{category.code}-{n:06d}", n = max existing suffix for that prefix + 1
async def get_asset_for_update(db, asset_id) -> Asset   # lock_row(db, Asset, asset_id) or 404 via LookupError
async def open_allocation(db, asset_id) -> EmployeeAsset | None
async def open_allocations_for_employee(db, employee_id) -> list[EmployeeAsset]
async def allocate(db, *, asset, employee, actor, issued_date=None, condition=None, remarks=None) -> EmployeeAsset
    # requires asset.status == in_stock and no open allocation; employee.status not in ("inactive",)
    # writes EmployeeAsset(status="allocated", asset_id, asset_type=category.name, model=asset.name,
    #   serial_no, identifier=asset.asset_tag, allocated_by_id, created_by_id); asset.status = allocated
async def return_asset(db, *, asset, actor, returned_date=None, condition=None, remarks=None, to_status="in_stock") -> EmployeeAsset
    # requires an open allocation; to_status in ("in_stock", "in_repair", "retired");
    # closes the allocation (status returned, returned_date default today, returned_condition, returned_to_id)
async def mark_lost(db, *, asset, actor, remarks) -> Optional[EmployeeAsset]
    # from allocated (closes allocation as "lost") or in_stock/in_repair; remarks required
async def set_status(db, *, asset, actor, to_status, remarks=None)
    # admin moves without an employee: in_stock <-> in_repair, in_stock|in_repair -> retired,
    # lost|retired -> in_stock (reinstate). Refuses when an allocation is open (use return_asset).
```

Allowed transitions (anything else raises `AssetStateError` with a readable message):

| from \ to | in_stock | allocated | in_repair | retired | lost |
|---|---|---|---|---|---|
| in_stock | – | allocate | set_status | set_status | mark_lost |
| allocated | return_asset | – | return_asset(to in_repair) | return_asset(to retired) | mark_lost |
| in_repair | set_status | – | – | set_status | mark_lost |
| retired | set_status (reinstate) | – | – | – | – |
| lost | set_status (found) | – | – | – | – |

Every transition calls `log_audit` with resource_type `"asset"`.

- [ ] **Step 1:** Write the tests (real DB, fixture creates 1 category, 2 employees, assets; teardown purges):
  - allocate → status allocated + one open allocation row with `identifier == asset_tag`
  - allocating twice → `AssetStateError`
  - allocating an `in_repair` asset → error
  - return (default) → in_stock, allocation `returned` with today's date + `returned_condition`
  - return to `in_repair` → in_repair
  - mark_lost while allocated → asset lost, allocation `lost`
  - reinstate a lost asset → in_stock
  - `set_status` on an allocated asset → error
  - `next_asset_tag` increments per prefix and ignores other prefixes
  - allocating to an inactive employee → error
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat(assets): asset state service and allocation log`.

### Task 4: Register API + legacy route refit + QR

**Files:**
- Create: `backend/app/api/v1/endpoints/assets.py` (router prefix `/assets`, registered in `app/api/v1/api.py` the way `biometric` is: **not** attendance-gated, so requests and HR work don't need a punch-in)
- Modify: `backend/app/api/v1/endpoints/hr.py` (asset section ~4105–4260), `backend/requirements.txt` (+ `segno==1.6.1`), then `docker exec … pip install segno==1.6.1`
- Test: `backend/tests/test_assets_api.py`

Endpoints (all require `asset manage` unless noted; 404 on unknown ids; `AssetStateError` → 409; serialisers return ISO dates and paise ints):

| Method | Path | Notes |
|---|---|---|
| GET/POST | `/assets/categories` | POST validates `code` with `^[A-Z0-9]{2,10}$`; duplicate name/code → 409 |
| PATCH | `/assets/categories/{id}` | rename / life / deactivate (deactivated: hidden from request form, existing assets kept) |
| GET | `/assets` | filters `status, category_id, location_id, q` (tag/name/serial/holder name, `ilike`), `expiring_within_days`, paging `limit<=200, offset`; each row includes `holder` `{employee_id, name, emp_code}` from the open allocation and `book_value_paise` |
| POST | `/assets` | `asset_tag` optional; blank → `next_asset_tag`; explicit tags validated `^[A-Z0-9-]{3,32}$` and unique (409) |
| GET | `/assets/{id}` | detail + `depreciation` (BookValue as dict) + `history` (all allocations newest first, with employee names) + `maintenance` |
| PATCH | `/assets/{id}` | edit master fields only. `status` is **not** editable here (422 if sent). Changing a warranty/AMC date leaves `*_alert_for` alone; the job compares dates |
| POST | `/assets/{id}/allocate` | `{employee_id, issued_date?, condition?, remarks?}` |
| POST | `/assets/{id}/return` | `{returned_date?, condition?, remarks?, to_status?}` |
| POST | `/assets/{id}/lost` | `{remarks}` (required, min 3 chars) |
| POST | `/assets/{id}/status` | `{to_status, remarks?}` via `set_status` |
| GET | `/assets/{id}/qr.svg` | `segno.make(asset.asset_tag, error='m').save(buf, kind='svg', scale=4, border=2)`; `media_type="image/svg+xml"` |
| GET | `/assets/by-tag/{tag}` | exact tag lookup (what scanning a label resolves to) |
| GET | `/assets/summary` | counts by status, by category, `expiring_30d` (warranty or AMC), total cost and total book value (paise) |

Lock order: every write takes `get_asset_for_update` first, then reads the allocation.

**Legacy refit** (`hr.py`, keep URLs and response shape so the existing UI keeps working until Task 9):
- `POST /hr/employees/{id}/assets` gains an optional `asset_id`.
  - With `asset_id` → `assets.allocate`.
  - Without it → create an `Asset` in a category matched (case-insensitive) or created from `asset_type`, then allocate.
- `PATCH /hr/assets/{id}` (id = the allocation id):
  - `status=returned` → `assets.return_asset`
  - `status=lost` → `assets.mark_lost`
  - other fields edit the log row only.
- `DELETE /hr/assets/{id}`:
  - Allowed only when the allocation is closed, or its asset was created on the fly and has no other allocations; else 409 "Return the asset instead".
  - Deleting an open allocation of a fly-created asset deletes both.

- [ ] **Step 1:** Write the API tests with httpx `AsyncClient` (follow `tests/test_biometric_api.py` for auth headers):
  - a non-`asset manage` user gets 403 on every route
  - category create + duplicate 409
  - asset create → auto tag `LAP-000001`-style
  - list filters (`status`, `q` by holder name)
  - allocate → GET shows the holder + history
  - double allocate 409
  - return with `to_status=in_repair`
  - lost requires remarks (422)
  - PATCH with `status` → 422
  - `qr.svg` starts with `<?xml` or `<svg` and content-type `image/svg+xml`
  - by-tag 200/404
  - summary counts
  - legacy POST without `asset_id` creates an asset + allocation
  - legacy PATCH returned → asset in_stock
  - legacy DELETE of an open register allocation → 409
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS. Run the existing tests touching `hr.py` assets: `grep -rl "assets" backend/tests`.
- [ ] **Step 5:** Commit `feat(assets): register API, QR labels, legacy routes via service`.

### Task 5: Maintenance log

**Files:**
- Modify: `backend/app/api/v1/endpoints/assets.py`
- Test: `backend/tests/test_asset_maintenance.py`

| Method | Path | Notes |
|---|---|---|
| GET | `/assets/{id}/maintenance` | newest first |
| POST | `/assets/{id}/maintenance` | `{kind, description, vendor?, cost_paise>=0, started_on, completed_on?, move_to_repair: bool=false}`. Validate the kind set and `completed_on >= started_on`. When `move_to_repair` and the asset is in_stock → `set_status(in_repair)`; when it is allocated → 409 "Return the asset first" |
| PATCH | `/assets/maintenance/{mid}` | edit fields; `{complete: true, return_to_stock: bool=true}` sets `completed_on` (default today) and, if the asset is `in_repair` and `return_to_stock`, `set_status(in_stock)` |
| DELETE | `/assets/maintenance/{mid}` | only when `cost_paise == 0` and not completed; else 409 (cost records are kept for reporting) |

Asset detail (Task 4) adds `maintenance_cost_total_paise`.

- [ ] **Step 1:** Write the tests:
  - log a service on an in_stock asset (status unchanged)
  - repair with `move_to_repair` → in_repair
  - complete → in_stock + `completed_on`
  - `move_to_repair` on an allocated asset → 409
  - `completed_on < started_on` → 422
  - deleting a costed entry → 409
  - the total cost appears in the detail
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5:** Commit `feat(assets): maintenance log`.

### Task 6: Asset requests (approval chain or direct)

**Files:**
- Create: `backend/app/api/v1/endpoints/asset_requests.py` (prefix `/asset-requests`, registered in `api.py`, not attendance-gated)
- Modify: `backend/app/api/v1/endpoints/approval_chains.py` (`_entity_summary` branch + finalisation branch in `act_on_instance`)
- Test: `backend/tests/test_asset_requests.py`

Employee routes (any authenticated user with an `Employee` row; reuse `_get_my_employee_or_404` from `hr.py`):
- `POST /asset-requests` `{category_id, reason (min 5), needed_by?}`
  - The category must be active (else 422).
  - Refuse a second `pending`/`approved` request for the same category (409).
  - Then: does an active `ApprovalChain` exist with `entity_type == "asset_request"`?
    - If yes → `instantiate_for_entity(entity_type=ASSET_REQUEST, amount_paise=0, department=emp.department, context={"category": name})`, stamp `approval_instance_id`. If the instance came back already `APPROVED` (auto-approve), set the request `approved`.
    - If no chain → leave it `pending` and notify every `asset manage` holder (`event_type="asset_request_submitted"`, `resource_type="asset_request"`).
- `GET /asset-requests/my` — own requests, newest first, with category name, status, fulfilled asset tag/name.
- `POST /asset-requests/{id}/cancel` — own, only while `pending` (409 otherwise). Cancelling a chained request also sets its instance to `ChainedApprovalStatus.CANCELLED` (and its pending step instances), so it drops out of approvers' queues.

Manager routes (`asset manage`):
- `GET /asset-requests` — filter `status`, includes employee name/code/department, `routed_via` (`"chain"`/`"direct"`).
- `POST /asset-requests/{id}/decide` `{action: approve|reject, note?}`
  - Only for **direct** requests (chained ones → 409 "Decide in the approval queue").
  - Lock the row. Not pending → 409.
  - Notify the employee.
- `POST /asset-requests/{id}/fulfil` `{asset_id, issued_date?, condition?}`
  - Request must be `approved`.
  - Asset category must equal the requested category, unless the body has `allow_other_category: true`.
  - Calls `assets.allocate`, sets `fulfilled_asset_id`, `allocation_id`, status `fulfilled`.
  - Notifies the employee.
  - Lock order: request then asset.

Chain integration in `approval_chains.py`:
- `_entity_summary`: `ASSET_REQUEST` → `{"kind": "asset_request", "id", "title": f"Asset request: {name} — {category}", "reason", "needed_by", "employee_id", "amount_paise": 0}`.
- `act_on_instance` finalisation: on `APPROVED` → request `approved` (if still pending); on `REJECTED` → `rejected`. Set `decided_by_id`/`decided_at` from the acting user. Notify `asset manage` holders on approve so someone fulfils it. The existing generic employee notification already fires.

- [ ] **Step 1:** Write the tests:
  - direct path: submit → managers notified → approve → fulfil with an in-stock asset → asset allocated, request fulfilled, employee notified
  - duplicate open request for the category → 409
  - cancel pending → cancelled; cancel approved → 409
  - fulfil with a wrong-category asset → 422, then 200 with `allow_other_category`
  - fulfil with an allocated asset → 409
  - non-manager decide → 403
  - **chain path:**
    - create a 1-step `asset_request` chain (`specific_user` approver) in the fixture
    - submit → `approval_instance_id` set and direct decide → 409
    - act approve via `/approval-chains/instances/{id}/act` → request approved
    - a second request rejected through the chain → rejected
    - the fixture deletes the chain + instances
  - the chain my-queue row shows the `asset_request` summary
- [ ] **Step 2–4:** FAIL → implement → PASS. Also run `tests/test_approval_chains*.py` to confirm no regressions.
- [ ] **Step 5:** Commit `feat(assets): employee asset requests via approval chain or direct approval`.

### Task 7: Exit clearance block

**Files:**
- Modify: `backend/app/api/v1/endpoints/exit_management.py` (`final_release` ~972; `/resign/my` ~289 and HR detail ~428 builders), `backend/app/schemas/exit_management.py` (`ExitDetailsRead.outstanding_assets: List[OutstandingAsset] = []`, `OutstandingAsset{allocation_id, asset_id, asset_tag, name, category, issued_date}`)
- Test: `backend/tests/test_exit_assets.py`

- In `final_release`, after the clearance check, call `assets.open_allocations_for_employee(db, resignation.employee_id)`.
  - If any are open → 400 `detail=f"Assets not returned: {', '.join(tag or model)}"`, same style as the pending-clearance error.
  - Legacy allocations with `asset_id IS NULL` and status `allocated` also block. They were backfilled, so this only matters for rows created between migration and deploy; harmless.
- Both exit-details builders fill `outstanding_assets`.
- When HR initiates clearance (`initiate_clearance` ~821), if the employee holds assets, add a `ClearanceItem` "Return assets: <tags>" to the clearance request whose department is "IT" (case-insensitive), or else to the first request. Purely informational; the hard gate is in release.

- [ ] **Step 1:** Write the tests:
  - employee with 1 open allocation: release → 400 naming the tag
  - return it → release 200
  - an allocation marked `lost` doesn't block
  - `/resign/my` lists the outstanding asset
  - clearance initiation adds the item
  - Fixture: resignation in `clearance` status with all clearances `cleared` (there are no existing exit tests; build the fixture from the models directly); teardown re-activates the user and deletes rows.
- [ ] **Step 2–4:** FAIL → implement → PASS. 
- [ ] **Step 5:** Commit `feat(assets): block exit release until assets are returned`.

### Task 8: Expiry alerts job + time rule

**Files:**
- Modify: `backend/app/services/time_rules.py` (`"assets.expiry_alert_days": ("30", "Alert asset managers this many days before warranty/AMC expiry")`, validated int 1–365), `backend/app/services/scheduler.py`, `frontend/src/components/workforce/time-rules-tab.tsx` (show the rule if the tab lists rules explicitly)
- Test: `backend/tests/test_asset_expiry_job.py`

Job `asset_expiry_alerts`, daily at 03:30 UTC (09:00 IST); follow `JobSpec` usage:
- `window = today + expiry_alert_days`.
- Select non-retired, non-lost assets where `warranty_expiry BETWEEN today AND window AND (warranty_alert_for IS NULL OR warranty_alert_for != warranty_expiry)`. Same for AMC.
- Group the hits into **one notification per recipient per run**: title "N assets expiring soon", message listing up to 5 tags + "and N more", `resource_type="asset"`, `event_type="asset_expiry"`. Recipients are active users holding `asset manage` (via role permissions, plus superusers).
- Stamp `warranty_alert_for = warranty_expiry` / `amc_alert_for = amc_expiry`, then commit.
- Already-expired dates are never alerted (only `>= today`).

- [ ] **Step 1:** Write the tests, calling the job fn with a session factory like the biometric offline job tests:
  - warranty in 10 days → 1 notification per manager, `warranty_alert_for` stamped
  - rerun → no new notification
  - change `warranty_expiry` to +20 days → alerts again
  - AMC in window → included
  - expired or 90 days out → ignored
  - retired asset → ignored
  - time rule validation rejects 0 and 400
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5:** Commit `feat(assets): warranty/AMC expiry alert job`.

### Task 9: Web — Asset Management page

**Files:**
- Create: `frontend/src/components/assets/asset-management.tsx` (tabs shell), `register-tab.tsx`, `asset-detail-dialog.tsx`, `asset-form-dialog.tsx`, `allocate-return-dialogs.tsx`, `requests-tab.tsx`, `maintenance-tab.tsx`, `expiring-tab.tsx`, `categories-dialog.tsx`, `asset-utils.ts` (paise ↔ ₹ formatting, status badge colours)
- Modify: `frontend/src/api/endpoints.ts` (`ASSETS` group), `frontend/src/App.tsx` (lazy import + `case 'asset-management'` + title), `frontend/src/components/sidebar.tsx` (entry next to Biometric Devices, gated on `asset manage`, mirror the biometric entry's permission check)

Page behaviour:
- **Header:** summary tiles from `/assets/summary`: In stock, Allocated, In repair, Expiring in 30 days, Book value.
- **Register:**
  - Table: tag, name, category, status badge, holder, location, warranty date (red within 30 days), book value.
  - Filters: status, category, search (debounced 300 ms).
  - Buttons: "Add asset" and "Categories".
  - Clicking a row opens the detail dialog.
- **Detail dialog:**
  - Master fields (editable), QR (`<img src={qrUrl}>`; fetch the SVG with the auth header and use an object URL, as the biometric page does for any authed binaries).
  - "Print label": opens a small print-friendly window with the QR + tag + name; `window.open` is fine in the app.
  - Actions by status: Allocate (employee picker; reuse the existing employee search component used by roster/biometric mapping), Return (condition + to_status), Mark lost (remarks), Send to repair / Retire / Reinstate.
  - Depreciation block (cost, accumulated, book value, months).
  - Allocation history timeline; maintenance list + "Log maintenance".
  - Show 409 messages verbatim in toasts.
- **Requests:**
  - Status filter (default pending + approved).
  - Direct pending rows: Approve/Reject. Chained rows show "In approval queue".
  - Approved rows: Fulfil (in-stock assets of that category, with a toggle to show all categories).
- **Maintenance:** open repairs across assets (assets in `in_repair` with their open maintenance entry) + Complete.
- **Expiring:** `/assets?expiring_within_days=30`, plus a selector for 60/90.

- [ ] **Step 1:** Implement. Check every Tailwind class with the exact-selector regex from the Environment section and add missing ones to `@layer utilities`.
- [ ] **Step 2:** tsc: count ≤ 164 (`npx -y -p typescript@5.6.3 tsc --noEmit -p .` in `frontend/`). Zero new errors in `components/assets/*`.
- [ ] **Step 3:** Smoke in the browser against the dev stack (http://localhost:5173, `admin@gmail.com` / `test@12345`):
  - create a category + asset → allocate → return to repair → log maintenance → complete → retire
  - the QR renders
  - no console errors
- [ ] **Step 4:** Commit `feat(web): asset management page`.

### Task 10: Web — employee self-service, employee tab, exit warning

**Files:**
- Modify: `frontend/src/components/profile-view.tsx` (`MyAssetsSection` ~1048), `frontend/src/components/employee-management.tsx` (Assets tab ~2452; exit release action, the code that calls `EXIT.RELEASE`), `frontend/src/api/endpoints.ts`

- **My Assets:**
  - Each asset shows its tag.
  - "Request an asset" dialog (active categories from `GET /assets/categories`; this route must allow any authenticated user for reads. **Backend change:** make `GET /assets/categories` require only authentication, and add a test in `test_assets_api.py`).
  - "My requests" list with status chips and Cancel on pending.
- **Employee management Assets tab:**
  - "Allocate" opens a picker of in-stock register assets (`/assets?status=in_stock&q=`), with a secondary "Add new asset" path that opens the asset form, then allocates.
  - Return asks for condition + to_status.
  - Rows link to the asset tag.
  - Keep the legacy free-text form only if the register picker cannot be used (no `asset manage`). HR has it, so remove the free-text form.
- **Exit:**
  - Where HR sees the resignation detail, render `outstanding_assets` as a warning list.
  - Disable "Final release" with a tooltip while the list is non-empty.
  - The backend still enforces it.

- [ ] **Step 1:** Backend: auth-only categories GET + test → PASS.
- [ ] **Step 2:** Implement the frontend. Run the class check + tsc ≤ 164.
- [ ] **Step 3:** Browser smoke:
  - an employee (`hr@gmail.com` or a `pay.*@test.com` user) requests a laptop
  - admin approves and fulfils it from the Requests tab
  - the employee sees it under My Assets
  - an exit for that employee shows the warning and cannot be released until it's returned
- [ ] **Step 4:** Commit `feat(web): asset requests self-service, allocate from register, exit warning`.

### Task 11: Verification + final review

- [ ] Backend full suite (exclusions as in Environment): all pass except the 2 known `test_hr_employees` failures. Record the count. The Phase 4 baseline was 1262.
- [ ] Migration chain: from head, `downgrade` 2 steps and `upgrade head` twice, clean. Restore the dev DB from a dump first if downgrade drops data you need: `mysqldump` before, like Phase 3.
- [ ] API E2E agent (scratchpad script, like Phase 4's `e2e_api/run.py`). It must cover:
  - every route
  - permission matrix (employee / HR / admin)
  - the full state table in Task 3 (each allowed and each forbidden transition)
  - concurrency: 2 parallel allocates of one asset → exactly one 200 and one 409, never 500; 2 parallel fulfils of one request → same
  - chain and direct request paths
  - exit block
  - expiry job idempotency
  - 0 × 5xx
- [ ] Browser QA agent (Playwright or Claude in Chrome) over Task 9/10 flows, plus phone width (400px) for My Assets.
- [ ] Final whole-branch review (superpowers:code-reviewer). Fix findings, rerun the affected tests, commit.
- [ ] Update `DEPLOYMENT.md`: `segno` dependency; `asset manage` permission; configure an `asset_request` approval chain if multi-step approval is wanted; time rule `assets.expiry_alert_days`; scheduler must be enabled for alerts.
- [ ] Commit `docs: asset management deployment notes`.

## Follow-ups (not in Phase 5)

- Mobile app: My Assets + request + scan QR to look up an asset.
- Recover a lost asset's cost through F&F (Phase 6 payroll).
- Employee "report an issue" on their asset → maintenance ticket.
- Bulk import of the asset register (fits the Phase 6 Excel import item).
- Asset depreciation report export (reports module).
