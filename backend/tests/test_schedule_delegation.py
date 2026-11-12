"""Scheduling delegation tests (Roadmap v2 Phase 1A). DB-backed; every row
created is removed in fixture teardown."""
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core.config import settings
from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.main import create_app
from app.models.audit import AuditLog
from app.models.department import Department
from app.models.employee import Employee, EmployeeStatus
from app.models.notification import Notification
from app.models.schedule_delegation import DelegationScope, ScheduleDelegation
from app.models.user import User
from app.services import roster as svc

BASE = f"{settings.API_V1_STR}/roster/delegations"
PW = "test@12345"
TODAY = datetime.now(timezone.utc).date()


@pytest.fixture
async def client():
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def world():
    sfx = uuid.uuid4().hex[:8]
    dept_x, dept_y, loc = f"DX{sfx}", f"DY{sfx}", f"LOC{sfx}"
    async with SessionLocal() as db:
        def mk(tag, **kw):
            return User(email=f"sd_{tag}_{sfx}@t.com", full_name=f"SD {tag}",
                        hashed_password=get_password_hash(PW),
                        is_active=True, **kw)
        deleg, e1, e2, stranger = mk("deleg"), mk("e1"), mk("e2"), mk("str")
        db.add_all([deleg, e1, e2, stranger])
        await db.flush()
        rep = mk("rep", manager_id=deleg.id)
        db.add(rep)
        db.add_all([Department(name=dept_x), Department(name=dept_y)])
        await db.flush()
        for tag, u, d, lc in (("1", e1, dept_x, loc), ("2", e2, dept_y, None),
                              ("r", rep, dept_y, None)):
            db.add(Employee(
                user_id=u.id, employee_id=f"SD{sfx}{tag}", department=d,
                designation="Tester", date_of_joining=date(2020, 1, 1),
                status=EmployeeStatus.ACTIVE, location=lc,
            ))
        await db.commit()
        ids = {"deleg": deleg.id, "e1": e1.id, "e2": e2.id,
               "str": stranger.id, "rep": rep.id}
    w = {"ids": ids, "dx": dept_x, "dy": dept_y, "loc": loc,
         "email": f"sd_deleg_{sfx}@t.com"}
    try:
        yield w
    finally:
        async with SessionLocal() as db:
            uids = list(ids.values())
            dids = (await db.execute(select(ScheduleDelegation.id).where(
                ScheduleDelegation.grantee_id.in_(uids)))).scalars().all()
            await db.execute(delete(AuditLog).where(
                AuditLog.resource_type == "schedule_delegation",
                AuditLog.resource_id.in_([str(i) for i in dids])))
            await db.execute(delete(Notification).where(
                Notification.user_id.in_(uids)))
            await db.execute(delete(ScheduleDelegation).where(
                ScheduleDelegation.grantee_id.in_(uids)))
            await db.execute(delete(Employee).where(Employee.user_id.in_(uids)))
            await db.execute(delete(Department).where(
                Department.name.in_([dept_x, dept_y])))
            await db.execute(delete(User).where(User.id.in_(uids)))
            await db.commit()


async def _grant(w, **kw):
    kw.setdefault("valid_from", TODAY - timedelta(days=1))
    kw.setdefault("employee_ids", [])
    async with SessionLocal() as db:
        d = ScheduleDelegation(grantee_id=w["ids"]["deleg"], **kw)
        db.add(d)
        await db.commit()
        return d.id


async def _user(uid):
    async with SessionLocal() as db:
        return (await db.execute(select(User).where(User.id == uid))).scalars().one()


async def _can_manage(w, target):
    async with SessionLocal() as db:
        u = await db.get(User, w["ids"]["deleg"])
        return await svc.can_manage_employee(db, u, w["ids"][target])


async def test_department_delegation(world):
    await _grant(world, scope_type=DelegationScope.DEPARTMENT, scope_value=world["dx"])
    assert await _can_manage(world, "e1") is True
    assert await _can_manage(world, "e2") is False
    assert await _can_manage(world, "str") is False


async def test_employees_list_delegation(world):
    await _grant(world, scope_type=DelegationScope.EMPLOYEES,
                 employee_ids=[world["ids"]["e2"], world["ids"]["str"]])
    async with SessionLocal() as db:
        u = await db.get(User, world["ids"]["deleg"])
        assert await svc.delegated_user_ids(db, u) == {
            world["ids"]["e2"], world["ids"]["str"]}


async def test_location_delegation(world):
    await _grant(world, scope_type=DelegationScope.LOCATION, scope_value=world["loc"])
    assert await _can_manage(world, "e1") is True
    assert await _can_manage(world, "e2") is False


async def test_team_delegation(world):
    await _grant(world, scope_type=DelegationScope.TEAM)
    async with SessionLocal() as db:
        u = await db.get(User, world["ids"]["deleg"])
        assert await svc.delegated_user_ids(db, u) == {world["ids"]["rep"]}


async def test_inactive_delegations_grant_nothing(world):
    await _grant(world, scope_type=DelegationScope.DEPARTMENT, scope_value=world["dx"],
                 valid_to=TODAY - timedelta(days=1))  # expired
    await _grant(world, scope_type=DelegationScope.DEPARTMENT, scope_value=world["dx"],
                 valid_from=TODAY + timedelta(days=3))  # future
    await _grant(world, scope_type=DelegationScope.DEPARTMENT, scope_value=world["dx"],
                 revoked_at=datetime.now(timezone.utc))  # revoked
    assert await _can_manage(world, "e1") is False
    async with SessionLocal() as db:
        u = await db.get(User, world["ids"]["deleg"])
        assert await svc.active_delegations(db, u) == []
        # the future one becomes active on its start date
        assert len(await svc.active_delegations(
            db, u, TODAY + timedelta(days=3))) == 1


async def test_can_publish_for_flag_and_admin(world):
    await _grant(world, scope_type=DelegationScope.DEPARTMENT, scope_value=world["dx"])
    e1 = world["ids"]["e1"]
    async with SessionLocal() as db:
        u = await db.get(User, world["ids"]["deleg"])
        assert await svc.can_publish_for(db, u, e1) is False
        assert await svc.can_approve_changes_for(db, u, e1) is False
    await _grant(world, scope_type=DelegationScope.EMPLOYEES, employee_ids=[e1],
                 can_publish=True, can_approve_changes=True)
    async with SessionLocal() as db:
        u = await db.get(User, world["ids"]["deleg"])
        assert await svc.can_publish_for(db, u, e1) is True
        assert await svc.can_approve_changes_for(db, u, e1) is True
        assert await svc.can_publish_for(db, u, world["ids"]["e2"]) is False
        admin = (await db.execute(select(User).where(
            User.email == "admin@gmail.com"))).scalars().one()
        assert await svc.can_publish_for(db, admin, e1) is True


async def test_scoped_employees_for_pure_delegate(world):
    async with SessionLocal() as db:
        u = await db.get(User, world["ids"]["deleg"])
        assert await svc.scoped_employees(db, u) == []
    await _grant(world, scope_type=DelegationScope.DEPARTMENT, scope_value=world["dx"])
    async with SessionLocal() as db:
        u = await db.get(User, world["ids"]["deleg"])
        emps = await svc.scoped_employees(db, u)
        assert [e.user_id for e in emps] == [world["ids"]["e1"]]


# ----------------------------- API -----------------------------

async def _login(client, email):
    r = await client.post(f"{settings.API_V1_STR}/auth/login",
                          data={"username": email, "password": PW})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _body(w, **kw):
    b = {"grantee_id": w["ids"]["deleg"], "scope_type": "department",
         "scope_value": w["dx"], "valid_from": TODAY.isoformat(),
         "can_publish": True}
    b.update(kw)
    return b


async def test_non_admin_forbidden(client, world):
    h = await _login(client, world["email"])
    assert (await client.post(f"{BASE}/", json=_body(world), headers=h)
            ).status_code == 403
    assert (await client.get(f"{BASE}/", headers=h)).status_code == 403
    assert (await client.get(f"{BASE}/my", headers=h)).status_code == 200


async def test_create_revoke_flow(client, world):
    admin = await _login(client, "admin@gmail.com")
    h = await _login(client, world["email"])
    r = await client.post(f"{BASE}/", json=_body(world), headers=admin)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["covered_count"] == 1 and d["grantee_name"] == "SD deleg"
    my = await client.get(f"{BASE}/my", headers=h)
    assert [x["id"] for x in my.json()] == [d["id"]]
    lst = await client.get(f"{BASE}", headers=admin)
    assert d["id"] in [x["id"] for x in lst.json()]
    pv = await client.get(f"{BASE}/preview", params={
        "scope_type": "department", "scope_value": world["dx"]}, headers=admin)
    assert [x["user_id"] for x in pv.json()] == [world["ids"]["e1"]]
    up = await client.patch(f"{BASE}/{d['id']}", json={"can_publish": False},
                            headers=admin)
    assert up.status_code == 200 and up.json()["can_publish"] is False
    rv = await client.post(f"{BASE}/{d['id']}/revoke", headers=admin)
    assert rv.status_code == 200 and rv.json()["revoked_at"]
    assert (await client.post(f"{BASE}/{d['id']}/revoke", headers=admin)
            ).status_code == 409
    assert (await client.get(f"{BASE}/my", headers=h)).json() == []
    lst = await client.get(f"{BASE}", params={"include_inactive": True}, headers=admin)
    assert d["id"] in [x["id"] for x in lst.json()]


async def test_validation(client, world):
    admin = await _login(client, "admin@gmail.com")
    for bad in (
        {"scope_type": "department", "scope_value": "NoSuchDept"},
        {"scope_type": "location", "scope_value": "NoSuchLoc"},
        {"scope_type": "employees", "employee_ids": []},
        {"scope_type": "employees", "employee_ids": [99999999]},
        {"scope_type": "team", "scope_value": "x"},
        {"valid_to": (TODAY - timedelta(days=5)).isoformat()},
        {"grantee_id": 99999999},
    ):
        r = await client.post(f"{BASE}/", json=_body(world, **bad), headers=admin)
        assert r.status_code == 422, (bad, r.text)
    ok = await client.post(f"{BASE}/", json=_body(
        world, scope_type="team", scope_value=None), headers=admin)
    assert ok.status_code == 200 and ok.json()["covered_count"] == 1
