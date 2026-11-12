"""DB-backed tests for services/effective_shift (roster > assignment)."""
import uuid
from datetime import date, time

import pytest
from sqlalchemy import delete

from app.db.session import SessionLocal, engine
from app.models.roster import RosterEntry, RosterStatus
from app.models.shift import EmployeeShiftAssignment, ShiftTemplate
from app.models.user import User
from app.services.effective_shift import (
    effective_shift_on,
    effective_shifts_for_range,
)

MON = date(2031, 3, 3)  # a Monday
assert MON.weekday() == 0


@pytest.fixture
async def env():
    async with SessionLocal() as db:
        tag = uuid.uuid4().hex[:8]
        user = User(email=f"eff_{tag}@test.com", full_name="Eff", hashed_password="x")
        db.add(user)
        await db.flush()
        asg_tpl = ShiftTemplate(
            name=f"EffA_{tag}", start_time=time(9, 0), end_time=time(18, 0),
            weekly_offs=[6],
        )
        ros_tpl = ShiftTemplate(
            name=f"EffR_{tag}", start_time=time(22, 0), end_time=time(6, 0),
            is_overnight=True, weekly_offs=[],
        )
        db.add_all([asg_tpl, ros_tpl])
        await db.flush()
        await db.commit()
        # Plain ids: ORM instances expire on commit (async can't lazy-load).
        uid, asg_id, ros_id = user.id, asg_tpl.id, ros_tpl.id
        ctx = {"db": db, "uid": uid, "asg_id": asg_id, "ros_id": ros_id}
        try:
            yield ctx
        finally:
            await db.rollback()
            await db.execute(delete(RosterEntry).where(RosterEntry.employee_id == uid))
            await db.execute(delete(EmployeeShiftAssignment).where(
                EmployeeShiftAssignment.employee_id == uid))
            await db.execute(delete(ShiftTemplate).where(
                ShiftTemplate.id.in_([asg_id, ros_id])))
            await db.execute(delete(User).where(User.id == uid))
            await db.commit()
    await engine.dispose()


async def _assign(e, frm=date(2031, 1, 1), to=None):
    e["db"].add(EmployeeShiftAssignment(
        employee_id=e["uid"], shift_template_id=e["asg_id"],
        effective_from=frm, effective_to=to,
    ))
    await e["db"].commit()


async def _roster(e, d, status=RosterStatus.PUBLISHED, shift=None, off=False):
    e["db"].add(RosterEntry(
        employee_id=e["uid"], work_date=d, status=status,
        shift_template_id=shift if shift else None, is_week_off=off,
    ))
    await e["db"].commit()


async def test_published_roster_overrides_assignment(env):
    await _assign(env)
    await _roster(env, MON, shift=env["ros_id"])
    r = await effective_shift_on(env["db"], env["uid"], MON)
    assert r.source == "roster" and r.shift.id == env["ros_id"] and not r.is_week_off


async def test_roster_week_off(env):
    await _assign(env)
    await _roster(env, MON, off=True)
    r = await effective_shift_on(env["db"], env["uid"], MON)
    assert r.shift is None and r.is_week_off and r.source == "roster"


async def test_blank_cell_falls_back(env):
    await _assign(env)
    await _roster(env, MON)
    r = await effective_shift_on(env["db"], env["uid"], MON)
    assert r.source == "assignment" and r.shift.id == env["asg_id"]


async def test_draft_ignored(env):
    await _assign(env)
    await _roster(env, MON, status=RosterStatus.DRAFT, shift=env["ros_id"])
    await _roster(env, date(2031, 3, 4), status=RosterStatus.DRAFT, off=True)
    r = await effective_shift_on(env["db"], env["uid"], MON)
    assert r.source == "assignment" and r.shift.id == env["asg_id"]
    r2 = await effective_shift_on(env["db"], env["uid"], date(2031, 3, 4))
    assert r2.source == "assignment" and not r2.is_week_off


async def test_assignment_weekly_off(env):
    await _assign(env)
    sun = date(2031, 3, 9)
    assert (await effective_shift_on(env["db"], env["uid"], sun)).is_week_off
    assert not (await effective_shift_on(env["db"], env["uid"], MON)).is_week_off


async def test_no_data(env):
    r = await effective_shift_on(env["db"], env["uid"], MON)
    assert (r.shift, r.is_week_off, r.source) == (None, False, "none")


async def test_assignment_window_respected(env):
    await _assign(env, frm=date(2031, 3, 5), to=date(2031, 3, 6))
    uid = env["uid"]
    assert (await effective_shift_on(env["db"], uid, date(2031, 3, 4))).source == "none"
    assert (await effective_shift_on(env["db"], uid, date(2031, 3, 6))).source == "assignment"
    assert (await effective_shift_on(env["db"], uid, date(2031, 3, 7))).source == "none"


async def test_range_agrees_with_single_day(env):
    await _assign(env, frm=date(2031, 3, 4))
    await _roster(env, date(2031, 3, 3), shift=env["ros_id"])
    await _roster(env, date(2031, 3, 5), off=True)
    await _roster(env, date(2031, 3, 6))
    await _roster(env, date(2031, 3, 7), status=RosterStatus.DRAFT, off=True)
    uid, db = env["uid"], env["db"]
    start, end = MON, date(2031, 3, 9)
    rng = await effective_shifts_for_range(db, [uid], start, end)
    assert len(rng) == 7
    for i in range(7):
        d = date(2031, 3, 3 + i)
        one = await effective_shift_on(db, uid, d)
        got = rng[(uid, d)]
        assert (got.shift.id if got.shift else None, got.is_week_off, got.source) == (
            one.shift.id if one.shift else None, one.is_week_off, one.source
        ), d
