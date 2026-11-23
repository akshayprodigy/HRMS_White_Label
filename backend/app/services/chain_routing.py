"""Pieces shared by the request features that route either through an
approval chain or directly to a manager/HR (optional holidays, work-location
requests). Services never commit; the endpoint commits once."""
from datetime import date, datetime, timedelta, timezone
from typing import Awaitable, Callable, Optional

from fastapi import HTTPException
from sqlalchemy import delete, select

from app.models.approval_chain import (
    ApprovalChain, ChainedApprovalInstance, ChainedApprovalStatus,
    ChainedApprovalStepInstance, StepInstanceStatus,
)
from app.models.employee import Employee
from app.models.notification import Notification
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


def choose_direct_approvers(employee_user_id: int, manager_id: Optional[int],
                            manager_active: bool, hr_ids) -> list[int]:
    """Pure rule: an active reporting manager decides; otherwise HR
    (holders of 'hr employee write') and superusers (already active-only),
    never the requester."""
    if manager_id and manager_active and manager_id != employee_user_id:
        return [manager_id]
    return sorted(set(hr_ids) - {employee_user_id})


async def direct_approver_ids(db, employee_user_id: int) -> list[int]:
    """Who to notify on the direct path: the active reporting manager, else
    (no manager, or the manager is inactive) HR and superusers."""
    mgr = (await db.execute(select(User.manager_id).where(
        User.id == employee_user_id))).scalar_one_or_none()
    mgr_active = False
    if mgr:
        mgr_active = bool((await db.execute(select(User.is_active).where(
            User.id == mgr))).scalar_one_or_none())
        if mgr_active:
            return choose_direct_approvers(employee_user_id, mgr, True, [])
    sup = (await db.execute(select(User.id).where(
        User.is_active.is_(True), User.is_superuser.is_(True)))).scalars().all()
    perm = (await db.execute(
        select(User.id).join(User.roles).join(Role.permissions)
        .where(User.is_active.is_(True),
               Permission.name == "hr employee write")
    )).scalars().all()
    return choose_direct_approvers(
        employee_user_id, mgr, mgr_active, set(sup) | set(perm))


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


async def _drop_unactionable_instance(db, inst) -> bool:
    """These requests (work location, optional holidays) are only ever taken
    once a person approves them. An instance that auto-approved (amount
    threshold / no applicable steps) or whose current step has no pending
    approver would either grant the request with nobody deciding or strand
    it. Delete such an instance with its step rows and notifications so the
    request falls back to the direct path. Returns True when dropped."""
    if inst.status == ChainedApprovalStatus.PENDING:
        # Only rows held by an ACTIVE user count: a step whose pending
        # approvers are all deactivated would strand the request.
        pending = (await db.execute(
            select(ChainedApprovalStepInstance.id)
            .join(User, User.id == ChainedApprovalStepInstance.approver_user_id)
            .where(
                ChainedApprovalStepInstance.instance_id == inst.id,
                ChainedApprovalStepInstance.step_order
                == inst.current_step_order,
                ChainedApprovalStepInstance.status
                == StepInstanceStatus.PENDING,
                User.is_active.is_(True)).limit(1))).first()
        if pending is not None:
            return False
    await db.execute(delete(Notification).where(
        Notification.resource_type == "chained_approval_instance",
        Notification.resource_id == str(inst.id)))
    await db.execute(delete(ChainedApprovalStepInstance).where(
        ChainedApprovalStepInstance.instance_id == inst.id))
    await db.delete(inst)
    await db.flush()
    return True


async def route_submission(
    db, *, entity_type: str, entity_id: int, submitter, context: dict,
    audit: Callable[[str], None],
    notify_direct: Callable[[list], Awaitable[None]],
) -> None:
    """Route a freshly created entity: an active chain with a real approver
    on its current step -> instantiate (commit=False); otherwise notify the
    direct approvers (reporting manager, else HR/superusers). Never
    approves on its own: the entity stays pending until someone decides.
    `audit(routed_via)` is called once after routing."""
    from app.api.v1.endpoints.approval_chains import instantiate_for_entity
    chain_exists = (await db.execute(select(ApprovalChain.id).where(
        ApprovalChain.entity_type == entity_type,
        ApprovalChain.is_active.is_(True)).limit(1))).first() is not None
    if chain_exists:
        dept = (await db.execute(select(Employee.department).where(
            Employee.user_id == submitter.id))).scalar_one_or_none()
        inst = await instantiate_for_entity(
            db=db, entity_type=entity_type, entity_id=entity_id,
            submitter=submitter, amount_paise=0, department=dept,
            context=context, commit=False, exclude_submitter=True)
        if not await _drop_unactionable_instance(db, inst):
            audit("chain")
            return
    audit("direct")
    await notify_direct(await direct_approver_ids(db, submitter.id))
