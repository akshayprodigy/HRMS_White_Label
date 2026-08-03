# F1 — Functional Head Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every Department a functional **head** (and optional **deputy**), and expose a reusable resolution service so downstream features (rostering, salary revision, approvals) can answer "who is this employee's head?" and "who is on my team?".

**Architecture:** Add `head_user_id` + `deputy_head_user_id` FK columns to the existing `department` table (both nullable, `ON DELETE SET NULL`). Employees are grouped by the existing free-text `Employee.department` string, which matches `Department.name` — the established team key across the codebase (bulk shift-assign, attendance filters, department rename all key on it). A new `functional_head` service resolves head↔team using that key. A thin `/functional-head` router assigns heads (HR/Super Admin only) and serves resolution reads. **No new role is created** — the existing `DEPT_HEAD` role already carries the functional-head permission set; "functional head" is operationally *a user assigned as head/deputy on a department*.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 (async, typed `Mapped[...]`), Alembic (hand-authored migrations), MariaDB, Pydantic v2, pytest + httpx ASGI. Runs in Docker.

**Design decisions locked (from scope + code audit):**
- The "function" is the **Department** (not `FunctionalArea`, which stays a project-classification taxonomy).
- Reuse `DEPT_HEAD` role; do **not** rename it (avoids breaking seed/string references). UI may label it "Functional Head."
- Assigning a head is an **HR / Super Admin** action, gated by a new `"department head write"` permission.
- A user is a functional head of a department if they are its `head_user_id` **or** `deputy_head_user_id`.

---

## File Structure

- **Modify** `backend/app/models/department.py` — add `head_user_id`, `deputy_head_user_id` columns + `head`/`deputy_head` relationships.
- **Create** `backend/alembic/versions/m1n2o3p4q5r6_functional_head_on_department.py` — columns + FKs + the new permission granted to HR/Super Admin.
- **Create** `backend/app/services/functional_head.py` — `resolve_head`, `resolve_team`, `is_head_of`.
- **Modify** `backend/app/schemas/department.py` — add head fields to `DepartmentRead`; add `DepartmentHeadUpdate`, `TeamMemberRead`.
- **Create** `backend/app/api/v1/endpoints/functional_head.py` — assign-head + resolution endpoints.
- **Modify** `backend/app/api/v1/api.py` — register the new router under `/functional-head`.
- **Modify** `backend/scripts/seed_demo_users.py` — add the permission + grant to HR/Super Admin (fresh-install parity with the migration).
- **Create** `backend/app/tests/test_functional_head.py` — service integration tests (real `db` fixture).
- **Create** `backend/tests/test_functional_head_api.py` — endpoint permission-gate tests (dependency-override mocks).

**Migration chain note:** current single head is `l9g0h1i2j3k4`. The new migration's `down_revision` is `"l9g0h1i2j3k4"`. If a later migration was added first, re-point `down_revision` to the true head (`docker compose exec backend python -m alembic heads`).

---

### Task 1: Add head/deputy columns to the Department model

**Files:**
- Modify: `backend/app/models/department.py`

- [ ] **Step 1: Replace the model file with the head/deputy-augmented version**

Replace the entire contents of `backend/app/models/department.py` with:

```python
from typing import TYPE_CHECKING, Optional

from sqlalchemy import String, Integer, Boolean, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base

if TYPE_CHECKING:
    from app.models.user import User


class Department(Base):
    """
    Department model for organizing employees.

    A department may have a functional head and an optional deputy head.
    Employees belong to a department via the free-text `Employee.department`
    string, which matches `Department.name` (the established team key).
    """
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    head_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True
    )
    deputy_head_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Two FKs to user -> foreign_keys must be explicit (mirrors Employee).
    head: Mapped[Optional["User"]] = relationship("User", foreign_keys=[head_user_id])
    deputy_head: Mapped[Optional["User"]] = relationship("User", foreign_keys=[deputy_head_user_id])
```

- [ ] **Step 2: Verify the model imports cleanly**

Run: `docker compose exec backend python -c "from app.models.department import Department; print(Department.__table__.c.keys())"`
Expected: prints a list including `head_user_id` and `deputy_head_user_id`, e.g. `['id', 'name', 'description', 'is_active', 'head_user_id', 'deputy_head_user_id']`. No import/mapper errors.

- [ ] **Step 3: Commit**

```bash
git add backend/app/models/department.py
git commit -m "feat(dept): add functional head + deputy columns to Department model"
```

---

### Task 2: Alembic migration — columns, FKs, and the new permission

**Files:**
- Create: `backend/alembic/versions/m1n2o3p4q5r6_functional_head_on_department.py`

- [ ] **Step 1: Confirm the current migration head**

Run: `docker compose exec backend python -m alembic heads`
Expected: a single head `l9g0h1i2j3k4 (head)`. If it differs, use that value as `down_revision` in Step 2.

- [ ] **Step 2: Create the migration file**

Create `backend/alembic/versions/m1n2o3p4q5r6_functional_head_on_department.py`:

```python
"""functional head: head/deputy on department + permission (F1)

Adds head_user_id + deputy_head_user_id FKs to the department table, and a
'department head write' permission granted to the HR and Super Admin roles.

Revision ID: m1n2o3p4q5r6
Revises: l9g0h1i2j3k4
Create Date: 2026-08-03
"""
from alembic import op
import sqlalchemy as sa


revision = "m1n2o3p4q5r6"
down_revision = "l9g0h1i2j3k4"
branch_labels = None
depends_on = None

PERM = "department head write"


def upgrade():
    op.add_column("department", sa.Column("head_user_id", sa.Integer(), nullable=True))
    op.add_column("department", sa.Column("deputy_head_user_id", sa.Integer(), nullable=True))
    op.create_index("ix_department_head_user_id", "department", ["head_user_id"])
    op.create_index("ix_department_deputy_head_user_id", "department", ["deputy_head_user_id"])
    op.create_foreign_key(
        "fk_department_head_user", "department", "user",
        ["head_user_id"], ["id"], ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_department_deputy_head_user", "department", "user",
        ["deputy_head_user_id"], ["id"], ondelete="SET NULL",
    )

    op.execute(
        f"""
        INSERT INTO permission (name, description)
        VALUES ('{PERM}', 'Assign functional head / deputy to a department')
        ON DUPLICATE KEY UPDATE description = VALUES(description);
        """
    )
    op.execute(
        f"""
        INSERT IGNORE INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id
        FROM role r
        JOIN permission p ON p.name = '{PERM}'
        WHERE r.name IN ('HR', 'Super Admin');
        """
    )


def downgrade():
    op.execute(
        f"""
        DELETE rp FROM role_permissions rp
        JOIN permission p ON p.id = rp.permission_id
        WHERE p.name = '{PERM}';
        """
    )
    op.execute(f"DELETE FROM permission WHERE name = '{PERM}';")
    op.drop_constraint("fk_department_deputy_head_user", "department", type_="foreignkey")
    op.drop_constraint("fk_department_head_user", "department", type_="foreignkey")
    op.drop_index("ix_department_deputy_head_user_id", table_name="department")
    op.drop_index("ix_department_head_user_id", table_name="department")
    op.drop_column("department", "deputy_head_user_id")
    op.drop_column("department", "head_user_id")
```

- [ ] **Step 3: Apply the migration**

Run: `docker compose exec backend python -m alembic upgrade head`
Expected: output ends with `Running upgrade l9g0h1i2j3k4 -> m1n2o3p4q5r6`. No errors.

- [ ] **Step 4: Verify columns and permission landed**

Run:
```bash
docker compose exec backend python -c "import asyncio; from sqlalchemy import text; from app.db.session import SessionLocal; \
async def m():\
 import asyncio;\
 s=SessionLocal();\
 async with s as db:\
  print((await db.execute(text('SHOW COLUMNS FROM department'))).fetchall());\
  print((await db.execute(text(\"SELECT name FROM permission WHERE name='department head write'\"))).fetchall())\
; asyncio.run(m())"
```
Expected: the `department` columns list includes `head_user_id` and `deputy_head_user_id`; the permission query returns one row `('department head write',)`.
(If the inline heredoc is awkward in your shell, instead run `docker compose exec backend python -m alembic current` and confirm it prints `m1n2o3p4q5r6 (head)`.)

- [ ] **Step 5: Verify downgrade/upgrade round-trips (safety check)**

Run: `docker compose exec backend python -m alembic downgrade -1 && docker compose exec backend python -m alembic upgrade head`
Expected: downgrade removes the columns/permission without error, upgrade re-applies. Ends at `m1n2o3p4q5r6`.

- [ ] **Step 6: Commit**

```bash
git add backend/alembic/versions/m1n2o3p4q5r6_functional_head_on_department.py
git commit -m "feat(dept): migration for functional-head columns + department-head-write permission"
```

---

### Task 3: Functional-head resolution service

**Files:**
- Create: `backend/app/services/functional_head.py`
- Test: `backend/app/tests/test_functional_head.py`

- [ ] **Step 1: Write the failing integration test**

Create `backend/app/tests/test_functional_head.py`:

```python
import pytest
from datetime import date

from app.models.user import User
from app.models.department import Department
from app.models.employee import Employee
from app.services import functional_head as fh


async def _mk_user(db, email, name):
    u = User(email=email, full_name=name, hashed_password="x", is_active=True)
    db.add(u)
    await db.flush()
    return u


async def _mk_employee(db, user, dept, status="active"):
    e = Employee(
        employee_id=f"E{user.id}",
        user_id=user.id,
        department=dept,
        designation="Engineer",
        status=status,
        date_of_joining=date(2024, 1, 1),
        salary=0.0,
        employment_type="permanent",
    )
    db.add(e)
    await db.flush()
    return e


@pytest.mark.asyncio
async def test_resolve_head_returns_head_then_deputy(db):
    head = await _mk_user(db, "fh_head@pytest.local", "Head One")
    deputy = await _mk_user(db, "fh_dep@pytest.local", "Deputy One")
    emp_user = await _mk_user(db, "fh_emp@pytest.local", "Emp One")
    dept = Department(name="FH_ENG", is_active=True, head_user_id=head.id, deputy_head_user_id=deputy.id)
    db.add(dept)
    await db.flush()
    emp = await _mk_employee(db, emp_user, "FH_ENG")

    resolved = await fh.resolve_head(db, emp)
    assert resolved is not None and resolved.id == head.id

    # With no primary head, falls back to deputy
    dept.head_user_id = None
    await db.flush()
    resolved2 = await fh.resolve_head(db, emp)
    assert resolved2 is not None and resolved2.id == deputy.id


@pytest.mark.asyncio
async def test_resolve_head_none_when_unassigned_or_no_dept(db):
    emp_user = await _mk_user(db, "fh_emp2@pytest.local", "Emp Two")
    dept = Department(name="FH_OPS", is_active=True)
    db.add(dept)
    await db.flush()
    emp = await _mk_employee(db, emp_user, "FH_OPS")
    assert await fh.resolve_head(db, emp) is None


@pytest.mark.asyncio
async def test_resolve_team_returns_active_members_of_headed_depts(db):
    head = await _mk_user(db, "fh_head3@pytest.local", "Head Three")
    dept = Department(name="FH_QA", is_active=True, head_user_id=head.id)
    db.add(dept)
    await db.flush()
    u1 = await _mk_user(db, "fh_m1@pytest.local", "M1")
    u2 = await _mk_user(db, "fh_m2@pytest.local", "M2")
    u3 = await _mk_user(db, "fh_m3@pytest.local", "M3")
    await _mk_employee(db, u1, "FH_QA")
    await _mk_employee(db, u2, "FH_QA")
    await _mk_employee(db, u3, "FH_QA", status="inactive")  # excluded

    team = await fh.resolve_team(db, head)
    emails = {m.user.full_name for m in team}
    assert emails == {"M1", "M2"}


@pytest.mark.asyncio
async def test_resolve_team_empty_when_heads_nothing(db):
    nobody = await _mk_user(db, "fh_nobody@pytest.local", "Nobody")
    assert await fh.resolve_team(db, nobody) == []


@pytest.mark.asyncio
async def test_is_head_of_true_for_head_and_deputy(db):
    head = await _mk_user(db, "fh_h4@pytest.local", "H4")
    deputy = await _mk_user(db, "fh_d4@pytest.local", "D4")
    other = await _mk_user(db, "fh_o4@pytest.local", "O4")
    dept = Department(name="FH_DES", is_active=True, head_user_id=head.id, deputy_head_user_id=deputy.id)
    db.add(dept)
    await db.flush()
    emp_user = await _mk_user(db, "fh_e4@pytest.local", "E4")
    emp = await _mk_employee(db, emp_user, "FH_DES")

    assert await fh.is_head_of(db, head, emp) is True
    assert await fh.is_head_of(db, deputy, emp) is True
    assert await fh.is_head_of(db, other, emp) is False
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `docker compose exec backend pytest app/tests/test_functional_head.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.functional_head'` (or `AttributeError` on `fh.resolve_head`).

- [ ] **Step 3: Implement the service**

Create `backend/app/services/functional_head.py`:

```python
"""Functional-head resolution (F1).

A 'functional head' is the user set as head_user_id (or deputy_head_user_id)
on a Department. Employees are grouped by the free-text `Employee.department`
string, which matches `Department.name` — the established team key.
"""
from typing import Optional

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.department import Department
from app.models.employee import Employee
from app.models.user import User


async def resolve_head(db: AsyncSession, employee: Employee) -> Optional[User]:
    """Return the functional head governing an employee: the department's
    head if set, else its deputy, else None."""
    if not employee.department:
        return None
    dept = (
        await db.execute(select(Department).where(Department.name == employee.department))
    ).scalars().first()
    if dept is None:
        return None
    if dept.head_user_id:
        return await db.get(User, dept.head_user_id)
    if dept.deputy_head_user_id:
        return await db.get(User, dept.deputy_head_user_id)
    return None


async def resolve_team(db: AsyncSession, head_user: User) -> list[Employee]:
    """Return active employees across every department this user heads (as
    head or deputy). Empty list if the user heads nothing. The `user`
    relationship is eager-loaded for display."""
    dept_names = (
        await db.execute(
            select(Department.name).where(
                or_(
                    Department.head_user_id == head_user.id,
                    Department.deputy_head_user_id == head_user.id,
                )
            )
        )
    ).scalars().all()
    if not dept_names:
        return []
    rows = (
        await db.execute(
            select(Employee)
            .options(selectinload(Employee.user))
            .where(
                Employee.department.in_(dept_names),
                Employee.status == "active",
            )
        )
    ).scalars().all()
    return list(rows)


async def is_head_of(db: AsyncSession, head_user: User, employee: Employee) -> bool:
    """True if head_user is the head OR deputy of the employee's department."""
    if not employee.department:
        return False
    dept = (
        await db.execute(select(Department).where(Department.name == employee.department))
    ).scalars().first()
    if dept is None:
        return False
    return head_user.id in (dept.head_user_id, dept.deputy_head_user_id)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `docker compose exec backend pytest app/tests/test_functional_head.py -v`
Expected: all 5 tests PASS. (If an `Employee(...)` insert fails on a NOT NULL column not set in `_mk_employee`, add that column to `_mk_employee` with a minimal valid value — the model file `app/models/employee.py` is the source of truth for required columns.)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/functional_head.py backend/app/tests/test_functional_head.py
git commit -m "feat(functional-head): resolution service (resolve_head/resolve_team/is_head_of) + tests"
```

---

### Task 4: Schemas + assign-head endpoint

**Files:**
- Modify: `backend/app/schemas/department.py`
- Create: `backend/app/api/v1/endpoints/functional_head.py`
- Test: `backend/tests/test_functional_head_api.py`

- [ ] **Step 1: Extend the department schemas**

Replace the entire contents of `backend/app/schemas/department.py` with:

```python
from typing import Optional

from pydantic import BaseModel, ConfigDict


class DepartmentBase(BaseModel):
    name: str
    description: Optional[str] = None
    is_active: bool = True


class DepartmentCreate(DepartmentBase):
    pass


class DepartmentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class DepartmentRead(DepartmentBase):
    id: int
    head_user_id: Optional[int] = None
    deputy_head_user_id: Optional[int] = None
    model_config = ConfigDict(from_attributes=True)


class DepartmentHeadUpdate(BaseModel):
    """Assign/clear the functional head and/or deputy of a department.
    Only provided fields are changed; pass null to clear."""
    head_user_id: Optional[int] = None
    deputy_head_user_id: Optional[int] = None


class TeamMemberRead(BaseModel):
    employee_id: str
    user_id: int
    full_name: Optional[str] = None
    department: str
    designation: Optional[str] = None
    status: str
    model_config = ConfigDict(from_attributes=True)
```

- [ ] **Step 2: Write the failing endpoint test (permission gate + happy path)**

Create `backend/tests/test_functional_head_api.py`:

```python
import pytest
from httpx import AsyncClient, ASGITransport

from app.main import create_app
from app.core.config import settings
from app.api.deps import get_current_user, get_db
from app.models.user import User, Role, Permission
from app.models.department import Department
from unittest.mock import MagicMock, AsyncMock

BASE = settings.API_V1_STR

role_with_perm = Role(id=1, name="HR")
role_with_perm.permissions = [Permission(name="department head write")]

role_no_perm = Role(id=2, name="Staff")
role_no_perm.permissions = [Permission(name="hr employee read")]

user_with_perm = User(id=1, email="hr@test.com", full_name="HR", is_active=True, roles=[role_with_perm])
user_no_perm = User(id=2, email="staff@test.com", full_name="Staff", is_active=True, roles=[role_no_perm])


@pytest.fixture
def app():
    return create_app()


@pytest.mark.asyncio
async def test_assign_head_forbidden_without_permission(app):
    app.dependency_overrides[get_current_user] = lambda: user_no_perm

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.patch(f"{BASE}/functional-head/departments/1", json={"head_user_id": 5})
        assert resp.status_code == 403

    app.dependency_overrides = {}


@pytest.mark.asyncio
async def test_assign_head_sets_head_user_id(app):
    dept = Department(id=1, name="Engineering", is_active=True)

    def override_user():
        return user_with_perm

    async def override_db():
        db = AsyncMock()
        db.get = AsyncMock(return_value=dept)  # Department lookup AND user-exists check
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        return db

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_db] = override_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.patch(f"{BASE}/functional-head/departments/1", json={"head_user_id": 5})
        assert resp.status_code == 200, resp.text
        assert resp.json()["head_user_id"] == 5

    app.dependency_overrides = {}


@pytest.mark.asyncio
async def test_assign_head_404_when_department_missing(app):
    def override_user():
        return user_with_perm

    async def override_db():
        db = AsyncMock()
        db.get = AsyncMock(return_value=None)
        return db

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_db] = override_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.patch(f"{BASE}/functional-head/departments/999", json={"head_user_id": 5})
        assert resp.status_code == 404

    app.dependency_overrides = {}
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `docker compose exec backend pytest tests/test_functional_head_api.py -v`
Expected: FAIL — the route does not exist yet, so `test_assign_head_sets_head_user_id` returns 404 for the wrong reason and the assertion on `head_user_id == 5` fails (or all three fail on routing). This confirms the endpoint is missing.

- [ ] **Step 4: Create the endpoint module**

Create `backend/app/api/v1/endpoints/functional_head.py`:

```python
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException

from app.api import deps
from app.models.user import User
from app.models.department import Department
from app.models.employee import Employee
from app.schemas.department import DepartmentRead, DepartmentHeadUpdate, TeamMemberRead
from app.services import functional_head as fh_service

router = APIRouter()

PERM_HEAD_WRITE = "department head write"


@router.patch("/departments/{dept_id}", response_model=DepartmentRead)
async def assign_department_head(
    *,
    db: deps.DBDep,
    dept_id: int,
    payload: DepartmentHeadUpdate,
    current_user: User = Depends(deps.check_permissions([PERM_HEAD_WRITE])),
) -> Any:
    """Assign or clear a department's functional head and/or deputy head.
    Only provided fields change; pass null to clear. HR / Super Admin only."""
    dept = await db.get(Department, dept_id)
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")

    data = payload.model_dump(exclude_unset=True)
    for field in ("head_user_id", "deputy_head_user_id"):
        if field not in data:
            continue
        value = data[field]
        if value is not None:
            u = await db.get(User, value)
            if u is None:
                raise HTTPException(status_code=400, detail=f"User {value} not found")
        setattr(dept, field, value)

    db.add(dept)
    await db.commit()
    await db.refresh(dept)
    return dept


@router.get("/my-team", response_model=List[TeamMemberRead])
async def my_team(db: deps.DBDep, current_user: deps.CurrentUser) -> Any:
    """Active employees in every department the current user heads."""
    team = await fh_service.resolve_team(db, current_user)
    return [
        TeamMemberRead(
            employee_id=e.employee_id,
            user_id=e.user_id,
            full_name=(e.user.full_name if e.user else None),
            department=e.department,
            designation=e.designation,
            status=e.status,
        )
        for e in team
    ]


@router.get("/of-employee/{employee_id}")
async def head_of_employee(
    employee_id: int, db: deps.DBDep, current_user: deps.CurrentUser
) -> Any:
    """Resolve the functional head governing a given employee."""
    emp = await db.get(Employee, employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    head = await fh_service.resolve_head(db, emp)
    if head is None:
        return {"employee_id": employee_id, "head_user_id": None, "head_name": None}
    return {"employee_id": employee_id, "head_user_id": head.id, "head_name": head.full_name}
```

- [ ] **Step 5: Register the router**

In `backend/app/api/v1/api.py`, add `functional_head` to the endpoints import tuple (alongside `admin, leave, hr, ...`):

```python
from app.api.v1.endpoints import (
    auth, health, attendance, timesheets,
    tasks, admin, leave, hr, projects, payroll,
    functional_head,
)
```
(Keep the existing names in the tuple; just append `functional_head`. The exact existing import list is longer — add the name without removing others.)

Then add the router registration next to the other `api_router.include_router(...)` calls:

```python
api_router.include_router(
    functional_head.router,
    prefix="/functional-head",
    tags=["functional-head"],
    dependencies=[Depends(deps.verify_attendance)],
)
```

- [ ] **Step 6: Run the endpoint tests to verify they pass**

Run: `docker compose exec backend pytest tests/test_functional_head_api.py -v`
Expected: all 3 tests PASS (403 without perm, 200 + `head_user_id == 5` with perm, 404 for missing department).

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/department.py backend/app/api/v1/endpoints/functional_head.py backend/app/api/v1/api.py backend/tests/test_functional_head_api.py
git commit -m "feat(functional-head): assign-head + resolution endpoints under /functional-head"
```

---

### Task 5: Seed-script parity for the new permission

**Files:**
- Modify: `backend/scripts/seed_demo_users.py`

- [ ] **Step 1: Add the permission to the catalog**

In `backend/scripts/seed_demo_users.py`, inside the `perms_to_create = [ ... ]` list, add:

```python
            {"name": "department head write", "description": "Assign functional head / deputy to a department"},
```

- [ ] **Step 2: Grant it to HR and Super Admin**

Find the block that assigns `db_roles["HR"].permissions = [ ... ]` and append:

```python
            db_perms["department head write"],
```

Do the same in the `db_roles["Super Admin"].permissions = [ ... ]` block (append the same line).

- [ ] **Step 3: Run the seed script (idempotent) and verify no error**

Run: `docker compose exec backend python -m scripts.seed_demo_users`
Expected: completes without error (upserts are idempotent). If your local DB already has demo users, it updates in place.

- [ ] **Step 4: Commit**

```bash
git add backend/scripts/seed_demo_users.py
git commit -m "chore(seed): grant 'department head write' to HR + Super Admin"
```

---

### Task 6: Full-suite verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full backend test suite**

Run: `docker compose exec backend pytest -q`
Expected: the two new test files pass and no previously-passing test regresses. (Pre-existing unrelated failures, if any, should match the state before this task — note them but do not fix here.)

- [ ] **Step 2: Sanity-check the OpenAPI surface exposes the new routes**

Run: `docker compose exec backend python -c "from app.main import create_app; app=create_app(); print([r.path for r in app.routes if 'functional-head' in r.path])"`
Expected: prints the three paths — `.../functional-head/departments/{dept_id}`, `.../functional-head/my-team`, `.../functional-head/of-employee/{employee_id}`.

- [ ] **Step 3: Final commit (if anything uncommitted)**

```bash
git status
# if clean, nothing to do; otherwise:
git add -A && git commit -m "chore(functional-head): F1 finalize"
```

---

## Self-Review

**Spec coverage (F1 requirements):**
- "Add head (+ optional deputy) to Department" → Tasks 1, 2. ✅
- "Head governs their team's roster/revisions/approvals" → resolution service consumed downstream; `resolve_team`/`resolve_head`/`is_head_of` in Task 3. ✅
- "HR assigns head/deputy in Settings" → `PATCH /functional-head/departments/{id}`, gated by `department head write` (HR/Super Admin), Tasks 2, 4, 5. ✅
- "resolve_team(head)→employees; resolve_head(employee)→head" acceptance → Task 3 tests assert exactly this, including the head-with-no-assignment→none case. ✅
- Deviation from scope doc (no new "Functional Head" role — reuse `DEPT_HEAD`) is documented in the header rationale. ✅

**Placeholder scan:** No TBD/TODO. Every code step has complete code. The only conditional instruction (Task 3 Step 4 "add a missing NOT NULL column") points at a concrete source of truth (`app/models/employee.py`) rather than leaving logic undefined. ✅

**Type consistency:** `head_user_id`/`deputy_head_user_id` used identically in model (Task 1), migration (Task 2), schema (Task 4), service (Task 3), endpoint (Task 4). `resolve_head`/`resolve_team`/`is_head_of` signatures match between the test (Task 3 Step 1) and impl (Task 3 Step 3). `TeamMemberRead`/`DepartmentHeadUpdate` defined in Task 4 Step 1 before use in Task 4 Step 4. Permission string `"department head write"` identical across migration, endpoint constant, seed, and tests. ✅
