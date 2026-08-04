"""Late-mark processing (W9).

Counts late marks per employee per month, converts them into leave-day
deductions, and cascades Casual Leave -> Privilege Leave -> Loss of Pay.
CL/PL debits hit LeaveBalanceLedger.used; the residual LOP days are stored
on LateMarkDeduction and later folded into payroll payable_days.

Processing is idempotent: re-running a month first reverses prior
(unpaid) deductions before recomputing, so ledgers never double-debit.
Deductions already stamped with a payroll_run_id are locked and skipped.
"""
import calendar
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance import Attendance
from app.models.employee import Employee
from app.models.late_mark import LateMarkDeduction, LateMarkRule, LateMarkScope
from app.models.leave import LeaveBalanceLedger
from app.models.shift import ShiftTemplate


@dataclass
class RuleSet:
    org_default: Optional[LateMarkRule]
    by_shift: dict          # shift_template_id -> LateMarkRule

    def for_shift(self, shift_template_id: Optional[int]) -> Optional[LateMarkRule]:
        if shift_template_id is not None and shift_template_id in self.by_shift:
            return self.by_shift[shift_template_id]
        return self.org_default


async def load_rules(db: AsyncSession) -> RuleSet:
    rules = (await db.execute(
        select(LateMarkRule).where(LateMarkRule.is_active.is_(True))
    )).scalars().all()
    org = next((r for r in rules if r.scope == LateMarkScope.ORG_DEFAULT), None)
    by_shift = {r.shift_template_id: r for r in rules if r.scope == LateMarkScope.SHIFT and r.shift_template_id}
    return RuleSet(org_default=org, by_shift=by_shift)


def _is_late(punch_in: datetime, work_date: date, shift: ShiftTemplate, grace_minutes: int) -> bool:
    """A punch-in later than shift start + grace is a late mark. Compares as
    naive wall-clock (attendance is stored UTC-naive; shift.start_time is a
    wall-clock time), so tz-aware/naive rows both work."""
    from datetime import timedelta
    pin = punch_in.replace(tzinfo=None) if punch_in.tzinfo is not None else punch_in
    start = datetime.combine(work_date, shift.start_time)
    return pin > start + timedelta(minutes=grace_minutes)


async def _available(
    db: AsyncSession, user_id: int, leave_type_id: Optional[int],
) -> tuple[Optional[LeaveBalanceLedger], float]:
    """Ledger + available balance for a user's configured cascade leave type.
    Returns (None, 0) when the rule doesn't configure this tier."""
    if leave_type_id is None:
        return None, 0.0
    row = (await db.execute(
        select(LeaveBalanceLedger).where(and_(
            LeaveBalanceLedger.user_id == user_id,
            LeaveBalanceLedger.leave_type_id == leave_type_id,
        ))
    )).scalars().first()
    if row is None:
        return None, 0.0
    return row, max(0.0, (row.balance or 0.0) - (row.used or 0.0))


def _count_late_marks(rows, shift_by_id: dict, rules: RuleSet) -> int:
    late = 0
    for att in rows:
        if att.captured_at is None:
            continue
        shift = shift_by_id.get(att.shift_template_id)
        if shift is None:
            continue  # no shift snapshot -> cannot judge lateness
        rule = rules.for_shift(att.shift_template_id)
        grace = rule.grace_minutes if rule else 10
        if _is_late(att.captured_at, att.work_date, shift, grace):
            late += 1
    return late


async def process_month(
    db: AsyncSession, year: int, month: int, *, commit: bool = True,
) -> dict:
    """Compute + persist late-mark deductions for a month. Returns a summary.
    Reverses prior unpaid deductions for the period first (idempotent)."""
    rules = await load_rules(db)
    if rules.org_default is None:
        return {"processed": 0, "skipped_locked": 0, "note": "no active org-default late-mark rule"}

    org = rules.org_default
    num_days = calendar.monthrange(year, month)[1]
    start_d, end_d = date(year, month, 1), date(year, month, num_days)

    shift_by_id = {s.id: s for s in (await db.execute(select(ShiftTemplate))).scalars().all()}

    # Reverse prior UNPAID deductions for this period (credit ledgers back), keep locked ones.
    prior = (await db.execute(
        select(LateMarkDeduction).where(and_(
            LateMarkDeduction.year == year, LateMarkDeduction.month == month,
        ))
    )).scalars().all()
    locked_users = set()
    for d in prior:
        if d.payroll_run_id is not None:
            locked_users.add(d.user_id)
            continue
        for lt_id, days in ((org.first_leave_type_id, d.cl_days), (org.second_leave_type_id, d.pl_days)):
            if days:
                ledger, _ = await _available(db, d.user_id, lt_id)
                if ledger:
                    ledger.used = max(0.0, (ledger.used or 0.0) - days)
    await db.execute(delete(LateMarkDeduction).where(and_(
        LateMarkDeduction.year == year, LateMarkDeduction.month == month,
        LateMarkDeduction.payroll_run_id.is_(None),
    )))

    employees = (await db.execute(
        select(Employee).where(Employee.status == "active")
    )).scalars().all()

    processed = 0
    for emp in employees:
        if emp.user_id in locked_users:
            continue
        att_rows = (await db.execute(
            select(Attendance).where(and_(
                Attendance.user_id == emp.user_id,
                Attendance.work_date >= start_d, Attendance.work_date <= end_d,
            ))
        )).scalars().all()
        late_count = _count_late_marks(att_rows, shift_by_id, rules)
        blocks = late_count // org.lates_per_deduction
        deduct = round(blocks * org.deduction_days_per_block, 2)
        if deduct <= 0:
            continue

        # Cascade first_leave_type -> second_leave_type -> LOP (configurable).
        remaining = deduct
        cl_ledger, cl_avail = await _available(db, emp.user_id, org.first_leave_type_id)
        cl_take = min(remaining, cl_avail)
        if cl_take > 0 and cl_ledger:
            cl_ledger.used = (cl_ledger.used or 0.0) + cl_take
            remaining -= cl_take
        pl_ledger, pl_avail = await _available(db, emp.user_id, org.second_leave_type_id)
        pl_take = min(remaining, pl_avail)
        if pl_take > 0 and pl_ledger:
            pl_ledger.used = (pl_ledger.used or 0.0) + pl_take
            remaining -= pl_take
        lop = round(remaining, 2)

        db.add(LateMarkDeduction(
            user_id=emp.user_id, year=year, month=month,
            late_count=late_count, deducted_days=deduct,
            cl_days=round(cl_take, 2), pl_days=round(pl_take, 2), lop_days=lop,
        ))
        processed += 1

    if commit:
        await db.commit()
    return {"processed": processed, "skipped_locked": len(locked_users)}


async def lop_days_for_run(db: AsyncSession, year: int, month: int) -> dict:
    """{user_id: lop_days} for a month's unpaid late-mark deductions — the
    payroll hook. Only rows not yet tied to a run are returned."""
    rows = (await db.execute(
        select(LateMarkDeduction).where(and_(
            LateMarkDeduction.year == year, LateMarkDeduction.month == month,
            LateMarkDeduction.payroll_run_id.is_(None),
            LateMarkDeduction.lop_days > 0,
        ))
    )).scalars().all()
    return {r.user_id: r.lop_days for r in rows}
