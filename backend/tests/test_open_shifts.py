"""Open shifts (Roadmap v2 Phase 1B, Task 3)."""
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
from app.models.availability import EmployeeAvailability
from app.models.department import Department
from app.models.employee import Employee, EmployeeStatus
from app.models.leave import LeaveRequest, LeaveStatus, LeaveType
from app.models.notification import Notification
from app.models.open_shift import OpenShift, OpenShiftClaim
from app.models.roster import (
    RosterChangeRequest, RosterEntry, RosterEntryHistory, RosterStatus,
)
from app.models.shift import ShiftTemplate
from app.models.system import SystemSetting
from app.models.user import User
from app.services import open_shifts as os_svc
from app.services.time_rules import set_time_rules

API = f"{settings.API_V1_STR}/roster/open-shifts"
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
    dept_x, dept_y = f"OX{sfx}", f"OY{sfx}"
    loc = f"LOC{sfx}"
    try:
        async with SessionLocal() as db:
            def mk(tag, **kw):
                return User(email=f"os_{tag}_{sfx}@t.com", full_name=f"OS {tag}",
                            hashed_password=get_password_hash(PW),
                            is_active=True, **kw)
            us = {t: mk(t) for t in (
                "e1", "e2", "e3", "e4", "e5", "e6", "sx", "sy")}
            us["admin"] = mk("admin", is_superuser=True)
            db.add_all(us.values())
            db.add_all([Department(name=dept_x), Department(name=dept_y)])
            t1 = ShiftTemplate(name=f"OST1{sfx}", start_time=time(9), end_time=time(17))
            t2 = ShiftTemplate(name=f"OST2{sfx}", start_time=time(14), end_time=time(22))
            db.add_all([t1, t2])
            await db.commit()
            for tag, dept, st, lc in (
                ("e1", dept_x, EmployeeStatus.ACTIVE, None),
                ("e2", dept_x, EmployeeStatus.ACTIVE, loc),
                ("e3", dept_x, EmployeeStatus.ACTIVE, None),
                ("e4", dept_y, EmployeeStatus.ACTIVE, None),
                ("e5", dept_x, EmployeeStatus.INACTIVE, None),
                ("e6", dept_x, EmployeeStatus.ACTIVE, None),
            ):
                db.add(Employee(
                    user_id=us[tag].id, employee_id=f"OS{sfx}{tag}",
                    department=dept, designation="Tester", location=lc,
                    date_of_joining=date(2020, 1, 1), status=st))
            await db.execute(Department.__table__.update().where(
                Department.name == dept_x).values(head_user_id=us["sx"].id))
            await db.execute(Department.__table__.update().where(
                Department.name == dept_y).values(head_user_id=us["sy"].id))
            await db.commit()
            ids = {t: u.id for t, u in us.items()}
            ids.update(t1=t1.id, t2=t2.id)
        yield {"ids": ids, "sfx": sfx, "dept": dept_x, "deptY": dept_y,
               "loc": loc, "email": lambda t: f"os_{t}_{sfx}@t.com"}
    finally:
        async with SessionLocal() as db:
            uids = list((await db.execute(select(User.id).where(
                User.email.like(f"os\\_%\\_{sfx}@t.com")))).scalars().all())
            await db.execute(delete(AuditLog).where(
                AuditLog.user_id.in_(uids), AuditLog.action.like("roster.%")))
            await db.execute(delete(Notification).where(
                Notification.user_id.in_(uids)))
            # company-wide shifts also notify real dev-DB employees
            shift_ids = [str(i) for i in (await db.execute(
                select(OpenShift.id).where(
                    OpenShift.created_by_id.in_(uids)))).scalars().all()]
            if shift_ids:
                await db.execute(delete(Notification).where(
                    Notification.resource_type == "open_shift",
                    Notification.resource_id.in_(shift_ids)))
            await db.execute(delete(OpenShiftClaim).where(
                OpenShiftClaim.user_id.in_(uids)))
            await db.execute(delete(OpenShift).where(
                OpenShift.created_by_id.in_(uids)))
            await db.execute(delete(LeaveRequest).where(
                LeaveRequest.employee_id.in_(uids)))
            await db.execute(delete(LeaveType).where(
                LeaveType.name == f"OSLV{sfx}"))
            await db.execute(delete(EmployeeAvailability).where(
                EmployeeAvailability.user_id.in_(uids)))
            await db.execute(delete(RosterChangeRequest).where(
                RosterChangeRequest.employee_id.in_(uids)))
            await db.execute(Department.__table__.update().where(
                Department.name.in_([dept_x, dept_y])).values(
                head_user_id=None, deputy_head_user_id=None))
            await db.execute(delete(RosterEntryHistory).where(
                RosterEntryHistory.employee_id.in_(uids)))
            await db.execute(delete(RosterEntry).where(
                RosterEntry.employee_id.in_(uids)))
            await db.execute(delete(Employee).where(Employee.user_id.in_(uids)))
            await db.execute(delete(Department).where(
                Department.name.in_([dept_x, dept_y])))
            tids = list((await db.execute(select(ShiftTemplate.id).where(
                ShiftTemplate.name.in_([f"OST1{sfx}", f"OST2{sfx}"])))).scalars().all())
            await purge_shift_templates(db, tids)
            await db.execute(delete(User).where(User.id.in_(uids)))
            await db.commit()


async def _login(client, email):
    r = await client.post(f"{settings.API_V1_STR}/auth/login",
                          data={"username": email, "password": PW})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _h(client, w, tag):
    return await _login(client, w["email"](tag))


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


async def _create(client, w, who="sx", **over):
    body = {"work_date": dd(), "shift_template_id": w["ids"]["t1"],
            "department": w["dept"], "slots": 1, "auto_confirm": False}
    body.update(over)
    return await client.post(API, headers=await _h(client, w, who), json=body)


async def _mk(client, w, **over):
    r = await _create(client, w, **over)
    assert r.status_code == 200, r.text
    return r.json()


async def _claim(client, w, sid, who):
    return await client.post(f"{API}/{sid}/claim", headers=await _h(client, w, who))


async def _decide(client, w, cid, action="approve", who="sx"):
    return await client.post(f"{API}/claims/{cid}/decide",
                             headers=await _h(client, w, who),
                             json={"action": action})


async def _notes(uid, title):
    async with SessionLocal() as db:
        return list((await db.execute(select(Notification).where(
            Notification.user_id == uid, Notification.title == title
        ))).scalars().all())


# ------------------------------ create ------------------------------

async def test_create_scope_and_validation(client, world):
    w, ids = world, world["ids"]
    h1 = await _h(client, w, "e1")
    r = await client.post(API, headers=h1, json={
        "work_date": dd(), "shift_template_id": ids["t1"], "slots": 1})
    assert r.status_code == 403
    # sy heads a different department: nobody in dept X is in scope
    assert (await _create(client, w, who="sy")).status_code == 403
    assert (await _create(client, w, work_date=(TODAY - timedelta(days=1)).isoformat())
            ).status_code == 400
    assert (await _create(client, w, slots=0)).status_code == 422
    assert (await _create(client, w, slots=51)).status_code == 422
    assert (await _create(client, w, shift_template_id=999999)).status_code == 400
    async with SessionLocal() as db:
        await db.execute(ShiftTemplate.__table__.update().where(
            ShiftTemplate.id == ids["t2"]).values(is_active=False))
        await db.commit()
    assert (await _create(client, w, shift_template_id=ids["t2"])).status_code == 400
    j = await _mk(client, w, note="  need cover  ")
    assert j["status"] == "open" and j["filled"] == 0 and j["slots"] == 1
    assert j["note"] == "need cover" and j["created_by_id"] == ids["sx"]
    assert j["shift_name"] == f"OST1{w['sfx']}" and j["claims"] == []


async def test_create_notifies_only_eligible_who_can_act(client, world):
    w, ids = world, world["ids"]
    await _pub(ids["e2"], dn(), ids["t2"])   # working that day -> not eligible
    j = await _mk(client, w)
    for tag, expect in (("e1", 1), ("e3", 1), ("e6", 1), ("e2", 0),
                        ("e4", 0), ("e5", 0), ("sx", 0)):
        n = [x for x in await _notes(ids[tag], "Open shift available")
             if x.resource_id == str(j["id"])]
        assert len(n) == expect, tag
    # everyone notified can actually claim
    assert (await _claim(client, w, j["id"], "e1")).status_code == 200


async def test_service_create_reusable_with_source_drop(client, world):
    w, ids = world, world["ids"]
    async with SessionLocal() as db:
        actor = await db.get(User, ids["sx"])
        s = await os_svc.create_open_shift(
            db, actor, work_date=dn(), shift_template_id=ids["t1"],
            department=w["dept"], slots=2, source_drop_id=77)
        await db.commit()
        sid = s.id
    async with SessionLocal() as db:
        s = await db.get(OpenShift, sid)
        assert s.source_drop_id == 77 and s.slots == 2
        assert len(await os_svc.eligible_user_ids(
            db, s, [ids["e1"], ids["e3"], ids["e4"], ids["e5"]])) == 2
    assert len([x for x in await _notes(ids["e1"], "Open shift available")
                if x.resource_id == str(sid)]) == 1


# ---------------------------- eligibility ----------------------------

async def test_eligibility_rules(client, world):
    w, ids = world, world["ids"]
    await _pub(ids["e2"], dn(), ids["t2"])                 # already working
    async with SessionLocal() as db:
        lt = LeaveType(name=f"OSLV{w['sfx']}")
        db.add(lt)
        await db.commit()
        db.add(LeaveRequest(
            employee_id=ids["e3"], leave_type_id=lt.id, start_date=dn(),
            end_date=dn(), is_half_day=False, reason="t",
            status=LeaveStatus.APPROVED, created_by_user_id=ids["e3"]))
        db.add(EmployeeAvailability(
            user_id=ids["e6"], kind="unavailable", specific_date=dn(),
            shift_template_id=ids["t1"]))
        await db.commit()
    j = await _mk(client, w)
    r = await _claim(client, w, j["id"], "e2")
    assert r.status_code == 400 and "scheduled" in r.json()["error"]["message"]
    r = await _claim(client, w, j["id"], "e3")
    assert r.status_code == 400 and "leave" in r.json()["error"]["message"]
    r = await _claim(client, w, j["id"], "e6")
    assert r.status_code == 400 and "unavailable" in r.json()["error"]["message"]
    r = await _claim(client, w, j["id"], "e4")
    assert r.status_code == 400 and "department" in r.json()["error"]["message"]
    async with SessionLocal() as db:
        s = await db.get(OpenShift, j["id"])
        reasons = await os_svc.eligibility_reasons(
            db, s, [ids["e1"], ids["e5"], ids["e4"]])
        assert reasons[ids["e1"]] is None
        assert "active" in reasons[ids["e5"]]
        # no department filter: creator's scope rule still excludes dept Y
        s.department = None
        reasons = await os_svc.eligibility_reasons(db, s, [ids["e4"]])
        assert "scope" in reasons[ids["e4"]]
        s.department, s.location = w["dept"], w["loc"]
        reasons = await os_svc.eligibility_reasons(db, s, [ids["e1"], ids["e6"]])
        assert all("location" in v for v in reasons.values())
        db.expunge(s)
    assert (await _claim(client, w, j["id"], "e1")).status_code == 200


async def test_eligibility_week_off_ok_and_past_date(client, world):
    w, ids = world, world["ids"]
    await _pub(ids["e1"], dn(), off=True)
    j = await _mk(client, w)
    assert (await _claim(client, w, j["id"], "e1")).status_code == 200
    async with SessionLocal() as db:
        s = await db.get(OpenShift, j["id"])
        s.work_date = TODAY - timedelta(days=1)
        assert "past" in await os_svc.eligible_reason(db, s, ids["e3"])
        db.expunge(s)


# ------------------------- claim / approve flow -------------------------

async def test_claim_approve_publishes_and_records_history(client, world):
    w, ids = world, world["ids"]
    j = await _mk(client, w)
    r = await _claim(client, w, j["id"], "e1")
    assert r.status_code == 200, r.text
    assert r.json()["my_claim_status"] == "pending" and len(r.json()["claims"]) == 1
    assert len(await _notes(ids["sx"], "Open shift claimed")) == 1
    cid = r.json()["my_claim_id"]
    assert (await _claim(client, w, j["id"], "e1")).status_code == 409
    r = await _decide(client, w, cid)
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["filled"] == 1 and b["status"] == "filled"
    assert b["claims"][0]["status"] == "approved"
    assert await _cell(ids["e1"], dn()) == (ids["t1"], False)
    async with SessionLocal() as db:
        hist = (await db.execute(select(RosterEntryHistory).where(
            RosterEntryHistory.employee_id == ids["e1"]))).scalars().all()
        assert len(hist) == 1 and hist[0].reason == f"Open shift #{j['id']}"
        assert hist[0].new_shift_template_id == ids["t1"]
        assert hist[0].changed_by_id == ids["sx"]
    assert len(await _notes(ids["e1"], "Open shift confirmed")) == 1
    assert (await _decide(client, w, cid)).status_code == 409   # already decided
    assert (await _claim(client, w, j["id"], "e3")).status_code == 409  # filled


async def test_slot_exhaustion_auto_rejects_others(client, world):
    w, ids = world, world["ids"]
    j = await _mk(client, w, slots=2)
    cids = {}
    for t in ("e1", "e3", "e6"):
        r = await _claim(client, w, j["id"], t)
        assert r.status_code == 200, r.text
        cids[t] = r.json()["my_claim_id"]
    r = await _decide(client, w, cids["e1"])
    assert r.json()["status"] == "open" and r.json()["filled"] == 1
    r = await _decide(client, w, cids["e3"])
    b = r.json()
    assert b["status"] == "filled" and b["filled"] == 2
    st = {c["user_id"]: c["status"] for c in b["claims"]}
    assert st == {ids["e1"]: "approved", ids["e3"]: "approved",
                  ids["e6"]: "rejected"}
    assert len(await _notes(ids["e6"], "Open shift claim rejected")) == 1
    assert await _cell(ids["e6"], dn()) is None


async def test_concurrent_approvals_last_slot(client, world):
    w, ids = world, world["ids"]
    j = await _mk(client, w, slots=1)
    c1 = (await _claim(client, w, j["id"], "e1")).json()["my_claim_id"]
    c3 = (await _claim(client, w, j["id"], "e3")).json()["my_claim_id"]
    h = await _h(client, w, "sx")
    r1, r2 = await asyncio.gather(
        client.post(f"{API}/claims/{c1}/decide", headers=h,
                    json={"action": "approve"}),
        client.post(f"{API}/claims/{c3}/decide", headers=h,
                    json={"action": "approve"}))
    assert sorted([r1.status_code, r2.status_code]) == [200, 409], (
        r1.text, r2.text)
    async with SessionLocal() as db:
        s = await db.get(OpenShift, j["id"])
        assert s.filled == 1 and s.status == "filled"
        n = (await db.execute(select(OpenShiftClaim).where(
            OpenShiftClaim.open_shift_id == j["id"],
            OpenShiftClaim.status == "approved"))).scalars().all()
        assert len(n) == 1
        cells = (await db.execute(select(RosterEntry).where(
            RosterEntry.employee_id.in_([ids["e1"], ids["e3"]])))).scalars().all()
        assert len(cells) == 1


async def test_concurrent_double_claim(client, world):
    w, ids = world, world["ids"]
    j = await _mk(client, w, slots=3)
    h = await _h(client, w, "e1")
    r1, r2 = await asyncio.gather(
        client.post(f"{API}/{j['id']}/claim", headers=h),
        client.post(f"{API}/{j['id']}/claim", headers=h))
    assert sorted([r1.status_code, r2.status_code]) == [200, 409], (r1.text, r2.text)
    async with SessionLocal() as db:
        n = (await db.execute(select(OpenShiftClaim).where(
            OpenShiftClaim.open_shift_id == j["id"]))).scalars().all()
        assert len(n) == 1


async def test_same_person_two_shifts_same_day_second_approve_fails(client, world):
    w, ids = world, world["ids"]
    j1 = await _mk(client, w)
    j2 = await _mk(client, w, shift_template_id=ids["t2"])
    c1 = (await _claim(client, w, j1["id"], "e1")).json()["my_claim_id"]
    c2 = (await _claim(client, w, j2["id"], "e1")).json()["my_claim_id"]
    h = await _h(client, w, "sx")
    r1, r2 = await asyncio.gather(
        client.post(f"{API}/claims/{c1}/decide", headers=h, json={"action": "approve"}),
        client.post(f"{API}/claims/{c2}/decide", headers=h, json={"action": "approve"}))
    codes = sorted([r1.status_code, r2.status_code])
    assert codes[0] == 200 and codes[1] in (400, 409), (r1.text, r2.text)
    win_tpl = ids["t1"] if r1.status_code == 200 else ids["t2"]
    async with SessionLocal() as db:
        cl = {c.id: c.status for c in (await db.execute(select(OpenShiftClaim).where(
            OpenShiftClaim.user_id == ids["e1"]))).scalars().all()}
    assert sorted(cl.values()) == ["approved", "pending"]
    assert cl[c1 if r1.status_code == 200 else c2] == "approved"
    assert await _cell(ids["e1"], dn()) == (win_tpl, False)


async def test_same_person_two_auto_confirm_shifts_concurrent(client, world):
    w, ids = world, world["ids"]
    j1 = await _mk(client, w, auto_confirm=True)
    j2 = await _mk(client, w, shift_template_id=ids["t2"], auto_confirm=True)
    h = await _h(client, w, "e1")
    r1, r2 = await asyncio.gather(
        client.post(f"{API}/{j1['id']}/claim", headers=h),
        client.post(f"{API}/{j2['id']}/claim", headers=h))
    codes = sorted([r1.status_code, r2.status_code])
    assert codes[0] == 200 and codes[1] in (400, 409), (r1.text, r2.text)
    win_tpl = ids["t1"] if r1.status_code == 200 else ids["t2"]
    async with SessionLocal() as db:
        cl = (await db.execute(select(OpenShiftClaim).where(
            OpenShiftClaim.user_id == ids["e1"]))).scalars().all()
        assert [c.status for c in cl] == ["approved"]
    assert await _cell(ids["e1"], dn()) == (win_tpl, False)


async def test_auto_confirm(client, world):
    w, ids = world, world["ids"]
    j = await _mk(client, w, slots=1, auto_confirm=True)
    r = await _claim(client, w, j["id"], "e1")
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["my_claim_status"] == "approved" and b["status"] == "filled"
    assert await _cell(ids["e1"], dn()) == (ids["t1"], False)
    async with SessionLocal() as db:
        h = (await db.execute(select(RosterEntryHistory).where(
            RosterEntryHistory.employee_id == ids["e1"]))).scalars().all()
        assert len(h) == 1 and h[0].changed_by_id == ids["sx"]
    assert (await _claim(client, w, j["id"], "e3")).status_code == 409


async def test_claim_supersedes_pending_change_request(client, world):
    w, ids = world, world["ids"]
    async with SessionLocal() as db:
        db.add(RosterChangeRequest(
            employee_id=ids["e1"], work_date=dn(), requested_week_off=True,
            reason="need off", status="pending"))
        await db.commit()
    j = await _mk(client, w, auto_confirm=True)
    assert (await _claim(client, w, j["id"], "e1")).status_code == 200
    async with SessionLocal() as db:
        c = (await db.execute(select(RosterChangeRequest).where(
            RosterChangeRequest.employee_id == ids["e1"]))).scalars().one()
        assert c.status == "cancelled"
    assert len(await _notes(ids["e1"], "Change request superseded")) == 1


async def test_blank_published_entry_uses_fallback_for_old(client, world):
    w, ids = world, world["ids"]
    await _pub(ids["e1"], dn(), None)   # published blank cell
    j = await _mk(client, w, auto_confirm=True)
    assert (await _claim(client, w, j["id"], "e1")).status_code == 200
    async with SessionLocal() as db:
        h = (await db.execute(select(RosterEntryHistory).where(
            RosterEntryHistory.employee_id == ids["e1"]))).scalars().one()
        assert (h.old_shift_template_id, h.old_is_week_off) == (None, False)
    assert await _cell(ids["e1"], dn()) == (ids["t1"], False)


async def test_approve_overwrites_draft_never_blank(client, world):
    w, ids = world, world["ids"]
    await _pub(ids["e1"], dn(), ids["t2"], status=RosterStatus.DRAFT)
    j = await _mk(client, w, auto_confirm=True)
    assert (await _claim(client, w, j["id"], "e1")).status_code == 200
    assert await _cell(ids["e1"], dn()) == (ids["t1"], False)
    # nobody else got a cell
    async with SessionLocal() as db:
        n = (await db.execute(select(RosterEntry).where(
            RosterEntry.employee_id.in_([ids["e3"], ids["e6"]])))).scalars().all()
        assert n == []


# --------------------- withdraw / reject / cancel ---------------------

async def test_withdraw_then_reclaim(client, world):
    w, ids = world, world["ids"]
    j = await _mk(client, w)
    cid = (await _claim(client, w, j["id"], "e1")).json()["my_claim_id"]
    h3 = await _h(client, w, "e3")
    r = await client.post(f"{API}/claims/{cid}/withdraw", headers=h3)
    assert r.status_code == 403
    h1 = await _h(client, w, "e1")
    r = await client.post(f"{API}/claims/{cid}/withdraw", headers=h1)
    assert r.status_code == 200 and r.json()["my_claim_status"] == "withdrawn"
    assert (await client.post(f"{API}/claims/{cid}/withdraw", headers=h1)
            ).status_code == 409
    assert (await _decide(client, w, cid)).status_code == 409
    r = await _claim(client, w, j["id"], "e1")
    assert r.status_code == 200 and r.json()["my_claim_status"] == "pending"
    assert r.json()["my_claim_id"] == cid


async def test_reject(client, world):
    w, ids = world, world["ids"]
    j = await _mk(client, w)
    cid = (await _claim(client, w, j["id"], "e1")).json()["my_claim_id"]
    r = await _decide(client, w, cid, "reject")
    assert r.status_code == 200 and r.json()["claims"][0]["status"] == "rejected"
    assert r.json()["status"] == "open" and r.json()["filled"] == 0
    assert len(await _notes(ids["e1"], "Open shift claim rejected")) == 1
    assert await _cell(ids["e1"], dn()) is None
    assert (await _claim(client, w, j["id"], "e1")).status_code == 409


async def test_cancel(client, world):
    w, ids = world, world["ids"]
    j = await _mk(client, w, slots=2)
    c1 = (await _claim(client, w, j["id"], "e1")).json()["my_claim_id"]
    await _claim(client, w, j["id"], "e3")
    assert (await _decide(client, w, c1)).status_code == 200
    he = await _h(client, w, "e1")
    assert (await client.post(f"{API}/{j['id']}/cancel", headers=he)).status_code == 403
    hy = await _h(client, w, "sy")
    assert (await client.post(f"{API}/{j['id']}/cancel", headers=hy)).status_code == 403
    r = await client.post(f"{API}/{j['id']}/cancel", headers=await _h(client, w, "sx"))
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    st = {c["user_id"]: c["status"] for c in r.json()["claims"]}
    assert st == {ids["e1"]: "approved", ids["e3"]: "rejected"}
    assert await _cell(ids["e1"], dn()) == (ids["t1"], False)   # kept
    assert len(await _notes(ids["e3"], "Open shift cancelled")) == 1
    assert (await client.post(f"{API}/{j['id']}/cancel",
                              headers=await _h(client, w, "sx"))).status_code == 409
    assert (await _claim(client, w, j["id"], "e6")).status_code == 409


async def test_admin_can_cancel_and_decide(client, world):
    w, ids = world, world["ids"]
    j = await _mk(client, w)
    cid = (await _claim(client, w, j["id"], "e1")).json()["my_claim_id"]
    assert (await _decide(client, w, cid, who="admin")).status_code == 200
    j2 = await _mk(client, w)
    r = await client.post(f"{API}/{j2['id']}/cancel", headers=await _h(client, w, "admin"))
    assert r.status_code == 200


async def test_decide_authorization(client, world):
    w, ids = world, world["ids"]
    j = await _mk(client, w)
    cid = (await _claim(client, w, j["id"], "e1")).json()["my_claim_id"]
    body = {"action": "approve"}
    url = f"{API}/claims/{cid}/decide"
    assert (await client.post(url, headers=await _h(client, w, "e3"), json=body)
            ).status_code == 403    # peer
    assert (await client.post(url, headers=await _h(client, w, "e1"), json=body)
            ).status_code == 403    # own claim
    assert (await client.post(url, headers=await _h(client, w, "sy"), json=body)
            ).status_code == 403    # other department head
    assert (await client.post(url, headers=await _h(client, w, "sx"),
                              json={"action": "nope"})).status_code == 422
    assert (await client.post(f"{API}/claims/999999/decide",
                              headers=await _h(client, w, "sx"), json=body)
            ).status_code == 404


async def test_approve_rechecks_eligibility(client, world):
    w, ids = world, world["ids"]
    j = await _mk(client, w)
    cid = (await _claim(client, w, j["id"], "e1")).json()["my_claim_id"]
    await _pub(ids["e1"], dn(), ids["t2"])   # scheduled elsewhere meanwhile
    r = await _decide(client, w, cid)
    assert r.status_code == 400 and "scheduled" in r.json()["error"]["message"]
    async with SessionLocal() as db:
        s = await db.get(OpenShift, j["id"])
        assert s.filled == 0 and s.status == "open"
    assert await _cell(ids["e1"], dn()) == (ids["t2"], False)


# ------------------------------- lists -------------------------------

async def test_lists(client, world):
    w, ids = world, world["ids"]
    await _pub(ids["e2"], dn(), ids["t2"])
    j = await _mk(client, w)
    far = await _mk(client, w, work_date=(TODAY + timedelta(days=90)).isoformat())
    cid = (await _claim(client, w, j["id"], "e1")).json()["my_claim_id"]
    h = await _h(client, w, "e1")
    r = await client.get(f"{API}/available", headers=h)
    assert r.status_code == 200
    mine = {x["id"]: x for x in r.json()}
    assert j["id"] in mine and far["id"] not in mine
    assert mine[j["id"]]["my_claim_status"] == "pending"
    assert all(c["user_id"] == ids["e1"] for c in mine[j["id"]]["claims"])
    r = await client.get(f"{API}/available", headers=await _h(client, w, "e2"))
    assert j["id"] not in {x["id"] for x in r.json()}   # working that day
    r = await client.get(f"{API}/available", headers=await _h(client, w, "e4"))
    assert j["id"] not in {x["id"] for x in r.json()}   # other department
    q = {"start": dd(-1), "end": dd(1)}
    r = await client.get(API, headers=await _h(client, w, "sx"), params=q)
    row = next(x for x in r.json() if x["id"] == j["id"])
    assert row["claims"][0]["eligibility_reason"] is None
    assert row["claims"][0]["user_name"] == "OS e1"
    r = await client.get(API, headers=await _h(client, w, "sy"), params=q)
    assert j["id"] not in {x["id"] for x in r.json()}   # not creator
    r = await client.get(API, headers=await _h(client, w, "admin"),
                         params={**q, "status": "open"})
    assert j["id"] in {x["id"] for x in r.json()}
    r = await client.get(API, headers=await _h(client, w, "sx"),
                         params={**q, "status": "bogus"})
    assert r.status_code == 400
    await _pub(ids["e1"], dn(), ids["t2"])
    r = await client.get(API, headers=await _h(client, w, "sx"), params=q)
    row = next(x for x in r.json() if x["id"] == j["id"])
    assert "scheduled" in row["claims"][0]["eligibility_reason"]


# ------------------------ review follow-ups ------------------------

async def _set_head(w, uid):
    async with SessionLocal() as db:
        await db.execute(Department.__table__.update().where(
            Department.name == w["dept"]).values(head_user_id=uid))
        await db.commit()


async def test_creator_cannot_claim_own_shift(client, world):
    w, ids = world, world["ids"]
    await _set_head(w, ids["e3"])          # e3 is an employee AND the scheduler
    j = await _mk(client, w, who="e3")
    r = await _claim(client, w, j["id"], "e3")
    assert r.status_code == 400 and "posted" in r.json()["error"]["message"]
    assert [x for x in await _notes(ids["e3"], "Open shift available")
            if x.resource_id == str(j["id"])] == []
    j2 = await _mk(client, w, who="e3", auto_confirm=True)
    assert (await _claim(client, w, j2["id"], "e3")).status_code == 400
    assert await _cell(ids["e3"], dn()) is None
    assert (await _claim(client, w, j2["id"], "e1")).status_code == 200


async def test_decide_after_creator_deactivated_or_lost_scope(client, world):
    w, ids = world, world["ids"]
    j = await _mk(client, w)
    cid = (await _claim(client, w, j["id"], "e1")).json()["my_claim_id"]
    async with SessionLocal() as db:
        await db.execute(User.__table__.update().where(
            User.id == ids["sx"]).values(is_active=False))
        await db.commit()
    r = await _decide(client, w, cid, who="admin")   # approver supplies scope
    assert r.status_code == 200, r.text
    assert await _cell(ids["e1"], dn()) == (ids["t1"], False)
    # creator loses scope: 403 (not a later 400)
    async with SessionLocal() as db:
        await db.execute(User.__table__.update().where(
            User.id == ids["sx"]).values(is_active=True))
        await db.commit()
    j2 = await _mk(client, w, work_date=dd(1))
    cid2 = (await _claim(client, w, j2["id"], "e3")).json()["my_claim_id"]
    await _set_head(w, None)
    r = await _decide(client, w, cid2, who="sx")
    assert r.status_code == 403
    assert (await _decide(client, w, cid2, who="admin")).status_code == 200


async def test_other_head_can_approve_when_creator_lacks_scope(client, world):
    w, ids = world, world["ids"]
    j = await _mk(client, w)
    cid = (await _claim(client, w, j["id"], "e1")).json()["my_claim_id"]
    # head moves from sx to e3; sx (creator) no longer covers e1
    await _set_head(w, ids["e3"])
    r = await _decide(client, w, cid, who="e3")
    assert r.status_code == 200, r.text


async def test_excluded_user_and_notification_exclusion(client, world):
    w, ids = world, world["ids"]
    async with SessionLocal() as db:
        actor = await db.get(User, ids["sx"])
        s = await os_svc.create_open_shift(
            db, actor, work_date=dn(), shift_template_id=ids["t1"],
            department=w["dept"], excluded_user_id=ids["e1"],
            exclude_user_ids=[ids["e6"]], source_drop_id=5)
        await db.commit()
        sid = s.id
    for tag, n in (("e1", 0), ("e6", 0), ("e3", 1)):
        got = [x for x in await _notes(ids[tag], "Open shift available")
               if x.resource_id == str(sid)]
        assert len(got) == n, tag
    r = await _claim(client, w, sid, "e1")
    assert r.status_code == 400 and "gave away" in r.json()["error"]["message"]
    assert (await _claim(client, w, sid, "e6")).status_code == 200  # only not notified
    r = await client.get(f"{API}/available", headers=await _h(client, w, "e1"))
    assert sid not in {x["id"] for x in r.json()}


async def test_available_query_count_is_bounded(client, world):
    from sqlalchemy import event
    from app.db.session import engine
    w, ids = world, world["ids"]
    for i in range(6):
        await _mk(client, w, work_date=dd(i))
    h = await _h(client, w, "e1")
    n = {"q": 0}

    def count(*a, **k):
        n["q"] += 1
    event.listen(engine.sync_engine, "before_cursor_execute", count)
    try:
        r = await client.get(f"{API}/available", headers=h)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", count)
    assert r.status_code == 200 and len(
        [x for x in r.json() if x["department"] == w["dept"]]) == 6
    assert n["q"] < 20, n["q"]      # not O(shifts)


async def test_warnings_draft_replaced_and_rest_violation(client, world):
    w, ids = world, world["ids"]
    await _pub(ids["e1"], dn(), ids["t2"], status=RosterStatus.DRAFT)
    j = await _mk(client, w, auto_confirm=True)
    r = await _claim(client, w, j["id"], "e1")
    assert r.status_code == 200
    # claimant is not shown the draft warning; the creator is notified instead
    assert not any("draft" in x for x in r.json()["warnings"])
    assert len(await _notes(ids["sx"], "Draft replaced by open shift")) == 1
    # rest rule: t2 (14-22) the evening before, then t1 (09-17)
    async with SessionLocal() as db:
        old = {}
        for k in ("min_rest_hours",):
            row = await db.get(SystemSetting, f"schedule.{k}")
            old[k] = row.value if row else None
        await set_time_rules(db, {"schedule.min_rest_hours": "12"})
    try:
        await _pub(ids["e3"], dn(-1), ids["t2"])
        j2 = await _mk(client, w, work_date=dd(0), department=w["dept"])
        cid = (await _claim(client, w, j2["id"], "e3")).json()["my_claim_id"]
        r = await _decide(client, w, cid)
        assert r.status_code == 200, r.text
        assert any("rest" in x.lower() for x in r.json()["warnings"]), r.json()
    finally:
        async with SessionLocal() as db:
            row = await db.get(SystemSetting, "schedule.min_rest_hours")
            if old["min_rest_hours"] is None:
                if row:
                    await db.delete(row)
            elif row:
                row.value = old["min_rest_hours"]
            await db.commit()


async def test_decide_response_scopes_claims(client, world):
    w, ids = world, world["ids"]
    # admin posts a company-wide shift; claims from both departments
    r = await client.post(API, headers=await _h(client, w, "admin"), json={
        "work_date": dd(), "shift_template_id": ids["t1"], "slots": 2})
    assert r.status_code == 200, r.text
    sid = r.json()["id"]
    c1 = (await _claim(client, w, sid, "e1")).json()["my_claim_id"]
    assert (await _claim(client, w, sid, "e4")).status_code == 200
    r = await _decide(client, w, c1)     # sx heads dept X only
    assert r.status_code == 200, r.text
    assert {c["user_id"] for c in r.json()["claims"]} == {ids["e1"]}
    r = await _decide(client, w, c1, who="admin")  # already decided; still 409
    assert r.status_code == 409


async def test_list_includes_claimed_shifts_for_delegate_and_can_cancel(client, world):
    w, ids = world, world["ids"]
    adm = await _h(client, w, "admin")
    mk = lambda day: client.post(API, headers=adm, json={
        "work_date": day, "shift_template_id": ids["t1"], "slots": 2})
    claimed = (await mk(dd())).json()
    unclaimed = (await mk(dd(1))).json()
    assert claimed["can_cancel"] is True
    assert (await _claim(client, w, claimed["id"], "e1")).status_code == 200
    q = {"start": dd(-1), "end": dd(3)}
    rows = {x["id"]: x for x in (await client.get(
        API, headers=await _h(client, w, "sx"), params=q)).json()}
    assert claimed["id"] in rows and unclaimed["id"] not in rows
    assert rows[claimed["id"]]["can_cancel"] is False
    assert [c["user_id"] for c in rows[claimed["id"]]["claims"]] == [ids["e1"]]
    # head of the other department has no claimant in scope
    other = {x["id"] for x in (await client.get(
        API, headers=await _h(client, w, "sy"), params=q)).json()}
    assert claimed["id"] not in other
    # creator keeps own shift and can cancel it
    mine = await _mk(client, w, work_date=dd(2))
    assert mine["can_cancel"] is True
