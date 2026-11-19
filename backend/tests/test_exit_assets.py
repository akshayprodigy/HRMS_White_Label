"""Exit clearance asset block (Roadmap v2 Phase 5, Task 7). Real dev DB, full teardown."""
import uuid
from datetime import date

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, insert, select

from app.api import deps
from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.main import create_app
from app.models.asset import Asset, AssetCategory
from app.models.audit import AuditLog
from app.models.employee import Employee, EmployeeStatus
from app.models.employee_asset import EmployeeAsset
from app.models.exit_management import (
    ClearanceItem, ClearanceRequest, Resignation,
)
from app.models.notification import Notification
from app.models.user import Role, User, user_roles
from app.services import assets as svc

P = "/api/v1/exit"


async def _cleanup(sfx):
    async with SessionLocal() as db:
        uids = list((await db.execute(select(User.id).where(
            User.email.like(f"exa\\_%\\_{sfx}@test.com")))).scalars().all())
        eids = list((await db.execute(select(Employee.id).where(
            Employee.user_id.in_(uids)))).scalars().all()) if uids else []
        cids = list((await db.execute(select(AssetCategory.id).where(
            AssetCategory.name.like(f"%{sfx}%")))).scalars().all())
        aids = list((await db.execute(select(Asset.id).where(
            Asset.category_id.in_(cids)))).scalars().all()) if cids else []
        rids = list((await db.execute(select(Resignation.id).where(
            Resignation.employee_id.in_(eids)))).scalars().all()) if eids else []
        if rids:
            crids = list((await db.execute(select(ClearanceRequest.id).where(
                ClearanceRequest.resignation_id.in_(rids)))).scalars().all())
            if crids:
                await db.execute(delete(ClearanceItem).where(
                    ClearanceItem.clearance_request_id.in_(crids)))
                await db.execute(delete(Notification).where(
                    Notification.resource_type == "clearance",
                    Notification.resource_id.in_([str(c) for c in crids])))
                await db.execute(delete(ClearanceRequest).where(
                    ClearanceRequest.id.in_(crids)))
            await db.execute(delete(Notification).where(
                Notification.resource_type == "resignation",
                Notification.resource_id.in_([str(r) for r in rids])))
            await db.execute(delete(Resignation).where(Resignation.id.in_(rids)))
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
            for n in ("hr", "emp"):
                us[n] = User(email=f"exa_{n}_{sfx}@test.com",
                             full_name=f"Exa {n} {sfx}",
                             hashed_password=get_password_hash("x"),
                             is_active=True)
            db.add_all(us.values())
            await db.commit()
            role = (await db.execute(
                select(Role).where(Role.name == "HR"))).scalars().first()
            await db.execute(insert(user_roles).values(
                user_id=us["hr"].id, role_id=role.id))
            emp = Employee(
                user_id=us["emp"].id, employee_id=f"EX{sfx}",
                department="T", designation="T",
                date_of_joining=date(2020, 1, 1),
                status=EmployeeStatus.ACTIVE)
            db.add(emp)
            cat = AssetCategory(name=f"ExitCat {sfx}", code=f"X{sfx[:4].upper()}",
                                is_active=True)
            db.add(cat)
            await db.flush()
            res = Resignation(
                employee_id=emp.id, reason="personal", status="clearance",
                resignation_date=date.today(), last_working_day=date.today(),
                notice_period_days=30)
            db.add(res)
            await db.flush()
            db.add(ClearanceRequest(
                resignation_id=res.id, department="Finance",
                assigned_to_id=us["hr"].id, status="cleared"))
            await db.commit()
            ids.update(uid={n: u.id for n, u in us.items()}, eid=emp.id,
                       cat=cat.id, rid=res.id)
        yield ids
    finally:
        await _cleanup(sfx)


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
        c.hr = await _login(c, f"exa_hr_{s}@test.com")
        c.emp = await _login(c, f"exa_emp_{s}@test.com")
        yield c


async def allocate_asset(world, tag_suffix="1"):
    """Create + allocate a register asset to the employee; returns (asset_id, tag)."""
    async with SessionLocal() as db:
        a = Asset(asset_tag=f"EX{world['sfx'].upper()}{tag_suffix}",
                  category_id=world["cat"], name=f"Laptop {tag_suffix}",
                  status="in_stock")
        db.add(a)
        await db.flush()
        emp = await db.get(Employee, world["eid"])
        actor = await db.get(User, world["uid"]["hr"])
        await svc.allocate(db, asset=a, employee=emp, actor=actor)
        await db.commit()
        return a.id, a.asset_tag


async def return_it(world, asset_id):
    async with SessionLocal() as db:
        a = await db.get(Asset, asset_id)
        actor = await db.get(User, world["uid"]["hr"])
        await svc.return_asset(db, asset=a, actor=actor)
        await db.commit()


async def lose_it(world, asset_id):
    async with SessionLocal() as db:
        a = await db.get(Asset, asset_id)
        actor = await db.get(User, world["uid"]["hr"])
        await svc.mark_lost(db, asset=a, actor=actor, remarks="lost in transit")
        await db.commit()


async def state(world):
    async with SessionLocal() as db:
        r = await db.get(Resignation, world["rid"])
        u = await db.get(User, world["uid"]["emp"])
        e = await db.get(Employee, world["eid"])
        return r.status, u.is_active, e.status


async def test_release_blocked_then_allowed(api, world):
    aid, tag = await allocate_asset(world)
    r = await api.post(f"{P}/resignations/{world['rid']}/release", headers=api.hr)
    assert r.status_code == 400, r.text
    assert "Assets not returned" in r.json()["error"]["message"]
    assert tag in r.json()["error"]["message"]
    st, active, estatus = await state(world)
    assert st == "clearance" and active is True and estatus != "inactive"

    await return_it(world, aid)
    r = await api.post(f"{P}/resignations/{world['rid']}/release", headers=api.hr)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "released"
    st, active, _ = await state(world)
    assert st == "released" and active is False


async def test_lost_allocation_does_not_block(api, world):
    aid, _ = await allocate_asset(world)
    await lose_it(world, aid)
    r = await api.post(f"{P}/resignations/{world['rid']}/release", headers=api.hr)
    assert r.status_code == 200, r.text


async def test_legacy_allocation_blocks(api, world):
    async with SessionLocal() as db:
        db.add(EmployeeAsset(
            employee_id=world["eid"], asset_id=None, status="allocated",
            asset_type="Laptop", model="Old Dell", identifier="LEG-1",
            issued_date=date(2021, 1, 1)))
        await db.commit()
    r = await api.post(f"{P}/resignations/{world['rid']}/release", headers=api.hr)
    assert r.status_code == 400, r.text
    assert "LEG-1" in r.json()["error"]["message"]
    st, active, _ = await state(world)
    assert st == "clearance" and active is True


async def test_details_list_outstanding_assets(api, world):
    aid, tag = await allocate_asset(world)
    async with SessionLocal() as db:
        db.add(EmployeeAsset(
            employee_id=world["eid"], asset_id=None, status="allocated",
            asset_type="Phone", model="Old Phone", identifier=None))
        await db.commit()
    for url, h in ((f"{P}/resign/my", api.emp),
                   (f"{P}/resignations/{world['rid']}", api.hr)):
        r = await api.get(url, headers=h)
        assert r.status_code == 200, r.text
        out = r.json()["outstanding_assets"]
        assert len(out) == 2
        reg = next(o for o in out if o["asset_id"] == aid)
        assert reg["asset_tag"] == tag and reg["name"] == "Laptop 1"
        assert reg["category"] == f"ExitCat {world['sfx']}"
        assert reg["allocation_id"] and reg["issued_date"]
        leg = next(o for o in out if o["asset_id"] is None)
        assert leg["asset_tag"] is None and leg["name"] == "Old Phone"
        assert leg["category"] == "Phone"
    await return_it(world, aid)
    r = await api.get(f"{P}/resignations/{world['rid']}", headers=api.hr)
    assert len(r.json()["outstanding_assets"]) == 1


async def _reset_for_initiate(world):
    async with SessionLocal() as db:
        await db.execute(delete(ClearanceRequest).where(
            ClearanceRequest.resignation_id == world["rid"]))
        r = await db.get(Resignation, world["rid"])
        r.status = "notice_period"
        await db.commit()


def _body(world, depts):
    return {"clearances": [{"department": d,
                            "assigned_to_id": world["uid"]["hr"],
                            "items": [{"item_name": "Dues"}]} for d in depts]}


def _asset_items(data):
    return [(c["department"], i["item_name"])
            for c in data for i in c["items"]
            if i["item_name"].startswith("Return assets:")]


async def test_initiate_adds_item_to_it_once(api, world):
    await _reset_for_initiate(world)
    _, tag = await allocate_asset(world)
    url = f"{P}/resignations/{world['rid']}/clearance"
    r = await api.post(url, headers=api.hr, json=_body(world, ["Finance", "it"]))
    assert r.status_code == 200, r.text
    assert _asset_items(r.json()) == [("it", f"Return assets: {tag}")]
    r = await api.post(url, headers=api.hr, json=_body(world, ["Finance", "IT"]))
    assert r.status_code == 200, r.text
    assert len(_asset_items(r.json())) == 1


async def test_initiate_without_it_uses_first(api, world):
    await _reset_for_initiate(world)
    _, tag = await allocate_asset(world)
    r = await api.post(f"{P}/resignations/{world['rid']}/clearance",
                       headers=api.hr, json=_body(world, ["Finance", "Admin"]))
    assert r.status_code == 200, r.text
    assert _asset_items(r.json()) == [("Finance", f"Return assets: {tag}")]


async def test_initiate_no_assets_no_item(api, world):
    await _reset_for_initiate(world)
    r = await api.post(f"{P}/resignations/{world['rid']}/clearance",
                       headers=api.hr, json=_body(world, ["Finance"]))
    assert r.status_code == 200, r.text
    assert _asset_items(r.json()) == []
