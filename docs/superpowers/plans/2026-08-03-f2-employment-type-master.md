# F2 — Employment-Type Master Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Turn the free-string `Employee.employment_type` into a configurable **master table** HR manages in Settings, where each type carries a payroll profile (statutory on/off + flat-TDS rate), and make payroll read that profile instead of a hardcoded string check — so a new "Consultant (off-payroll)" type computes correctly with no code change.

**Architecture:** Keep the `employment_type` **string** column; add an `employment_type` master table keyed by `code` (`master.code == employee.employment_type`). This preserves all 12 existing read sites. Payroll's `is_contractual` decision and the contractual flat-TDS rate become lookups against the master, with a legacy fallback (`code in ("contractual","advisor")`, rate 0.10) so behavior is byte-identical for existing employees. Per-type **leave** seeding is deferred to W1; the **salary-template** link is deferred to F3.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async, Alembic (MariaDB), Pydantic v2, pytest + httpx, Docker.

**Design decisions (locked):**
- String column retained; master keyed by `code` (lowercased). No FK conversion in F2.
- Master fields: `code`, `name`, `is_on_payroll`, `statutory_enabled`, `flat_tds_rate` (nullable), `is_active`, timestamps.
- Seed the 3 existing codes so nothing breaks: `permanent` (statutory on), `contractual` (statutory off, flat 0.10), `advisor` (statutory off, flat 0.10, off-payroll).
- Master CRUD gated by `HR_WRITE = "hr employee write"` (HR owns it; Super Admin bypasses as superuser).
- Payroll reads the master via a service with a legacy fallback → regression-safe.
- Employee create/update validate `employment_type` against active master rows.

**Prereqs:** Dev stack up; current migration head `n2o3p4q5r6s7`.

---

## File Structure
- **Create** `backend/app/models/employment_type.py` — the master model.
- **Create** `backend/alembic/versions/o3p4q5r6s7t8_employment_type_master.py` — table + seed 3 rows.
- **Create** `backend/app/schemas/employment_type.py` — Pydantic schemas.
- **Create** `backend/app/services/employment_type.py` — `get_employment_type`, `is_statutory_employee`, `flat_tds_rate_for`.
- **Create** `backend/app/api/v1/endpoints/employment_types.py` — HR CRUD, registered under `/hr`.
- **Modify** `backend/app/api/v1/api.py` — register the router.
- **Modify** `backend/app/services/salary_calculator.py` — parameterize the contractual TDS rate.
- **Modify** `backend/app/api/v1/endpoints/payroll.py` — read the master at the two `is_contractual` sites.
- **Modify** `backend/app/schemas/employee.py` + `backend/app/api/v1/endpoints/hr.py` — accept + validate `employment_type` on create/update.
- **Create** `backend/app/tests/test_employment_type.py` — service + endpoint tests.

---

### Task 1: master model + migration (table + seed)

**Files:**
- Create: `backend/app/models/employment_type.py`
- Create: `backend/alembic/versions/o3p4q5r6s7t8_employment_type_master.py`

- [ ] **Step 1: Create the model**

`backend/app/models/employment_type.py`:
```python
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class EmploymentType(Base):
    __tablename__ = "employment_type"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    # `code` matches the free-string Employee.employment_type value.
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    # Informational: is this worker paid through payroll at all.
    is_on_payroll: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Behaviour: do PF/ESI/PT/regular-TDS apply (True) or is this a flat-TDS
    # contractual/advisor profile (False).
    statutory_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Flat TDS rate (fraction, e.g. 0.10) used when statutory_enabled is False.
    flat_tds_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc), nullable=False,
    )
```

- [ ] **Step 2: Confirm head, create the migration**

Run `docker compose exec -T backend python -m alembic heads` (expect `n2o3p4q5r6s7 (head)`). Then create `backend/alembic/versions/o3p4q5r6s7t8_employment_type_master.py`:
```python
"""employment type master (F2)

Configurable employment-type master keyed by `code` (matches the existing
Employee.employment_type string). Seeds the 3 existing codes so current
employees resolve unchanged.

Revision ID: o3p4q5r6s7t8
Revises: n2o3p4q5r6s7
Create Date: 2026-08-03
"""
from alembic import op
import sqlalchemy as sa

revision = "o3p4q5r6s7t8"
down_revision = "n2o3p4q5r6s7"
branch_labels = None
depends_on = None

SEED = [
    # code, name, is_on_payroll, statutory_enabled, flat_tds_rate
    ("permanent", "Permanent (Full-time)", True, True, None),
    ("contractual", "Contractual", True, False, 0.10),
    ("advisor", "Advisor / Consultant", False, False, 0.10),
]


def upgrade():
    op.create_table(
        "employment_type",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(20), nullable=False),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("is_on_payroll", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("statutory_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("flat_tds_rate", sa.Float(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), server_onupdate=sa.func.now()),
        sa.UniqueConstraint("code", name="uq_employment_type_code"),
    )
    op.create_index("ix_employment_type_code", "employment_type", ["code"], unique=False)

    t = sa.table(
        "employment_type",
        sa.column("code", sa.String), sa.column("name", sa.String),
        sa.column("is_on_payroll", sa.Boolean), sa.column("statutory_enabled", sa.Boolean),
        sa.column("flat_tds_rate", sa.Float),
    )
    op.bulk_insert(t, [
        {"code": c, "name": n, "is_on_payroll": p, "statutory_enabled": s, "flat_tds_rate": r}
        for (c, n, p, s, r) in SEED
    ])


def downgrade():
    op.drop_index("ix_employment_type_code", table_name="employment_type")
    op.drop_table("employment_type")
```

- [ ] **Step 3: Apply + verify seed**

Run `docker compose exec -T backend python -m alembic upgrade head`, then
`docker compose exec -T db mariadb -uerp_user -perp_password erp_db -e "SELECT code, statutory_enabled, flat_tds_rate FROM employment_type ORDER BY code;"`
Expected: 3 rows — advisor(0,0.1), contractual(0,0.1), permanent(1,NULL).

- [ ] **Step 4: Commit**
```bash
git add backend/app/models/employment_type.py backend/alembic/versions/o3p4q5r6s7t8_employment_type_master.py
git commit -m "feat(employment-type): master table keyed by code + seed existing 3 types"
```

---

### Task 2: resolution service

**Files:**
- Create: `backend/app/services/employment_type.py`
- Test: `backend/app/tests/test_employment_type.py`

- [ ] **Step 1: Write the failing test**

`backend/app/tests/test_employment_type.py`:
```python
import pytest
from app.services import employment_type as et_svc


@pytest.mark.asyncio
async def test_seeded_types_drive_statutory(db):
    assert await et_svc.is_statutory_employee(db, "permanent") is True
    assert await et_svc.is_statutory_employee(db, "contractual") is False
    assert await et_svc.is_statutory_employee(db, "advisor") is False


@pytest.mark.asyncio
async def test_flat_tds_rate_from_master(db):
    assert await et_svc.flat_tds_rate_for(db, "contractual") == 0.10
    assert await et_svc.flat_tds_rate_for(db, "advisor") == 0.10
    # permanent has no flat rate -> default
    assert await et_svc.flat_tds_rate_for(db, "permanent") == 0.10


@pytest.mark.asyncio
async def test_legacy_fallback_for_unknown_code(db):
    # Unknown/None code must reproduce the old string-based behaviour.
    assert await et_svc.is_statutory_employee(db, "some_new_code") is True
    assert await et_svc.is_statutory_employee(db, None) is True
    assert await et_svc.is_statutory_employee(db, "contractual") is False
    assert await et_svc.flat_tds_rate_for(db, "unknown") == 0.10
```

- [ ] **Step 2: Run — expect ModuleNotFoundError**

Run: `docker compose exec -T backend pytest app/tests/test_employment_type.py -v`
Expected: FAIL (`No module named 'app.services.employment_type'`).

- [ ] **Step 3: Implement**

`backend/app/services/employment_type.py`:
```python
"""Employment-type resolution (F2).

The employment_type master is keyed by `code`, which matches the free-string
`Employee.employment_type`. These helpers let payroll read the per-type
payroll profile with a legacy fallback so unseeded/unknown codes reproduce
the historical string-based behaviour.
"""
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employment_type import EmploymentType

# Legacy codes that historically skipped statutory deductions.
_LEGACY_NON_STATUTORY = ("contractual", "advisor")
DEFAULT_FLAT_TDS_RATE = 0.10


async def get_employment_type(db: AsyncSession, code: Optional[str]) -> Optional[EmploymentType]:
    if not code:
        return None
    return (
        await db.execute(select(EmploymentType).where(EmploymentType.code == code))
    ).scalars().first()


async def is_statutory_employee(db: AsyncSession, code: Optional[str]) -> bool:
    """True if PF/ESI/PT/regular-TDS apply. Falls back to the legacy string
    rule when no master row exists for `code`."""
    et = await get_employment_type(db, code)
    if et is None:
        return (code or "permanent") not in _LEGACY_NON_STATUTORY
    return et.statutory_enabled


async def flat_tds_rate_for(db: AsyncSession, code: Optional[str]) -> float:
    """Flat TDS rate for a non-statutory type; default 0.10 when unset."""
    et = await get_employment_type(db, code)
    if et is not None and et.flat_tds_rate is not None:
        return et.flat_tds_rate
    return DEFAULT_FLAT_TDS_RATE
```

- [ ] **Step 4: Run — all pass**

Run: `docker compose exec -T backend pytest app/tests/test_employment_type.py -v`
Expected: 3 tests PASS.

- [ ] **Step 5: Commit**
```bash
git add backend/app/services/employment_type.py backend/app/tests/test_employment_type.py
git commit -m "feat(employment-type): resolution service (statutory/flat-TDS) with legacy fallback"
```

---

### Task 3: HR CRUD endpoints

**Files:**
- Create: `backend/app/schemas/employment_type.py`
- Create: `backend/app/api/v1/endpoints/employment_types.py`
- Modify: `backend/app/api/v1/api.py`
- Test: `backend/app/tests/test_employment_type_api.py`

- [ ] **Step 1: Schemas**

`backend/app/schemas/employment_type.py`:
```python
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class EmploymentTypeBase(BaseModel):
    code: str = Field(..., min_length=1, max_length=20)
    name: str = Field(..., min_length=1, max_length=60)
    is_on_payroll: bool = True
    statutory_enabled: bool = True
    flat_tds_rate: Optional[float] = None
    is_active: bool = True


class EmploymentTypeCreate(EmploymentTypeBase):
    pass


class EmploymentTypeUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=60)
    is_on_payroll: Optional[bool] = None
    statutory_enabled: Optional[bool] = None
    flat_tds_rate: Optional[float] = None
    is_active: Optional[bool] = None


class EmploymentTypeRead(EmploymentTypeBase):
    id: int
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)
```

- [ ] **Step 2: Endpoints**

`backend/app/api/v1/endpoints/employment_types.py`:
```python
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from app.api import deps
from app.models.user import User
from app.models.employment_type import EmploymentType
from app.schemas.employment_type import (
    EmploymentTypeRead, EmploymentTypeCreate, EmploymentTypeUpdate,
)

router = APIRouter()

HR_WRITE = "hr employee write"


@router.get("/employment-types", response_model=List[EmploymentTypeRead])
async def list_employment_types(
    db: deps.DBDep,
    current_user: deps.CurrentUser,
    include_inactive: bool = Query(False),
) -> Any:
    """List employment types (any authenticated user — used by HR pickers)."""
    stmt = select(EmploymentType)
    if not include_inactive:
        stmt = stmt.where(EmploymentType.is_active.is_(True))
    stmt = stmt.order_by(EmploymentType.name)
    return (await db.execute(stmt)).scalars().all()


@router.post("/employment-types", response_model=EmploymentTypeRead)
async def create_employment_type(
    *,
    db: deps.DBDep,
    obj_in: EmploymentTypeCreate,
    current_user: User = Depends(deps.check_permissions([HR_WRITE])),
) -> Any:
    """Create an employment type (HR)."""
    code = obj_in.code.strip().lower()
    clash = (await db.execute(
        select(EmploymentType).where(EmploymentType.code == code)
    )).scalars().first()
    if clash is not None:
        raise HTTPException(status_code=400, detail=f"Employment type code '{code}' already exists")
    db_obj = EmploymentType(
        code=code, name=obj_in.name.strip(),
        is_on_payroll=obj_in.is_on_payroll, statutory_enabled=obj_in.statutory_enabled,
        flat_tds_rate=obj_in.flat_tds_rate, is_active=obj_in.is_active,
    )
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj


@router.patch("/employment-types/{et_id}", response_model=EmploymentTypeRead)
async def update_employment_type(
    *,
    db: deps.DBDep,
    et_id: int,
    obj_in: EmploymentTypeUpdate,
    current_user: User = Depends(deps.check_permissions([HR_WRITE])),
) -> Any:
    """Update an employment type (HR). `code` is immutable."""
    db_obj = await db.get(EmploymentType, et_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Employment type not found")
    data = obj_in.model_dump(exclude_unset=True)
    for field, value in data.items():
        if field == "name" and value is not None:
            value = value.strip()
        setattr(db_obj, field, value)
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj
```

- [ ] **Step 3: Register the router**

In `backend/app/api/v1/api.py`, add `employment_types` to the endpoints import tuple, then register (attendance-gated, mounted under `/hr` so paths are `/hr/employment-types`):
```python
api_router.include_router(
    employment_types.router,
    prefix="/hr",
    tags=["employment-types"],
    dependencies=[Depends(deps.verify_attendance)],
)
```

- [ ] **Step 4: Write + run endpoint tests**

`backend/app/tests/test_employment_type_api.py`:
```python
import pytest
from httpx import AsyncClient, ASGITransport

from app.core.config import settings
from app.api.deps import get_current_user, get_db, verify_attendance
from app.models.user import User, Role, Permission
from unittest.mock import AsyncMock

BASE = settings.API_V1_STR

role_hr = Role(id=1, name="HR")
role_hr.permissions = [Permission(name="hr employee write")]
role_none = Role(id=2, name="Staff")
role_none.permissions = [Permission(name="hr employee read")]
user_hr = User(id=1, email="hr@test.com", full_name="HR", is_active=True, is_superuser=False, roles=[role_hr])
user_none = User(id=2, email="s@test.com", full_name="S", is_active=True, is_superuser=False, roles=[role_none])


@pytest.mark.asyncio
async def test_create_employment_type_forbidden_without_hr_write(app):
    app.dependency_overrides[verify_attendance] = lambda: None
    app.dependency_overrides[get_current_user] = lambda: user_none
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(f"{BASE}/hr/employment-types", json={"code": "consultant", "name": "Consultant"})
            assert resp.status_code == 403, resp.text
    finally:
        app.dependency_overrides = {}


@pytest.mark.asyncio
async def test_create_employment_type_ok(app):
    created = {}

    async def override_db():
        db = AsyncMock()
        db.execute = AsyncMock(return_value=AsyncMock(scalars=lambda: AsyncMock(first=lambda: None)))
        async def _refresh(obj):
            obj.id = 99
            from datetime import datetime, timezone
            obj.created_at = datetime.now(timezone.utc)
            obj.updated_at = datetime.now(timezone.utc)
        db.commit = AsyncMock()
        db.refresh = AsyncMock(side_effect=_refresh)
        db.add = lambda obj: created.setdefault("obj", obj)
        return db

    app.dependency_overrides[verify_attendance] = lambda: None
    app.dependency_overrides[get_current_user] = lambda: user_hr
    app.dependency_overrides[get_db] = override_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(f"{BASE}/hr/employment-types",
                                 json={"code": "Consultant", "name": "Consultant", "statutory_enabled": False, "flat_tds_rate": 0.1})
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["code"] == "consultant"  # lowercased
            assert body["statutory_enabled"] is False
    finally:
        app.dependency_overrides = {}
```
Run: `docker compose exec -T backend pytest app/tests/test_employment_type_api.py -v`
Expected: 2 passed. (If the `override_db` mock for the clash-check `.scalars().first()` chain doesn't serialize, simplify by giving `db.execute` an `AsyncMock` whose `.scalars.return_value.first.return_value = None`; the goal is a 403 test + a 200 create returning a lowercased code.)

- [ ] **Step 5: Commit**
```bash
git add backend/app/schemas/employment_type.py backend/app/api/v1/endpoints/employment_types.py backend/app/api/v1/api.py backend/app/tests/test_employment_type_api.py
git commit -m "feat(employment-type): HR CRUD endpoints under /hr/employment-types"
```

---

### Task 4: wire payroll to the master (regression-safe)

**Files:**
- Modify: `backend/app/services/salary_calculator.py`
- Modify: `backend/app/api/v1/endpoints/payroll.py`

- [ ] **Step 1: Parameterize the contractual TDS rate**

In `backend/app/services/salary_calculator.py`, change `calculate_salary_contractual`'s signature to accept a rate (default preserves current behavior):
```python
def calculate_salary_contractual(
    basic_salary: float,
    paid_days: int,
    days_in_month: int = 31,
    arrear: float = 0,
    incentive: float = 0,
    tds_rate: float = 0.10,
) -> dict:
```
and change the internal `tds = roundup(gross * 0.10)` line to `tds = roundup(gross * tds_rate)`. (Leave the rest untouched.)

- [ ] **Step 2: Read the master at both payroll sites**

In `backend/app/api/v1/endpoints/payroll.py`, add the import near the other service imports:
```python
from app.services import employment_type as employment_type_service
```
At BOTH `is_contractual` sites (the generate-run loop ~line 411 and the single-line recompute ~line 812), replace:
```python
        is_contractual = (emp.employment_type or "permanent") in ("contractual", "advisor")
```
with:
```python
        is_contractual = not await employment_type_service.is_statutory_employee(db, emp.employment_type)
```
And where each site calls `calculate_salary_contractual(...)`, add the rate argument:
```python
            breakdown = calculate_salary_contractual(
                basic_salary=base_salary,
                paid_days=int(payable_days),   # or int(line.payable_days) at the second site
                days_in_month=num_days,
                tds_rate=await employment_type_service.flat_tds_rate_for(db, emp.employment_type),
            )
```
(At the single-line recompute site keep its existing `arrear=`/`incentive=` args and add `tds_rate=` alongside.)

- [ ] **Step 3: Verify parity (behavior unchanged for seeded types)**

Run a quick check that the new predicate matches the old string rule for every seeded code:
```bash
docker compose exec -T backend python -c "
import asyncio
from app.db.session import SessionLocal
from app.services import employment_type as e
async def m():
    async with SessionLocal() as db:
        for code in ['permanent','contractual','advisor',None,'weird']:
            old = (code or 'permanent') in ('contractual','advisor')
            new = not await e.is_statutory_employee(db, code)
            print(code, 'old_contractual=', old, 'new_contractual=', new, 'MATCH' if old==new else 'MISMATCH')
asyncio.run(m())
"
```
Expected: every line prints `MATCH` (permanent/None/weird → False, contractual/advisor → True).

- [ ] **Step 4: Full suite still green + payroll imports OK**

Run: `docker compose exec -T backend pytest -q` — expect 0 failed/0 errors.
Run: `docker compose exec -T backend python -c "import app.api.v1.endpoints.payroll"` — no import error.

- [ ] **Step 5: Commit**
```bash
git add backend/app/services/salary_calculator.py backend/app/api/v1/endpoints/payroll.py
git commit -m "feat(payroll): derive statutory/flat-TDS from employment_type master (regression-safe)"
```

---

### Task 5: accept + validate employment_type on employee create/update

**Files:**
- Modify: `backend/app/schemas/employee.py`
- Modify: `backend/app/api/v1/endpoints/hr.py`
- Test: `backend/app/tests/test_employment_type_api.py` (append)

- [ ] **Step 1: Add employment_type to EmployeeCreate**

In `backend/app/schemas/employee.py`, add to `EmploymentCreate`… i.e. the `EmployeeCreate` schema (which currently lacks it) a field:
```python
    employment_type: Optional[str] = None
```
(`EmployeeUpdate` already has `employment_type: Optional[str]`.)

- [ ] **Step 2: Validate against the master in create + update**

In `backend/app/api/v1/endpoints/hr.py`, add near the top imports:
```python
from app.services import employment_type as employment_type_service
```
Add a small helper (place it above `create_employee`):
```python
async def _validate_employment_type(db, code):
    """Reject an employment_type that isn't an active master code."""
    if code is None:
        return
    et = await employment_type_service.get_employment_type(db, code)
    if et is None or not et.is_active:
        raise HTTPException(status_code=400, detail=f"Unknown or inactive employment type '{code}'")
```
In `create_employee`, after building `data` and before constructing `Employee(**data)`, call:
```python
    await _validate_employment_type(db, data.get("employment_type"))
```
In `update_employee`, after computing `update_data` and before the `setattr` loop, call:
```python
    await _validate_employment_type(db, update_data.get("employment_type"))
```

- [ ] **Step 3: Append endpoint test (invalid type rejected)**

Append to `backend/app/tests/test_employment_type_api.py`:
```python
@pytest.mark.asyncio
async def test_employee_create_rejects_unknown_employment_type(app):
    from app.models.employment_type import EmploymentType
    async def override_db():
        db = AsyncMock()
        # get_employment_type -> None (unknown code)
        db.execute = AsyncMock(return_value=AsyncMock(scalars=lambda: AsyncMock(first=lambda: None)))
        return db
    app.dependency_overrides[verify_attendance] = lambda: None
    app.dependency_overrides[get_current_user] = lambda: user_hr
    app.dependency_overrides[get_db] = override_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(f"{BASE}/hr/employees", json={
                "user_id": 1, "employee_id": "E1", "department": "X", "designation": "Y",
                "employment_type": "does_not_exist",
            })
            # 400 from the employment-type validation (before any DB write)
            assert resp.status_code == 400, resp.text
    finally:
        app.dependency_overrides = {}
```
Run: `docker compose exec -T backend pytest app/tests/test_employment_type_api.py -v`
Expected: all pass (the create is rejected at validation). If `EmployeeCreate` requires other mandatory fields causing a 422 before reaching the validation, add those minimal fields to the JSON so the request body validates and the 400 comes from `_validate_employment_type`.

- [ ] **Step 4: Commit**
```bash
git add backend/app/schemas/employee.py backend/app/api/v1/endpoints/hr.py backend/app/tests/test_employment_type_api.py
git commit -m "feat(hr): accept + validate employee employment_type against the master"
```

---

### Task 6: full verification

- [ ] **Step 1:** `docker compose exec -T backend pytest -q` — report summary; expect 0 failed / 0 errors.
- [ ] **Step 2:** `docker compose exec -T backend python -m alembic current` — expect `o3p4q5r6s7t8 (head)`.
- [ ] **Step 3:** `docker compose exec -T backend python -c "from app.main import create_app; a=create_app(); print([r.path for r in a.routes if 'employment-types' in r.path])"` — expect the 3 employment-types paths.

---

## Self-Review

**Spec coverage (F2):** master table + HR CRUD (Tasks 1,3) ✅; payroll reads the profile so a new off-payroll type computes correctly with no code change (Tasks 2,4) ✅; employee create/update accept+validate the type (Task 5) ✅; regression-safe via legacy fallback + parity check (Task 4 Step 3) ✅; leave-seeding + salary-template deferred to W1/F3 (documented) ✅.

**Placeholder scan:** No TBD/TODO; conditional test-mock notes point at concrete adjustments, not undefined logic. ✅

**Type consistency:** `EmploymentType.code/statutory_enabled/flat_tds_rate` consistent across model (T1), service (T2), schema/endpoints (T3), payroll (T4). `is_statutory_employee`/`flat_tds_rate_for` signatures match between tests (T2) and payroll callers (T4). `HR_WRITE = "hr employee write"` matches the seeded HR permission. ✅
