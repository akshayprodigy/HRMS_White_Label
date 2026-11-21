"""Phase 6A Task 7: on-duty / client-visit / WFH requests. Real dev DB;
everything created here is removed in teardown."""
import asyncio
import uuid
from datetime import timedelta

import pytest
from _tz import org_today  # noqa: E402
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, insert, select

from app.api import deps
from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.main import create_app
from app.models.approval_chain import (
    ApprovalChain, ApprovalChainStep, ChainedApprovalInstance,
    ChainedApprovalStepInstance,
)
from app.models.audit import AuditLog
from app.models.notification import Notification
from app.models.payroll import PayrollRun, PayrollRunStatus
from app.models.system import SystemSetting
from app.models.user import Role, User, user_roles
from app.models.work_location import WorkLocationRequest
from app.services import work_location as WL

P = "/api/v1/work-location-requests"
BASE = org_today() + timedelta(days=400)


def D(n):
    return BASE + timedelta(days=n)


def iso(d):
    return d.isoformat()


async def _cleanup(sfx, run_ids=()):
    async with SessionLocal() as db:
        uids = list((await db.execute(select(User.id).where(
            User.email.like(f"wl\\_%\\_{sfx}@test.com")))).scalars().all())
        rids = list((await db.execute(select(WorkLocationRequest.id).where(
            WorkLocationRequest.user_id.in_(uids)))).scalars().all()) \
            if uids else []
        chain_ids = list((await db.execute(select(ApprovalChain.id).where(
            ApprovalChain.name.like(f"%{sfx}%")))).scalars().all())
        inst_ids = list((await db.execute(select(ChainedApprovalInstance.id).where(
            ChainedApprovalInstance.submitter_id.in_(uids)))).scalars().all()) \
            if uids else []
        if inst_ids:
            await db.execute(delete(ChainedApprovalStepInstance).where(
                ChainedApprovalStepInstance.instance_id.in_(inst_ids)))
            await db.execute(delete(Notification).where(
                Notification.resource_type == "chained_approval_instance",
                Notification.resource_id.in_([str(i) for i in inst_ids])))
            await db.execute(delete(ChainedApprovalInstance).where(
                ChainedApprovalInstance.id.in_(inst_ids)))
        if chain_ids:
            await db.execute(delete(ApprovalChainStep).where(
                ApprovalChainStep.chain_id.in_(chain_ids)))
            await db.execute(delete(ApprovalChain).where(
                ApprovalChain.id.in_(chain_ids)))
        if rids:
            await db.execute(delete(Notification).where(
                Notification.resource_type == "work_location",
                Notification.resource_id.in_([str(p) for p in rids])))
            await db.execute(delete(AuditLog).where(
                AuditLog.resource_type == "work_location",
                AuditLog.resource_id.in_([str(p) for p in rids])))
            await db.execute(delete(WorkLocationRequest).where(
                WorkLocationRequest.id.in_(rids)))
        if run_ids:
            await db.execute(delete(PayrollRun).where(
                PayrollRun.id.in_(list(run_ids))))
        if uids:
            await db.execute(delete(Notification).where(Notification.user_id.in_(uids)))
            await db.execute(delete(AuditLog).where(AuditLog.user_id.in_(uids)))
            await db.execute(delete(user_roles).where(user_roles.c.user_id.in_(uids)))
            await db.execute(delete(User).where(User.id.in_(uids)))
        await db.commit()


@pytest.fixture
async def world():
    sfx = uuid.uuid4().hex[:8]
    w: dict = {"sfx": sfx, "runs": []}
    async with SessionLocal() as db:
        row = await db.get(SystemSetting, WL.BACKDATE_KEY)
        w["saved"] = (row.value, row.description) if row else None
        if row:
            row.value = "7"
        else:
            db.add(SystemSetting(key=WL.BACKDATE_KEY, value="7", description="t"))
        await db.commit()
    try:
        async with SessionLocal() as db:
            us = {}
            for n in ("hr", "mgr", "emp", "emp2", "plain", "lv", "su"):
                us[n] = User(email=f"wl_{n}_{sfx}@test.com",
                             full_name=f"Wl {n} {sfx}",
                             hashed_password=get_password_hash("x"),
                             is_active=True)
            db.add_all(us.values())
            await db.flush()
            us["su"].is_superuser = True
            us["emp"].manager_id = us["mgr"].id
            for who, rname in (("hr", "HR"), ("lv", "PM")):
                role = (await db.execute(
                    select(Role).where(Role.name == rname))).scalars().first()
                await db.execute(insert(user_roles).values(
                    user_id=us[who].id, role_id=role.id))
            await db.commit()
            w["uid"] = {n: u.id for n, u in us.items()}
        yield w
    finally:
        await _cleanup(sfx, w["runs"])
        async with SessionLocal() as db:
            row = await db.get(SystemSetting, WL.BACKDATE_KEY)
            sv = w["saved"]
            if sv is None:
                if row:
                    await db.delete(row)
            elif row:
                row.value = sv[0]
            await db.commit()


async def _login(c, email):
    r = await c.post("/api/v1/auth/login",
                     data={"username": email, "password": "x"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
async def api(world):
    app = create_app()
    app.dependency_overrides[deps.verify_attendance] = lambda: None
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as c:
        for n in ("hr", "mgr", "emp", "emp2", "plain", "lv", "su"):
            setattr(c, n, await _login(c, f"wl_{n}_{world['sfx']}@test.com"))
        yield c


async def _second_client(world, who):
    app = create_app()
    app.dependency_overrides[deps.verify_attendance] = lambda: None
    c = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    return c, await _login(c, f"wl_{who}_{world['sfx']}@test.com")


async def req(api, who="emp", kind="wfh", s=0, e=None, portion="full",
              place=None, purpose="work"):
    if e is None:
        e = s
    return await api.post(P, headers=getattr(api, who), json={
        "kind": kind, "start_date": iso(D(s)), "end_date": iso(D(e)),
        "day_portion": portion, "place": place, "purpose": purpose})


async def decide(api, rid, who="mgr", approve=True):
    return await api.post(f"{P}/{rid}/decide", headers=getattr(api, who),
                          json={"approve": approve})


async def mk_run(world, d):
    async with SessionLocal() as db:
        run = PayrollRun(month=d.month, year=d.year,
                         status=PayrollRunStatus.FINALIZED)
        db.add(run)
        await db.commit()
        world["runs"].append(run.id)


async def drop_runs(world):
    async with SessionLocal() as db:
        await db.execute(delete(PayrollRun).where(
            PayrollRun.id.in_(world["runs"])))
        await db.commit()
    world["runs"].clear()


@pytest.fixture
async def chain(api, world):
    async with SessionLocal() as db:
        c = ApprovalChain(
            name=f"WlChain {world['sfx']}", entity_type="work_location",
            is_active=True, effective_from=org_today().replace(year=2020),
            skip_if_same_person=False)
        db.add(c)
        await db.flush()
        db.add(ApprovalChainStep(
            chain_id=c.id, step_order=1, approver_type="specific_user",
            approver_ref=str(world["uid"]["hr"]), label="HR"))
        await db.commit()
    yield c


async def _status(rid):
    async with SessionLocal() as db:
        return (await db.get(WorkLocationRequest, rid)).status


async def _audits(rid):
    async with SessionLocal() as db:
        return {a.action for a in (await db.execute(select(AuditLog).where(
            AuditLog.resource_type == "work_location",
            AuditLog.resource_id == str(rid)))).scalars().all()}


async def test_validation(api, world):
    t = org_today()
    r = await api.post(P, headers=api.emp, json={
        "kind": "bogus", "start_date": iso(D(0)), "end_date": iso(D(0)),
        "purpose": "x"})
    assert r.status_code == 422
    assert (await req(api, s=3, e=2)).status_code == 422          # end < start
    assert (await req(api, s=0, e=31)).status_code == 422         # 32 days
    assert (await req(api, s=0, e=30)).status_code == 201         # 31 days ok
    assert (await req(api, s=40, e=41, portion="first_half")).status_code == 422
    assert (await req(api, kind="on_duty", s=50)).status_code == 422   # place
    assert (await req(api, kind="client_visit", s=50, place="  ")
            ).status_code == 422
    assert (await req(api, kind="on_duty", s=50, place="x" * 201)
            ).status_code == 422
    assert (await req(api, s=50, place="x" * 201)).status_code == 422
    assert (await req(api, s=50, purpose="   ")).status_code == 422
    assert (await req(api, s=50, purpose="x" * 1001)).status_code == 422
    # back-date limit (rule = 7)
    old = await api.post(P, headers=api.emp, json={
        "kind": "wfh", "start_date": iso(t - timedelta(days=8)),
        "end_date": iso(t - timedelta(days=8)), "purpose": "x"})
    assert old.status_code == 422
    ok = await api.post(P, headers=api.emp, json={
        "kind": "wfh", "start_date": iso(t - timedelta(days=7)),
        "end_date": iso(t - timedelta(days=7)), "purpose": "x"})
    assert ok.status_code == 201, ok.text
    assert ok.json()["routed_via"] == "direct"
    r = await req(api, kind="client_visit", s=60, place="Acme",
                  portion="first_half")
    assert r.status_code == 201
    assert r.json()["summary"].startswith("Client visit: Acme, ")
    assert r.json()["summary"].endswith("(first half)")
    assert "WORK_LOCATION_CREATE" in await _audits(r.json()["id"])


async def test_time_rule_validation():
    from app.services import time_rules as tr
    assert tr.TIME_RULE_DEFAULTS[WL.BACKDATE_KEY][0] == "7"
    async with SessionLocal() as db:
        for bad in ("61", "-1", "x"):
            with pytest.raises(ValueError):
                await tr.set_time_rules(db, {WL.BACKDATE_KEY: bad})
        await db.rollback()


async def test_overlap_and_halves(api, world):
    assert (await req(api, s=0, e=3)).status_code == 201
    assert (await req(api, s=3, e=5)).status_code == 409
    assert (await req(api, s=1, portion="first_half")).status_code == 409
    assert (await req(api, s=4, e=6)).status_code == 201
    # opposite halves allowed, same half twice 409, full overlaps a half
    assert (await req(api, s=10, portion="first_half")).status_code == 201
    assert (await req(api, s=10, portion="first_half")).status_code == 409
    assert (await req(api, s=10, portion="full")).status_code == 409
    assert (await req(api, s=10, portion="second_half")).status_code == 201
    # a range containing a half-day date still conflicts
    assert (await req(api, s=9, e=11)).status_code == 409
    # another user's request does not conflict
    assert (await req(api, who="emp2", s=0, e=3)).status_code == 201
    # cancelled/rejected requests free the dates
    rid = (await req(api, s=20)).json()["id"]
    await api.post(f"{P}/{rid}/cancel", headers=api.emp)
    assert (await req(api, s=20)).status_code == 201


async def test_direct_approve_and_helpers(api, world):
    uid = world["uid"]["emp"]
    r = await req(api, kind="on_duty", place="Site", s=0, e=2)
    rid = r.json()["id"]
    assert (await decide(api, rid)).json()["status"] == "approved"
    async with SessionLocal() as db:
        assert await WL.approved_portion(db, uid, D(0)) == "full"
        assert await WL.approved_portion(db, uid, D(3)) is None
        res = await WL.approved_portions(db, [uid, world["uid"]["emp2"]],
                                         D(1), D(10))
        assert res[uid] == {D(1): "full", D(2): "full"}      # clipped
        assert res[world["uid"]["emp2"]] == {}
        k = await WL.approved_kinds(db, [uid], D(0), D(5))
        assert k[uid] == {D(0): "on_duty", D(1): "on_duty", D(2): "on_duty"}
    # halves merge to full; kinds pick first half deterministically
    a = (await req(api, kind="wfh", s=10, portion="second_half")).json()["id"]
    b = (await req(api, kind="on_duty", place="P", s=10,
                   portion="first_half")).json()["id"]
    for x in (a, b):
        assert (await decide(api, x)).status_code == 200
    c = (await req(api, kind="wfh", s=11, portion="first_half")).json()["id"]
    await decide(api, c)
    async with SessionLocal() as db:
        p = await WL.approved_portions(db, [uid], D(10), D(11))
        assert p[uid] == {D(10): "full", D(11): "first_half"}
        k = await WL.approved_kinds(db, [uid], D(10), D(11))
        assert k[uid][D(10)] == "on_duty" and k[uid][D(11)] == "wfh"
    d = await api.get(f"{P}/my?status=approved", headers=api.emp)
    assert {x["id"] for x in d.json()} >= {rid, a, b}
    assert {"WORK_LOCATION_DECIDE"} <= await _audits(rid)
    async with SessionLocal() as db:
        n = (await db.execute(select(Notification).where(
            Notification.resource_type == "work_location",
            Notification.resource_id == str(rid),
            Notification.user_id == uid))).scalars().all()
        assert n
    # deciding twice -> 409
    assert (await decide(api, rid)).status_code == 409


async def test_reject(api, world):
    rid = (await req(api, s=0)).json()["id"]
    r = await decide(api, rid, approve=False)
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    async with SessionLocal() as db:
        assert await WL.approved_portion(db, world["uid"]["emp"], D(0)) is None


async def test_cancel_rules(api, world):
    t = org_today()
    rid = (await req(api, s=0)).json()["id"]
    r = await api.post(f"{P}/{rid}/cancel", headers=api.emp)
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert (await api.post(f"{P}/{rid}/cancel", headers=api.emp)
            ).status_code == 409
    # someone else cannot cancel
    rid = (await req(api, s=5)).json()["id"]
    assert (await api.post(f"{P}/{rid}/cancel", headers=api.emp2)
            ).status_code == 404
    # already started: employee 409, HR ok
    async with SessionLocal() as db:
        r2 = WorkLocationRequest(
            user_id=world["uid"]["emp"], kind="wfh",
            start_date=t - timedelta(days=2), end_date=t, day_portion="full",
            purpose="x", status="approved")
        db.add(r2)
        await db.commit()
        old = r2.id
    assert (await api.post(f"{P}/{old}/cancel", headers=api.emp)
            ).status_code == 409
    r = await api.post(f"{P}/{old}/cancel", headers=api.hr)
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert "WORK_LOCATION_CANCEL" in await _audits(old)


async def test_locked_period(api, world):
    rid = (await req(api, s=30)).json()["id"]
    await mk_run(world, D(30))
    r = await decide(api, rid)
    assert r.status_code == 409 and "payroll period locked" in r.text
    assert (await decide(api, rid, approve=False)).status_code == 200
    await drop_runs(world)
    rid2 = (await req(api, s=30)).json()["id"]
    assert (await decide(api, rid2)).status_code == 200
    await mk_run(world, D(30))
    r = await api.post(f"{P}/{rid2}/cancel", headers=api.hr)
    assert r.status_code == 409 and "payroll period locked" in r.text
    assert await _status(rid2) == "approved"


async def test_chain_path(api, world, chain):
    q = (await req(api, s=0, e=1)).json()
    assert q["routed_via"] == "chain"
    r = await decide(api, q["id"], who="hr")
    assert r.status_code == 409 and "approvals" in r.text
    r = await api.get("/api/v1/approval-chains/my-queue", headers=api.hr)
    row = next(x for x in r.json() if x["entity"]["id"] == q["id"]
               and x["entity"]["kind"] == "work_location")
    assert row["entity"]["title"].startswith("WFH")
    iid = row["instance"]["id"]
    r = await api.post(f"/api/v1/approval-chains/instances/{iid}/act",
                       headers=api.hr, json={"action": "approve"})
    assert r.status_code == 200, r.text
    assert await _status(q["id"]) == "approved"
    async with SessionLocal() as db:
        assert await WL.approved_portion(db, world["uid"]["emp"], D(1)) == "full"
    # reject
    q2 = (await req(api, s=10)).json()
    r = await api.get("/api/v1/approval-chains/my-queue", headers=api.hr)
    iid2 = next(x["instance"]["id"] for x in r.json()
                if x["entity"]["id"] == q2["id"]
                and x["entity"]["kind"] == "work_location")
    r = await api.post(f"/api/v1/approval-chains/instances/{iid2}/act",
                       headers=api.hr, json={"action": "reject"})
    assert r.status_code == 200
    assert await _status(q2["id"]) == "rejected"
    # cancel closes the instance
    q3 = (await req(api, s=20)).json()
    r = await api.post(f"{P}/{q3['id']}/cancel", headers=api.emp)
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    async with SessionLocal() as db:
        inst = (await db.execute(select(ChainedApprovalInstance).where(
            ChainedApprovalInstance.entity_type == "work_location",
            ChainedApprovalInstance.entity_id == q3["id"]))).scalars().one()
        assert inst.status == "cancelled"


async def test_concurrent_creates(api, world):
    c2, h2 = await _second_client(world, "emp2")
    try:
        r1, r2 = await asyncio.gather(
            req(api, s=0, e=2),
            c2.post(P, headers=h2, json={
                "kind": "wfh", "start_date": iso(D(0)),
                "end_date": iso(D(2)), "purpose": "x"}))
    finally:
        await c2.aclose()
    assert (r1.status_code, r2.status_code) == (201, 201), (r1.text, r2.text)
    c3, h3 = await _second_client(world, "emp")
    try:
        r1, r2 = await asyncio.gather(
            req(api, s=10, e=12),
            c3.post(P, headers=h3, json={
                "kind": "wfh", "start_date": iso(D(11)),
                "end_date": iso(D(13)), "purpose": "x"}))
    finally:
        await c3.aclose()
    assert sorted([r1.status_code, r2.status_code]) == [201, 409], (
        r1.text, r2.text)


async def test_decide_vs_cancel_race(api, world):
    rid = (await req(api, s=0)).json()["id"]
    c2, h2 = await _second_client(world, "mgr")
    try:
        rd, rc = await asyncio.gather(
            c2.post(f"{P}/{rid}/decide", headers=h2, json={"approve": True}),
            api.post(f"{P}/{rid}/cancel", headers=api.emp))
    finally:
        await c2.aclose()
    assert rd.status_code in (200, 409) and rc.status_code in (200, 409), (
        rd.text, rc.text)
    st = await _status(rid)
    assert st in ("approved", "cancelled")
    if rd.status_code == 409:
        assert st == "cancelled"


async def test_chain_act_vs_cancel_race(api, world, chain):
    q = (await req(api, s=0)).json()
    r = await api.get("/api/v1/approval-chains/my-queue", headers=api.hr)
    iid = next(x["instance"]["id"] for x in r.json()
               if x["entity"]["kind"] == "work_location"
               and x["entity"]["id"] == q["id"])
    c2, h2 = await _second_client(world, "hr")
    try:
        ra, rc = await asyncio.gather(
            c2.post(f"/api/v1/approval-chains/instances/{iid}/act",
                    headers=h2, json={"action": "approve"}),
            api.post(f"{P}/{q['id']}/cancel", headers=api.emp))
    finally:
        await c2.aclose()
    assert ra.status_code < 500 and rc.status_code < 500, (ra.text, rc.text)
    async with SessionLocal() as db:
        wr = await db.get(WorkLocationRequest, q["id"])
        inst = await db.get(ChainedApprovalInstance, iid)
        assert wr.status in ("approved", "cancelled")
        assert inst.status in ("approved", "cancelled")
        if inst.status == "cancelled":
            assert wr.status == "cancelled"


async def test_list_scoping(api, world):
    a = (await req(api, s=0)).json()["id"]          # emp (reports to mgr)
    b = (await req(api, who="emp2", s=0)).json()["id"]
    assert (await api.get(P, headers=api.plain)).status_code == 403
    ids = {x["id"] for x in (await api.get(
        f"{P}?status=pending", headers=api.mgr)).json()}
    assert a in ids and b not in ids
    for who in ("hr", "lv", "su"):
        ids = {x["id"] for x in (await api.get(P, headers=getattr(api, who))
                                 ).json()}
        assert {a, b} <= ids, who
    r = await api.get(f"{P}?user_id={world['uid']['emp2']}&kind=wfh"
                      f"&from={iso(D(0))}&to={iso(D(0))}", headers=api.hr)
    assert [x["id"] for x in r.json()] == [b]
    assert (await api.get(f"{P}?status=bogus", headers=api.hr)
            ).status_code == 422


async def test_permissions(api, world):
    rid = (await req(api, s=0)).json()["id"]
    assert (await decide(api, rid, who="emp")).status_code == 403   # self
    assert (await decide(api, rid, who="plain")).status_code == 403
    assert (await decide(api, rid, who="su")).status_code == 200
    rid2 = (await req(api, s=5)).json()["id"]
    assert (await decide(api, rid2, who="lv")).status_code == 200
    rid3 = (await req(api, s=9)).json()["id"]
    assert (await decide(api, rid3, who="hr", approve=False)
            ).status_code == 200
    assert (await api.post(f"{P}/999999999/decide", headers=api.hr,
                           json={"approve": True})).status_code == 404


async def test_create_in_locked_period(api, world):
    await mk_run(world, D(-3))
    try:
        r = await req(api, s=-3)
        assert r.status_code == 409 and "payroll period locked" in r.text
        async with SessionLocal() as db:
            n = (await db.execute(select(WorkLocationRequest.id).where(
                WorkLocationRequest.user_id == world["uid"]["emp"]))
                 ).all()
        assert n == []
    finally:
        await drop_runs(world)
    assert (await req(api, s=-3)).status_code == 201


async def test_create_multi_day_later_date_locked(api, world):
    # only the month of the LAST date is locked
    await mk_run(world, D(30))
    try:
        r = await req(api, s=0, e=30)
        if (D(0).year, D(0).month) != (D(30).year, D(30).month):
            assert r.status_code == 409 and "payroll period locked" in r.text
        else:
            assert r.status_code == 409
    finally:
        await drop_runs(world)


async def test_hr_cancel_notifies_owner(api, world):
    rid = (await req(api, s=5)).json()["id"]
    r = await api.post(f"{P}/{rid}/cancel", headers=api.hr)
    assert r.status_code == 200 and r.json()["user_name"]
    async with SessionLocal() as db:
        notes = (await db.execute(select(Notification).where(
            Notification.user_id == world["uid"]["emp"],
            Notification.resource_type == "work_location",
            Notification.resource_id == str(rid)))).scalars().all()
    assert any("cancelled" in n.title.lower() for n in notes)
    # owner cancelling their own request sends no cancel notice
    rid2 = (await req(api, s=9)).json()["id"]
    await api.post(f"{P}/{rid2}/cancel", headers=api.emp)
    async with SessionLocal() as db:
        notes = (await db.execute(select(Notification).where(
            Notification.resource_type == "work_location",
            Notification.resource_id == str(rid2),
            Notification.user_id == world["uid"]["emp"]))).scalars().all()
    assert notes == []
