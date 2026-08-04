import pytest
from fastapi import HTTPException

from app.services.self_approval import (
    is_self_approval, guard_self_approval, resolve_approval_owner_id,
    SELF_APPROVAL_DETAIL,
)


def test_is_self_approval_pure():
    assert is_self_approval(5, 5) is True
    assert is_self_approval(5, 6) is False
    assert is_self_approval(5, None) is False


def test_guard_raises_only_on_self():
    with pytest.raises(HTTPException) as ei:
        guard_self_approval(5, 5)
    assert ei.value.status_code == 403
    assert ei.value.detail == SELF_APPROVAL_DETAIL
    # different / unknown requester -> no raise
    assert guard_self_approval(5, 6) is None
    assert guard_self_approval(5, None) is None


@pytest.mark.asyncio
async def test_resolver_prefers_requested_by_id():
    class _Item:
        requested_by_id = 42
        resource_type = "leave_request"
        resource_id = "1"
    # requested_by_id present -> returned without a DB hit
    assert await resolve_approval_owner_id(None, _Item()) == 42


@pytest.mark.asyncio
async def test_resolver_falls_back_to_leave_owner(db):
    from datetime import date
    from app.models.leave import LeaveRequest, LeaveStatus, LeaveType
    from app.models.user import User
    from sqlalchemy import select
    lt = (await db.execute(select(LeaveType).limit(1))).scalars().first()
    user = (await db.execute(select(User).limit(1))).scalars().first()
    lr = LeaveRequest(
        employee_id=user.id, leave_type_id=lt.id,
        start_date=date(2026, 6, 1), end_date=date(2026, 6, 1),
        reason="sod test", status=LeaveStatus.SUBMITTED, created_by_user_id=user.id,
    )
    db.add(lr)
    await db.flush()

    class _Item:
        requested_by_id = None
        resource_type = "leave_request"
        resource_id = str(lr.id)

    assert await resolve_approval_owner_id(db, _Item()) == user.id
