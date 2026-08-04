"""Salary component + template master CRUD (F3).

Earnings-only structure catalogue that payroll opts into per employee.
HR-gated writes; reads open to any authenticated user (for pickers).
"""
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api import deps
from app.models.user import User
from app.models.salary_component import SalaryComponent, CANONICAL_SLOTS
from app.models.salary_template import SalaryTemplate, SalaryTemplateComponent
from app.schemas.salary_structure import (
    SalaryComponentRead, SalaryComponentCreate, SalaryComponentUpdate,
    SalaryTemplateRead, SalaryTemplateCreate, SalaryTemplateUpdate,
    SalaryTemplateComponentBase, SalaryTemplateComponentRead,
)

router = APIRouter()

HR_WRITE = "hr employee write"


def _validate_slot(slot):
    if slot is not None and slot not in CANONICAL_SLOTS:
        raise HTTPException(
            status_code=400,
            detail=f"slot must be one of {CANONICAL_SLOTS} or null",
        )


# ---------------- Salary components ----------------

@router.get("/salary-components", response_model=List[SalaryComponentRead])
async def list_salary_components(
    db: deps.DBDep,
    current_user: deps.CurrentUser,
    include_inactive: bool = Query(False),
) -> Any:
    stmt = select(SalaryComponent)
    if not include_inactive:
        stmt = stmt.where(SalaryComponent.is_active.is_(True))
    stmt = stmt.order_by(SalaryComponent.display_order, SalaryComponent.name)
    return (await db.execute(stmt)).scalars().all()


@router.post("/salary-components", response_model=SalaryComponentRead)
async def create_salary_component(
    *,
    db: deps.DBDep,
    obj_in: SalaryComponentCreate,
    current_user: User = Depends(deps.check_permissions([HR_WRITE])),
) -> Any:
    _validate_slot(obj_in.slot)
    code = obj_in.code.strip().lower()
    clash = (await db.execute(
        select(SalaryComponent).where(SalaryComponent.code == code)
    )).scalars().first()
    if clash is not None:
        raise HTTPException(status_code=400, detail=f"Component code '{code}' already exists")
    db_obj = SalaryComponent(
        code=code, name=obj_in.name.strip(), component_type=obj_in.component_type,
        slot=obj_in.slot, default_calc_method=obj_in.default_calc_method,
        default_percent=obj_in.default_percent, is_taxable=obj_in.is_taxable,
        display_order=obj_in.display_order, is_active=obj_in.is_active,
    )
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj


@router.patch("/salary-components/{comp_id}", response_model=SalaryComponentRead)
async def update_salary_component(
    *,
    db: deps.DBDep,
    comp_id: int,
    obj_in: SalaryComponentUpdate,
    current_user: User = Depends(deps.check_permissions([HR_WRITE])),
) -> Any:
    db_obj = await db.get(SalaryComponent, comp_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Salary component not found")
    data = obj_in.model_dump(exclude_unset=True)
    if "slot" in data:
        _validate_slot(data["slot"])
    for field, value in data.items():
        if field == "name" and value is not None:
            value = value.strip()
        setattr(db_obj, field, value)
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj


# ---------------- Salary templates ----------------

async def _get_template_or_404(db, template_id: int) -> SalaryTemplate:
    stmt = (
        select(SalaryTemplate)
        .where(SalaryTemplate.id == template_id)
        .options(selectinload(SalaryTemplate.components))
    )
    tmpl = (await db.execute(stmt)).scalars().first()
    if not tmpl:
        raise HTTPException(status_code=404, detail="Salary template not found")
    return tmpl


async def _assert_component_exists(db, component_id: int) -> None:
    comp = await db.get(SalaryComponent, component_id)
    if comp is None:
        raise HTTPException(
            status_code=400, detail=f"Unknown component_id {component_id}",
        )


@router.get("/salary-templates", response_model=List[SalaryTemplateRead])
async def list_salary_templates(
    db: deps.DBDep,
    current_user: deps.CurrentUser,
    include_inactive: bool = Query(False),
) -> Any:
    stmt = select(SalaryTemplate).options(selectinload(SalaryTemplate.components))
    if not include_inactive:
        stmt = stmt.where(SalaryTemplate.is_active.is_(True))
    stmt = stmt.order_by(SalaryTemplate.name)
    return (await db.execute(stmt)).scalars().all()


@router.get("/salary-templates/{template_id}", response_model=SalaryTemplateRead)
async def get_salary_template(
    db: deps.DBDep,
    current_user: deps.CurrentUser,
    template_id: int,
) -> Any:
    return await _get_template_or_404(db, template_id)


@router.post("/salary-templates", response_model=SalaryTemplateRead)
async def create_salary_template(
    *,
    db: deps.DBDep,
    obj_in: SalaryTemplateCreate,
    current_user: User = Depends(deps.check_permissions([HR_WRITE])),
) -> Any:
    code = obj_in.code.strip().lower()
    clash = (await db.execute(
        select(SalaryTemplate).where(SalaryTemplate.code == code)
    )).scalars().first()
    if clash is not None:
        raise HTTPException(status_code=400, detail=f"Template code '{code}' already exists")
    tmpl = SalaryTemplate(
        code=code, name=obj_in.name.strip(),
        description=obj_in.description, is_active=obj_in.is_active,
    )
    db.add(tmpl)
    await db.flush()
    for line in obj_in.components:
        await _assert_component_exists(db, line.component_id)
        db.add(SalaryTemplateComponent(
            template_id=tmpl.id, component_id=line.component_id,
            calc_method=line.calc_method, value=line.value,
            percent=line.percent, display_order=line.display_order,
        ))
    await db.commit()
    return await _get_template_or_404(db, tmpl.id)


@router.patch("/salary-templates/{template_id}", response_model=SalaryTemplateRead)
async def update_salary_template(
    *,
    db: deps.DBDep,
    template_id: int,
    obj_in: SalaryTemplateUpdate,
    current_user: User = Depends(deps.check_permissions([HR_WRITE])),
) -> Any:
    tmpl = await _get_template_or_404(db, template_id)
    data = obj_in.model_dump(exclude_unset=True)
    for field, value in data.items():
        if field == "name" and value is not None:
            value = value.strip()
        setattr(tmpl, field, value)
    db.add(tmpl)
    await db.commit()
    return await _get_template_or_404(db, template_id)


@router.put(
    "/salary-templates/{template_id}/components",
    response_model=SalaryTemplateRead,
)
async def set_template_components(
    *,
    db: deps.DBDep,
    template_id: int,
    lines: List[SalaryTemplateComponentBase],
    current_user: User = Depends(deps.check_permissions([HR_WRITE])),
) -> Any:
    """Replace the template's component set wholesale (idempotent editor)."""
    tmpl = await _get_template_or_404(db, template_id)
    seen: set[int] = set()
    for line in lines:
        if line.component_id in seen:
            raise HTTPException(
                status_code=400,
                detail=f"Duplicate component_id {line.component_id} in template",
            )
        seen.add(line.component_id)
        await _assert_component_exists(db, line.component_id)
    # Clear + re-add (cascade delete-orphan handles removals).
    for existing in list(tmpl.components):
        await db.delete(existing)
    await db.flush()
    for line in lines:
        db.add(SalaryTemplateComponent(
            template_id=template_id, component_id=line.component_id,
            calc_method=line.calc_method, value=line.value,
            percent=line.percent, display_order=line.display_order,
        ))
    await db.commit()
    return await _get_template_or_404(db, template_id)
