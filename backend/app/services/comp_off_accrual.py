"""Shared comp-off accrual creation (manager -> HR approval chain).

Used by attendance punch-out (holiday / week-off work) and by call-back
compensation (roster emergency change). Callers decide WHETHER an accrual is
due and guard idempotency on (user_id, holiday_date); this only builds the
CompOffAccrual + its ApprovalItem + steps. Caller commits.
"""
from datetime import date
from typing import Optional

from sqlalchemy import select

from app.models.approval import ApprovalItem, ApprovalStatus, ApprovalStep
from app.models.comp_off import CompOffAccrual
from app.models.user import Role


async def create_comp_off_accrual(
    db,
    *,
    user,
    work_date: date,
    holiday_name: Optional[str],
    attendance_id: Optional[int],
    worked_minutes: int,
    reason: str,
    days_credited: float = 1.0,
) -> CompOffAccrual:
    accrual = CompOffAccrual(
        user_id=user.id,
        holiday_date=work_date,
        holiday_name=holiday_name,
        attendance_id=attendance_id,
        worked_minutes=worked_minutes,
        days_credited=days_credited,
        status="pending",
        reason=reason,
    )
    db.add(accrual)
    await db.flush()

    approval_item = ApprovalItem(
        resource_type="comp_off_accrual",
        resource_id=str(accrual.id),
        status=ApprovalStatus.PENDING,
        current_step_number=1,
        requested_by_id=user.id,
    )
    db.add(approval_item)
    await db.flush()

    step_idx = 1
    if user.manager_id:
        db.add(ApprovalStep(
            approval_item_id=approval_item.id,
            step_number=step_idx,
            approver_id=user.manager_id,
            status=ApprovalStatus.PENDING,
        ))
        step_idx += 1

    hr_role = (await db.execute(
        select(Role).where(Role.name == "HR")
    )).scalar_one_or_none()
    if hr_role is None:
        raise RuntimeError(
            "HR role not configured — comp-off accrual skipped"
        )
    db.add(ApprovalStep(
        approval_item_id=approval_item.id,
        step_number=step_idx,
        role_id=hr_role.id,
        status=ApprovalStatus.PENDING,
    ))
    return accrual
