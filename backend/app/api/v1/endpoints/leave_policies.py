"""Per-employment-type leave policy matrix + allocation (W1)."""
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, select

from app.api import deps
from app.models.user import User
from app.models.audit import AuditLog
from app.models.employee import Employee
from app.models.employment_type import EmploymentType
from app.models.employment_type_leave_policy import EmploymentTypeLeavePolicy
from app.models.leave import LeaveType
from app.schemas.leave_policy import LeavePolicyRead, LeavePolicyCell, LeavePolicyMatrix, AllocateRequest
from app.services import leave_policy as leave_policy_service

router = APIRouter()

HR_WRITE = "hr employee write"


@router.get("/leave-policies", response_model=List[LeavePolicyRead])
async def list_policies(db: deps.DBDep, current_user: deps.CurrentUser) -> Any:
    return (await db.execute(select(EmploymentTypeLeavePolicy))).scalars().all()


@router.get("/leave-policies/matrix", response_model=LeavePolicyMatrix)
async def policy_matrix(db: deps.DBDep, current_user: deps.CurrentUser) -> Any:
    ets = (await db.execute(select(EmploymentType).order_by(EmploymentType.name))).scalars().all()
    lts = (await db.execute(select(LeaveType).order_by(LeaveType.name))).scalars().all()
    cells = (await db.execute(select(EmploymentTypeLeavePolicy))).scalars().all()
    return {
        "employment_types": [{"id": e.id, "code": e.code, "name": e.name} for e in ets],
        "leave_types": [{"id": l.id, "code": l.code, "name": l.name, "default_quota": l.annual_quota,
                         "unpaid_allowed": l.unpaid_allowed} for l in lts],
        "cells": cells,
    }


@router.put("/leave-policies", response_model=LeavePolicyRead)
async def upsert_policy(
    *, db: deps.DBDep, cell: LeavePolicyCell,
    current_user: User = Depends(deps.check_permissions([HR_WRITE])),
) -> Any:
    row = (await db.execute(select(EmploymentTypeLeavePolicy).where(and_(
        EmploymentTypeLeavePolicy.employment_type_id == cell.employment_type_id,
        EmploymentTypeLeavePolicy.leave_type_id == cell.leave_type_id,
    )))).scalars().first()
    if row is None:
        row = EmploymentTypeLeavePolicy(**cell.model_dump())
        db.add(row)
    else:
        row.is_eligible = cell.is_eligible
        row.annual_quota = cell.annual_quota
    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/leave-policies/{policy_id}")
async def delete_policy(
    *, db: deps.DBDep, policy_id: int,
    current_user: User = Depends(deps.check_permissions([HR_WRITE])),
) -> Any:
    row = await db.get(EmploymentTypeLeavePolicy, policy_id)
    if not row:
        raise HTTPException(status_code=404, detail="Policy not found")
    await db.delete(row)
    await db.commit()
    return {"message": "Reverted to default (eligible at leave-type quota)"}


@router.post("/leave-policies/allocate")
async def allocate(
    *, db: deps.DBDep, payload: AllocateRequest,
    current_user: User = Depends(deps.check_permissions([HR_WRITE])),
) -> Any:
    """Seed/refresh leave balances from policy — for one user or every active
    employee of an employment type."""
    if payload.user_id:
        user_ids = [payload.user_id]
    elif payload.employment_type_id:
        et = await db.get(EmploymentType, payload.employment_type_id)
        if not et:
            raise HTTPException(status_code=404, detail="Employment type not found")
        emps = (await db.execute(select(Employee).where(and_(
            Employee.status == "active", Employee.employment_type == et.code,
        )))).scalars().all()
        user_ids = [e.user_id for e in emps]
    else:
        raise HTTPException(status_code=400, detail="Provide user_id or employment_type_id")

    total = 0
    for uid in user_ids:
        rows = await leave_policy_service.allocate_for_user(db, uid, overwrite=payload.overwrite)
        total += len(rows)
    db.add(AuditLog(
        user_id=current_user.id, action="LEAVE_ALLOCATE",
        resource_type="leave_policy", resource_id=str(payload.user_id or payload.employment_type_id),
        details={"users": len(user_ids), "ledgers_touched": total, "overwrite": payload.overwrite},
    ))
    await db.commit()
    return {"users": len(user_ids), "ledgers_touched": total}
