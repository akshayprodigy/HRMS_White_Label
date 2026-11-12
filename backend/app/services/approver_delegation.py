"""Out-of-office approval delegation helpers (Task 6).

A delegation lets `delegate_id` see and act on pending steps whose named
approver (`approver_id` / `approver_user_id`) is `user_id`. Role-held steps
are not delegated. Delegations are NOT transitive (A->B, B->C: C cannot act
for A) because only delegations whose delegate is the caller are consulted.
Dates are UTC calendar days (product convention).
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Dict, Optional

from sqlalchemy import and_, or_, select

from app.models.approver_delegation import ApproverDelegation
from app.models.leave import LeaveRequest, LeaveStatus
from app.models.user import User


def today_utc() -> date:
    return datetime.now(timezone.utc).date()


async def active_delegators(
    db, delegate_id: int, today: Optional[date] = None,
) -> Dict[int, ApproverDelegation]:
    """{delegator_user_id: delegation} that are live today for `delegate_id`."""
    today = today or today_utc()
    rows = (await db.execute(
        select(ApproverDelegation)
        .join(User, User.id == ApproverDelegation.user_id)
        .where(
            ApproverDelegation.delegate_id == delegate_id,
            ApproverDelegation.user_id != delegate_id,
            ApproverDelegation.revoked_at.is_(None),
            ApproverDelegation.starts_on <= today,
            or_(ApproverDelegation.ends_on.is_(None),
                ApproverDelegation.ends_on >= today),
            User.is_active.is_(True),
        ).order_by(ApproverDelegation.id)
    )).scalars().all()
    out: Dict[int, ApproverDelegation] = {}
    leave_ids = [d.user_id for d in rows if d.only_when_on_leave]
    on_leave: set = set()
    if leave_ids:
        on_leave = set((await db.execute(
            select(LeaveRequest.employee_id).where(
                LeaveRequest.employee_id.in_(leave_ids),
                LeaveRequest.status == LeaveStatus.APPROVED,
                LeaveRequest.start_date <= today,
                LeaveRequest.end_date >= today,
            ))).scalars().all())
    for d in rows:
        if d.only_when_on_leave and d.user_id not in on_leave:
            continue
        out.setdefault(d.user_id, d)
    return out


async def delegator_ids(db, delegate_id: int) -> list[int]:
    return list((await active_delegators(db, delegate_id)).keys())


async def user_names(db, ids) -> Dict[int, str]:
    ids = list({i for i in ids if i})
    if not ids:
        return {}
    rows = (await db.execute(
        select(User.id, User.full_name, User.email).where(User.id.in_(ids))
    )).all()
    return {r[0]: (r[1] or r[2]) for r in rows}
