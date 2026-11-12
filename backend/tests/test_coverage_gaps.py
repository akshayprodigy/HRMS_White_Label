"""Coverage gap engine (Roadmap v2 Phase 2, Task 3)."""
import asyncio
import uuid
from datetime import date, time, timedelta, datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from _cleanup import purge_gap_notifications, purge_shift_templates
from app.api import deps
from app.core.config import settings
from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.main import create_app
from app.models.audit import AuditLog
from app.models.coverage_gap import CoverageGap
from app.models.department import Department
from app.models.employee import Employee, EmployeeStatus
from app.models.notification import Notification
from app.models.open_shift import (
    OpenShift, OpenShiftClaim, ShiftDropRequest,
)
from app.models.roster import (
    RosterChangeRequest, RosterEntry, RosterEntryHistory, RosterStatus,
)
from app.models.shift import ShiftTemplate
from app.models.user import User
from app.models.attendance import Attendance
from app.models.no_show import NoShowAlert
from app.services import coverage_gaps as gap_svc
from app.services.coverage_gaps import Candidate, rank_candidates
from app.services.live_ops import no_show_job

API = f"{settings.API_V1_STR}/roster/gaps"
OS = f"{settings.API_V1_STR}/roster/open-shifts"
DR = f"{settings.API_V1_STR}/roster/drops"
PW = "test@12345"
D = date(2030, 6, 12)  # a Wednesday, fixed so month-hours logic is stable


def dn(n=0):
    return D + timedelta(days=n)


# ------------------------------ pure ranking ------------------------------

def C(u, **kw):
    return Candidate(user_id=u, **kw)


def test_rank_orders_by_month_hours_then_id():
    out = rank_candidates([C(5, month_hours=40), C(3, month_hours=8),
                           C(2, month_hours=8), C(9, month_hours=0)])
    assert [s.user_id for s in out] == [9, 2, 3, 5]
    assert [s.score for s in out] == [0, -8, -8, -40]
    assert any("Lightest load" in r for r in out[0].reasons)
    assert not any("Lightest" in r for r in out[3].reasons)


def test_rank_filters():
    out = rank_candidates([
        C(1, eligible_reason="Already scheduled to work that day"),
        C(2, rule_violations=("Only 4h rest",)),
        C(3, ot_used_minutes=600, ot_cap_minutes=600),
        C(4, ot_used_minutes=100, ot_cap_minutes=600, month_hours=2),
        C(5, ot_used_minutes=9999, ot_cap_minutes=None),
        C(6),
    ], exclude=[6])
    assert [s.user_id for s in out] == [5, 4]
    assert out[1].ot_headroom_minutes == 500
    assert any("overtime headroom" in r for r in out[1].reasons)
    assert out[0].ot_headroom_minutes is None


def test_rank_limit_and_deterministic():
    cs = [C(i, month_hours=float(i % 3)) for i in range(1, 31)]
    a = rank_candidates(cs, 10)
    b = rank_candidates(list(reversed(cs)), 10)
    assert len(a) == 10 and a == b
    assert len(rank_candidates(cs, 99)) == 30  # service caps at 10 separately


# ------------------------------ fixtures ------------------------------

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
    dept_x, dept_y = f"GX{sfx}", f"GY{sfx}"
    try:
        async with SessionLocal() as db:
            def mk(tag, **kw):
                return User(email=f"cg_{tag}_{sfx}@t.com", full_name=f"CG {tag}",
                            hashed_password=get_password_hash(PW),
                            is_active=True, **kw)
            us = {t: mk(t) for t in (
                "e1", "e2", "e3", "e4", "e5", "e6", "sx", "sy")}
            us["admin"] = mk("admin", is_superuser=True)
            db.add_all(us.values())
            db.add_all([Department(name=dept_x), Department(name=dept_y)])
            t1 = ShiftTemplate(name=f"GT1{sfx}", start_time=time(9), end_time=time(17))
            db.add(t1)
            await db.commit()
            for tag, dept, st in (
                ("e1", dept_x, EmployeeStatus.ACTIVE),
                ("e2", dept_x, EmployeeStatus.ACTIVE),
                ("e3", dept_x, EmployeeStatus.ACTIVE),
                ("e4", dept_y, EmployeeStatus.ACTIVE),
                ("e5", dept_x, EmployeeStatus.INACTIVE),
                ("e6", dept_x, EmployeeStatus.ACTIVE),
            ):
                db.add(Employee(
                    user_id=us[tag].id, employee_id=f"CG{sfx}{tag}",
                    department=dept, designation="T",
                    date_of_joining=date(2020, 1, 1), status=st))
            await db.execute(Department.__table__.update().where(
                Department.name == dept_x).values(head_user_id=us["sx"].id))
            await db.execute(Department.__table__.update().where(
                Department.name == dept_y).values(head_user_id=us["sy"].id))
            await db.commit()
            ids = {t: u.id for t, u in us.items()}
            ids["t1"] = t1.id
        yield {"ids": ids, "sfx": sfx, "dept": dept_x, "deptY": dept_y,
               "email": lambda t: f"cg_{t}_{sfx}@t.com"}
    finally:
        async with SessionLocal() as db:
            uids = list((await db.execute(select(User.id).where(
                User.email.like(f"cg\\_%\\_{sfx}@t.com")))).scalars().all())
            tids = list((await db.execute(select(ShiftTemplate.id).where(
                ShiftTemplate.name == f"GT1{sfx}"))).scalars().all())
            gids = [str(i) for i in (await db.execute(select(CoverageGap.id).where(
                CoverageGap.shift_template_id.in_(tids)))).scalars().all()]
            oids = [str(i) for i in (await db.execute(select(OpenShift.id).where(
                OpenShift.shift_template_id.in_(tids)))).scalars().all()]
            if gids:  # may have fallen back to real admins
                await db.execute(delete(Notification).where(
                    Notification.resource_type == "coverage_gap",
                    Notification.resource_id.in_(gids)))
            if oids:
                await db.execute(delete(Notification).where(
                    Notification.resource_type == "open_shift",
                    Notification.resource_id.in_(oids)))
            await db.execute(delete(Notification).where(
                Notification.user_id.in_(uids)))
            await db.execute(delete(AuditLog).where(
                AuditLog.user_id.in_(uids), AuditLog.action.like("roster.%")))
            await db.execute(delete(NoShowAlert).where(NoShowAlert.user_id.in_(uids)))
            await db.execute(delete(Attendance).where(Attendance.user_id.in_(uids)))
            await purge_gap_notifications(db, tids)
            await db.execute(delete(CoverageGap).where(
                CoverageGap.shift_template_id.in_(tids)))
            await db.execute(delete(OpenShiftClaim).where(
                OpenShiftClaim.user_id.in_(uids)))
            await db.execute(delete(ShiftDropRequest).where(
                ShiftDropRequest.user_id.in_(uids)))
            await db.execute(delete(OpenShift).where(
                OpenShift.shift_template_id.in_(tids)))
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
            await purge_gap_notifications(db, tids)
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


async def _pub(uid, day, tpl):
    async with SessionLocal() as db:
        db.add(RosterEntry(employee_id=uid, work_date=day,
                           shift_template_id=tpl, is_week_off=False,
                           status=RosterStatus.PUBLISHED))
        await db.commit()


async def _cell(uid, day):
    async with SessionLocal() as db:
        r = (await db.execute(select(RosterEntry).where(
            RosterEntry.employee_id == uid, RosterEntry.work_date == day,
            RosterEntry.status == RosterStatus.PUBLISHED))).scalars().first()
        return None if r is None else (r.shift_template_id, r.is_week_off)


async def _gap(w, absent="e1", source="no_show", day=0):
    async with SessionLocal() as db:
        g = await gap_svc.open_gap(
            db, work_date=dn(day), shift_template_id=w["ids"]["t1"],
            absent_user_id=w["ids"][absent] if absent else None,
            department=w["dept"] if not absent else None,
            source=source, source_id=None)
        await db.commit()
        return g.id


async def _get_gap(gid):
    async with SessionLocal() as db:
        return await db.get(CoverageGap, gid)


async def _notes(uid, title=None):
    async with SessionLocal() as db:
        q = select(Notification).where(Notification.user_id == uid)
        if title:
            q = q.where(Notification.title == title)
        return list((await db.execute(q)).scalars().all())


# ------------------------------ service ------------------------------

async def test_open_gap_idempotent_and_notifies(world):
    w, ids = world, world["ids"]
    g1 = await _gap(w)
    g2 = await _gap(w)
    assert g1 == g2
    g3 = await _gap(w, source="drop")
    assert g3 != g1
    got = await _notes(ids["sx"], "Coverage gap needs a replacement")
    assert len(got) == 2 and {n.resource_id for n in got} == {str(g1), str(g3)}
    gap = await _get_gap(g1)
    assert gap.department == w["dept"] and gap.status == "open"
    with pytest.raises(ValueError):
        async with SessionLocal() as db:
            await gap_svc.open_gap(db, work_date=D, shift_template_id=ids["t1"],
                                   source="bogus")


# ------------------------------ create / list ------------------------------

async def test_create_validation_and_scope(client, world):
    w, ids = world, world["ids"]
    body = {"work_date": D.isoformat(), "shift_template_id": ids["t1"],
            "absent_user_id": ids["e1"], "source": "sick_call"}
    r = await client.post(API, headers=await _h(client, w, "sx"), json=body)
    assert r.status_code == 200, r.text
    g = r.json()
    assert g["source"] == "sick_call" and g["absent_name"] == "CG e1"
    assert g["department"] == w["dept"] and g["status"] == "open"
    # idempotent
    r = await client.post(API, headers=await _h(client, w, "sx"), json=body)
    assert r.json()["id"] == g["id"]
    # out of scope
    r = await client.post(API, headers=await _h(client, w, "sy"), json=body)
    assert r.status_code == 403
    # bad source / past / no absent without dept scope
    assert (await client.post(API, headers=await _h(client, w, "sx"),
            json={**body, "source": "no_show"})).status_code == 422
    assert (await client.post(API, headers=await _h(client, w, "sx"),
            json={**body, "work_date": "2020-01-01"})).status_code == 400
    nb = {"work_date": D.isoformat(), "shift_template_id": ids["t1"],
          "department": w["dept"]}
    assert (await client.post(API, headers=await _h(client, w, "sy"),
            json=nb)).status_code == 403
    assert (await client.post(API, headers=await _h(client, w, "sx"),
            json=nb)).status_code == 200
    assert (await client.post(API, headers=await _h(client, w, "admin"),
            json={**nb, "department": None})).status_code == 200


async def test_list_scoping_and_filters(client, world):
    w, ids = world, world["ids"]
    g1 = await _gap(w)                 # absent e1 (dept x)
    g2 = await _gap(w, absent=None)    # no absentee, dept x
    g3 = await _gap(w, absent="e4")    # dept y
    async def seen(tag, **q):
        r = await client.get(API, headers=await _h(client, w, tag), params=q)
        assert r.status_code == 200, r.text
        return {x["id"] for x in r.json()} & {g1, g2, g3}
    assert await seen("sx") == {g1, g2}
    assert await seen("sy") == {g3}
    assert await seen("admin") == {g1, g2, g3}
    assert await seen("e1") == set()
    assert await seen("admin", status="filled") == set()
    assert await seen("admin", status="open", date_from=dn(1).isoformat()) == set()
    assert await seen("admin", date_to=dn().isoformat()) == {g1, g2, g3}
    r = await client.get(API, headers=await _h(client, w, "admin"),
                         params={"status": "bogus"})
    assert r.status_code == 400
    row = next(x for x in (await client.get(
        API, headers=await _h(client, w, "sx"))).json() if x["id"] == g1)
    assert row["shift_name"] == f"GT1{w['sfx']}" and row["shift_start"] == "09:00"


# ------------------------------ suggestions ------------------------------

async def test_suggestions_ranking_and_exclusions(client, world):
    w, ids = world, world["ids"]
    await _pub(ids["e1"], dn(), ids["t1"])
    await _pub(ids["e3"], dn(), ids["t1"])         # busy that day
    await _pub(ids["e2"], dn(1), ids["t1"])        # e2 carries more hours
    await _pub(ids["e2"], dn(2), ids["t1"])
    gid = await _gap(w)
    r = await client.get(f"{API}/{gid}/suggestions", headers=await _h(client, w, "sx"))
    assert r.status_code == 200, r.text
    sug = r.json()["suggestions"]
    got = [s["user_id"] for s in sug]
    assert got == [ids["e6"], ids["e2"]], got    # e1 absent, e3 busy, e4 other dept, e5 inactive
    assert sug[0]["score"] > sug[1]["score"] and sug[1]["month_hours"] == 14.0  # 2 x (8h - 60m break)
    assert sug[0]["reasons"] and sug[0]["name"] == "CG e6"
    # scope: sy cannot see; e1 cannot
    assert (await client.get(f"{API}/{gid}/suggestions",
            headers=await _h(client, w, "sy"))).status_code == 403
    assert (await client.get(f"{API}/{gid}/suggestions",
            headers=await _h(client, w, "e1"))).status_code == 403
    assert (await client.get(f"{API}/99999999/suggestions",
            headers=await _h(client, w, "sx"))).status_code == 404


async def test_suggestions_exclude_rule_breakers(client, world):
    from app.services.time_rules import set_time_rules  # noqa: F401
    w, ids = world, world["ids"]
    # e2 works a late shift the previous evening: rest rule would break
    async with SessionLocal() as db:
        late = ShiftTemplate(name=f"GT1{w['sfx']}late", start_time=time(16),
                             end_time=time(23, 30))
        db.add(late)
        await db.commit()
        late_id = late.id
    try:
        await _pub(ids["e2"], dn(-1), late_id)
        gid = await _gap(w)
        r = await client.get(f"{API}/{gid}/suggestions",
                             headers=await _h(client, w, "sx"))
        got = {s["user_id"] for s in r.json()["suggestions"]}
        # default min_rest 11h: 23:30 -> 09:00 is 9.5h
        assert ids["e2"] not in got and ids["e6"] in got
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(RosterEntry).where(
                RosterEntry.shift_template_id == late_id))
            await purge_shift_templates(db, [late_id])
            await db.commit()


# ------------------------------ assign ------------------------------

async def test_assign_publishes_and_notifies(client, world):
    w, ids = world, world["ids"]
    await _pub(ids["e1"], dn(), ids["t1"])
    cr = None
    async with SessionLocal() as db:
        cr = RosterChangeRequest(
            employee_id=ids["e2"], work_date=dn(), requested_week_off=True,
            reason="pls", status="pending")
        db.add(cr)
        await db.commit()
        crid = cr.id
    gid = await _gap(w)
    r = await client.post(f"{API}/{gid}/assign", headers=await _h(client, w, "sx"),
                          json={"user_id": ids["e2"]})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["status"] == "filled" and b["filled_by_user_id"] == ids["e2"]
    assert b["resolved_by_id"] == ids["sx"] and b["warnings"] == []
    assert await _cell(ids["e2"], dn()) == (ids["t1"], False)
    async with SessionLocal() as db:
        h = (await db.execute(select(RosterEntryHistory).where(
            RosterEntryHistory.employee_id == ids["e2"]))).scalars().all()
        assert [x.reason for x in h] == [f"Coverage gap #{gid}"]
        assert (await db.get(RosterChangeRequest, crid)).status == "cancelled"
        await db.execute(delete(RosterChangeRequest).where(RosterChangeRequest.id == crid))
        await db.commit()
    assert await _notes(ids["e2"], "Covering a shift")
    assert await _notes(ids["e2"], "Schedule changed")
    # second assign: gap no longer open
    r = await client.post(f"{API}/{gid}/assign", headers=await _h(client, w, "sx"),
                          json={"user_id": ids["e6"]})
    assert r.status_code == 409
    assert await _cell(ids["e6"], dn()) is None


async def test_assign_validation(client, world):
    w, ids = world, world["ids"]
    await _pub(ids["e3"], dn(), ids["t1"])
    gid = await _gap(w)
    H = await _h(client, w, "sx")
    post = lambda u, h=H: client.post(f"{API}/{gid}/assign", headers=h, json={"user_id": u})
    assert (await post(ids["e4"])).status_code == 403          # cannot publish dept y
    assert (await post(ids["e3"])).status_code == 400          # already working
    assert (await post(ids["e1"])).status_code == 400          # the absentee
    assert (await post(ids["e5"])).status_code == 403          # inactive: outside scope
    assert (await post(ids["e2"], await _h(client, w, "sy"))).status_code == 403
    assert (await post(ids["e2"], await _h(client, w, "e6"))).status_code == 403
    assert (await _get_gap(gid)).status == "open"
    assert (await post(ids["e2"])).status_code == 200


async def test_assign_concurrent_one_wins(client, world):
    w, ids = world, world["ids"]
    gid = await _gap(w)
    H = await _h(client, w, "sx")
    r = await asyncio.gather(*[
        client.post(f"{API}/{gid}/assign", headers=H, json={"user_id": ids[t]})
        for t in ("e2", "e6")])
    codes = sorted(x.status_code for x in r)
    assert codes == [200, 409], [x.text for x in r]
    gap = await _get_gap(gid)
    winner = ids["e2"] if r[0].status_code == 200 else ids["e6"]
    loser = ids["e6"] if winner == ids["e2"] else ids["e2"]
    assert gap.filled_by_user_id == winner
    assert await _cell(winner, dn()) == (ids["t1"], False)
    assert await _cell(loser, dn()) is None


# ------------------------------ broadcast / dismiss ------------------------------

async def test_broadcast_then_fill_marks_gap_filled(client, world):
    w, ids = world, world["ids"]
    await _pub(ids["e1"], dn(), ids["t1"])
    gid = await _gap(w)
    H = await _h(client, w, "sx")
    assert (await client.post(f"{API}/{gid}/broadcast", json={},
            headers=await _h(client, w, "sy"))).status_code == 403
    r = await client.post(f"{API}/{gid}/broadcast", json={"auto_confirm": False},
                          headers=H)
    assert r.status_code == 200, r.text
    sid = r.json()["open_shift_id"]
    assert sid and r.json()["status"] == "open" and r.json()["open_shift_status"] == "open"
    assert (await client.post(f"{API}/{gid}/broadcast", json={}, headers=H)
            ).status_code == 409
    # absentee never notified; eligible colleagues are
    assert not [n for n in await _notes(ids["e1"], "Open shift available")]
    assert await _notes(ids["e2"], "Open shift available")
    # claim + approve -> gap filled
    r = await client.post(f"{OS}/{sid}/claim", headers=await _h(client, w, "e2"))
    assert r.status_code == 200, r.text
    cid = r.json()["claims"][0]["id"] if r.json().get("claims") else None
    if cid is None:
        async with SessionLocal() as db:
            cid = (await db.execute(select(OpenShiftClaim.id).where(
                OpenShiftClaim.open_shift_id == sid))).scalar()
    r = await client.post(f"{OS}/claims/{cid}/decide", headers=H,
                          json={"action": "approve"})
    assert r.status_code == 200, r.text
    gap = await _get_gap(gid)
    assert gap.status == "filled" and gap.filled_by_user_id == ids["e2"]
    assert await _cell(ids["e2"], dn()) == (ids["t1"], False)
    assert (await client.post(f"{API}/{gid}/dismiss", json={}, headers=H)
            ).status_code == 409


async def test_broadcast_auto_confirm_and_cancel_releases(client, world):
    w, ids = world, world["ids"]
    gid = await _gap(w)
    H = await _h(client, w, "sx")
    sid = (await client.post(f"{API}/{gid}/broadcast", json={"auto_confirm": True},
                             headers=H)).json()["open_shift_id"]
    r = await client.post(f"{OS}/{sid}/cancel", headers=H)
    assert r.status_code == 200, r.text
    gap = await _get_gap(gid)
    assert gap.status == "open" and gap.open_shift_id is None
    sid2 = (await client.post(f"{API}/{gid}/broadcast", json={"auto_confirm": True},
                              headers=H)).json()["open_shift_id"]
    assert sid2 != sid
    r = await client.post(f"{OS}/{sid2}/claim", headers=await _h(client, w, "e6"))
    assert r.status_code == 200, r.text
    gap = await _get_gap(gid)
    assert gap.status == "filled" and gap.filled_by_user_id == ids["e6"]


async def test_assign_cancels_linked_open_shift(client, world):
    w, ids = world, world["ids"]
    gid = await _gap(w)
    H = await _h(client, w, "sx")
    sid = (await client.post(f"{API}/{gid}/broadcast", json={}, headers=H)
           ).json()["open_shift_id"]
    await client.post(f"{OS}/{sid}/claim", headers=await _h(client, w, "e2"))
    r = await client.post(f"{API}/{gid}/assign", headers=H, json={"user_id": ids["e6"]})
    assert r.status_code == 200, r.text
    async with SessionLocal() as db:
        assert (await db.get(OpenShift, sid)).status == "cancelled"
        cl = (await db.execute(select(OpenShiftClaim).where(
            OpenShiftClaim.open_shift_id == sid))).scalars().all()
        assert [c.status for c in cl] == ["rejected"]


async def test_dismiss(client, world):
    w, ids = world, world["ids"]
    g1 = await _gap(w)
    g2 = await _gap(w, absent=None)
    assert (await client.post(f"{API}/{g1}/dismiss", json={"note": "x"},
            headers=await _h(client, w, "sy"))).status_code == 403
    assert (await client.post(f"{API}/{g1}/dismiss", json={"note": "x"},
            headers=await _h(client, w, "e2"))).status_code == 403
    sid = (await client.post(f"{API}/{g1}/broadcast", json={},
           headers=await _h(client, w, "sx"))).json()["open_shift_id"]
    r = await client.post(f"{API}/{g1}/dismiss", json={"note": "covered by agency"},
                          headers=await _h(client, w, "sx"))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "dismissed" and r.json()["note"] == "covered by agency"
    async with SessionLocal() as db:
        assert (await db.get(OpenShift, sid)).status == "cancelled"
    assert (await client.post(f"{API}/{g1}/dismiss", json={},
            headers=await _h(client, w, "sx"))).status_code == 409
    assert (await client.post(f"{API}/{g1}/assign", json={"user_id": ids["e2"]},
            headers=await _h(client, w, "sx"))).status_code == 409
    # absentee-less gap: dept head or admin
    assert (await client.post(f"{API}/{g2}/dismiss", json={},
            headers=await _h(client, w, "admin"))).status_code == 200


# ------------------------------ triggers ------------------------------

async def test_no_show_job_opens_gap(world):
    w, ids = world, world["ids"]
    await _pub(ids["e1"], dn(), ids["t1"])
    now = datetime.combine(dn(), time(11, 0), timezone.utc)
    async with SessionLocal() as db:
        res = await no_show_job(db, now=now, user_ids=[ids["e1"]])
    assert res["alerts_created"] == 1
    async with SessionLocal() as db:
        gs = (await db.execute(select(CoverageGap).where(
            CoverageGap.absent_user_id == ids["e1"]))).scalars().all()
    assert len(gs) == 1
    g = gs[0]
    assert (g.source, g.work_date, g.shift_template_id, g.status) == (
        "no_show", dn(), ids["t1"], "open")
    assert g.department == w["dept"]
    async with SessionLocal() as db:  # re-run: idempotent
        await no_show_job(db, now=now, user_ids=[ids["e1"]])
        assert len((await db.execute(select(CoverageGap).where(
            CoverageGap.absent_user_id == ids["e1"]))).scalars().all()) == 1


async def _drop(client, w, who="e1"):
    r = await client.post(DR, headers=await _h(client, w, who), json={
        "work_date": dn().isoformat(), "reason": "family event"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


async def test_drop_approval_without_open_shift_opens_gap(client, world):
    w, ids = world, world["ids"]
    await _pub(ids["e1"], dn(), ids["t1"])
    did = await _drop(client, w)
    r = await client.post(f"{DR}/{did}/decide", headers=await _h(client, w, "sx"),
                          json={"action": "approve", "post_open_shift": False})
    assert r.status_code == 200, r.text
    async with SessionLocal() as db:
        g = (await db.execute(select(CoverageGap).where(
            CoverageGap.absent_user_id == ids["e1"]))).scalars().one()
    assert (g.source, g.source_id, g.status, g.work_date) == (
        "drop", did, "open", dn())


async def test_drop_approval_with_open_shift_opens_no_gap(client, world):
    w, ids = world, world["ids"]
    await _pub(ids["e1"], dn(), ids["t1"])
    did = await _drop(client, w)
    r = await client.post(f"{DR}/{did}/decide", headers=await _h(client, w, "sx"),
                          json={"action": "approve"})
    assert r.status_code == 200 and r.json()["open_shift_id"]
    async with SessionLocal() as db:
        assert not (await db.execute(select(CoverageGap).where(
            CoverageGap.absent_user_id == ids["e1"]))).scalars().all()


async def test_suggestions_respect_monthly_ot_cap(client, world):
    from app.models.overtime import OvertimeEntry, OvertimeRule
    w, ids = world, world["ids"]
    async with SessionLocal() as db:
        rule = OvertimeRule(name=f"GOT{w['sfx']}", scope="shift",
                            shift_template_id=ids["t1"],
                            monthly_ot_cap_minutes=120, is_active=True)
        db.add(rule)
        await db.flush()
        db.add(OvertimeEntry(user_id=ids["e2"], work_date=dn(-3),
                             ot_minutes=120, status="approved", rule_id=rule.id))
        db.add(OvertimeEntry(user_id=ids["e6"], work_date=dn(-3),
                             ot_minutes=30, status="approved", rule_id=rule.id))
        # rejected OT does not count
        db.add(OvertimeEntry(user_id=ids["e3"], work_date=dn(-3),
                             ot_minutes=500, status="rejected", rule_id=rule.id))
        await db.commit()
    try:
        gid = await _gap(w)
        r = await client.get(f"{API}/{gid}/suggestions",
                             headers=await _h(client, w, "sx"))
        sug = {s["user_id"]: s for s in r.json()["suggestions"]}
        assert ids["e2"] not in sug                      # cap reached
        assert sug[ids["e6"]]["ot_headroom_minutes"] == 90
        assert sug[ids["e3"]]["ot_headroom_minutes"] == 120
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(OvertimeEntry).where(
                OvertimeEntry.user_id.in_([ids["e2"], ids["e3"], ids["e6"]])))
            await db.execute(delete(OvertimeRule).where(
                OvertimeRule.name == f"GOT{w['sfx']}"))
            await db.commit()


# ------------------------------ review follow-ups ------------------------------

async def test_open_gap_concurrent_sessions_same_gap(world):
    w, ids = world, world["ids"]

    async def one():
        async with SessionLocal() as db:
            # establish the snapshot BEFORE the other session commits
            await db.execute(select(CoverageGap.id).where(
                CoverageGap.shift_template_id == ids["t1"]))
            await asyncio.sleep(0.2)
            g = await gap_svc.open_gap(
                db, work_date=dn(), shift_template_id=ids["t1"],
                absent_user_id=ids["e1"], source="manual")
            gid = g.id
            await db.commit()
            return gid
    got = await asyncio.gather(one(), one(), one())
    assert len(set(got)) == 1, got
    async with SessionLocal() as db:
        assert len((await db.execute(select(CoverageGap).where(
            CoverageGap.absent_user_id == ids["e1"]))).scalars().all()) == 1


async def test_open_gap_notify_false(world):
    w, ids = world, world["ids"]
    async with SessionLocal() as db:
        g = await gap_svc.open_gap(
            db, work_date=dn(), shift_template_id=ids["t1"],
            absent_user_id=ids["e1"], source="emergency_leave", notify=False)
        await db.commit()
        gid = g.id
    assert not [n for n in await _notes(ids["sx"])
                if n.resource_id == str(gid)]


async def test_no_show_gap_does_not_double_notify(world):
    w, ids = world, world["ids"]
    await _pub(ids["e1"], dn(), ids["t1"])
    now = datetime.combine(dn(), time(11, 0), timezone.utc)
    async with SessionLocal() as db:
        await no_show_job(db, now=now, user_ids=[ids["e1"]])
    assert not await _notes(ids["sx"], "Coverage gap needs a replacement")
    async with SessionLocal() as db:
        assert (await db.execute(select(CoverageGap).where(
            CoverageGap.absent_user_id == ids["e1"]))).scalars().one()


async def test_drop_gap_does_not_notify_approver(client, world):
    w, ids = world, world["ids"]
    await _pub(ids["e1"], dn(), ids["t1"])
    did = await _drop(client, w)
    r = await client.post(f"{DR}/{did}/decide", headers=await _h(client, w, "sx"),
                          json={"action": "approve", "post_open_shift": False})
    assert r.status_code == 200, r.text
    assert not await _notes(ids["sx"], "Coverage gap needs a replacement")


async def test_create_gap_existing_not_open_or_other_template_409(client, world):
    w, ids = world, world["ids"]
    H = await _h(client, w, "sx")
    body = {"work_date": D.isoformat(), "shift_template_id": ids["t1"],
            "absent_user_id": ids["e1"], "source": "sick_call"}
    gid = (await client.post(API, headers=H, json=body)).json()["id"]
    assert (await client.post(f"{API}/{gid}/dismiss", json={}, headers=H)
            ).status_code == 200
    r = await client.post(API, headers=H, json=body)
    assert r.status_code == 409 and "dismissed" in r.json()["error"]["message"]
    async with SessionLocal() as db:
        t2 = ShiftTemplate(name=f"GT1{w['sfx']}b", start_time=time(10),
                           end_time=time(18))
        db.add(t2)
        await db.commit()
        t2id = t2.id
    g2 = await _gap(w, source="manual", day=3)
    r = await client.post(API, headers=H, json={
        "work_date": dn(3).isoformat(), "shift_template_id": t2id,
        "absent_user_id": ids["e1"], "source": "manual"})
    assert r.status_code == 409, r.text
    assert (await _get_gap(g2)).shift_template_id == ids["t1"]
    async with SessionLocal() as db:
        await purge_shift_templates(db, [t2id])
        await db.commit()


async def test_assign_warns_when_replacement_over_ot_cap(client, world):
    from app.models.overtime import OvertimeEntry, OvertimeRule
    w, ids = world, world["ids"]
    async with SessionLocal() as db:
        rule = OvertimeRule(name=f"GOT{w['sfx']}", scope="shift",
                            shift_template_id=ids["t1"],
                            monthly_ot_cap_minutes=60, is_active=True)
        db.add(rule)
        await db.flush()
        db.add(OvertimeEntry(user_id=ids["e2"], work_date=dn(-3),
                             ot_minutes=90, status="approved", rule_id=rule.id))
        await db.commit()
    try:
        gid = await _gap(w)
        r = await client.post(f"{API}/{gid}/assign",
                              headers=await _h(client, w, "sx"),
                              json={"user_id": ids["e2"]})
        assert r.status_code == 200, r.text
        assert any("overtime cap" in x for x in r.json()["warnings"]), r.json()
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(OvertimeEntry).where(
                OvertimeEntry.user_id == ids["e2"]))
            await db.execute(delete(OvertimeRule).where(
                OvertimeRule.name == f"GOT{w['sfx']}"))
            await db.commit()


async def test_create_gap_unknown_or_non_employee_absent_user(client, world):
    w, ids = world, world["ids"]
    base = {"work_date": D.isoformat(), "shift_template_id": ids["t1"],
            "source": "sick_call"}
    ha = await _h(client, w, "admin")
    r = await client.post(API, headers=ha, json={**base, "absent_user_id": 999999999})
    assert r.status_code == 404, r.text
    # an existing user with no active employee record
    r = await client.post(API, headers=ha, json={**base, "absent_user_id": ids["admin"]})
    assert r.status_code == 400, r.text
