"""Effective shift resolution: roster first, then shift assignment.

Precedence for a (user, date):
  1. PUBLISHED RosterEntry -> explicit week-off, or its shift template.
     (A blank published cell, and any DRAFT entry, is ignored.)
  2. Active EmployeeShiftAssignment (latest effective_from wins); the
     template's weekly_offs decide `is_week_off`.
  3. Nothing -> source "none" (callers apply the org default shift).

`employee_id` on both tables is a User id, not an Employee PK.
"""
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from app.models.roster import RosterEntry, RosterStatus
from app.models.shift import EmployeeShiftAssignment, ShiftTemplate


@dataclass(frozen=True)
class EffectiveShift:
    shift: Optional[ShiftTemplate]
    is_week_off: bool
    source: str  # "roster" | "assignment" | "none"


def _resolve(
    roster: Optional[RosterEntry],
    roster_shift: Optional[ShiftTemplate],
    assignment: Optional[EmployeeShiftAssignment],
    on_date: date,
) -> EffectiveShift:
    """Pure precedence function shared by single-day and range lookups."""
    if roster is not None and roster.status == RosterStatus.PUBLISHED:
        if roster.is_week_off:
            return EffectiveShift(None, True, "roster")
        if roster.shift_template_id is not None and roster_shift is not None:
            return EffectiveShift(roster_shift, False, "roster")
    if assignment is not None and assignment.shift_template is not None:
        tpl = assignment.shift_template
        offs = tpl.weekly_offs or []
        return EffectiveShift(tpl, on_date.weekday() in offs, "assignment")
    return EffectiveShift(None, False, "none")


async def effective_shifts_for_range(
    db, user_ids: list[int], start: date, end: date
) -> dict[tuple[int, date], EffectiveShift]:
    """Batched resolution: two queries (roster + assignments) regardless of
    window size. Returns an entry for every (user_id, date) inclusive."""
    out: dict[tuple[int, date], EffectiveShift] = {}
    if not user_ids or end < start:
        return out
    uids = list(set(user_ids))

    roster_rows = (await db.execute(
        select(RosterEntry)
        .options(selectinload(RosterEntry.shift_template))
        .where(
            RosterEntry.employee_id.in_(uids),
            RosterEntry.work_date >= start,
            RosterEntry.work_date <= end,
            RosterEntry.status == RosterStatus.PUBLISHED,
        )
    )).scalars().all()
    roster_by_key = {(r.employee_id, r.work_date): r for r in roster_rows}

    asg_rows = (await db.execute(
        select(EmployeeShiftAssignment)
        .options(selectinload(EmployeeShiftAssignment.shift_template))
        .where(
            EmployeeShiftAssignment.employee_id.in_(uids),
            EmployeeShiftAssignment.effective_from <= end,
            or_(
                EmployeeShiftAssignment.effective_to.is_(None),
                EmployeeShiftAssignment.effective_to >= start,
            ),
        )
        .order_by(EmployeeShiftAssignment.effective_from.desc())
    )).scalars().all()
    # Already sorted latest effective_from first per user.
    asg_by_user: dict[int, list[EmployeeShiftAssignment]] = {}
    for a in asg_rows:
        asg_by_user.setdefault(a.employee_id, []).append(a)

    days = (end - start).days + 1
    for uid in uids:
        user_asgs = asg_by_user.get(uid, [])
        for i in range(days):
            d = start + timedelta(days=i)
            asg = next(
                (
                    a for a in user_asgs
                    if a.effective_from <= d
                    and (a.effective_to is None or a.effective_to >= d)
                ),
                None,
            )
            r = roster_by_key.get((uid, d))
            out[(uid, d)] = _resolve(
                r, r.shift_template if r is not None else None, asg, d
            )
    return out


async def effective_shift_on(db, user_id: int, on_date: date) -> EffectiveShift:
    res = await effective_shifts_for_range(db, [user_id], on_date, on_date)
    return res[(user_id, on_date)]
