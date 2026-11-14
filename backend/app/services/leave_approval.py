"""Single path for deciding a leave / comp-off approval step.

Both `POST /approvals/{id}/action` and `POST /leave/approvals/{id}/action`
delegate here, so step advance, final status, ledger debit/credit and the
requester/approver notifications happen in exactly one place. Authorization
(who may act) stays in the endpoints.

Idempotency: the ApprovalItem (and the LeaveRequest / CompOffAccrual row) is
locked FOR UPDATE with fresh state, and an already-decided item or step is
rejected with 400 — a concurrent second approval can never debit twice.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import and_, select, update
from sqlalchemy.orm import selectinload

from app.models.approval import ApprovalItem, ApprovalStatus, ApprovalStep
from app.models.comp_off import CompOffAccrual
from app.models.leave import (
    LeaveBalanceLedger, LeaveRequest, LeaveStatus, LeaveType,
)
from app.models.user import Role, User, user_roles

logger = logging.getLogger(__name__)

LEAVE_RESOURCE = "leave_request"
COMP_OFF_RESOURCE = "comp_off_accrual"
DECISION_RESOURCES = (LEAVE_RESOURCE, COMP_OFF_RESOURCE)
ROLE_NOTIFY_CAP = 25
ALREADY_ACTIONED = "Approval already actioned"


def leave_days(leave: LeaveRequest) -> float:
    return 0.5 if leave.is_half_day else (leave.end_date - leave.start_date).days + 1


async def _lock(db, stmt, msg):
    from app.api.v1.endpoints.roster_common import lock_row
    return await lock_row(db, stmt, msg)


async def _bump_ledger(db, user_id: int, leave_type_id: int, *,
                       used: float = 0.0, balance: float = 0.0) -> None:
    """Atomic ledger adjustment. `UPDATE ... SET col = col + d` is a current
    read, so concurrent approvals for the same employee never lose updates
    (a SELECT ... FOR UPDATE would instead hit MariaDB 1020 on a stale
    snapshot). The ledger has no unique (user, type) key, so the
    create-if-missing path runs under the user-row lock; the UPDATE rowcount
    (a current read) decides whether a row exists."""
    from sqlalchemy.exc import OperationalError
    from app.api.v1.endpoints.roster_common import _map_db_error, lock_user_rows
    await lock_user_rows(db, [user_id], ALREADY_ACTIONED)
    try:
        res = await db.execute(
            update(LeaveBalanceLedger).where(and_(
                LeaveBalanceLedger.user_id == user_id,
                LeaveBalanceLedger.leave_type_id == leave_type_id,
            )).values(used=LeaveBalanceLedger.used + used,
                      balance=LeaveBalanceLedger.balance + balance)
            .execution_options(synchronize_session=False))
    except OperationalError as exc:
        # MariaDB 1020: ledger row changed since this transaction's snapshot
        # (a concurrent approval for the same employee committed first).
        # Nothing was applied; the client retries.
        mapped = await _map_db_error(db, exc, ALREADY_ACTIONED)
        if mapped is None:
            raise
        raise mapped from exc
    if res.rowcount == 0:
        db.add(LeaveBalanceLedger(
            user_id=user_id, leave_type_id=leave_type_id,
            balance=balance, used=used))


async def _debit_leave(db, leave: LeaveRequest) -> None:
    await _bump_ledger(db, leave.employee_id, leave.leave_type_id,
                       used=leave_days(leave))


async def _credit_comp_off(db, accrual: CompOffAccrual) -> None:
    co_type = (await db.execute(
        select(LeaveType).where(LeaveType.code == "CO").limit(1)
    )).scalar_one_or_none()
    if co_type is None:
        return
    await _bump_ledger(db, accrual.user_id, co_type.id,
                       balance=accrual.days_credited)


async def step_approver_ids(db, step: Optional[ApprovalStep]) -> list[int]:
    """Users to alert for a pending step: the named approver, else active
    holders of the step's role (capped)."""
    if step is None:
        return []
    if step.approver_id:
        return [step.approver_id]
    if step.role_id:
        rows = (await db.execute(
            select(User.id).join(user_roles, user_roles.c.user_id == User.id)
            .where(user_roles.c.role_id == step.role_id, User.is_active.is_(True))
            .order_by(User.id).limit(ROLE_NOTIFY_CAP)
        )).scalars().all()
        return list(rows)
    return []


async def _safe_notify(db, **kw) -> None:
    """Best-effort rich notification inside a savepoint; never raises."""
    from app.services.notifications_delivery import notify
    try:
        async with db.begin_nested():
            await notify(db, **kw)
    except Exception:  # pragma: no cover
        logger.warning("leave notification failed", exc_info=True)


async def notify_step_approvers(
    db, *, leave: LeaveRequest, step: Optional[ApprovalStep],
    requester_name: str, event_type: str = "approval_pending",
) -> None:
    """Alert whoever must act on `step` that a leave awaits them."""
    msg = (f"{requester_name} requested leave "
           f"{leave.start_date} to {leave.end_date}. Open the ERP to review.")
    for uid in await step_approver_ids(db, step):
        if uid == leave.employee_id:
            continue
        await _safe_notify(
            db, user_id=uid, event_type=event_type,
            title=f"Leave request from {requester_name}", message=msg,
            resource_type=LEAVE_RESOURCE, resource_id=str(leave.id),
            context={"title": f"Leave request from {requester_name}",
                     "message": msg},
        )


async def notify_new_leave(db, *, leave: LeaveRequest, item: ApprovalItem,
                           requester_name: str) -> None:
    """Called after apply / apply-on-behalf creates the chain (steps flushed)."""
    steps = (await db.execute(select(ApprovalStep).where(
        ApprovalStep.approval_item_id == item.id,
        ApprovalStep.step_number == item.current_step_number,
    ))).scalars().all()
    await notify_step_approvers(
        db, leave=leave, step=steps[0] if steps else None,
        requester_name=requester_name,
        event_type="leave_submitted",
    )


async def apply_leave_decision(
    db, item: ApprovalItem, actor: User, approve: bool,
    comment: Optional[str] = None, *, override_all: bool = False,
    expected_step_id: Optional[int] = None,
) -> str:
    """Apply an approve/reject decision on `item`'s current step.

    Caller has already authorized `actor` for the step `expected_step_id`; if
    the freshly locked current step differs (someone acted meanwhile) → 409.
    Caller has already authorized `actor`. Returns "advanced", "approved" or
    "rejected". Does not commit. `override_all` (admin override) approves every
    pending step at once.
    """
    locked = await _lock(
        db,
        select(ApprovalItem).where(ApprovalItem.id == item.id)
        .options(selectinload(ApprovalItem.steps)),
        ALREADY_ACTIONED,
    )
    if locked is None:
        raise HTTPException(status_code=404, detail="Approval item not found")
    item = locked
    if item.status != ApprovalStatus.PENDING:
        raise HTTPException(status_code=409, detail=ALREADY_ACTIONED)
    steps = sorted(
        (await db.execute(
            select(ApprovalStep).where(ApprovalStep.approval_item_id == item.id)
            .execution_options(populate_existing=True)
        )).scalars().all(), key=lambda s: s.step_number)
    current = next(
        (s for s in steps if s.step_number == item.current_step_number), None)
    if current is None or current.status != ApprovalStatus.PENDING:
        raise HTTPException(
            status_code=400, detail="No pending step found for this approval")
    if expected_step_id is not None and current.id != expected_step_id:
        raise HTTPException(status_code=409, detail=ALREADY_ACTIONED)

    now = datetime.now(timezone.utc)
    current.status = ApprovalStatus.APPROVED if approve else ApprovalStatus.REJECTED
    current.comment = comment
    current.approver_id = actor.id
    current.actioned_at = now

    leave = accrual = None
    if item.resource_type in DECISION_RESOURCES:
        rid = str(item.resource_id or "")
        if not rid.isdigit():
            raise HTTPException(status_code=409, detail="Invalid resource id")
        model = LeaveRequest if item.resource_type == LEAVE_RESOURCE \
            else CompOffAccrual
        row = await _lock(
            db, select(model).where(model.id == int(rid)), ALREADY_ACTIONED)
        if row is None:
            raise HTTPException(
                status_code=409, detail="Underlying request not found")
        if item.resource_type == LEAVE_RESOURCE:
            leave = row
        else:
            accrual = row

    if not approve:
        item.status = ApprovalStatus.REJECTED
        if leave is not None:
            leave.status = LeaveStatus.REJECTED
            from app.services.emergency_leave import dismiss_gaps_for_leave
            await dismiss_gaps_for_leave(
                db, leave, actor.id, "Leave rejected/cancelled")
        if accrual is not None:
            accrual.status = "rejected"
        outcome = "rejected"
    else:
        if override_all:
            for s in steps:
                if s.status == ApprovalStatus.PENDING:
                    s.status = ApprovalStatus.APPROVED
                    if not s.comment:
                        s.comment = "Auto-approved by admin"
                    s.approver_id = actor.id
                    s.actioned_at = now
            nxt = None
        else:
            nxt = next((s for s in steps
                        if s.step_number == item.current_step_number + 1), None)
        if nxt is not None:
            item.current_step_number += 1
            from app.services.approval_sla import next_due
            item.due_date = await next_due(db, now)
            outcome = "advanced"
        else:
            if override_all:
                item.current_step_number = len(steps)
            item.status = ApprovalStatus.APPROVED
            if leave is not None and leave.status != LeaveStatus.APPROVED:
                leave.status = LeaveStatus.APPROVED
                await _debit_leave(db, leave)
            if accrual is not None and accrual.status != "approved":
                accrual.status = "approved"
                await _credit_comp_off(db, accrual)
            outcome = "approved"

    if leave is not None:
        await _notify_leave_outcome(db, leave, item, steps, outcome, nxt if approve else None)
    return outcome


async def _notify_leave_outcome(db, leave, item, steps, outcome, next_step):
    if outcome == "advanced" and next_step is not None:
        emp = await db.get(User, leave.employee_id)
        await notify_step_approvers(
            db, leave=leave, step=next_step,
            requester_name=(emp.full_name or emp.email) if emp else "An employee")
        return
    if outcome not in ("approved", "rejected"):
        return
    ok = outcome == "approved"
    msg = (f"Your leave {leave.start_date} to {leave.end_date} was "
           f"{'approved' if ok else 'rejected'}.")
    await _safe_notify(
        db, user_id=leave.employee_id,
        event_type="leave_approved" if ok else "leave_rejected",
        title="Leave approved" if ok else "Leave rejected", message=msg,
        resource_type=LEAVE_RESOURCE, resource_id=str(leave.id),
        notif_type="success" if ok else "error",
        context={"title": "Leave approved" if ok else "Leave rejected",
                 "message": msg},
    )
