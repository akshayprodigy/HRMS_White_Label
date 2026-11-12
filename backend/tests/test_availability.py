"""Availability & preferences (Roadmap v2 Phase 1B, Task 1)."""
import uuid
from datetime import date, time, timedelta, datetime, timezone
from types import SimpleNamespace as NS

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from _cleanup import purge_shift_templates
from app.api import deps
from app.core.config import settings
from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.main import create_app
from app.models.audit import AuditLog
from app.models.availability import EmployeeAvailability
from app.models.department import Department
from app.models.employee import Employee, EmployeeStatus
from app.models.notification import Notification
from app.models.roster import RosterEntry, RosterEntryHistory
from app.models.schedule_delegation import DelegationScope, ScheduleDelegation
from app.models.shift import ShiftTemplate
from app.models.user import User
from app.services.availability import AvailabilityDay, expand_availability

ROSTER = f"{settings.API_V1_STR}/roster"
PW = "test@12345"
TODAY = datetime.now(timezone.utc).date()
D = date(2030, 3, 4)  # Monday


def dd(n):
    return (D + timedelta(days=n)).isoformat()


def R(**kw):
    base = dict(user_id=1, kind="unavailable", weekday=None, specific_date=None,
                shift_template_id=None, valid_from=None, valid_to=None)
    base.update(kw)
    return NS(**base)


# ------------------------------ pure ------------------------------

def test_weekday_recurring_unbounded():
    out = expand_availability([R(weekday=0)], D, D + timedelta(days=13))
    assert set(out) == {(1, D), (1, D + timedelta(days=7))}
    assert out[(1, D)].unavailable_all_day


def test_weekday_bounds():
    out = expand_availability(
        [R(weekday=0, valid_from=D + timedelta(days=7),
           valid_to=D + timedelta(days=7))], D, D + timedelta(days=21))
    assert set(out) == {(1, D + timedelta(days=7))}


def test_specific_date_and_outside_window():
    r = R(specific_date=D + timedelta(days=2))
    assert set(expand_availability([r], D, D + timedelta(days=3))) == {
        (1, D + timedelta(days=2))}
    assert expand_availability([r], D, D + timedelta(days=1)) == {}


def test_template_vs_whole_day():
    out = expand_availability(
        [R(weekday=0, shift_template_id=5)], D, D)
    day = out[(1, D)]
    assert not day.unavailable_all_day
    assert day.blocks(5) and not day.blocks(6) and not day.blocks(None)
    whole = expand_availability([R(weekday=0)], D, D)[(1, D)]
    assert whole.blocks(6) and whole.blocks(None)


def test_preferred():
    out = expand_availability(
        [R(kind="preferred", weekday=0, shift_template_id=7)], D, D)
    day = out[(1, D)]
    assert day.preferred_templates == {7}
    assert not day.blocks(7)
    assert isinstance(day, AvailabilityDay)


# ------------------------------ API ------------------------------

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
    dept_x, dept_y = f"AX{sfx}", f"AY{sfx}"
    ids = {}
    try:
        async with SessionLocal() as db:
            def mk(tag, **kw):
                return User(email=f"av_{tag}_{sfx}@t.com", full_name=f"AV {tag}",
                            hashed_password=get_password_hash(PW),
                            is_active=True, **kw)
            deleg, e1, e2, e3 = mk("deleg"), mk("e1"), mk("e2"), mk("e3")
            admin = mk("admin", is_superuser=True)
            db.add_all([deleg, e1, e2, e3, admin])
            db.add_all([Department(name=dept_x), Department(name=dept_y)])
            t1 = ShiftTemplate(name=f"AVT1{sfx}", start_time=time(9), end_time=time(17))
            t2 = ShiftTemplate(name=f"AVT2{sfx}", start_time=time(14), end_time=time(22))
            t3 = ShiftTemplate(name=f"AVT3{sfx}", start_time=time(6), end_time=time(10),
                               is_active=False)
            db.add_all([t1, t2, t3])
            await db.commit()
            for tag, u, d in (("1", e1, dept_x), ("2", e2, dept_x), ("3", e3, dept_y)):
                db.add(Employee(
                    user_id=u.id, employee_id=f"AV{sfx}{tag}", department=d,
                    designation="Tester", date_of_joining=date(2020, 1, 1),
                    status=EmployeeStatus.ACTIVE))
            await db.commit()
            ids = {"deleg": deleg.id, "e1": e1.id, "e2": e2.id, "e3": e3.id,
                   "admin": admin.id, "t1": t1.id, "t2": t2.id, "t3": t3.id}
        yield {"ids": ids, "sfx": sfx,
               "deleg_email": f"av_deleg_{sfx}@t.com",
               "e1_email": f"av_e1_{sfx}@t.com",
               "e2_email": f"av_e2_{sfx}@t.com",
               "admin_email": f"av_admin_{sfx}@t.com"}
    finally:
        async with SessionLocal() as db:
            uids = list((await db.execute(select(User.id).where(
                User.email.like(f"av\\_%\\_{sfx}@t.com")))).scalars().all())
            await db.execute(delete(AuditLog).where(
                AuditLog.user_id.in_(uids), AuditLog.action.like("roster.%")))
            await db.execute(delete(EmployeeAvailability).where(
                EmployeeAvailability.user_id.in_(uids)))
            await db.execute(delete(RosterEntryHistory).where(
                RosterEntryHistory.employee_id.in_(uids)))
            await db.execute(delete(RosterEntry).where(
                RosterEntry.employee_id.in_(uids)))
            await db.execute(delete(Notification).where(
                Notification.user_id.in_(uids)))
            await db.execute(delete(ScheduleDelegation).where(
                ScheduleDelegation.grantee_id.in_(uids)))
            await db.execute(delete(Employee).where(Employee.user_id.in_(uids)))
            await db.execute(delete(Department).where(
                Department.name.in_([dept_x, dept_y])))
            await purge_shift_templates(
                db, [ids["t1"], ids["t2"], ids["t3"]])
            await db.execute(delete(User).where(User.id.in_(uids)))
            await db.commit()


async def _login(client, email):
    r = await client.post(f"{settings.API_V1_STR}/auth/login",
                          data={"username": email, "password": PW})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_crud_own_and_isolation(client, world):
    w = world
    h1 = await _login(client, w["e1_email"])
    h2 = await _login(client, w["e2_email"])
    r = await client.post(f"{ROSTER}/availability/my", headers=h1, json={
        "kind": "unavailable", "weekday": 0, "note": "gym"})
    assert r.status_code == 200, r.text
    rule = r.json()
    assert rule["user_id"] == w["ids"]["e1"] and rule["weekday"] == 0
    rid = rule["id"]
    r = await client.get(f"{ROSTER}/availability/my", headers=h1)
    assert [x["id"] for x in r.json()] == [rid]
    assert (await client.get(f"{ROSTER}/availability/my", headers=h2)).json() == []
    r = await client.patch(f"{ROSTER}/availability/my/{rid}", headers=h1,
                           json={"note": "swim", "shift_template_id": w["ids"]["t1"]})
    assert r.status_code == 200 and r.json()["note"] == "swim"
    assert r.json()["shift_template_id"] == w["ids"]["t1"]
    # switch to one-off date clears weekday
    r = await client.patch(f"{ROSTER}/availability/my/{rid}", headers=h1,
                           json={"specific_date": dd(2)})
    assert r.status_code == 200 and r.json()["weekday"] is None
    # other user cannot touch it
    assert (await client.patch(f"{ROSTER}/availability/my/{rid}", headers=h2,
                               json={"note": "x"})).status_code == 404
    assert (await client.delete(f"{ROSTER}/availability/my/{rid}",
                                headers=h2)).status_code == 404
    assert (await client.delete(f"{ROSTER}/availability/my/{rid}",
                                headers=h1)).status_code == 200
    assert (await client.get(f"{ROSTER}/availability/my", headers=h1)).json() == []


async def test_validation(client, world):
    w = world
    h = await _login(client, w["e1_email"])
    url = f"{ROSTER}/availability/my"
    t1 = w["ids"]["t1"]
    bad = [
        {"kind": "unavailable", "weekday": 0, "specific_date": dd(0)},
        {"kind": "unavailable"},
        {"kind": "preferred", "weekday": 0},
        {"kind": "bogus", "weekday": 0},
        {"kind": "unavailable", "weekday": 9},
        {"kind": "unavailable", "specific_date": dd(0), "valid_from": dd(0)},
        {"kind": "unavailable", "weekday": 0, "valid_from": dd(5), "valid_to": dd(1)},
        {"kind": "preferred", "weekday": 0, "shift_template_id": w["ids"]["t3"]},
        {"kind": "preferred", "weekday": 0, "shift_template_id": 2**31 - 1},
    ]
    for b in bad:
        r = await client.post(url, headers=h, json=b)
        assert r.status_code == 422, (b, r.status_code, r.text)
    ok = await client.post(url, headers=h, json={
        "kind": "preferred", "weekday": 0, "shift_template_id": t1})
    assert ok.status_code == 200
    # patch producing an invalid merged state
    r = await client.patch(f"{url}/{ok.json()['id']}", headers=h,
                           json={"shift_template_id": None, "kind": "preferred"})
    assert r.status_code == 422
    r = await client.patch(f"{url}/{ok.json()['id']}", headers=h,
                           json={"specific_date": dd(1), "weekday": 2})
    assert r.status_code == 422


async def test_max_rules(client, world):
    w = world
    h = await _login(client, w["e1_email"])
    async with SessionLocal() as db:
        db.add_all([EmployeeAvailability(
            user_id=w["ids"]["e1"], kind="unavailable", weekday=i % 7)
            for i in range(50)])
        await db.commit()
    r = await client.post(f"{ROSTER}/availability/my", headers=h, json={
        "kind": "unavailable", "weekday": 1})
    assert r.status_code == 400


async def test_scheduler_list_scoped(client, world):
    w = world
    async with SessionLocal() as db:
        db.add_all([
            EmployeeAvailability(user_id=w["ids"]["e1"], kind="unavailable", weekday=0),
            EmployeeAvailability(user_id=w["ids"]["e2"], kind="unavailable", weekday=1),
            EmployeeAvailability(user_id=w["ids"]["e3"], kind="unavailable", weekday=2),
            EmployeeAvailability(user_id=w["ids"]["e1"], kind="unavailable",
                                 specific_date=date(2031, 1, 1)),
        ])
        db.add(ScheduleDelegation(
            grantee_id=w["ids"]["deleg"], scope_type=DelegationScope.EMPLOYEES,
            employee_ids=[w["ids"]["e1"]], can_publish=False,
            valid_from=TODAY - timedelta(days=1)))
        await db.commit()
    q = f"?start={dd(0)}&end={dd(13)}"
    hd = await _login(client, w["deleg_email"])
    r = await client.get(f"{ROSTER}/availability{q}", headers=hd)
    assert r.status_code == 200, r.text
    assert {x["user_id"] for x in r.json()} == {w["ids"]["e1"]}
    assert len(r.json()) == 1  # out-of-window date rule filtered
    assert r.json()[0]["employee_name"] == "AV e1"
    ha = await _login(client, w["admin_email"])
    r = await client.get(f"{ROSTER}/availability{q}&department=AX{w['sfx']}", headers=ha)
    assert {x["user_id"] for x in r.json()} == {w["ids"]["e1"], w["ids"]["e2"]}
    r = await client.get(f"{ROSTER}/availability?start={dd(0)}&end={dd(100)}", headers=ha)
    assert r.status_code == 400
    # employee with no scope
    h1 = await _login(client, w["e1_email"])
    assert (await client.get(f"{ROSTER}/availability{q}", headers=h1)).status_code == 403


async def test_insights_unavailable_violation(client, world):
    w = world
    ha = await _login(client, w["admin_email"])
    async with SessionLocal() as db:
        db.add_all([
            EmployeeAvailability(user_id=w["ids"]["e1"], kind="unavailable", weekday=0),
            EmployeeAvailability(user_id=w["ids"]["e2"], kind="unavailable",
                                 weekday=0, shift_template_id=w["ids"]["t2"]),
        ])
        await db.commit()
    for emp in ("e1", "e2"):
        r = await client.post(f"{ROSTER}/entries", headers=ha, json={
            "employee_id": w["ids"][emp], "work_date": dd(0),
            "shift_template_id": w["ids"]["t1"], "status": "draft"})
        assert r.status_code == 200, r.text
    r = await client.get(f"{ROSTER}/insights?start={dd(0)}&end={dd(6)}"
                         f"&department=AX{w['sfx']}", headers=ha)
    assert r.status_code == 200, r.text
    un = [v for v in r.json()["violations"] if v["rule"] == "unavailable"]
    assert [(v["user_id"], v["work_date"]) for v in un] == [
        (w["ids"]["e1"], dd(0))]  # e2's rule is for t2 only


async def test_patch_switch_clears_other_fields(client, world):
    w = world
    h = await _login(client, w["e1_email"])
    url = f"{ROSTER}/availability/my"
    r = await client.post(url, headers=h, json={
        "kind": "unavailable", "weekday": 0,
        "valid_from": dd(0), "valid_to": dd(30)})
    assert r.status_code == 200, r.text
    rid = r.json()["id"]
    r = await client.patch(f"{url}/{rid}", headers=h, json={"specific_date": dd(2)})
    assert r.status_code == 200, r.text
    j = r.json()
    assert (j["weekday"], j["valid_from"], j["valid_to"]) == (None, None, None)
    assert j["specific_date"] == dd(2)
    r = await client.patch(f"{url}/{rid}", headers=h, json={"weekday": 3})
    assert r.status_code == 200, r.text
    assert r.json()["weekday"] == 3 and r.json()["specific_date"] is None


async def test_clear_template_on_preferred_422(client, world):
    w = world
    h = await _login(client, w["e1_email"])
    url = f"{ROSTER}/availability/my"
    r = await client.post(url, headers=h, json={
        "kind": "preferred", "weekday": 1, "shift_template_id": w["ids"]["t1"]})
    rid = r.json()["id"]
    r = await client.patch(f"{url}/{rid}", headers=h, json={"shift_template_id": None})
    assert r.status_code == 422


async def test_duplicates_409(client, world):
    w = world
    h = await _login(client, w["e1_email"])
    url = f"{ROSTER}/availability/my"
    body = {"kind": "unavailable", "weekday": 2}
    a = await client.post(url, headers=h, json=body)
    assert a.status_code == 200
    assert (await client.post(url, headers=h, json=body)).status_code == 409
    # note differences do not make a rule distinct
    assert (await client.post(url, headers=h, json={**body, "note": "x"})).status_code == 409
    b = await client.post(url, headers=h, json={"kind": "unavailable", "weekday": 3})
    assert b.status_code == 200
    r = await client.patch(f"{url}/{b.json()['id']}", headers=h, json={"weekday": 2})
    assert r.status_code == 409
    # another user may have the same rule
    h2 = await _login(client, w["e2_email"])
    assert (await client.post(url, headers=h2, json=body)).status_code == 200
