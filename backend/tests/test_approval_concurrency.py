"""Concurrent approval decisions: exactly one wins, the rest get 409, side
effects happen once (never a 5xx from MariaDB 1020)."""
import asyncio
from datetime import date

from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from _appr_world import (  # noqa: F401
    client, login, mk_item, world,
)
from app.api import deps
from app.core.config import settings
from app.db.session import SessionLocal
from app.main import create_app
from app.models.approval import ApprovalItem, ApprovalStatus
from app.models.leave import (
    LeaveBalanceLedger, LeaveRequest, LeaveStatus,
)
from app.models.notification import Notification

API = settings.API_V1_STR
N = 5


async def _fire(headers, calls):
    """Run `calls` (list of (path, json)) concurrently, each on its own
    client/app, so they use separate DB sessions."""
    app = create_app()
    app.dependency_overrides[deps.verify_attendance] = lambda: None

    async def one(path, body):
        async with AsyncClient(transport=ASGITransport(app=app),
                               base_url="http://test") as c:
            return await c.post(f"{API}{path}", headers=headers, json=body)
    return await asyncio.gather(*(one(p, b) for p, b in calls))


def _assert_one_winner(rs):
    codes = sorted(r.status_code for r in rs)
    assert codes == [200] + [409] * (len(rs) - 1), [r.text for r in rs]


async def _count_notes(uid, title):
    async with SessionLocal() as db:
        return (await db.execute(
            select(func.count()).select_from(Notification).where(
                Notification.user_id == uid, Notification.title == title)
        )).scalar_one()


async def test_concurrent_generic_approve(client, world):
    ids = world["ids"]
    iid, _ = await mk_item(world, "apr")
    ha = await login(client, world, "apr")
    rs = await _fire(ha, [(f"/approvals/{iid}/action",
                           {"status": "approved"})] * N)
    _assert_one_winner(rs)
    async with SessionLocal() as db:
        assert (await db.get(ApprovalItem, iid)).status \
            == ApprovalStatus.APPROVED
    assert await _count_notes(ids["req"], "Approval Request Approved") == 1
    # a later sequential decision is also a clean 409
    r = await client.post(f"{API}/approvals/{iid}/action", headers=ha,
                          json={"status": "approved"})
    assert r.status_code == 409


async def test_concurrent_chained_step_advances_once(client, world):
    iid, _ = await mk_item(world, "apr", steps=2)
    ha = await login(client, world, "apr")
    rs = await _fire(ha, [(f"/approvals/{iid}/action",
                           {"status": "approved"})] * N)
    # step 2 is also held by apr, so exactly one request may win step 1; the
    # rest must be 200/409 only, and the item must be at step 2 at most.
    assert all(r.status_code in (200, 409) for r in rs), [r.text for r in rs]
    assert sum(r.status_code == 200 for r in rs) >= 1
    async with SessionLocal() as db:
        it = await db.get(ApprovalItem, iid)
        assert it.current_step_number <= 2


async def test_concurrent_leave_approve_debits_once(client, world):
    ids = world["ids"]
    async with SessionLocal() as db:
        lv = LeaveRequest(
            employee_id=ids["req"], leave_type_id=ids["lt"],
            start_date=date(2031, 5, 5), end_date=date(2031, 5, 6),
            reason="t", status=LeaveStatus.SUBMITTED,
            created_by_user_id=ids["req"])
        db.add(lv)
        await db.flush()
        from app.models.approval import ApprovalStep
        item = ApprovalItem(resource_type="leave_request",
                            resource_id=str(lv.id),
                            status=ApprovalStatus.PENDING,
                            current_step_number=1,
                            requested_by_id=ids["req"])
        db.add(item)
        await db.flush()
        db.add(ApprovalStep(approval_item_id=item.id, step_number=1,
                            approver_id=ids["apr"],
                            status=ApprovalStatus.PENDING))
        await db.commit()
        iid, lid = item.id, lv.id
    ha = await login(client, world, "apr")
    rs = await _fire(ha, [(f"/approvals/{iid}/action",
                           {"status": "approved"})] * N)
    _assert_one_winner(rs)
    async with SessionLocal() as db:
        assert (await db.get(LeaveRequest, lid)).status == LeaveStatus.APPROVED
        led = (await db.execute(select(LeaveBalanceLedger).where(
            LeaveBalanceLedger.user_id == ids["req"]))).scalars().first()
        assert led.used == 2.0


async def test_concurrent_notification_actions(client, world, monkeypatch):
    async def ok(*a, **k):
        return None
    monkeypatch.setattr(deps, "verify_attendance", ok)
    ids = world["ids"]
    iid, _ = await mk_item(world, "apr")
    async with SessionLocal() as db:
        item = await db.get(ApprovalItem, iid)
        n = Notification(user_id=ids["apr"], title="Approval Request Pending",
                         message="m", type="info",
                         resource_type=item.resource_type,
                         resource_id=item.resource_id)
        db.add(n)
        await db.commit()
        nid = n.id
    ha = await login(client, world, "apr")
    rs = await _fire(ha, [("/notifications/actions",
                           {"notification_id": nid, "action": "approve"})] * N)
    codes = sorted(r.status_code for r in rs)
    # up-front "no longer pending" stays 400; a lost race is 409; never 5xx
    assert codes.count(200) == 1, [r.text for r in rs]
    assert all(c in (200, 400, 409) for c in codes), [r.text for r in rs]
    assert await _count_notes(ids["req"], "Approval Request Approved") == 1


# ── leave cancel / approve races, 409 for decided, benign writers ───────────

async def _mk_leave_item(world, day):
    from app.models.approval import ApprovalStep
    ids = world["ids"]
    async with SessionLocal() as db:
        lv = LeaveRequest(
            employee_id=ids["req"], leave_type_id=ids["lt"],
            start_date=date(2031, 6, day), end_date=date(2031, 6, day + 1),
            reason="t", status=LeaveStatus.SUBMITTED,
            created_by_user_id=ids["req"])
        db.add(lv)
        await db.flush()
        item = ApprovalItem(resource_type="leave_request",
                            resource_id=str(lv.id),
                            status=ApprovalStatus.PENDING,
                            current_step_number=1,
                            requested_by_id=ids["req"])
        db.add(item)
        await db.flush()
        db.add(ApprovalStep(approval_item_id=item.id, step_number=1,
                            approver_id=ids["apr"],
                            status=ApprovalStatus.PENDING))
        await db.commit()
        return item.id, lv.id


async def _used(uid):
    async with SessionLocal() as db:
        led = (await db.execute(select(LeaveBalanceLedger).where(
            LeaveBalanceLedger.user_id == uid))).scalars().first()
        return led.used


async def test_sequential_repeat_leave_decision_is_409(client, world):
    iid, lid = await _mk_leave_item(world, 3)
    ha = await login(client, world, "apr")
    p = f"{API}/leave/approvals/{iid}/action"
    assert (await client.post(p, headers=ha,
                              json={"status": "approved"})).status_code == 200
    for st in ("approved", "rejected"):
        r = await client.post(p, headers=ha, json={"status": st})
        assert r.status_code == 409, r.text
        assert "Approval already actioned" in r.text
    r = await client.post(f"{API}/approvals/{iid}/action", headers=ha,
                          json={"status": "approved"})
    assert r.status_code == 409
    assert await _used(world["ids"]["req"]) == 2.0


async def test_cancel_racing_approve(client, world):
    from sqlalchemy import insert
    from app.db.session import SessionLocal as SL
    from app.models.user import Permission, role_permissions
    ids = world["ids"]
    made = None
    async with SL() as db:
        p = (await db.execute(select(Permission).where(
            Permission.name == "employee leave write"))).scalar_one_or_none()
        if p is None:
            p = Permission(name="employee leave write", description="t")
            db.add(p)
            await db.flush()
            made = p.id
        pid = p.id
        await db.execute(insert(role_permissions).values(
            role_id=ids["role"], permission_id=pid))
        await db.commit()
    try:
        hr = await login(client, world, "req")
        ha = await login(client, world, "apr")
        outcomes = set()
        for k in range(4):
            iid, lid = await _mk_leave_item(world, 10 + 3 * k)
            before = await _used(ids["req"])
            app = create_app()
            app.dependency_overrides[deps.verify_attendance] = lambda: None

            async def one(path, headers, body):
                async with AsyncClient(transport=ASGITransport(app=app),
                                       base_url="http://test") as c:
                    return await c.post(f"{API}{path}", headers=headers,
                                        json=body)
            rs = await asyncio.gather(
                one(f"/leave/approvals/{iid}/action", ha,
                    {"status": "approved"}),
                one(f"/leave/{lid}/cancel", hr, {}))
            assert all(r.status_code < 500 for r in rs), [r.text for r in rs]
            assert all(r.status_code in (200, 400, 409) for r in rs), \
                [r.text for r in rs]
            async with SessionLocal() as db:
                lv = await db.get(LeaveRequest, lid)
                it = await db.get(ApprovalItem, iid)
                final = lv.status
                istat = it.status
            used = await _used(ids["req"])
            if final == LeaveStatus.CANCELLED:
                assert used == before and istat == ApprovalStatus.REJECTED
            else:
                assert final == LeaveStatus.APPROVED
                assert istat == ApprovalStatus.APPROVED
                assert used == before + 2.0
            outcomes.add(final)
    finally:
        async with SL() as db:
            from sqlalchemy import delete
            await db.execute(delete(role_permissions).where(
                role_permissions.c.role_id == ids["role"],
                role_permissions.c.permission_id == pid))
            if made:
                await db.execute(delete(Permission).where(
                    Permission.id == made))
            await db.commit()


async def test_benign_writer_does_not_cause_false_409(client, world):
    ha = await login(client, world, "apr")
    for _ in range(3):
        iid, _ = await mk_item(world, "apr")
        app = create_app()
        app.dependency_overrides[deps.verify_attendance] = lambda: None

        async def touch():
            for _i in range(5):
                async with SessionLocal() as db:
                    it = await db.get(ApprovalItem, iid)
                    it.due_date = None if it.due_date else date(2031, 1, 1)
                    await db.commit()
                await asyncio.sleep(0.01)

        async def approve():
            async with AsyncClient(transport=ASGITransport(app=app),
                                   base_url="http://test") as c:
                return await c.post(f"{API}/approvals/{iid}/action",
                                    headers=ha, json={"status": "approved"})
        _, r = await asyncio.gather(touch(), approve())
        assert r.status_code == 200, r.text
