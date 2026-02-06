from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import require_permissions
from app.core.database import get_db
from app.db.models.hr import LeaveType
from app.modules.hr.leave_service import (
    create_leave_type,
    delete_leave_type,
    list_leave_types,
    update_leave_type,
)
from app.modules.hr.schemas import (
    LeaveTypeCreate,
    LeaveTypePublic,
    LeaveTypeUpdate,
)

router = APIRouter(prefix="/leave-types")

_ERR_NOT_FOUND = "Leave type not found"


@router.get(
    "",
    response_model=list[LeaveTypePublic],
    dependencies=[Depends(require_permissions({"hr.leave_types.read"}))],
)
def hr_list_leave_types(
    db: Session = Depends(get_db),
) -> list[LeaveTypePublic]:
    return [LeaveTypePublic.model_validate(x) for x in list_leave_types(db)]


@router.post(
    "",
    response_model=LeaveTypePublic,
    dependencies=[Depends(require_permissions({"hr.leave_types.write"}))],
)
def hr_create_leave_type(
    payload: LeaveTypeCreate,
    db: Session = Depends(get_db),
) -> LeaveTypePublic:
    row = create_leave_type(
        db,
        code=payload.code,
        name=payload.name,
        description=payload.description,
        is_active=payload.is_active,
    )
    return LeaveTypePublic.model_validate(row)


@router.put(
    "/{leave_type_id}",
    response_model=LeaveTypePublic,
    dependencies=[Depends(require_permissions({"hr.leave_types.write"}))],
)
def hr_update_leave_type(
    leave_type_id: int,
    payload: LeaveTypeUpdate,
    db: Session = Depends(get_db),
) -> LeaveTypePublic:
    leave_type = db.get(LeaveType, leave_type_id)
    if not leave_type:
        raise HTTPException(status_code=404, detail=_ERR_NOT_FOUND)

    updated = update_leave_type(
        db,
        leave_type=leave_type,
        name=payload.name,
        description=payload.description,
        is_active=payload.is_active,
    )
    return LeaveTypePublic.model_validate(updated)


@router.delete(
    "/{leave_type_id}",
    dependencies=[Depends(require_permissions({"hr.leave_types.write"}))],
)
def hr_delete_leave_type(
    leave_type_id: int,
    db: Session = Depends(get_db),
) -> dict:
    leave_type = db.get(LeaveType, leave_type_id)
    if not leave_type:
        raise HTTPException(status_code=404, detail=_ERR_NOT_FOUND)

    delete_leave_type(db, leave_type=leave_type)
    return {"status": "ok"}
