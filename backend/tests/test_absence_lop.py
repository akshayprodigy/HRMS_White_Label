"""Tests for services/absence_lop (unexplained-absence LOP) + half-day helper."""
import uuid
from datetime import date, datetime, time, timedelta, timezone

import pytest
from sqlalchemy import delete

from app.services.effective_shift import EffectiveShift
from app.db.session import SessionLocal
from app.models.attendance import Attendance
from app.models.employee import Employee
from app.models.exit_management import Resignation
from app.models.hr import HolidayCalendar
from app.models.leave import LeaveRequest, LeaveStatus, LeaveType
from app.models.roster import RosterEntry, RosterStatus
from app.models.shift import EmployeeShiftAssignment, ShiftTemplate
from app.models.user import User
from app.services.absence_lop import (
    absence_days_for_period,
    absence_lop_applies,
    count_absent_days,
    default_offs_from_rules,
    unpaid_leave_lop_days,
)

# March 2031: Mar 3 = Monday.
START = date(2031, 3, 3)   # Mon
END = date(2031, 3, 7)     # Fri
FAR_TODAY = date(2031, 4, 1)


# ---------- pure helper ----------

def test_half_day_single_day():
    d = date(2031, 3, 10)
    assert unpaid_leave_lop_days(d, d, True, date(2031, 3, 1), date(2031, 3, 31)) == 0.5


def test_half_day_multi_day():
    assert unpaid_leave_lop_days(
        date(2031, 3, 10), date(2031, 3, 12), True,
        date(2031, 3, 1), date(2031, 3, 31)) == 1.5


def test_full_day_clipped_to_month():
    # Feb 27 .. Mar 3 -> only Mar 1..3 in March.
    assert unpaid_leave_lop_days(
        date(2031, 2, 27), date(2031, 3, 3), False,
        date(2031, 3, 1), date(2031, 3, 31)) == 3.0
    # Mar 30 .. Apr 2 -> Mar 30..31
    assert unpaid_leave_lop_days(
        date(2031, 3, 30), date(2031, 4, 2), False,
        date(2031, 3, 1), date(2031, 3, 31)) == 2.0


def test_no_overlap_is_zero():
    assert unpaid_leave_lop_days(
        date(2031, 5, 1), date(2031, 5, 2), False,
        date(2031, 3, 1), date(2031, 3, 31)) == 0.0


# ---------- pure per-employee loop ----------

def _count(first, last, **kw):
    base = dict(user_id=1, shifts={}, default_offs={6},
                punched=set(), full_leave=set(), half_leave=set(),
                holidays={})
    base.update(kw)
    return count_absent_days(first=first, last=last, **base)


def test_pure_week_off_with_punch_and_default_off():
    sun = date(2031, 3, 9)
    # no shift entry -> default off Sunday excused
    assert _count(sun, sun) == 0.0
    # roster week-off excuses even with no punch
    off = {(1, START): EffectiveShift(None, True, "roster")}
    assert _count(START, START, shifts=off) == 0.0
    # source "none" on a Monday is NOT a default off
    none = {(1, START): EffectiveShift(None, False, "none")}
    assert _count(START, START, shifts=none) == 1.0
    # punch on a working day
    assert _count(START, START, punched={(1, START)}) == 0.0


def test_pure_half_and_full_leave_overlap_and_holiday():
    d = START
    k = (1, d)
    assert _count(d, d, half_leave={k}) == 0.5
    assert _count(d, d, half_leave={k}, full_leave={k}) == 0.0
    assert _count(d, d, half_leave={k}, punched={k}) == 0.0
    assert _count(d, d, holidays={d: 1}) == 0.0
    assert _count(d, d, holidays={d: 1}) == 0.0
    assert _count(d, d, holidays={d + timedelta(days=1): 1}) == 1.0


def test_absence_lop_applies():
    k = "attendance.absence_lop_enabled"
    assert absence_lop_applies({k: "0"}, "monthly") is False
    assert absence_lop_applies({}, "monthly") is False
    assert absence_lop_applies({k: "1"}, "monthly") is True
    assert absence_lop_applies({k: "TRUE"}, "monthly") is True
    assert absence_lop_applies({k: "1"}, "off_cycle") is False


def test_default_offs_fallback():
    assert default_offs_from_rules({"attendance.default_weekly_offs": "5, 6"}) == {5, 6}
    assert default_offs_from_rules({"attendance.default_weekly_offs": ""}) == {6}
    assert default_offs_from_rules({"attendance.default_weekly_offs": "x,9"}) == {6}


async def test_set_time_rules_rejects_bad_weekly_offs():
    from app.services.time_rules import set_time_rules
    async with SessionLocal() as db:
        for bad in ("", "7", "a", "5,,6", "-1"):
            with pytest.raises(ValueError):
                await set_time_rules(db, {"attendance.default_weekly_offs": bad})


# ---------- DB-backed ----------

@pytest.fixture
async def env():
    user_ids: list[int] = []
    emp_ids: list[int] = []
    tpl_ids: list[int] = []
    hol_ids: list[int] = []
    lt_ids: list[int] = []
    async with SessionLocal() as db:
        try:
            tag = uuid.uuid4().hex[:8]

            async def mk(i: int, joined=date(2030, 1, 1), location="HQ"):
                u = User(email=f"abs{i}_{tag}@test.com", full_name="Abs",
                         hashed_password="x")
                db.add(u)
                await db.flush()
                user_ids.append(u.id)
                e = Employee(
                    user_id=u.id, employee_id=f"AB{tag[:5]}{i}",
                    department="T", designation="T",
                    date_of_joining=joined, location=location,
                )
                db.add(e)
                await db.flush()
                emp_ids.append(e.id)
                return u.id, e.id

            lt = LeaveType(name=f"AbsLT_{tag}", code=f"A{tag[:6]}")
            db.add(lt)
            await db.flush()
            lt_ids.append(lt.id)
            await db.commit()
            yield {
                "db": db, "tag": tag, "mk": mk, "lt_id": lt.id,
                "tpl_ids": tpl_ids, "hol_ids": hol_ids,
                "user_ids": user_ids, "emp_ids": emp_ids,
            }
        finally:
            await db.rollback()
            if user_ids:
                await db.execute(delete(Attendance).where(Attendance.user_id.in_(user_ids)))
                await db.execute(delete(LeaveRequest).where(LeaveRequest.employee_id.in_(user_ids)))
                await db.execute(delete(RosterEntry).where(RosterEntry.employee_id.in_(user_ids)))
                await db.execute(delete(EmployeeShiftAssignment).where(
                    EmployeeShiftAssignment.employee_id.in_(user_ids)))
            if emp_ids:
                await db.execute(delete(Resignation).where(Resignation.employee_id.in_(emp_ids)))
                await db.execute(delete(Employee).where(Employee.id.in_(emp_ids)))
            if tpl_ids:
                await db.execute(delete(ShiftTemplate).where(ShiftTemplate.id.in_(tpl_ids)))
            if hol_ids:
                await db.execute(delete(HolidayCalendar).where(HolidayCalendar.id.in_(hol_ids)))
            if lt_ids:
                await db.execute(delete(LeaveType).where(LeaveType.id.in_(lt_ids)))
            if user_ids:
                await db.execute(delete(User).where(User.id.in_(user_ids)))
            await db.commit()


async def _emp(db, emp_id):
    return await db.get(Employee, emp_id)


async def _run(env, emp_id, start=START, end=END, today=FAR_TODAY):
    db = env["db"]
    emp = await db.get(Employee, emp_id)
    return await absence_days_for_period(db, [emp], start, end, today, {6})


def _punch(uid, d):
    return Attendance(
        user_id=uid, mode="web", work_date=d,
        captured_at=datetime(d.year, d.month, d.day, 9, 0, tzinfo=timezone.utc),
    )


async def test_no_punch_counted_punch_not(env):
    db = env["db"]
    uid, eid = await env["mk"](1)
    db.add(_punch(uid, date(2031, 3, 4)))
    await db.commit()
    res = await _run(env, eid)
    # Mon-Fri, 1 punched; default offs = Sunday only -> 4 absent
    assert res[uid] == 4.0


async def test_holiday_excluded(env):
    db = env["db"]
    uid, eid = await env["mk"](1)
    h = HolidayCalendar(name=f"H{env['tag']}", date=date(2031, 3, 5),
                        location="All", is_optional=False)
    opt = HolidayCalendar(name=f"O{env['tag']}", date=date(2031, 3, 6),
                          location="All", is_optional=True)
    other = HolidayCalendar(name=f"X{env['tag']}", date=date(2031, 3, 7),
                            location="Nowhere", is_optional=False)
    db.add_all([h, opt, other])
    await db.flush()
    env["hol_ids"].extend([h.id, opt.id, other.id])
    await db.commit()
    res = await _run(env, eid)
    # 5 days - 1 holiday = 4 (optional + other-location don't excuse)
    assert res[uid] == 4.0


async def test_roster_week_off_excluded(env):
    db = env["db"]
    uid, eid = await env["mk"](1)
    db.add(RosterEntry(employee_id=uid, work_date=date(2031, 3, 5),
                       is_week_off=True, status=RosterStatus.PUBLISHED))
    await db.commit()
    res = await _run(env, eid)
    assert res[uid] == 4.0


async def test_shift_weekly_off_excluded(env):
    db = env["db"]
    uid, eid = await env["mk"](1)
    tpl = ShiftTemplate(name=f"AbsS_{env['tag']}", start_time=time(9, 0),
                        end_time=time(18, 0), weekly_offs=[0, 1])  # Mon, Tue
    db.add(tpl)
    await db.flush()
    env["tpl_ids"].append(tpl.id)
    db.add(EmployeeShiftAssignment(
        employee_id=uid, shift_template_id=tpl.id,
        effective_from=date(2031, 1, 1)))
    await db.commit()
    res = await _run(env, eid)
    assert res[uid] == 3.0  # Wed-Fri


async def test_default_weekly_off_excluded(env):
    db = env["db"]
    uid, eid = await env["mk"](1)
    sat, sun = date(2031, 3, 8), date(2031, 3, 9)
    res = await _run(env, eid, start=date(2031, 3, 3), end=sun)
    assert res[uid] == 6.0  # Mon-Sat; Sunday (6) is the default off


async def test_full_day_leave_excluded(env):
    db = env["db"]
    uid, eid = await env["mk"](1)
    db.add(LeaveRequest(
        employee_id=uid, leave_type_id=env["lt_id"],
        start_date=date(2031, 3, 4), end_date=date(2031, 3, 5),
        reason="r", status=LeaveStatus.APPROVED, created_by_user_id=uid))
    db.add(LeaveRequest(  # not approved: must not excuse
        employee_id=uid, leave_type_id=env["lt_id"],
        start_date=date(2031, 3, 7), end_date=date(2031, 3, 7),
        reason="r", status=LeaveStatus.SUBMITTED, created_by_user_id=uid))
    await db.commit()
    res = await _run(env, eid)
    assert res[uid] == 3.0


async def test_half_day_leave_no_punch(env):
    db = env["db"]
    uid, eid = await env["mk"](1)
    db.add(LeaveRequest(
        employee_id=uid, leave_type_id=env["lt_id"],
        start_date=date(2031, 3, 4), end_date=date(2031, 3, 4), is_half_day=True,
        reason="r", status=LeaveStatus.APPROVED, created_by_user_id=uid))
    await db.commit()
    res = await _run(env, eid, start=date(2031, 3, 4), end=date(2031, 3, 4))
    assert res[uid] == 0.5


async def test_unpaid_half_day_leave_absence_side_is_half(env):
    # The payroll loop adds 0.5 for the unpaid half; absence side adds the
    # other unexplained 0.5 (total 1.0 for the day, intended).
    db = env["db"]
    uid, eid = await env["mk"](1)
    lt = await db.get(LeaveType, env["lt_id"])
    lt.unpaid_allowed = True
    db.add(LeaveRequest(
        employee_id=uid, leave_type_id=env["lt_id"],
        start_date=date(2031, 3, 4), end_date=date(2031, 3, 4), is_half_day=True,
        reason="r", status=LeaveStatus.APPROVED, created_by_user_id=uid))
    await db.commit()
    res = await _run(env, eid, start=date(2031, 3, 4), end=date(2031, 3, 4))
    assert res[uid] == 0.5


async def test_half_day_leave_with_punch(env):
    db = env["db"]
    uid, eid = await env["mk"](1)
    db.add(LeaveRequest(
        employee_id=uid, leave_type_id=env["lt_id"],
        start_date=date(2031, 3, 4), end_date=date(2031, 3, 4), is_half_day=True,
        reason="r", status=LeaveStatus.APPROVED, created_by_user_id=uid))
    db.add(_punch(uid, date(2031, 3, 4)))
    await db.commit()
    res = await _run(env, eid, start=date(2031, 3, 4), end=date(2031, 3, 4))
    assert res.get(uid, 0.0) == 0.0


async def test_before_joining_excluded(env):
    uid, eid = await env["mk"](1, joined=date(2031, 3, 6))
    res = await _run(env, eid)
    assert res[uid] == 2.0  # Thu, Fri


async def test_today_and_future_excluded(env):
    uid, eid = await env["mk"](1)
    res = await _run(env, eid, today=date(2031, 3, 5))
    assert res[uid] == 2.0  # Mon, Tue only


async def test_after_last_working_day_excluded(env):
    db = env["db"]
    uid, eid = await env["mk"](1)
    uid2, eid2 = await env["mk"](2)
    uid3, eid3 = await env["mk"](3)
    db.add(Resignation(
        employee_id=eid, reason="personal", status="accepted",
        resignation_date=date(2031, 2, 1), last_working_day=date(2031, 3, 4),
        notice_period_days=30))
    db.add(Resignation(  # withdrawn: ignored
        employee_id=eid2, reason="personal", status="withdrawn",
        resignation_date=date(2031, 2, 1), last_working_day=date(2031, 3, 4),
        notice_period_days=30))
    db.add(Resignation(  # submitted: ignored
        employee_id=eid3, reason="personal", status="submitted",
        resignation_date=date(2031, 2, 1), last_working_day=date(2031, 3, 4),
        notice_period_days=30))
    await db.commit()
    emps = [await db.get(Employee, i) for i in (eid, eid2, eid3)]
    res = await absence_days_for_period(db, emps, START, END, FAR_TODAY, {6})
    assert res[uid] == 2.0   # Mon, Tue
    assert res[uid2] == 5.0
    assert res[uid3] == 5.0


# ---------- weekly-off fallback (pure) ----------

class _Tpl:
    def __init__(self, offs):
        self.weekly_offs = offs


def test_pure_assignment_with_empty_weekly_offs_uses_default():
    sun = date(2031, 3, 9)
    for offs in ([], None):
        eff = {(1, sun): EffectiveShift(_Tpl(offs), False, "assignment")}
        assert _count(sun, sun, shifts=eff) == 0.0
    # Non-default-off weekday still working
    eff = {(1, START): EffectiveShift(_Tpl([]), False, "assignment")}
    assert _count(START, START, shifts=eff) == 1.0
    # Template WITH offs does not fall back (Sunday not in its offs -> working)
    eff = {(1, sun): EffectiveShift(_Tpl([5]), False, "assignment")}
    assert _count(sun, sun, shifts=eff) == 1.0


def test_pure_roster_shift_on_default_off_is_working_day():
    sun = date(2031, 3, 9)
    eff = {(1, sun): EffectiveShift(_Tpl([]), False, "roster")}
    assert _count(sun, sun, shifts=eff) == 1.0
