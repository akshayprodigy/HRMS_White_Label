"""Section R: apply an approved shift-change request.

Shared by shifts.py (auto-approve short-circuit) and
approval_chains.py (chain finalize) — lives here so neither endpoint
module has to import the other.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.shift import (
    EmployeeShiftAssignment,
    ShiftChangeRequest,
    ShiftChangeStatus,
)


async def apply_shift_change(
    db: AsyncSession, req: ShiftChangeRequest
) -> EmployeeShiftAssignment:
    """Materialize the approved request as an assignment.

    Any existing assignment overlapping the new open-ended range is
    closed the day before the new one starts (same semantics as the
    assign endpoint's close_previous=True). Does NOT commit — the
    caller owns the transaction.
    """
    prior_end = req.effective_from - timedelta(days=1)
    overlapping = (await db.execute(
        select(EmployeeShiftAssignment).where(
            EmployeeShiftAssignment.employee_id == req.user_id,
            or_(
                EmployeeShiftAssignment.effective_to.is_(None),
                EmployeeShiftAssignment.effective_to >= req.effective_from,
            ),
        )
    )).scalars().all()
    for o in overlapping:
        if o.effective_from > prior_end:
            # Assignment starts on/after the change date — supersede it
            # entirely by ending it before it begins is impossible, so
            # shrink-to-nothing is replaced by deleting the future row.
            await db.delete(o)
        else:
            o.effective_to = prior_end
            db.add(o)

    assignment = EmployeeShiftAssignment(
        employee_id=req.user_id,
        shift_template_id=req.requested_shift_template_id,
        effective_from=req.effective_from,
        effective_to=None,
        note=f"shift change request #{req.id}",
    )
    db.add(assignment)

    req.status = ShiftChangeStatus.APPROVED
    req.decided_at = datetime.now(timezone.utc)
    db.add(req)
    return assignment
