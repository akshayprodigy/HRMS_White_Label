from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, require_permissions
from app.core.database import get_db
from app.db.models.hr import LeaveRequest
from app.db.models.iam import User
from app.modules.hr.leave_service import (
    apply_leave_request,
    approve_leave_request,
    cancel_leave_request,
    list_leave_requests,
    reject_leave_request,
)
from app.modules.hr.schemas import (
    LeaveApplyRequest,
    LeaveDecisionRequest,
    LeaveRequestPublic,
)

router = APIRouter(prefix="/leave-requests")

_ERR_NOT_FOUND = "Leave request not found"


@router.get(
    "",
    response_model=list[LeaveRequestPublic],
    dependencies=[Depends(require_permissions({"hr.leave_requests.read"}))],
)
def hr_list_leave_requests(
    status: str | None = Query(default=None),
    employee_id: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[LeaveRequestPublic]:
    rows = list_leave_requests(
        db,
        status=status,
        employee_id=employee_id,
        limit=limit,
        offset=offset,
    )
    return [LeaveRequestPublic.model_validate(r) for r in rows]


@router.post(
    "/apply",
    response_model=LeaveRequestPublic,
    dependencies=[Depends(require_permissions({"hr.leave_requests.apply"}))],
)
def hr_apply_leave(
    payload: LeaveApplyRequest,
    db: Session = Depends(get_db),
) -> LeaveRequestPublic:
    req = apply_leave_request(
        db,
        employee_id=payload.employee_id,
        leave_type_id=payload.leave_type_id,
        date_from=payload.date_from,
        date_to=payload.date_to,
        reason=payload.reason,
    )
    return LeaveRequestPublic.model_validate(req)


@router.post(
    "/{request_id}/approve",
    response_model=LeaveRequestPublic,
    dependencies=[Depends(require_permissions({"hr.leave_requests.approve"}))],
)
def hr_approve_leave(
    request_id: int,
    payload: LeaveDecisionRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LeaveRequestPublic:
    req = db.get(LeaveRequest, request_id)
    if not req:
        raise HTTPException(status_code=404, detail=_ERR_NOT_FOUND)

    updated = approve_leave_request(
        db,
        req=req,
        actor_user_id=user.id,
        comment=payload.comment,
    )
    return LeaveRequestPublic.model_validate(updated)


@router.post(
    "/{request_id}/reject",
    response_model=LeaveRequestPublic,
    dependencies=[Depends(require_permissions({"hr.leave_requests.reject"}))],
)
def hr_reject_leave(
    request_id: int,
    payload: LeaveDecisionRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LeaveRequestPublic:
    req = db.get(LeaveRequest, request_id)
    if not req:
        raise HTTPException(status_code=404, detail=_ERR_NOT_FOUND)

    updated = reject_leave_request(
        db,
        req=req,
        actor_user_id=user.id,
        comment=payload.comment,
    )
    return LeaveRequestPublic.model_validate(updated)


@router.post(
    "/{request_id}/cancel",
    response_model=LeaveRequestPublic,
    dependencies=[Depends(require_permissions({"hr.leave_requests.cancel"}))],
)
def hr_cancel_leave(
    request_id: int,
    db: Session = Depends(get_db),
) -> LeaveRequestPublic:
    req = db.get(LeaveRequest, request_id)
    if not req:
        raise HTTPException(status_code=404, detail=_ERR_NOT_FOUND)

    updated = cancel_leave_request(db, req=req)
    return LeaveRequestPublic.model_validate(updated)
