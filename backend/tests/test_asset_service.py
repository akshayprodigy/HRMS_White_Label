"""Asset state service (Roadmap v2 Phase 5, Task 3). DB-backed; cleans up."""
import random
import string
import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import delete, select

from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.models.asset import Asset, AssetCategory, AssetStatus
from app.models.audit import AuditLog
from app.models.employee import Employee, EmployeeStatus
from app.models.employee_asset import EmployeeAsset
from app.models.user import User
from app.services import assets as svc
from app.services.assets import AssetStateError


@pytest.fixture
async def env():
    sfx = uuid.uuid4().hex[:8]
    code = "T" + "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    ids = {"users": [], "emps": [], "assets": [], "cat": None, "code": code}
    try:
      async with SessionLocal() as db:
          users = [User(email=f"svc_{sfx}_{i}@test.com", full_name=f"Svc {i}",
                        hashed_password=get_password_hash("x"), is_active=True)
                   for i in range(3)]
          db.add_all(users)
          await db.commit()
          ids["users"] = [u.id for u in users]
          emps = [
              Employee(user_id=users[1].id, employee_id=f"SV{sfx}A", department="QA",
                       designation="T", date_of_joining=date(2020, 1, 1),
                       status=EmployeeStatus.ACTIVE),
              Employee(user_id=users[2].id, employee_id=f"SV{sfx}B", department="QA",
                       designation="T", date_of_joining=date(2020, 1, 1),
                       status=EmployeeStatus.INACTIVE),
          ]
          cat = AssetCategory(name=f"SvcCat {sfx}", code=code)
          db.add_all(emps + [cat])
          await db.commit()
          ids["emps"] = [e.id for e in emps]
          ids["cat"] = cat.id
          assets = [Asset(asset_tag=f"{code}-{i:06d}", category_id=cat.id,
                          name=f"Laptop {i}", serial_no=f"SN{sfx}{i}")
                    for i in range(1, 6)]
          db.add_all(assets)
          await db.commit()
          ids["assets"] = [a.id for a in assets]
      yield ids
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(AuditLog).where(
                AuditLog.resource_type == "asset",
                AuditLog.resource_id.in_([str(i) for i in ids["assets"]])))
            await db.execute(delete(EmployeeAsset).where(
                EmployeeAsset.employee_id.in_(ids["emps"])))
            await db.execute(delete(Asset).where(Asset.category_id == ids["cat"]))
            await db.execute(delete(AssetCategory).where(AssetCategory.id == ids["cat"]))
            await db.execute(delete(Employee).where(Employee.id.in_(ids["emps"])))
            await db.execute(delete(User).where(User.id.in_(ids["users"])))
            await db.commit()


async def _ctx(db, env, idx=0, emp=0):
    asset = await svc.get_asset_for_update(db, env["assets"][idx])
    employee = await db.get(Employee, env["emps"][emp])
    actor = await db.get(User, env["users"][0])
    return asset, employee, actor


async def _audit_actions(db, asset_id):
    rows = (await db.execute(select(AuditLog.action).where(
        AuditLog.resource_type == "asset",
        AuditLog.resource_id == str(asset_id)).order_by(AuditLog.id))).scalars().all()
    return list(rows)


async def test_allocate_and_audit(env):
    async with SessionLocal() as db:
        asset, emp, actor = await _ctx(db, env)
        alloc = await svc.allocate(db, asset=asset, employee=emp, actor=actor)
        await db.commit()
        assert asset.status == AssetStatus.ALLOCATED
        assert alloc.identifier == asset.asset_tag
        assert alloc.allocated_by_id == actor.id
        assert alloc.status == "allocated" and alloc.issued_date == date.today()
        open_ = await svc.open_allocation(db, asset.id)
        assert open_.id == alloc.id
        assert await _audit_actions(db, asset.id) == ["ASSET_ALLOCATE"]


async def test_allocate_guards(env):
    async with SessionLocal() as db:
        asset, emp, actor = await _ctx(db, env)
        await svc.allocate(db, asset=asset, employee=emp, actor=actor)
        with pytest.raises(AssetStateError):
            await svc.allocate(db, asset=asset, employee=emp, actor=actor)
        a2, emp2, _ = await _ctx(db, env, idx=1)
        a2.status = AssetStatus.IN_REPAIR
        with pytest.raises(AssetStateError):
            await svc.allocate(db, asset=a2, employee=emp, actor=actor)
        a3, inactive, _ = await _ctx(db, env, idx=2, emp=1)
        with pytest.raises(AssetStateError):
            await svc.allocate(db, asset=a3, employee=inactive, actor=actor)
        await db.rollback()


async def test_return_default_and_repair(env):
    async with SessionLocal() as db:
        asset, emp, actor = await _ctx(db, env)
        await svc.allocate(db, asset=asset, employee=emp, actor=actor)
        alloc = await svc.return_asset(db, asset=asset, actor=actor,
                                       condition="good")
        assert asset.status == AssetStatus.IN_STOCK
        assert alloc.status == "returned"
        assert alloc.returned_date == date.today()
        assert alloc.returned_condition == "good"
        assert alloc.returned_to_id == actor.id
        assert await svc.open_allocation(db, asset.id) is None

        await svc.allocate(db, asset=asset, employee=emp, actor=actor)
        await svc.return_asset(db, asset=asset, actor=actor,
                               to_status="in_repair")
        assert asset.status == AssetStatus.IN_REPAIR

        a2, _, _ = await _ctx(db, env, idx=1)
        await svc.allocate(db, asset=a2, employee=emp, actor=actor)
        with pytest.raises(AssetStateError):
            await svc.return_asset(db, asset=a2, actor=actor, to_status="lost")
        with pytest.raises(AssetStateError):
            await svc.return_asset(db, asset=a2, actor=actor,
                                   returned_date=date.today() - timedelta(days=5))
        await db.rollback()


async def test_return_without_allocation_errors(env):
    async with SessionLocal() as db:
        asset, _, actor = await _ctx(db, env)
        with pytest.raises(AssetStateError):
            await svc.return_asset(db, asset=asset, actor=actor)


async def test_mark_lost(env):
    async with SessionLocal() as db:
        asset, emp, actor = await _ctx(db, env)
        alloc = await svc.allocate(db, asset=asset, employee=emp, actor=actor)
        with pytest.raises(AssetStateError):
            await svc.mark_lost(db, asset=asset, actor=actor, remarks="  ")
        res = await svc.mark_lost(db, asset=asset, actor=actor, remarks="stolen")
        assert res.id == alloc.id and alloc.status == "lost"
        assert alloc.returned_date == date.today()
        assert asset.status == AssetStatus.LOST
        with pytest.raises(AssetStateError):
            await svc.mark_lost(db, asset=asset, actor=actor, remarks="again")

        a2, _, _ = await _ctx(db, env, idx=1)
        assert await svc.mark_lost(db, asset=a2, actor=actor, remarks="gone") is None
        assert a2.status == AssetStatus.LOST
        await db.rollback()


async def test_set_status_transitions(env):
    async with SessionLocal() as db:
        asset, emp, actor = await _ctx(db, env)
        await svc.set_status(db, asset=asset, actor=actor, to_status="in_repair")
        assert asset.status == AssetStatus.IN_REPAIR
        await svc.set_status(db, asset=asset, actor=actor, to_status="retired")
        await svc.set_status(db, asset=asset, actor=actor, to_status="in_stock")
        assert asset.status == AssetStatus.IN_STOCK
        with pytest.raises(AssetStateError):
            await svc.set_status(db, asset=asset, actor=actor, to_status="in_stock")
        with pytest.raises(AssetStateError):
            await svc.set_status(db, asset=asset, actor=actor, to_status="allocated")
        with pytest.raises(AssetStateError):
            await svc.set_status(db, asset=asset, actor=actor, to_status="lost")

        a2, _, _ = await _ctx(db, env, idx=1)
        await svc.mark_lost(db, asset=a2, actor=actor, remarks="x")
        await svc.set_status(db, asset=a2, actor=actor, to_status="in_stock")
        assert a2.status == AssetStatus.IN_STOCK

        a3, _, _ = await _ctx(db, env, idx=2)
        await svc.allocate(db, asset=a3, employee=emp, actor=actor)
        with pytest.raises(AssetStateError):
            await svc.set_status(db, asset=a3, actor=actor, to_status="in_repair")
        await db.rollback()


async def test_next_asset_tag(env):
    async with SessionLocal() as db:
        cat = await db.get(AssetCategory, env["cat"])
        # fixture created 1..5; add 7 and a non-numeric + other prefix
        db.add_all([
            Asset(asset_tag=f"{cat.code}-000007", category_id=cat.id, name="a"),
            Asset(asset_tag=f"{cat.code}-LEGACY", category_id=cat.id, name="b"),
            Asset(asset_tag=f"{cat.code}X-009999", category_id=cat.id, name="c"),
        ])
        await db.flush()
        assert await svc.next_asset_tag(db, cat) == f"{cat.code}-000008"
        await db.rollback()


async def test_open_allocations_for_employee_and_audit(env):
    async with SessionLocal() as db:
        a1, emp, actor = await _ctx(db, env)
        a2, _, _ = await _ctx(db, env, idx=1)
        await svc.allocate(db, asset=a1, employee=emp, actor=actor)
        await svc.allocate(db, asset=a2, employee=emp, actor=actor)
        await svc.return_asset(db, asset=a1, actor=actor)
        await db.commit()
        rows = await svc.open_allocations_for_employee(db, emp.id)
        assert [r.asset_id for r in rows] == [a2.id]
        assert await _audit_actions(db, a1.id) == ["ASSET_ALLOCATE", "ASSET_RETURN"]
        await svc.mark_lost(db, asset=a2, actor=actor, remarks="x")
        await svc.set_status(db, asset=(await _ctx(db, env, idx=2))[0],
                             actor=actor, to_status="retired")
        await db.commit()
        assert await _audit_actions(db, a2.id) == ["ASSET_ALLOCATE", "ASSET_LOST"]
        assert await _audit_actions(db, env["assets"][2]) == ["ASSET_STATUS"]


async def test_review_edge_cases(env):
    async with SessionLocal() as db:
        asset, emp, actor = await _ctx(db, env)
        with pytest.raises(AssetStateError):
            await svc.return_asset(db, asset=asset, actor=actor)
        with pytest.raises(AssetStateError):
            await svc.allocate(db, asset=asset, employee=emp, actor=actor,
                               issued_date=date.today() + timedelta(days=2))
        await svc.allocate(db, asset=asset, employee=emp, actor=actor)
        with pytest.raises(AssetStateError):
            await svc.return_asset(db, asset=asset, actor=actor,
                                   returned_date=date.today() + timedelta(days=2))
        # legacy open row without asset_id
        legacy = EmployeeAsset(employee_id=emp.id, asset_type="Old", model="m",
                               status="allocated")
        db.add(legacy)
        await db.flush()
        rows = await svc.open_allocations_for_employee(db, emp.id)
        assert legacy.id in [r.id for r in rows] and len(rows) == 2
        a2, _, _ = await _ctx(db, env, idx=1)
        await svc.set_status(db, asset=a2, actor=actor, to_status="retired")
        with pytest.raises(AssetStateError):
            await svc.mark_lost(db, asset=a2, actor=actor, remarks="x")
        await db.rollback()


async def test_next_asset_tag_edge(env):
    async with SessionLocal() as db:
        cat = await db.get(AssetCategory, env["cat"])
        c = cat.code
        db.add_all([
            Asset(asset_tag=f"{c}-9", category_id=cat.id, name="a"),
            Asset(asset_tag=f"{c}-000010", category_id=cat.id, name="b"),
        ])
        await db.flush()
        assert await svc.next_asset_tag(db, cat) == f"{c}-000011"
        db.add(Asset(asset_tag=f"{c.lower()}-000020", category_id=cat.id, name="c"))
        await db.flush()
        assert await svc.next_asset_tag(db, cat) == f"{c}-000021"
        await db.rollback()
