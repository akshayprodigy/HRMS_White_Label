"""Deleting accounts/departments never silently cascades DOP data."""
from datetime import timedelta

import pytest
from _dop_world import dop  # noqa: F401
from sqlalchemy import delete, select
from test_dop_edit_routes import _client, _eid, api  # noqa: F401

from app.db.session import SessionLocal
from app.models.audit import AuditLog
from app.models.department import Department
from app.models.dop import (
    ActingAssignment, ManagerAssignment, Post, PostHolder,
)
from app.models.user import User
from app.services.dop import assignments as A
from app.services.org_time import local_today

HR = "/api/v1/hr"


async def _assign(dop, scope, mgr, **kw):
    u = dop["uid"]
    async with SessionLocal() as db:
        today = await local_today(db)
        kind = (await A.lock_reporting(db)).id
        starts = kw.pop("starts_on", today)
        a = await A.create(db, actor_id=u["admin"], kind_id=kind,
                           scope_type="user", scope_user_id=u[scope],
                           manager_user_id=u[mgr], starts_on=starts, **kw)
        await db.commit()
        return a.id


async def _exists(uid):
    async with SessionLocal() as db:
        return (await db.execute(select(User.id).where(
            User.id == uid))).first() is not None


async def _del(api, uid):
    return await api.delete(f"{HR}/employees/{await _eid(uid)}",
                            headers=api.h)


async def test_manager_blocks_delete(dop, api):
    u = dop["uid"]
    await _assign(dop, "emp", "mgr")
    r = await _del(api, u["mgr"])
    assert r.status_code == 409, r.text
    msg = str(r.json())
    assert "manager of 1 employee: Dop emp" in msg
    assert "0 employees" not in msg
    assert await _exists(u["mgr"])
    # preview shows the same
    r = await api.get(f"{HR}/employees/{await _eid(u['mgr'])}/delete-blockers",
                      headers=api.h)
    assert r.json()["deletable"] is False
    # admin endpoint too
    r = await api.delete(f"/api/v1/admin/users/{u['mgr']}", headers=api.h)
    assert r.status_code == 409 and "manager of 1 employee: Dop emp" in r.text
    assert await _exists(u["mgr"])


async def test_post_holder_and_acting_block_delete(dop, api):
    u = dop["uid"]
    async with SessionLocal() as db:
        today = await local_today(db)
        p = Post(code=f"P{dop['sfx']}", title=f"Boss{dop['sfx']}",
                 is_active=True)
        db.add(p)
        await db.flush()
        db.add(PostHolder(post_id=p.id, user_id=u["mgr2"], starts_on=today))
        db.add(ActingAssignment(covers_user_id=u["mgr"],
                                acting_user_id=u["act"], starts_on=today))
        await db.commit()
    r = await _del(api, u["mgr2"])
    assert r.status_code == 409 and f"holds post Boss{dop['sfx']}" in r.text
    r = await _del(api, u["act"])
    assert r.status_code == 409 and "acting for Dop mgr" in r.text
    r = await _del(api, u["mgr"])
    assert r.status_code == 409 and "covered by Dop act" in r.text
    for k in ("mgr", "mgr2", "act"):
        assert await _exists(u[k])


async def test_history_alone_and_own_scope_rows_do_not_block(dop, api):
    u = dop["uid"]
    async with SessionLocal() as db:
        today = await local_today(db)
    # ended history where mgr was the manager
    await _assign(dop, "emp", "mgr", starts_on=today - timedelta(days=10),
                  ends_on=today - timedelta(days=2))
    r = await _del(api, u["mgr"])
    assert r.status_code == 200, r.text
    assert not await _exists(u["mgr"])
    # emp is only the employee of a live row: delete proceeds and audits it
    aid = await _assign(dop, "emp", "mgr2")
    r = await _del(api, u["emp"])
    assert r.status_code == 200, r.text
    async with SessionLocal() as db:
        assert (await db.execute(select(ManagerAssignment.id).where(
            ManagerAssignment.id == aid))).first() is None
        log = (await db.execute(select(AuditLog).where(
            AuditLog.action == "dop.assignment.removed",
            AuditLog.resource_id == str(u["emp"])))).scalars().all()
    assert len(log) == 1
    assert [x["id"] for x in log[0].details["rows"]] == [aid]
    # admin endpoint, plain user without an employee record
    from test_dop_edit_routes import _new_user
    nid = await _new_user(dop, "plain")
    r = await api.delete(f"/api/v1/admin/users/{nid}", headers=api.h)
    assert r.status_code == 204, r.text


async def test_department_delete_guards(dop, api):
    u = dop["uid"]
    names = {"A": f"DOP{dop['sfx']}X", "B": f"DOP{dop['sfx']}Y"}
    ids = {}
    try:
        async with SessionLocal() as db:
            today = await local_today(db)
            for k, n in names.items():
                d = Department(name=n, is_active=True)
                db.add(d)
                await db.flush()
                ids[k] = d.id
            await db.commit()
            kind = (await A.lock_reporting(db)).id
            await A.create(db, actor_id=u["admin"], kind_id=kind,
                           scope_type="department",
                           scope_department_id=ids["A"],
                           manager_user_id=u["hr"], starts_on=today)
            db.add(Post(code=f"H{dop['sfx']}", title=f"Head{dop['sfx']}",
                        is_active=True, heads_department_id=ids["B"]))
            await db.commit()
        r = await api.delete(f"/api/v1/admin/departments/{ids['A']}",
                             headers=api.h)
        assert r.status_code == 409 and "manager assignment" in r.text
        r = await api.delete(f"/api/v1/admin/departments/{ids['B']}",
                             headers=api.h)
        assert r.status_code == 409 and f"Head{dop['sfx']}" in r.text
        async with SessionLocal() as db:               # end A's row: allowed
            await db.execute(delete(ManagerAssignment).where(
                ManagerAssignment.scope_department_id == ids["A"]))
            await db.commit()
        r = await api.delete(f"/api/v1/admin/departments/{ids['A']}",
                             headers=api.h)
        assert r.status_code == 204, r.text
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(ManagerAssignment).where(
                ManagerAssignment.scope_department_id.in_(ids.values())))
            await db.execute(delete(Post).where(
                Post.code == f"H{dop['sfx']}"))
            await db.execute(delete(Department).where(
                Department.id.in_(list(ids.values()))))
            await db.commit()


async def test_message_names_first_five_and_shared_scopes(dop, api):
    u = dop["uid"]
    async with SessionLocal() as db:
        today = await local_today(db)
        # inactive people are not counted, so make all six others active
        (await db.get(User, u["off"])).is_active = True
        await db.commit()
        kind = (await A.lock_reporting(db)).id
        await A.create(db, actor_id=u["admin"], kind_id=kind,
                       scope_type="department",
                       scope_department_id=dop["dept_id"],
                       manager_user_id=u["mgr"], starts_on=today)
        await db.commit()
    r = await _del(api, u["mgr"])
    assert r.status_code == 409, r.text
    # 7 colleagues in the department besides mgr itself... mgr is excluded
    assert "manager of 6 employees: " in r.text
    assert "and 1 more" in r.text
    assert f"department DOP{dop['sfx']}" in r.text


async def test_non_reporting_create_waits_for_delete_lock_order(dop, api):
    """A non-reporting create takes the reporting lock first, so it cannot
    interleave with an account delete (same order everywhere)."""
    u = dop["uid"]
    import asyncio
    async with SessionLocal() as db:
        kid = (await db.execute(select(A.ManagerKind.id).where(
            A.ManagerKind.code == "functional"))).scalar_one()
        today = await local_today(db)
    holder = SessionLocal()
    await A.lock_reporting(holder)              # a delete holds the lock
    done = []

    async def other():
        async with SessionLocal() as db2:
            await db2.commit()
            await A.create(db2, actor_id=u["admin"], kind_id=kid,
                           scope_type="user", scope_user_id=u["emp"],
                           manager_user_id=u["mgr"], starts_on=today)
            await db2.commit()
            done.append(1)
    t = asyncio.create_task(other())
    await asyncio.sleep(1.0)
    assert not done                             # blocked on the reporting lock
    await holder.commit()
    await holder.close()
    await asyncio.wait_for(t, 20)
    assert done


async def test_audit_lists_ended_history_with_totals(dop, api):
    u = dop["uid"]
    async with SessionLocal() as db:
        today = await local_today(db)
    await _assign(dop, "emp", "mgr", starts_on=today - timedelta(days=10),
                  ends_on=today - timedelta(days=2))
    r = await _del(api, u["mgr"])
    assert r.status_code == 200, r.text
    async with SessionLocal() as db:
        log = (await db.execute(select(AuditLog).where(
            AuditLog.action == "dop.assignment.removed",
            AuditLog.resource_id == str(u["mgr"])))).scalars().all()
    assert len(log) == 1
    h = log[0].details["history"]["as_manager"]
    assert h["total"] == 1 and len(h["rows"]) == 1


async def test_inactive_reports_do_not_block(dop, api):
    """Former employees keep old rows but must not pin their manager; the
    removed rows are still listed in the audit."""
    u = dop["uid"]
    aid = await _assign(dop, "emp", "mgr")
    async with SessionLocal() as db:
        (await db.get(User, u["emp"])).is_active = False
        await db.commit()
    r = await _del(api, u["mgr"])
    assert r.status_code == 200, r.text
    assert not await _exists(u["mgr"])
    async with SessionLocal() as db:
        row = (await db.execute(select(AuditLog).where(
            AuditLog.action == "dop.assignment.removed",
            AuditLog.resource_id == str(u["mgr"])))).scalars().one()
        assert [x["id"] for x in row.details["history"]["as_manager"]["rows"]
                ] == [aid]
        await db.delete(row)
        await db.commit()
