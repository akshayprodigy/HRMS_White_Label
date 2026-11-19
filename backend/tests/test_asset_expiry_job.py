"""Asset warranty/AMC expiry alert job + time rule (Roadmap v2 Phase 5, Task 8).

DB-backed on the dev DB with a fixed far-future `today` (2031) so dev assets
cannot match; full teardown."""
import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import delete, insert, select

from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.models.asset import Asset, AssetCategory, AssetStatus
from app.models.notification import Notification
from app.models.system import SystemSetting
from app.models.user import Permission, Role, User, role_permissions, user_roles
from app.services.assets import run_asset_expiry_alerts
from app.services.time_rules import get_time_rules, set_time_rules

TODAY = date(2031, 1, 10)
RULE = "assets.expiry_alert_days"


@pytest.fixture
async def world():
    sfx = uuid.uuid4().hex[:6]
    w: dict = {"code": f"X{sfx}", "assets": []}
    created_perm = False
    try:
        async with SessionLocal() as db:
            row = await db.get(SystemSetting, RULE)
            w["saved_rule"] = row.value if row else None
            perm = (await db.execute(select(Permission).where(
                Permission.name == "asset manage"))).scalars().first()
            if perm is None:
                perm = Permission(name="asset manage")
                db.add(perm)
                await db.flush()
                created_perm = True
            role = Role(name=f"aexp_{sfx}")
            user = User(email=f"aexp_{sfx}@test.com", full_name="Aexp Mgr",
                        hashed_password=get_password_hash("x"), is_active=True)
            cat = AssetCategory(name=f"aexp cat {sfx}", code=w["code"])
            db.add_all([role, user, cat])
            await db.flush()
            await db.execute(insert(role_permissions).values(
                role_id=role.id, permission_id=perm.id))
            await db.execute(insert(user_roles).values(
                user_id=user.id, role_id=role.id))
            await set_time_rules(db, {RULE: "30"})
            await db.commit()
            w.update(role_id=role.id, user_id=user.id, cat_id=cat.id,
                     perm_id=perm.id)
        yield w
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(Notification).where(
                Notification.event_type == "asset_expiry",
                Notification.message.like(f"%{w['code']}-%")))
            if w.get("user_id"):
                await db.execute(delete(Notification).where(
                    Notification.user_id == w["user_id"]))
            await db.execute(delete(Asset).where(
                Asset.category_id == w.get("cat_id", -1)))
            if w.get("cat_id"):
                await db.execute(delete(AssetCategory).where(
                    AssetCategory.id == w["cat_id"]))
            if w.get("user_id"):
                await db.execute(delete(user_roles).where(
                    user_roles.c.user_id == w["user_id"]))
                await db.execute(delete(User).where(User.id == w["user_id"]))
            if w.get("role_id"):
                await db.execute(delete(role_permissions).where(
                    role_permissions.c.role_id == w["role_id"]))
                await db.execute(delete(Role).where(Role.id == w["role_id"]))
            if created_perm and w.get("perm_id"):
                await db.execute(delete(Permission).where(
                    Permission.id == w["perm_id"]))
            row = await db.get(SystemSetting, RULE)
            if w.get("saved_rule") is None:
                if row:
                    await db.delete(row)
            elif row:
                row.value = w["saved_rule"]
            await db.commit()


async def mk(w, n, **kw) -> int:
    async with SessionLocal() as db:
        a = Asset(asset_tag=f"{w['code']}-{n:06d}", category_id=w["cat_id"],
                  name=f"asset {n}", **kw)
        db.add(a)
        await db.commit()
        return a.id


async def run(today=TODAY):
    async with SessionLocal() as db:
        out = await run_asset_expiry_alerts(db, today)
        await db.commit()
        return out


async def mine(w):
    async with SessionLocal() as db:
        return (await db.execute(select(Notification).where(
            Notification.user_id == w["user_id"],
            Notification.event_type == "asset_expiry"))).scalars().all()


async def get(aid):
    async with SessionLocal() as db:
        return await db.get(Asset, aid)


async def test_warranty_alert_dedupe_and_realert(world):
    w = world
    exp = TODAY + timedelta(days=10)
    aid = await mk(w, 1, warranty_expiry=exp)
    out = await run()
    assert out["assets"] >= 1 and out["recipients"] >= 1
    ns = await mine(w)
    assert len(ns) == 1
    assert f"{w['code']}-000001 warranty {exp.isoformat()}" in ns[0].message
    assert ns[0].resource_type == "asset"
    assert (await get(aid)).warranty_alert_for == exp

    await run()
    assert len(await mine(w)) == 1  # rerun: nothing new

    new_exp = TODAY + timedelta(days=20)
    async with SessionLocal() as db:
        a = await db.get(Asset, aid)
        a.warranty_expiry = new_exp
        await db.commit()
    await run()
    ns = await mine(w)
    assert len(ns) == 2
    assert (await get(aid)).warranty_alert_for == new_exp


async def test_amc_included(world):
    w = world
    exp = TODAY + timedelta(days=5)
    aid = await mk(w, 1, amc_expiry=exp)
    await run()
    ns = await mine(w)
    assert len(ns) == 1 and f"{w['code']}-000001 AMC {exp.isoformat()}" in ns[0].message
    a = await get(aid)
    assert a.amc_alert_for == exp and a.warranty_alert_for is None


async def test_mixed_sides_amc_dedupe(world):
    w = world
    aid = await mk(w, 1, warranty_expiry=TODAY + timedelta(days=5),
                   amc_expiry=TODAY + timedelta(days=60))
    await run()
    a = await get(aid)
    assert a.amc_alert_for is None and a.warranty_alert_for is not None
    assert len(await mine(w)) == 1

    amc = TODAY + timedelta(days=7)
    async with SessionLocal() as db:
        x = await db.get(Asset, aid)
        x.amc_expiry = amc
        await db.commit()
    await run()
    ns = await mine(w)
    assert len(ns) == 2
    new = [n for n in ns if "AMC" in n.message]
    assert len(new) == 1 and "warranty" not in new[0].message
    assert (await get(aid)).amc_alert_for == amc
    await run()
    assert len(await mine(w)) == 2


async def test_out_of_window_and_inactive_ignored(world):
    w = world
    ids = [
        await mk(w, 1, warranty_expiry=TODAY - timedelta(days=1)),
        await mk(w, 2, warranty_expiry=TODAY + timedelta(days=90)),
        await mk(w, 3, warranty_expiry=TODAY + timedelta(days=3),
                 status=AssetStatus.RETIRED),
        await mk(w, 4, amc_expiry=TODAY + timedelta(days=3),
                 status=AssetStatus.LOST),
    ]
    await run()
    assert await mine(w) == []
    for i in ids:
        a = await get(i)
        assert a.warranty_alert_for is None and a.amc_alert_for is None


async def test_more_than_five_truncated(world):
    w = world
    for n in range(1, 8):
        await mk(w, n, warranty_expiry=TODAY + timedelta(days=n))
    await run()
    ns = await mine(w)
    assert len(ns) == 1
    assert "7 asset(s) expiring soon" in ns[0].title
    assert ns[0].message.endswith("and 2 more expiries")
    assert ns[0].message.count("warranty") == 5


async def test_time_rule_validation(world):
    async with SessionLocal() as db:
        assert RULE in await get_time_rules(db)
        for bad in ("0", "400", "abc", "-1"):
            with pytest.raises(ValueError):
                await set_time_rules(db, {RULE: bad})
            await db.rollback()
        out = await set_time_rules(db, {RULE: "30"})
        assert out[RULE] == "30"
        await db.commit()
