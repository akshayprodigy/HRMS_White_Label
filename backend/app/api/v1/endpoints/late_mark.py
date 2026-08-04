"""Late-mark rules engine endpoints (W9)."""
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from app.api import deps
from app.models.user import User
from app.models.late_mark import LateMarkRule, LateMarkDeduction
from app.schemas.late_mark import (
    LateMarkRuleRead, LateMarkRuleCreate, LateMarkRuleUpdate, LateMarkDeductionRead,
)
from app.services import late_mark as late_mark_service

router = APIRouter()

PERM = "late mark rule write"


@router.get("/rules", response_model=List[LateMarkRuleRead])
async def list_rules(db: deps.DBDep, current_user: deps.CurrentUser) -> Any:
    return (await db.execute(
        select(LateMarkRule).order_by(LateMarkRule.name)
    )).scalars().all()


@router.post("/rules", response_model=LateMarkRuleRead)
async def create_rule(
    *, db: deps.DBDep, obj_in: LateMarkRuleCreate,
    current_user: User = Depends(deps.check_permissions([PERM])),
) -> Any:
    if obj_in.scope == "shift" and not obj_in.shift_template_id:
        raise HTTPException(status_code=400, detail="shift-scoped rule needs a shift_template_id")
    clash = (await db.execute(
        select(LateMarkRule).where(LateMarkRule.name == obj_in.name)
    )).scalars().first()
    if clash:
        raise HTTPException(status_code=400, detail=f"Rule '{obj_in.name}' already exists")
    obj = LateMarkRule(**obj_in.model_dump(), created_by_id=current_user.id)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.patch("/rules/{rule_id}", response_model=LateMarkRuleRead)
async def update_rule(
    *, db: deps.DBDep, rule_id: int, obj_in: LateMarkRuleUpdate,
    current_user: User = Depends(deps.check_permissions([PERM])),
) -> Any:
    obj = await db.get(LateMarkRule, rule_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Rule not found")
    for field, value in obj_in.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/rules/{rule_id}")
async def deactivate_rule(
    *, db: deps.DBDep, rule_id: int,
    current_user: User = Depends(deps.check_permissions([PERM])),
) -> Any:
    obj = await db.get(LateMarkRule, rule_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Rule not found")
    obj.is_active = False
    db.add(obj)
    await db.commit()
    return {"message": "Rule deactivated"}


@router.post("/process")
async def process_month(
    *, db: deps.DBDep, year: int = Query(...), month: int = Query(..., ge=1, le=12),
    current_user: User = Depends(deps.check_permissions([PERM])),
) -> Any:
    """Compute late-mark deductions for a month (CL→PL→LOP cascade).
    Idempotent — reverses prior unpaid deductions first."""
    return await late_mark_service.process_month(db, year, month)


@router.get("/deductions", response_model=List[LateMarkDeductionRead])
async def list_deductions(
    *, db: deps.DBDep, current_user: deps.CurrentUser,
    year: int = Query(...), month: int = Query(..., ge=1, le=12),
) -> Any:
    rows = (await db.execute(
        select(LateMarkDeduction, User.full_name)
        .join(User, LateMarkDeduction.user_id == User.id)
        .where(LateMarkDeduction.year == year, LateMarkDeduction.month == month)
        .order_by(User.full_name)
    )).all()
    out = []
    for d, full_name in rows:
        d.full_name = full_name
        out.append(d)
    return out
