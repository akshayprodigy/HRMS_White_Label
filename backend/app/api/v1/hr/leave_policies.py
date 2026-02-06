from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import require_permissions
from app.core.database import get_db
from app.db.models.hr import LeavePolicy
from app.modules.hr.leave_service import (
    create_leave_policy,
    delete_leave_policy,
    list_leave_policies,
    update_leave_policy,
)
from app.modules.hr.schemas import (
    LeavePolicyCreate,
    LeavePolicyPublic,
    LeavePolicyUpdate,
)

router = APIRouter(prefix="/leave-policies")

_ERR_NOT_FOUND = "Leave policy not found"


@router.get(
    "",
    response_model=list[LeavePolicyPublic],
    dependencies=[Depends(require_permissions({"hr.leave_policies.read"}))],
)
def hr_list_leave_policies(
    db: Session = Depends(get_db),
) -> list[LeavePolicyPublic]:
    return [
        LeavePolicyPublic.model_validate(x)
        for x in list_leave_policies(db)
    ]


@router.post(
    "",
    response_model=LeavePolicyPublic,
    dependencies=[Depends(require_permissions({"hr.leave_policies.write"}))],
)
def hr_create_leave_policy(
    payload: LeavePolicyCreate,
    db: Session = Depends(get_db),
) -> LeavePolicyPublic:
    row = create_leave_policy(
        db,
        leave_type_id=payload.leave_type_id,
        name=payload.name,
        monthly_credit_days=payload.monthly_credit_days,
        max_balance_days=payload.max_balance_days,
        is_active=payload.is_active,
        notes=payload.notes,
    )
    return LeavePolicyPublic.model_validate(row)


@router.put(
    "/{policy_id}",
    response_model=LeavePolicyPublic,
    dependencies=[Depends(require_permissions({"hr.leave_policies.write"}))],
)
def hr_update_leave_policy(
    policy_id: int,
    payload: LeavePolicyUpdate,
    db: Session = Depends(get_db),
) -> LeavePolicyPublic:
    policy = db.get(LeavePolicy, policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail=_ERR_NOT_FOUND)

    updated = update_leave_policy(
        db,
        policy=policy,
        name=payload.name,
        monthly_credit_days=payload.monthly_credit_days,
        max_balance_days=payload.max_balance_days,
        is_active=payload.is_active,
        notes=payload.notes,
    )
    return LeavePolicyPublic.model_validate(updated)


@router.delete(
    "/{policy_id}",
    dependencies=[Depends(require_permissions({"hr.leave_policies.write"}))],
)
def hr_delete_leave_policy(
    policy_id: int,
    db: Session = Depends(get_db),
) -> dict:
    policy = db.get(LeavePolicy, policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail=_ERR_NOT_FOUND)

    delete_leave_policy(db, policy=policy)
    return {"status": "ok"}
