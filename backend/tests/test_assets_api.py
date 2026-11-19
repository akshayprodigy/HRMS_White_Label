"""Asset register API (Roadmap v2 Phase 5, Task 4). Real dev DB, full teardown."""
import uuid
from datetime import date, timedelta

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
from app.models.user import Role, User, user_roles

P = "/api/v1/assets"


@pytest.fixture
async def world():
    sfx = uuid.uuid4().hex[:8]
    ids: dict = {"sfx": sfx}
    try:
        async with SessionLocal() as db:
            us = {}
            for n in ("hr", "emp", "plain"):
                us[n] = User(email=f"aapi_{n}_{sfx}@test.com",
                             full_name=f"Aapi {n} {sfx}",
                             hashed_password=get_password_hash("x"),
                             is_active=True)
            db.add_all(us.values())
            await db.commit()
            role = (await db.execute(
                select(Role).where(Role.name == "HR"))).scalars().first()
            assert role is not None
            await db.execute(insert(user_roles).values(
                user_id=us["hr"].id, role_id=role.id))
            emp = Employee(
                user_id=us["emp"].id, employee_id=f"AA{sfx}",
                department="T", designation="T",
                date_of_joining=date(2020, 1, 1),
                status=EmployeeStatus.ACTIVE)
            db.add(emp)
            await db.commit()
            ids["emp_id"] = emp.id
            ids["emp_name"] = us["emp"].full_name
            ids["hr_uid"] = us["hr"].id
        yield ids
    finally:
        async with SessionLocal() as db:
            uids = list((await db.execute(select(User.id).where(
                User.email.like(f"aapi\\_%\\_{sfx}@test.com")))).scalars().all())
            cids = list(ids.get("cat_ids", []))
            aids = list((await db.execute(select(Asset.id).where(
                Asset.category_id.in_(cids)))).scalars().all()) if cids else []
            eids = list((await db.execute(select(Employee.id).where(
                Employee.user_id.in_(uids)))).scalars().all())
            await db.execute(delete(EmployeeAsset).where(
                EmployeeAsset.employee_id.in_(eids)))
            if aids:
                await db.execute(delete(EmployeeAsset).where(
                    EmployeeAsset.asset_id.in_(aids)))
                await db.execute(delete(AuditLog).where(
                    AuditLog.resource_type == "asset",
                    AuditLog.resource_id.in_([str(a) for a in aids])))
                await db.execute(delete(Asset).where(Asset.id.in_(aids)))
            # legacy-route categories are named by sfx
            lcids = list((await db.execute(select(AssetCategory.id).where(
                AssetCategory.name.like(f"%{sfx}%")))).scalars().all())
            if lcids:
                laids = list((await db.execute(select(Asset.id).where(
                    Asset.category_id.in_(lcids)))).scalars().all())
                if laids:
                    await db.execute(delete(EmployeeAsset).where(
                        EmployeeAsset.asset_id.in_(laids)))
                    await db.execute(delete(AuditLog).where(
                        AuditLog.resource_type == "asset",
                        AuditLog.resource_id.in_([str(a) for a in laids])))
                    await db.execute(delete(Asset).where(Asset.id.in_(laids)))
                await db.execute(delete(AssetCategory).where(
                    AssetCategory.id.in_(lcids)))
            if cids:
                await db.execute(delete(AssetCategory).where(
                    AssetCategory.id.in_(cids)))
            await db.execute(delete(AuditLog).where(AuditLog.user_id.in_(uids)))
            await db.execute(delete(Employee).where(Employee.user_id.in_(uids)))
            await db.execute(delete(user_roles).where(
                user_roles.c.user_id.in_(uids)))
            await db.execute(delete(User).where(User.id.in_(uids)))
            await db.commit()


async def _login(c, email, pw="x"):
    r = await c.post("/api/v1/auth/login",
                     data={"username": email, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
async def api(world):
    app = create_app()
    app.dependency_overrides[deps.verify_attendance] = lambda: None
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as c:
        c.hr = await _login(c, f"aapi_hr_{world['sfx']}@test.com")
        c.plain = await _login(c, f"aapi_plain_{world['sfx']}@test.com")
        yield c


@pytest.fixture
async def cat(api, world):
    code = f"T{world['sfx'][:4].upper()}"
    r = await api.post(f"{P}/categories", headers=api.hr, json={
        "name": f"Cat {world['sfx']}", "code": code,
        "default_useful_life_months": 24})
    assert r.status_code == 200, r.text
    world.setdefault("cat_ids", []).append(r.json()["id"])
    return r.json()


async def mk(api, cat, **kw):
    body = {"category_id": cat["id"], "name": "Laptop X"}
    body.update(kw)
    r = await api.post(P, headers=api.hr, json=body)
    assert r.status_code == 200, r.text
    return r.json()


async def test_permission_denied(api):
    reqs = [
        ("GET", f"{P}/categories", None), ("POST", f"{P}/categories", {}),
        ("PATCH", f"{P}/categories/1", {}), ("GET", P, None),
        ("POST", P, {}), ("GET", f"{P}/1", None), ("PATCH", f"{P}/1", {}),
        ("POST", f"{P}/1/allocate", {}), ("POST", f"{P}/1/return", {}),
        ("POST", f"{P}/1/lost", {}), ("POST", f"{P}/1/status", {}),
        ("GET", f"{P}/1/qr.svg", None), ("GET", f"{P}/by-tag/x", None),
        ("GET", f"{P}/summary", None),
    ]
    for m, p, b in reqs:
        r = await api.request(m, p, headers=api.plain, json=b)
        assert r.status_code == 403, (m, p, r.status_code)


async def test_category_rules(api, world, cat):
    r = await api.post(f"{P}/categories", headers=api.hr, json={
        "name": f"CAT {world['sfx']}", "code": "ZZ9"})
    assert r.status_code == 409
    r = await api.post(f"{P}/categories", headers=api.hr, json={
        "name": f"Other {world['sfx']}", "code": "bad code"})
    assert r.status_code == 422
    r = await api.get(f"{P}/categories", headers=api.hr)
    assert any(c["id"] == cat["id"] for c in r.json())
    r = await api.patch(f"{P}/categories/{cat['id']}", headers=api.hr,
                        json={"is_active": False})
    assert r.status_code == 200 and r.json()["is_active"] is False
    r = await api.post(P, headers=api.hr, json={
        "category_id": cat["id"], "name": "x"})
    assert r.status_code == 422


async def test_create_tags(api, cat):
    a = await mk(api, cat)
    assert a["asset_tag"] == f"{cat['code']}-000001"
    assert a["status"] == "in_stock"
    b = await mk(api, cat, asset_tag=f"{cat['code'].lower()}-custom")
    assert b["asset_tag"] == f"{cat['code']}-CUSTOM"
    r = await api.post(P, headers=api.hr, json={
        "category_id": cat["id"], "name": "d", "asset_tag": b["asset_tag"]})
    assert r.status_code == 409
    r = await api.post(P, headers=api.hr, json={
        "category_id": cat["id"], "name": "d",
        "purchase_date": (date.today() + timedelta(days=5)).isoformat()})
    assert r.status_code == 422


async def test_allocate_flow_and_filters(api, world, cat):
    a = await mk(api, cat)
    r = await api.post(f"{P}/{a['id']}/allocate", headers=api.hr,
                       json={"employee_id": world["emp_id"]})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "allocated"
    assert d["holder"]["employee_id"] == world["emp_id"]
    assert len(d["history"]) == 1
    r = await api.post(f"{P}/{a['id']}/allocate", headers=api.hr,
                       json={"employee_id": world["emp_id"]})
    assert r.status_code == 409
    b = await mk(api, cat)
    r = await api.post(f"{P}/{b['id']}/allocate", headers=api.hr,
                       json={"employee_id": 99999999})
    assert r.status_code == 404
    r = await api.get(P, headers=api.hr, params={"q": world["emp_name"]})
    assert [i["id"] for i in r.json()["items"]] == [a["id"]]
    r = await api.get(P, headers=api.hr, params={
        "status": "in_stock", "category_id": cat["id"]})
    j = r.json()
    assert j["total"] == 1 and j["items"][0]["id"] == b["id"]
    assert j["items"][0]["holder"] is None


async def test_expiring_filter(api, cat):
    soon = (date.today() + timedelta(days=10)).isoformat()
    far = (date.today() + timedelta(days=200)).isoformat()
    a = await mk(api, cat, warranty_expiry=soon)
    await mk(api, cat, amc_expiry=far)
    r = await api.get(P, headers=api.hr, params={
        "expiring_within_days": 30, "category_id": cat["id"]})
    assert [i["id"] for i in r.json()["items"]] == [a["id"]]


async def test_return_and_lost(api, world, cat):
    a = await mk(api, cat)
    await api.post(f"{P}/{a['id']}/allocate", headers=api.hr,
                   json={"employee_id": world["emp_id"]})
    r = await api.post(f"{P}/{a['id']}/return", headers=api.hr,
                       json={"to_status": "in_repair", "condition": "cracked"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "in_repair" and d["holder"] is None
    assert d["history"][0]["status"] == "returned"
    assert d["history"][0]["returned_condition"] == "cracked"
    r = await api.post(f"{P}/{a['id']}/lost", headers=api.hr, json={})
    assert r.status_code == 422
    r = await api.post(f"{P}/{a['id']}/lost", headers=api.hr,
                       json={"remarks": "x"})
    assert r.status_code == 422
    r = await api.post(f"{P}/{a['id']}/lost", headers=api.hr,
                       json={"remarks": "stolen"})
    assert r.status_code == 200 and r.json()["status"] == "lost"
    r = await api.post(f"{P}/{a['id']}/status", headers=api.hr,
                       json={"to_status": "in_stock"})
    assert r.status_code == 200 and r.json()["status"] == "in_stock"
    r = await api.post(f"{P}/{a['id']}/status", headers=api.hr,
                       json={"to_status": "lost"})
    assert r.status_code == 422


async def test_patch_rejects_status(api, cat):
    a = await mk(api, cat)
    r = await api.patch(f"{P}/{a['id']}", headers=api.hr,
                        json={"status": "retired"})
    assert r.status_code == 422
    r = await api.patch(f"{P}/{a['id']}", headers=api.hr, json={"name": "New"})
    assert r.status_code == 200 and r.json()["name"] == "New"
    r = await api.get(f"{P}/999999999", headers=api.hr)
    assert r.status_code == 404


async def test_qr_and_by_tag(api, cat):
    a = await mk(api, cat)
    r = await api.get(f"{P}/{a['id']}/qr.svg", headers=api.hr)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/svg+xml")
    assert "<svg" in r.text
    r = await api.get(f"{P}/by-tag/{a['asset_tag'].lower()}", headers=api.hr)
    assert r.status_code == 200 and r.json()["id"] == a["id"]
    r = await api.get(f"{P}/by-tag/nope-{cat['code']}", headers=api.hr)
    assert r.status_code == 404


async def test_summary_and_depreciation(api, cat):
    before = (await api.get(f"{P}/summary", headers=api.hr)).json()
    pd = (date.today() - timedelta(days=400)).isoformat()
    a = await mk(api, cat, purchase_date=pd, purchase_cost_paise=240000,
                 warranty_expiry=(date.today() + timedelta(days=5)).isoformat())
    await mk(api, cat)
    d = (await api.get(f"{P}/{a['id']}", headers=api.hr)).json()
    assert d["depreciation"]["cost_paise"] == 240000
    assert 0 < d["depreciation"]["book_value_paise"] < 240000
    assert d["maintenance"] == [] and d["maintenance_cost_total_paise"] == 0
    assert (d["effective_useful_life_months"], d["life_source"]) == (24, "category")
    after = (await api.get(f"{P}/summary", headers=api.hr)).json()
    assert set(after["by_status"]) == {
        "in_stock", "allocated", "in_repair", "retired", "lost"}
    assert after["by_status"]["in_stock"] == before["by_status"]["in_stock"] + 2
    assert after["expiring_30d"] == before["expiring_30d"] + 1
    assert after["total_cost_paise"] == before["total_cost_paise"] + 240000
    assert (after["total_book_value_paise"]
            == before["total_book_value_paise"] + d["depreciation"]["book_value_paise"])
    cnt = {c["id"]: c["count"] for c in after["by_category"]}
    assert cnt[cat["id"]] == 2
    own = await mk(api, cat, useful_life_months=12)
    assert (own["effective_useful_life_months"], own["life_source"]) == (12, "asset")
    r = await api.patch(f"{P}/categories/{cat['id']}", headers=api.hr,
                        json={"default_useful_life_months": None})
    assert r.status_code == 200 and r.json()["default_useful_life_months"] is None
    d2 = (await api.get(f"{P}/{a['id']}", headers=api.hr)).json()
    assert (d2["effective_useful_life_months"], d2["life_source"]) == (36, "default")


async def test_legacy_routes(api, world):
    sfx = world["sfx"]
    L = f"/api/v1/hr/employees/{world['emp_id']}/assets"
    r = await api.post(L, headers=api.hr, json={
        "asset_type": f"  Gadget {sfx} ", "model": "G1", "serial_no": "S1"})
    assert r.status_code == 200, r.text
    alloc = r.json()
    assert alloc["status"] == "allocated"
    async with SessionLocal() as db:
        row = await db.get(EmployeeAsset, alloc["id"])
        assert row.asset_id
        asset = await db.get(Asset, row.asset_id)
        assert asset.status == "allocated"
        aid = asset.id
    r = await api.delete(f"/api/v1/hr/assets/{alloc['id']}", headers=api.hr)
    assert r.status_code == 409
    r = await api.patch(f"/api/v1/hr/assets/{alloc['id']}", headers=api.hr,
                        json={"status": "returned"})
    assert r.status_code == 200 and r.json()["status"] == "returned"
    r = await api.get(f"{P}/{aid}", headers=api.hr)
    assert r.json()["status"] == "in_stock"
    r = await api.patch(f"/api/v1/hr/assets/{alloc['id']}", headers=api.hr,
                        json={"status": "allocated"})
    assert r.status_code == 409
    r = await api.delete(f"/api/v1/hr/assets/{alloc['id']}", headers=api.hr)
    assert r.status_code == 200
    r = await api.get(f"{P}/{aid}", headers=api.hr)
    assert r.status_code == 200
    # second call reuses the category (case-insensitive)
    r = await api.post(L, headers=api.hr, json={
        "asset_type": f"GADGET {sfx}", "model": "G2", "asset_id": aid})
    assert r.status_code == 200
    async with SessionLocal() as db:
        n = (await db.execute(select(AssetCategory).where(
            AssetCategory.name.like(f"%Gadget {sfx}%")))).scalars().all()
        assert len(n) == 1


async def test_legacy_category_reuse_identifier_lost_and_null(api, world):
    sfx = world["sfx"]
    L = f"/api/v1/hr/employees/{world['emp_id']}/assets"
    r = await api.post(f"{P}/categories", headers=api.hr, json={
        "name": f"Widget {sfx}", "code": f"W{sfx[:4].upper()}"})
    cid = r.json()["id"]
    world.setdefault("cat_ids", []).append(cid)
    r = await api.post(L, headers=api.hr, json={
        "asset_type": f"WIDGET {sfx}", "model": "W1",
        "identifier": f"ast-{sfx}"})
    assert r.status_code == 200, r.text
    first = r.json()
    assert first["identifier"] == f"AST-{sfx.upper()}"
    async with SessionLocal() as db:
        row = await db.get(EmployeeAsset, first["id"])
        a = await db.get(Asset, row.asset_id)
        assert a.category_id == cid and a.asset_tag == f"AST-{sfx.upper()}"
    r = await api.post(L, headers=api.hr, json={
        "asset_type": f"Widget {sfx}", "model": "W2",
        "identifier": f"AST-{sfx}"})
    assert r.status_code == 409
    r = await api.post(L, headers=api.hr, json={
        "asset_type": f"Widget {sfx}", "model": "W3",
        "identifier": "bad id!"})
    assert r.status_code == 200
    async with SessionLocal() as db:
        row = await db.get(EmployeeAsset, r.json()["id"])
        a = await db.get(Asset, row.asset_id)
        assert a.notes == "Legacy identifier: bad id!"
        assert a.asset_tag.startswith("W")
    # legacy lost path + edit-only patch
    r = await api.patch(f"/api/v1/hr/assets/{first['id']}", headers=api.hr,
                        json={"condition": "scratched"})
    assert r.status_code == 200 and r.json()["condition"] == "scratched"
    r = await api.patch(f"/api/v1/hr/assets/{first['id']}", headers=api.hr,
                        json={"status": "lost"})
    assert r.status_code == 200 and r.json()["status"] == "lost"
    async with SessionLocal() as db:
        row = await db.get(EmployeeAsset, first["id"])
        assert (await db.get(Asset, row.asset_id)).status == "lost"
    # legacy NULL asset_id row keeps old behaviour
    async with SessionLocal() as db:
        old = EmployeeAsset(employee_id=world["emp_id"], asset_type="Old",
                            model="Old", status="allocated")
        db.add(old)
        await db.commit()
        oid = old.id
    r = await api.patch(f"/api/v1/hr/assets/{oid}", headers=api.hr,
                        json={"status": "returned"})
    assert r.status_code == 200 and r.json()["returned_date"]
    r = await api.delete(f"/api/v1/hr/assets/{oid}", headers=api.hr)
    assert r.status_code == 200


async def test_category_patch_duplicate_and_blank(api, world, cat):
    other = await api.post(f"{P}/categories", headers=api.hr, json={
        "name": f"Second {world['sfx']}", "code": f"S{world['sfx'][:4].upper()}"})
    world["cat_ids"].append(other.json()["id"])
    r = await api.patch(f"{P}/categories/{other.json()['id']}", headers=api.hr,
                        json={"name": f"cat {world['sfx']}"})
    assert r.status_code == 409
    r = await api.patch(f"{P}/categories/{other.json()['id']}", headers=api.hr,
                        json={"name": "   "})
    assert r.status_code == 422
    r = await api.post(f"{P}/categories", headers=api.hr,
                       json={"name": "  ", "code": "ABCD"})
    assert r.status_code == 422
    r = await api.post(P, headers=api.hr, json={
        "category_id": cat["id"], "name": "   "})
    assert r.status_code == 422


async def test_pagination_expiring_retired_and_bad_status(api, cat):
    soon = (date.today() + timedelta(days=5)).isoformat()
    ids = [(await mk(api, cat))["id"] for _ in range(3)]
    r = await api.get(P, headers=api.hr, params={
        "category_id": cat["id"], "limit": 2, "offset": 0})
    j = r.json()
    assert j["total"] == 3 and len(j["items"]) == 2
    r = await api.get(P, headers=api.hr, params={
        "category_id": cat["id"], "limit": 2, "offset": 2})
    assert len(r.json()["items"]) == 1
    keep = await mk(api, cat, warranty_expiry=soon)
    gone = await mk(api, cat, warranty_expiry=soon)
    r = await api.post(f"{P}/{gone['id']}/status", headers=api.hr,
                       json={"to_status": "retired"})
    assert r.status_code == 200
    r = await api.get(P, headers=api.hr, params={
        "category_id": cat["id"], "expiring_within_days": 30})
    assert [i["id"] for i in r.json()["items"]] == [keep["id"]]
    r = await api.get(P, headers=api.hr, params={"status": "bogus"})
    assert r.status_code == 422
    r = await api.post(f"{P}/{ids[0]}/status", headers=api.hr,
                       json={"to_status": "bogus"})
    assert r.status_code == 422
    r = await api.post(f"{P}/{ids[0]}/return", headers=api.hr,
                       json={"to_status": "lost"})
    assert r.status_code == 422
