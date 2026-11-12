"""On-call / standby roster (Roadmap v2 Phase 2, Task 5)."""
import uuid
from datetime import date, time, timedelta, datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.api import deps
from app.core.config import settings
from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.main import create_app
from app.models.department import Department
from app.models.employee import Employee, EmployeeStatus
from app.models.notification import Notification
from app.models.on_call import OnCallAssignment, OnCallRule
from app.models.payroll import PayrollRun, PayrollRunStatus
from app.models.shift_allowance import ShiftAllowanceEntry
from app.models.user import User
from app.services import on_call as oc

API = f"{settings.API_V1_STR}/roster/on-call"
PW = "test@12345"
TODAY = datetime.now(timezone.utc).date()
D = TODAY + timedelta(days=10)


def dd(n=0):
    return (D + timedelta(days=n)).isoformat()


def test_duration_and_amount_pure():
    assert oc.duration_minutes(time(9), time(17)) == 480
    assert oc.duration_minutes(time(22), time(6)) == 480      # overnight
    assert oc.duration_minutes(time(8, 0), time(8, 0)) == 1440
    assert oc.is_overnight(time(22), time(6)) and not oc.is_overnight(time(9), time(17))
    flat = OnCallRule(payout_model="flat_per_day", flat_amount=500, hourly_rate=0)
    hourly = OnCallRule(payout_model="hourly", flat_amount=0, hourly_rate=62.5)
    assert oc.compute_amount(flat, 90) == 500.0
    assert oc.compute_amount(hourly, 480) == 500.0
    assert oc.compute_amount(hourly, 90) == 93.75


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
    dx, dy = f"CX{sfx}", f"CY{sfx}"
    try:
        async with SessionLocal() as db:
            def mk(tag, **kw):
                return User(email=f"oc_{tag}_{sfx}@t.com", full_name=f"OC {tag}",
                            hashed_password=get_password_hash(PW),
                            is_active=True, **kw)
            us = {t: mk(t) for t in ("e1", "e2", "e4", "e5", "sx", "sy")}
            us["admin"] = mk("admin", is_superuser=True)
            db.add_all(us.values())
            db.add_all([Department(name=dx), Department(name=dy)])
            await db.commit()
            for tag, dept, st in (
                ("e1", dx, EmployeeStatus.ACTIVE), ("e2", dx, EmployeeStatus.ACTIVE),
                ("e4", dy, EmployeeStatus.ACTIVE), ("e5", dx, EmployeeStatus.INACTIVE),
            ):
                db.add(Employee(user_id=us[tag].id, employee_id=f"OC{sfx}{tag}",
                                department=dept, designation="T",
                                date_of_joining=date(2020, 1, 1), status=st))
            await db.execute(Department.__table__.update().where(
                Department.name == dx).values(head_user_id=us["sx"].id))
            await db.execute(Department.__table__.update().where(
                Department.name == dy).values(head_user_id=us["sy"].id))
            await db.commit()
            ids = {t: u.id for t, u in us.items()}
        yield {"ids": ids, "sfx": sfx, "dx": dx,
               "email": lambda t: f"oc_{t}_{sfx}@t.com"}
    finally:
        async with SessionLocal() as db:
            uids = list((await db.execute(select(User.id).where(
                User.email.like(f"oc\\_%\\_{sfx}@t.com")))).scalars().all())
            await db.execute(delete(Notification).where(
                Notification.user_id.in_(uids)))
            await db.execute(delete(ShiftAllowanceEntry).where(
                ShiftAllowanceEntry.user_id.in_(uids)))
            await db.execute(delete(OnCallAssignment).where(
                OnCallAssignment.user_id.in_(uids)))
            await db.execute(delete(OnCallRule).where(
                OnCallRule.name.like(f"ocr{sfx}%")))
            await db.execute(Department.__table__.update().where(
                Department.name.in_([dx, dy])).values(head_user_id=None))
            await db.execute(delete(Employee).where(Employee.user_id.in_(uids)))
            await db.execute(delete(Department).where(Department.name.in_([dx, dy])))
            await db.execute(delete(User).where(User.id.in_(uids)))
            await db.commit()


async def login(client, world, tag):
    r = await client.post(f"{settings.API_V1_STR}/auth/login",
                          data={"username": world["email"](tag), "password": PW})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def mk_rule(client, h, world, suffix="a", **kw):
    body = {"name": f"ocr{world['sfx']}{suffix}", "payout_model": "flat_per_day",
            "flat_amount": 500.0, **kw}
    r = await client.post(f"{API}/rules", json=body, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def body(world, tag, rule_id, day=0, st="09:00", en="17:00", **kw):
    return {"user_id": world["ids"][tag], "work_date": dd(day),
            "start_time": st, "end_time": en, "rule_id": rule_id, **kw}


async def entry_of(uid, d):
    async with SessionLocal() as db:
        return (await db.execute(select(ShiftAllowanceEntry).where(
            ShiftAllowanceEntry.user_id == uid,
            ShiftAllowanceEntry.work_date == d,
            ShiftAllowanceEntry.kind == "on_call"))).scalars().first()


async def notifs(uid):
    async with SessionLocal() as db:
        return [n.title for n in (await db.execute(select(Notification).where(
            Notification.user_id == uid))).scalars().all()]


async def test_rules_admin_only_and_validation(client, world):
    ha = await login(client, world, "admin")
    hs = await login(client, world, "sx")
    r = await client.post(f"{API}/rules", json={
        "name": f"ocr{world['sfx']}z", "flat_amount": 1}, headers=hs)
    assert r.status_code == 403
    rule = await mk_rule(client, ha, world)
    dup = await client.post(f"{API}/rules", json={
        "name": rule["name"], "flat_amount": 9}, headers=ha)
    assert dup.status_code == 409
    bad = await client.post(f"{API}/rules", json={
        "name": f"ocr{world['sfx']}b", "payout_model": "hourly"}, headers=ha)
    assert bad.status_code == 400  # hourly needs a rate
    assert (await client.post(f"{API}/rules", json={
        "name": f"ocr{world['sfx']}c", "payout_model": "weekly",
        "flat_amount": 1}, headers=ha)).status_code == 422
    # head may list rules; employee without scope may not
    r = await client.get(f"{API}/rules", headers=hs)
    assert r.status_code == 200 and any(x["id"] == rule["id"] for x in r.json())
    he = await login(client, world, "e1")
    assert (await client.get(f"{API}/rules", headers=he)).status_code == 403
    # rule in use cannot be deleted
    a = await client.post(API, json=body(world, "e1", rule["id"]), headers=hs)
    assert a.status_code == 200, a.text
    assert (await client.delete(
        f"{API}/rules/{rule['id']}", headers=ha)).status_code == 409
    assert (await client.patch(
        f"{API}/rules/{rule['id']}", json={"is_active": False},
        headers=hs)).status_code == 403
    unused = await mk_rule(client, ha, world, "u")
    assert (await client.delete(
        f"{API}/rules/{unused['id']}", headers=ha)).status_code == 200


async def test_create_amounts_notify_dup_scope(client, world):
    ha = await login(client, world, "admin")
    hs = await login(client, world, "sx")
    flat = await mk_rule(client, ha, world, "f")
    hourly = await mk_rule(client, ha, world, "h", payout_model="hourly",
                           flat_amount=0, hourly_rate=62.5)
    e1 = world["ids"]["e1"]
    r = await client.post(API, json=body(world, "e1", flat["id"]), headers=hs)
    assert r.status_code == 200, r.text
    assert r.json()["amount"] == 500.0 and r.json()["is_overnight"] is False
    assert (await entry_of(e1, D)).minutes == 480
    assert "On-call duty assigned" in await notifs(e1)
    # hourly overnight 22:00-06:00 = 8h * 62.5 = 500
    r2 = await client.post(API, json=body(
        world, "e2", hourly["id"], st="22:00", en="06:00"), headers=hs)
    assert r2.status_code == 200, r2.text
    assert r2.json()["is_overnight"] is True and r2.json()["amount"] == 500.0
    # duplicate user/date
    assert (await client.post(API, json=body(
        world, "e1", hourly["id"]), headers=hs)).status_code == 409
    # scope: head X cannot manage dept Y; admin can
    assert (await client.post(API, json=body(
        world, "e4", flat["id"]), headers=hs)).status_code == 403
    assert (await client.post(API, json=body(
        world, "e4", flat["id"]), headers=ha)).status_code == 200
    # inactive employee, inactive rule
    assert (await client.post(API, json=body(
        world, "e5", flat["id"]), headers=ha)).status_code == 400
    await client.patch(f"{API}/rules/{hourly['id']}",
                       json={"is_active": False}, headers=ha)
    assert (await client.post(API, json=body(
        world, "e2", hourly["id"], day=1), headers=ha)).status_code == 400


async def test_update_delete_sync_and_rule_resync(client, world):
    ha = await login(client, world, "admin")
    hs = await login(client, world, "sx")
    rule = await mk_rule(client, ha, world)
    e1 = world["ids"]["e1"]
    a = (await client.post(API, json=body(world, "e1", rule["id"]),
                           headers=hs)).json()
    hourly = await mk_rule(client, ha, world, "h", payout_model="hourly",
                           flat_amount=0, hourly_rate=100)
    r = await client.patch(f"{API}/{a['id']}", json={
        "rule_id": hourly["id"], "start_time": "10:00", "end_time": "14:00"},
        headers=hs)
    assert r.status_code == 200, r.text
    assert r.json()["amount"] == 400.0
    ent = await entry_of(e1, D)
    assert ent.amount == 400.0 and ent.minutes == 240 and ent.rule_id == hourly["id"]
    # rule rate change resyncs unpaid entries
    r = await client.patch(f"{API}/rules/{hourly['id']}",
                           json={"hourly_rate": 150}, headers=ha)
    assert r.status_code == 200 and r.json()["entries_refreshed"] == 1
    assert (await entry_of(e1, D)).amount == 600.0
    # delete removes entry + notifies
    assert (await client.delete(f"{API}/{a['id']}", headers=hs)).status_code == 200
    assert await entry_of(e1, D) is None
    assert "On-call duty removed" in await notifs(e1)
    assert (await client.delete(f"{API}/{a['id']}", headers=hs)).status_code == 404


async def test_paid_entries_frozen(client, world):
    ha = await login(client, world, "admin")
    rule = await mk_rule(client, ha, world)
    e1 = world["ids"]["e1"]
    a = (await client.post(API, json=body(world, "e1", rule["id"]),
                           headers=ha)).json()
    async with SessionLocal() as db:   # simulate payroll stamping
        run = PayrollRun(month=11, year=2016, status=PayrollRunStatus.DRAFT)
        db.add(run)
        await db.flush()
        run_id = run.id
        e = (await db.execute(select(ShiftAllowanceEntry).where(
            ShiftAllowanceEntry.user_id == e1))).scalar_one()
        e.payroll_run_id = run_id
        await db.commit()
    try:
        assert (await client.delete(f"{API}/{a['id']}", headers=ha)).status_code == 409
        assert (await client.patch(f"{API}/{a['id']}", json={
            "end_time": "20:00"}, headers=ha)).status_code == 409
        r = await client.patch(f"{API}/rules/{rule['id']}",
                               json={"flat_amount": 9999}, headers=ha)
        assert r.status_code == 200 and r.json()["entries_refreshed"] == 0
        ent = await entry_of(e1, D)
        assert ent.amount == 500.0 and ent.payroll_run_id == run_id
        listed = (await client.get(API, params={"start": dd(), "end": dd()},
                                   headers=ha)).json()
        assert [x["paid"] for x in listed if x["id"] == a["id"]] == [True]
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(ShiftAllowanceEntry).where(
                ShiftAllowanceEntry.user_id == e1))
            await db.execute(delete(PayrollRun).where(PayrollRun.id == run_id))
            await db.commit()


async def test_past_date_policy(client, world):
    ha = await login(client, world, "admin")
    hs = await login(client, world, "sx")
    rule = await mk_rule(client, ha, world)
    past = lambda n: (TODAY - timedelta(days=n)).isoformat()  # noqa: E731
    b = lambda n, tag="e1": {**body(world, tag, rule["id"]), "work_date": past(n)}  # noqa: E731
    # head: within 7 days ok, beyond refused
    assert (await client.post(API, json=b(3), headers=hs)).status_code == 200
    r = await client.post(API, json=b(9, "e2"), headers=hs)
    assert r.status_code == 400 and "7 days" in r.json()["error"]["message"]
    # admin may go further back when the month is not processed...
    d_old = date(2016, 6, 15)
    ok = await client.post(API, json={**b(0, "e2"), "work_date": d_old.isoformat()},
                           headers=ha)
    assert ok.status_code == 200, ok.text
    # ...but not once payroll locked attendance for that month
    async with SessionLocal() as db:
        run = PayrollRun(month=5, year=2016, status=PayrollRunStatus.LEAVES_LOCKED)
        db.add(run)
        await db.commit()
        run_id = run.id
    try:
        r = await client.post(API, json={**b(0, "e1"), "work_date": "2016-05-10"},
                              headers=ha)
        assert r.status_code == 409
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(PayrollRun).where(PayrollRun.id == run_id))
            await db.commit()


async def test_list_window_scope_and_my(client, world):
    ha = await login(client, world, "admin")
    hs = await login(client, world, "sx")
    rule = await mk_rule(client, ha, world)
    await client.post(API, json=body(world, "e1", rule["id"]), headers=ha)
    await client.post(API, json=body(world, "e4", rule["id"]), headers=ha)
    r = await client.get(API, params={"start": dd(), "end": dd()}, headers=hs)
    assert r.status_code == 200
    assert {x["user_id"] for x in r.json()} == {world["ids"]["e1"]}
    r = await client.get(API, params={
        "start": dd(), "end": dd(70)}, headers=hs)
    assert r.status_code == 400
    assert (await client.get(API, params={"start": dd(), "end": dd()},
                             headers=await login(client, world, "e1"))
            ).status_code == 403
    me = await client.get(f"{API.replace('/on-call', '/my/on-call')}",
                          headers=await login(client, world, "e1"))
    assert me.status_code == 200
    assert [x["work_date"] for x in me.json()] == [dd()]
    assert "user_id" not in me.json()[0]
    other = await client.get(f"{API.replace('/on-call', '/my/on-call')}",
                             headers=await login(client, world, "e2"))
    assert other.json() == []


async def test_hourly_equal_times_rejected_flat_allows_24h(client, world):
    ha = await login(client, world, "admin")
    hourly = await mk_rule(client, ha, world, "h", payout_model="hourly",
                           flat_amount=0, hourly_rate=10)
    flat = await mk_rule(client, ha, world, "f")
    r = await client.post(API, json=body(world, "e1", hourly["id"],
                                         st="08:00", en="08:00"), headers=ha)
    assert r.status_code == 400
    r = await client.post(API, json=body(world, "e1", flat["id"],
                                         st="08:00", en="08:00"), headers=ha)
    assert r.status_code == 200 and r.json()["is_overnight"] is True
    a = r.json()
    # switching that 24h flat day to an hourly rule is also refused
    r = await client.patch(f"{API}/{a['id']}", json={"rule_id": hourly["id"]},
                           headers=ha)
    assert r.status_code == 400
    assert (await entry_of(world["ids"]["e1"], D)).minutes == 1440
