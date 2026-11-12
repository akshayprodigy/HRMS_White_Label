"""Live operations board + no-show detection (Roadmap v2 Phase 1B, Task 9)."""
import uuid
from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from _cleanup import purge_gap_notifications, purge_shift_templates
from app.api import deps
from app.core.config import settings
from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.main import create_app
from app.models.attendance import Attendance
from app.models.department import Department
from app.models.hr import HolidayCalendar
from app.models.leave import HalfDaySession, LeaveRequest, LeaveStatus, LeaveType
from app.models.employee import Employee, EmployeeStatus
from app.models.no_show import NoShowAlert
from app.models.coverage_gap import CoverageGap
from app.models.notification import Notification
from app.models.roster import RosterEntry, RosterEntryHistory, RosterStatus
from app.models.schedule_delegation import DelegationScope, ScheduleDelegation
from app.models.shift import EmployeeShiftAssignment, ShiftTemplate
from app.models.system import SystemSetting
from app.models.user import User
from app.services import live_ops
from app.services.time_rules import TIME_RULE_DEFAULTS
from app.services.live_ops import LiveStatus as S, classify, no_show_job

PW = "test@12345"
RULE_KEY = "schedule.no_show_minutes"
UTC = timezone.utc
D = date(2030, 6, 10)


def dt(h, m=0, day=D):
    return datetime(day.year, day.month, day.day, h, m, tzinfo=UTC)


# ---------------- pure classifier ----------------

START, END = dt(9), dt(17)
CASES = [
    # name, now, punch_in, punch_out, on_leave, no_show, expected
    ("upcoming", dt(8, 59), None, None, False, 30, (S.UPCOMING, 0)),
    ("at start is not_arrived", dt(9), None, None, False, 30, (S.NOT_ARRIVED, 0)),
    ("29m after start", dt(9, 29), None, None, False, 30, (S.NOT_ARRIVED, 0)),
    ("exactly threshold is no_show", dt(9, 30), None, None, False, 30, (S.NO_SHOW, 0)),
    ("no_show 0 never flags within shift", dt(15), None, None, False, 0, (S.NOT_ARRIVED, 0)),
    ("after end, never punched", dt(18), None, None, False, 0, (S.NO_SHOW, 0)),
    ("on shift on time", dt(10), dt(9, 5), None, False, 30, (S.ON_SHIFT, 0)),
    ("grace boundary (10m) not late", dt(10), dt(9, 10), None, False, 30, (S.ON_SHIFT, 0)),
    ("one minute past grace", dt(10), dt(9, 11), None, False, 30, (S.ON_SHIFT, 1)),
    ("punched after no-show threshold", dt(11), dt(10, 40), None, False, 30, (S.ON_SHIFT, 90)),
    ("completed", dt(18), dt(9), dt(17), False, 30, (S.COMPLETED, 0)),
    ("on leave", dt(10), None, None, True, 30, (S.ON_LEAVE, 0)),
    ("on leave beats not-arrived", dt(9, 45), None, None, True, 30, (S.ON_LEAVE, 0)),
]


@pytest.mark.parametrize("name,now,pin,pout,leave,ns,exp", CASES,
                         ids=[c[0] for c in CASES])
def test_classify_table(name, now, pin, pout, leave, ns, exp):
    assert classify(now=now, start=START, end=END, grace_in=10, punch_in=pin,
                    punch_out=pout, on_leave=leave, no_show_minutes=ns) == exp


def test_classify_no_shift():
    kw = dict(now=dt(12), start=None, end=None, grace_in=0, on_leave=False,
              no_show_minutes=30)
    assert classify(punch_in=None, punch_out=None, **kw) == (S.OFF, 0)
    assert classify(punch_in=dt(11), punch_out=None, **kw) == (S.ON_SHIFT, 0)
    assert classify(punch_in=dt(8), punch_out=dt(11), **kw) == (S.COMPLETED, 0)


def test_classify_overnight_still_running():
    # Shift 22:00 -> 06:00 next day, evaluated at 02:00 next day.
    s, e = dt(22), dt(6, day=D + timedelta(days=1))
    now = dt(2, day=D + timedelta(days=1))
    assert classify(now=now, start=s, end=e, grace_in=10, punch_in=dt(22, 5),
                    punch_out=None, on_leave=False,
                    no_show_minutes=30) == (S.ON_SHIFT, 0)
    assert classify(now=now, start=s, end=e, grace_in=10, punch_in=None,
                    punch_out=None, on_leave=False,
                    no_show_minutes=30) == (S.NO_SHOW, 0)


def test_shift_bounds_overnight():
    t = SimpleNamespace(start_time=time(22), end_time=time(6), is_overnight=True)
    assert live_ops.shift_bounds(t, D) == (dt(22), dt(6, day=D + timedelta(days=1)))


# ---------------- DB world ----------------


@pytest.fixture
async def client():
    app = create_app()
    app.dependency_overrides[deps.verify_attendance] = lambda: None
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as c:
        yield c


@pytest.fixture
async def world():
    sfx = uuid.uuid4().hex[:8]
    dx, dy = f"LX{sfx}", f"LY{sfx}"
    async with SessionLocal() as db:
        prior = await db.get(SystemSetting, RULE_KEY)
        prior_val = (prior.value, prior.description) if prior else None
    try:
        async with SessionLocal() as db:
            def mk(tag, **kw):
                return User(email=f"lo_{tag}_{sfx}@t.com", full_name=f"LO {tag} {sfx}",
                            hashed_password=get_password_hash(PW),
                            is_active=True, **kw)
            mgr, head = mk("mgr"), mk("head")
            admin = mk("admin", is_superuser=True)
            db.add_all([mgr, head, admin])
            await db.flush()
            names = ["day", "night", "noshow", "leave", "off", "inact", "othr"]
            us = {n: mk(n) for n in names}
            us["day"].manager_id = mgr.id
            us["noshow"].manager_id = mgr.id
            us["inact"].is_active = False
            db.add_all(us.values())
            db.add_all([Department(name=dx, head_user_id=head.id),
                        Department(name=dy)])
            t_day = ShiftTemplate(name=f"LD{sfx}", start_time=time(9),
                                  end_time=time(17), grace_in_minutes=10)
            t_night = ShiftTemplate(name=f"LN{sfx}", start_time=time(22),
                                    end_time=time(6), is_overnight=True)
            db.add_all([t_day, t_night])
            await db.commit()
            for n, u in us.items():
                db.add(Employee(
                    user_id=u.id, employee_id=f"LO{sfx}{n}",
                    department=dy if n == "othr" else dx,
                    location="LocB" if n == "othr" else "LocA",
                    designation="T", date_of_joining=date(2020, 1, 1),
                    status=EmployeeStatus.ACTIVE))
            await db.commit()
            ids = {n: u.id for n, u in us.items()}
            ids.update(mgr=mgr.id, head=head.id, admin=admin.id,
                       t_day=t_day.id, t_night=t_night.id)
        yield {"ids": ids, "sfx": sfx, "dx": dx, "dy": dy}
    finally:
        async with SessionLocal() as db:
            uids = list((await db.execute(select(User.id).where(
                User.email.like(f"lo\\_%\\_{sfx}@t.com")))).scalars().all())
            gtids = list((await db.execute(select(ShiftTemplate.id).where(
                ShiftTemplate.name.in_([f"LD{sfx}", f"LN{sfx}"])))).scalars().all())
            await purge_gap_notifications(db, gtids)
            await db.execute(delete(CoverageGap).where(
                CoverageGap.shift_template_id.in_(gtids)))
            await db.execute(delete(NoShowAlert).where(NoShowAlert.user_id.in_(uids)))
            await db.execute(delete(Attendance).where(Attendance.user_id.in_(uids)))
            await db.execute(delete(RosterEntryHistory).where(
                RosterEntryHistory.employee_id.in_(uids)))
            await db.execute(delete(RosterEntry).where(RosterEntry.employee_id.in_(uids)))
            await db.execute(delete(Notification).where(Notification.user_id.in_(uids)))
            # fallback notifications to real roster admins mention our names
            await db.execute(delete(Notification).where(
                Notification.message.like(f"%{sfx}%")))
            await db.execute(delete(ScheduleDelegation).where(
                ScheduleDelegation.grantee_id.in_(uids)))
            await db.execute(delete(Employee).where(Employee.user_id.in_(uids)))
            await db.execute(delete(Department).where(Department.name.in_([dx, dy])))
            tids = (await db.execute(select(ShiftTemplate.id).where(
                ShiftTemplate.name.in_([f"LD{sfx}", f"LN{sfx}"])))).scalars().all()
            await purge_gap_notifications(db, tids)
            await purge_shift_templates(db, tids)
            await db.execute(delete(User).where(User.id.in_(uids)))
            await db.execute(delete(HolidayCalendar).where(
                HolidayCalendar.name == f"LOH{sfx}"))
            await db.execute(delete(LeaveRequest).where(
                LeaveRequest.employee_id.in_(uids)))
            await db.execute(delete(LeaveType).where(LeaveType.name == f"LOL{sfx}"))
            await db.execute(delete(EmployeeShiftAssignment).where(
                EmployeeShiftAssignment.employee_id.in_(uids)))
            # restore any pre-existing setting; delete only if we created it
            await db.execute(delete(SystemSetting).where(
                SystemSetting.key == RULE_KEY))
            if prior_val is not None:
                db.add(SystemSetting(key=RULE_KEY, value=prior_val[0],
                                     description=prior_val[1]))
            await db.commit()


async def _set_rule(db, value):
    row = await db.get(SystemSetting, RULE_KEY)
    if row:
        row.value = value
    else:
        db.add(SystemSetting(key=RULE_KEY, value=value, description="t"))
    await db.commit()


async def _roster(db, uid, d, tpl):
    db.add(RosterEntry(employee_id=uid, work_date=d, shift_template_id=tpl,
                       status=RosterStatus.PUBLISHED))


async def _seed(w, now):
    """day: 09-17 today, punched in 09:05; noshow: 09-17 today, nothing;
    night: overnight from yesterday, punched in; off: week-off; othr: day shift."""
    today, yday = now.date(), now.date() - timedelta(days=1)
    i = w["ids"]
    async with SessionLocal() as db:
        await _roster(db, i["day"], today, i["t_day"])
        await _roster(db, i["noshow"], today, i["t_day"])
        await _roster(db, i["othr"], today, i["t_day"])
        await _roster(db, i["inact"], today, i["t_day"])
        await _roster(db, i["night"], yday, i["t_night"])
        db.add(RosterEntry(employee_id=i["off"], work_date=today,
                           is_week_off=True, status=RosterStatus.PUBLISHED))
        db.add(Attendance(user_id=i["day"], mode="web", work_date=today,
                          captured_at=datetime.combine(today, time(9, 25), UTC),
                          shift_template_id=i["t_day"]))
        db.add(Attendance(user_id=i["night"], mode="web", work_date=yday,
                          captured_at=datetime.combine(yday, time(22, 0), UTC),
                          shift_template_id=i["t_night"]))
        await db.commit()


NOW = datetime(2030, 6, 10, 10, 0, tzinfo=UTC)


async def _board(w, now=NOW):
    ids = [v for k, v in w["ids"].items() if k in
           ("day", "night", "noshow", "leave", "off", "inact", "othr")]
    async with SessionLocal() as db:
        return {r.user_id: r for r in await live_ops.live_board(db, ids, now)}


async def test_loader_statuses(world):
    now = datetime(2030, 6, 10, 2, 0, tzinfo=UTC)  # night shift still running
    await _seed(world, NOW)
    i = world["ids"]
    rows = await _board(world, now)
    assert i["inact"] not in rows
    assert rows[i["night"]].status == S.ON_SHIFT
    assert rows[i["night"]].work_date == date(2030, 6, 9)
    assert rows[i["off"]].status == S.OFF
    assert rows[i["leave"]].status == S.OFF  # no shift at all
    rows = await _board(world, NOW)  # 10:00
    # night shift ended 06:00 -> falls to today's (no shift) -> off
    assert rows[i["night"]].status == S.OFF
    assert rows[i["day"]].status == S.ON_SHIFT and rows[i["day"]].late_minutes == 15
    assert rows[i["noshow"]].status == S.NO_SHOW
    assert rows[i["noshow"]].start_hhmm == "09:00"


async def test_loader_on_leave(world):
    await _seed(world, NOW)
    i = world["ids"]
    # Build via the service query shape: patch approved_leave_days instead of
    # depending on the leave table's required columns.
    from unittest import mock
    with mock.patch.object(live_ops.roster_svc, "approved_leave_days",
                           new=mock.AsyncMock(return_value={(i["noshow"], NOW.date())})):
        rows = await _board(world)
    assert rows[i["noshow"]].status == S.ON_LEAVE


async def test_loader_constant_queries(world):
    from sqlalchemy import event
    await _seed(world, NOW)
    ids = [world["ids"][k] for k in ("day", "noshow", "othr", "off")]
    counts = []
    for sub in (ids[:1], ids):
        async with SessionLocal() as db:
            n = [0]
            event.listen(db.sync_session.get_bind(), "before_cursor_execute",
                         lambda *a, n=n: n.__setitem__(0, n[0] + 1))
            await live_ops.live_board(db, sub, NOW)
            counts.append(n[0])
    assert counts[0] == counts[1], counts


def _emp_ids(w):
    return [w["ids"][k] for k in ("day", "night", "noshow", "leave", "off", "inact", "othr")]


async def _alerts(w):
    async with SessionLocal() as db:
        return list((await db.execute(select(NoShowAlert).where(
            NoShowAlert.user_id.in_(list(w["ids"].values()))))).scalars().all())


async def _notes(uid):
    async with SessionLocal() as db:
        return list((await db.execute(select(Notification).where(
            Notification.user_id == uid))).scalars().all())


async def test_job_idempotent_notifies_manager(world):
    await _seed(world, NOW)
    i = world["ids"]
    async with SessionLocal() as db:
        res = await no_show_job(db, now=NOW, user_ids=_emp_ids(world))
    assert res["alerts_created"] >= 1
    mine = [a for a in await _alerts(world)]
    assert sorted(a.user_id for a in mine) == sorted([i["noshow"], i["othr"]])
    assert len(await _notes(i["noshow"])) == 1
    mgr_notes = await _notes(i["mgr"])
    assert len(mgr_notes) == 1 and "LO noshow" in mgr_notes[0].message
    async with SessionLocal() as db:
        res2 = await no_show_job(db, now=NOW, user_ids=_emp_ids(world))
    assert len(await _alerts(world)) == 2
    assert len(await _notes(i["mgr"])) == 1  # no duplicate notification
    # board marks it
    rows = await _board(world)
    assert rows[i["noshow"]].alerted is True and rows[i["day"]].alerted is False


async def test_job_delegate_and_fallback_and_inactive(world):
    await _seed(world, NOW)
    i = world["ids"]
    # `othr` has no manager, no delegate, in dept dy -> fall back to roster
    # admins (our admin). Make `othr` a no-show too (already: no punch).
    # `noshow` also gets a delegate covering them; manager made inactive.
    async with SessionLocal() as db:
        db.add(ScheduleDelegation(
            grantee_id=i["head"], scope_type=DelegationScope.EMPLOYEES,
            employee_ids=[i["noshow"]], valid_from=NOW.date() - timedelta(days=1)))
        mgr = await db.get(User, i["mgr"])
        mgr.is_active = False
        await db.commit()
        await no_show_job(db, now=NOW, user_ids=_emp_ids(world))
    assert await _notes(i["mgr"]) == []           # inactive: skipped
    assert len([n for n in await _notes(i["head"])
                if n.title == "Employee no-show"]) == 1   # delegate notified
    assert len(await _notes(i["admin"])) >= 1      # othr fell back to admins
    head_msgs = [n.message for n in await _notes(i["head"])]
    assert all("LO othr" not in m for m in head_msgs)
    assert any("LO noshow" in m for m in head_msgs)


async def test_job_disabled_when_zero(world):
    await _seed(world, NOW)
    async with SessionLocal() as db:
        await _set_rule(db, "0")
        assert await no_show_job(db, now=NOW) == {"skipped": "disabled"}
    assert await _alerts(world) == []


def test_job_registered():
    from app.services.scheduler import REGISTRY
    spec = REGISTRY["roster_no_show_alerts"]
    assert spec.default_cadence_cron == "*/5 * * * *"


async def test_time_rule_validation():
    from app.services.time_rules import get_schedule_rules, set_time_rules
    async with SessionLocal() as db:
        if await db.get(SystemSetting, RULE_KEY) is None:
            assert (await get_schedule_rules(db))["no_show_minutes"] == int(
                TIME_RULE_DEFAULTS[RULE_KEY][0])
        with pytest.raises(ValueError):
            await set_time_rules(db, {"schedule.no_show_minutes": "241"})


# ---------------- endpoint ----------------


async def _login(client, email):
    r = await client.post(f"{settings.API_V1_STR}/auth/login",
                          data={"username": email, "password": PW})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_endpoint_scope_and_filters(client, world):
    today = datetime.now(UTC).date()
    i, sfx = world["ids"], world["sfx"]
    await _seed(world, datetime.now(UTC))
    url = f"{settings.API_V1_STR}/roster/live"
    admin = await _login(client, f"lo_admin_{sfx}@t.com")
    r = await client.get(url, headers=admin, params={"department": world["dx"]})
    assert r.status_code == 200, r.text
    body = r.json()
    got = {row["user_id"] for row in body["rows"]}
    assert i["day"] in got and i["othr"] not in got and i["inact"] not in got
    assert sum(body["counts"].values()) == len(body["rows"])
    assert set(body["counts"]) == {s.value for s in S}
    r = await client.get(url, headers=admin, params={"location": "LocB"})
    assert {row["user_id"] for row in r.json()["rows"]} >= {i["othr"]}
    # head of dx sees only dx
    head = await _login(client, f"lo_head_{sfx}@t.com")
    r = await client.get(url, headers=head)
    assert r.status_code == 200
    got = {row["user_id"] for row in r.json()["rows"]}
    assert i["day"] in got and i["othr"] not in got
    # unscoped user -> 403
    e = await _login(client, f"lo_day_{sfx}@t.com")
    assert (await client.get(url, headers=e)).status_code == 403
    assert (await client.get(url)).status_code in (401, 403)


# ---------------- review follow-ups ----------------

SUN = date(2030, 6, 9)  # Sunday; D (06-10) is Monday


async def _assign(uid, tpl, effective_from=date(2030, 1, 1)):
    async with SessionLocal() as db:
        db.add(EmployeeShiftAssignment(
            employee_id=uid, shift_template_id=tpl,
            effective_from=effective_from))
        await db.commit()


async def _holiday(w, d):
    async with SessionLocal() as db:
        db.add(HolidayCalendar(name=f"LOH{w['sfx']}", date=d, location="All",
                               is_optional=False))
        await db.commit()


async def _only(w, uid, now):
    async with SessionLocal() as db:
        return (await live_ops.live_board(db, [uid], now))[0]


async def test_holiday_assignment_is_off(world):
    i = world["ids"]
    await _assign(i["leave"], i["t_day"])
    await _holiday(world, D)
    r = await _only(world, i["leave"], NOW)
    assert r.status == S.OFF and r.shift_name is None


async def test_holiday_with_roster_shift_still_expected(world):
    i = world["ids"]
    await _holiday(world, D)
    async with SessionLocal() as db:
        await _roster(db, i["leave"], D, i["t_day"])
        await db.commit()
    r = await _only(world, i["leave"], NOW)
    assert r.status == S.NO_SHOW  # roster is explicit


async def test_assignment_without_weekly_offs_on_default_off_day(world):
    i = world["ids"]
    async with SessionLocal() as db:
        t = await db.get(ShiftTemplate, i["t_day"])
        assert not t.weekly_offs
    await _assign(i["leave"], i["t_day"])
    # Sunday 10:00: default off day -> OFF; Monday 10:00 -> expected.
    assert (await _only(world, i["leave"], dt(10, day=SUN))).status == S.OFF
    assert (await _only(world, i["leave"], NOW)).status == S.NO_SHOW


async def _leave(w, uid, d, half):
    async with SessionLocal() as db:
        lt = (await db.execute(select(LeaveType).where(
            LeaveType.name == f"LOL{w['sfx']}"))).scalars().first()
        if lt is None:
            lt = LeaveType(name=f"LOL{w['sfx']}")
            db.add(lt)
            await db.flush()
        db.add(LeaveRequest(
            employee_id=uid, leave_type_id=lt.id, start_date=d, end_date=d,
            is_half_day=half, half_day_session=HalfDaySession.MORNING if half else None,
            reason="t", status=LeaveStatus.APPROVED, created_by_user_id=uid))
        await db.commit()


async def test_half_day_leave_not_alerted(world):
    await _seed(world, NOW)
    i = world["ids"]
    await _leave(world, i["noshow"], D, True)
    rows = await _board(world)
    r = rows[i["noshow"]]
    assert r.status == S.NOT_ARRIVED and r.half_day_leave is True
    async with SessionLocal() as db:
        await no_show_job(db, now=NOW, user_ids=_emp_ids(world))
    assert i["noshow"] not in [a.user_id for a in await _alerts(world)]


async def test_full_day_leave_not_alerted(world):
    await _seed(world, NOW)
    i = world["ids"]
    await _leave(world, i["noshow"], D, False)
    assert (await _board(world))[i["noshow"]].status == S.ON_LEAVE
    async with SessionLocal() as db:
        await no_show_job(db, now=NOW, user_ids=_emp_ids(world))
    assert i["noshow"] not in [a.user_id for a in await _alerts(world)]


async def test_job_skips_ended_shifts(world):
    await _seed(world, NOW)
    late = dt(18)  # day shift ended 17:00, nobody punched
    async with SessionLocal() as db:
        res = await no_show_job(db, now=late, user_ids=_emp_ids(world))
    assert res["alerts_created"] == 0
    rows = await _board(world, late)
    assert rows[world["ids"]["noshow"]].status == S.NO_SHOW  # board still shows it


async def test_job_alerts_overnight_from_yesterday(world):
    i = world["ids"]
    now = dt(2, day=D)  # 02:00; night shift 22:00 (06-09) -> 06:00 still running
    async with SessionLocal() as db:
        await _roster(db, i["night"], SUN, i["t_night"])
        await db.commit()
        res = await no_show_job(db, now=now, user_ids=[i["night"]])
    assert res["alerts_created"] == 1
    a = (await _alerts(world))[0]
    assert a.user_id == i["night"] and a.work_date == SUN


def test_threshold_uses_max_of_grace():
    # no_show_minutes=5 but grace_in=10 -> not a no-show at 9:05..9:09
    kw = dict(start=START, end=END, grace_in=10, punch_in=None, punch_out=None,
              on_leave=False, no_show_minutes=5)
    assert classify(now=dt(9, 9), **kw)[0] == S.NOT_ARRIVED
    assert classify(now=dt(9, 10), **kw)[0] == S.NO_SHOW
