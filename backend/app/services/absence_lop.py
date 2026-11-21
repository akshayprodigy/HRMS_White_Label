"""Unexplained-absence LOP (payroll).

A scheduled working day on which an employee has no punch, no holiday,
no week-off and no approved leave counts as LOP. Everything is loaded in
batched queries (attendance, leaves, holidays, resignations, plus the two
inside effective_shifts_for_range) -- never per employee or per day.

Unpaid leave is counted by the payroll loop itself. A full-day approved
leave (any type) excuses the day here, so there is no overlap. A half-day
leave with no punch counts 0.5 here (the unexplained other half); if that
leave is UNPAID the payroll loop adds its own 0.5, so the day totals 1.0 --
intended semantics.

Id spaces: Attendance.user_id / LeaveRequest.employee_id are User ids;
Resignation.employee_id is the Employee PK.
"""
import logging
from datetime import date, timedelta
from typing import Any, Container, Iterable, Mapping

from sqlalchemy import and_, or_, select

from app.models.attendance import Attendance
from app.models.employee import Employee
from app.models.exit_management import Resignation, ResignationStatus
from app.services.holidays import holidays_for
from app.services.work_location import approved_portions
from app.models.leave import LeaveRequest, LeaveStatus, LeaveType
from app.services.effective_shift import effective_shifts_for_range

logger = logging.getLogger(__name__)

_EFFECTIVE_RESIGNATION = (
    ResignationStatus.ACCEPTED,
    ResignationStatus.NOTICE_PERIOD,
    ResignationStatus.EXIT_INTERVIEW,
    ResignationStatus.CLEARANCE,
    ResignationStatus.RELEASED,
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


async def leave_lop_days(
    db, user_id: int, month_start: date, month_end: date,
) -> float:
    """LOP days from approved leave in [month_start, month_end]: unpaid leave
    types plus emergency leaves converted to LOP (proof overdue). Each leave
    row counts once; the absence LOP excuses every approved-leave day, so it
    never double counts these."""
    rows = (await db.execute(
        select(LeaveRequest).join(LeaveType).where(and_(
            LeaveRequest.employee_id == user_id,
            LeaveRequest.status == LeaveStatus.APPROVED,
            or_(LeaveType.unpaid_allowed.is_(True),
                LeaveRequest.converted_to_lop_at.is_not(None)),
            LeaveRequest.start_date <= month_end,
            LeaveRequest.end_date >= month_start,
        )))).scalars().all()
    return sum(
        unpaid_leave_lop_days(lv.start_date, lv.end_date, bool(lv.is_half_day),
                              month_start, month_end) for lv in rows)


def parse_weekdays(raw: str | None) -> set[int]:
    """'6' / '5,6' -> {5, 6}. Blank or unparseable tokens are ignored."""
    out: set[int] = set()
    for tok in (raw or "").split(","):
        tok = tok.strip()
        if tok.isdigit() and 0 <= int(tok) <= 6:
            out.add(int(tok))
    return out


def default_offs_from_rules(rules: dict) -> set[int]:
    """Parsed default weekly offs; empty/garbage falls back to {6} (Sunday)
    so a bad setting can never turn every weekday into an LOP day."""
    offs = parse_weekdays(rules.get("attendance.default_weekly_offs"))
    if not offs:
        logger.warning(
            "attendance.default_weekly_offs is empty/invalid; using Sunday"
        )
        return {6}
    return offs


def absence_lop_applies(rules: dict, run_type: str) -> bool:
    """Whether generate_draft should add unexplained-absence LOP."""
    on = str(rules.get("attendance.absence_lop_enabled", "0")).strip().lower() in (
        "1", "true", "yes", "on",
    )
    return on and run_type != "off_cycle"


def is_non_working_day(
    eff, d: date, user_holidays: Container[date], default_offs: set[int],
    *, roster_beats_holiday: bool = False,
) -> bool:
    """Shared skip rules: holiday, week-off, no-shift default off day, or an
    assigned template with no weekly offs on a default off day. Roster
    shifts are explicit working days for the template rule. With
    `roster_beats_holiday` a published roster working shift stays a working
    day even on a holiday (used by the live board)."""
    if d in user_holidays:
        if not (
            roster_beats_holiday and eff is not None
            and eff.source == "roster" and not eff.is_week_off
        ):
            return True
    if eff is not None and eff.is_week_off:
        return True
    if (eff is None or eff.source == "none") and d.weekday() in default_offs:
        return True
    if (
        eff is not None
        and eff.source == "assignment"
        and not (eff.shift.weekly_offs if eff.shift is not None else None)
        and d.weekday() in default_offs
    ):
        return True
    return False


def count_absent_days(
    *,
    first: date,
    last: date,
    user_id: int,
    shifts: dict,
    default_offs: set[int],
    punched: set[tuple[int, date]],
    full_leave: set[tuple[int, date]],
    half_leave: set[tuple[int, date]],
    holidays: Mapping[date, Any] | Container[date],
    remote: Mapping[date, str] | None = None,
) -> float:
    """Pure per-employee loop over [first, last]. `shifts` maps
    (user_id, date) -> EffectiveShift (missing == no shift). `holidays` is
    this user's holiday dates (a dict keyed by date, or a set). `remote` is
    this user's approved on-duty/WFH portions (date -> full|first_half|
    second_half): a full day excuses a no-punch day, a half portion excuses
    half of it (a half portion plus half leave covers the whole day)."""
    remote = remote or {}
    total = 0.0
    d = first
    while d <= last:
        key = (user_id, d)
        eff = shifts.get(key)
        if is_non_working_day(eff, d, holidays, default_offs):
            pass
        elif key in punched or key in full_leave:
            pass
        else:
            portion = remote.get(d)
            if portion == "full":
                pass
            elif portion is not None:  # half-day remote
                if key not in half_leave:
                    total += 0.5
            elif key in half_leave:
                total += 0.5
            else:
                total += 1.0
        d += timedelta(days=1)
    return total


async def load_leave_days(
    db, user_ids, start: date, last_day: date,
) -> tuple[set[tuple[int, date]], set[tuple[int, date]]]:
    """(full_leave, half_leave) sets of (user_id, date) from APPROVED leave in
    [start, last_day]; one query."""
    leave_rows = (await db.execute(
        select(LeaveRequest).where(
            LeaveRequest.employee_id.in_(list(user_ids)),
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
    return full_leave, half_leave


async def last_working_days(db, emps: Iterable[Employee]) -> dict[int, date]:
    """Employee.id -> earliest effective-resignation last working day."""
    res_rows = (await db.execute(
        select(Resignation.employee_id, Resignation.last_working_day).where(
            Resignation.employee_id.in_([e.id for e in emps]),
            Resignation.status.in_(_EFFECTIVE_RESIGNATION),
        )
    )).all()
    lwd_by_emp: dict[int, date] = {}
    for eid, lwd in res_rows:
        if eid not in lwd_by_emp or lwd < lwd_by_emp[eid]:
            lwd_by_emp[eid] = lwd
    return lwd_by_emp


async def absence_days_for_period(
    db, employees: Iterable[Employee], start: date, end: date, today: date,
    default_weekly_offs: set[int],
) -> dict[int, float]:
    """Absent (LOP) days per user_id in [start, end], never reaching today."""
    emps = list(employees)
    last_day = min(end, today - timedelta(days=1))
    if not emps or last_day < start:
        return {e.user_id: 0.0 for e in emps}

    user_ids = [e.user_id for e in emps]
    shifts = await effective_shifts_for_range(db, user_ids, start, last_day)

    # Attendance.work_date is NOT NULL, so no captured_at fallback needed.
    att_rows = (await db.execute(
        select(Attendance.user_id, Attendance.work_date).where(
            Attendance.user_id.in_(user_ids),
            Attendance.work_date >= start,
            Attendance.work_date <= last_day,
        )
    )).all()
    punched: set[tuple[int, date]] = {(u, d) for u, d in att_rows}

    full_leave, half_leave = await load_leave_days(
        db, user_ids, start, last_day)

    holidays = await holidays_for(db, user_ids, start, last_day)
    remote = await approved_portions(db, user_ids, start, last_day)

    lwd_by_emp = await last_working_days(db, emps)

    out: dict[int, float] = {}
    for e in emps:
        stop = last_day
        lwd = lwd_by_emp.get(e.id)
        if lwd is not None:
            stop = min(stop, lwd)
        out[e.user_id] = count_absent_days(
            first=max(start, e.date_of_joining), last=stop,
            user_id=e.user_id,
            shifts=shifts, default_offs=default_weekly_offs,
            punched=punched, full_leave=full_leave,
            half_leave=half_leave,
            holidays=holidays.get(e.user_id, {}),
            remote=remote.get(e.user_id, {}),
        )
    return out
