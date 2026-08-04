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
