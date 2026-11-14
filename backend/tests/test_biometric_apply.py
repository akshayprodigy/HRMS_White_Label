"""Biometric apply engine, first-in / last-out (Roadmap v2 Phase 4, Task 3).

DB-backed on the real dev DB, far-future dates (2031), full teardown."""
import asyncio
import itertools
import random
import uuid
from datetime import date, datetime, time, timedelta, timezone

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, insert, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from _cleanup import purge_shift_templates
from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.models.attendance import Attendance
from app.models.approval import ApprovalItem, ApprovalStep
from app.models.audit import AuditLog
from app.models.biometric import (
    BiometricDevice, BiometricDeviceStatus, BiometricPunch,
    BiometricPunchState as S, BiometricUserMap,
)
from app.models.comp_off import CompOffAccrual
from app.models.employee import Employee
from app.models.hr import HolidayCalendar
from app.models.notification import Notification
from app.models.shift import EmployeeShiftAssignment, ShiftTemplate
from app.models.system import SystemSetting
from app.models.user import Role, User, user_roles
from app.services import biometric as bio
from app.api import deps
from app.main import create_app
from app.services import punch
from app.services.time_rules import set_time_rules
from app.services.attendance_lock import LockRetry

NAMES = ("fwd", "rev", "rnd", "night", "app", "edit", "lock", "unm", "pend",
         "single", "quiet", "live", "conc", "hol", "inact", "mapq", "perm")
NO_SHIFT = {"quiet", "live"}


def at(d: date, hh: int, mm: int, ss: int = 0) -> datetime:
    return datetime(d.year, d.month, d.day, hh, mm, ss, tzinfo=timezone.utc)


@pytest.fixture
async def world():
    sfx = uuid.uuid4().hex[:8]
    ids: dict = {"sfx": sfx}
    try:
        async with SessionLocal() as db:
            day = ShiftTemplate(name=f"BAD{sfx}", start_time=time(9),
                                end_time=time(18))
            night = ShiftTemplate(name=f"BAN{sfx}", start_time=time(22),
                                  end_time=time(6), is_overnight=True)
            us = {n: User(email=f"bio_{n}_{sfx}@t.com", full_name=f"B {n}",
                          hashed_password=get_password_hash("x"),
                          is_active=(n != "inact")) for n in NAMES}
            us["hr"] = User(email=f"bio_hr_{sfx}@t.com", full_name="B hr",
                            hashed_password=get_password_hash("x"),
                            is_active=True)
            db.add_all([day, night, *us.values()])
            await db.commit()
            hr_role = (await db.execute(
                select(Role).where(Role.name == "HR"))).scalars().first()
            if hr_role is not None:
                await db.execute(insert(user_roles).values(
                    user_id=us["hr"].id, role_id=hr_role.id))
            for n, u in us.items():
                if n in NO_SHIFT or n == "hr":
                    continue
                db.add(EmployeeShiftAssignment(
                    employee_id=u.id,
                    shift_template_id=(night if n == "night" else day).id,
                    effective_from=date(2031, 1, 1)))
            dev = BiometricDevice(serial=f"BSN{sfx}", utc_offset_minutes=330,
                                  status=BiometricDeviceStatus.ACTIVE)
            db.add(dev)
            await db.commit()
            ids.update({n: u.id for n, u in us.items()})
            ids["dev"] = dev.id
            ids["tpls"] = [day.id, night.id]
            ids["has_hr_role"] = hr_role is not None
        yield ids
    finally:
        async with SessionLocal() as db:
            uids = list((await db.execute(select(User.id).where(
                User.email.like(f"bio\\_%\\_{sfx}@t.com")))).scalars().all())
            aids = [str(i) for i in (await db.execute(select(Attendance.id).where(
                Attendance.user_id.in_(uids)))).scalars().all()]
            if aids:
                await db.execute(delete(Notification).where(
                    Notification.resource_type == "attendance",
                    Notification.resource_id.in_(aids)))
                await db.execute(delete(AuditLog).where(
                    AuditLog.resource_type == "attendance",
                    AuditLog.resource_id.in_(aids)))
            accids = [str(i) for i in (await db.execute(select(
                CompOffAccrual.id).where(
                CompOffAccrual.user_id.in_(uids)))).scalars().all()]
            if accids:
                items = list((await db.execute(select(ApprovalItem.id).where(
                    ApprovalItem.resource_type == "comp_off_accrual",
                    ApprovalItem.resource_id.in_(accids)))).scalars().all())
                if items:
                    await db.execute(delete(ApprovalStep).where(
                        ApprovalStep.approval_item_id.in_(items)))
                    await db.execute(delete(ApprovalItem).where(
                        ApprovalItem.id.in_(items)))
                await db.execute(delete(Notification).where(
                    Notification.resource_type == "comp_off_accrual",
                    Notification.resource_id.in_(accids)))
                await db.execute(delete(AuditLog).where(
                    AuditLog.resource_type == "comp_off_accrual",
                    AuditLog.resource_id.in_(accids)))
            await db.execute(delete(CompOffAccrual).where(
                CompOffAccrual.user_id.in_(uids)))
            await db.execute(delete(Notification).where(
                Notification.user_id.in_(uids)))
            await db.execute(delete(AuditLog).where(AuditLog.user_id.in_(uids)))
            devs = list((await db.execute(select(BiometricDevice.id).where(
                BiometricDevice.serial.like(f"BSN{sfx}%")))).scalars().all())
            await db.execute(delete(BiometricPunch).where(
                BiometricPunch.pin.like(f"{sfx}%")))
            await db.execute(delete(BiometricUserMap).where(
                BiometricUserMap.pin.like(f"{sfx}%")))
            await db.execute(delete(Attendance).where(
                Attendance.user_id.in_(uids)))
            await db.execute(delete(HolidayCalendar).where(
                HolidayCalendar.name == f"BIOH{sfx}"))
            if devs:
                await db.execute(delete(BiometricDevice).where(
                    BiometricDevice.id.in_(devs)))
            await db.execute(delete(EmployeeShiftAssignment).where(
                EmployeeShiftAssignment.employee_id.in_(uids)))
            await purge_shift_templates(db, ids.get("tpls", []))
            await db.execute(delete(User).where(User.id.in_(uids)))
            await db.commit()


async def _map(db, w, name, pin, device_id=None):
    db.add(BiometricUserMap(device_id=device_id, pin=pin, user_id=w[name]))
    await db.commit()


async def feed(w, name, times, *, order=None, pin=None, quiet=False,
               dedupe=120):
    """Store `times` for user `name` (mapped globally) and apply them in
    `order` (default: given order). Returns states in application order."""
    pin = pin or f"{w['sfx']}{name}"
    async with SessionLocal() as db:
        if await bio.resolve_user_id(db, w["dev"], pin) is None:
            await _map(db, w, name, pin)
        dev = await db.get(BiometricDevice, w["dev"])
        n, rows = await bio.store_taps(
            db, source="adms", device=dev,
            taps=[(pin, t, "0", "1", "raw") for t in times])
        await db.commit()
        assert n == len(set(times))
        by_time = {bio.as_utc(r.punch_time): r for r in rows}
        states = []
        for t in (order or times):
            bp = by_time[t]
            await bio.apply_punch(db, bp, dedupe_seconds=dedupe, quiet=quiet)
            await db.commit()
            states.append(bp.state)
        return states


async def day_row(w, name, d):
    async with SessionLocal() as db:
        return (await db.execute(select(Attendance).where(
            Attendance.user_id == w[name], Attendance.work_date == d
        ).execution_options(populate_existing=True))).scalars().all()


def io(row):
    return (bio.as_utc(row.captured_at),
            bio.as_utc(row.punch_out_time) if row.punch_out_time else None)


async def test_forward_order_first_in_last_out(world):
    d = date(2031, 3, 10)
    taps = [at(d, 9, 2), at(d, 9, 3), at(d, 13, 0), at(d, 18, 5)]
    states = await feed(world, "fwd", taps)
    assert states == [S.APPLIED, S.DUPLICATE, S.APPLIED, S.APPLIED]
    (row,) = await day_row(world, "fwd", d)
    assert io(row) == (at(d, 9, 2), at(d, 18, 5))
    assert row.mode == "biometric"
    assert row.remarks == f"device BSN{world['sfx']}"


async def test_reverse_order_same_result(world):
    d = date(2031, 3, 10)
    taps = [at(d, 9, 2), at(d, 9, 3), at(d, 13, 0), at(d, 18, 5)]
    await feed(world, "rev", taps, order=list(reversed(taps)))
    (row,) = await day_row(world, "rev", d)
    assert io(row) == (at(d, 9, 2), at(d, 18, 5))


async def test_random_permutations_are_order_independent(world):
    taps_of = lambda d: [at(d, 9, 0), at(d, 9, 1), at(d, 9, 1, 30),
                         at(d, 9, 2, 30), at(d, 13, 0), at(d, 18, 0, 30)]
    rng = random.Random(2031)
    seen = set()
    for i in range(5):
        d = date(2031, 4, 1) + timedelta(days=i)
        taps = taps_of(d)
        order = taps[:]
        rng.shuffle(order)
        await feed(world, "rnd", taps, order=order)
        (row,) = await day_row(world, "rnd", d)
        i_, o_ = io(row)
        seen.add((i_ - at(d, 0, 0), o_ - at(d, 0, 0)))
    assert seen == {(timedelta(hours=9), timedelta(hours=18, seconds=30))}


async def test_all_permutations_close_taps_never_make_an_out(world):
    # 09:00:00 / 09:00:50 / 09:01:40: whole day spans 100s < 120s
    for i, perm in enumerate(itertools.permutations(range(3))):
        d = date(2031, 4, 10) + timedelta(days=i)
        taps = [at(d, 9, 0), at(d, 9, 0, 50), at(d, 9, 1, 40)]
        await feed(world, "perm", taps, order=[taps[j] for j in perm])
        (row,) = await day_row(world, "perm", d)
        assert io(row) == (at(d, 9, 0), None), perm


async def test_all_permutations_span_at_threshold_makes_out(world):
    # span exactly 120s: out = latest tap, in every order
    for i, perm in enumerate(itertools.permutations(range(3))):
        d = date(2031, 4, 20) + timedelta(days=i)
        taps = [at(d, 9, 0), at(d, 9, 1, 10), at(d, 9, 2)]
        await feed(world, "perm", taps, order=[taps[j] for j in perm])
        (row,) = await day_row(world, "perm", d)
        assert io(row) == (at(d, 9, 0), at(d, 9, 2)), perm


async def test_night_shift_one_row_workdate_is_start_day(world):
    d = date(2031, 3, 20)
    taps = [at(d, 22, 1), at(d + timedelta(days=1), 6, 4)]
    await feed(world, "night", taps)
    rows = await day_row(world, "night", d)
    assert len(rows) == 1 and io(rows[0]) == (taps[0], taps[1])
    assert not await day_row(world, "night", d + timedelta(days=1))
    # reverse order, a different night
    d2 = date(2031, 3, 25)
    taps2 = [at(d2, 22, 1), at(d2 + timedelta(days=1), 6, 4)]
    await feed(world, "night", taps2, order=list(reversed(taps2)))
    (r2,) = await day_row(world, "night", d2)
    assert io(r2) == (taps2[0], taps2[1])


async def test_merges_with_existing_app_punch_keeps_mode(world):
    d = date(2031, 3, 11)
    async with SessionLocal() as db:
        user = await db.get(User, world["app"])
        await punch.record_punch_in(
            db, user, mode="web", captured_at=at(d, 9, 10), fresh=True)
        await db.commit()
    await feed(world, "app", [at(d, 9, 0), at(d, 18, 0)])
    (row,) = await day_row(world, "app", d)
    assert io(row) == (at(d, 9, 0), at(d, 18, 0))
    assert row.mode == "web"


async def test_hr_edited_row_is_never_overwritten(world):
    d = date(2031, 3, 12)
    async with SessionLocal() as db:
        user = await db.get(User, world["edit"])
        row, _ = await punch.record_punch_in(
            db, user, mode="web", captured_at=at(d, 9, 30), fresh=True)
        row.edited_by_id = world["hr"]
        await db.commit()
    states = await feed(world, "edit", [at(d, 9, 0), at(d, 18, 0)])
    assert states == [S.EDITED, S.EDITED]
    (row,) = await day_row(world, "edit", d)
    assert io(row) == (at(d, 9, 30), None)


async def test_payroll_locked_day(world, monkeypatch):
    async def locked(db, wd, fresh=False):
        raise HTTPException(status_code=409, detail="locked")
    monkeypatch.setattr(bio, "assert_attendance_editable", locked)
    d = date(2031, 3, 13)
    states = await feed(world, "lock", [at(d, 9, 0)])
    assert states == [S.LOCKED]
    assert not await day_row(world, "lock", d)


async def test_unmapped_then_map_then_apply_pending(world):
    d = date(2031, 3, 14)
    pin = f"{world['sfx']}unm"
    async with SessionLocal() as db:
        dev = await db.get(BiometricDevice, world["dev"])
        _, rows = await bio.store_taps(
            db, source="adms", device=dev,
            taps=[(pin, at(d, 9, 0), None, None, "r"),
                  (pin, at(d, 18, 0), None, None, "r")])
        await db.commit()
        assert [r.state for r in rows] == [S.UNMAPPED, S.UNMAPPED]
        await bio.apply_punch(db, rows[0])  # still unmapped
        assert rows[0].state == S.UNMAPPED
        await db.commit()
        await _map(db, world, "unm", pin)
        counts = await bio.apply_pending(SessionLocal, pin=pin)
        await db.commit()
        assert counts == {S.APPLIED: 2}
    (row,) = await day_row(world, "unm", d)
    assert io(row) == (at(d, 9, 0), at(d, 18, 0))
    # user_id filter also finds rows via the user's maps
    async with SessionLocal() as db:
        assert await bio.apply_pending(SessionLocal, user_id=world["unm"]) == {}


async def test_apply_pending_by_user_id(world):
    d = date(2031, 3, 15)
    pin = f"{world['sfx']}mapq"
    async with SessionLocal() as db:
        dev = await db.get(BiometricDevice, world["dev"])
        await bio.store_taps(db, source="adms", device=dev,
                             taps=[(pin, at(d, 9, 0), None, None, "r")])
        await _map(db, world, "mapq", pin)
        assert await bio.apply_pending(SessionLocal, user_id=world["mapq"]) == \
            {S.APPLIED: 1}
        await db.commit()
    assert len(await day_row(world, "mapq", d)) == 1


async def test_pending_device_then_approve_then_apply_pending(world):
    d = date(2031, 3, 16)
    pin = f"{world['sfx']}pend"
    async with SessionLocal() as db:
        pdev = BiometricDevice(serial=f"BSN{world['sfx']}P",
                               utc_offset_minutes=330)  # default: pending
        db.add(pdev)
        await db.commit()
        await _map(db, world, "pend", pin)
        _, rows = await bio.store_taps(
            db, source="adms", device=pdev,
            taps=[(pin, at(d, 9, 0), None, None, "r"),
                  (pin, at(d, 18, 0), None, None, "r")])
        await db.commit()
        assert [r.state for r in rows] == [S.PENDING_DEVICE] * 2
        await bio.apply_punch(db, rows[0])
        assert rows[0].state == S.PENDING_DEVICE
        assert await bio.apply_pending(SessionLocal, device_id=pdev.id) == \
            {S.PENDING_DEVICE: 2}  # still pending: nothing applied
        pdev.status = BiometricDeviceStatus.ACTIVE
        await db.commit()
        assert await bio.apply_pending(SessionLocal, device_id=pdev.id) == {S.APPLIED: 2}
        await db.commit()
    (row,) = await day_row(world, "pend", d)
    assert io(row) == (at(d, 9, 0), at(d, 18, 0))


async def test_store_taps_idempotent_and_truncates(world):
    d = date(2031, 3, 17)
    long_pin = "P" * 50
    taps = [(long_pin, at(d, 9, 0), "0", "1", "x" * 900)]
    async with SessionLocal() as db:
        dev = await db.get(BiometricDevice, world["dev"])
        try:
            n, rows = await bio.store_taps(db, source="adms", device=dev,
                                           taps=taps)
            await db.commit()
            assert n == 1 and len(rows[0].raw) == 500
            assert rows[0].pin == "P" * 32
            n2, rows2 = await bio.store_taps(db, source="adms", device=dev,
                                             taps=taps)
            assert (n2, rows2) == (0, [])
            # same tap via another source key is a different row
            n3, _ = await bio.store_taps(db, source="import", device=None,
                                         taps=taps)
            assert n3 == 1
            await db.commit()
        finally:
            await db.execute(delete(BiometricPunch).where(
                BiometricPunch.pin == "P" * 32,
                BiometricPunch.punch_time == at(d, 9, 0)))
            await db.commit()


async def test_single_tap_is_in_only(world):
    d = date(2031, 3, 18)
    assert await feed(world, "single", [at(d, 9, 5)]) == [S.APPLIED]
    (row,) = await day_row(world, "single", d)
    assert io(row) == (at(d, 9, 5), None)


async def test_inactive_user_ignored(world):
    d = date(2031, 3, 19)
    assert await feed(world, "inact", [at(d, 9, 0)]) == [S.IGNORED]
    assert not await day_row(world, "inact", d)


async def _att_notifs(w, name, d):
    async with SessionLocal() as db:
        aids = [str(i) for i in (await db.execute(select(Attendance.id).where(
            Attendance.user_id == w[name], Attendance.work_date == d
        ))).scalars().all()]
        if not aids:
            return None
        return (await db.execute(select(Notification).where(
            Notification.resource_type == "attendance",
            Notification.resource_id.in_(aids)))).scalars().all()


async def test_backfill_is_quiet_live_tap_notifies_like_app_punch(world):
    if not world["has_hr_role"]:
        pytest.skip("no HR role in DB")
    d = date(2031, 5, 5)  # these two users have no shift: NO_SHIFT flag
    # back-fill path: apply_pending(quiet=True)
    pin = f"{world['sfx']}quiet"
    async with SessionLocal() as db:
        dev = await db.get(BiometricDevice, world["dev"])
        await bio.store_taps(db, source="adms", device=dev,
                             taps=[(pin, at(d, 9, 0), None, None, "r")])
        await _map(db, world, "quiet", pin)
        assert await bio.apply_pending(SessionLocal, pin=pin) == {S.APPLIED: 1}
        await db.commit()
    (qrow,) = await day_row(world, "quiet", d)
    assert qrow.attribution_flag == "no_shift"  # attribution kept
    assert await _att_notifs(world, "quiet", d) == []
    # live path: apply_punch default quiet=False == an app punch
    assert await feed(world, "live", [at(d, 9, 0)]) == [S.APPLIED]
    notifs = await _att_notifs(world, "live", d)
    assert notifs and any(
        n.user_id == world["hr"] and n.event_type == "attendance_unscheduled"
        for n in notifs)
    # audit rows are still written in quiet mode
    async with SessionLocal() as db:
        assert (await db.execute(select(AuditLog).where(
            AuditLog.resource_type == "attendance",
            AuditLog.resource_id == str(qrow.id),
            AuditLog.action == "MARK_ATTENDANCE"))).scalars().first()


async def test_concurrent_first_taps_make_one_row(world):
    d = date(2031, 3, 21)
    pin = f"{world['sfx']}conc"
    async with SessionLocal() as db:
        await _map(db, world, "conc", pin)
        dev = await db.get(BiometricDevice, world["dev"])
        _, rows = await bio.store_taps(
            db, source="adms", device=dev,
            taps=[(pin, at(d, 9, 0), None, None, "r"),
                  (pin, at(d, 18, 0), None, None, "r")])
        await db.commit()
        bp_ids = [r.id for r in rows]

    states = await asyncio.gather(*[
        bio.apply_punch_committed(SessionLocal, i) for i in bp_ids])
    assert S.ERROR not in states
    rows = await day_row(world, "conc", d)
    assert len(rows) == 1
    assert io(rows[0]) == (at(d, 9, 0), at(d, 18, 0))


async def _accruals(w):
    async with SessionLocal() as db:
        return (await db.execute(select(CompOffAccrual).where(
            CompOffAccrual.user_id == w["hol"]
        ).order_by(CompOffAccrual.holiday_date))).scalars().all()


async def test_comp_off_is_independent_of_arrival_order(world):
    ds = [date(2031, 6, 2) + timedelta(days=i) for i in range(4)]
    async with SessionLocal() as db:
        for d in ds:
            db.add(HolidayCalendar(name=f"BIOH{world['sfx']}", date=d,
                                   location="All"))
        await db.commit()
    t = lambda d: {"in": at(d, 9, 0), "mid": at(d, 13, 0), "out": at(d, 17, 0)}
    orders = [
        ("in", "mid", "out"),   # out extended twice
        ("out", "mid", "in"),   # fully reversed
        ("mid", "out", "in"),   # closed row, earliest tap arrives last
        ("out", "in", "mid"),
    ]
    for d, order in zip(ds, orders):
        tt = t(d)
        await feed(world, "hol", [tt["in"], tt["mid"], tt["out"]],
                   order=[tt[k] for k in order])
    acc = await _accruals(world)
    assert [(a.holiday_date, a.worked_minutes) for a in acc] == \
        [(d, 480) for d in ds]


async def test_in_move_writes_audit_row(world):
    d = date(2031, 7, 10)
    await feed(world, "rev", [at(d, 9, 0), at(d, 18, 0)],
               order=[at(d, 18, 0), at(d, 9, 0)])
    (row,) = await day_row(world, "rev", d)
    async with SessionLocal() as db:
        a = (await db.execute(select(AuditLog).where(
            AuditLog.resource_id == str(row.id),
            AuditLog.action == "BIOMETRIC_PUNCH_IN_MOVED"))).scalars().all()
    assert len(a) == 1
    assert a[0].details["previous"].startswith("2031-07-10T18:00")
    assert a[0].details["new"].startswith("2031-07-10T09:00")


async def test_app_out_later_than_tap_stays(world):
    d = date(2031, 3, 30)
    async with SessionLocal() as db:
        user = await db.get(User, world["app"])
        await punch.record_punch_in(
            db, user, mode="web", captured_at=at(d, 9, 10), fresh=True)
        await punch.record_punch_out(db, user, at=at(d, 19, 0), fresh=True)
        await db.commit()
    assert await feed(world, "app", [at(d, 18, 0)]) == [S.DUPLICATE]
    (row,) = await day_row(world, "app", d)
    assert io(row) == (at(d, 9, 10), at(d, 19, 0))


async def _unmapped_taps(w, name, d, times):
    pin = f"{w['sfx']}{name}"
    async with SessionLocal() as db:
        dev = await db.get(BiometricDevice, w["dev"])
        _, rows = await bio.store_taps(
            db, source="adms", device=dev,
            taps=[(pin, tm, None, None, "r") for tm in times])
        await _map(db, w, name, pin)
        return pin, [r.id for r in rows]


async def test_apply_pending_conflict_leaves_state_others_apply(
        world, monkeypatch):
    d = date(2031, 7, 11)
    pin, ids = await _unmapped_taps(
        world, "mapq", d, [at(d, 9, 0), at(d, 13, 0), at(d, 18, 0)])
    real = bio.apply_punch

    async def flaky(db, bp, **kw):
        if bp.id == ids[1]:
            raise LockRetry()
        return await real(db, bp, **kw)
    monkeypatch.setattr(bio, "apply_punch", flaky)
    counts = await bio.apply_pending(SessionLocal, pin=pin, attempts=2)
    assert counts == {S.APPLIED: 2, "conflict": 1}
    async with SessionLocal() as db:
        st = {i: (await db.get(BiometricPunch, i)).state for i in ids}
    assert st[ids[1]] == S.UNMAPPED  # unchanged, never ERROR
    assert st[ids[0]] == st[ids[2]] == S.APPLIED
    # next run (no more conflict) picks it up
    monkeypatch.setattr(bio, "apply_punch", real)
    assert await bio.apply_pending(SessionLocal, pin=pin) == {S.DUPLICATE: 1}


async def test_apply_pending_error_path_continues_and_reprocess_states(
        world, monkeypatch):
    d = date(2031, 7, 12)
    pin, ids = await _unmapped_taps(
        world, "mapq", d, [at(d, 9, 0), at(d, 13, 0), at(d, 18, 0)])
    real = bio.apply_punch

    async def boom(db, bp, **kw):
        if bp.id == ids[1]:
            raise RuntimeError("kaboom")
        return await real(db, bp, **kw)
    monkeypatch.setattr(bio, "apply_punch", boom)
    counts = await bio.apply_pending(SessionLocal, pin=pin)
    assert counts == {S.APPLIED: 2, S.ERROR: 1}
    async with SessionLocal() as db:
        bp = await db.get(BiometricPunch, ids[1])
        assert bp.state == S.ERROR and "kaboom" in bp.error
    # default states skip ERROR rows; states={error} reprocesses them
    monkeypatch.setattr(bio, "apply_punch", real)
    assert await bio.apply_pending(SessionLocal, pin=pin) == {}
    assert await bio.apply_pending(
        SessionLocal, pin=pin, states={S.ERROR}) == {S.DUPLICATE: 1}


async def test_app_punch_out_extends_device_closed_row(world):
    d = date(2031, 7, 13)
    await feed(world, "single", [at(d, 9, 0), at(d, 17, 0)])
    async with SessionLocal() as db:
        user = await db.get(User, world["single"])
        await punch.record_punch_out(db, user, at=at(d, 19, 0), fresh=True)
        await db.commit()
    (row,) = await day_row(world, "single", d)
    assert io(row) == (at(d, 9, 0), at(d, 19, 0))


async def test_app_only_second_punch_out_still_400(world):
    d = date(2031, 7, 14)
    async with SessionLocal() as db:
        user = await db.get(User, world["lock"])
        await punch.record_punch_in(
            db, user, mode="web", captured_at=at(d, 9, 10), fresh=True)
        await punch.record_punch_out(db, user, at=at(d, 18, 0), fresh=True)
        await db.commit()
        with pytest.raises(punch.PunchRejected) as ei:
            await punch.record_punch_out(db, user, at=at(d, 19, 0), fresh=True)
        assert ei.value.status_code == 400


@pytest.fixture
async def rules():
    keys = ("attendance.selfie_required", "attendance.offline_max_hours")
    async with SessionLocal() as db:
        saved = {k: (await db.get(SystemSetting, k)) for k in keys}
        saved = {k: (v.value if v else None) for k, v in saved.items()}

    async def setter(**kw):
        async with SessionLocal() as db:
            await set_time_rules(db, {f"attendance.{k}": v for k, v in kw.items()})
    yield setter
    async with SessionLocal() as db:
        for k, v in saved.items():
            row = await db.get(SystemSetting, k)
            if v is None and row is not None:
                await db.delete(row)
            elif v is not None and row is not None:
                row.value = v
        await db.commit()


async def test_selfie_rule_follows_caller_not_device_row_mode(world, rules):
    await rules(selfie_required="1")
    d = date(2031, 7, 20)
    await feed(world, "single", [at(d, 9, 0)])  # device-created, mode biometric
    async with SessionLocal() as db:
        user = await db.get(User, world["single"])
        for kw in ({"mode": "mobile"}, {"is_offline": True}):
            with pytest.raises(punch.PunchRejected) as ei:
                await punch.record_punch_out(
                    db, user, at=at(d, 18, 0), fresh=True, **kw)
            assert ei.value.status_code == 400
            assert "selfie" in str(ei.value.detail).lower()
        # a web caller is exempt, as before
        await punch.record_punch_out(
            db, user, at=at(d, 18, 0), fresh=True, mode="web")
        await db.commit()
    (row,) = await day_row(world, "single", d)
    assert io(row) == (at(d, 9, 0), at(d, 18, 0))


async def test_offline_punch_out_replay_on_device_closed_row_is_duplicate(
        world, rules):
    await rules(offline_max_hours="72", selfie_required="0")
    y = datetime.now(timezone.utc).date() - timedelta(days=1)
    await feed(world, "perm", [at(y, 10, 0), at(y, 17, 0)])
    app = create_app()
    app.dependency_overrides[deps.verify_attendance] = lambda: None
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as c:
        r = await c.post("/api/v1/auth/login", data={
            "username": f"bio_perm_{world['sfx']}@t.com", "password": "x"})
        assert r.status_code == 200, r.text
        h = {"Authorization": f"Bearer {r.json()['access_token']}"}
        item = lambda when: {
            "client_uuid": uuid.uuid4().hex, "kind": "out",
            "captured_at": when.isoformat()}
        r = await c.post("/api/v1/attendance/offline-sync", headers=h, json={
            "punches": [item(at(y, 12, 0)), item(at(y, 17, 0))]})
    res = r.json()["results"]
    assert [x["status"] for x in res] == ["duplicate", "duplicate"], res
    assert all(x["attendance_id"] for x in res)
    (row,) = await day_row(world, "perm", y)
    assert io(row) == (at(y, 10, 0), at(y, 17, 0))


async def test_apply_pending_stamp_failure_is_a_conflict_not_an_abort(
        world, monkeypatch):
    d = date(2031, 7, 21)
    pin, ids = await _unmapped_taps(
        world, "mapq", d, [at(d, 9, 0), at(d, 13, 0), at(d, 18, 0)])
    real = bio.apply_punch

    async def boom(db, bp, **kw):
        if bp.id == ids[1]:
            raise RuntimeError("kaboom")
        return await real(db, bp, **kw)
    monkeypatch.setattr(bio, "apply_punch", boom)

    class FakeOrig(Exception):
        pass
    err = OperationalError("stmt", {}, FakeOrig(1213, "deadlock"))
    err.orig = FakeOrig(1213, "deadlock")
    real_commit = AsyncSession.commit

    async def commit(self):
        # the ERROR-stamping commit hits a deadlock
        if any(isinstance(o, BiometricPunch) and o.id == ids[1]
               and o.state == S.ERROR for o in self.dirty):
            raise err
        return await real_commit(self)
    monkeypatch.setattr(AsyncSession, "commit", commit)
    counts = await bio.apply_pending(SessionLocal, pin=pin)
    monkeypatch.setattr(AsyncSession, "commit", real_commit)
    assert counts == {S.APPLIED: 2, "conflict": 1}
    async with SessionLocal() as db:
        assert (await db.get(BiometricPunch, ids[0])).state == S.APPLIED
        assert (await db.get(BiometricPunch, ids[2])).state == S.APPLIED
        assert (await db.get(BiometricPunch, ids[1])).state == S.UNMAPPED
