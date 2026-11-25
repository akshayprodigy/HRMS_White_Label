"""DOP D1 Task 5: existing manager edits go through the assignment service.
Real HTTP through ASGI on the dev DB; teardown leaves nothing behind."""
import asyncio
import io

import pandas as pd
import pytest
from _dop_world import dop  # noqa: F401
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.exc import OperationalError

from app.api import deps
from app.db.session import SessionLocal
from app.main import create_app
from app.models.audit import AuditLog
from app.models.department import Department
from app.models.dop import ManagerAssignment
from app.models.employee import Employee
from app.models.user import User
from app.services.dop import assignments as A

HR = "/api/v1/hr"


async def _login(c, email):
    r = await c.post("/api/v1/auth/login",
                     data={"username": email, "password": "x"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _client(sfx, who):
    app = create_app()
    app.dependency_overrides[deps.verify_attendance] = lambda: None
    c = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    c.h = await _login(c, f"dop_{who}_{sfx}@test.com")
    return c


@pytest.fixture
async def api(dop):
    from sqlalchemy import insert
    from app.models.user import Permission, Role, role_permissions, user_roles
    sfx = dop["sfx"]
    async with SessionLocal() as db:       # employee write, no payroll write
        role = Role(name=f"dopx{sfx}", description="t")
        db.add(role)
        await db.flush()
        pid = (await db.execute(select(Permission.id).where(
            Permission.name == "hr employee write"))).scalar_one()
        await db.execute(insert(role_permissions).values(
            role_id=role.id, permission_id=pid))
        await db.execute(insert(user_roles).values(
            user_id=dop["uid"]["act"], role_id=role.id))
        await db.commit()
        rid = role.id
    c = await _client(sfx, "admin")
    c.hr_h = await _login(c, f"dop_hr_{sfx}@test.com")
    c.lim = await _login(c, f"dop_act_{sfx}@test.com")
    yield c
    await c.aclose()
    async with SessionLocal() as db:
        from sqlalchemy import delete as dele
        await db.execute(dele(user_roles).where(user_roles.c.role_id == rid))
        await db.execute(dele(role_permissions).where(
            role_permissions.c.role_id == rid))
        await db.execute(dele(Role).where(Role.id == rid))
        await db.commit()


async def _eid(uid):
    async with SessionLocal() as db:
        return (await db.execute(select(Employee.id).where(
            Employee.user_id == uid))).scalar_one()


async def _mgr(uid):
    async with SessionLocal() as db:
        return (await db.execute(select(User.manager_id).where(
            User.id == uid))).scalar_one()


async def _emp_field(uid, f):
    async with SessionLocal() as db:
        return (await db.execute(select(getattr(Employee, f)).where(
            Employee.user_id == uid))).scalar_one()


async def _live_rows(uid):
    async with SessionLocal() as db:
        return (await db.execute(select(ManagerAssignment).where(
            ManagerAssignment.scope_user_id == uid,
            ManagerAssignment.cancelled_at.is_(None),
            ManagerAssignment.ends_on.is_(None)))).scalars().all()


async def _patch(api, uid, body, hdr=None):
    return await api.patch(f"{HR}/employees/{await _eid(uid)}",
                           headers=hdr or api.h, json=body)


async def test_update_manager_and_response(dop, api):
    u = dop["uid"]
    r = await _patch(api, u["emp"], {"manager_id": u["mgr"],
                                     "designation": "Lead"})
    assert r.status_code == 200, r.text
    assert r.json()["user"]["manager_id"] == u["mgr"]
    assert r.json()["designation"] == "Lead"
    assert await _mgr(u["emp"]) == u["mgr"]
    assert [a.manager_user_id for a in await _live_rows(u["emp"])] == [u["mgr"]]
    # same manager again: nothing new
    r = await _patch(api, u["emp"], {"manager_id": u["mgr"]})
    assert r.status_code == 200
    assert len(await _live_rows(u["emp"])) == 1
    # HR (not superuser) can do it too, and change to another
    r = await _patch(api, u["emp"], {"manager_id": u["mgr2"]}, api.hr_h)
    assert r.status_code == 200, r.text
    assert r.json()["user"]["manager_id"] == u["mgr2"]
    assert await _mgr(u["emp"]) == u["mgr2"]


async def test_clear_manager_with_explicit_null(dop, api):
    u = dop["uid"]
    assert (await _patch(api, u["emp"], {"manager_id": u["mgr"]})
            ).status_code == 200
    r = await _patch(api, u["emp"], {"manager_id": None, "designation": "X"})
    assert r.status_code == 200, r.text
    assert r.json()["user"]["manager_id"] is None
    assert await _mgr(u["emp"]) is None
    assert await _live_rows(u["emp"]) == []
    # not sent: untouched
    assert (await _patch(api, u["emp"], {"manager_id": u["mgr"]})
            ).status_code == 200
    r = await _patch(api, u["emp"], {"designation": "Y"})
    assert r.json()["user"]["manager_id"] == u["mgr"]


async def test_loop_rejected_and_other_fields_unchanged(dop, api):
    u = dop["uid"]
    assert (await _patch(api, u["mgr"], {"manager_id": u["emp"]})
            ).status_code == 200
    before = await _emp_field(u["emp"], "designation")
    r = await _patch(api, u["emp"], {"manager_id": u["mgr"],
                                     "designation": "Changed"})
    assert r.status_code == 422, r.text
    assert await _emp_field(u["emp"], "designation") == before
    assert await _mgr(u["emp"]) is None


async def test_inactive_manager_422(dop, api):
    u = dop["uid"]
    r = await _patch(api, u["emp"], {"manager_id": u["off"],
                                     "designation": "Changed"})
    assert r.status_code == 422, r.text
    assert await _mgr(u["emp"]) is None
    assert await _emp_field(u["emp"], "designation") == "T"


async def test_rejected_requests_leave_manager_alone(dop, api):
    u = dop["uid"]
    assert (await _patch(api, u["emp"], {"manager_id": u["mgr"]})
            ).status_code == 200
    # payroll-forbidden: a user with employee-write but no payroll write
    r = await _patch(api, u["emp"], {"manager_id": u["mgr2"], "salary": 5},
                     api.lim)
    assert r.status_code == 403, r.text
    assert await _mgr(u["emp"]) == u["mgr"]
    # unknown department
    r = await _patch(api, u["emp"], {"manager_id": u["mgr2"],
                                     "department": "Nope" + dop["sfx"]})
    assert r.status_code in (400, 422), r.text
    assert await _mgr(u["emp"]) == u["mgr"]
    # unknown employment type
    r = await _patch(api, u["emp"], {"manager_id": u["mgr2"],
                                     "employment_type": "zzz-" + dop["sfx"]})
    assert r.status_code in (400, 422), r.text
    assert await _mgr(u["emp"]) == u["mgr"]
    # unknown employee
    r = await api.patch(f"{HR}/employees/999999999", headers=api.h,
                        json={"manager_id": u["mgr2"]})
    assert r.status_code == 404


async def test_department_move_picks_up_and_drops_manager(dop, api):
    u = dop["uid"]
    dnames = {"B": f"DOP{dop['sfx']}B", "C": f"DOP{dop['sfx']}C"}
    ids = {}
    try:
        async with SessionLocal() as db:
            for k, n in dnames.items():
                d = Department(name=n, is_active=True)
                db.add(d)
                await db.flush()
                ids[k] = d.id
            await db.commit()
        async with SessionLocal() as db:
            await A.lock_reporting(db)
            from app.services.org_time import local_today
            today = await local_today(db)
            kind = (await A.lock_reporting(db)).id
            for dept, mgr in ((dop["dept_id"], "hr"), (ids["C"], "mgr2")):
                await A.create(db, actor_id=u["admin"], kind_id=kind,
                               scope_type="department",
                               scope_department_id=dept,
                               manager_user_id=u[mgr], starts_on=today)
            await db.commit()
        assert await _mgr(u["emp"]) == u["hr"]
        r = await _patch(api, u["emp"], {"department": dnames["B"]})
        assert r.status_code == 200, r.text
        assert r.json()["department"] == dnames["B"]
        assert r.json()["user"]["manager_id"] is None        # dropped
        assert await _mgr(u["emp"]) is None
        r = await _patch(api, u["emp"], {"department": dnames["C"]})
        assert r.status_code == 200
        assert r.json()["user"]["manager_id"] == u["mgr2"]   # picked up
        r = await _patch(api, u["emp"], {"department": dop["dept"]})
        assert r.json()["user"]["manager_id"] == u["hr"]
        # a manager set by hand is not cleared by a move
        async with SessionLocal() as db:
            await db.execute(delete(ManagerAssignment).where(
                ManagerAssignment.scope_department_id.in_(
                    [dop["dept_id"], *ids.values()])))
            await db.commit()
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(ManagerAssignment).where(
                ManagerAssignment.scope_department_id.in_(ids.values())))
            await db.execute(delete(Department).where(
                Department.id.in_(list(ids.values()))))
            await db.commit()


async def test_profile_location_change_resyncs(dop):
    u = dop["uid"]
    from app.services.org_time import local_today
    async with SessionLocal() as db:
        kind = (await A.lock_reporting(db)).id
        await A.create(db, actor_id=u["admin"], kind_id=kind,
                       scope_type="location", scope_location=dop["loc"],
                       manager_user_id=u["hr"],
                       starts_on=await local_today(db))
        await db.commit()
    assert await _mgr(u["emp"]) == u["hr"]
    c = await _client(dop["sfx"], "emp")
    try:
        r = await c.patch(f"{HR}/employees/me/profile", headers=c.h,
                          json={"location": "Elsewhere" + dop["sfx"],
                                "phone": "123"})
        assert r.status_code == 200, r.text
        assert r.json()["location"] == "Elsewhere" + dop["sfx"]
        assert r.json()["phone"] == "123"
        assert await _mgr(u["emp"]) is None
        r = await c.patch(f"{HR}/employees/me/profile", headers=c.h,
                          json={"location": dop["loc"]})
        assert r.status_code == 200
        assert await _mgr(u["emp"]) == u["hr"]
    finally:
        await c.aclose()


def _emp_body(sfx, tag, **kw):
    return {"employee_id": f"N{tag}{sfx}", "department": f"DOP{sfx}",
            "designation": "D", "date_of_joining": "2024-01-01", **kw}


async def _new_user(dop, tag):
    from app.core.security import get_password_hash
    async with SessionLocal() as db:
        usr = User(email=f"dop_{tag}_{dop['sfx']}@test.com", full_name=tag,
                   hashed_password=get_password_hash("x"), is_active=True)
        db.add(usr)
        await db.commit()
        return usr.id


async def test_create_employee_for_existing_user(dop, api):
    u = dop["uid"]
    n1 = await _new_user(dop, "n1")
    r = await api.post(f"{HR}/employees", headers=api.h, json={
        **_emp_body(dop["sfx"], "1"), "user_id": n1, "manager_id": u["mgr"]})
    assert r.status_code == 200, r.text
    assert r.json()["user"]["manager_id"] == u["mgr"]
    assert await _mgr(n1) == u["mgr"]
    assert [a.manager_user_id for a in await _live_rows(n1)] == [u["mgr"]]
    # bad manager: nothing is created
    n2 = await _new_user(dop, "n2")
    r = await api.post(f"{HR}/employees", headers=api.h, json={
        **_emp_body(dop["sfx"], "2"), "user_id": n2, "manager_id": u["off"]})
    assert r.status_code == 422, r.text
    async with SessionLocal() as db:
        assert (await db.execute(select(Employee).where(
            Employee.user_id == n2))).scalars().first() is None


async def test_create_without_manager_applies_scope_assignments(dop, api):
    u = dop["uid"]
    from app.services.org_time import local_today
    async with SessionLocal() as db:
        kind = (await A.lock_reporting(db)).id
        await A.create(db, actor_id=u["admin"], kind_id=kind,
                       scope_type="department",
                       scope_department_id=dop["dept_id"],
                       manager_user_id=u["hr"],
                       starts_on=await local_today(db))
        await db.commit()
    n1 = await _new_user(dop, "n1")
    r = await api.post(f"{HR}/employees", headers=api.h, json={
        **_emp_body(dop["sfx"], "1"), "user_id": n1})
    assert r.status_code == 200, r.text
    assert r.json()["user"]["manager_id"] == u["hr"]
    assert await _mgr(n1) == u["hr"]


async def test_create_with_user(dop, api):
    u = dop["uid"]
    em = f"dop_w1_{dop['sfx']}@test.com"
    r = await api.post(f"{HR}/employees/with-user", headers=api.h, json={
        **_emp_body(dop["sfx"], "w1"),
        "user": {"full_name": "W1", "email": em, "password": "x12345",
                 "manager_id": u["mgr"]}})
    assert r.status_code == 200, r.text
    nid = r.json()["user_id"]
    assert r.json()["user"]["manager_id"] == u["mgr"]
    assert await _mgr(nid) == u["mgr"]
    # without a manager
    r = await api.post(f"{HR}/employees/with-user", headers=api.h, json={
        **_emp_body(dop["sfx"], "w2"),
        "user": {"full_name": "W2",
                 "email": f"dop_w2_{dop['sfx']}@test.com",
                 "password": "x12345"}})
    assert r.status_code == 200, r.text
    assert r.json()["user"]["manager_id"] is None
    # bad manager: no user is left behind
    em3 = f"dop_w3_{dop['sfx']}@test.com"
    r = await api.post(f"{HR}/employees/with-user", headers=api.h, json={
        **_emp_body(dop["sfx"], "w3"),
        "user": {"full_name": "W3", "email": em3, "password": "x12345",
                 "manager_id": u["off"]}})
    assert r.status_code == 422, r.text
    async with SessionLocal() as db:
        assert (await db.execute(select(User).where(
            User.email == em3))).scalars().first() is None


def _xlsx(rows):
    cols = ["Full Name", "Email", "Employee ID", "Department", "Designation",
            "Manager Email"]
    buf = io.BytesIO()
    pd.DataFrame(rows, columns=cols).to_excel(buf, index=False)
    return buf.getvalue()


async def test_bulk_import_row_errors_do_not_poison(dop, api):
    u, s = dop["uid"], dop["sfx"]
    rows = [
        ["Good1", f"dop_b1_{s}@test.com", f"B1{s}", dop["dept"], "D",
         f"dop_mgr_{s}@test.com"],
        ["BadMgr", f"dop_b2_{s}@test.com", f"B2{s}", dop["dept"], "D",
         f"dop_off_{s}@test.com"],                       # inactive manager
        ["Good3", f"dop_b3_{s}@test.com", f"B3{s}", dop["dept"], "D", None],
        ["Good4", f"dop_b4_{s}@test.com", f"B4{s}", dop["dept"], "D",
         f"dop_mgr2_{s}@test.com"],
    ]
    r = await api.post(
        f"{HR}/employees/bulk-upload", headers=api.h,
        files={"file": ("e.xlsx", _xlsx(rows),
                        "application/vnd.openxmlformats-officedocument."
                        "spreadsheetml.sheet")})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["success"] == 3 and out["failed"] == 1, out
    assert "Row 3" in out["errors"][0] and "BadMgr" in out["errors"][0]
    async with SessionLocal() as db:
        got = dict((await db.execute(select(User.email, User.manager_id).where(
            User.email.like(f"dop\\_b_\\_{s}@test.com")))).all())
    assert got == {f"dop_b1_{s}@test.com": u["mgr"],
                   f"dop_b3_{s}@test.com": None,
                   f"dop_b4_{s}@test.com": u["mgr2"]}, got


async def test_admin_patch_manager(dop, api):
    u = dop["uid"]
    r = await api.patch(f"/api/v1/admin/users/{u['emp']}", headers=api.h,
                        json={"manager_id": u["mgr"], "full_name": "Renamed"})
    assert r.status_code == 200, r.text
    assert r.json()["manager_id"] == u["mgr"]
    assert r.json()["full_name"] == "Renamed"
    assert await _mgr(u["emp"]) == u["mgr"]
    assert [a.manager_user_id for a in await _live_rows(u["emp"])] == [u["mgr"]]
    # None means "not sent"
    r = await api.patch(f"/api/v1/admin/users/{u['emp']}", headers=api.h,
                        json={"manager_id": None, "full_name": "Again"})
    assert r.status_code == 200 and r.json()["manager_id"] == u["mgr"]
    # loop / inactive reject the whole request
    r = await api.patch(f"/api/v1/admin/users/{u['mgr']}", headers=api.h,
                        json={"manager_id": u["emp"], "full_name": "Nope"})
    assert r.status_code == 422, r.text
    r = await api.patch(f"/api/v1/admin/users/{u['emp']}", headers=api.h,
                        json={"manager_id": u["off"]})
    assert r.status_code == 422
    async with SessionLocal() as db:
        assert (await db.execute(select(User.full_name).where(
            User.id == u["mgr"]))).scalar_one() != "Nope"
    assert (await api.patch("/api/v1/admin/users/999999999", headers=api.h,
                            json={"manager_id": u["mgr"]})).status_code == 404


async def test_two_concurrent_edits_no_5xx(dop, api):
    u = dop["uid"]
    c2 = await _client(dop["sfx"], "admin")
    try:
        for _ in range(3):
            eid = await _eid(u["emp"])
            r1, r2, r3 = await asyncio.gather(
                api.patch(f"{HR}/employees/{eid}", headers=api.h,
                          json={"manager_id": u["mgr"]}),
                c2.patch(f"{HR}/employees/{eid}", headers=c2.h,
                         json={"manager_id": u["mgr2"],
                               "designation": "Z"}),
                c2.patch(f"/api/v1/admin/users/{u['act']}", headers=c2.h,
                         json={"manager_id": u["mgr"]}))
            for r in (r1, r2, r3):
                assert r.status_code < 500, r.text
                assert r.status_code in (200, 409), r.text
            assert r3.status_code == 200 or r3.status_code == 409
            if r1.status_code == 200:
                assert r1.json()["id"] == eid       # body intact
        assert await _mgr(u["emp"]) in (u["mgr"], u["mgr2"])
    finally:
        await c2.aclose()


async def test_body_survives_a_lock_retry(dop, api, monkeypatch):
    """First attempt of the manager change fails with MariaDB 1020 after
    partial work; the retried request still answers with a full body."""
    u = dop["uid"]
    real = A.set_reporting_manager
    calls = {"n": 0}

    class _Orig(Exception):
        args = (1020, "snapshot")

    async def flaky(db, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            await real(db, **kw)            # work done, then the conflict
            raise OperationalError("stmt", {}, _Orig())
        return await real(db, **kw)
    monkeypatch.setattr(A, "set_reporting_manager", flaky)
    r = await _patch(api, u["emp"], {"manager_id": u["mgr"],
                                     "designation": "Retry"})
    assert r.status_code == 200, r.text
    assert calls["n"] == 2
    assert r.json()["user"]["manager_id"] == u["mgr"]
    assert r.json()["designation"] == "Retry"
    assert len(await _live_rows(u["emp"])) == 1
    # audit row written once by the endpoint
    async with SessionLocal() as db:
        n = len((await db.execute(select(AuditLog.id).where(
            AuditLog.user_id == u["admin"], AuditLog.action == "UPDATE",
            AuditLog.resource_id == str(await _eid(u["emp"]))))).all())
    assert n == 1


async def test_scheduler_job_retries_and_never_raises(dop, monkeypatch):
    from app.services import scheduler as S
    u = dop["uid"]
    seen = {"n": 0}

    async def scoped(db, user_ids=None):    # never a full sync on dev data
        seen["n"] += 1
        return await real(db, [u["emp"]])
    real = A.sync_mirror
    monkeypatch.setattr(A, "sync_mirror", scoped)
    async with SessionLocal() as db:
        out = await S._job_dop_manager_mirror(db)
    assert out["changed"] == 0 and seen["n"] == 1

    async def boom(db, user_ids=None):
        raise RuntimeError("boom")
    monkeypatch.setattr(A, "sync_mirror", boom)
    async with SessionLocal() as db:
        out = await S._job_dop_manager_mirror(db)     # must not raise
    assert out["changed"] == 0 and "boom" in out["error"]
    assert "dop_manager_mirror" in S.REGISTRY
