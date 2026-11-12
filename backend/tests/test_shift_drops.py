"""Give-away (drop shift) requests (Roadmap v2 Phase 1B, Task 4)."""
import asyncio
import uuid
from datetime import date, time, timedelta, datetime, timezone

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
from app.models.department import Department
from app.models.employee import Employee, EmployeeStatus
from app.models.notification import Notification
from app.models.open_shift import OpenShift, OpenShiftClaim, ShiftDropRequest
from app.models.roster import (
    RosterChangeRequest, RosterEntry, RosterEntryHistory, RosterStatus,
)
from app.models.schedule_delegation import DelegationScope, ScheduleDelegation
from app.models.shift import ShiftTemplate
from app.models.user import User

DR = f"{settings.API_V1_STR}/roster/drops"
OS = f"{settings.API_V1_STR}/roster/open-shifts"
PW = "test@12345"
TODAY = datetime.now(timezone.utc).date()
D = TODAY + timedelta(days=10)


def dd(n=0):
    return (D + timedelta(days=n)).isoformat()


def dn(n=0):
    return D + timedelta(days=n)


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
    dept_x, dept_y = f"DX{sfx}", f"DY{sfx}"
    try:
        async with SessionLocal() as db:
            def mk(tag, **kw):
                return User(email=f"dr_{tag}_{sfx}@t.com", full_name=f"DR {tag}",
                            hashed_password=get_password_hash(PW),
                            is_active=True, **kw)
            us = {t: mk(t) for t in (
                "e1", "e2", "e3", "e4", "sx", "sy", "deleg")}
            us["admin"] = mk("admin", is_superuser=True)
            db.add_all(us.values())
            db.add_all([Department(name=dept_x), Department(name=dept_y)])
            t1 = ShiftTemplate(name=f"DRT1{sfx}", start_time=time(9), end_time=time(17))
            t2 = ShiftTemplate(name=f"DRT2{sfx}", start_time=time(14), end_time=time(22))
            db.add_all([t1, t2])
            await db.commit()
            for tag, dept in (("e1", dept_x), ("e2", dept_x), ("e3", dept_x),
                              ("e4", dept_y)):
                db.add(Employee(
                    user_id=us[tag].id, employee_id=f"DR{sfx}{tag}",
                    department=dept, designation="Tester",
                    date_of_joining=date(2020, 1, 1),
                    status=EmployeeStatus.ACTIVE))
            await db.execute(Department.__table__.update().where(
                Department.name == dept_x).values(head_user_id=us["sx"].id))
            await db.execute(Department.__table__.update().where(
                Department.name == dept_y).values(head_user_id=us["sy"].id))
            # approve-only delegate for e1 (cannot publish)
            db.add(ScheduleDelegation(
                grantee_id=us["deleg"].id, scope_type=DelegationScope.EMPLOYEES,
                employee_ids=[us["e1"].id], can_approve_changes=True,
                can_publish=False, valid_from=TODAY - timedelta(days=1)))
            await db.commit()
            ids = {t: u.id for t, u in us.items()}
            ids.update(t1=t1.id, t2=t2.id)
        yield {"ids": ids, "sfx": sfx, "dept": dept_x,
               "email": lambda t: f"dr_{t}_{sfx}@t.com"}
    finally:
        async with SessionLocal() as db:
            uids = list((await db.execute(select(User.id).where(
                User.email.like(f"dr\\_%\\_{sfx}@t.com")))).scalars().all())
            await db.execute(delete(AuditLog).where(
                AuditLog.user_id.in_(uids), AuditLog.action.like("roster.%")))
            drop_ids = [str(i) for i in (await db.execute(
                select(ShiftDropRequest.id).where(
                    ShiftDropRequest.user_id.in_(uids)))).scalars().all()]
            shift_ids = [str(i) for i in (await db.execute(
                select(OpenShift.id).where(
                    OpenShift.created_by_id.in_(uids)))).scalars().all()]
            await db.execute(delete(Notification).where(
                Notification.user_id.in_(uids)))
            for rt, rids in (("shift_drop", drop_ids), ("open_shift", shift_ids)):
                if rids:
                    await db.execute(delete(Notification).where(
                        Notification.resource_type == rt,
                        Notification.resource_id.in_(rids)))
            await db.execute(delete(ShiftDropRequest).where(
                ShiftDropRequest.user_id.in_(uids)))
            await db.execute(delete(OpenShiftClaim).where(
                OpenShiftClaim.user_id.in_(uids)))
            await db.execute(delete(OpenShift).where(
                OpenShift.created_by_id.in_(uids)))
            await db.execute(delete(RosterChangeRequest).where(
                RosterChangeRequest.employee_id.in_(uids)))
            await db.execute(Department.__table__.update().where(
                Department.name.in_([dept_x, dept_y])).values(
                head_user_id=None, deputy_head_user_id=None))
            await db.execute(delete(RosterEntryHistory).where(
                RosterEntryHistory.employee_id.in_(uids)))
            await db.execute(delete(RosterEntry).where(
                RosterEntry.employee_id.in_(uids)))
            await db.execute(delete(ScheduleDelegation).where(
                ScheduleDelegation.grantee_id.in_(uids)))
            await db.execute(delete(Employee).where(Employee.user_id.in_(uids)))
            await db.execute(delete(Department).where(
                Department.name.in_([dept_x, dept_y])))
            tids = list((await db.execute(select(ShiftTemplate.id).where(
                ShiftTemplate.name.in_([f"DRT1{sfx}", f"DRT2{sfx}"])))).scalars().all())
            await purge_shift_templates(db, tids)
            await db.execute(delete(User).where(User.id.in_(uids)))
            await db.commit()


async def _h(client, w, tag):
    r = await client.post(f"{settings.API_V1_STR}/auth/login",
                          data={"username": w["email"](tag), "password": PW})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _pub(uid, day, tpl=None, off=False, status=RosterStatus.PUBLISHED):
    async with SessionLocal() as db:
        db.add(RosterEntry(employee_id=uid, work_date=day,
                           shift_template_id=None if off else tpl,
                           is_week_off=off, status=status))
        await db.commit()


async def _cell(uid, day):
    async with SessionLocal() as db:
        r = (await db.execute(select(RosterEntry).where(
            RosterEntry.employee_id == uid, RosterEntry.work_date == day,
            RosterEntry.status == RosterStatus.PUBLISHED))).scalars().first()
        return None if r is None else (r.shift_template_id, r.is_week_off)


async def _notes(uid, title):
    async with SessionLocal() as db:
        return list((await db.execute(select(Notification).where(
            Notification.user_id == uid, Notification.title == title
        ))).scalars().all())


async def _drop(client, w, who="e1", day=0, reason="family event"):
    return await client.post(DR, headers=await _h(client, w, who), json={
        "work_date": dd(day), "reason": reason})


async def _mk(client, w, who="e1", **kw):
    r = await _drop(client, w, who, **kw)
    assert r.status_code == 200, r.text
    return r.json()


async def _decide(client, w, did, who="sx", **body):
    body.setdefault("action", "approve")
    return await client.post(f"{DR}/{did}/decide",
                             headers=await _h(client, w, who), json=body)


# ------------------------------ create ------------------------------

async def test_create_validation(client, world):
    w, ids = world, world["ids"]
    r = await _drop(client, w)
    assert r.status_code == 400                       # no entry at all
    await _pub(ids["e1"], dn(), ids["t1"], status=RosterStatus.DRAFT)
    assert (await _drop(client, w)).status_code == 400  # draft only
    await _pub(ids["e1"], dn(1), off=True)
    assert (await _drop(client, w, day=1)).status_code == 400  # week-off
    past = TODAY - timedelta(days=1)
    await _pub(ids["e1"], past, ids["t1"])
    r = await client.post(DR, headers=await _h(client, w, "e1"), json={
        "work_date": past.isoformat(), "reason": "family event"})
    assert r.status_code == 400
    await _pub(ids["e1"], dn(2), ids["t1"])
    assert (await _drop(client, w, day=2, reason="ab")).status_code == 422
    r = await _drop(client, w, day=2)
    assert r.status_code == 200
    b = r.json()
    assert b["status"] == "pending" and b["shift_template_id"] == ids["t1"]
    assert b["shift_name"] == f"DRT1{w['sfx']}" and b["user_name"] == "DR e1"
    assert (await _drop(client, w, day=2)).status_code == 409   # duplicate


async def test_create_notifies_approvers_who_can_decide(client, world):
    w, ids = world, world["ids"]
    await _pub(ids["e1"], dn(), ids["t1"])
    d = await _mk(client, w)
    for tag, n in (("sx", 1), ("deleg", 1), ("sy", 0), ("e2", 0), ("e1", 0)):
        got = [x for x in await _notes(ids[tag], "Shift give-away request")
               if x.resource_id == str(d["id"])]
        assert len(got) == n, tag
    # everyone notified can actually decide
    assert (await _decide(client, w, d["id"], "deleg", action="reject")
            ).status_code == 200


async def test_lists_and_cancel(client, world):
    w, ids = world, world["ids"]
    await _pub(ids["e1"], dn(), ids["t1"])
    d = await _mk(client, w)
    r = await client.get(f"{DR}/my", headers=await _h(client, w, "e1"))
    assert [x["id"] for x in r.json()] == [d["id"]]
    for tag, seen in (("sx", True), ("deleg", True), ("admin", True),
                      ("sy", False), ("e1", False), ("e2", False)):
        r = await client.get(DR, headers=await _h(client, w, tag))
        assert (d["id"] in {x["id"] for x in r.json()}) is seen, tag
    r = await client.post(f"{DR}/{d['id']}/cancel", headers=await _h(client, w, "e2"))
    assert r.status_code == 403
    r = await client.post(f"{DR}/{d['id']}/cancel", headers=await _h(client, w, "e1"))
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert (await client.post(f"{DR}/{d['id']}/cancel",
                              headers=await _h(client, w, "e1"))).status_code == 409
    assert (await _decide(client, w, d["id"])).status_code == 409
    assert await _cell(ids["e1"], dn()) == (ids["t1"], False)
    assert (await _drop(client, w)).status_code == 200      # can re-request


# ------------------------------ decide ------------------------------

async def test_approve_with_open_shift(client, world):
    w, ids = world, world["ids"]
    await _pub(ids["e1"], dn(), ids["t1"])
    d = await _mk(client, w)
    r = await _decide(client, w, d["id"], note="ok")
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["status"] == "approved" and b["post_open_shift"] is True
    assert b["open_shift_id"] and b["open_shift_skipped_reason"] is None
    assert await _cell(ids["e1"], dn()) == (None, True)
    async with SessionLocal() as db:
        h = (await db.execute(select(RosterEntryHistory).where(
            RosterEntryHistory.employee_id == ids["e1"]))).scalars().all()
        assert len(h) == 1
        assert h[0].reason == f"Shift give-away #{d['id']}: family event"
        assert h[0].old_shift_template_id == ids["t1"] and h[0].new_is_week_off
        assert h[0].changed_by_id == ids["sx"]
        s = await db.get(OpenShift, b["open_shift_id"])
        assert s.slots == 1 and s.shift_template_id == ids["t1"]
        assert s.work_date == dn() and s.department == w["dept"]
        assert s.source_drop_id == d["id"] and s.excluded_user_id == ids["e1"]
        assert s.created_by_id == ids["sx"]
    assert len(await _notes(ids["e1"], "Schedule changed")) == 1
    assert len(await _notes(ids["e1"], "Shift give-away approved")) == 1
    # the dropper cannot take it back and is not notified; a colleague is
    sid = b["open_shift_id"]
    assert [x for x in await _notes(ids["e1"], "Open shift available")
            if x.resource_id == str(sid)] == []
    assert len([x for x in await _notes(ids["e3"], "Open shift available")
                if x.resource_id == str(sid)]) == 1
    r = await client.post(f"{OS}/{sid}/claim", headers=await _h(client, w, "e1"))
    assert r.status_code == 400 and "gave away" in r.json()["error"]["message"]
    r = await client.post(f"{OS}/{sid}/claim", headers=await _h(client, w, "e3"))
    assert r.status_code == 200
    assert (await _decide(client, w, d["id"])).status_code == 409


async def test_approve_without_open_shift(client, world):
    w, ids = world, world["ids"]
    await _pub(ids["e1"], dn(), ids["t1"])
    d = await _mk(client, w)
    r = await _decide(client, w, d["id"], post_open_shift=False)
    assert r.status_code == 200
    assert r.json()["open_shift_id"] is None and r.json()["post_open_shift"] is False
    assert r.json()["open_shift_skipped_reason"] is None
    assert await _cell(ids["e1"], dn()) == (None, True)
    async with SessionLocal() as db:
        assert (await db.execute(select(OpenShift).where(
            OpenShift.source_drop_id == d["id"]))).scalars().all() == []


async def test_reject(client, world):
    w, ids = world, world["ids"]
    await _pub(ids["e1"], dn(), ids["t1"])
    d = await _mk(client, w)
    r = await _decide(client, w, d["id"], action="reject", note="busy")
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    assert r.json()["decision_note"] == "busy"
    assert await _cell(ids["e1"], dn()) == (ids["t1"], False)
    n = await _notes(ids["e1"], "Shift give-away rejected")
    assert len(n) == 1 and "busy" in n[0].message


async def test_decide_authorization(client, world):
    w, ids = world, world["ids"]
    await _pub(ids["e1"], dn(), ids["t1"])
    d = await _mk(client, w)
    for tag in ("e2", "e1", "sy"):
        assert (await _decide(client, w, d["id"], tag)).status_code == 403, tag
    assert (await _decide(client, w, 999999)).status_code == 404
    assert (await _decide(client, w, d["id"], action="x")).status_code == 422


async def test_self_approval_blocked_unless_admin(client, world):
    w, ids = world, world["ids"]
    async with SessionLocal() as db:   # e3 heads the dept
        await db.execute(Department.__table__.update().where(
            Department.name == w["dept"]).values(head_user_id=ids["e3"]))
        await db.commit()
    await _pub(ids["e3"], dn(), ids["t1"])
    d = await _mk(client, w, who="e3")
    assert (await _decide(client, w, d["id"], "e3")).status_code == 403
    assert (await _decide(client, w, d["id"], "admin")).status_code == 200


async def test_approver_without_publish_rights(client, world):
    w, ids = world, world["ids"]
    await _pub(ids["e1"], dn(), ids["t1"])
    d = await _mk(client, w)
    # explicit post_open_shift=true: 400 and nothing changed
    r = await _decide(client, w, d["id"], "deleg", post_open_shift=True)
    assert r.status_code == 400 and "publish rights" in r.json()["error"]["message"]
    assert await _cell(ids["e1"], dn()) == (ids["t1"], False)
    async with SessionLocal() as db:
        assert (await db.get(ShiftDropRequest, d["id"])).status == "pending"
    # defaulted: approves, skips posting and says why
    r = await _decide(client, w, d["id"], "deleg")
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["status"] == "approved" and b["open_shift_id"] is None
    assert "publish" in b["open_shift_skipped_reason"]
    assert await _cell(ids["e1"], dn()) == (None, True)


async def test_stale_entry_409(client, world):
    w, ids = world, world["ids"]
    await _pub(ids["e1"], dn(), ids["t1"])
    await _pub(ids["e1"], dn(1), ids["t1"])
    d1 = await _mk(client, w)
    d2 = await _mk(client, w, day=1)
    async with SessionLocal() as db:
        rows = (await db.execute(select(RosterEntry).where(
            RosterEntry.employee_id == ids["e1"]))).scalars().all()
        for e in rows:
            if e.work_date == dn():
                e.shift_template_id = ids["t2"]          # template changed
            else:
                e.shift_template_id, e.is_week_off = None, True  # now off
        await db.commit()
    assert (await _decide(client, w, d1["id"])).status_code == 409
    assert (await _decide(client, w, d2["id"])).status_code == 409
    assert await _cell(ids["e1"], dn()) == (ids["t2"], False)
    async with SessionLocal() as db:
        assert (await db.get(ShiftDropRequest, d1["id"])).status == "pending"


async def test_supersedes_pending_change_request(client, world):
    w, ids = world, world["ids"]
    await _pub(ids["e1"], dn(), ids["t1"])
    d = await _mk(client, w)
    async with SessionLocal() as db:
        db.add(RosterChangeRequest(
            employee_id=ids["e1"], work_date=dn(),
            requested_shift_template_id=ids["t2"], reason="swap me",
            status="pending"))
        await db.commit()
    assert (await _decide(client, w, d["id"], post_open_shift=False)
            ).status_code == 200
    async with SessionLocal() as db:
        c = (await db.execute(select(RosterChangeRequest).where(
            RosterChangeRequest.employee_id == ids["e1"]))).scalars().one()
        assert c.status == "cancelled"
    assert len(await _notes(ids["e1"], "Change request superseded")) == 1


async def test_double_decide_concurrent(client, world):
    w, ids = world, world["ids"]
    await _pub(ids["e1"], dn(), ids["t1"])
    d = await _mk(client, w)
    h = await _h(client, w, "sx")
    r1, r2 = await asyncio.gather(
        client.post(f"{DR}/{d['id']}/decide", headers=h, json={"action": "approve"}),
        client.post(f"{DR}/{d['id']}/decide", headers=h, json={"action": "approve"}))
    assert sorted([r1.status_code, r2.status_code]) == [200, 409], (r1.text, r2.text)
    async with SessionLocal() as db:
        assert len((await db.execute(select(RosterEntryHistory).where(
            RosterEntryHistory.employee_id == ids["e1"]))).scalars().all()) == 1
        assert len((await db.execute(select(OpenShift).where(
            OpenShift.source_drop_id == d["id"]))).scalars().all()) == 1


async def test_concurrent_create_one_wins(client, world):
    w, ids = world, world["ids"]
    await _pub(ids["e1"], dn(), ids["t1"])
    r1, r2 = await asyncio.gather(_drop(client, w), _drop(client, w))
    assert sorted([r1.status_code, r2.status_code]) == [200, 409], (r1.text, r2.text)
