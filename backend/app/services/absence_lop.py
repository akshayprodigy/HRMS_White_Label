"""Unexplained-absence LOP (payroll).

A scheduled working day on which an employee has no punch, no holiday,
no week-off and no approved leave counts as LOP. Everything is loaded in
batched queries (attendance, leaves, holidays, resignations, plus the two
inside effective_shifts_for_range) -- never per employee or per day.

Unpaid leave is counted by the payroll loop itself; because ANY approved
leave excuses the day here, nothing is double counted.

Id spaces: Attendance.user_id / LeaveRequest.employee_id are User ids;
Resignation.employee_id is the Employee PK.
"""
from datetime import date, datetime, timedelta
from typing import Iterable

from sqlalchemy import and_, or_, select

from app.models.attendance import Attendance
from app.models.employee import Employee
from app.models.exit_management import Resignation, ResignationStatus
from app.models.hr import HolidayCalendar
from app.models.leave import LeaveRequest, LeaveStatus
from app.services.effective_shift import effective_shifts_for_range
from app.services.time_rules import get_time_rules

_IGNORED_RESIGNATION = (
    ResignationStatus.WITHDRAWN,
    ResignationStatus.REJECTED,
    ResignationStatus.SUBMITTED,
)


def unpaid_leave_lop_days(
    start_date: date, end_date: date, is_half_day: bool,
    month_start: date, month_end: date,
) -> float:
    """LOP days an unpaid leave contributes inside [month_start, month_end]."""
    overlap_start = max(start_date, month_start)
    overlap_end = min(end_date, month_end)
    overlap = (overlap_end - overlap_start).days + 1
    if overlap <= 0:
        return 0.0
    return overlap * (0.5 if is_half_day else 1.0)


def parse_weekdays(raw: str | None) -> set[int]:
    """'6' / '5,6' -> {5, 6}. Blank or unparseable tokens are ignored."""
    out: set[int] = set()
    for tok in (raw or "").split(","):
        tok = tok.strip()
        if tok.isdigit() and 0 <= int(tok) <= 6:
            out.add(int(tok))
    return out


def _as_date(v) -> date:
    return v.date() if isinstance(v, datetime) else v


async def absence_days_for_period(
    db, employees: Iterable[Employee], start: date, end: date, today: date
) -> dict[int, float]:
    """Absent (LOP) days per user_id in [start, end], never reaching today."""
    emps = list(employees)
    last_day = min(end, today - timedelta(days=1))
    if not emps or last_day < start:
        return {e.user_id: 0.0 for e in emps}

    user_ids = [e.user_id for e in emps]
    rules = await get_time_rules(db)
    default_offs = parse_weekdays(rules.get("attendance.default_weekly_offs"))

    shifts = await effective_shifts_for_range(db, user_ids, start, last_day)

    # Attendance: set of (user_id, day). work_date is the logical date;
    # fall back to captured_at's date if it is ever NULL.
    att_rows = (await db.execute(
        select(Attendance.user_id, Attendance.work_date, Attendance.captured_at)
        .where(
            Attendance.user_id.in_(user_ids),
            or_(
                and_(Attendance.work_date >= start,
                     Attendance.work_date <= last_day),
                and_(Attendance.work_date.is_(None),
                     Attendance.captured_at >= datetime.combine(start, datetime.min.time()),
                     Attendance.captured_at < datetime.combine(
                         last_day + timedelta(days=1), datetime.min.time())),
            ),
        )
    )).all()
    punched: set[tuple[int, date]] = set()
    for uid, wd, cap in att_rows:
        d = wd if wd is not None else _as_date(cap)
        punched.add((uid, d))

    leave_rows = (await db.execute(
        select(LeaveRequest).where(
            LeaveRequest.employee_id.in_(user_ids),
            LeaveRequest.status == LeaveStatus.APPROVED,
            LeaveRequest.start_date <= last_day,
            LeaveRequest.end_date >= start,
        )
    )).scalars().all()
    full_leave: set[tuple[int, date]] = set()
    half_leave: set[tuple[int, date]] = set()
    for lv in leave_rows:
        d = max(lv.start_date, start)
        stop = min(lv.end_date, last_day)
        target = half_leave if lv.is_half_day else full_leave
        while d <= stop:
            target.add((lv.employee_id, d))
            d += timedelta(days=1)

    hol_rows = (await db.execute(
        select(HolidayCalendar.date, HolidayCalendar.location).where(
            HolidayCalendar.date >= start,
            HolidayCalendar.date <= last_day,
            HolidayCalendar.is_optional.is_(False),
        )
    )).all()
    holidays: set[tuple[str, date]] = {(loc, d) for d, loc in hol_rows}

    res_rows = (await db.execute(
        select(Resignation.employee_id, Resignation.last_working_day).where(
            Resignation.employee_id.in_([e.id for e in emps]),
            Resignation.status.notin_(_IGNORED_RESIGNATION),
        )
    )).all()
    lwd_by_emp = {eid: lwd for eid, lwd in res_rows}

    out: dict[int, float] = {}
    for e in emps:
        first = max(start, e.date_of_joining)
        stop = last_day
        lwd = lwd_by_emp.get(e.id)
        if lwd is not None:
            stop = min(stop, lwd)
        loc = e.location or "HQ"
        total = 0.0
        d = first
        while d <= stop:
            if ("All", d) in holidays or (loc, d) in holidays:
                d += timedelta(days=1)
                continue
            eff = shifts.get((e.user_id, d))
            if eff is not None and eff.is_week_off:
                pass
            elif (eff is None or eff.source == "none") and d.weekday() in default_offs:
                pass
            elif (e.user_id, d) in punched or (e.user_id, d) in full_leave:
                pass
            elif (e.user_id, d) in half_leave:
                total += 0.5
            else:
                total += 1.0
            d += timedelta(days=1)
        out[e.user_id] = total
    return out
