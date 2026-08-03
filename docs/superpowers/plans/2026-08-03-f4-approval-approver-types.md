# F4 — Approval-Engine Unification (extend-first) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Extend the generic configurable approval engine with the org-hierarchy approver types the roadmap needs — `functional_head` (wired to F1's Department head), `ceo`, and `md` — resolving `functional_head` by the *affected department* so downstream flows (salary revision, rostering) can route to the right head; plus fix the pre-existing `DEPT_HEAD` resolver bug and lock separation-of-duties with a test.

**Architecture:** No new tables. `ApproverType` is a plain string-constant class and the columns are `String(32)`, so new approver types are code-only. We add constants + resolver branches in `_resolve_approvers`, thread the `department` through from `instantiate_for_entity`, and add a department-based head resolver to the F1 `functional_head` service. The legacy leave/OT/revision flows are **not** migrated here (extend-first, per the approved decision) — each migrates later inside the workstream that touches it. Separation-of-duties already exists in the generic engine (`skip_if_same_person`, default on); we add a test to prove it end-to-end.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async, Alembic (hand-authored, MariaDB), Pydantic v2, pytest + httpx ASGI, Docker.

**Design decisions (locked):**
- `functional_head` resolves the **affected department's** active head (deputy fallback) via `functional_head.resolve_head_for_department`, using the `department` already passed to `instantiate_for_entity`. Existing consumers (expense/travel/shift) pass the submitter's department, so for them `functional_head` = the submitter's head; salary revision (later) will pass the *revised* employee's department.
- `ceo` → users with role `CEO` (exists). `md` → users with role `MD` (seeded here).
- Fix `DEPT_HEAD` resolver case bug (`"dept_head"` → `"DEPT_HEAD"`).
- `accounts` approver type is **out of scope** here — it ships with F6 alongside the Accounts role.
- Legacy-engine migration of leave/OT/revision is **out of scope** here (extend-first).

**Prereqs:** F1 is merged on this branch (the `functional_head` service + `Department.head_user_id` exist). Current migration head after F1 is `m1n2o3p4q5r6`. Dev stack running (`docker compose exec -T backend ...`).

---

## File Structure

- **Modify** `backend/app/services/functional_head.py` — extract `resolve_head_for_department(db, name)`; `resolve_head` delegates to it.
- **Modify** `backend/app/tests/test_functional_head.py` — tests for `resolve_head_for_department`.
- **Create** `backend/alembic/versions/n2o3p4q5r6s7_seed_md_role.py` — seed the `MD` role.
- **Modify** `backend/scripts/seed_demo_users.py` — add `MD` to the role catalog.
- **Modify** `backend/app/models/approval_chain.py` — add `FUNCTIONAL_HEAD`, `CEO`, `MD` to `ApproverType`.
- **Modify** `backend/app/api/v1/endpoints/approval_chains.py` — extend `_resolve_approvers` (new branches + `department` param + `DEPT_HEAD` fix); pass `department` at the `instantiate_for_entity` call site.
- **Create** `backend/app/tests/test_approval_approver_types.py` — DB-backed resolver tests + a SoD test.

---

### Task 1: department-based head resolver in the F1 service

**Files:**
- Modify: `backend/app/services/functional_head.py`
- Test: `backend/app/tests/test_functional_head.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/app/tests/test_functional_head.py`:

```python
@pytest.mark.asyncio
async def test_resolve_head_for_department_active_then_deputy(db):
    from app.services import functional_head as fh2
    head = await _mk_user(db, "fh_dh1@pytest.local", "Dept Head")
    deputy = await _mk_user(db, "fh_dd1@pytest.local", "Dept Deputy")
    dept = Department(name="FH_DEPT_A", is_active=True, head_user_id=head.id, deputy_head_user_id=deputy.id)
    db.add(dept)
    await db.flush()

    resolved = await fh2.resolve_head_for_department(db, "FH_DEPT_A")
    assert resolved is not None and resolved.id == head.id

    # inactive head -> deputy
    head.is_active = False
    await db.flush()
    resolved2 = await fh2.resolve_head_for_department(db, "FH_DEPT_A")
    assert resolved2 is not None and resolved2.id == deputy.id


@pytest.mark.asyncio
async def test_resolve_head_for_department_none_cases(db):
    from app.services import functional_head as fh2
    assert await fh2.resolve_head_for_department(db, None) is None
    assert await fh2.resolve_head_for_department(db, "") is None
    assert await fh2.resolve_head_for_department(db, "FH_NO_SUCH_DEPT") is None
```

- [ ] **Step 2: Run it — expect failure**

Run: `docker compose exec -T backend pytest app/tests/test_functional_head.py -k resolve_head_for_department -v`
Expected: FAIL with `AttributeError: module 'app.services.functional_head' has no attribute 'resolve_head_for_department'`.

- [ ] **Step 3: Implement — extract the department resolver, delegate from `resolve_head`**

In `backend/app/services/functional_head.py`, replace the entire `resolve_head` function with these TWO functions (keeps behavior identical, adds the reusable department resolver):

```python
async def resolve_head_for_department(db: AsyncSession, department_name: Optional[str]) -> Optional[User]:
    """Return the ACTIVE functional head of a department by name: its head
    if set and active, else its (active) deputy, else None. An inactive head
    is skipped so a deactivated account never silently becomes the approver."""
    if not department_name:
        return None
    dept = (
        await db.execute(select(Department).where(Department.name == department_name))
    ).scalars().first()
    if dept is None:
        return None
    for uid in (dept.head_user_id, dept.deputy_head_user_id):
        if uid:
            candidate = await db.get(User, uid)
            if candidate is not None and candidate.is_active:
                return candidate
    return None


async def resolve_head(db: AsyncSession, employee: Employee) -> Optional[User]:
    """Return the ACTIVE functional head governing an employee (via the
    employee's department). Delegates to resolve_head_for_department."""
    if not employee.department:
        return None
    return await resolve_head_for_department(db, employee.department)
```

- [ ] **Step 4: Run the F1 service tests — all pass (old + new)**

Run: `docker compose exec -T backend pytest app/tests/test_functional_head.py -v`
Expected: all PASS (the 6 pre-existing + 2 new). The delegation keeps `resolve_head` behavior identical.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/functional_head.py backend/app/tests/test_functional_head.py
git commit -m "feat(functional-head): add resolve_head_for_department; resolve_head delegates"
```

---

### Task 2: seed the MD (Managing Director) role

**Files:**
- Create: `backend/alembic/versions/n2o3p4q5r6s7_seed_md_role.py`
- Modify: `backend/scripts/seed_demo_users.py`

- [ ] **Step 1: Confirm the current head**

Run: `docker compose exec -T backend python -m alembic heads`
Expected: `m1n2o3p4q5r6 (head)`. If different, use that as `down_revision` below.

- [ ] **Step 2: Create the migration**

Create `backend/alembic/versions/n2o3p4q5r6s7_seed_md_role.py`:

```python
"""seed MD (Managing Director) role (F4)

Adds a top-level MD approver role used by the ceo/md approver types in the
generic approval engine (e.g. salary-revision final sign-off).

Revision ID: n2o3p4q5r6s7
Revises: m1n2o3p4q5r6
Create Date: 2026-08-03
"""
from alembic import op

revision = "n2o3p4q5r6s7"
down_revision = "m1n2o3p4q5r6"
branch_labels = None
depends_on = None

ROLE = "MD"


def upgrade():
    op.execute(
        f"""
        INSERT INTO role (name, description)
        VALUES ('{ROLE}', 'Managing Director — top-level approver')
        ON DUPLICATE KEY UPDATE description = VALUES(description);
        """
    )


def downgrade():
    # Association rows (user_roles/role_permissions) cascade via their FKs.
    op.execute(f"DELETE FROM role WHERE name = '{ROLE}';")
```

- [ ] **Step 3: Apply + verify**

Run: `docker compose exec -T backend python -m alembic upgrade head`
Then: `docker compose exec -T db mariadb -uerp_user -perp_password erp_db -e "SELECT name FROM role WHERE name='MD';"`
Expected: upgrade ends `... -> n2o3p4q5r6s7`; the query returns one row `MD`.

- [ ] **Step 4: Seed-script parity**

In `backend/scripts/seed_demo_users.py`, find the `roles_to_create = [ ... ]` list and add:
```python
            {"name": "MD", "description": "Managing Director — top-level approver"},
```
Then run `docker compose exec -T backend python -m scripts.seed_demo_users` and confirm it completes without error.

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/n2o3p4q5r6s7_seed_md_role.py backend/scripts/seed_demo_users.py
git commit -m "feat(rbac): seed MD (Managing Director) role"
```

---

### Task 3: add approver-type constants + extend `_resolve_approvers`

**Files:**
- Modify: `backend/app/models/approval_chain.py`
- Modify: `backend/app/api/v1/endpoints/approval_chains.py`

- [ ] **Step 1: Add the constants**

In `backend/app/models/approval_chain.py`, in the `class ApproverType:` block, add three constants so it reads:

```python
class ApproverType:
    REPORTING_MANAGER = "reporting_manager"
    DEPT_HEAD = "dept_head"
    ROLE = "role"
    SPECIFIC_USER = "specific_user"
    FINANCE = "finance"
    FUNCTIONAL_HEAD = "functional_head"
    CEO = "ceo"
    MD = "md"
```

- [ ] **Step 2: Extend `_resolve_approvers` (new branches + department param + DEPT_HEAD fix)**

In `backend/app/api/v1/endpoints/approval_chains.py`:

(a) Ensure these imports exist at the top of the file (add any that are missing):
```python
from app.models.employee import Employee
from app.services import functional_head as functional_head_service
```

(b) Replace the entire `_resolve_approvers` function with:

```python
async def _resolve_approvers(
    db, step, submitter_id: int, department: Optional[str] = None,
) -> List[int]:
    """Turn an approver_type into a list of user ids.

    - REPORTING_MANAGER: submitter's User.manager_id
    - DEPT_HEAD: users with the "DEPT_HEAD" role (org-wide)
    - ROLE: all users with the named role (approver_ref)
    - SPECIFIC_USER: exactly the referenced user id
    - FINANCE: users with the "Finance" role
    - FUNCTIONAL_HEAD: the active head (deputy fallback) of `department`
    - CEO: users with the "CEO" role
    - MD: users with the "MD" role
    """
    kind = step.approver_type
    if kind == ApproverType.REPORTING_MANAGER:
        row = (await db.execute(
            select(User.manager_id).where(User.id == submitter_id)
        )).scalar_one_or_none()
        return [row] if row else []
    if kind == ApproverType.DEPT_HEAD:
        stmt = select(User.id).join(User.roles).where(Role.name == "DEPT_HEAD")
        return list((await db.execute(stmt)).scalars().all())
    if kind == ApproverType.ROLE:
        role_name = step.approver_ref or ""
        stmt = select(User.id).join(User.roles).where(Role.name == role_name)
        return list((await db.execute(stmt)).scalars().all())
    if kind == ApproverType.SPECIFIC_USER:
        try:
            uid = int(step.approver_ref or "")
        except (TypeError, ValueError):
            return []
        return [uid]
    if kind == ApproverType.FINANCE:
        stmt = select(User.id).join(User.roles).where(Role.name == "Finance")
        return list((await db.execute(stmt)).scalars().all())
    if kind == ApproverType.FUNCTIONAL_HEAD:
        head = await functional_head_service.resolve_head_for_department(db, department)
        return [head.id] if head else []
    if kind == ApproverType.CEO:
        stmt = select(User.id).join(User.roles).where(Role.name == "CEO")
        return list((await db.execute(stmt)).scalars().all())
    if kind == ApproverType.MD:
        stmt = select(User.id).join(User.roles).where(Role.name == "MD")
        return list((await db.execute(stmt)).scalars().all())
    return []
```

Note: this also fixes two pre-existing case bugs — `DEPT_HEAD` now queries `"DEPT_HEAD"` (was `"dept_head"`), and `FINANCE` now queries `"Finance"` (the seeded role name; was `"finance"`).

(c) Update the call site so `functional_head` can resolve. In `instantiate_for_entity`, find the line:
```python
        approver_ids = await _resolve_approvers(db, step, submitter.id)
```
and change it to:
```python
        approver_ids = await _resolve_approvers(db, step, submitter.id, department=department)
```

(d) Grep for any OTHER callers of `_resolve_approvers` and confirm they still work with the new optional param:
Run: `docker compose exec -T backend grep -rn "_resolve_approvers(" app/`
Expected: the definition, the `instantiate_for_entity` call (now passing `department`), and possibly a `/preview` call. Any other caller not passing `department` is fine (defaults to `None` → `functional_head` yields no approver there, which is acceptable for preview). If a `/preview` caller exists and has a department in scope, pass it too.

- [ ] **Step 3: Smoke-check the module imports**

Run: `docker compose exec -T backend python -c "from app.api.v1.endpoints.approval_chains import _resolve_approvers; from app.models.approval_chain import ApproverType; print(ApproverType.FUNCTIONAL_HEAD, ApproverType.CEO, ApproverType.MD)"`
Expected: prints `functional_head ceo md`, no import errors (verifies no circular import from pulling in the functional_head service / Employee).

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/approval_chain.py backend/app/api/v1/endpoints/approval_chains.py
git commit -m "feat(approvals): functional_head/ceo/md approver types + dept_head/finance resolver fix"
```

---

### Task 4: DB-backed resolver tests + separation-of-duties test

**Files:**
- Create: `backend/app/tests/test_approval_approver_types.py`

- [ ] **Step 1: Write the tests**

Create `backend/app/tests/test_approval_approver_types.py`:

```python
import pytest
from types import SimpleNamespace

from app.models.user import User, Role
from app.models.department import Department
from app.models.approval_chain import ApproverType
from app.api.v1.endpoints.approval_chains import _resolve_approvers
from app.services.approval_engine import build_plan, ChainSpec, StepSpec, RequestContext


async def _user(db, email, name):
    u = User(email=email, full_name=name, hashed_password="x", is_active=True)
    db.add(u)
    await db.flush()
    return u


async def _user_with_role(db, email, role_name):
    role = (await db.execute(
        __import__("sqlalchemy").select(Role).where(Role.name == role_name)
    )).scalars().first()
    if role is None:
        role = Role(name=role_name, description=role_name)
        db.add(role)
        await db.flush()
    u = User(email=email, full_name=email, hashed_password="x", is_active=True, roles=[role])
    db.add(u)
    await db.flush()
    return u


def _step(approver_type, approver_ref=None):
    return SimpleNamespace(approver_type=approver_type, approver_ref=approver_ref)


@pytest.mark.asyncio
async def test_functional_head_resolves_department_head(db):
    head = await _user(db, "at_fh_head@pytest.local", "Head")
    dept = Department(name="AT_ENG", is_active=True, head_user_id=head.id)
    db.add(dept)
    await db.flush()
    submitter = await _user(db, "at_sub@pytest.local", "Sub")

    ids = await _resolve_approvers(db, _step(ApproverType.FUNCTIONAL_HEAD), submitter.id, department="AT_ENG")
    assert ids == [head.id]

    # no department context -> no approver
    ids_none = await _resolve_approvers(db, _step(ApproverType.FUNCTIONAL_HEAD), submitter.id, department=None)
    assert ids_none == []


@pytest.mark.asyncio
async def test_ceo_and_md_resolve_by_role(db):
    ceo = await _user_with_role(db, "at_ceo@pytest.local", "CEO")
    md = await _user_with_role(db, "at_md@pytest.local", "MD")
    submitter = await _user(db, "at_sub2@pytest.local", "Sub2")

    ceo_ids = await _resolve_approvers(db, _step(ApproverType.CEO), submitter.id)
    md_ids = await _resolve_approvers(db, _step(ApproverType.MD), submitter.id)
    assert ceo.id in ceo_ids
    assert md.id in md_ids


@pytest.mark.asyncio
async def test_dept_head_resolver_uses_correct_case(db):
    dh = await _user_with_role(db, "at_dh@pytest.local", "DEPT_HEAD")
    submitter = await _user(db, "at_sub3@pytest.local", "Sub3")
    ids = await _resolve_approvers(db, _step(ApproverType.DEPT_HEAD), submitter.id)
    assert dh.id in ids  # would have been empty before the case fix


def test_sod_drops_submitter_when_resolver_returns_self():
    # build_plan applies skip_if_same_person; a functional_head who is also
    # the submitter must be removed, leaving the step with no approver.
    step = StepSpec(step_order=1, approver_type=ApproverType.FUNCTIONAL_HEAD,
                    min_amount_paise=None, max_amount_paise=None)
    chain = ChainSpec(id=1, name="c", entity_type="revision", steps=(step,),
                      auto_approve_below_paise=None, skip_if_same_person=True, department=None)
    ctx = RequestContext(submitter_id=7, amount_paise=100_000)
    plan = build_plan(chain, ctx, lambda s, c: [7])  # resolver returns the submitter
    assert plan[0].approver_user_ids == []
    assert plan[0].skip_reason == "no_eligible_approver"
```

Note: `StepSpec`/`ChainSpec`/`RequestContext` field names come from `app/services/approval_engine.py` — if `StepSpec` requires additional fields without defaults, add them minimally (check the dataclass definition). The DB-backed tests use only `SimpleNamespace`, so they don't depend on `StepSpec` internals.

- [ ] **Step 2: Run the tests**

Run: `docker compose exec -T backend pytest app/tests/test_approval_approver_types.py -v`
Expected: all 4 tests PASS. (If the last test fails on `StepSpec(...)` construction, inspect `app/services/approval_engine.py` for `StepSpec`'s required fields and add them; do not change the assertion.)

- [ ] **Step 3: Commit**

```bash
git add backend/app/tests/test_approval_approver_types.py
git commit -m "test(approvals): resolver tests for functional_head/ceo/md/dept_head + SoD"
```

---

### Task 5: full verification

**Files:** none.

- [ ] **Step 1: Full suite green**

Run: `docker compose exec -T backend pytest -q`
Expected: 0 failed, 0 errors (skips fine). Report the summary line. The new F4 tests + all prior tests pass.

- [ ] **Step 2: Confirm migration head**

Run: `docker compose exec -T backend python -m alembic current`
Expected: `n2o3p4q5r6s7 (head)`.

- [ ] **Step 3: Final commit if needed**

```bash
git status
# commit anything stray with an appropriate message, else done.
```

---

## Self-Review

**Spec coverage (F4 extend-first):**
- Add functional_head/ceo/md approver types → Task 3. ✅
- functional_head resolves the affected department's head (deputy fallback, active-only) → Task 1 (`resolve_head_for_department`) + Task 3 branch + `department` threading. ✅
- ceo/md role resolution; MD role seeded → Task 2 + Task 3. ✅
- Separation-of-duties enforced → already in engine; locked by the SoD test in Task 4. ✅
- Fix DEPT_HEAD (and Finance) resolver case bug → Task 3. ✅
- Legacy migration explicitly deferred (extend-first) → not in scope, documented in header. ✅

**Placeholder scan:** No TBD/TODO. The two conditional instructions (Task 4 `StepSpec` fields; Task 3(d) other callers) point at concrete source-of-truth files, not undefined logic. ✅

**Type consistency:** `resolve_head_for_department` defined in Task 1, used in Task 3. `ApproverType.FUNCTIONAL_HEAD/CEO/MD` defined in Task 3 Step 1, used in Task 3 Step 2 + Task 4. `_resolve_approvers(db, step, submitter_id, department=None)` signature consistent between definition (Task 3) and all test calls (Task 4). Role names `"CEO"`, `"MD"`, `"DEPT_HEAD"`, `"Finance"` match the seed catalog. ✅
