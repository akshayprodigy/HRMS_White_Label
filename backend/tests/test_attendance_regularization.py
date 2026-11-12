"""Attendance regularization API tests. Uses a far-past month (2019) that no
real payroll run locks; every row created is removed in finally."""
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core.config import settings
from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.main import create_app
from app.models.attendance import Attendance
from app.models.attendance_regularization import AttendanceRegularization
from app.models.audit import AuditLog
from app.models.notification import Notification
from app.models.payroll import PayrollRun, PayrollRunStatus
from app.models.user import User

BASE = f"{settings.API_V1_STR}/attendance/regularizations"
PW = "test@12345"
WD = date(2019, 3, 12)
LOCKED_WD = date(2019, 4, 10)


def _dt(d: date, h: int, m: int = 0) -> str:
    return datetime(d.year, d.month, d.day, h, m, tzinfo=timezone.utc).isoformat()


@pytest.fixture
async def client():
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def world():
    """manager, employee (reports to manager), stranger; cleaned afterwards."""
    sfx = uuid.uuid4().hex[:8]
    async with SessionLocal() as db:
        mgr = User(email=f"reg_mgr_{sfx}@t.com", full_name="Reg Mgr",
                   hashed_password=get_password_hash(PW), is_active=True)
        stranger = User(email=f"reg_str_{sfx}@t.com", full_name="Reg Str",
                        hashed_password=get_password_hash(PW), is_active=True)
        db.add_all([mgr, stranger])
        await db.flush()
        emp = User(email=f"reg_emp_{sfx}@t.com", full_name="Reg Emp",
                   manager_id=mgr.id,
                   hashed_password=get_password_hash(PW), is_active=True)
        db.add(emp)
        await db.commit()
        ids = {"mgr": mgr.id, "emp": emp.id, "str": stranger.id}
        emails = {"mgr": mgr.email, "emp": emp.email, "str": stranger.email}
    try:
        yield ids, emails
    finally:
        async with SessionLocal() as db:
            uids = list(ids.values())
            reg_ids = (await db.execute(select(AttendanceRegularization.id)
                       .where(AttendanceRegularization.user_id.in_(uids)))
                       ).scalars().all()
            await db.execute(delete(AuditLog).where(
                AuditLog.resource_type == "attendance_regularization",
                AuditLog.resource_id.in_([str(i) for i in reg_ids])))
            await db.execute(delete(Notification).where(
                Notification.user_id.in_(uids)))
            await db.execute(delete(AttendanceRegularization).where(
                AttendanceRegularization.user_id.in_(uids)))
            await db.execute(delete(Attendance).where(
                Attendance.user_id.in_(uids)))
            await db.execute(delete(PayrollRun).where(
                PayrollRun.month == LOCKED_WD.month,
                PayrollRun.year == LOCKED_WD.year))
            await db.execute(delete(User).where(User.id.in_(uids)))
            await db.commit()


async def _login(client, email: str, password: str = PW) -> dict:
    r = await client.post(f"{settings.API_V1_STR}/auth/login",
                          data={"username": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _admin(client) -> dict:
    return await _login(client, "admin@gmail.com")


def _body(wd=WD, out=True, reason="Forgot to punch"):
    b = {"work_date": wd.isoformat(), "requested_punch_in": _dt(wd, 9),
         "reason": reason}
    if out:
        b["requested_punch_out"] = _dt(wd, 18)
    return b


async def _att(uid):
    async with SessionLocal() as db:
        return (await db.execute(select(Attendance).where(
            Attendance.user_id == uid, Attendance.work_date == WD)
        )).scalars().first()


async def test_create_ok_and_my_list(client, world):
    ids, em = world
    h = await _login(client, em["emp"])
    r = await client.post(f"{BASE}/", json=_body(), headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "pending" and d["user_id"] == ids["emp"]
    assert d["requester_name"] == "Reg Emp"
    my = await client.get(f"{BASE}/my", headers=h)
    assert [x["id"] for x in my.json()] == [d["id"]]


async def test_validation_errors(client, world):
    _, em = world
    h = await _login(client, em["emp"])
    fut = date.today() + timedelta(days=2)
    assert (await client.post(f"{BASE}/", json=_body(fut), headers=h)
            ).status_code == 422
    bad = _body()
    bad["requested_punch_out"] = _dt(WD, 8)
    assert (await client.post(f"{BASE}/", json=bad, headers=h)
            ).status_code == 422
    assert (await client.post(f"{BASE}/", json=_body(reason="   "),
                              headers=h)).status_code == 422
    off = _body()
    off["requested_punch_in"] = _dt(WD + timedelta(days=5), 9)
    off.pop("requested_punch_out")
    assert (await client.post(f"{BASE}/", json=off, headers=h)
            ).status_code == 422


async def test_duplicate_pending_409(client, world):
    _, em = world
    h = await _login(client, em["emp"])
    assert (await client.post(f"{BASE}/", json=_body(), headers=h)
            ).status_code == 200
    assert (await client.post(f"{BASE}/", json=_body(), headers=h)
            ).status_code == 409


async def test_manager_approves_creates_attendance(client, world):
    ids, em = world
    he = await _login(client, em["emp"])
    hm = await _login(client, em["mgr"])
    rid = (await client.post(f"{BASE}/", json=_body(), headers=he)).json()["id"]
    q = await client.get(f"{BASE}/", headers=hm)
    assert [x["id"] for x in q.json()] == [rid]
    r = await client.post(f"{BASE}/{rid}/decide",
                          json={"approve": True}, headers=hm)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved"
    att = await _att(ids["emp"])
    assert att and att.mode == "regularized"
    assert att.edited_by_id == ids["mgr"]
    assert r.json()["attendance_id"] == att.id
    # decided -> cannot decide again
    assert (await client.post(f"{BASE}/{rid}/decide",
            json={"approve": True}, headers=hm)).status_code == 409
    async with SessionLocal() as db:
        a = (await db.execute(select(AuditLog).where(
            AuditLog.resource_type == "attendance_regularization",
            AuditLog.resource_id == str(rid)))).scalars().first()
        assert a and a.action == "APPROVE_ATTENDANCE_REGULARIZATION"


async def test_approve_updates_existing_row(client, world):
    ids, em = world
    async with SessionLocal() as db:
        db.add(Attendance(user_id=ids["emp"], mode="office", work_date=WD,
                          captured_at=datetime(2019, 3, 12, 11, tzinfo=timezone.utc)))
        await db.commit()
    he = await _login(client, em["emp"])
    ha = await _admin(client)
    created = (await client.post(f"{BASE}/", json=_body(out=False),
                                 headers=he)).json()
    assert created["attendance_id"] is not None
    r = await client.post(f"{BASE}/{created['id']}/decide",
                          json={"approve": True}, headers=ha)
    assert r.status_code == 200, r.text
    att = await _att(ids["emp"])
    assert att.mode == "office"
    assert att.captured_at.hour == 9
    assert att.edited_by_id is not None


async def test_cannot_decide_own(client, world):
    _, em = world
    he = await _login(client, em["emp"])
    rid = (await client.post(f"{BASE}/", json=_body(), headers=he)).json()["id"]
    r = await client.post(f"{BASE}/{rid}/decide",
                          json={"approve": True}, headers=he)
    assert r.status_code == 403


async def test_unrelated_user_cannot_decide_or_see(client, world):
    _, em = world
    he = await _login(client, em["emp"])
    hs = await _login(client, em["str"])
    rid = (await client.post(f"{BASE}/", json=_body(), headers=he)).json()["id"]
    assert (await client.post(f"{BASE}/{rid}/decide",
            json={"approve": True}, headers=hs)).status_code == 403
    assert (await client.get(f"{BASE}/", headers=hs)).json() == []


async def test_reject_requires_note(client, world):
    _, em = world
    he = await _login(client, em["emp"])
    hm = await _login(client, em["mgr"])
    rid = (await client.post(f"{BASE}/", json=_body(), headers=he)).json()["id"]
    assert (await client.post(f"{BASE}/{rid}/decide",
            json={"approve": False}, headers=hm)).status_code == 422
    r = await client.post(f"{BASE}/{rid}/decide",
                          json={"approve": False, "note": "no proof"},
                          headers=hm)
    assert r.status_code == 200 and r.json()["status"] == "rejected"


async def test_cancel(client, world):
    _, em = world
    he = await _login(client, em["emp"])
    hs = await _login(client, em["str"])
    rid = (await client.post(f"{BASE}/", json=_body(), headers=he)).json()["id"]
    assert (await client.post(f"{BASE}/{rid}/cancel", headers=hs)
            ).status_code == 403
    r = await client.post(f"{BASE}/{rid}/cancel", headers=he)
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert (await client.post(f"{BASE}/{rid}/cancel", headers=he)
            ).status_code == 409


async def test_locked_month_409(client, world):
    _, em = world
    he = await _login(client, em["emp"])
    async with SessionLocal() as db:
        db.add(PayrollRun(month=LOCKED_WD.month, year=LOCKED_WD.year,
                          status=PayrollRunStatus.FINALIZED))
        await db.commit()
    r = await client.post(f"{BASE}/", json=_body(LOCKED_WD), headers=he)
    assert r.status_code == 409
