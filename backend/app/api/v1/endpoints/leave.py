import io
import pandas as pd
from pathlib import Path
from typing import Any, List, Optional
from datetime import datetime, date, timedelta, timezone
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select, and_, or_, func
from sqlalchemy.orm import selectinload

from app.api import deps
from app.core.config import settings
from app.models.leave import LeaveType, LeaveBalanceLedger, LeaveRequest, LeaveStatus, HalfDaySession
from app.models.approval import ApprovalItem, ApprovalStep, ApprovalStatus
from app.models.comp_off import CompOffAccrual
from app.models.user import User, Role
from app.models.audit import AuditLog
from app.schemas.leave import LeaveRequestCreate, LeaveRequestRead, LeaveBalanceRead, LeaveTypeRead
from app.schemas.approval import ApprovalItemRead, ApprovalAction

router = APIRouter()

# Permission strings reused across HR-facing leave endpoints
PERM_HR_READ = "hr employee read"
PERM_HR_WRITE = "hr employee write"


@router.get("/balances", response_model=List[LeaveBalanceRead])
async def get_leave_balances(
    *,
    db: deps.DBDep,
    current_user: User = Depends(
        deps.check_permissions(["employee leave read"])
    )
) -> Any:
    """Get leave balances for the current user."""
    query = select(LeaveBalanceLedger).where(
        LeaveBalanceLedger.user_id == current_user.id
    ).options(selectinload(LeaveBalanceLedger.leave_type))
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/balances/user/{user_id}", response_model=List[LeaveBalanceRead])
async def get_user_leave_balances(
    *,
    db: deps.DBDep,
    user_id: int,
    current_user: User = Depends(
        deps.check_permissions([PERM_HR_READ])
    ),
) -> Any:
    """HR-only: fetch any employee's leave balances (single source of truth)."""
    exists = await db.execute(select(User).where(User.id == user_id))
    if not exists.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Employee not found")

    query = (
        select(LeaveBalanceLedger)
        .where(LeaveBalanceLedger.user_id == user_id)
        .options(selectinload(LeaveBalanceLedger.leave_type))
    )
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/balances/all")
async def get_all_leave_balances(
    *,
    db: deps.DBDep,
    current_user: User = Depends(
        deps.check_permissions([PERM_HR_READ])
    ),
) -> Any:
    """HR-only: list every employee with their per-leave-type balances.
    One row per user, with a nested `balances` array keyed by leave type."""
    users_res = await db.execute(
        select(User).where(User.is_active.is_(True)).order_by(User.full_name)
    )
    users = users_res.scalars().all()

    ledger_res = await db.execute(
        select(LeaveBalanceLedger).options(selectinload(LeaveBalanceLedger.leave_type))
    )
    ledgers = ledger_res.scalars().all()
    by_user: dict[int, list[LeaveBalanceLedger]] = {}
    for led in ledgers:
        by_user.setdefault(led.user_id, []).append(led)

    out: list[dict] = []
    for u in users:
        entries = by_user.get(u.id, [])
        out.append({
            "user_id": u.id,
            "full_name": u.full_name,
            "email": u.email,
            "balances": [
                {
                    "leave_type_id": led.leave_type_id,
                    "leave_type_name": led.leave_type.name,
                    "leave_type_code": led.leave_type.code,
                    "balance": led.balance,
                    "used": led.used,
                    "remaining": led.balance - led.used,
                }
                for led in entries
            ],
        })
    return out


@router.get("/types", response_model=List[LeaveTypeRead])
async def get_leave_types(
    *,
    db: deps.DBDep,
    current_user: deps.CurrentUser
) -> Any:
    """Get all available leave types."""
    result = await db.execute(select(LeaveType).order_by(LeaveType.name))
    return result.scalars().all()


@router.get("/my", response_model=List[LeaveRequestRead])
async def get_my_leaves(
    *,
    db: deps.DBDep,
    current_user: User = Depends(
        deps.check_permissions(["employee leave read"])
    )
) -> Any:
    """Get leave requests for the current user."""
    query = select(LeaveRequest).where(
        LeaveRequest.employee_id == current_user.id
    ).options(selectinload(LeaveRequest.leave_type)).order_by(LeaveRequest.created_at.desc())
    result = await db.execute(query)
    return result.scalars().all()


def _half_day_session_value(session: Any) -> Optional[str]:
    """Return a plain string for a HalfDaySession enum (or None)."""
    if not session:
        return None
    if hasattr(session, "value"):
        return session.value
    return str(session)


def _serialize_leave_for_history(lv: LeaveRequest) -> dict:
    """Flatten a LeaveRequest for the HR history view."""
    days = 0.5 if lv.is_half_day else (lv.end_date - lv.start_date).days + 1.0
    status_val = lv.status.value if hasattr(lv.status, "value") else str(lv.status)
    session_val = _half_day_session_value(lv.half_day_session)
    return {
        "id": lv.id,
        "employee_id": lv.employee_id,
        "employee_name": lv.employee.full_name if lv.employee else None,
        "employee_email": lv.employee.email if lv.employee else None,
        "leave_type": lv.leave_type.name if lv.leave_type else None,
        "leave_type_code": lv.leave_type.code if lv.leave_type else None,
        "start_date": lv.start_date.isoformat(),
        "end_date": lv.end_date.isoformat(),
        "is_half_day": lv.is_half_day,
        "half_day_session": session_val,
        "days": days,
        "reason": lv.reason,
        "attachment_url": lv.attachment_url,
        "status": status_val,
        "created_at": lv.created_at.isoformat() if lv.created_at else None,
    }


@router.get(
    "/history",
    responses={400: {"description": "Unknown status filter"}},
)
async def get_leave_history(
    *,
    db: deps.DBDep,
    status_filter: Optional[str] = None,
    limit: int = 200,
    current_user: User = Depends(
        deps.check_permissions([PERM_HR_READ])
    ),
) -> Any:
    """HR-only: org-wide leave history (all statuses by default).

    Query params:
      - status_filter: one of approved|rejected|cancelled|submitted|draft (optional)
      - limit: max rows (default 200)
    """
    q = (
        select(LeaveRequest)
        .options(
            selectinload(LeaveRequest.leave_type),
            selectinload(LeaveRequest.employee),
        )
        .order_by(LeaveRequest.created_at.desc())
        .limit(max(1, min(limit, 1000)))
    )
    if status_filter:
        try:
            status_enum = LeaveStatus(status_filter.upper())
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown status: {status_filter}",
            ) from exc
        q = q.where(LeaveRequest.status == status_enum)

    leaves = (await db.execute(q)).scalars().all()
    return [_serialize_leave_for_history(lv) for lv in leaves]


_ALLOWED_ATTACHMENT_TYPES = {
    "application/pdf": "pdf",
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/heic": "heic",
}


def _leave_attachments_dir() -> Path:
    return Path(settings.LEAVE_ATTACHMENTS_DIR)


@router.post("/attachments")
async def upload_leave_attachment(
    *,
    current_user: User = Depends(
        deps.check_permissions(["employee leave write"])
    ),
    file: UploadFile = File(...),
) -> Any:
    """Upload a supporting document (e.g. medical certificate).

    Returns the opaque filename the client then passes as `attachment_url`
    when calling POST /leave/apply.
    """
    content_type = (file.content_type or "").lower()
    ext = _ALLOWED_ATTACHMENT_TYPES.get(content_type)
    if ext is None:
        raise HTTPException(
            status_code=400,
            detail="Only PDF, JPEG, PNG, WebP, or HEIC files are allowed",
        )

    attach_dir = _leave_attachments_dir()
    attach_dir.mkdir(parents=True, exist_ok=True)

    stored_name = f"{uuid4().hex}.{ext}"
    dest = attach_dir / stored_name
    max_bytes = int(settings.LEAVE_ATTACHMENT_MAX_BYTES)
    total = 0
    with dest.open("wb") as f:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                dest.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail="File exceeds the 10 MB limit",
                )
            f.write(chunk)

    return {
        "attachment_url": stored_name,
        "original_name": file.filename,
        "size": total,
    }


@router.get("/attachments/{filename}")
async def download_leave_attachment(
    *,
    db: deps.DBDep,
    filename: str,
    current_user: deps.CurrentUser,
) -> Any:
    """Stream back an attachment. Access is granted to the owner of the leave
    request, their manager, or users with HR/leave-approve permission."""
    # Basic path-traversal guard — filenames are opaque UUIDs, no slashes allowed.
    if "/" in filename or "\\" in filename or filename.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid filename")

    lr = (await db.execute(
        select(LeaveRequest).where(LeaveRequest.attachment_url == filename).limit(1)
    )).scalar_one_or_none()
    if lr is None:
        raise HTTPException(status_code=404, detail="Attachment not found")

    is_owner = lr.employee_id == current_user.id
    owner = (await db.execute(
        select(User).where(User.id == lr.employee_id).limit(1)
    )).scalar_one_or_none()
    is_manager = bool(owner and owner.manager_id == current_user.id)
    perm_names = {p.name for r in (current_user.roles or []) for p in (r.permissions or [])}
    has_priv = bool(
        current_user.is_superuser
        or {"hr employee read", "hr employee write", "employee leave approve"} & perm_names
    )
    if not (is_owner or is_manager or has_priv):
        raise HTTPException(status_code=403, detail="Not allowed to view this attachment")

    path = _leave_attachments_dir() / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Attachment file missing on disk")
    return FileResponse(path)


@router.post("/apply", response_model=LeaveRequestRead)
async def apply_leave(
    *,
    db: deps.DBDep,
    current_user: User = Depends(
        deps.check_permissions(["employee leave write"])
    ),
    leave_in: LeaveRequestCreate,
    request: Request
) -> Any:
    """Apply for a new leave."""
    # 1. Date range validation
    if leave_in.start_date > leave_in.end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Start date cannot be after end date"
        )
    
    if leave_in.is_half_day and leave_in.start_date != leave_in.end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Half day leaves must be for a single day"
        )

    # 2. Overlap detection
    overlap_query = select(LeaveRequest).where(
        and_(
            LeaveRequest.employee_id == current_user.id,
            LeaveRequest.status.in_([LeaveStatus.SUBMITTED, LeaveStatus.APPROVED]),
            LeaveRequest.start_date <= leave_in.end_date,
            LeaveRequest.end_date >= leave_in.start_date
        )
    )
    overlap_result = await db.execute(overlap_query)
    if overlap_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Leave request overlaps with an existing or pending request"
        )

    # 3. Balance check
    lt_query = select(LeaveType).where(LeaveType.id == leave_in.leave_type_id)
    lt_result = await db.execute(lt_query)
    leave_type = lt_result.scalar_one_or_none()
    if not leave_type:
        raise HTTPException(status_code=404, detail="Leave type not found")

    days = 0.5 if leave_in.is_half_day else (leave_in.end_date - leave_in.start_date).days + 1

    # Policy-based validations
    if leave_in.is_half_day and not leave_type.allow_half_day:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{leave_type.name} does not allow half-day leaves"
        )

    if leave_type.max_consecutive_days and days > leave_type.max_consecutive_days:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{leave_type.name} allows max {leave_type.max_consecutive_days} consecutive days"
        )

    if leave_type.requires_medical_cert_after and days >= leave_type.requires_medical_cert_after:
        if not leave_in.attachment_url:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{leave_type.name} requires a medical certificate for {leave_type.requires_medical_cert_after}+ consecutive days"
            )

    # Monthly limit check (e.g., Comp-off max 2/month)
    if leave_type.max_per_month:
        month_start = leave_in.start_date.replace(day=1)
        if leave_in.start_date.month == 12:
            month_end = leave_in.start_date.replace(year=leave_in.start_date.year + 1, month=1, day=1)
        else:
            month_end = leave_in.start_date.replace(month=leave_in.start_date.month + 1, day=1)
        month_count_q = select(func.count(LeaveRequest.id)).where(
            and_(
                LeaveRequest.employee_id == current_user.id,
                LeaveRequest.leave_type_id == leave_in.leave_type_id,
                LeaveRequest.status.in_([LeaveStatus.SUBMITTED, LeaveStatus.APPROVED]),
                LeaveRequest.start_date >= month_start,
                LeaveRequest.start_date < month_end,
            )
        )
        month_count = (await db.execute(month_count_q)).scalar() or 0
        if month_count >= leave_type.max_per_month:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{leave_type.name} allows max {leave_type.max_per_month} per month"
            )

    if not leave_type.unpaid_allowed:
        balance_query = select(LeaveBalanceLedger).where(
            and_(
                LeaveBalanceLedger.user_id == current_user.id,
                LeaveBalanceLedger.leave_type_id == leave_in.leave_type_id
            )
        )
        balance_result = await db.execute(balance_query)
        ledger = balance_result.scalar_one_or_none()
        if not ledger or (ledger.balance - ledger.used) < days:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient leave balance"
            )

    # 4. Create Leave Request
    db_obj = LeaveRequest(
        **leave_in.model_dump(),
        employee_id=current_user.id,
        created_by_user_id=current_user.id,
        status=LeaveStatus.SUBMITTED
    )
    db.add(db_obj)
    await db.flush()

    # 5. Create Approval Item & Steps
    approval_item = ApprovalItem(
        resource_type="leave_request",
        resource_id=str(db_obj.id),
        status=ApprovalStatus.PENDING,
        current_step_number=1,
        requested_by_id=current_user.id,
    )
    db.add(approval_item)
    await db.flush()

    step_idx = 1
    # Step 1: Manager Approval (if exists)
    if current_user.manager_id:
        step = ApprovalStep(
            approval_item_id=approval_item.id,
            step_number=step_idx,
            approver_id=current_user.manager_id,
            status=ApprovalStatus.PENDING
        )
        db.add(step)
        step_idx += 1
    
    # Step 2: HR Approval
    hr_role_query = select(Role).where(Role.name == "HR")
    hr_role_result = await db.execute(hr_role_query)
    hr_role = hr_role_result.scalar_one_or_none()
    
    step_hr = ApprovalStep(
        approval_item_id=approval_item.id,
        step_number=step_idx,
        role_id=hr_role.id if hr_role else None,
        status=ApprovalStatus.PENDING
    )
    db.add(step_hr)

    # 6. Audit Log
    audit = AuditLog(
        user_id=current_user.id,
        action="LEAVE_APPLY",
        resource_type="leave_request",
        resource_id=str(db_obj.id),
        ip_address=request.client.host if request.client else None,
        details={"days": days, "leave_type": leave_type.name}
    )
    db.add(audit)
    
    await db.commit()
    await db.refresh(db_obj)
    
    # Refresh to get leave_type loaded
    query = select(LeaveRequest).where(LeaveRequest.id == db_obj.id).options(selectinload(LeaveRequest.leave_type))
    result = await db.execute(query)
    return result.scalar_one()


@router.post("/{id}/cancel", response_model=LeaveRequestRead)
async def cancel_leave(
    *,
    db: deps.DBDep,
    id: int,
    current_user: User = Depends(
        deps.check_permissions(["employee leave write"])
    ),
    request: Request
) -> Any:
    """Cancel a leave request."""
    query = select(LeaveRequest).where(
        LeaveRequest.id == id,
        LeaveRequest.employee_id == current_user.id
    )
    result = await db.execute(query)
    leave = result.scalar_one_or_none()
    
    if not leave:
        raise HTTPException(status_code=404, detail="Leave request not found")
    
    if leave.status not in [LeaveStatus.SUBMITTED, LeaveStatus.DRAFT]:
        raise HTTPException(
            status_code=400, 
            detail=f"Cannot cancel leave in {leave.status} status"
        )
    
    leave.status = LeaveStatus.CANCELLED
    
    # Cancel pending approvals
    approval_query = select(ApprovalItem).where(
        ApprovalItem.resource_type == "leave_request",
        ApprovalItem.resource_id == str(id)
    )
    app_result = await db.execute(approval_query)
    approval_item = app_result.scalar_one_or_none()
    if approval_item:
        approval_item.status = ApprovalStatus.REJECTED # Or another status like CANCELLED if added
        for step in approval_item.steps:
            if step.status == ApprovalStatus.PENDING:
                step.status = ApprovalStatus.REJECTED
                step.comment = "Cancelled by requester"
                step.actioned_at = datetime.now(timezone.utc)

    db.add(AuditLog(
        user_id=current_user.id,
        action="LEAVE_CANCEL",
        resource_type="leave_request",
        resource_id=str(id),
        ip_address=request.client.host if request.client else None
    ))
    
    await db.commit()
    await db.refresh(leave)
    return leave


def _parse_leave_resource_id(raw: Any) -> Optional[int]:
    """Parse an ApprovalItem.resource_id into a LeaveRequest id (or None)."""
    s = str(raw) if raw is not None else ""
    return int(s) if s.isdigit() else None


async def _fetch_leaves_for_items(
    db: Any, items: list[ApprovalItem]
) -> dict[int, LeaveRequest]:
    """Bulk-load the LeaveRequest rows referenced by `items` (batched to avoid N+1)."""
    leave_ids = [
        _parse_leave_resource_id(it.resource_id)
        for it in items
        if it.resource_type == "leave_request"
    ]
    leave_ids = [i for i in leave_ids if i is not None]
    if not leave_ids:
        return {}
    lr_query = (
        select(LeaveRequest)
        .where(LeaveRequest.id.in_(leave_ids))
        .options(
            selectinload(LeaveRequest.leave_type),
            selectinload(LeaveRequest.employee),
        )
    )
    return {
        lr.id: lr for lr in (await db.execute(lr_query)).scalars().all()
    }


def _serialize_leave_for_approval(lr: LeaveRequest) -> dict:
    """Flatten a LeaveRequest for embedding in an approval card."""
    days = 0.5 if lr.is_half_day else (lr.end_date - lr.start_date).days + 1.0
    return {
        "id": lr.id,
        "leave_type": lr.leave_type.name if lr.leave_type else None,
        "leave_type_code": lr.leave_type.code if lr.leave_type else None,
        "start_date": lr.start_date.isoformat(),
        "end_date": lr.end_date.isoformat(),
        "is_half_day": lr.is_half_day,
        "half_day_session": _half_day_session_value(lr.half_day_session),
        "days": days,
        "reason": lr.reason,
        "emergency_contact": lr.emergency_contact,
        "attachment_url": lr.attachment_url,
    }


def _build_approver_step_filter(current_user: User) -> Any:
    """Build the OR-clause that matches pending steps an approver can action."""
    role_ids = [r.id for r in current_user.roles]
    role_clause = (
        ApprovalStep.role_id.in_(role_ids) if role_ids else False
    )
    return or_(
        ApprovalStep.approver_id == current_user.id,
        and_(
            ApprovalStep.approver_id == None,  # noqa: E711 (SA column compare)
            or_(
                role_clause,
                ApprovalStep.role_id == None,  # noqa: E711
            ),
        ),
    )


@router.get("/approvals/inbox")
async def get_leave_approvals(
    *,
    db: deps.DBDep,
    current_user: User = Depends(
        deps.check_permissions(["leave approve"])
    )
) -> Any:
    """Get pending leave approvals for the current user."""
    query = (
        select(ApprovalItem)
        .join(ApprovalStep)
        .where(
            and_(
                ApprovalItem.status == ApprovalStatus.PENDING,
                ApprovalStep.status == ApprovalStatus.PENDING,
                ApprovalItem.current_step_number == ApprovalStep.step_number,
                _build_approver_step_filter(current_user),
            )
        )
        .options(
            selectinload(ApprovalItem.steps),
            selectinload(ApprovalItem.requested_by),
        )
    )

    items = (await db.execute(query)).scalars().unique().all()
    leaves_by_id = await _fetch_leaves_for_items(db, items)

    # Bulk-load comp-off accruals for any matching items
    co_ids = [
        int(it.resource_id)
        for it in items
        if it.resource_type == "comp_off_accrual" and str(it.resource_id).isdigit()
    ]
    co_by_id: dict[int, CompOffAccrual] = {}
    if co_ids:
        co_rows = (await db.execute(
            select(CompOffAccrual).where(CompOffAccrual.id.in_(co_ids))
        )).scalars().all()
        co_by_id = {row.id: row for row in co_rows}

    out = []
    for item in items:
        d = ApprovalItemRead.model_validate(item).model_dump()
        d['requested_by_name'] = (
            item.requested_by.full_name if item.requested_by else None
        )
        if item.resource_type == "leave_request":
            lr_id = _parse_leave_resource_id(item.resource_id)
            lr = leaves_by_id.get(lr_id) if lr_id is not None else None
            if lr:
                d['leave_detail'] = _serialize_leave_for_approval(lr)
                # Fallback for older approval rows whose requested_by_id is NULL.
                if not d['requested_by_name'] and lr.employee:
                    d['requested_by_name'] = lr.employee.full_name
        elif item.resource_type == "comp_off_accrual":
            co = co_by_id.get(int(item.resource_id)) if str(item.resource_id).isdigit() else None
            if co is not None:
                d['comp_off_detail'] = {
                    "id": co.id,
                    "holiday_date": co.holiday_date.isoformat(),
                    "holiday_name": co.holiday_name,
                    "worked_minutes": co.worked_minutes,
                    "worked_hours_label": (
                        f"{co.worked_minutes // 60}h {co.worked_minutes % 60:02d}m"
                    ),
                    "days_credited": co.days_credited,
                    "reason": co.reason,
                }
        out.append(d)
    return out


@router.post("/approvals/{item_id}/action")
async def action_approval(
    *,
    db: deps.DBDep,
    item_id: int,
    action: ApprovalAction,
    current_user: User = Depends(
        deps.check_permissions(["leave approve"])
    ),
    request: Request
) -> Any:
    """Approve or reject a leave request."""
    query = select(ApprovalItem).where(ApprovalItem.id == item_id).options(selectinload(ApprovalItem.steps))
    result = await db.execute(query)
    approval_item = result.scalar_one_or_none()
    
    if not approval_item:
        raise HTTPException(status_code=404, detail="Approval item not found")
    
    if approval_item.status != ApprovalStatus.PENDING:
        raise HTTPException(status_code=400, detail="Approval already actioned")
    
    # Find the current pending step
    role_ids = [r.id for r in current_user.roles]
    current_step = next((s for s in approval_item.steps if s.step_number == approval_item.current_step_number), None)
    
    if not current_step:
        raise HTTPException(status_code=500, detail="Approval workflow inconsistent")
    
    # Check if user can action this step:
    # - Explicit approver match, OR
    # - Role-based step (no specific approver assigned) — any user with leave approve permission can act
    can_action = (
        current_step.approver_id == current_user.id
        or (current_step.approver_id is None and (current_step.role_id in role_ids or current_step.role_id is None))
    )

    if not can_action:
        raise HTTPException(status_code=403, detail="Not authorized to action this step")
    
    # Update step
    current_step.status = action.status
    current_step.comment = action.comment
    current_step.actioned_at = datetime.now(timezone.utc)
    current_step.approver_id = current_user.id # Set the actual approver
    
    if action.status == ApprovalStatus.REJECTED:
        approval_item.status = ApprovalStatus.REJECTED
        # Update leave status
        if approval_item.resource_type == "leave_request":
            l_query = select(LeaveRequest).where(LeaveRequest.id == int(approval_item.resource_id))
            l_result = await db.execute(l_query)
            leave = l_result.scalar_one()
            leave.status = LeaveStatus.REJECTED
        elif approval_item.resource_type == "comp_off_accrual":
            accrual = await db.get(CompOffAccrual, int(approval_item.resource_id))
            if accrual is not None:
                accrual.status = "rejected"
    else:
        # Check if more steps exist
        next_step = next((s for s in approval_item.steps if s.step_number == approval_item.current_step_number + 1), None)
        if next_step:
            approval_item.current_step_number += 1
        else:
            approval_item.status = ApprovalStatus.APPROVED
            # Update leave status
            if approval_item.resource_type == "leave_request":
                l_query = select(LeaveRequest).where(LeaveRequest.id == int(approval_item.resource_id))
                l_result = await db.execute(l_query)
                leave = l_result.scalar_one()
                leave.status = LeaveStatus.APPROVED

                # Update ledger
                days = 0.5 if leave.is_half_day else (leave.end_date - leave.start_date).days + 1
                bal_query = select(LeaveBalanceLedger).where(
                    and_(
                        LeaveBalanceLedger.user_id == leave.employee_id,
                        LeaveBalanceLedger.leave_type_id == leave.leave_type_id
                    )
                )
                bal_result = await db.execute(bal_query)
                ledger = bal_result.scalar_one_or_none()
                if ledger:
                    ledger.used += days
                else:
                    # Create ledger if not exists (should have been there)
                    db.add(LeaveBalanceLedger(
                        user_id=leave.employee_id,
                        leave_type_id=leave.leave_type_id,
                        balance=0.0,
                        used=days
                    ))
            elif approval_item.resource_type == "comp_off_accrual":
                accrual = await db.get(CompOffAccrual, int(approval_item.resource_id))
                if accrual is not None:
                    accrual.status = "approved"
                    co_type = (await db.execute(
                        select(LeaveType).where(LeaveType.code == "CO").limit(1)
                    )).scalar_one_or_none()
                    if co_type is not None:
                        bal = (await db.execute(
                            select(LeaveBalanceLedger).where(and_(
                                LeaveBalanceLedger.user_id == accrual.user_id,
                                LeaveBalanceLedger.leave_type_id == co_type.id,
                            ))
                        )).scalar_one_or_none()
                        if bal is None:
                            db.add(LeaveBalanceLedger(
                                user_id=accrual.user_id,
                                leave_type_id=co_type.id,
                                balance=accrual.days_credited,
                                used=0.0,
                            ))
                        else:
                            bal.balance += accrual.days_credited

    db.add(AuditLog(
        user_id=current_user.id,
        action=f"APPROVAL_{action.status}",
        resource_type=approval_item.resource_type,
        resource_id=approval_item.resource_id,
        ip_address=request.client.host if request.client else None
    ))
    
    await db.commit()
    return {"status": "success"}


# ─── Manual Leave Grant (single employee) ─────────────────────────────────────

def _parse_grant_days(raw: Any) -> Optional[float]:
    """Parse a grant entry's `days` value; return None if unusable/zero."""
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if value == 0:
        return None
    return value


def _apply_grant_delta(
    ledger: Optional[LeaveBalanceLedger],
    employee_id: int,
    leave_type_id: int,
    leave_type_name: str,
    days: float,
    db: Any,
) -> tuple[Optional[LeaveBalanceLedger], float, float, Optional[str]]:
    """Apply a signed delta to a ledger row (existing or new).

    Returns (ledger, previous_balance, new_balance, error). Error is set when
    the delta would violate invariants; in that case ledger mutation is skipped.
    """
    if ledger:
        previous = ledger.balance
        new_balance = ledger.balance + days
        if new_balance < ledger.used:
            return None, previous, new_balance, (
                f"{leave_type_name}: resulting balance {new_balance} is "
                f"less than already-used {ledger.used}"
            )
        ledger.balance = new_balance
        return ledger, previous, new_balance, None

    if days < 0:
        return None, 0.0, days, (
            f"{leave_type_name}: cannot create negative opening balance"
        )
    ledger = LeaveBalanceLedger(
        user_id=employee_id,
        leave_type_id=leave_type_id,
        balance=days,
        used=0.0,
    )
    db.add(ledger)
    return ledger, 0.0, days, None


async def _process_single_grant(
    db: Any,
    employee_id: int,
    entry: dict,
    audit_user_id: int,
    audit_ip: Optional[str],
) -> tuple[Optional[dict], Optional[str]]:
    """Process one grant entry. Returns (result, error); both may be None (skip)."""
    leave_type_id = entry.get("leave_type_id")
    days = _parse_grant_days(entry.get("days", 0))
    if not leave_type_id or days is None:
        return None, None

    lt = (await db.execute(
        select(LeaveType).where(LeaveType.id == leave_type_id)
    )).scalar_one_or_none()
    if not lt:
        return None, None

    ledger = (await db.execute(
        select(LeaveBalanceLedger).where(and_(
            LeaveBalanceLedger.user_id == employee_id,
            LeaveBalanceLedger.leave_type_id == leave_type_id,
        ))
    )).scalar_one_or_none()

    _, previous, new_balance, error = _apply_grant_delta(
        ledger, employee_id, leave_type_id, lt.name, days, db,
    )
    if error:
        return None, error

    db.add(AuditLog(
        user_id=audit_user_id,
        action="LEAVE_GRANT",
        resource_type="leave_balance",
        resource_id=str(employee_id),
        ip_address=audit_ip,
        details={
            "leave_type": lt.name,
            "delta_days": days,
            "previous_balance": previous,
            "new_balance": new_balance,
            "reason": entry.get("reason", ""),
        },
    ))
    return {
        "leave_type": lt.name,
        "delta_days": days,
        "previous_balance": previous,
        "new_balance": new_balance,
    }, None


@router.post(
    "/grant",
    responses={
        400: {"description": "Invalid payload or all deltas rejected"},
        404: {"description": "Employee not found"},
    },
)
async def grant_leave(
    *,
    db: deps.DBDep,
    payload: dict,
    current_user: User = Depends(deps.check_permissions([PERM_HR_WRITE])),
    request: Request,
) -> Any:
    """Grant (delta-adjust) leave balance for a single employee.

    `days` is a signed delta: positive adds, negative subtracts.
    The resulting balance must stay >= already-used days (no retroactive LOP).

    Body: { "employee_id": int, "grants": [{"leave_type_id": int, "days": float, "reason": str}] }
    """
    employee_id = payload.get("employee_id")
    grants = payload.get("grants", [])
    if not employee_id or not grants:
        raise HTTPException(
            status_code=400,
            detail="employee_id and at least one grant entry are required",
        )

    emp_row = (await db.execute(
        select(User).where(User.id == employee_id)
    )).scalar_one_or_none()
    if not emp_row:
        raise HTTPException(status_code=404, detail="Employee not found")

    audit_ip = request.client.host if request.client else None
    results: list[dict] = []
    errors: list[str] = []
    for entry in grants:
        result, error = await _process_single_grant(
            db, employee_id, entry, current_user.id, audit_ip,
        )
        if result is not None:
            results.append(result)
        if error is not None:
            errors.append(error)

    if errors and not results:
        await db.rollback()
        raise HTTPException(status_code=400, detail="; ".join(errors))

    await db.commit()
    return {"status": "success", "grants": results, "errors": errors}


# ─── Bulk Leave Balance Upload ─────────────────────────────────────────────────

@router.get("/balances/template")
async def download_leave_balance_template(
    current_user: User = Depends(deps.check_permissions([PERM_HR_WRITE]))
) -> Any:
    """Download the Excel template for bulk leave balance upload."""
    # Columns: Employee Email, Leave Type Name, Balance (days), Used (days)
    sample_data = [
        {"Employee Email": "john.doe@company.com", "Leave Type": "Annual Leave", "Balance": 18, "Used": 0},
        {"Employee Email": "jane.smith@company.com", "Leave Type": "Sick Leave", "Balance": 12, "Used": 2},
        {"Employee Email": "john.doe@company.com", "Leave Type": "Sick Leave", "Balance": 12, "Used": 0},
    ]
    df = pd.DataFrame(sample_data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Leave Balances")
        ws = writer.sheets["Leave Balances"]
        for col in ws.columns:
            ws.column_dimensions[col[0].column_letter].width = 28
        # Instructions sheet
        inst = writer.book.create_sheet("Instructions")
        inst["A1"] = "Leave Balance Upload Instructions"
        inst["A3"] = "Employee Email"
        inst["B3"] = "Email address of the employee (must match an existing user in the system)"
        inst["A4"] = "Leave Type"
        inst["B4"] = "Exact name of the leave type (e.g. Annual Leave, Sick Leave)"
        inst["A5"] = "Balance"
        inst["B5"] = "Total leave days allocated (e.g. 18)"
        inst["A6"] = "Used"
        inst["B6"] = "Days already consumed (usually 0 for opening balances)"
        inst["A8"] = "Notes:"
        inst["A9"] = "- If a balance already exists for the employee+leave type pair, it will be UPDATED."
        inst["A10"] = "- Leave type names must exactly match what is configured in the system."
        inst["A11"] = "- Rows with missing email or leave type are skipped."

    output.seek(0)
    headers = {"Content-Disposition": 'attachment; filename="leave_balance_template.xlsx"'}
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers
    )


@router.post("/balances/bulk-upload")
async def bulk_upload_leave_balances(
    *,
    db: deps.DBDep,
    file: UploadFile = File(...),
    current_user: User = Depends(deps.check_permissions([PERM_HR_WRITE]))
) -> Any:
    """Bulk upload or update leave balances from an Excel file."""
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Please upload an Excel file (.xlsx or .xls)")

    contents = await file.read()
    try:
        df = pd.read_excel(io.BytesIO(contents), sheet_name="Leave Balances")
    except Exception:
        raise HTTPException(status_code=400, detail="Could not read 'Leave Balances' sheet from file")

    required_cols = {"Employee Email", "Leave Type", "Balance"}
    missing = required_cols - set(df.columns)
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing columns: {', '.join(missing)}")

    # Pre-load all users and leave types for fast lookup
    users_result = await db.execute(select(User))
    user_map = {u.email.lower(): u for u in users_result.scalars().all()}

    lt_result = await db.execute(select(LeaveType))
    lt_map = {lt.name.lower(): lt for lt in lt_result.scalars().all()}

    results = {"updated": 0, "created": 0, "skipped": 0, "errors": []}

    for idx, row in df.iterrows():
        email = str(row.get("Employee Email", "")).strip().lower()
        lt_name = str(row.get("Leave Type", "")).strip().lower()
        try:
            balance = float(row.get("Balance", 0) or 0)
            used = float(row.get("Used", 0) or 0)
        except (ValueError, TypeError):
            results["errors"].append(f"Row {idx + 2}: Invalid balance/used value")
            results["skipped"] += 1
            continue

        if not email or not lt_name:
            results["skipped"] += 1
            continue

        user = user_map.get(email)
        if not user:
            results["errors"].append(f"Row {idx + 2}: User not found — {email}")
            results["skipped"] += 1
            continue

        leave_type = lt_map.get(lt_name)
        if not leave_type:
            results["errors"].append(f"Row {idx + 2}: Leave type not found — {row.get('Leave Type', '')}")
            results["skipped"] += 1
            continue

        # Upsert the ledger entry
        ledger_q = select(LeaveBalanceLedger).where(
            and_(
                LeaveBalanceLedger.user_id == user.id,
                LeaveBalanceLedger.leave_type_id == leave_type.id
            )
        )
        existing = (await db.execute(ledger_q)).scalar_one_or_none()

        if existing:
            existing.balance = balance
            existing.used = used
            db.add(existing)
            results["updated"] += 1
        else:
            db.add(LeaveBalanceLedger(
                user_id=user.id,
                leave_type_id=leave_type.id,
                balance=balance,
                used=used,
            ))
            results["created"] += 1

    await db.commit()
    return results
