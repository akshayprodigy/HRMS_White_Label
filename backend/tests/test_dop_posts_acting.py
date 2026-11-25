import asyncio
import json
from datetime import timedelta

import pytest
from _dop_world import dop  # noqa: F401
from fastapi import HTTPException
from sqlalchemy import select

from app.api.v1.endpoints.roster_common import retry_on_lock
from app.db.session import SessionLocal
from app.models.audit import AuditLog
from app.models.dop import ManagerKind, PostHolder
from app.models.user import User
from app.services.dop import acting as AC
from app.services.dop import assignments as A
from app.services.dop import posts as PS
from app.services.org_time import local_today


async def _post(db, dop, code="P", **kw):
    return await PS.create(db, actor_id=dop["uid"]["admin"],
                           code=f"{code}{dop['sfx']}", title="HR Manager", **kw)


async def _raises(code, coro):
    with pytest.raises(HTTPException) as e:
        await coro
    assert e.value.status_code == code
    return e.value


async def _mgr_of(db, uid):
    return (await db.execute(select(User.manager_id).where(
        User.id == uid).execution_options(populate_existing=True))
    ).scalar_one()


async def _rep_kind(db):
    return (await db.execute(select(ManagerKind.id).where(
        ManagerKind.code == "reporting"))).scalar_one()


async def _to_post(db, dop, post_id, who="emp", **kw):
    t = await local_today(db)
    kw.setdefault("starts_on", t)
    return await A.create(
        db, actor_id=dop["uid"]["admin"], kind_id=await _rep_kind(db),
        scope_type="user", scope_user_id=dop["uid"][who],
        manager_post_id=post_id, **kw)


async def _hold(db, dop, post_id, who, starts_on, **kw):
    return await PS.assign_holder(
        db, actor_id=dop["uid"]["admin"], post_id=post_id,
        user_id=dop["uid"][who], starts_on=starts_on, **kw)


async def test_one_holder_at_a_time_and_handover(dop):
    u = dop["uid"]
    async with SessionLocal() as db:
        t = await local_today(db)
        p = await _post(db, dop)
        await PS.assign_holder(db, actor_id=u["admin"], post_id=p.id,
                               user_id=u["mgr"], starts_on=t)
        await PS.assign_holder(db, actor_id=u["admin"], post_id=p.id,
                               user_id=u["mgr2"],
                               starts_on=t + timedelta(days=5))
        hist = await PS.history(db, p.id)
        assert [(h.user_id, h.starts_on, h.ends_on) for h in hist] == [
            (u["mgr"], t, t + timedelta(days=4)),
            (u["mgr2"], t + timedelta(days=5), None)]
        await _raises(409, PS.assign_holder(
            db, actor_id=u["admin"], post_id=p.id, user_id=u["act"],
            starts_on=t + timedelta(days=2)))
        await db.rollback()


async def test_post_validation(dop):
    u = dop["uid"]
    async with SessionLocal() as db:
        t = await local_today(db)
        p = await _post(db, dop, heads_department_id=dop["dept_id"])
        await _raises(409, _post(db, dop))
        await _raises(409, _post(db, dop, code="Q",
                                 heads_department_id=dop["dept_id"]))
        await _raises(422, PS.assign_holder(
            db, actor_id=u["admin"], post_id=p.id, user_id=u["off"],
            starts_on=t))
        await _raises(422, PS.update(db, actor_id=u["admin"], post_id=p.id,
                                     changes={"parent_post_id": p.id}))
        await db.rollback()


async def test_text_validation_and_trim(dop):
    u = dop["uid"]
    async with SessionLocal() as db:
        s = dop["sfx"]
        for code, title in (("  ", "T"), ("C" + s, "   "), ("C" * 41, "T"),
                            ("C" + s, "T" * 121)):
            await _raises(422, PS.create(db, actor_id=u["admin"], code=code,
                                         title=title))
        p = await PS.create(db, actor_id=u["admin"], code=f"  C{s}  ",
                            title="  Head  ")
        assert (p.code, p.title) == (f"C{s}", "Head")
        await _raises(422, PS.update(db, actor_id=u["admin"], post_id=p.id,
                                     changes={"title": " "}))
        await _raises(422, PS.update(db, actor_id=u["admin"], post_id=p.id,
                                     changes={"code": "X" * 41}))
        await db.rollback()


async def test_unique_violation_at_flush_is_409(dop, monkeypatch):
    u = dop["uid"]

    async def skip(*a, **k):
        return None
    async with SessionLocal() as db:
        await _post(db, dop)
        monkeypatch.setattr(PS, "_validate", skip)
        await _raises(409, _post(db, dop))          # same code, no pre-check
        # the transaction is still usable
        assert (await db.execute(select(User.id).where(
            User.id == u["emp"]))).scalar_one() == u["emp"]
        await db.rollback()


async def test_update_audit_is_json(dop):
    u = dop["uid"]
    async with SessionLocal() as db:
        p = await _post(db, dop)
        await PS.update(db, actor_id=u["admin"], post_id=p.id,
                        changes={"title": "New", "location": "X",
                                 "department_id": dop["dept_id"]})
        await db.flush()
        rows = (await db.execute(select(AuditLog).where(
            AuditLog.resource_id == str(p.id),
            AuditLog.action.like("dop.post.%")))).scalars().all()
        assert len(rows) == 2
        for r in rows:
            json.dumps(r.details)
        await db.rollback()


async def test_deactivate_rules(dop):
    u = dop["uid"]
    async with SessionLocal() as db:
        t = await local_today(db)
        p = await _post(db, dop)
        a = await _to_post(db, dop, p.id)
        await _raises(409, PS.update(db, actor_id=u["admin"], post_id=p.id,
                                     changes={"is_active": False}))
        # a future assignment blocks too
        await A.end(db, actor_id=u["admin"], assignment_id=a.id,
                    ends_on=t - timedelta(days=1))
        await _to_post(db, dop, p.id, starts_on=t + timedelta(days=9))
        await _raises(409, PS.update(db, actor_id=u["admin"], post_id=p.id,
                                     changes={"is_active": False}))
        await db.rollback()
    async with SessionLocal() as db:
        t = await local_today(db)
        p = await _post(db, dop, code="Q")
        c = await AC.create(db, actor_id=u["admin"], covers_post_id=p.id,
                            acting_user_id=u["act"], starts_on=t)
        await _raises(409, PS.update(db, actor_id=u["admin"], post_id=p.id,
                                     changes={"is_active": False}))
        await AC.revoke(db, actor_id=u["admin"], cover_id=c.id)
        p = await PS.update(db, actor_id=u["admin"], post_id=p.id,
                            changes={"is_active": False})
        assert p.is_active is False
        await _raises(422, _hold(db, dop, p.id, "mgr", t))
        await _raises(422, AC.create(
            db, actor_id=u["admin"], covers_post_id=p.id,
            acting_user_id=u["act"], starts_on=t))
        p = await PS.update(db, actor_id=u["admin"], post_id=p.id,
                            changes={"is_active": True})
        assert p.is_active is True
        await db.rollback()


async def test_acting_rules(dop):
    u = dop["uid"]
    async with SessionLocal() as db:
        t = await local_today(db)

        async def mk(**kw):
            base = dict(actor_id=u["admin"], covers_user_id=u["mgr"],
                        acting_user_id=u["act"], starts_on=t,
                        ends_on=t + timedelta(days=3))
            base.update(kw)
            return await AC.create(db, **base)
        c = await mk()
        assert c.original_can_act is False
        await _raises(409, mk(acting_user_id=u["mgr2"]))
        await mk(acting_user_id=u["mgr2"], subdomains=["expense"])
        await _raises(422, mk(acting_user_id=u["mgr"]))
        await _raises(422, mk(acting_user_id=u["off"]))
        await _raises(422, mk(covers_user_id=None))
        await AC.update(db, actor_id=u["admin"], cover_id=c.id,
                        original_can_act=True, ends_on=t)
        assert c.original_can_act is True
        await AC.revoke(db, actor_id=u["admin"], cover_id=c.id)
        await _raises(409, AC.revoke(db, actor_id=u["admin"], cover_id=c.id))
        await mk(acting_user_id=u["hr"])          # free again
        await db.rollback()


async def test_acting_inactive_and_past(dop):
    u = dop["uid"]
    async with SessionLocal() as db:
        t = await local_today(db)
        await _raises(422, AC.create(      # covered user inactive
            db, actor_id=u["admin"], covers_user_id=u["off"],
            acting_user_id=u["act"], starts_on=t))
        await _raises(422, AC.create(      # already ended
            db, actor_id=u["admin"], covers_user_id=u["mgr"],
            acting_user_id=u["act"], starts_on=t - timedelta(days=5),
            ends_on=t - timedelta(days=1)))
        await _raises(422, AC.create(      # unknown covered user
            db, actor_id=u["admin"], covers_user_id=999999999,
            acting_user_id=u["act"], starts_on=t))
        await _raises(422, AC.create(      # both targets
            db, actor_id=u["admin"], covers_user_id=u["mgr"],
            covers_post_id=1, acting_user_id=u["act"], starts_on=t))
        await db.rollback()


async def test_vacant_post_clears_and_restores_mirror(dop):
    u = dop["uid"]
    async with SessionLocal() as db:
        t = await local_today(db)
        p = await _post(db, dop)
        h = await _hold(db, dop, p.id, "mgr", t - timedelta(days=3))
        await _to_post(db, dop, p.id, starts_on=t - timedelta(days=3))
        assert await _mgr_of(db, u["emp"]) == u["mgr"]
        # a manager nobody's assignment governs is never touched
        other = (await db.execute(select(User).where(
            User.id == u["hr"]))).scalar_one()
        other.manager_id = u["act"]
        await db.flush()
        await PS.end_holder(db, actor_id=u["admin"], post_id=p.id,
                            holder_id=h.id, ends_on=t - timedelta(days=1))
        assert await _mgr_of(db, u["emp"]) is None          # vacant
        assert await _mgr_of(db, u["hr"]) == u["act"]
        await _hold(db, dop, p.id, "mgr2", t)
        assert await _mgr_of(db, u["emp"]) == u["mgr2"]     # restored
        assert await _mgr_of(db, u["hr"]) == u["act"]
        await db.rollback()


async def test_future_handover_leaves_today(dop):
    u = dop["uid"]
    async with SessionLocal() as db:
        t = await local_today(db)
        p = await _post(db, dop)
        await _hold(db, dop, p.id, "mgr", t - timedelta(days=3))
        await _to_post(db, dop, p.id, starts_on=t - timedelta(days=3))
        assert await _mgr_of(db, u["emp"]) == u["mgr"]
        h2 = await _hold(db, dop, p.id, "mgr2", t + timedelta(days=3))
        hist = await PS.history(db, p.id)
        assert hist[0].ends_on == t + timedelta(days=2)
        assert await _mgr_of(db, u["emp"]) == u["mgr"]      # not yet
        # a scheduled holder can be removed; the old one stays ended
        await PS.remove_holder(db, actor_id=u["admin"], post_id=p.id,
                               holder_id=h2.id)
        assert len(await PS.history(db, p.id)) == 1
        assert await _mgr_of(db, u["emp"]) == u["mgr"]
        await db.rollback()


async def test_same_day_replace_and_remove(dop):
    u = dop["uid"]
    async with SessionLocal() as db:
        t = await local_today(db)
        p = await _post(db, dop)
        await _to_post(db, dop, p.id)
        h = await _hold(db, dop, p.id, "mgr", t)
        assert await _mgr_of(db, u["emp"]) == u["mgr"]
        e = await _raises(409, _hold(db, dop, p.id, "mgr2", t))
        assert "remove" in e.detail.lower()
        await PS.remove_holder(db, actor_id=u["admin"], post_id=p.id,
                               holder_id=h.id)
        assert await _mgr_of(db, u["emp"]) is None
        await _hold(db, dop, p.id, "mgr2", t)
        assert await _mgr_of(db, u["emp"]) == u["mgr2"]
        rows = (await db.execute(select(AuditLog).where(
            AuditLog.resource_id == str(p.id),
            AuditLog.action == "dop.post.holder_remove"))).scalars().all()
        assert len(rows) == 1 and rows[0].details["user_id"] == u["mgr"]
        await _raises(404, PS.remove_holder(
            db, actor_id=u["admin"], post_id=p.id, holder_id=h.id))
        await db.rollback()


async def test_remove_started_holder_refused(dop):
    u = dop["uid"]
    async with SessionLocal() as db:
        t = await local_today(db)
        p = await _post(db, dop)
        h = await _hold(db, dop, p.id, "mgr", t - timedelta(days=2))
        await _raises(422, PS.remove_holder(
            db, actor_id=u["admin"], post_id=p.id, holder_id=h.id))
        await db.rollback()


async def test_loop_through_holder_refused(dop):
    u = dop["uid"]
    async with SessionLocal() as db:
        t = await local_today(db)
        p = await _post(db, dop)
        await _to_post(db, dop, p.id)                       # emp -> post
        await A.create(db, actor_id=u["admin"], kind_id=await _rep_kind(db),
                       scope_type="user", scope_user_id=u["mgr"],
                       manager_user_id=u["emp"], starts_on=t)
        # mgr reports to emp, so mgr cannot hold emp's manager post
        await _raises(422, _hold(db, dop, p.id, "mgr", t))
        await db.rollback()
    async with SessionLocal() as db:        # nothing leaked
        assert (await db.execute(select(PostHolder.id).where(
            PostHolder.user_id == u["mgr"]))).first() is None


# ---- concurrency: real sessions, fresh-transaction contract ---------------

async def _tx(fn):
    async with SessionLocal() as db:
        async def body():
            return await fn(db)
        return await retry_on_lock(db, body, commit=True)


def _outcomes(results):
    return [r.status_code if isinstance(r, HTTPException) else
            ("ok" if not isinstance(r, BaseException) else repr(r))
            for r in results]


async def _committed_post(dop):
    async with SessionLocal() as db:
        t = await local_today(db)
        p = await _post(db, dop)
        await db.commit()
        return p.id, t


async def test_concurrent_two_holders_one_post(dop):
    u = dop["uid"]
    pid, t = await _committed_post(dop)

    def hold(who):
        async def f(db):
            return (await PS.assign_holder(
                db, actor_id=u["admin"], post_id=pid, user_id=u[who],
                starts_on=t)).id
        return _tx(f)
    res = await asyncio.gather(hold("mgr"), hold("mgr2"),
                               return_exceptions=True)
    assert sorted(map(str, _outcomes(res))) == ["409", "ok"]
    async with SessionLocal() as db:
        assert len(await PS.history(db, pid)) == 1


async def test_concurrent_two_covers_one_person(dop):
    u = dop["uid"]
    async with SessionLocal() as db:
        t = await local_today(db)

    def cover(who):
        async def f(db):
            return (await AC.create(
                db, actor_id=u["admin"], covers_user_id=u["mgr"],
                acting_user_id=u[who], starts_on=t,
                ends_on=t + timedelta(days=2))).id
        return _tx(f)
    res = await asyncio.gather(cover("act"), cover("hr"),
                               return_exceptions=True)
    assert sorted(map(str, _outcomes(res))) == ["409", "ok"]


async def test_concurrent_holder_change_vs_assignment_create(dop):
    u = dop["uid"]
    pid, t = await _committed_post(dop)

    async def hold(db):
        return (await PS.assign_holder(
            db, actor_id=u["admin"], post_id=pid, user_id=u["mgr"],
            starts_on=t)).id

    async def asg(db):
        await A.lock_reporting(db)        # the contract: lock first
        return (await _to_post(db, dop, pid)).id
    res = await asyncio.gather(_tx(hold), _tx(asg), return_exceptions=True)
    assert _outcomes(res) == ["ok", "ok"]
    async with SessionLocal() as db:
        assert await _mgr_of(db, u["emp"]) == u["mgr"]
