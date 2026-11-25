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


# ---- review fixes ---------------------------------------------------------

async def _set_manager(uid, mgr):
    async with SessionLocal() as db:
        (await db.get(User, uid)).manager_id = mgr
        await db.commit()


async def test_named_subdomain_row_never_touches_manager_id(dop):
    u = dop["uid"]
    await _set_manager(u["emp"], u["mgr"])          # seeded, ungoverned
    async with SessionLocal() as db:
        await A.lock_reporting(db)
        await _mk(db, dop, mgr="mgr2", subdomains=["expense"])
        await db.commit()
    assert await _manager_of(u["emp"]) == u["mgr"]
    async with SessionLocal() as db:                # still alone after a sync
        await A.lock_reporting(db)
        await A.sync_mirror(db, [u["emp"]])
        await db.commit()
    assert await _manager_of(u["emp"]) == u["mgr"]


async def test_vacant_post_clears_governed_manager(dop):
    from app.models.dop import Post
    u = dop["uid"]
    async with SessionLocal() as db:
        db.add(Post(code=f"P{dop['sfx']}", title="T", is_active=True))
        await db.commit()
        pid = (await db.execute(select(Post.id).where(
            Post.code == f"P{dop['sfx']}"))).scalar_one()
    await _set_manager(u["emp"], u["mgr"])
    async with SessionLocal() as db:
        await A.lock_reporting(db)
        today = await local_today(db)
        await A.create(db, actor_id=u["admin"], kind_id=await _kind(db),
                       scope_type="user", scope_user_id=u["emp"],
                       manager_post_id=pid, starts_on=today)
        await db.commit()
    assert await _manager_of(u["emp"]) is None


async def test_end_rules(dop):
    u = dop["uid"]
    async with SessionLocal() as db:
        await A.lock_reporting(db)
        today = await local_today(db)
        started = await _mk(db, dop, starts_on=today - timedelta(days=3))
        sid = started.id
        await db.commit()
    async with SessionLocal() as db:
        await A.lock_reporting(db)
        today = await local_today(db)
        # started before today: cannot be cancelled by an early end
        with pytest.raises(HTTPException) as e:
            await A.end(db, actor_id=u["admin"], assignment_id=sid,
                        ends_on=today - timedelta(days=5))
        assert e.value.status_code == 422
        end = today - timedelta(days=1)
        await A.end(db, actor_id=u["admin"], assignment_id=sid, ends_on=end)
        await A.end(db, actor_id=u["admin"], assignment_id=sid, ends_on=end)
        await db.commit()
    async with SessionLocal() as db:
        n = len((await db.execute(select(AuditLog).where(
            AuditLog.action == "dop.assignment.end",
            AuditLog.resource_id == str(sid)))).scalars().all())
        assert n == 1                               # second call: no-op
    async with SessionLocal() as db:                # starting today: cancel
        await A.lock_reporting(db)
        today = await local_today(db)
        a = await _mk(db, dop, mgr="mgr2")
        await A.end(db, actor_id=u["admin"], assignment_id=a.id,
                    ends_on=today - timedelta(days=1))
        assert a.cancelled_at is not None
        await db.rollback()


async def test_resync_after_move_clears_when_nothing_applies_now(dop):
    u = dop["uid"]
    async with SessionLocal() as db:
        await A.lock_reporting(db)
        await _mk(db, dop, mgr="mgr", scope_type="department",
                  scope_department_id=dop["dept_id"])
        await db.commit()
    assert await _manager_of(u["act"]) == u["mgr"]
    async with SessionLocal() as db:
        await A.lock_reporting(db)
        had = await A.has_reporting_assignment(db, u["act"])
        assert had is True
        emp = (await db.execute(select(Employee).where(
            Employee.user_id == u["act"]))).scalar_one()
        emp.department = "Elsewhere"
        await db.flush()
        await A.resync_after_move(db, u["act"], had)
        await db.commit()
    assert await _manager_of(u["act"]) is None


async def test_department_loop_and_future_loop_refused(dop):
    u = dop["uid"]
    async with SessionLocal() as db:
        await A.lock_reporting(db)
        await A.set_reporting_manager(db, actor_id=u["admin"],
                                      user_id=u["emp"], manager_id=u["mgr"])
        await db.commit()
    async with SessionLocal() as db:                # mgr falls in the dept
        await A.lock_reporting(db)
        with pytest.raises(HTTPException) as e:
            await _mk(db, dop, mgr="emp", scope_type="department",
                      scope_department_id=dop["dept_id"])
        assert e.value.status_code == 422
        await db.rollback()
    async with SessionLocal() as db:                # loop starts next week
        await A.lock_reporting(db)
        today = await local_today(db)
        with pytest.raises(HTTPException) as e:
            await _mk(db, dop, mgr="emp", scope_user_id=u["mgr"],
                      starts_on=today + timedelta(days=7))
        assert e.value.status_code == 422
        await db.rollback()


async def test_set_reporting_manager_keeps_future_rows_and_noops(dop):
    u = dop["uid"]
    async with SessionLocal() as db:
        await A.lock_reporting(db)
        today = await local_today(db)
        await _mk(db, dop, mgr="mgr", ends_on=today + timedelta(days=30))
        fut = await _mk(db, dop, mgr="mgr2",
                        starts_on=today + timedelta(days=31))
        await db.commit()
        fid = fut.id
    async with SessionLocal() as db:                # same manager: no change
        await A.lock_reporting(db)
        await A.set_reporting_manager(db, actor_id=u["admin"],
                                      user_id=u["emp"], manager_id=u["mgr"])
        await db.commit()
        rows = (await db.execute(select(ManagerAssignment).where(
            ManagerAssignment.scope_user_id == u["emp"]))).scalars().all()
        assert len(rows) == 2
    async with SessionLocal() as db:
        await A.lock_reporting(db)
        today = await local_today(db)
        await A.set_reporting_manager(db, actor_id=u["admin"],
                                      user_id=u["emp"], manager_id=u["act"])
        await db.commit()
        rows = (await db.execute(select(ManagerAssignment).where(
            ManagerAssignment.scope_user_id == u["emp"],
            ManagerAssignment.cancelled_at.is_(None))
            .order_by(ManagerAssignment.id))).scalars().all()
        fut_row = next(r for r in rows if r.id == fid)
        assert fut_row.ends_on is None              # scheduled row untouched
        new = rows[-1]
        assert new.manager_user_id == u["act"]
        assert new.ends_on == fut_row.starts_on - timedelta(days=1)
    assert await _manager_of(u["emp"]) == u["act"]


# ---- concurrency: real sessions, fresh-transaction contract ---------------

async def _tx(fn):
    from app.api.v1.endpoints.roster_common import retry_on_lock
    async with SessionLocal() as db:
        async def body():
            await A.lock_reporting(db)
            return await fn(db)
        return await retry_on_lock(db, body, commit=True)


def _outcomes(results):
    from sqlalchemy.exc import OperationalError
    assert not [r for r in results if isinstance(r, OperationalError)]
    return [r.status_code if isinstance(r, HTTPException) else "ok"
            for r in results]


async def test_concurrent_creates_one_wins(dop):
    import asyncio
    u = dop["uid"]

    async def mk(mgr):
        async def f(db):
            return (await _mk(db, dop, mgr=mgr)).id
        return await _tx(f)
    res = await asyncio.gather(mk("mgr"), mk("mgr2"), return_exceptions=True)
    assert sorted(map(str, _outcomes(res))) == ["409", "ok"]
    assert await _manager_of(u["emp"]) in (u["mgr"], u["mgr2"])


async def test_concurrent_ends_and_end_vs_create(dop):
    import asyncio
    u = dop["uid"]
    async with SessionLocal() as db:
        await A.lock_reporting(db)
        today = await local_today(db)
        a = await _mk(db, dop, starts_on=today - timedelta(days=10))
        await db.commit()
        aid = a.id

    async def end(db):
        today = await local_today(db)
        await A.end(db, actor_id=u["admin"], assignment_id=aid,
                    ends_on=today - timedelta(days=1))

    res = await asyncio.gather(_tx(end), _tx(end), return_exceptions=True)
    assert _outcomes(res) == ["ok", "ok"]
    async with SessionLocal() as db:
        n = len((await db.execute(select(AuditLog).where(
            AuditLog.action == "dop.assignment.end",
            AuditLog.resource_id == str(aid)))).scalars().all())
        assert n == 1
    # end vs create on a fresh row
    async with SessionLocal() as db:
        await A.lock_reporting(db)
        today = await local_today(db)
        b = await _mk(db, dop, mgr="mgr", starts_on=today)
        await db.commit()
        bid = b.id

    async def end2(db):
        today = await local_today(db)
        await A.end(db, actor_id=u["admin"], assignment_id=bid,
                    ends_on=today - timedelta(days=1))

    async def mk(db):
        return (await _mk(db, dop, mgr="mgr2")).id
    res = await asyncio.gather(_tx(end2), _tx(mk), return_exceptions=True)
    out = _outcomes(res)
    assert out[0] == "ok" and out[1] in ("ok", 409)
    assert await _manager_of(u["emp"]) == (u["mgr2"] if out[1] == "ok"
                                           else None)


async def test_concurrent_set_reporting_manager(dop):
    import asyncio
    u = dop["uid"]

    async def setm(mgr):
        async def f(db):
            await A.set_reporting_manager(
                db, actor_id=u["admin"], user_id=u["emp"],
                manager_id=u[mgr])
        return await _tx(f)
    res = await asyncio.gather(setm("mgr"), setm("mgr2"),
                               return_exceptions=True)
    assert _outcomes(res) == ["ok", "ok"]
    async with SessionLocal() as db:
        today = await local_today(db)
        live = [r for r in (await db.execute(select(ManagerAssignment).where(
            ManagerAssignment.scope_user_id == u["emp"],
            ManagerAssignment.cancelled_at.is_(None)))).scalars().all()
            if r.ends_on is None or r.ends_on >= today]
        assert len(live) == 1
        assert await _manager_of(u["emp"]) == live[0].manager_user_id


async def test_department_create_beside_unrelated_user_update(dop):
    import asyncio
    u = dop["uid"]
    started = asyncio.Event()

    async def other():
        async with SessionLocal() as db:
            (await db.get(User, u["mgr"])).full_name = "Renamed " + dop["sfx"]
            await db.flush()
            started.set()
            await asyncio.sleep(0.8)
            await db.commit()

    async def dept(db):
        return (await _mk(db, dop, mgr="mgr2", scope_type="department",
                          scope_department_id=dop["dept_id"])).id

    async def mine():
        await started.wait()
        return await _tx(dept)
    res = await asyncio.gather(other(), mine(), return_exceptions=True)
    assert _outcomes(res) == ["ok", "ok"]
    assert await _manager_of(u["emp"]) == u["mgr2"]
    assert await _manager_of(u["mgr2"]) is None


async def _plant_loop(dop):
    """A loop mgr -> mgr2 -> mgr, as legacy data could hold it (inserted
    directly: the service refuses to create one)."""
    u = dop["uid"]
    today = None
    async with SessionLocal() as db:
        today = await local_today(db)
        kid = await _kind(db)
        for a, b in (("mgr", "mgr2"), ("mgr2", "mgr")):
            db.add(ManagerAssignment(
                manager_kind_id=kid, scope_type="user",
                scope_user_id=u[a], manager_user_id=u[b], subdomains=[],
                starts_on=today, created_by_id=u["admin"]))
        await db.commit()


async def test_preexisting_loop_does_not_block_unrelated_edits(dop):
    u = dop["uid"]
    await _plant_loop(dop)
    async with SessionLocal() as db:               # unrelated user edit
        await A.lock_reporting(db)
        await A.set_reporting_manager(db, actor_id=u["admin"],
                                      user_id=u["emp"], manager_id=u["act"])
        await db.commit()
    assert await _manager_of(u["emp"]) == u["act"]
    async with SessionLocal() as db:               # wide-scope create
        await A.lock_reporting(db)
        await _mk(db, dop, mgr="hr", scope_type="department",
                  scope_department_id=dop["dept_id"])
        await db.commit()
    # people with their own row keep it; the loop is untouched
    assert await _manager_of(u["emp"]) == u["act"]


async def test_loop_can_be_broken_but_not_extended(dop):
    u = dop["uid"]
    await _plant_loop(dop)
    async with SessionLocal() as db:               # a third user joins the loop
        await A.lock_reporting(db)
        with pytest.raises(HTTPException) as e:
            await A.set_reporting_manager(db, actor_id=u["admin"],
                                          user_id=u["emp"], manager_id=u["mgr"])
            await A.set_reporting_manager(db, actor_id=u["admin"],
                                          user_id=u["mgr"], manager_id=u["emp"])
        assert e.value.status_code == 422
        await db.rollback()
    async with SessionLocal() as db:               # breaking it works
        await A.lock_reporting(db)
        await A.set_reporting_manager(db, actor_id=u["admin"],
                                      user_id=u["mgr"], manager_id=u["hr"])
        await db.commit()
    assert await _manager_of(u["mgr"]) == u["hr"]


async def test_changed_user_staying_in_a_loop_is_refused(dop):
    u = dop["uid"]
    await _plant_loop(dop)
    async with SessionLocal() as db:               # mgr -> emp -> mgr2 -> mgr
        await A.lock_reporting(db)
        with pytest.raises(HTTPException) as e:
            await A.set_reporting_manager(db, actor_id=u["admin"],
                                          user_id=u["mgr2"], manager_id=u["emp"])
            await A.set_reporting_manager(db, actor_id=u["admin"],
                                          user_id=u["emp"], manager_id=u["mgr"])
        assert e.value.status_code == 422
        await db.rollback()


async def test_loop_baseline_api_for_holder_changes(dop):
    """Task 6 pattern: baseline, change anything, then compare."""
    u = dop["uid"]
    async with SessionLocal() as db:
        await A.lock_reporting(db)
        today = await local_today(db)
        await _mk(db, dop, mgr="mgr")
        base = await A.loop_baseline(db, [today])
        db.add(ManagerAssignment(           # a change made behind the service
            manager_kind_id=await _kind(db), scope_type="user",
            scope_user_id=u["mgr"], manager_user_id=u["emp"], subdomains=[],
            starts_on=today, created_by_id=u["admin"]))
        await db.flush()
        with pytest.raises(HTTPException) as e:
            await A.assert_no_new_loops(db, base)
        assert e.value.status_code == 422
        await db.rollback()
