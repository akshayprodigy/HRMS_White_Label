from datetime import timedelta

import pytest
from _dop_world import dop  # noqa: F401
from fastapi import HTTPException
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.audit import AuditLog
from app.models.dop import ManagerAssignment, ManagerKind
from app.models.employee import Employee
from app.models.user import User
from app.services.dop import assignments as A
from app.services.dop import resolver as R
from app.services.dop.world import load_world
from app.services.org_time import local_today


async def _kind(db, code="reporting"):
    return (await db.execute(select(ManagerKind.id).where(
        ManagerKind.code == code))).scalar_one()


async def _mk(db, dop, mgr="mgr", **kw):
    today = await local_today(db)
    kw.setdefault("starts_on", today)
    kw.setdefault("scope_type", "user")
    if kw["scope_type"] == "user":
        kw.setdefault("scope_user_id", dop["uid"]["emp"])
    return await A.create(db, actor_id=dop["uid"]["admin"],
                          kind_id=await _kind(db),
                          manager_user_id=dop["uid"][mgr], **kw)


async def _manager_of(uid):
    async with SessionLocal() as db:
        return (await db.execute(select(User.manager_id).where(
            User.id == uid))).scalar_one()


async def test_create_mirrors_and_audits(dop):
    async with SessionLocal() as db:
        a = await _mk(db, dop)
        await db.commit()
        aid = a.id
    assert await _manager_of(dop["uid"]["emp"]) == dop["uid"]["mgr"]
    async with SessionLocal() as db:
        assert (await db.execute(select(AuditLog).where(
            AuditLog.action == "dop.assignment.create",
            AuditLog.resource_id == str(aid)))).scalars().first()


async def test_overlap_refused_but_named_and_all_coexist(dop):
    async with SessionLocal() as db:
        await _mk(db, dop)
        await _mk(db, dop, mgr="mgr2", subdomains=["expense"])
        for subs in ([], ["expense", "leave"]):
            with pytest.raises(HTTPException) as e:
                await _mk(db, dop, mgr="act", subdomains=subs)
            assert e.value.status_code == 409
        await db.rollback()


@pytest.mark.parametrize("bad", [
    {"scope_type": "nope"}, {"subdomains": ["zzz"]},
    {"mgr": "emp"},                       # own manager
    {"mgr": "off"},                       # inactive
])
async def test_validation(dop, bad):
    async with SessionLocal() as db:
        with pytest.raises(HTTPException) as e:
            await _mk(db, dop, **bad)
        assert e.value.status_code == 422
        await db.rollback()


async def test_end_before_start_refused(dop):
    async with SessionLocal() as db:
        today = await local_today(db)
        with pytest.raises(HTTPException) as e:
            await _mk(db, dop, ends_on=today - timedelta(days=1))
        assert e.value.status_code == 422
        await db.rollback()


async def test_department_scope_mirrors_only_people_without_their_own(dop):
    u = dop["uid"]
    async with SessionLocal() as db:
        await _mk(db, dop, mgr="mgr2", scope_user_id=u["emp"])
        await _mk(db, dop, mgr="mgr", scope_type="department",
                  scope_department_id=dop["dept_id"])
        await db.commit()
    assert await _manager_of(u["emp"]) == u["mgr2"]
    assert await _manager_of(u["act"]) == u["mgr"]
    assert await _manager_of(u["mgr"]) is None        # never own manager


async def test_set_reporting_manager_replaces_and_clears(dop):
    u = dop["uid"]
    for mgr in ("mgr", "mgr2", "mgr2", None):
        async with SessionLocal() as db:
            await A.set_reporting_manager(
                db, actor_id=u["admin"], user_id=u["emp"],
                manager_id=u[mgr] if mgr else None)
            await db.commit()
        assert await _manager_of(u["emp"]) == (u[mgr] if mgr else None)
    async with SessionLocal() as db:
        today = await local_today(db)
        rows = (await db.execute(select(ManagerAssignment).where(
            ManagerAssignment.scope_user_id == u["emp"],
            ManagerAssignment.cancelled_at.is_(None)))).scalars().all()
        assert not [r for r in rows
                    if r.ends_on is None or r.ends_on >= today]


async def test_full_sync_leaves_ungoverned_managers_alone(dop):
    u = dop["uid"]
    async with SessionLocal() as db:
        (await db.get(User, u["emp"])).manager_id = u["mgr"]
        await db.commit()
        await A.sync_mirror(db, [u["emp"]])
        await db.commit()
    assert await _manager_of(u["emp"]) == u["mgr"]


async def test_future_assignment_does_not_clear_existing_manager(dop):
    u = dop["uid"]
    async with SessionLocal() as db:
        today = await local_today(db)
        (await db.get(User, u["emp"])).manager_id = u["mgr"]
        await db.commit()
        await _mk(db, dop, mgr="mgr2", starts_on=today + timedelta(days=5))
        await db.commit()
    assert await _manager_of(u["emp"]) == u["mgr"]


async def test_cycle_refused(dop):
    u = dop["uid"]
    async with SessionLocal() as db:
        await A.set_reporting_manager(db, actor_id=u["admin"],
                                      user_id=u["emp"], manager_id=u["mgr"])
        with pytest.raises(HTTPException) as e:
            await A.set_reporting_manager(
                db, actor_id=u["admin"], user_id=u["mgr"],
                manager_id=u["emp"])
        assert e.value.status_code == 422
        await db.rollback()


async def test_end_and_cancel_update_mirror_and_audit(dop):
    u = dop["uid"]
    async with SessionLocal() as db:
        today = await local_today(db)
        a = await _mk(db, dop, starts_on=today - timedelta(days=10))
        await db.commit()
        aid = a.id
    async with SessionLocal() as db:
        today = await local_today(db)
        await A.end(db, actor_id=u["admin"], assignment_id=aid,
                    ends_on=today - timedelta(days=1))
        await db.commit()
    assert await _manager_of(u["emp"]) is None        # ended: governed, cleared
    async with SessionLocal() as db:
        row = await db.get(ManagerAssignment, aid)
        assert row.cancelled_at is None and row.ends_on is not None
        with pytest.raises(HTTPException) as e:
            await A.end(db, actor_id=u["admin"], assignment_id=aid,
                        ends_on=row.ends_on + timedelta(days=3))
        assert e.value.status_code == 422
        with pytest.raises(HTTPException) as e:
            await A.end(db, actor_id=u["admin"], assignment_id=10**9,
                        ends_on=row.ends_on)
        assert e.value.status_code == 404
        await db.rollback()
        assert (await db.execute(select(AuditLog).where(
            AuditLog.action == "dop.assignment.end",
            AuditLog.resource_id == str(aid)))).scalars().first()


async def test_scope_matching_agrees_with_resolver(dop):
    """Location scope, normalised, with the employee-then-user fallback."""
    u = dop["uid"]
    async with SessionLocal() as db:
        # emp: employee location differs in case/spaces; act: only the user
        # has a location; mgr: a different place
        emp = (await db.execute(select(Employee).where(
            Employee.user_id == u["emp"]))).scalar_one()
        emp.location = f"  {dop['loc'].upper()}  "
        act = (await db.execute(select(Employee).where(
            Employee.user_id == u["act"]))).scalar_one()
        act.location = None
        (await db.get(User, u["act"])).location = f" {dop['loc'].lower()}"
        mgr = (await db.execute(select(Employee).where(
            Employee.user_id == u["mgr"]))).scalar_one()
        mgr.location = "Elsewhere"
        await db.commit()
    async with SessionLocal() as db:
        a = await _mk(db, dop, mgr="mgr2", scope_type="location",
                      scope_location=f" {dop['loc']} ")
        affected = set(await A.affected_users(db, a))
        today = await local_today(db)
        w = await load_world(db, today)
        resolved = {i for i in w.people
                    if R.find_assignment(w, "reporting", i, "", today)
                    and i in {x for x in u.values()}}
        assert affected & set(u.values()) == resolved
        assert {u["emp"], u["act"]} <= affected and u["mgr"] not in affected
        await db.commit()
    assert await _manager_of(u["emp"]) == u["mgr2"]
    assert await _manager_of(u["act"]) == u["mgr2"]
    assert await _manager_of(u["mgr"]) is None


async def test_post_manager_and_company_scope_matching(dop):
    from app.models.dop import Post
    u = dop["uid"]
    async with SessionLocal() as db:
        db.add(Post(code=f"P{dop['sfx']}", title="T", is_active=True))
        await db.commit()
        pid = (await db.execute(select(Post.id).where(
            Post.code == f"P{dop['sfx']}"))).scalar_one()
    async with SessionLocal() as db:
        today = await local_today(db)
        # vacant post: governs but yields no manager
        a = await A.create(db, actor_id=u["admin"], kind_id=await _kind(db),
                           scope_type="user", scope_user_id=u["emp"],
                           manager_post_id=pid, starts_on=today)
        assert (await db.get(User, u["emp"])).manager_id is None
        # company scope: read-only check that everyone matches (no mirror
        # is run for it here: it would touch real users)
        c = ManagerAssignment(scope_type="company", subdomains=[])
        everyone = set(await A.affected_users(db, c))
        assert set(u.values()) <= everyone
        await db.rollback()
