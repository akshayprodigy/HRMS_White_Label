"""Publish lifecycle + change history tests (Roadmap v2 Phase 1A, Task 5).
DB-backed; everything created is removed in fixture teardown."""
import asyncio
import uuid
from datetime import date, time, timedelta, datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.api import deps
from app.core.config import settings
from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.main import create_app
from app.models.audit import AuditLog
from app.models.department import Department
from app.models.employee import Employee, EmployeeStatus
from app.models.notification import Notification
from app.models.roster import (
    RosterChangeRequest, RosterEntry, RosterEntryHistory,
    RosterPublishRequest,
)
from app.models.schedule_delegation import DelegationScope, ScheduleDelegation
from app.models.shift import ShiftTemplate
from app.models.user import User

ROSTER = f"{settings.API_V1_STR}/roster"
PW = "test@12345"
TODAY = datetime.now(timezone.utc).date()
D = date(2030, 3, 4)


def dd(n):
    return (D + timedelta(days=n)).isoformat()


@pytest.fixture
async def client():
    app = create_app()
    app.dependency_overrides[deps.verify_attendance] = lambda: None
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as c:
        yield c


@pytest.fixture
async def world():
    sfx = uuid.uuid4().hex[:8]
    dept_x, dept_y = f"PX{sfx}", f"PY{sfx}"
    try:
        async with SessionLocal() as db:
            def mk(tag, **kw):
                return User(email=f"pb_{tag}_{sfx}@t.com", full_name=f"PB {tag}",
                            hashed_password=get_password_hash(PW),
                            is_active=True, **kw)
            deleg, e1, e2, e3, other = (mk("deleg"), mk("e1"), mk("e2"),
                                        mk("e3"), mk("other"))
            admin = mk("admin", is_superuser=True)
            db.add_all([deleg, e1, e2, e3, other, admin])
            db.add_all([Department(name=dept_x), Department(name=dept_y)])
            t1 = ShiftTemplate(name=f"PBT1{sfx}", start_time=time(9), end_time=time(17))
            t2 = ShiftTemplate(name=f"PBT2{sfx}", start_time=time(14), end_time=time(22))
            db.add_all([t1, t2])
            await db.commit()
            for tag, u, d in (("1", e1, dept_x), ("2", e2, dept_x), ("3", e3, dept_y)):
                db.add(Employee(
                    user_id=u.id, employee_id=f"PB{sfx}{tag}", department=d,
                    designation="Tester", date_of_joining=date(2020, 1, 1),
                    status=EmployeeStatus.ACTIVE))
            await db.commit()
            ids = {"deleg": deleg.id, "e1": e1.id, "e2": e2.id, "e3": e3.id,
                   "other": other.id, "admin": admin.id,
                   "t1": t1.id, "t2": t2.id}
        yield {"ids": ids, "sfx": sfx,
               "email": f"pb_deleg_{sfx}@t.com",
               "other_email": f"pb_other_{sfx}@t.com",
               "e1_email": f"pb_e1_{sfx}@t.com",
               "admin_email": f"pb_admin_{sfx}@t.com"}
    finally:
        async with SessionLocal() as db:
            uids = list((await db.execute(select(User.id).where(
                User.email.like(f"pb\\_%\\_{sfx}@t.com")))).scalars().all())
            prids = (await db.execute(select(RosterPublishRequest.id).where(
                RosterPublishRequest.requested_by_id.in_(uids)))).scalars().all()
            await db.execute(delete(AuditLog).where(
                AuditLog.user_id.in_(uids),
                AuditLog.action.like("roster.%")))
            await db.execute(delete(RosterEntryHistory).where(
                RosterEntryHistory.employee_id.in_(uids)))
            await db.execute(delete(RosterPublishRequest).where(
                RosterPublishRequest.id.in_(prids)))
            await db.execute(delete(RosterChangeRequest).where(
                RosterChangeRequest.employee_id.in_(uids)))
            await db.execute(delete(RosterEntry).where(
                RosterEntry.employee_id.in_(uids)))
            await db.execute(delete(Notification).where(
                Notification.user_id.in_(uids)))
            await db.execute(delete(ScheduleDelegation).where(
                ScheduleDelegation.grantee_id.in_(uids)))
            await db.execute(delete(Employee).where(Employee.user_id.in_(uids)))
            await db.execute(delete(Department).where(
                Department.name.in_([dept_x, dept_y])))
            await db.execute(delete(ShiftTemplate).where(
                ShiftTemplate.name.like(f"PBT_{sfx}")))
            await db.execute(delete(User).where(User.id.in_(uids)))
            await db.commit()


async def _login(client, email):
    r = await client.post(f"{settings.API_V1_STR}/auth/login",
                          data={"username": email, "password": PW})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _grant(w, *, can_publish, emps=("e1", "e2")):
    async with SessionLocal() as db:
        db.add(ScheduleDelegation(
            grantee_id=w["ids"]["deleg"], scope_type=DelegationScope.EMPLOYEES,
            employee_ids=[w["ids"][e] for e in emps], can_publish=can_publish,
            valid_from=TODAY - timedelta(days=1)))
        await db.commit()


async def _put(client, h, w, emp, n, tpl="t1", status="published", **kw):
    body = {"employee_id": w["ids"][emp], "work_date": dd(n),
            "shift_template_id": w["ids"][tpl], "status": status}
    body.update(kw)
    r = await client.post(f"{ROSTER}/entries", headers=h, json=body)
    assert r.status_code == 200, r.text
    return r.json()


async def _hist(uid):
    async with SessionLocal() as db:
        return list((await db.execute(select(RosterEntryHistory).where(
            RosterEntryHistory.employee_id == uid
        ).order_by(RosterEntryHistory.id))).scalars().all())


async def _notes(uid):
    async with SessionLocal() as db:
        return list((await db.execute(select(Notification).where(
            Notification.user_id == uid))).scalars().all())


async def _statuses(uid):
    async with SessionLocal() as db:
        return {r.work_date: r.status for r in (await db.execute(
            select(RosterEntry).where(RosterEntry.employee_id == uid))
        ).scalars().all()}


async def test_patch_published_needs_reason(client, world):
    ha = await _login(client, world["admin_email"])
    e1, t2 = world["ids"]["e1"], world["ids"]["t2"]
    pub = await _put(client, ha, world, "e1", 0)
    drf = await _put(client, ha, world, "e1", 1, status="draft")
    r = await client.patch(f"{ROSTER}/entries/{pub['id']}", headers=ha,
                           json={"shift_template_id": t2})
    assert r.status_code == 422 and "reason required" in r.text
    r = await client.patch(f"{ROSTER}/entries/{pub['id']}", headers=ha,
                           json={"shift_template_id": t2, "reason": " x "})
    assert r.status_code == 422
    r = await client.patch(f"{ROSTER}/entries/{pub['id']}", headers=ha,
                           json={"shift_template_id": t2, "reason": "cover swap"})
    assert r.status_code == 200, r.text
    h = await _hist(e1)
    assert len(h) == 1 and h[0].action == "update" and h[0].reason == "cover swap"
    assert h[0].old_shift_template_id == world["ids"]["t1"]
    assert h[0].new_shift_template_id == t2
    assert len(await _notes(e1)) == 1
    # note-only change on published: reason required but no history row
    r = await client.patch(f"{ROSTER}/entries/{pub['id']}", headers=ha,
                           json={"note": "n", "reason": "just a note"})
    assert r.status_code == 200 and len(await _hist(e1)) == 1
    # draft edit: no reason, no history
    r = await client.patch(f"{ROSTER}/entries/{drf['id']}", headers=ha,
                           json={"shift_template_id": t2})
    assert r.status_code == 200 and len(await _hist(e1)) == 1
    # published -> draft counts as an update
    r = await client.patch(f"{ROSTER}/entries/{pub['id']}", headers=ha,
                           json={"status": "draft", "reason": "pull back"})
    assert r.status_code == 200 and len(await _hist(e1)) == 2


async def test_delete_published_needs_reason(client, world):
    ha = await _login(client, world["admin_email"])
    e1 = world["ids"]["e1"]
    pub = await _put(client, ha, world, "e1", 0)
    drf = await _put(client, ha, world, "e1", 1, status="draft")
    r = await client.delete(f"{ROSTER}/entries/{pub['id']}", headers=ha)
    assert r.status_code == 422 and "reason required" in r.text
    r = await client.delete(f"{ROSTER}/entries/{pub['id']}", headers=ha,
                            params={"reason": "no longer needed"})
    assert r.status_code == 200
    h = await _hist(e1)
    assert len(h) == 1 and h[0].action == "delete" and h[0].new_shift_template_id is None
    assert h[0].roster_entry_id is None
    r = await client.delete(f"{ROSTER}/entries/{drf['id']}", headers=ha)
    assert r.status_code == 200 and len(await _hist(e1)) == 1


async def test_post_overwrite_published(client, world):
    ha = await _login(client, world["admin_email"])
    e1, t2 = world["ids"]["e1"], world["ids"]["t2"]
    await _put(client, ha, world, "e1", 0)
    r = await client.post(f"{ROSTER}/entries", headers=ha, json={
        "employee_id": e1, "work_date": dd(0), "shift_template_id": t2})
    assert r.status_code == 422 and "reason required" in r.text
    await _put(client, ha, world, "e1", 0, tpl="t2", reason="swap shifts")
    assert len(await _hist(e1)) == 1


async def test_bulk_overwrite_history(client, world):
    ha = await _login(client, world["admin_email"])
    e1, t1, t2 = world["ids"]["e1"], world["ids"]["t1"], world["ids"]["t2"]
    await _put(client, ha, world, "e1", 0, tpl="t1")
    await _put(client, ha, world, "e1", 1, tpl="t1")
    r = await client.post(f"{ROSTER}/bulk", headers=ha, json={
        "overwrite": True, "status": "published",
        "start": dd(0), "end": dd(2), "entries": [
            {"employee_id": e1, "work_date": dd(0), "shift_template_id": t2},
            {"employee_id": e1, "work_date": dd(1), "shift_template_id": t1},
            {"employee_id": e1, "work_date": dd(2), "shift_template_id": t1},
        ]})
    assert r.status_code == 200, r.text
    h = await _hist(e1)
    assert len(h) == 1 and h[0].work_date == D and h[0].reason == "bulk re-plan"
    notes = await _notes(e1)
    assert len(notes) == 1  # once per request, not per cell


async def test_publish_flips_only_permitted(client, world):
    ha = await _login(client, world["admin_email"])
    hd = await _login(client, world["email"])
    await _grant(world, can_publish=False)
    e1, e2 = world["ids"]["e1"], world["ids"]["e2"]
    for e in ("e1", "e2"):
        await _put(client, ha, world, e, 0, status="draft")
        await _put(client, ha, world, e, 1, status="draft")
    body = {"start": dd(0), "end": dd(6)}
    r = await client.post(f"{ROSTER}/publish", headers=hd, json=body)
    assert r.status_code == 200, r.text
    assert r.json() == {"published": 0, "employees": 0,
                        "not_permitted": sorted([e1, e2])}
    assert set((await _statuses(e1)).values()) == {"draft"}
    r = await client.post(f"{ROSTER}/publish", headers=ha,
                          json={**body, "employee_ids": [e1]})
    assert r.json() == {"published": 2, "employees": 1, "not_permitted": []}
    assert set((await _statuses(e1)).values()) == {"published"}
    assert set((await _statuses(e2)).values()) == {"draft"}
    h = await _hist(e1)
    assert [x.action for x in h] == ["publish", "publish"]
    assert len(await _notes(e1)) == 1
    assert "published" in (await _notes(e1))[0].message
    # nothing left -> zero, audit skipped for 0
    r = await client.post(f"{ROSTER}/publish", headers=ha,
                          json={**body, "employee_ids": [e1]})
    assert r.json()["published"] == 0
    r = await client.post(f"{ROSTER}/publish", headers=ha, json={
        "start": dd(5), "end": dd(0)})
    assert r.status_code == 400
    r = await client.post(f"{ROSTER}/publish", headers=ha, json={
        "start": dd(0), "end": dd(80)})
    assert r.status_code == 400


async def test_publish_request_flow(client, world):
    ha = await _login(client, world["admin_email"])
    hd = await _login(client, world["email"])
    ho = await _login(client, world["other_email"])
    await _grant(world, can_publish=False)
    e1 = world["ids"]["e1"]
    await _put(client, ha, world, "e1", 0, status="draft")
    body = {"start": dd(0), "end": dd(6), "note": "pls"}
    # no scope -> 422
    assert (await client.post(f"{ROSTER}/publish-requests", headers=ho,
                              json=body)).status_code == 422
    r = await client.post(f"{ROSTER}/publish-requests", headers=hd, json=body)
    assert r.status_code == 200, r.text
    pr = r.json()
    assert pr["status"] == "pending" and pr["requester_name"] == "PB deleg"
    assert set(pr["employee_ids"]) == {e1, world["ids"]["e2"]}
    assert (await client.post(f"{ROSTER}/publish-requests", headers=hd,
                              json=body)).status_code == 409
    r = await client.get(f"{ROSTER}/publish-requests", headers=hd)
    assert [x["id"] for x in r.json()] == [pr["id"]]
    assert r.json()[0]["draft_count"] == 1
    r = await client.get(f"{ROSTER}/publish-requests", headers=ha)
    assert pr["id"] in [x["id"] for x in r.json()]
    assert (await client.get(f"{ROSTER}/publish-requests", headers=ho)).json() == []
    # admin got notified
    assert any("publish" in n.message
               for n in await _notes(world["ids"]["admin"]))
    # non-admin decide 403
    assert (await client.post(f"{ROSTER}/publish-requests/{pr['id']}/decide",
                              headers=hd, json={"approve": True})).status_code == 403
    # reject needs note
    assert (await client.post(f"{ROSTER}/publish-requests/{pr['id']}/decide",
                              headers=ha, json={"approve": False})).status_code == 422
    r = await client.post(f"{ROSTER}/publish-requests/{pr['id']}/decide",
                          headers=ha, json={"approve": True})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved"
    assert r.json()["publish_result"]["published"] == 1
    assert set((await _statuses(e1)).values()) == {"published"}
    notes = await _notes(world["ids"]["deleg"])
    assert any("approved" in n.title for n in notes)
    assert (await client.post(f"{ROSTER}/publish-requests/{pr['id']}/decide",
                              headers=ha, json={"approve": True})).status_code == 409
    # second request: reject, and cancel paths
    body2 = {"start": dd(10), "end": dd(12)}
    pr2 = (await client.post(f"{ROSTER}/publish-requests", headers=hd,
                             json=body2)).json()
    assert (await client.post(f"{ROSTER}/publish-requests/{pr2['id']}/cancel",
                              headers=ha)).status_code == 403
    r = await client.post(f"{ROSTER}/publish-requests/{pr2['id']}/cancel",
                          headers=hd)
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert (await client.post(f"{ROSTER}/publish-requests/{pr2['id']}/cancel",
                              headers=hd)).status_code == 409
    pr3 = (await client.post(f"{ROSTER}/publish-requests", headers=hd,
                             json=body2)).json()
    r = await client.post(f"{ROSTER}/publish-requests/{pr3['id']}/decide",
                          headers=ha, json={"approve": False, "note": "later"})
    assert r.json()["status"] == "rejected"
    assert any("rejected" in n.title
               for n in await _notes(world["ids"]["deleg"]))


async def test_copy_week(client, world):
    ha = await _login(client, world["admin_email"])
    e1, t1 = world["ids"]["e1"], world["ids"]["t1"]
    await _put(client, ha, world, "e1", 0, status="published")
    await _put(client, ha, world, "e1", 1, status="draft", tpl="t2")
    await _put(client, ha, world, "e1", 2, status="draft")
    # existing published target cell (day 7+2 = 9) must survive
    await _put(client, ha, world, "e1", 9, status="published", tpl="t2")
    body = {"source_start": dd(0), "source_end": dd(6), "target_start": dd(7),
            "employee_ids": [e1], "overwrite": True}
    r = await client.post(f"{ROSTER}/copy", headers=ha, json=body)
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 2 and r.json()["skipped"] == 1
    async with SessionLocal() as db:
        rows = {x.work_date: x for x in (await db.execute(select(RosterEntry).where(
            RosterEntry.employee_id == e1))).scalars().all()}
    assert rows[D + timedelta(days=7)].status == "draft"
    assert rows[D + timedelta(days=7)].shift_template_id == t1
    assert rows[D + timedelta(days=8)].shift_template_id == world["ids"]["t2"]
    assert rows[D + timedelta(days=9)].status == "published"
    assert len(await _hist(e1)) == 0
    # overlap
    r = await client.post(f"{ROSTER}/copy", headers=ha, json={
        **body, "target_start": dd(3)})
    assert r.status_code == 422
    r = await client.post(f"{ROSTER}/copy", headers=ha, json={
        **body, "source_end": dd(40), "target_start": dd(60)})
    assert r.status_code == 400


async def test_history_scoping_and_my(client, world):
    ha = await _login(client, world["admin_email"])
    hd = await _login(client, world["email"])
    he = await _login(client, world["e1_email"])
    ho = await _login(client, world["other_email"])
    await _grant(world, can_publish=True)
    e1, e3, t2 = world["ids"]["e1"], world["ids"]["e3"], world["ids"]["t2"]
    pub = await _put(client, ha, world, "e1", 0)
    await _put(client, ha, world, "e1", 1, status="draft")
    r = await client.patch(f"{ROSTER}/entries/{pub['id']}", headers=hd,
                           json={"shift_template_id": t2, "reason": "swap"})
    assert r.status_code == 200, r.text
    # default window = last 30 days of CHANGES (work date is in 2030)
    r = await client.get(f"{ROSTER}/history", headers=hd,
                         params={"employee_id": e1})
    assert r.status_code == 200 and len(r.json()) == 1
    row = r.json()[0]
    assert row["employee_name"] == "PB e1" and row["changed_by_name"] == "PB deleg"
    assert row["old_shift_name"].startswith("PBT1") and row["new_shift_name"].startswith("PBT2")
    # work-date filters narrow
    r = await client.get(f"{ROSTER}/history", headers=hd, params={
        "employee_id": e1, "work_start": dd(1), "work_end": dd(3)})
    assert r.json() == []
    r = await client.get(f"{ROSTER}/history", headers=hd, params={
        "employee_id": e1, "work_start": dd(0), "work_end": dd(0)})
    assert len(r.json()) == 1
    # change-time window that excludes now
    old = (TODAY - timedelta(days=10)).isoformat()
    r = await client.get(f"{ROSTER}/history", headers=hd, params={
        "employee_id": e1, "start": old, "end": old})
    assert r.json() == []
    assert (await client.get(f"{ROSTER}/history", headers=hd,
                             params={"employee_id": e3})).status_code == 403
    assert (await client.get(f"{ROSTER}/history", headers=hd, params={
        "employee_id": e1,
        "start": (TODAY - timedelta(days=100)).isoformat()})).status_code == 400
    # non-admin without any scope and no employee_id -> 403
    assert (await client.get(f"{ROSTER}/history", headers=ho)).status_code == 403
    r = await client.get(f"{ROSTER}/my/history", headers=he)
    assert r.status_code == 200 and [x["id"] for x in r.json()] == [row["id"]]
    # drafts stay hidden from /my
    r = await client.get(f"{ROSTER}/my", headers=he,
                         params={"start": dd(0), "end": dd(3)})
    assert [x["work_date"] for x in r.json()] == [dd(0)]


async def test_reason_only_when_history_written(client, world):
    ha = await _login(client, world["admin_email"])
    e1 = world["ids"]["e1"]
    pub = await _put(client, ha, world, "e1", 0)
    # note-only patch and idempotent re-save succeed without a reason
    r = await client.patch(f"{ROSTER}/entries/{pub['id']}", headers=ha,
                           json={"note": "n"})
    assert r.status_code == 200, r.text
    await _put(client, ha, world, "e1", 0)  # identical re-save
    assert await _hist(e1) == []
    # whitespace-only reason is rejected when a change would be recorded
    r = await client.patch(f"{ROSTER}/entries/{pub['id']}", headers=ha,
                           json={"is_week_off": True, "reason": "     "})
    assert r.status_code == 422 and "at least 3" in r.text
    r = await client.delete(f"{ROSTER}/entries/{pub['id']}", headers=ha,
                            params={"reason": "   "})
    assert r.status_code == 422


async def test_publish_idempotent_and_concurrent(client, world):
    ha = await _login(client, world["admin_email"])
    e1, e2 = world["ids"]["e1"], world["ids"]["e2"]
    for e in ("e1", "e2"):
        for n in (0, 1, 2):
            await _put(client, ha, world, e, n, status="draft")
    body = {"start": dd(0), "end": dd(6), "employee_ids": [e1, e2]}
    r1, r2 = await asyncio.gather(
        client.post(f"{ROSTER}/publish", headers=ha, json=body),
        client.post(f"{ROSTER}/publish", headers=ha, json=body),
    )
    # the loser either sees nothing left (0) or gets a 409 retry signal
    codes = sorted([r1.status_code, r2.status_code])
    assert codes[0] == 200 and codes[1] in (200, 409), (r1.text, r2.text)
    done = [r.json()["published"] for r in (r1, r2) if r.status_code == 200]
    assert sorted(done) in ([6], [0, 6])
    r3 = await client.post(f"{ROSTER}/publish", headers=ha, json=body)
    assert r3.json()["published"] == 0
    for uid in (e1, e2):
        assert len([h for h in await _hist(uid) if h.action == "publish"]) == 3
        assert len(await _notes(uid)) == 1


async def test_decide_noop_message(client, world):
    ha = await _login(client, world["admin_email"])
    hd = await _login(client, world["email"])
    await _grant(world, can_publish=False)
    await _put(client, ha, world, "e1", 0, status="draft")
    body = {"start": dd(0), "end": dd(6)}
    pr = (await client.post(f"{ROSTER}/publish-requests", headers=hd,
                            json=body)).json()
    await client.post(f"{ROSTER}/publish", headers=ha, json=body)
    r = await client.post(f"{ROSTER}/publish-requests/{pr['id']}/decide",
                          headers=ha, json={"approve": True})
    assert r.status_code == 200
    assert r.json()["publish_result"]["published"] == 0
    assert "already published" in r.json()["message"]


def test_format_dates_many_runs():
    from app.services.roster import format_dates
    ds = [D + timedelta(days=i) for i in (0, 1, 2, 4, 5, 7, 9, 10, 11, 13, 15, 17, 19)]
    out = format_dates(ds)
    assert out.endswith("+3 more")
    assert f"{dd(0)} to {dd(2)}" in out and f"{dd(4)} to {dd(5)}" in out
    assert format_dates([D]) == dd(0)


async def test_grid_can_publish_flag(client, world):
    ha = await _login(client, world["admin_email"])
    hd = await _login(client, world["email"])
    await _grant(world, can_publish=False)
    q = {"start": dd(0), "end": dd(6)}
    r = await client.get(f"{ROSTER}/plan", headers=ha, params=q)
    assert r.status_code == 200 and r.json()["can_publish"] is True
    r = await client.get(f"{ROSTER}/plan", headers=hd, params=q)
    assert r.status_code == 200 and r.json()["can_publish"] is False


async def test_concurrent_publish_request_decide(client, world):
    ha = await _login(client, world["admin_email"])
    hd = await _login(client, world["email"])
    await _grant(world, can_publish=False)
    await _put(client, ha, world, "e1", 0, status="draft")
    for _ in range(3):
        pr = (await client.post(f"{ROSTER}/publish-requests", headers=hd,
                                json={"start": dd(0), "end": dd(6)})).json()
        url = f"{ROSTER}/publish-requests/{pr['id']}/decide"
        r1, r2 = await asyncio.gather(
            client.post(url, headers=ha, json={"approve": True}),
            client.post(url, headers=ha, json={"approve": True}),
        )
        assert sorted([r1.status_code, r2.status_code]) == [200, 409], (
            r1.text, r2.text)
        # reset for next loop: back to draft + fresh request
        async with SessionLocal() as db:
            await db.execute(RosterEntry.__table__.update().where(
                RosterEntry.employee_id == world["ids"]["e1"]
            ).values(status="draft"))
            await db.commit()


async def test_concurrent_publish_request_cancel_vs_decide(client, world):
    ha = await _login(client, world["admin_email"])
    hd = await _login(client, world["email"])
    await _grant(world, can_publish=False)
    await _put(client, ha, world, "e1", 0, status="draft")
    pr = (await client.post(f"{ROSTER}/publish-requests", headers=hd,
                            json={"start": dd(0), "end": dd(6)})).json()
    base = f"{ROSTER}/publish-requests/{pr['id']}"
    r1, r2 = await asyncio.gather(
        client.post(f"{base}/decide", headers=ha, json={"approve": True}),
        client.post(f"{base}/cancel", headers=hd),
    )
    assert sorted([r1.status_code, r2.status_code]) == [200, 409], (
        r1.text, r2.text)


async def test_concurrent_change_request_decide(client, world):
    ha = await _login(client, world["admin_email"])
    h1 = await _login(client, world["e1_email"])
    r = await client.post(f"{ROSTER}/change-requests", headers=h1, json={
        "work_date": dd(0), "requested_shift_template_id": world["ids"]["t2"],
        "reason": "need a swap"})
    assert r.status_code == 200, r.text
    url = f"{ROSTER}/change-requests/{r.json()['id']}/decide"
    r1, r2 = await asyncio.gather(
        client.post(url, headers=ha, json={"action": "approve"}),
        client.post(url, headers=ha, json={"action": "approve"}),
    )
    assert sorted([r1.status_code, r2.status_code]) == [200, 409], (
        r1.text, r2.text)


async def test_concurrent_change_request_cancel_vs_decide(client, world):
    ha = await _login(client, world["admin_email"])
    h1 = await _login(client, world["e1_email"])
    r = await client.post(f"{ROSTER}/change-requests", headers=h1, json={
        "work_date": dd(1), "requested_week_off": True, "reason": "need a day"})
    base = f"{ROSTER}/change-requests/{r.json()['id']}"
    ra, rb = await asyncio.gather(
        client.post(f"{base}/decide", headers=ha, json={"action": "reject"}),
        client.post(f"{base}/cancel", headers=h1),
    )
    assert sorted([ra.status_code, rb.status_code]) == [200, 409], (
        ra.text, rb.text)


async def test_copy_month_target_end_clamps(client, world):
    ha = await _login(client, world["admin_email"])
    e1 = world["ids"]["e1"]
    src0 = date(2027, 3, 1)
    for d in (date(2027, 3, 1), date(2027, 3, 31)):
        r = await client.post(f"{ROSTER}/entries", headers=ha, json={
            "employee_id": e1, "work_date": d.isoformat(),
            "shift_template_id": world["ids"]["t1"], "status": "draft"})
        assert r.status_code == 200, r.text
    body = {"source_start": "2027-03-01", "source_end": "2027-03-31",
            "target_start": "2027-04-01", "employee_ids": [e1]}
    # invalid target_end
    r = await client.post(f"{ROSTER}/copy", headers=ha, json={
        **body, "target_end": "2027-03-30"})
    assert r.status_code == 422
    r = await client.post(f"{ROSTER}/copy", headers=ha, json={
        **body, "target_end": "2027-06-30"})
    assert r.status_code == 422  # window longer than source
    r = await client.post(f"{ROSTER}/copy", headers=ha, json={
        **body, "target_end": "2027-04-30"})
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 1
    async with SessionLocal() as db:
        dates = {x.work_date for x in (await db.execute(select(RosterEntry).where(
            RosterEntry.employee_id == e1))).scalars().all()}
    assert date(2027, 4, 1) in dates and date(2027, 5, 1) not in dates
    assert src0 in dates


async def test_blank_cell_rejected(client, world):
    ha = await _login(client, world["admin_email"])
    h1 = await _login(client, world["e1_email"])
    e1 = world["ids"]["e1"]
    r = await client.post(f"{ROSTER}/entries", headers=ha, json={
        "employee_id": e1, "work_date": dd(0), "shift_template_id": None,
        "is_week_off": False, "status": "draft"})
    assert r.status_code == 422, r.text
    ok = await _put(client, ha, world, "e1", 0, status="draft")
    # PATCH resulting in a blank cell
    r = await client.patch(f"{ROSTER}/entries/{ok['id']}", headers=ha,
                           json={"shift_template_id": None})
    assert r.status_code == 422, r.text
    # PATCH that does not touch the cell content is still fine
    r = await client.patch(f"{ROSTER}/entries/{ok['id']}", headers=ha,
                           json={"note": "n"})
    assert r.status_code == 200, r.text
    # week-off via PATCH is fine
    r = await client.patch(f"{ROSTER}/entries/{ok['id']}", headers=ha,
                           json={"is_week_off": True})
    assert r.status_code == 200 and r.json()["is_week_off"] is True
    # change request without anything requested
    r = await client.post(f"{ROSTER}/change-requests", headers=h1, json={
        "work_date": dd(2), "reason": "no target given"})
    assert r.status_code == 422, r.text
    # bulk with a blank entry keeps its semantics (not a 422)
    r = await client.post(f"{ROSTER}/bulk", headers=ha, json={
        "start": dd(0), "end": dd(1), "status": "draft",
        "entries": [{"employee_id": e1, "work_date": dd(1)}]})
    assert r.status_code == 200, r.text


async def test_huge_id_is_422_not_500(client, world):
    ha = await _login(client, world["admin_email"])
    r = await client.post(f"{ROSTER}/entries", headers=ha, json={
        "employee_id": 10 ** 25, "work_date": dd(0),
        "shift_template_id": world["ids"]["t1"], "status": "draft"})
    assert r.status_code == 422, r.text


async def test_commit_or_409_maps_dataerror_and_lock_errors():
    from fastapi import HTTPException
    from sqlalchemy.exc import DataError, OperationalError
    from app.api.v1.endpoints.roster_common import commit_or_409

    class Orig(Exception):
        pass

    class FakeDB:
        def __init__(self, exc):
            self.exc, self.rolled = exc, False

        async def commit(self):
            raise self.exc

        async def rollback(self):
            self.rolled = True

    db = FakeDB(DataError("s", {}, Orig(1264, "out of range")))
    with pytest.raises(HTTPException) as ei:
        await commit_or_409(db)
    assert ei.value.status_code == 422 and db.rolled
    for code in (1020, 1213):
        db = FakeDB(OperationalError("s", {}, Orig(code, "x")))
        with pytest.raises(HTTPException) as ei:
            await commit_or_409(db)
        assert ei.value.status_code == 409 and db.rolled
    db = FakeDB(OperationalError("s", {}, Orig(2006, "gone")))
    with pytest.raises(OperationalError):
        await commit_or_409(db)
