from typing import Any, List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_, or_
from sqlalchemy.orm import selectinload
from app.api import deps
from app.models.approval import ApprovalItem, ApprovalStep, ApprovalStatus
from app.models.user import User
from app.models.notification import Notification
from app.models.bd import EstimateVersion, EstimateStatus
from app.models.leave import LeaveRequest, LeaveStatus
from app.schemas.approval import (
    ApprovalItemRead, ApprovalAction
)
from app.schemas.bd import EstimateVersionDetailed
from app.schemas.leave import LeaveRequestRead

router = APIRouter()


ADMIN_ACCESS_PERMISSION = "admin access"
LEAD_ESTIMATE_APPROVE = "lead estimate approve"


def _attach_requester_names(items):
    """Populate `requested_by_name` on each item so the frontend can
    render the person, not just their id. Requires the caller to have
    eager-loaded ApprovalItem.requested_by.
    """
    for it in items:
        u = getattr(it, "requested_by", None)
        if u is not None:
            it.requested_by_name = u.full_name or u.email
    return items


def _user_has_permission(user: User, permission_name: str) -> bool:
    roles = getattr(user, "roles", None) or []
    for role in roles:
        perms = getattr(role, "permissions", None) or []
        for perm in perms:
            if getattr(perm, "name", None) == permission_name:
                return True
    return False


def _user_can_approve_estimates(user: User) -> bool:
    return bool(
        user.is_superuser
        or _is_admin_approver(user)
        or _user_has_permission(user, LEAD_ESTIMATE_APPROVE)
    )


def _is_admin_approver(user: User) -> bool:
    if user.is_superuser:
        return True
    role_names = [(r.name or "").strip().lower() for r in (user.roles or [])]
    if "super admin" in role_names or "admin" in role_names:
        return True
    for role in user.roles or []:
        for perm in getattr(role, "permissions", []) or []:
            if (perm.name or "").strip().lower() == ADMIN_ACCESS_PERMISSION:
                return True
    return False


def _user_is_current_step_approver(
    approval_item: ApprovalItem,
    current_user: User,
) -> bool:
    current_step = next(
        (
            s
            for s in approval_item.steps
            if s.step_number == approval_item.current_step_number
        ),
        None,
    )
    if not current_step or current_step.status != ApprovalStatus.PENDING:
        return False

    user_role_ids = [role.id for role in current_user.roles]
    return bool(
        (
            current_step.approver_id
            and current_step.approver_id == current_user.id
        )
        or (
            current_step.role_id
            and current_step.role_id in user_role_ids
        )
    )


def _user_can_view_approval(
    approval_item: ApprovalItem,
    current_user: User,
) -> bool:
    if _is_admin_approver(current_user):
        return True

    if (
        getattr(approval_item, "requested_by_id", None) is not None
        and approval_item.requested_by_id == current_user.id
    ):
        return True

    user_role_ids = [role.id for role in (current_user.roles or [])]
    for step in approval_item.steps or []:
        if step.approver_id and step.approver_id == current_user.id:
            return True
        if step.role_id and step.role_id in user_role_ids:
            return True

    return False


async def create_notification(
    db: deps.DBDep,
    user_id: int,
    title: str,
    message: str,
    type: str = "info",
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None
):
    notification = Notification(
        user_id=user_id,
        title=title,
        message=message,
        type=type,
        resource_type=resource_type,
        resource_id=resource_id
    )
    db.add(notification)


@router.get("/inbox", response_model=List[ApprovalItemRead])
async def get_approvals_inbox(
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
    status: Optional[ApprovalStatus] = Query(None),
    resource_type: Optional[str] = Query(None),
    due_before: Optional[datetime] = Query(None)
) -> Any:
    # Get all approval items where user is approver for active step

    is_admin_approver = _is_admin_approver(current_user)
    user_role_ids = [role.id for role in current_user.roles]

    # Admin: when explicitly filtering non-pending statuses,
    # return items by status ("history" view).
    if (
        is_admin_approver
        and status is not None
        and status != ApprovalStatus.PENDING
    ):
        query = select(ApprovalItem).options(
            selectinload(ApprovalItem.steps),
            selectinload(ApprovalItem.requested_by),
        )
        query = query.where(ApprovalItem.status == status)
        if resource_type:
            query = query.where(ApprovalItem.resource_type == resource_type)
        if due_before:
            query = query.where(ApprovalItem.due_date <= due_before)

        result = await db.execute(query)
        return _attach_requester_names(result.scalars().all())

    # Non-admin: support non-pending history view too, but limit it to:
    # - requests created by the current user, or
    # - approvals where the current user already actioned a step
    if (
        not is_admin_approver
        and status is not None
        and status != ApprovalStatus.PENDING
    ):
        query = (
            select(ApprovalItem)
            .join(ApprovalStep)
            .where(ApprovalItem.status == status)
            .where(
                or_(
                    ApprovalItem.requested_by_id == current_user.id,
                    ApprovalStep.approver_id == current_user.id,
                )
            )
            .options(
                selectinload(ApprovalItem.steps),
                selectinload(ApprovalItem.requested_by),
            )
            .distinct()
        )
        if resource_type:
            query = query.where(ApprovalItem.resource_type == resource_type)
        if due_before:
            query = query.where(ApprovalItem.due_date <= due_before)

        result = await db.execute(query)
        return _attach_requester_names(result.scalars().all())

    base_conditions = [
        ApprovalItem.current_step_number == ApprovalStep.step_number,
        ApprovalStep.status == ApprovalStatus.PENDING,
    ]
    if not is_admin_approver:
        base_conditions.append(
            or_(
                ApprovalStep.approver_id == current_user.id,
                ApprovalStep.role_id.in_(user_role_ids),
            )
        )

    query = (
        select(ApprovalItem)
        .join(ApprovalStep)
        .where(and_(*base_conditions))
        .options(
            selectinload(ApprovalItem.steps),
            selectinload(ApprovalItem.requested_by),
        )
    )
    
    if status:
        query = query.where(ApprovalItem.status == status)
    if resource_type:
        query = query.where(ApprovalItem.resource_type == resource_type)
    if due_before:
        query = query.where(ApprovalItem.due_date <= due_before)
        
    result = await db.execute(query)
    return _attach_requester_names(result.scalars().all())


@router.get("/{id}", response_model=ApprovalItemRead)
async def get_approval_details(
    id: int,
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user)
) -> Any:
    query = select(ApprovalItem).where(ApprovalItem.id == id).options(
        selectinload(ApprovalItem.steps)
    )
    result = await db.execute(query)
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Approval item not found")

    # Authorization: allow viewing for admin approvers, the requester,
    # or any user who is an approver on any step.
    if not _user_can_view_approval(item, current_user):
        raise HTTPException(status_code=403, detail="Not authorized")
        
    return item


@router.get("/{id}/resource")
async def get_approval_resource(
    id: int,
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    query = select(ApprovalItem).where(ApprovalItem.id == id).options(
        selectinload(ApprovalItem.steps)
    )
    result = await db.execute(query)
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Approval item not found")

    if not _user_can_view_approval(item, current_user):
        raise HTTPException(status_code=403, detail="Not authorized")

    # Return a minimal, safe resource payload for common approval types.
    if item.resource_type in ("estimate", "estimate_version"):
        try:
            version_id = int(item.resource_id)
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=400,
                detail="Invalid estimate resource_id",
            )

        version = await db.get(EstimateVersion, version_id)
        if not version:
            raise HTTPException(
                status_code=404,
                detail="Estimate version not found",
            )

        # Include full estimate version details (phases + resource lines)
        # to support approvers reviewing the estimate.
        detailed = (
            await db.execute(
                select(EstimateVersion)
                .where(EstimateVersion.id == version_id)
                .options(
                    selectinload(EstimateVersion.phases),
                    selectinload(EstimateVersion.resource_lines),
                )
            )
        ).scalar_one()
        return {
            "resource_type": item.resource_type,
            "data": (
                EstimateVersionDetailed.model_validate(detailed).model_dump()
            ),
        }

    if item.resource_type in ("leave", "leave_request"):
        try:
            leave_id = int(item.resource_id)
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=400,
                detail="Invalid leave resource_id",
            )

        leave_req = (
            await db.execute(
                select(LeaveRequest)
                .where(LeaveRequest.id == leave_id)
                .options(selectinload(LeaveRequest.leave_type))
            )
        ).scalar_one_or_none()
        if not leave_req:
            raise HTTPException(
                status_code=404,
                detail="Leave request not found",
            )

        return {
            "resource_type": item.resource_type,
            "data": LeaveRequestRead.model_validate(leave_req).model_dump(),
        }

    if item.resource_type == "comp_off_accrual":
        from app.models.comp_off import CompOffAccrual
        try:
            accrual_id = int(item.resource_id)
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=400,
                detail="Invalid comp_off resource_id",
            )
        accrual = await db.get(CompOffAccrual, accrual_id)
        if not accrual:
            raise HTTPException(
                status_code=404,
                detail="Comp-off accrual not found",
            )
        return {
            "resource_type": item.resource_type,
            "data": {
                "id": accrual.id,
                "user_id": accrual.user_id,
                "holiday_date": accrual.holiday_date.isoformat(),
                "holiday_name": accrual.holiday_name,
                "worked_minutes": accrual.worked_minutes,
                "worked_hours_label": (
                    f"{accrual.worked_minutes // 60}h "
                    f"{accrual.worked_minutes % 60:02d}m"
                ),
                "days_credited": accrual.days_credited,
                "status": accrual.status,
                "reason": accrual.reason,
            },
        }

    # Unknown resource type
    return {"resource_type": item.resource_type, "data": None}


@router.post("/{id}/action", response_model=ApprovalItemRead)
async def action_approval(
    id: int,
    action: ApprovalAction,
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user)
) -> Any:
    query = select(ApprovalItem).where(ApprovalItem.id == id).options(
        selectinload(ApprovalItem.steps)
    )
    result = await db.execute(query)
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Approval item not found")
        
    # Find current step
    current_step = next(
        (s for s in item.steps if s.step_number == item.current_step_number),
        None
    )
    
    if not current_step or current_step.status != ApprovalStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail="No pending step found for this approval"
        )
        
    # Check permission
    user_role_ids = [role.id for role in current_user.roles]
    is_authorized = (
        (
            current_step.approver_id
            and current_step.approver_id == current_user.id
        )
        or (
            current_step.role_id
            and current_step.role_id in user_role_ids
        )
    )
    if not is_authorized and _is_admin_approver(current_user):
        is_authorized = True
    if not is_authorized:
        raise HTTPException(
            status_code=403,
            detail="You are not authorized to action this step"
        )

    # Estimate approvals are protected by a dedicated permission.
    if item.resource_type in ("estimate", "estimate_version") and not _user_can_approve_estimates(current_user):
        raise HTTPException(
            status_code=403,
            detail="You are not authorized to approve lead estimates",
        )
        
    # Apply action
    current_step.status = action.status
    current_step.comment = action.comment
    current_step.approver_id = current_user.id
    current_step.actioned_at = datetime.now(timezone.utc)

    is_admin_approver = _is_admin_approver(current_user)
    total_steps = len(item.steps)

    async def _apply_resource_status_update(
        final_status: ApprovalStatus,
    ) -> None:
        # Hook: update resource status based on approval decision.
        if item.resource_type in ("estimate", "estimate_version"):
            try:
                v_id = int(item.resource_id)
                version = await db.get(EstimateVersion, v_id)
                if version:
                    if final_status == ApprovalStatus.APPROVED:
                        version.status = EstimateStatus.APPROVED
                    elif final_status == ApprovalStatus.REJECTED:
                        version.status = EstimateStatus.REJECTED
            except (ValueError, TypeError):
                return
        elif item.resource_type == "requisition":
            from app.models.recruitment import (
                ManpowerRequisition,
                RequisitionStatus,
            )
            try:
                req_id = int(item.resource_id)
                req = await db.get(ManpowerRequisition, req_id)
                if req:
                    if final_status == ApprovalStatus.APPROVED:
                        req.status = RequisitionStatus.APPROVED
                    elif final_status == ApprovalStatus.REJECTED:
                        req.status = RequisitionStatus.REJECTED
            except (ValueError, TypeError):
                return
        elif item.resource_type == "leave_request":
            try:
                leave_id = int(item.resource_id)
                leave_req = await db.get(LeaveRequest, leave_id)
                if leave_req:
                    if final_status == ApprovalStatus.APPROVED:
                        leave_req.status = LeaveStatus.APPROVED
                    elif final_status == ApprovalStatus.REJECTED:
                        leave_req.status = LeaveStatus.REJECTED
            except (ValueError, TypeError):
                return
        elif item.resource_type == "comp_off_accrual":
            from app.models.comp_off import CompOffAccrual
            from app.models.leave import LeaveType, LeaveBalanceLedger
            try:
                accrual_id = int(item.resource_id)
            except (ValueError, TypeError):
                return
            accrual = await db.get(CompOffAccrual, accrual_id)
            if not accrual:
                return
            if final_status == ApprovalStatus.REJECTED:
                accrual.status = "rejected"
                return
            if final_status == ApprovalStatus.APPROVED:
                accrual.status = "approved"
                co_type = (await db.execute(
                    select(LeaveType).where(LeaveType.code == "CO").limit(1)
                )).scalar_one_or_none()
                if co_type is None:
                    return
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

    async def _notify_requester(
        title: str,
        message: str,
        type: str,
    ) -> None:
        if not item.requested_by_id:
            return
        await create_notification(
            db,
            item.requested_by_id,
            title,
            message,
            type,
            item.resource_type,
            item.resource_id,
        )

    async def _notify_next_approver(next_user_id: int) -> None:
        await create_notification(
            db,
            next_user_id,
            "Approval Request Pending",
            f"A {item.resource_type} request is waiting for your approval.",
            "info",
            item.resource_type,
            item.resource_id,
        )

    # One-step-at-a-time chaining: when approving an estimate, an approver can
    # optionally assign the next approver. If none is assigned, the estimate is
    # finalized as approved.
    if (
        item.resource_type in ("estimate", "estimate_version")
        and action.status == ApprovalStatus.APPROVED
        and action.next_approver_id
    ):
        next_user = await db.get(User, int(action.next_approver_id))
        if not next_user or not next_user.is_active:
            raise HTTPException(
                status_code=400,
                detail="Next approver not found or inactive",
            )
        if not _user_can_approve_estimates(next_user):
            raise HTTPException(
                status_code=400,
                detail="Selected next approver is not eligible",
            )

        next_step_number = max((s.step_number for s in item.steps), default=0) + 1
        db.add(
            ApprovalStep(
                approval_item_id=item.id,
                step_number=next_step_number,
                approver_id=next_user.id,
                status=ApprovalStatus.PENDING,
            )
        )
        item.current_step_number = next_step_number
        item.status = ApprovalStatus.PENDING
        await _notify_next_approver(next_user.id)

        await db.commit()
        await db.refresh(item)
        return item

    # Admin override: approving/rejecting finalizes the whole item immediately.
    if is_admin_approver and action.status in (
        ApprovalStatus.APPROVED,
        ApprovalStatus.REJECTED,
        ApprovalStatus.CHANGES_REQUESTED,
    ):
        now = datetime.now(timezone.utc)
        if action.status == ApprovalStatus.APPROVED:
            for step in item.steps:
                if step.status == ApprovalStatus.PENDING:
                    step.status = ApprovalStatus.APPROVED
                    if not step.comment:
                        step.comment = "Auto-approved by admin"
                    step.approver_id = current_user.id
                    step.actioned_at = now

            item.current_step_number = total_steps
            item.status = ApprovalStatus.APPROVED
            await _apply_resource_status_update(ApprovalStatus.APPROVED)
            await _notify_requester(
                "Approval Request Approved",
                f"Your {item.resource_type} request has been approved.",
                "success",
            )
        elif action.status == ApprovalStatus.REJECTED:
            item.status = ApprovalStatus.REJECTED
            await _apply_resource_status_update(ApprovalStatus.REJECTED)
            await _notify_requester(
                "Approval Request Rejected",
                f"Your {item.resource_type} request was rejected.",
                "error",
            )
        else:
            item.status = ApprovalStatus.CHANGES_REQUESTED
            await _notify_requester(
                "Changes Requested",
                f"Changes requested for your {item.resource_type} request.",
                "warning",
            )

        await db.commit()
        await db.refresh(item)
        return item
    
    if action.status == ApprovalStatus.APPROVED:
        # Move to next step or mark item as approved
        if item.current_step_number < total_steps:
            item.current_step_number += 1
            # Notify next approver?
        else:
            item.status = ApprovalStatus.APPROVED
            await _apply_resource_status_update(ApprovalStatus.APPROVED)
            await _notify_requester(
                "Approval Request Approved",
                f"Your {item.resource_type} request has been approved.",
                "success",
            )
    elif action.status == ApprovalStatus.REJECTED:
        item.status = ApprovalStatus.REJECTED
        await _apply_resource_status_update(ApprovalStatus.REJECTED)
        await _notify_requester(
            "Approval Request Rejected",
            f"Your {item.resource_type} request was rejected.",
            "error",
        )
    elif action.status == ApprovalStatus.CHANGES_REQUESTED:
        item.status = ApprovalStatus.CHANGES_REQUESTED
        await _notify_requester(
            "Changes Requested",
            f"Changes requested for your {item.resource_type} request.",
            "warning",
        )

    await db.commit()
    await db.refresh(item)
    return item
