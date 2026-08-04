"""Separation-of-duties guard (W3).

Blocks a user from approving their own request across the legacy approval
paths (leave, overtime, manpower requisition, comp-off). Enforced at action
time by comparing the acting approver to the resolved request owner — no
schema change. The generic chain engine already has skip_if_same_person (F4);
this covers the legacy engines it doesn't.
"""
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

SELF_APPROVAL_DETAIL = "You cannot approve your own request (separation of duties)."


def is_self_approval(approver_id: int, requester_id: Optional[int]) -> bool:
    return requester_id is not None and approver_id == requester_id


def guard_self_approval(approver_id: int, requester_id: Optional[int]) -> None:
    if is_self_approval(approver_id, requester_id):
        raise HTTPException(status_code=403, detail=SELF_APPROVAL_DETAIL)


async def resolve_approval_owner_id(db: AsyncSession, item) -> Optional[int]:
    """Resolve the user who owns the request behind an ApprovalItem.

    Prefers the explicit requested_by_id; falls back to the underlying
    resource's owner for legacy rows where it's NULL. Returns None for
    unknown types (guard then fails open — those have no self-approval path).
    """
    if getattr(item, "requested_by_id", None):
        return item.requested_by_id
    rt = getattr(item, "resource_type", None)
    rid = getattr(item, "resource_id", None)
    if rid is None:
        return None
    try:
        rid_int = int(rid)
    except (TypeError, ValueError):
        return None

    if rt == "leave_request":
        from app.models.leave import LeaveRequest
        row = await db.get(LeaveRequest, rid_int)
        return row.employee_id if row else None
    if rt == "requisition":
        from app.models.recruitment import ManpowerRequisition
        row = await db.get(ManpowerRequisition, rid_int)
        return row.creator_id if row else None
    if rt == "comp_off_accrual":
        from app.models.comp_off import CompOffAccrual
        row = await db.get(CompOffAccrual, rid_int)
        return row.user_id if row else None
    return None
