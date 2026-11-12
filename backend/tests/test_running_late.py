"""Running-late notices (Roadmap v2 Phase 2, Task 2)."""
import uuid
from datetime import date, datetime, time, timedelta, timezone

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
from app.models.coverage_gap import CoverageGap
from app.models.employee import Employee, EmployeeStatus
from app.models.late_notice import LateNotice
from app.models.no_show import NoShowAlert
from app.models.notification import Notification
from app.models.roster import RosterEntry, RosterEntryHistory, RosterStatus
from app.models.shift import ShiftTemplate
from app.models.system import SystemSetting
from app.models.user import User
from app.services import live_ops
from app.services.live_ops import LiveStatus as S, classify, no_show_job

PW = "test@12345"
UTC = timezone.utc
D = date(2030, 6, 10)
RULE_KEY = "schedule.no_show_minutes"
URL = f"{settings.API_V1_STR}/roster/my/running-late"


def dt(h, m=0, day=D):
    return datetime(day.year, day.month, day.day, h, m, tzinfo=UTC)


# ---------------- pure classify ----------------

START, END = dt(9), dt(17)
LATE_CASES = [
    # name, now, eta, punch_in, no_show, expected
    ("before start is upcoming", dt(8, 50), dt(10), None, 30, S.UPCOMING),
    ("started, eta ahead", dt(9, 45), dt(10), None, 30, S.RUNNING_LATE),
    ("past plain threshold but within eta+threshold", dt(10, 20), dt(10), None, 30,
     S.RUNNING_LATE),
    ("eta+threshold exactly is no_show", dt(10, 30), dt(10), None, 30, S.NO_SHOW),
    ("no_show 0 -> only until eta", dt(10, 1), dt(10), None, 0, S.NOT_ARRIVED),
    ("no_show 0 before eta", dt(9, 59), dt(10), None, 0, S.RUNNING_LATE),
    ("punched in wins", dt(9, 45), dt(10), dt(9, 40), 30, S.ON_SHIFT),
    ("after shift end is no_show", dt(17, 30), dt(17), None, 240, S.NO_SHOW),
    ("no notice unchanged", dt(9, 20), None, None, 30, S.NOT_ARRIVED),
]


@pytest.mark.parametrize("name,now,eta,pin,ns,exp", LATE_CASES,
                         ids=[c[0] for c in LATE_CASES])
def test_classify_late_eta(name, now, eta, pin, ns, exp):
    st, _ = classify(now=now, start=START, end=END, grace_in=10, punch_in=pin,
                     punch_out=None, on_leave=False, no_show_minutes=ns,
                     late_eta=eta)
    assert st == exp


def test_classify_on_leave_beats_late():
    assert classify(now=dt(9, 45), start=START, end=END, grace_in=10,
                    punch_in=None, punch_out=None, on_leave=True,
                    no_show_minutes=30, late_eta=dt(10))[0] == S.ON_LEAVE


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
    async with SessionLocal() as db:
        prior = await db.get(SystemSetting, RULE_KEY)
        prior_val = (prior.value, prior.description) if prior else None
    try:
        async with SessionLocal() as db:
            def mk(tag, **kw):
                return User(email=f"rl_{tag}_{sfx}@t.com", full_name=f"RL {tag} {sfx}",
                            hashed_password=get_password_hash(PW),
                            is_active=True, **kw)
            mgr = mk("mgr")
            db.add(mgr)
            await db.flush()
            names = ["emp", "none", "punched", "night", "fut"]
            us = {n: mk(n) for n in names}
            for u in us.values():
                u.manager_id = mgr.id
            db.add_all(us.values())
            t_day = ShiftTemplate(name=f"RD{sfx}", start_time=time(0, 0),
                                  end_time=time(23, 59))
            t_run = ShiftTemplate(name=f"RN{sfx}", start_time=time(0, 0),
                                  end_time=time(23, 59), is_overnight=True)
            t_fut = ShiftTemplate(name=f"RF{sfx}", start_time=time(9),
                                  end_time=time(17), grace_in_minutes=10)
            db.add_all([t_day, t_run, t_fut])
            await db.commit()
            for n, u in us.items():
                db.add(Employee(
                    user_id=u.id, employee_id=f"RL{sfx}{n}", department="RLD",
                    location="RLA", designation="T",
                    date_of_joining=date(2020, 1, 1),
                    status=EmployeeStatus.ACTIVE))
            await db.commit()
            ids = {n: u.id for n, u in us.items()}
            ids.update(mgr=mgr.id, t_day=t_day.id, t_run=t_run.id, t_fut=t_fut.id)
        async with SessionLocal() as db:
            await _set_rule(db, 30)
        yield {"ids": ids, "sfx": sfx}
    finally:
        async with SessionLocal() as db:
            uids = list((await db.execute(select(User.id).where(
                User.email.like(f"rl\\_%\\_{sfx}@t.com")))).scalars().all())
            tids = list((await db.execute(select(ShiftTemplate.id).where(
                ShiftTemplate.name.in_([f"RD{sfx}", f"RN{sfx}", f"RF{sfx}"])))
            ).scalars().all())
            await purge_gap_notifications(db, tids)
            await db.execute(delete(CoverageGap).where(
                CoverageGap.shift_template_id.in_(tids)))
            await db.execute(delete(LateNotice).where(LateNotice.user_id.in_(uids)))
            await db.execute(delete(NoShowAlert).where(NoShowAlert.user_id.in_(uids)))
            await db.execute(delete(Attendance).where(Attendance.user_id.in_(uids)))
            await db.execute(delete(RosterEntryHistory).where(
                RosterEntryHistory.employee_id.in_(uids)))
            await db.execute(delete(RosterEntry).where(RosterEntry.employee_id.in_(uids)))
            await db.execute(delete(Notification).where(Notification.user_id.in_(uids)))
            await db.execute(delete(Notification).where(
                Notification.message.like(f"%{sfx}%")))
            await db.execute(delete(Employee).where(Employee.user_id.in_(uids)))
            await purge_shift_templates(db, tids)
            await db.execute(delete(User).where(User.id.in_(uids)))
            await db.execute(delete(SystemSetting).where(SystemSetting.key == RULE_KEY))
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


async def _login(client, email):
    r = await client.post(f"{settings.API_V1_STR}/auth/login",
                          data={"username": email, "password": PW})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _roster(uid, d, tpl):
    async with SessionLocal() as db:
        db.add(RosterEntry(employee_id=uid, work_date=d, shift_template_id=tpl,
                           status=RosterStatus.PUBLISHED))
        await db.commit()


def _soon(minutes=1):
    return (datetime.now(UTC) + timedelta(minutes=minutes)).isoformat()


async def _notices(uid):
    async with SessionLocal() as db:
        return list((await db.execute(select(LateNotice).where(
            LateNotice.user_id == uid))).scalars().all())


async def _notes(uid):
    async with SessionLocal() as db:
        return list((await db.execute(select(Notification).where(
            Notification.user_id == uid))).scalars().all())


async def test_post_no_shift_400(client, world):
    h = await _login(client, f"rl_none_{world['sfx']}@t.com")
    r = await client.post(URL, headers=h, json={"minutes_late": 15})
    assert r.status_code == 400
    r = await client.get(URL, headers=h)
    assert r.status_code == 200 and r.json()["can_post"] is False


async def test_post_punched_400(client, world):
    i = world["ids"]
    today = datetime.now(UTC).date()
    await _roster(i["punched"], today, i["t_day"])
    async with SessionLocal() as db:
        db.add(Attendance(user_id=i["punched"], mode="web", work_date=today,
                          captured_at=datetime.now(UTC) - timedelta(minutes=1),
                          shift_template_id=i["t_day"]))
        await db.commit()
    h = await _login(client, f"rl_punched_{world['sfx']}@t.com")
    r = await client.post(URL, headers=h, json={"expected_at": _soon()})
    assert r.status_code == 400 and "punched" in r.text
    assert (await client.get(URL, headers=h)).json()["can_post"] is False


async def test_validation_shapes(client, world):
    i = world["ids"]
    await _roster(i["emp"], datetime.now(UTC).date(), i["t_day"])
    h = await _login(client, f"rl_emp_{world['sfx']}@t.com")
    for body in ({}, {"minutes_late": 4}, {"minutes_late": 241},
                 {"minutes_late": 10, "expected_at": _soon()}):
        r = await client.post(URL, headers=h, json=body)
        assert r.status_code == 422, (body, r.text)


async def test_post_window_and_upsert_and_notify(client, world):
    i, sfx = world["ids"], world["sfx"]
    today = datetime.now(UTC).date()
    await _roster(i["emp"], today, i["t_day"])
    h = await _login(client, f"rl_emp_{sfx}@t.com")
    # outside the shift window
    for eta in (datetime.now(UTC) + timedelta(days=1),
                datetime.now(UTC) - timedelta(days=1)):
        r = await client.post(URL, headers=h, json={"expected_at": eta.isoformat()})
        assert r.status_code == 400 and "within your shift" in r.text
    assert await _notices(i["emp"]) == []
    # ok
    r = await client.post(URL, headers=h, json={
        "expected_at": _soon(2), "reason": "Traffic"})
    assert r.status_code == 200, r.text
    n = r.json()["notice"]
    assert n["reason"] == "Traffic" and n["work_date"] == today.isoformat()
    assert len(await _notes(i["mgr"])) == 1
    # upsert
    r = await client.post(URL, headers=h, json={"expected_at": _soon(3)})
    assert r.status_code == 200
    rows = await _notices(i["emp"])
    assert len(rows) == 1 and rows[0].reason is None
    assert len(await _notes(i["mgr"])) == 2  # one per post
    g = (await client.get(URL, headers=h)).json()
    assert g["notice"]["eta_hhmm"] == rows[0].expected_at.strftime("%H:%M")
    assert g["can_post"] is True
    # board shows it
    async with SessionLocal() as db:
        board = {r.user_id: r for r in await live_ops.live_board(
            db, [i["emp"]], datetime.now(UTC))}
    row = board[i["emp"]]
    assert row.status == S.RUNNING_LATE and row.late_notice_eta is not None
    # delete clears
    r = await client.delete(URL, headers=h)
    assert r.status_code == 200 and r.json()["notice"] is None
    assert await _notices(i["emp"]) == []


async def test_minutes_late_computes_eta(client, world):
    i = world["ids"]
    await _roster(i["emp"], datetime.now(UTC).date(), i["t_day"])
    h = await _login(client, f"rl_emp_{world['sfx']}@t.com")
    before = datetime.now(UTC)
    r = await client.post(URL, headers=h, json={"minutes_late": 5})
    if before.hour == 23 and before.minute >= 50:
        pytest.skip("too close to end of UTC day")
    assert r.status_code == 200, r.text
    eta = datetime.fromisoformat(r.json()["notice"]["expected_at"])
    assert timedelta(minutes=4) <= eta - before <= timedelta(minutes=6)


async def test_overnight_from_yesterday(client, world):
    i = world["ids"]
    yday = datetime.now(UTC).date() - timedelta(days=1)
    await _roster(i["night"], yday, i["t_run"])
    h = await _login(client, f"rl_night_{world['sfx']}@t.com")
    r = await client.post(URL, headers=h, json={"expected_at": _soon(2)})
    assert r.status_code == 200, r.text
    assert r.json()["notice"]["work_date"] == yday.isoformat()
    assert (await _notices(i["night"]))[0].work_date == yday


# ---------------- board + job (frozen now) ----------------


async def _seed_future(w, eta):
    i = w["ids"]
    await _roster(i["fut"], D, i["t_fut"])
    async with SessionLocal() as db:
        db.add(LateNotice(user_id=i["fut"], work_date=D, expected_at=eta,
                          reason="Bus broke down"))
        await db.commit()


async def _alerts(uid):
    async with SessionLocal() as db:
        return list((await db.execute(select(NoShowAlert).where(
            NoShowAlert.user_id == uid))).scalars().all())


async def test_job_skips_while_running_late_then_alerts(world):
    i = world["ids"]
    await _seed_future(world, dt(10))
    for now in (dt(9, 45), dt(10, 20), dt(10, 29)):
        async with SessionLocal() as db:
            res = await no_show_job(db, now=now, user_ids=[i["fut"]])
        assert res["alerts_created"] == 0, now
        assert await _alerts(i["fut"]) == []
    async with SessionLocal() as db:
        board = {r.user_id: r for r in await live_ops.live_board(db, [i["fut"]], dt(10, 20))}
    r = board[i["fut"]]
    assert r.status == S.RUNNING_LATE
    assert r.late_notice_eta == dt(10) and r.late_notice_reason == "Bus broke down"
    async with SessionLocal() as db:
        res = await no_show_job(db, now=dt(10, 30), user_ids=[i["fut"]])
    assert res["alerts_created"] == 1
    assert len(await _alerts(i["fut"])) == 1
    async with SessionLocal() as db:
        board = {r.user_id: r for r in await live_ops.live_board(db, [i["fut"]], dt(10, 30))}
    assert board[i["fut"]].status == S.NO_SHOW and board[i["fut"]].alerted


async def test_punch_after_notice_clears_late(world):
    i = world["ids"]
    await _seed_future(world, dt(10))
    async with SessionLocal() as db:
        db.add(Attendance(user_id=i["fut"], mode="web", work_date=D,
                          captured_at=dt(9, 50), shift_template_id=i["t_fut"]))
        await db.commit()
        board = {r.user_id: r for r in await live_ops.live_board(db, [i["fut"]], dt(10, 5))}
    r = board[i["fut"]]
    assert r.status == S.ON_SHIFT and r.late_notice_eta is None


async def test_live_endpoint_row_fields(client, world):
    i, sfx = world["ids"], world["sfx"]
    await _roster(i["emp"], datetime.now(UTC).date(), i["t_day"])
    h = await _login(client, f"rl_emp_{sfx}@t.com")
    r = await client.post(URL, headers=h, json={
        "expected_at": _soon(2), "reason": "Rain"})
    assert r.status_code == 200
    async with SessionLocal() as db:
        mgr = await db.get(User, i["mgr"])
        mgr.is_superuser = True
        await db.commit()
    mh = await _login(client, f"rl_mgr_{sfx}@t.com")
    body = (await client.get(f"{settings.API_V1_STR}/roster/live", headers=mh,
                             params={"department": "RLD"})).json()
    row = next(x for x in body["rows"] if x["user_id"] == i["emp"])
    assert row["status"] == "running_late" and row["late_notice_reason"] == "Rain"
    assert row["late_notice_eta"] is not None
    assert body["counts"]["running_late"] >= 1


async def test_not_blocked_by_attendance_gate(world):
    """The endpoint is for people who have NOT punched in, so the attendance
    gate must not apply (while other roster routes still 403)."""
    i, sfx = world["ids"], world["sfx"]
    await _roster(i["emp"], datetime.now(UTC).date(), i["t_day"])
    app = create_app()  # no verify_attendance override
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as c:
        h = await _login(c, f"rl_emp_{sfx}@t.com")
        assert (await c.get(URL, headers=h)).status_code == 200
        r = await c.post(URL, headers=h, json={"expected_at": _soon(2)})
        assert r.status_code == 200, r.text
        assert (await c.get(f"{settings.API_V1_STR}/roster/my/week",
                            headers=h)).status_code == 403
