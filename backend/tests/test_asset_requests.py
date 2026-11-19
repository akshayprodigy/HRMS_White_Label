"""Employee asset requests (Roadmap v2 Phase 5, Task 6). Real dev DB, full teardown."""
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
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
from app.models.asset import Asset, AssetCategory, AssetRequest
from app.models.audit import AuditLog
from app.models.employee import Employee, EmployeeStatus
from app.models.employee_asset import EmployeeAsset
from app.models.notification import Notification
from app.models.user import Role, User, user_roles

P = "/api/v1/asset-requests"


async def _cleanup(sfx, ids):
    async with SessionLocal() as db:
        uids = list((await db.execute(select(User.id).where(
            User.email.like(f"areq\\_%\\_{sfx}@test.com")))).scalars().all())
        eids = list((await db.execute(select(Employee.id).where(
            Employee.user_id.in_(uids)))).scalars().all()) if uids else []
        cids = list((await db.execute(select(AssetCategory.id).where(
            AssetCategory.name.like(f"%{sfx}%")))).scalars().all())
        aids = list((await db.execute(select(Asset.id).where(
            Asset.category_id.in_(cids)))).scalars().all()) if cids else []
        rids = list((await db.execute(select(AssetRequest.id).where(
            AssetRequest.employee_id.in_(eids)))).scalars().all()) if eids else []
        # chains made by this test (any state) + their instances
        chain_ids = list((await db.execute(select(ApprovalChain.id).where(
            ApprovalChain.name.like(f"%{sfx}%")))).scalars().all())
        inst_ids = list((await db.execute(select(ChainedApprovalInstance.id).where(
            ChainedApprovalInstance.submitter_id.in_(uids)))).scalars().all()) if uids else []
        if inst_ids:
            await db.execute(delete(ChainedApprovalStepInstance).where(
                ChainedApprovalStepInstance.instance_id.in_(inst_ids)))
        if rids:
            await db.execute(delete(Notification).where(
                Notification.resource_type == "asset_request",
                Notification.resource_id.in_([str(r) for r in rids])))
            await db.execute(delete(AuditLog).where(
                AuditLog.resource_type == "asset_request",
                AuditLog.resource_id.in_([str(r) for r in rids])))
            await db.execute(delete(AssetRequest).where(AssetRequest.id.in_(rids)))
        if inst_ids:
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
        if eids:
            await db.execute(delete(EmployeeAsset).where(
                EmployeeAsset.employee_id.in_(eids)))
        if aids:
            await db.execute(delete(EmployeeAsset).where(
                EmployeeAsset.asset_id.in_(aids)))
            await db.execute(delete(AuditLog).where(
                AuditLog.resource_type == "asset",
                AuditLog.resource_id.in_([str(a) for a in aids])))
            await db.execute(delete(Asset).where(Asset.id.in_(aids)))
        if cids:
            await db.execute(delete(AssetCategory).where(AssetCategory.id.in_(cids)))
        if uids:
            await db.execute(delete(Notification).where(Notification.user_id.in_(uids)))
            await db.execute(delete(AuditLog).where(AuditLog.user_id.in_(uids)))
            await db.execute(delete(Employee).where(Employee.user_id.in_(uids)))
            await db.execute(delete(user_roles).where(user_roles.c.user_id.in_(uids)))
            await db.execute(delete(User).where(User.id.in_(uids)))
        await db.commit()


@pytest.fixture
async def world():
    sfx = uuid.uuid4().hex[:8]
    ids: dict = {"sfx": sfx}
    try:
        async with SessionLocal() as db:
            us = {}
            for n in ("hr", "emp", "plain"):
                us[n] = User(email=f"areq_{n}_{sfx}@test.com",
                             full_name=f"Areq {n} {sfx}",
                             hashed_password=get_password_hash("x"),
                             is_active=True)
            db.add_all(us.values())
            await db.commit()
            role = (await db.execute(
                select(Role).where(Role.name == "HR"))).scalars().first()
            await db.execute(insert(user_roles).values(
                user_id=us["hr"].id, role_id=role.id))
            for n in ("emp", "plain"):
                db.add(Employee(
                    user_id=us[n].id, employee_id=f"AR{n[0]}{sfx}",
                    department="T", designation="T",
                    date_of_joining=date(2020, 1, 1),
                    status=EmployeeStatus.ACTIVE))
            cats = {}
            for k, active in (("a", True), ("b", True), ("off", False)):
                cats[k] = AssetCategory(
                    name=f"ReqCat{k} {sfx}", code=f"R{k[0].upper()}{sfx[:4].upper()}",
                    is_active=active)
            db.add_all(cats.values())
            await db.commit()
            ids["uid"] = {n: u.id for n, u in us.items()}
            ids["cat"] = {k: c.id for k, c in cats.items()}
        yield ids
    finally:
        await _cleanup(sfx, ids)


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
        s = world["sfx"]
        c.hr = await _login(c, f"areq_hr_{s}@test.com")
        c.emp = await _login(c, f"areq_emp_{s}@test.com")
        c.plain = await _login(c, f"areq_plain_{s}@test.com")
        yield c


async def mk_asset(world, key="a", status="in_stock", n=1):
    async with SessionLocal() as db:
        a = Asset(asset_tag=f"RQ{world['sfx'].upper()}{key.upper()}{uuid.uuid4().hex[:4].upper()}",
                  category_id=world["cat"][key], name=f"Laptop {n}",
                  status=status)
        db.add(a)
        await db.commit()
        return a.id


async def submit(api, world, key="a", reason="Need a laptop for work", **kw):
    r = await api.post(P, headers=api.emp, json={
        "category_id": world["cat"][key], "reason": reason, **kw})
    return r


async def notes(uid, rid):
    async with SessionLocal() as db:
        return list((await db.execute(select(Notification).where(
            Notification.user_id == uid,
            Notification.resource_type == "asset_request",
            Notification.resource_id == str(rid)))).scalars().all())


async def test_direct_path_end_to_end(api, world):
    r = await submit(api, world)
    assert r.status_code == 200, r.text
    req = r.json()
    assert req["status"] == "pending" and req["routed_via"] == "direct"
    assert req["category"]["id"] == world["cat"]["a"]
    n = await notes(world["uid"]["hr"], req["id"])
    assert any(x.event_type == "asset_request_submitted" for x in n)

    r = await api.get(P, headers=api.hr)
    assert r.status_code == 200
    row = next(x for x in r.json() if x["id"] == req["id"])
    assert row["employee"]["emp_code"].startswith("AR")
    assert row["routed_via"] == "direct"

    r = await api.post(f"{P}/{req['id']}/decide", headers=api.hr,
                       json={"action": "approve", "note": "ok"})
    assert r.status_code == 200 and r.json()["status"] == "approved"
    aid = await mk_asset(world)
    r = await api.post(f"{P}/{req['id']}/fulfil", headers=api.hr,
                       json={"asset_id": aid})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "fulfilled"
    assert body["fulfilled_asset"]["id"] == aid
    async with SessionLocal() as db:
        a = await db.get(Asset, aid)
        assert a.status == "allocated"
        al = (await db.execute(select(EmployeeAsset).where(
            EmployeeAsset.asset_id == aid,
            EmployeeAsset.status == "allocated"))).scalars().one()
        rq = await db.get(AssetRequest, req["id"])
        assert rq.fulfilled_asset_id == aid and rq.allocation_id == al.id
        eid = rq.employee_id
        assert al.employee_id == eid
    n = await notes(world["uid"]["emp"], req["id"])
    assert {"asset_request_decided", "asset_request_fulfilled"} <= {
        x.event_type for x in n}
    r = await api.get(f"{P}/my", headers=api.emp)
    mine = next(x for x in r.json() if x["id"] == req["id"])
    assert mine["status"] == "fulfilled"
    assert mine["fulfilled_asset"]["asset_tag"].startswith("RQ")


async def test_create_validation(api, world):
    assert (await submit(api, world)).status_code == 200
    assert (await submit(api, world)).status_code == 409
    assert (await submit(api, world, key="off")).status_code == 422
    assert (await submit(api, world, key="b", reason="  ab  ")).status_code == 422
    past = (date.today() - timedelta(days=1)).isoformat()
    assert (await submit(api, world, key="b", needed_by=past)).status_code == 422
    fut = (date.today() + timedelta(days=5)).isoformat()
    assert (await submit(api, world, key="b", needed_by=fut)).status_code == 200
    r = await api.post(P, headers=api.emp, json={
        "category_id": 99999999, "reason": "need something"})
    assert r.status_code == 422


async def test_cancel_rules(api, world):
    rid = (await submit(api, world)).json()["id"]
    r = await api.post(f"{P}/{rid}/cancel", headers=api.plain)
    assert r.status_code == 404
    r = await api.post(f"{P}/{rid}/cancel", headers=api.emp)
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    r = await api.post(f"{P}/{rid}/cancel", headers=api.emp)
    assert r.status_code == 409
    rid2 = (await submit(api, world)).json()["id"]
    await api.post(f"{P}/{rid2}/decide", headers=api.hr, json={"action": "approve"})
    r = await api.post(f"{P}/{rid2}/cancel", headers=api.emp)
    assert r.status_code == 409


async def test_decide_rules_and_reject(api, world):
    rid = (await submit(api, world)).json()["id"]
    r = await api.post(f"{P}/{rid}/decide", headers=api.hr,
                       json={"action": "reject", "note": "no budget"})
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    assert r.json()["decision_note"] == "no budget"
    n = await notes(world["uid"]["emp"], rid)
    assert any(x.event_type == "asset_request_decided" for x in n)
    r = await api.post(f"{P}/{rid}/decide", headers=api.hr,
                       json={"action": "approve"})
    assert r.status_code == 409
    r = await api.post(f"{P}/{rid}/decide", headers=api.hr,
                       json={"action": "maybe"})
    assert r.status_code == 422


async def test_fulfil_rules(api, world):
    rid = (await submit(api, world)).json()["id"]
    aid_wrong = await mk_asset(world, "b")
    r = await api.post(f"{P}/{rid}/fulfil", headers=api.hr,
                       json={"asset_id": aid_wrong})
    assert r.status_code == 409  # still pending
    await api.post(f"{P}/{rid}/decide", headers=api.hr, json={"action": "approve"})
    r = await api.post(f"{P}/{rid}/fulfil", headers=api.hr,
                       json={"asset_id": aid_wrong})
    assert r.status_code == 422
    busy = await mk_asset(world, "a", status="allocated")
    r = await api.post(f"{P}/{rid}/fulfil", headers=api.hr,
                       json={"asset_id": busy})
    assert r.status_code == 409
    r = await api.post(f"{P}/{rid}/fulfil", headers=api.hr, json={
        "asset_id": aid_wrong, "allow_other_category": True})
    assert r.status_code == 200 and r.json()["status"] == "fulfilled"
    r = await api.post(f"{P}/{rid}/fulfil", headers=api.hr, json={
        "asset_id": aid_wrong, "allow_other_category": True})
    assert r.status_code == 409
    r = await api.post(f"{P}/{rid}/fulfil", headers=api.hr,
                       json={"asset_id": 99999999})
    assert r.status_code == 409  # request no longer approved


async def test_fulfil_missing_asset_404(api, world):
    rid = (await submit(api, world)).json()["id"]
    await api.post(f"{P}/{rid}/decide", headers=api.hr, json={"action": "approve"})
    r = await api.post(f"{P}/{rid}/fulfil", headers=api.hr,
                       json={"asset_id": 99999999})
    assert r.status_code == 404


async def test_auth(api):
    for m, p, b in [("GET", P, None), ("POST", f"{P}/1/decide", {"action": "approve"}),
                    ("POST", f"{P}/1/fulfil", {"asset_id": 1})]:
        r = await api.request(m, p, headers=api.emp, json=b)
        assert r.status_code == 403, (m, p)
        r = await api.request(m, p, json=b)
        assert r.status_code == 401, (m, p)
    assert (await api.get(f"{P}/my")).status_code == 401
    assert (await api.post(P, json={})).status_code == 401


# ── chain path ───────────────────────────────────────────────────────────
@pytest.fixture
async def chain(api, world):
    async with SessionLocal() as db:
        c = ApprovalChain(
            name=f"AreqChain {world['sfx']}", entity_type="asset_request",
            is_active=True, effective_from=date(2020, 1, 1),
            skip_if_same_person=False)
        db.add(c)
        await db.flush()
        db.add(ApprovalChainStep(
            chain_id=c.id, step_order=1, approver_type="specific_user",
            approver_ref=str(world["uid"]["hr"]), label="Mgr"))
        await db.commit()
        world["chain_id"] = c.id
    yield c  # teardown deletes the chain via world cleanup (name contains sfx)


async def test_chain_path(api, world, chain):
    r = await submit(api, world, key="a")
    assert r.status_code == 200, r.text
    q = r.json()
    assert q["routed_via"] == "chain" and q["approval_instance_id"]
    r = await api.post(f"{P}/{q['id']}/decide", headers=api.hr,
                       json={"action": "approve"})
    assert r.status_code == 409
    r = await api.get("/api/v1/approval-chains/my-queue", headers=api.hr)
    row = next(x for x in r.json()
               if x["instance"]["id"] == q["approval_instance_id"])
    assert row["entity"]["kind"] == "asset_request"
    assert row["entity"]["id"] == q["id"] and "ReqCata" in row["entity"]["title"]
    r = await api.post(
        f"/api/v1/approval-chains/instances/{q['approval_instance_id']}/act",
        headers=api.hr, json={"action": "approve"})
    assert r.status_code == 200, r.text
    r = await api.get(f"{P}/my", headers=api.emp)
    assert next(x for x in r.json() if x["id"] == q["id"])["status"] == "approved"
    n = await notes(world["uid"]["hr"], q["id"])
    assert any(x.event_type == "asset_request_approved" for x in n)

    # reject via chain
    r2 = (await submit(api, world, key="b")).json()
    r = await api.post(
        f"/api/v1/approval-chains/instances/{r2['approval_instance_id']}/act",
        headers=api.hr, json={"action": "reject"})
    assert r.status_code == 200, r.text
    r = await api.get(f"{P}/my", headers=api.emp)
    assert next(x for x in r.json() if x["id"] == r2["id"])["status"] == "rejected"

    # cancel via employee
    await api.post(f"{P}/{q['id']}/fulfil", headers=api.hr, json={
        "asset_id": await mk_asset(world, "a")})  # free category a slot
    r3 = (await submit(api, world, key="b")).json()
    assert r3["routed_via"] == "chain"
    r = await api.post(f"{P}/{r3['id']}/cancel", headers=api.emp)
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    async with SessionLocal() as db:
        inst = await db.get(ChainedApprovalInstance, r3["approval_instance_id"])
        assert inst.status == "cancelled" and inst.finalized_at is not None
    r = await api.get("/api/v1/approval-chains/my-queue", headers=api.hr)
    assert all(x["instance"]["id"] != r3["approval_instance_id"] for x in r.json())


async def test_concurrent_double_submit(api, world):
    import asyncio
    app = create_app()
    app.dependency_overrides[deps.verify_attendance] = lambda: None
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as c2:
        h2 = await _login(c2, f"areq_emp_{world['sfx']}@test.com")
        body = {"category_id": world["cat"]["a"], "reason": "Need a laptop now"}
        r1, r2 = await asyncio.gather(
            api.post(P, headers=api.emp, json=body),
            c2.post(P, headers=h2, json=body))
    assert sorted([r1.status_code, r2.status_code]) == [200, 409], (
        r1.text, r2.text)
    async with SessionLocal() as db:
        n = len((await db.execute(select(AssetRequest.id).where(
            AssetRequest.category_id == world["cat"]["a"]))).all())
    assert n == 1


async def test_employee_categories_active_only(api, world):
    r = await api.get(f"{P}/categories", headers=api.plain)
    assert r.status_code == 200, r.text
    mine = {c["id"]: c for c in r.json() if str(world["sfx"]) in c["name"]}
    assert set(mine) == {world["cat"]["a"], world["cat"]["b"]}
    assert set(mine[world["cat"]["a"]]) == {"id", "name", "code"}
    names = [c["name"] for c in r.json()]
    assert names == sorted(names)
    assert (await api.get(f"{P}/categories")).status_code == 401


async def test_concurrent_chain_act_vs_cancel(api, world, chain):
    """Approver act racing the employee's cancel on one chained pending
    request: never a 5xx; request and instance end in agreeing states."""
    import asyncio
    app = create_app()
    app.dependency_overrides[deps.verify_attendance] = lambda: None
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as c2:
        h2 = await _login(c2, f"areq_hr_{world['sfx']}@test.com")
        async with SessionLocal() as db:
            extra = []
            for i in range(6):
                c = AssetCategory(
                    name=f"RaceCat{i} {world['sfx']}",
                    code=f"Z{i}{world['sfx'][:4].upper()}", is_active=True)
                db.add(c)
                extra.append(c)
            await db.commit()
            cat_ids = [c.id for c in extra]
        outcomes = set()
        for cid in cat_ids:
            r = await api.post(P, headers=api.emp, json={
                "category_id": cid, "reason": "Need a laptop for work"})
            assert r.status_code == 200, r.text
            q = r.json()
            assert q["routed_via"] == "chain"
            ra, rc = await asyncio.gather(
                c2.post("/api/v1/approval-chains/instances/"
                        f"{q['approval_instance_id']}/act",
                        headers=h2, json={"action": "approve"}),
                api.post(f"{P}/{q['id']}/cancel", headers=api.emp))
            assert ra.status_code < 500 and rc.status_code < 500, (
                ra.text, rc.text)
            async with SessionLocal() as db:
                req = await db.get(AssetRequest, q["id"])
                inst = await db.get(
                    ChainedApprovalInstance, q["approval_instance_id"])
                assert (req.status, inst.status) in (
                    ("cancelled", "cancelled"), ("approved", "approved")), (
                    req.status, inst.status, ra.text, rc.text)
                outcomes.add(req.status)
