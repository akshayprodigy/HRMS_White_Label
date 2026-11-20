"""Scheduling delegation tests (Roadmap v2 Phase 1A). DB-backed; every row
created is removed in fixture teardown."""
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from _tz import org_today  # noqa: E402
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.api import deps
from app.core.config import settings
from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.main import create_app
from app.models.audit import AuditLog
from app.models.department import Department
from app.models.employee import Employee, EmployeeStatus
from app.models.notification import Notification
from app.models.roster import RosterChangeRequest, RosterEntry
from app.models.schedule_delegation import DelegationScope, ScheduleDelegation
from app.models.user import User
from app.services import roster as svc

BASE = f"{settings.API_V1_STR}/roster/delegations"
PW = "test@12345"
TODAY = org_today()


@pytest.fixture
async def client():
    app = create_app()
    # Attendance gating is orthogonal to scope logic under test.
    app.dependency_overrides[deps.verify_attendance] = lambda: None
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def world():
    """deleg (no scope), e1 (dept X, location), e2 (dept Y), rep (reports to
    deleg, dept Y), stranger, and a superuser. Cleanup is keyed on the unique
    suffix so a partial setup is still removed."""
    sfx = uuid.uuid4().hex[:8]
    dept_x, dept_y, loc = f"DX{sfx}", f"DY{sfx}", f"LOC{sfx}"
    ids: dict = {}
    try:
        async with SessionLocal() as db:
            def mk(tag, **kw):
                return User(email=f"sd_{tag}_{sfx}@t.com", full_name=f"SD {tag}",
                            hashed_password=get_password_hash(PW),
                            is_active=True, **kw)
            deleg, e1, e2, stranger = mk("deleg"), mk("e1"), mk("e2"), mk("str")
            admin = mk("admin", is_superuser=True)
            db.add_all([deleg, e1, e2, stranger, admin])
            await db.commit()
            rep = mk("rep", manager_id=deleg.id)
            db.add(rep)
            db.add_all([Department(name=dept_x), Department(name=dept_y)])
            await db.commit()
            for tag, u, d, lc in (("1", e1, dept_x, loc), ("2", e2, dept_y, None),
                                  ("r", rep, dept_y, None)):
                db.add(Employee(
                    user_id=u.id, employee_id=f"SD{sfx}{tag}", department=d,
                    designation="Tester", date_of_joining=date(2020, 1, 1),
                    status=EmployeeStatus.ACTIVE, location=lc,
                ))
            await db.commit()
            ids = {"deleg": deleg.id, "e1": e1.id, "e2": e2.id,
                   "str": stranger.id, "rep": rep.id, "admin": admin.id}
        yield {"ids": ids, "dx": dept_x, "dy": dept_y, "loc": loc,
               "email": f"sd_deleg_{sfx}@t.com",
               "admin_email": f"sd_admin_{sfx}@t.com",
               "str_email": f"sd_str_{sfx}@t.com",
               "e1_email": f"sd_e1_{sfx}@t.com"}
    finally:
        async with SessionLocal() as db:
            uids = list((await db.execute(select(User.id).where(
                User.email.like(f"sd\\_%\\_{sfx}@t.com")))).scalars().all())
            dids = (await db.execute(select(ScheduleDelegation.id).where(
                ScheduleDelegation.grantee_id.in_(uids)))).scalars().all()
            crids = (await db.execute(select(RosterChangeRequest.id).where(
                RosterChangeRequest.employee_id.in_(uids)))).scalars().all()
            await db.execute(delete(AuditLog).where(
                AuditLog.resource_type == "schedule_delegation",
                AuditLog.resource_id.in_([str(i) for i in dids])))
            await db.execute(delete(AuditLog).where(
                AuditLog.resource_type == "roster_change_request",
                AuditLog.resource_id.in_([str(i) for i in crids])))
            await db.execute(delete(AuditLog).where(
                AuditLog.action == "roster.bulk_publish",
                AuditLog.user_id.in_(uids)))
            await db.execute(delete(Notification).where(
                Notification.user_id.in_(uids)))
            await db.execute(delete(RosterChangeRequest).where(
                RosterChangeRequest.employee_id.in_(uids)))
            await db.execute(delete(RosterEntry).where(
                RosterEntry.employee_id.in_(uids)))
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
        # "str" has no Employee row => dropped from the resolved scope.
        assert await svc.delegated_user_ids(db, u) == {world["ids"]["e2"]}


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
            User.email == world["admin_email"]))).scalars().one()
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
    admin = await _login(client, world["admin_email"])
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
    admin = await _login(client, world["admin_email"])
    for bad in (
        {"scope_type": "department", "scope_value": "NoSuchDept"},
        {"scope_type": "location", "scope_value": "NoSuchLoc"},
        {"scope_type": "employees", "employee_ids": []},
        {"scope_type": "employees", "employee_ids": [99999999]},
        {"scope_type": "team", "scope_value": "x"},
        {"valid_to": (TODAY - timedelta(days=5)).isoformat()},
        {"grantee_id": 99999999},
        {"scope_type": "employees", "scope_value": "x",
         "employee_ids": [1]},
        {"scope_type": "team", "scope_value": None, "employee_ids": [1]},
    ):
        r = await client.post(f"{BASE}/", json=_body(world, **bad), headers=admin)
        assert r.status_code == 422, (bad, r.text)
    ok = await client.post(f"{BASE}/", json=_body(
        world, scope_type="team", scope_value=None), headers=admin)
    assert ok.status_code == 200 and ok.json()["covered_count"] == 1


# --------------- roster endpoints honour delegations ---------------

ROSTER = f"{settings.API_V1_STR}/roster"


async def _revoke(deleg_id):
    async with SessionLocal() as db:
        d = await db.get(ScheduleDelegation, deleg_id)
        d.revoked_at = datetime.now(timezone.utc)
        await db.commit()


async def _cr(uid):
    async with SessionLocal() as db:
        cr = RosterChangeRequest(
            employee_id=uid, work_date=TODAY + timedelta(days=2),
            requested_week_off=True, reason="Need the day off",
            status="pending")
        db.add(cr)
        await db.commit()
        return cr.id


def _plan(h, client):
    return client.get(f"{ROSTER}/plan", params={
        "start": TODAY.isoformat(), "end": TODAY.isoformat()}, headers=h)


async def test_plan_scope(client, world):
    hs = await _login(client, world["str_email"])
    assert (await _plan(hs, client)).status_code == 403
    hd = await _login(client, world["email"])
    assert (await _plan(hd, client)).status_code == 403
    await _grant(world, scope_type=DelegationScope.DEPARTMENT, scope_value=world["dx"])
    r = await _plan(hd, client)
    assert r.status_code == 200, r.text


async def test_bulk_reports_out_of_scope(client, world):
    await _grant(world, scope_type=DelegationScope.DEPARTMENT, scope_value=world["dx"])
    hd = await _login(client, world["email"])
    r = await client.post(f"{ROSTER}/bulk", json={
        "employee_ids": [world["ids"]["e1"], world["ids"]["e2"]],
        "start": TODAY.isoformat(),
        "end": (TODAY + timedelta(days=6)).isoformat(),
        "pattern": {"6": None},
    }, headers=hd)
    assert r.status_code == 200, r.text
    assert r.json()["out_of_scope"] == [world["ids"]["e2"]]
    assert r.json()["created"] >= 1


async def _decide(client, world, cr_id, h):
    return await client.post(f"{ROSTER}/change-requests/{cr_id}/decide",
                             json={"action": "reject"}, headers=h)


async def test_decide_requires_approve_flag(client, world):
    e1 = world["ids"]["e1"]
    hd = await _login(client, world["email"])
    gid = await _grant(world, scope_type=DelegationScope.EMPLOYEES,
                       employee_ids=[e1])  # manage only
    cr = await _cr(e1)
    assert (await _decide(client, world, cr, hd)).status_code == 403
    await _revoke(gid)
    await _grant(world, scope_type=DelegationScope.EMPLOYEES,
                 employee_ids=[e1], can_approve_changes=True)
    listed = await client.get(f"{ROSTER}/change-requests", headers=hd)
    assert cr in [x["id"] for x in listed.json()]
    assert (await _decide(client, world, cr, hd)).status_code == 200


async def test_decide_own_request_forbidden(client, world):
    me = world["ids"]["deleg"]
    await _grant(world, scope_type=DelegationScope.EMPLOYEES,
                 employee_ids=[me], can_approve_changes=True)
    cr = await _cr(me)
    hd = await _login(client, world["email"])
    assert (await _decide(client, world, cr, hd)).status_code == 403
    ha = await _login(client, world["admin_email"])
    assert (await _decide(client, world, cr, ha)).status_code == 200


async def test_revoked_grant_cannot_decide(client, world):
    e1 = world["ids"]["e1"]
    gid = await _grant(world, scope_type=DelegationScope.EMPLOYEES,
                       employee_ids=[e1], can_approve_changes=True)
    cr = await _cr(e1)
    await _revoke(gid)
    hd = await _login(client, world["email"])
    assert (await _decide(client, world, cr, hd)).status_code == 403


async def test_subsets_and_self_exclusion(world):
    me, e1, e2 = world["ids"]["deleg"], world["ids"]["e1"], world["ids"]["e2"]
    await _grant(world, scope_type=DelegationScope.EMPLOYEES,
                 employee_ids=[me, e1], can_publish=True)
    await _grant(world, scope_type=DelegationScope.DEPARTMENT,
                 scope_value=world["dy"])
    async with SessionLocal() as db:
        u = await db.get(User, me)
        assert await svc.delegated_user_ids(db, u) == {
            e1, e2, world["ids"]["rep"]}
        assert await svc.manageable_subset(db, u, {me, e1, e2, 0}) == {e1, e2}
        assert await svc.publishable_subset(db, u, {me, e1, e2}) == {e1}


async def _set_status(uid, status):
    async with SessionLocal() as db:
        e = (await db.execute(select(Employee).where(
            Employee.user_id == uid))).scalars().one()
        e.status = status
        await db.commit()


async def test_inactive_employee_not_manageable(world):
    e1, e2 = world["ids"]["e1"], world["ids"]["e2"]
    # Delegate over dept X / employees list / team.
    await _grant(world, scope_type=DelegationScope.DEPARTMENT,
                 scope_value=world["dx"], can_approve_changes=True)
    await _grant(world, scope_type=DelegationScope.EMPLOYEES, employee_ids=[e2])
    await _grant(world, scope_type=DelegationScope.TEAM)
    async with SessionLocal() as db:
        u = await db.get(User, world["ids"]["deleg"])
        assert await svc.manageable_subset(db, u, {e1, e2}) == {e1, e2}
    await _set_status(e1, EmployeeStatus.INACTIVE)
    await _set_status(e2, EmployeeStatus.INACTIVE)
    await _set_status(world["ids"]["rep"], EmployeeStatus.INACTIVE)
    async with SessionLocal() as db:
        u = await db.get(User, world["ids"]["deleg"])
        assert await svc.manageable_subset(
            db, u, {e1, e2, world["ids"]["rep"]}) == set()
        assert await svc.delegated_user_ids(db, u) == set()
        assert await svc.approvable_user_ids(db, u) == set()


async def test_inactive_employee_not_manageable_by_head(world):
    e1 = world["ids"]["e1"]
    async with SessionLocal() as db:
        d = (await db.execute(select(Department).where(
            Department.name == world["dx"]))).scalars().one()
        d.head_user_id = world["ids"]["deleg"]
        await db.commit()
    async with SessionLocal() as db:
        u = await db.get(User, world["ids"]["deleg"])
        assert await svc.manageable_subset(db, u, {e1}) == {e1}
        assert await svc.approvable_user_ids(db, u) == {e1}
    await _set_status(e1, EmployeeStatus.INACTIVE)
    async with SessionLocal() as db:
        u = await db.get(User, world["ids"]["deleg"])
        assert await svc.manageable_subset(db, u, {e1}) == set()
        assert await svc.approvable_user_ids(db, u) == set()


async def test_bulk_entry_date_outside_window_422(client, world):
    ha = await _login(client, world["admin_email"])
    r = await client.post(f"{ROSTER}/bulk", headers=ha, json={
        "start": TODAY.isoformat(), "end": (TODAY + timedelta(days=2)).isoformat(),
        "entries": [{"employee_id": world["ids"]["e1"],
                     "work_date": (TODAY + timedelta(days=5)).isoformat(),
                     "is_week_off": True}],
    })
    assert r.status_code == 422, r.text


async def test_change_request_unknown_template_422(client, world):
    he = await _login(client, world["e1_email"])
    r = await client.post(f"{ROSTER}/change-requests", headers=he, json={
        "work_date": (TODAY + timedelta(days=3)).isoformat(),
        "requested_shift_template_id": 99999999,
        "reason": "swap please"})
    assert r.status_code == 422, r.text


async def test_patch_revoked_409_and_utc_timestamps(client, world):
    admin = await _login(client, world["admin_email"])
    r = await client.post(f"{BASE}/", json=_body(world), headers=admin)
    d = r.json()
    assert d["created_at"].endswith(("Z", "+00:00"))
    rv = await client.post(f"{BASE}/{d['id']}/revoke", headers=admin)
    assert rv.json()["revoked_at"].endswith(("Z", "+00:00"))
    up = await client.patch(f"{BASE}/{d['id']}", json={"note": "x"},
                            headers=admin)
    assert up.status_code == 409 and "revoked" in up.text
