"""Pieces shared by the request features that route either through an
approval chain or directly to a manager/HR (optional holidays, work-location
requests). Services never commit; the endpoint commits once."""
from datetime import date, datetime, timedelta, timezone
from typing import Awaitable, Callable, Optional

from fastapi import HTTPException
from sqlalchemy import select

from app.models.approval_chain import (
    ApprovalChain, ChainedApprovalInstance, ChainedApprovalStatus,
    ChainedApprovalStepInstance, StepInstanceStatus,
)
from app.models.employee import Employee
from app.models.user import Permission, Role, User
from app.services.attendance_lock import LockRetry, assert_attendance_editable


async def close_instance(db, inst) -> None:
    """Cancel a (locked) pending chain instance and skip its pending steps."""
    if inst is None or inst.status != ChainedApprovalStatus.PENDING:
        return
    now = datetime.now(timezone.utc)
    inst.status = ChainedApprovalStatus.CANCELLED
    inst.finalized_at = now
    sis = (await db.execute(
        select(ChainedApprovalStepInstance).where(
            ChainedApprovalStepInstance.instance_id == inst.id,
            ChainedApprovalStepInstance.status == StepInstanceStatus.PENDING)
        .execution_options(populate_existing=True))).scalars().all()
    for si in sis:
        si.status = StepInstanceStatus.SKIPPED
        si.comment = "cancelled_by_requester"
        si.actioned_at = now


async def direct_approver_ids(db, employee_user_id: int) -> list[int]:
    """Who to notify on the direct path: the reporting manager, else HR
    (holders of 'hr employee write') and superusers."""
    mgr = (await db.execute(select(User.manager_id).where(
        User.id == employee_user_id))).scalar_one_or_none()
    if mgr:
        return [mgr]
    sup = (await db.execute(select(User.id).where(
        User.is_active.is_(True), User.is_superuser.is_(True)))).scalars().all()
    perm = (await db.execute(
        select(User.id).join(User.roles).join(Role.permissions)
        .where(User.is_active.is_(True),
               Permission.name == "hr employee write")
    )).scalars().all()
    return sorted((set(sup) | set(perm)) - {employee_user_id})


async def assert_dates_unlocked(db, start: date,
                                end: Optional[date] = None) -> None:
    """409 "payroll period locked: ..." when any month touched by
    [start, end] is locked by a payroll run (one check per month)."""
    end = end or start
    seen, d = set(), start
    while d <= end:
        if (d.year, d.month) not in seen:
            seen.add((d.year, d.month))
            try:
                await assert_attendance_editable(db, d, fresh=True)
            except LockRetry:
                raise
            except HTTPException as e:
                if e.status_code == 409:
                    raise HTTPException(
                        409, f"payroll period locked: {e.detail}")
                raise
        d += timedelta(days=1)


async def chained_ids(db, entity_type: str, ids) -> set:
    if not ids:
        return set()
    return set((await db.execute(
        select(ChainedApprovalInstance.entity_id).where(
            ChainedApprovalInstance.entity_type == entity_type,
            ChainedApprovalInstance.entity_id.in_(ids)))).scalars().all())


async def chain_instance_id(db, entity_type: str,
                            entity_id: int) -> Optional[int]:
    return (await db.execute(
        select(ChainedApprovalInstance.id).where(
            ChainedApprovalInstance.entity_type == entity_type,
            ChainedApprovalInstance.entity_id == entity_id)
        .order_by(ChainedApprovalInstance.id.desc()).limit(1)
    )).scalar_one_or_none()


async def route_submission(
    db, *, entity_type: str, entity_id: int, submitter, context: dict,
    audit: Callable[[str], None],
    finalize_approved: Callable[[], Awaitable[None]],
    notify_direct: Callable[[list], Awaitable[None]],
) -> None:
    """Route a freshly created entity: active chain -> instantiate (commit
    =False) and finalize when it auto-approves; otherwise notify the direct
    approvers. `audit(routed_via)` is called once before routing."""
    from app.api.v1.endpoints.approval_chains import instantiate_for_entity
    chain_exists = (await db.execute(select(ApprovalChain.id).where(
        ApprovalChain.entity_type == entity_type,
        ApprovalChain.is_active.is_(True)).limit(1))).first() is not None
    audit("chain" if chain_exists else "direct")
    if chain_exists:
        dept = (await db.execute(select(Employee.department).where(
            Employee.user_id == submitter.id))).scalar_one_or_none()
        inst = await instantiate_for_entity(
            db=db, entity_type=entity_type, entity_id=entity_id,
            submitter=submitter, amount_paise=0, department=dept,
            context=context, commit=False)
        if inst.status == ChainedApprovalStatus.APPROVED:
            await finalize_approved()
    else:
        await notify_direct(await direct_approver_ids(db, submitter.id))
