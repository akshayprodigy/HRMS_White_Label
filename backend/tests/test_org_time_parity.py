"""Shift windows + punch work-date use the org timezone (Phase 6A, Task 2).

org.timezone=UTC must reproduce the pre-6A behaviour exactly."""
import uuid
from datetime import date, datetime, time, timezone

import pytest
from sqlalchemy import delete, select

from _cleanup import purge_gap_notifications, purge_shift_templates
from app.db.session import SessionLocal
from app.models.attendance import Attendance
from app.models.coverage_gap import CoverageGap
from app.models.employee import Employee, EmployeeStatus
from app.models.no_show import NoShowAlert
from app.models.notification import Notification
from app.models.roster import RosterEntry, RosterEntryHistory, RosterStatus
from app.models.shift import ShiftTemplate
from app.models.system import SystemSetting
from app.models.user import User
from app.services import live_ops
from app.services.punch import _attribute_punch
from app.services.time_rules import set_time_rules

UTC = timezone.utc
TZ_KEY = "org.timezone"
NS_KEY = "schedule.no_show_minutes"


async def _snapshot(keys):
    async with SessionLocal() as db:
        out = {}
        for k in keys:
            r = await db.get(SystemSetting, k)
            out[k] = (r.value, r.description) if r else None
        return out


async def _restore(snap):
    async with SessionLocal() as db:
        for k, v in snap.items():
            await db.execute(delete(SystemSetting).where(SystemSetting.key == k))
            if v is not None:
                db.add(SystemSetting(key=k, value=v[0], description=v[1]))
        await db.commit()


@pytest.fixture
async def world():
    snap = await _snapshot([TZ_KEY, NS_KEY])
    sfx = uuid.uuid4().hex[:8]
    tpl_names = [f"PD{sfx}", f"PN{sfx}"]

    async def rules(tz, no_show=None):
        upd = {TZ_KEY: tz}
        if no_show is not None:
            upd[NS_KEY] = str(no_show)
        async with SessionLocal() as db:
            await set_time_rules(db, upd)

    try:
        async with SessionLocal() as db:
            u = {n: User(email=f"par_{n}_{sfx}@test.com", full_name=f"Par {n}",
                         hashed_password="x", is_active=True)
                 for n in ("day", "night", "none")}
            db.add_all(u.values())
            await db.flush()
            for n, x in u.items():
                db.add(Employee(
                    user_id=x.id, employee_id=f"PA{sfx}{n}", department="Eng",
                    location="LocA", designation="T",
                    date_of_joining=date(2020, 1, 1),
                    status=EmployeeStatus.ACTIVE))
            t_day = ShiftTemplate(name=tpl_names[0], start_time=time(9),
                                  end_time=time(17), grace_in_minutes=0,
                                  grace_out_minutes=30)
            t_night = ShiftTemplate(name=tpl_names[1], start_time=time(22),
                                    end_time=time(6), is_overnight=True,
                                    grace_in_minutes=0, grace_out_minutes=30)
            db.add_all([t_day, t_night])
            await db.commit()
            ids = {n: x.id for n, x in u.items()}
            ids.update(t_day=t_day.id, t_night=t_night.id)
        yield {"ids": ids, "rules": rules}
    finally:
        async with SessionLocal() as db:
            uids = list((await db.execute(select(User.id).where(
                User.email.like(f"par\\_%\\_{sfx}@test.com")))).scalars().all())
            tids = list((await db.execute(select(ShiftTemplate.id).where(
                ShiftTemplate.name.in_(tpl_names)))).scalars().all())
            await purge_gap_notifications(db, tids)
            await db.execute(delete(CoverageGap).where(
                CoverageGap.shift_template_id.in_(tids)))
            await db.execute(delete(NoShowAlert).where(NoShowAlert.user_id.in_(uids)))
            await db.execute(delete(Attendance).where(Attendance.user_id.in_(uids)))
            await db.execute(delete(RosterEntryHistory).where(
                RosterEntryHistory.employee_id.in_(uids)))
            await db.execute(delete(RosterEntry).where(RosterEntry.employee_id.in_(uids)))
            await db.execute(delete(Notification).where(Notification.user_id.in_(uids)))
            await db.execute(delete(Notification).where(
                Notification.message.like(f"%Par %")))
            await db.execute(delete(Employee).where(Employee.user_id.in_(uids)))
            await purge_shift_templates(db, tids)
            await db.execute(delete(User).where(User.id.in_(uids)))
            await db.commit()
        await _restore(snap)


async def _roster(uid, d, tpl):
    async with SessionLocal() as db:
        db.add(RosterEntry(employee_id=uid, work_date=d, shift_template_id=tpl,
                           status=RosterStatus.PUBLISHED))
        await db.commit()


async def _late_minutes(w, punch, now):
    d = date(2026, 11, 20)
    await _roster(w["ids"]["day"], d, w["ids"]["t_day"])
    async with SessionLocal() as db:
        db.add(Attendance(user_id=w["ids"]["day"], mode="web", work_date=d,
                          captured_at=punch, shift_template_id=w["ids"]["t_day"]))
        await db.commit()
    async with SessionLocal() as db:
        rows = await live_ops.live_board(db, [w["ids"]["day"]], now)
    assert rows[0].work_date == d
    return rows[0].late_minutes


async def test_late_minutes_utc(world):
    await world["rules"]("UTC")
    got = await _late_minutes(
        world, datetime(2026, 11, 20, 9, 20, tzinfo=UTC),
        datetime(2026, 11, 20, 10, 0, tzinfo=UTC))
    assert got == 20


async def test_late_minutes_ist_on_time_window(world):
    await world["rules"]("Asia/Kolkata")
    got = await _late_minutes(
        world, datetime(2026, 11, 20, 3, 50, tzinfo=UTC),
        datetime(2026, 11, 20, 5, 0, tzinfo=UTC))
    assert got == 20


async def test_late_minutes_ist_utc_punch_is_very_late(world):
    await world["rules"]("Asia/Kolkata")
    got = await _late_minutes(
        world, datetime(2026, 11, 20, 9, 20, tzinfo=UTC),
        datetime(2026, 11, 20, 10, 0, tzinfo=UTC))
    assert got == 350


async def test_punch_attribution_no_shift_local_date(world):
    punch = datetime(2026, 11, 20, 20, 0, tzinfo=UTC)  # 01:30 IST on the 21st
    await world["rules"]("Asia/Kolkata")
    async with SessionLocal() as db:
        wd, *_ = await _attribute_punch(db, world["ids"]["none"], punch)
    assert wd == date(2026, 11, 21)
    await world["rules"]("UTC")
    async with SessionLocal() as db:
        wd, *_ = await _attribute_punch(db, world["ids"]["none"], punch)
    assert wd == date(2026, 11, 20)


async def test_punch_attribution_overnight_ist_vs_utc(world):
    # 22:00-06:00 shift on the 20th. 17:00Z == 22:30 IST on the 20th: only
    # IST sees this punch inside the shift window.
    await _roster(world["ids"]["night"], date(2026, 11, 20), world["ids"]["t_night"])
    punch = datetime(2026, 11, 20, 17, 0, tzinfo=UTC)
    await world["rules"]("Asia/Kolkata")
    async with SessionLocal() as db:
        wd, shift_id, cross, flag = await _attribute_punch(
            db, world["ids"]["night"], punch)
    assert (wd, shift_id, cross, flag) == (
        date(2026, 11, 20), world["ids"]["t_night"], False, None)
    await world["rules"]("UTC")
    async with SessionLocal() as db:
        _wd, _sid, _cross, flag = await _attribute_punch(
            db, world["ids"]["night"], punch)
    assert flag == "outside_window"
    # the early-morning end of the shift: 00:45Z on the 21st == 06:15 IST
    await world["rules"]("Asia/Kolkata")
    async with SessionLocal() as db:
        wd, _sid, cross, _flag = await _attribute_punch(
            db, world["ids"]["night"], datetime(2026, 11, 21, 0, 45, tzinfo=UTC))
    assert wd == date(2026, 11, 20) and cross is True


async def _no_show(w, now):
    await w["rules"]("Asia/Kolkata", no_show=30)
    await _roster(w["ids"]["day"], date(2026, 11, 20), w["ids"]["t_day"])
    async with SessionLocal() as db:
        return await live_ops.no_show_job(db, now=now, user_ids=[w["ids"]["day"]])


async def _alert_count(w):
    async with SessionLocal() as db:
        return len((await db.execute(select(NoShowAlert).where(
            NoShowAlert.user_id == w["ids"]["day"]))).scalars().all())


async def test_no_show_flags_after_local_threshold(world):
    await _no_show(world, datetime(2026, 11, 20, 4, 10, tzinfo=UTC))  # 09:40 IST
    assert await _alert_count(world) == 1


async def test_no_show_not_before_local_threshold(world):
    await _no_show(world, datetime(2026, 11, 20, 3, 50, tzinfo=UTC))  # 09:20 IST
    assert await _alert_count(world) == 0


# ---------------- pure (no DB) IST unit tests ----------------

from types import SimpleNamespace  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

IST = ZoneInfo("Asia/Kolkata")


def test_is_late_ist():
    from app.services.late_mark import _is_late
    shift = SimpleNamespace(start_time=time(9, 0), end_time=time(17, 0))
    d = date(2026, 11, 20)
    assert _is_late(datetime(2026, 11, 20, 3, 40, tzinfo=UTC), d, shift, 10, IST) is False
    assert _is_late(datetime(2026, 11, 20, 3, 41, tzinfo=UTC), d, shift, 10, IST) is True
    assert _is_late(datetime(2026, 11, 20, 9, 5), d, shift, 10, UTC) is False


def _row(**kw):
    from app.services.reports import AttendanceRow
    base = dict(user_id=1, employee_code="E1", full_name="R", department="Eng",
                work_date=date(2026, 11, 20), shift_name="S",
                grace_in_minutes=0, grace_out_minutes=0)
    base.update(kw)
    return AttendanceRow(**base)


def test_build_late_early_ist_and_overnight():
    from app.services.reports import ReportFilter, build_late_early
    day = _row(shift_start=time(9), shift_end=time(18),
               punch_in=datetime(2026, 11, 20, 3, 50, tzinfo=UTC),   # 09:20 IST
               punch_out=datetime(2026, 11, 20, 12, 0, tzinfo=UTC))  # 17:30 IST
    r = build_late_early(records=[day], filters=ReportFilter(), tz=IST)
    assert (r.rows[0]["late_minutes"], r.rows[0]["early_minutes"]) == (20, 30)
    # overnight 22:00-06:00, left at 05:00 IST next day = 23:30Z -> 60 early
    night = _row(shift_start=time(22), shift_end=time(6),
                 punch_in=datetime(2026, 11, 20, 16, 30, tzinfo=UTC),
                 punch_out=datetime(2026, 11, 20, 23, 30, tzinfo=UTC))
    r = build_late_early(records=[night], filters=ReportFilter(), tz=IST)
    assert (r.rows[0]["late_minutes"], r.rows[0]["early_minutes"]) == (0, 60)


def test_night_allowance_ist_window():
    from app.services.overtime import compute_night_allowance
    rule = SimpleNamespace(payout_model="flat", flat_amount=200.0,
                           hourly_rate=80.0, night_window_start=time(22),
                           night_window_end=time(6), min_night_minutes=60)
    d = date(2026, 11, 20)
    # 16:30Z-00:30Z == 22:00-06:00 IST -> the full 8h night
    got = compute_night_allowance(
        punch_in=datetime(2026, 11, 20, 16, 30, tzinfo=UTC),
        punch_out=datetime(2026, 11, 21, 0, 30, tzinfo=UTC),
        work_date=d, rule=rule, tz=IST)
    assert got.night_minutes == 480
    # a 09:00-17:00 IST day shift (03:30Z-11:30Z) has no night minutes
    day = compute_night_allowance(
        punch_in=datetime(2026, 11, 20, 3, 30, tzinfo=UTC),
        punch_out=datetime(2026, 11, 20, 11, 30, tzinfo=UTC),
        work_date=d, rule=rule, tz=IST)
    assert day.night_minutes == 0


def test_parse_time_input_ist():
    from app.api.v1.endpoints.attendance_bulk import parse_time_input
    d = date(2026, 11, 20)
    assert parse_time_input("09:00", d, IST) == datetime(2026, 11, 20, 3, 30, tzinfo=UTC)
    assert parse_time_input("09:00", d) == datetime(2026, 11, 20, 9, 0, tzinfo=UTC)
    assert parse_time_input("2026-11-20T09:00:00Z", d, IST) == datetime(
        2026, 11, 20, 9, 0, tzinfo=UTC)


def test_ics_emits_utc_stamps_for_ist_shift():
    from app.services.ics import IcsEvent, render_ics
    from app.services.org_time import shift_window
    s, e = shift_window(date(2026, 11, 20), time(9), time(17), IST)
    out = render_ics([IcsEvent(uid="x@hrms", start=s, end=e, summary="D")],
                     cal_name="c", now=datetime(2026, 11, 20, tzinfo=UTC))
    assert "DTSTART:20261120T033000Z" in out and "DTEND:20261120T113000Z" in out


# ---------------- biometric default offset follows org tz ----------------

BIO_KEY = "biometric.default_utc_offset_minutes"


async def _bio_offset(tz, bio):
    from app.services.biometric import default_offset
    snap = await _snapshot([TZ_KEY, BIO_KEY])
    try:
        async with SessionLocal() as db:
            await set_time_rules(db, {TZ_KEY: tz, BIO_KEY: bio})
        async with SessionLocal() as db:
            return await default_offset(db)
    finally:
        await _restore(snap)


async def test_biometric_blank_follows_org_tz():
    assert await _bio_offset("Asia/Kolkata", "") == 330
    assert await _bio_offset("UTC", "") == 0


async def test_biometric_explicit_offset_wins():
    assert await _bio_offset("Asia/Kolkata", "240") == 240


async def test_org_tz_memoised_and_cleared_on_change():
    from app.services.org_time import org_tz
    snap = await _snapshot([TZ_KEY])
    try:
        async with SessionLocal() as db:
            await set_time_rules(db, {TZ_KEY: "UTC"})
            assert await org_tz(db) is UTC
            assert db.info["org_tz"] is UTC
            await set_time_rules(db, {TZ_KEY: "Asia/Kolkata"})
            assert "org_tz" not in db.info
            assert str(await org_tz(db)) == "Asia/Kolkata"
    finally:
        await _restore(snap)
