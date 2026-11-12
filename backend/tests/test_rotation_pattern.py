"""Rotation patterns + publish-rights enforcement tests (Roadmap v2 Phase 1A).
DB-backed; everything created is removed in fixture teardown."""
import uuid
from datetime import date, datetime, time, timedelta, timezone

import pytest
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
from app.models.roster import RosterEntry
from app.models.rotation_pattern import RotationPattern
from app.models.schedule_delegation import DelegationScope, ScheduleDelegation
from app.models.shift import ShiftTemplate
from app.models.user import User
from app.services.roster import expand_rotation

ROSTER = f"{settings.API_V1_STR}/roster"
PW = "test@12345"
TODAY = datetime.now(timezone.utc).date()
D = date(2030, 1, 1)


# ----------------------------- pure -----------------------------

def test_four_on_four_off():
    cyc = [1, 1, 1, 1, None, None, None, None]
    out = expand_rotation(cyc, D, D, D + timedelta(days=9))
    assert [t for _, t, _ in out] == [1, 1, 1, 1, None, None, None, None, 1, 1]
    assert [w for _, _, w in out][4:8] == [True] * 4
    assert out[0][0] == D and out[-1][0] == D + timedelta(days=9)


def test_offset_staggers():
    cyc = [1, 1, 1, 1, None, None, None, None]
    a = expand_rotation(cyc, D, D, D + timedelta(days=7), 0)
    b = expand_rotation(cyc, D, D, D + timedelta(days=7), 4)
    assert [t for _, t, _ in b] == [None] * 4 + [1] * 4
    assert all((x[1] is None) != (y[1] is None) for x, y in zip(a, b))


def test_before_anchor_wraps():
    cyc = [1, 2, 3]
    out = expand_rotation(cyc, D, D - timedelta(days=4), D - timedelta(days=1))
    # -4 % 3 = 2, -3 -> 0, -2 -> 1, -1 -> 2
    assert [t for _, t, _ in out] == [3, 1, 2, 3]


def test_week_off_flag():
    out = expand_rotation([None], D, D, D + timedelta(days=2))
    assert out == [(D + timedelta(days=i), None, True) for i in range(3)]


def test_two_two_three():
    cyc = [1, 1, None, None, 2, 2, 2, None, None, 1, 1, None, None, None]
    assert len(cyc) == 14
    out = expand_rotation(cyc, D, D, D + timedelta(days=15))
    assert [t for _, t, _ in out][:14] == cyc
    assert out[14][1] == cyc[0] and out[15][1] == cyc[1]


# ----------------------------- API -----------------------------

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
    dept_x, dept_y = f"RX{sfx}", f"RY{sfx}"
    ids: dict = {}
    try:
        async with SessionLocal() as db:
            def mk(tag, **kw):
                return User(email=f"rp_{tag}_{sfx}@t.com", full_name=f"RP {tag}",
                            hashed_password=get_password_hash(PW),
                            is_active=True, **kw)
            deleg, e1, e2, e3 = mk("deleg"), mk("e1"), mk("e2"), mk("e3")
            admin = mk("admin", is_superuser=True)
            db.add_all([deleg, e1, e2, e3, admin])
            db.add_all([Department(name=dept_x), Department(name=dept_y)])
            t1 = ShiftTemplate(name=f"RPT1{sfx}", start_time=time(9), end_time=time(17))
            t2 = ShiftTemplate(name=f"RPT2{sfx}", start_time=time(21), end_time=time(5),
                               is_overnight=True)
            t3 = ShiftTemplate(name=f"RPT3{sfx}", start_time=time(6), end_time=time(14),
                               is_active=False)
            db.add_all([t1, t2, t3])
            await db.commit()
            for tag, u, d in (("1", e1, dept_x), ("2", e2, dept_x), ("3", e3, dept_y)):
                db.add(Employee(
                    user_id=u.id, employee_id=f"RP{sfx}{tag}", department=d,
                    designation="Tester", date_of_joining=date(2020, 1, 1),
                    status=EmployeeStatus.ACTIVE))
            await db.commit()
            ids = {"deleg": deleg.id, "e1": e1.id, "e2": e2.id, "e3": e3.id,
                   "t1": t1.id, "t2": t2.id, "t3": t3.id}
        yield {"ids": ids, "dx": dept_x, "sfx": sfx,
               "email": f"rp_deleg_{sfx}@t.com",
               "admin_email": f"rp_admin_{sfx}@t.com"}
    finally:
        async with SessionLocal() as db:
            uids = list((await db.execute(select(User.id).where(
                User.email.like(f"rp\\_%\\_{sfx}@t.com")))).scalars().all())
            pids = (await db.execute(select(RotationPattern.id).where(
                RotationPattern.name.like(f"%{sfx}")))).scalars().all()
            eids = (await db.execute(select(RosterEntry.id).where(
                RosterEntry.employee_id.in_(uids)))).scalars().all()
            await db.execute(delete(AuditLog).where(
                AuditLog.resource_type == "rotation_pattern",
                AuditLog.resource_id.in_([str(i) for i in pids])))
            await db.execute(delete(AuditLog).where(
                AuditLog.resource_type == "roster_entry",
                AuditLog.resource_id.in_([str(i) for i in eids])))
            await db.execute(delete(AuditLog).where(
                AuditLog.action == "roster.bulk_publish",
                AuditLog.user_id.in_(uids)))
            await db.execute(delete(RosterEntry).where(
                RosterEntry.employee_id.in_(uids)))
            await db.execute(delete(RotationPattern).where(
                RotationPattern.name.like(f"%{sfx}")))
            await db.execute(delete(ScheduleDelegation).where(
                ScheduleDelegation.grantee_id.in_(uids)))
            await db.execute(delete(Employee).where(Employee.user_id.in_(uids)))
            await db.execute(delete(Department).where(
                Department.name.in_([dept_x, dept_y])))
            await db.execute(delete(ShiftTemplate).where(
                ShiftTemplate.name.like(f"RPT_{sfx}")))
            await db.execute(delete(User).where(User.id.in_(uids)))
            await db.commit()


async def _login(client, email):
    r = await client.post(f"{settings.API_V1_STR}/auth/login",
                          data={"username": email, "password": PW})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _grant(w, *, can_publish, emps=("e1", "e2")):
    async with SessionLocal() as db:
        db.add(ScheduleDelegation(
            grantee_id=w["ids"]["deleg"], scope_type=DelegationScope.EMPLOYEES,
            employee_ids=[w["ids"][e] for e in emps], can_publish=can_publish,
            valid_from=TODAY - timedelta(days=1)))
        await db.commit()


async def _mkpat(client, w, name="p", cycle=None):
    h = await _login(client, w["admin_email"])
    t1 = w["ids"]["t1"]
    r = await client.post(f"{ROSTER}/rotations", headers=h, json={
        "name": f"{name}{w['sfx']}", "cycle": cycle or [t1, t1, None, None]})
    assert r.status_code == 200, r.text
    return r.json()["id"], h


def _apply_body(w, emps, **kw):
    b = {"employee_ids": [w["ids"][e] for e in emps],
         "start": D.isoformat(), "end": (D + timedelta(days=3)).isoformat(),
         "anchor": D.isoformat()}
    b.update(kw)
    return b


async def _cells(uid):
    async with SessionLocal() as db:
        rows = (await db.execute(select(RosterEntry).where(
            RosterEntry.employee_id == uid).order_by(RosterEntry.work_date))
        ).scalars().all()
        return [(r.work_date, r.shift_template_id, r.is_week_off, r.status)
                for r in rows]


async def test_create_validation(client, world):
    ha = await _login(client, world["admin_email"])
    hd = await _login(client, world["email"])
    sfx, t1 = world["sfx"], world["ids"]["t1"]
    body = {"name": f"v{sfx}", "cycle": [t1, None]}
    assert (await client.post(f"{ROSTER}/rotations", json=body, headers=hd)
            ).status_code == 403
    for cyc in ([99999999], [world["ids"]["t3"]], [], [t1] * 57):
        r = await client.post(f"{ROSTER}/rotations", headers=ha,
                              json={"name": f"v{sfx}", "cycle": cyc})
        assert r.status_code == 422, (cyc, r.text)
    assert (await client.post(f"{ROSTER}/rotations", json=body, headers=ha)
            ).status_code == 200
    assert (await client.post(f"{ROSTER}/rotations", json=body, headers=ha)
            ).status_code == 409


async def test_list_update_delete(client, world):
    pid, ha = await _mkpat(client, world)
    hd = await _login(client, world["email"])
    assert (await client.get(f"{ROSTER}/rotations", headers=hd)).status_code == 403
    await _grant(world, can_publish=False)
    r = await client.get(f"{ROSTER}/rotations", headers=hd)
    assert pid in [x["id"] for x in r.json()]
    up = await client.patch(f"{ROSTER}/rotations/{pid}", headers=ha,
                            json={"description": "d"})
    assert up.status_code == 200 and up.json()["description"] == "d"
    assert (await client.delete(f"{ROSTER}/rotations/{pid}", headers=ha)
            ).status_code == 200
    r = await client.get(f"{ROSTER}/rotations", headers=hd)
    assert pid not in [x["id"] for x in r.json()]
    r = await client.get(f"{ROSTER}/rotations?include_inactive=true", headers=ha)
    assert pid in [x["id"] for x in r.json()]
    ap = await client.post(f"{ROSTER}/rotations/{pid}/apply", headers=ha,
                           json=_apply_body(world, ["e1"]))
    assert ap.status_code == 409


async def test_apply_default_draft_and_admin_published(client, world):
    pid, ha = await _mkpat(client, world)
    t1, e1, e2 = world["ids"]["t1"], world["ids"]["e1"], world["ids"]["e2"]
    r = await client.post(f"{ROSTER}/rotations/{pid}/apply", headers=ha,
                          json=_apply_body(world, ["e1", "e2"],
                                           offsets={str(e2): 2}))
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 8 and r.json()["errors"] == []
    c1, c2 = await _cells(e1), await _cells(e2)
    assert {c[3] for c in c1} == {"draft"}
    assert [c[1] for c in c1] == [t1, t1, None, None]
    assert [c[2] for c in c1] == [False, False, True, True]
    assert [c[1] for c in c2] == [None, None, t1, t1]  # offset 2
    r = await client.post(f"{ROSTER}/rotations/{pid}/apply", headers=ha,
                          json=_apply_body(world, ["e1"], status="published"))
    assert r.json()["updated"] == 4
    assert {c[3] for c in await _cells(e1)} == {"published"}
    bad = await client.post(f"{ROSTER}/rotations/{pid}/apply", headers=ha,
                            json=_apply_body(world, ["e1"], status="bogus"))
    assert bad.status_code == 422


async def test_delegate_publish_rules(client, world):
    pid, _ = await _mkpat(client, world)
    hd = await _login(client, world["email"])
    e1, e2, e3 = world["ids"]["e1"], world["ids"]["e2"], world["ids"]["e3"]
    await _grant(world, can_publish=False)
    r = await client.post(f"{ROSTER}/rotations/{pid}/apply", headers=hd,
                          json=_apply_body(world, ["e1", "e2", "e3"],
                                           status="published"))
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["out_of_scope"] == [e3] and j["created"] == 8
    assert len(j["errors"]) == 2
    assert all("Saved as draft" in m for m in j["errors"])
    assert await _cells(e3) == []
    assert {c[3] for c in await _cells(e1)} == {"draft"}
    # now with can_publish on e1 only
    async with SessionLocal() as db:
        await db.execute(delete(ScheduleDelegation).where(
            ScheduleDelegation.grantee_id == world["ids"]["deleg"]))
        await db.commit()
    await _grant(world, can_publish=True, emps=("e1",))
    await _grant(world, can_publish=False, emps=("e2",))
    r = await client.post(f"{ROSTER}/rotations/{pid}/apply", headers=hd,
                          json=_apply_body(world, ["e1", "e2"],
                                           status="published"))
    j = r.json()
    assert len(j["errors"]) == 1 and "RP e2" in j["errors"][0]
    assert {c[3] for c in await _cells(e1)} == {"published"}
    assert {c[3] for c in await _cells(e2)} == {"draft"}


async def test_entry_enforcement(client, world):
    hd = await _login(client, world["email"])
    ha = await _login(client, world["admin_email"])
    e1, t1 = world["ids"]["e1"], world["ids"]["t1"]
    await _grant(world, can_publish=False)
    d1, d2 = D, D + timedelta(days=1)
    # POST published -> downgraded to draft
    r = await client.post(f"{ROSTER}/entries", headers=hd, json={
        "employee_id": e1, "work_date": d1.isoformat(), "shift_template_id": t1})
    assert r.status_code == 200 and r.json()["status"] == "draft"
    draft_id = r.json()["id"]
    # admin publishes another cell
    r = await client.post(f"{ROSTER}/entries", headers=ha, json={
        "employee_id": e1, "work_date": d2.isoformat(), "shift_template_id": t1})
    assert r.json()["status"] == "published"
    pub_id = r.json()["id"]
    # non-publisher can't touch the live cell
    assert (await client.patch(f"{ROSTER}/entries/{pub_id}", headers=hd,
                               json={"note": "x"})).status_code == 403
    assert (await client.delete(f"{ROSTER}/entries/{pub_id}", headers=hd)
            ).status_code == 403
    assert (await client.post(f"{ROSTER}/entries", headers=hd, json={
        "employee_id": e1, "work_date": d2.isoformat(), "status": "draft",
        "is_week_off": True})).status_code == 403
    # drafts: editable, cannot self-publish, deletable
    assert (await client.patch(f"{ROSTER}/entries/{draft_id}", headers=hd,
                               json={"note": "x"})).status_code == 200
    assert (await client.patch(f"{ROSTER}/entries/{draft_id}", headers=hd,
                               json={"status": "published"})).status_code == 403
    assert (await client.patch(f"{ROSTER}/entries/{draft_id}", headers=hd,
                               json={"status": "weird"})).status_code == 422
    assert (await client.delete(f"{ROSTER}/entries/{draft_id}", headers=hd)
            ).status_code == 200
    assert (await client.delete(f"{ROSTER}/entries/{pub_id}", headers=ha)
            ).status_code == 200


async def test_bulk_overwrite_protects_published(client, world):
    hd = await _login(client, world["email"])
    ha = await _login(client, world["admin_email"])
    e1, t1, t2 = world["ids"]["e1"], world["ids"]["t1"], world["ids"]["t2"]
    await _grant(world, can_publish=False)
    r = await client.post(f"{ROSTER}/entries", headers=ha, json={
        "employee_id": e1, "work_date": D.isoformat(), "shift_template_id": t1})
    assert r.json()["status"] == "published"
    wd = D.weekday()
    r = await client.post(f"{ROSTER}/bulk", headers=hd, json={
        "employee_ids": [e1], "start": D.isoformat(),
        "end": (D + timedelta(days=1)).isoformat(),
        "pattern": {str(wd): t2, str((wd + 1) % 7): t2},
        "status": "draft", "overwrite": True})
    assert r.status_code == 200, r.text
    assert r.json()["skipped"] == 1 and r.json()["created"] == 1
    cells = await _cells(e1)
    assert cells[0][1:] == (t1, False, "published")
    assert cells[1][3] == "draft"
    # published request via bulk -> drafts + error
    r = await client.post(f"{ROSTER}/bulk", headers=hd, json={
        "employee_ids": [e1], "start": (D + timedelta(days=5)).isoformat(),
        "end": (D + timedelta(days=5)).isoformat(),
        "pattern": {str((D + timedelta(days=5)).weekday()): t2}})
    assert len(r.json()["errors"]) == 1
    assert (await _cells(e1))[-1][3] == "draft"


# ----------------------------- review fixes -----------------------------

async def test_apply_select_count_bounded(client, world):
    from sqlalchemy import event
    pid, ha = await _mkpat(client, world, cycle=[world["ids"]["t1"], None])
    stmts = []

    def _count(conn, cursor, statement, *a):
        if statement.lstrip().upper().startswith("SELECT"):
            stmts.append(statement)

    sync_engine = SessionLocal.kw["bind"].sync_engine
    event.listen(sync_engine, "before_cursor_execute", _count)
    try:
        r = await client.post(
            f"{ROSTER}/rotations/{pid}/apply", headers=ha,
            json=_apply_body(world, ["e1", "e2", "e3"],
                             end=(D + timedelta(days=13)).isoformat()))
    finally:
        event.remove(sync_engine, "before_cursor_execute", _count)
    assert r.status_code == 200 and r.json()["created"] == 42
    assert len(stmts) < 25, len(stmts)  # 42 cells; not per-cell


async def test_validation_fixes(client, world):
    ha = await _login(client, world["admin_email"])
    e1, t1, t3 = world["ids"]["e1"], world["ids"]["t1"], world["ids"]["t3"]
    r = await client.post(f"{ROSTER}/entries", headers=ha, json={
        "employee_id": e1, "work_date": D.isoformat(), "shift_template_id": t1})
    eid = r.json()["id"]
    assert (await client.patch(f"{ROSTER}/entries/{eid}", headers=ha,
                               json={"shift_template_id": 99999999})
            ).status_code == 422
    assert (await client.patch(f"{ROSTER}/entries/{eid}", headers=ha,
                               json={"shift_template_id": t3})
            ).status_code == 422
    assert (await client.patch(f"{ROSTER}/entries/{eid}", headers=ha,
                               json={"is_week_off": None})).status_code == 422
    assert (await client.post(f"{ROSTER}/entries", headers=ha, json={
        "employee_id": e1, "work_date": D.isoformat(),
        "shift_template_id": 99999999})).status_code == 422
    assert (await client.post(f"{ROSTER}/bulk", headers=ha, json={
        "employee_ids": [e1], "start": D.isoformat(), "end": D.isoformat(),
        "pattern": {"0": 99999999}})).status_code == 422
    # week-off clears the template
    r = await client.patch(f"{ROSTER}/entries/{eid}", headers=ha,
                           json={"is_week_off": True})
    assert r.status_code == 200 and r.json()["shift_template_id"] is None
    # bool in cycle rejected
    r = await client.post(f"{ROSTER}/rotations", headers=ha, json={
        "name": f"b{world['sfx']}", "cycle": [True, None]})
    assert r.status_code == 422
    # inactive template at apply time
    pid, _ = await _mkpat(client, world, name="stale")
    async with SessionLocal() as db:
        t = await db.get(ShiftTemplate, t1)
        t.is_active = False
        await db.commit()
    try:
        r = await client.post(f"{ROSTER}/rotations/{pid}/apply", headers=ha,
                              json=_apply_body(world, ["e1"]))
        assert r.status_code == 422 and str(t1) in r.text
    finally:
        async with SessionLocal() as db:
            t = await db.get(ShiftTemplate, t1)
            t.is_active = True
            await db.commit()


async def test_inactive_name_message_and_no_scope_apply(client, world):
    pid, ha = await _mkpat(client, world, name="dup")
    await client.delete(f"{ROSTER}/rotations/{pid}", headers=ha)
    r = await client.post(f"{ROSTER}/rotations", headers=ha, json={
        "name": f"dup{world['sfx']}", "cycle": [None]})
    assert r.status_code == 409 and "inactive" in r.text
    pid2, _ = await _mkpat(client, world, name="live")
    hd = await _login(client, world["email"])
    r = await client.post(f"{ROSTER}/rotations/{pid2}/apply", headers=hd,
                          json=_apply_body(world, ["e1"]))
    assert r.status_code == 403


async def test_downgrade_notice_and_message_only_when_written(client, world):
    hd = await _login(client, world["email"])
    ha = await _login(client, world["admin_email"])
    e1, t1 = world["ids"]["e1"], world["ids"]["t1"]
    await _grant(world, can_publish=False)
    r = await client.post(f"{ROSTER}/entries", headers=hd, json={
        "employee_id": e1, "work_date": D.isoformat(), "shift_template_id": t1})
    assert r.json()["notice"] == "Saved as draft: publishing requires HR approval"
    # all cells skipped (live) => no downgrade message
    await client.post(f"{ROSTER}/entries", headers=ha, json={
        "employee_id": e1, "work_date": (D + timedelta(days=9)).isoformat(),
        "shift_template_id": t1})
    r = await client.post(f"{ROSTER}/bulk", headers=hd, json={
        "employee_ids": [e1], "start": (D + timedelta(days=9)).isoformat(),
        "end": (D + timedelta(days=9)).isoformat(),
        "pattern": {str((D + timedelta(days=9)).weekday()): t1}})
    assert r.json()["skipped"] == 1 and r.json()["errors"] == []


async def test_commit_or_409_helper():
    from fastapi import HTTPException
    from sqlalchemy.exc import IntegrityError
    from app.api.v1.endpoints.roster import _commit_or_409

    class FakeDB:
        rolled = False

        async def commit(self):
            raise IntegrityError("x", {}, Exception("dup"))

        async def rollback(self):
            self.rolled = True

    db = FakeDB()
    with pytest.raises(HTTPException) as ei:
        await _commit_or_409(db)
    assert ei.value.status_code == 409 and db.rolled
