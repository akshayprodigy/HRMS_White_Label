"""Leave approval consistency + notifications (Roadmap v2 Phase 2, Task 0)."""
import asyncio
import uuid
from datetime import date

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, insert, select

from app.api import deps
from app.core.config import settings
from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.main import create_app
from app.models.approval import ApprovalItem, ApprovalStatus, ApprovalStep
from app.models.audit import AuditLog
from app.models.comp_off import CompOffAccrual
from app.models.leave import (
    LeaveBalanceLedger, LeaveRequest, LeaveStatus, LeaveType,
)
from app.models.notification import Notification
from app.models.notification_channel import NotificationDelivery
from app.models.user import Permission, Role, User, role_permissions, user_roles

PW = "test@12345"
PERMS = ("leave approve", "employee leave write", "employee leave read")


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
    made_perms, made_co = [], False
    try:
        async with SessionLocal() as db:
            role = Role(name=f"LVR{sfx}", description="t")
            hr_role = Role(name=f"LVH{sfx}", description="t")
            db.add_all([role, hr_role])
            await db.flush()
            for pn in PERMS:
                p = (await db.execute(select(Permission).where(
                    Permission.name == pn))).scalar_one_or_none()
                if p is None:
                    p = Permission(name=pn, description="t")
                    db.add(p)
                    await db.flush()
                    made_perms.append(p.id)
                await db.execute(insert(role_permissions).values(
                    role_id=role.id, permission_id=p.id))

            def mk(tag, **kw):
                return User(email=f"lv_{tag}_{sfx}@t.com", full_name=f"LV {tag}",
                            hashed_password=get_password_hash(PW),
                            is_active=True, **kw)
            mgr = mk("mgr")
            hr2 = mk("hr")
            admin = mk("admin", is_superuser=True)
            db.add_all([mgr, hr2, admin])
            await db.flush()
            emp = mk("emp", manager_id=mgr.id)
            emp_nm = mk("nm")
            db.add_all([emp, emp_nm])
            await db.flush()
            for u in (mgr, emp, emp_nm):
                await db.execute(insert(user_roles).values(
                    user_id=u.id, role_id=role.id))
            await db.execute(insert(user_roles).values(
                user_id=hr2.id, role_id=hr_role.id))
            await db.execute(insert(user_roles).values(
                user_id=hr2.id, role_id=role.id))
            lt = LeaveType(name=f"LVT{sfx}", unpaid_allowed=False)
            db.add(lt)
            co = (await db.execute(select(LeaveType).where(
                LeaveType.code == "CO"))).scalars().first()
            if co is None:
                co = LeaveType(name=f"LVCO{sfx}", code="CO")
                db.add(co)
                made_co = True
            await db.flush()
            for u in (emp, emp_nm):
                db.add(LeaveBalanceLedger(user_id=u.id, leave_type_id=lt.id,
                                          balance=10.0, used=0.0))
            await db.commit()
            ids = dict(mgr=mgr.id, hr=hr2.id, admin=admin.id, emp=emp.id,
                       nm=emp_nm.id, lt=lt.id, co=co.id, hr_role=hr_role.id)
        yield {"ids": ids, "sfx": sfx}
    finally:
        async with SessionLocal() as db:
            uids = list((await db.execute(select(User.id).where(
                User.email.like(f"lv\\_%\\_{sfx}@t.com")))).scalars().all())
            nids = list((await db.execute(select(Notification.id).where(
                Notification.user_id.in_(uids)))).scalars().all())
            if nids:
                await db.execute(delete(NotificationDelivery).where(
                    NotificationDelivery.notification_id.in_(nids)))
            await db.execute(delete(NotificationDelivery).where(
                NotificationDelivery.recipient_user_id.in_(uids)))
            await db.execute(delete(Notification).where(
                Notification.user_id.in_(uids)))
            lids = list((await db.execute(select(LeaveRequest.id).where(
                LeaveRequest.employee_id.in_(uids)))).scalars().all())
            cids = list((await db.execute(select(CompOffAccrual.id).where(
                CompOffAccrual.user_id.in_(uids)))).scalars().all())
            rids = [str(i) for i in lids + cids]
            if rids:
                items = list((await db.execute(select(ApprovalItem.id).where(
                    ApprovalItem.resource_id.in_(rids),
                    ApprovalItem.resource_type.in_(
                        ["leave_request", "comp_off_accrual"])
                ))).scalars().all())
                if items:
                    await db.execute(delete(ApprovalStep).where(
                        ApprovalStep.approval_item_id.in_(items)))
                    await db.execute(delete(ApprovalItem).where(
                        ApprovalItem.id.in_(items)))
                await db.execute(delete(AuditLog).where(
                    AuditLog.resource_id.in_(rids),
                    AuditLog.resource_type.in_(
                        ["leave_request", "comp_off_accrual"])))
            await db.execute(delete(AuditLog).where(AuditLog.user_id.in_(uids)))
            await db.execute(delete(CompOffAccrual).where(
                CompOffAccrual.user_id.in_(uids)))
            await db.execute(delete(LeaveRequest).where(
                LeaveRequest.employee_id.in_(uids)))
            await db.execute(delete(LeaveBalanceLedger).where(
                LeaveBalanceLedger.user_id.in_(uids)))
            await db.execute(delete(user_roles).where(
                user_roles.c.user_id.in_(uids)))
            await db.execute(delete(User).where(User.id.in_(uids)))
            await db.execute(delete(LeaveType).where(
                LeaveType.name == f"LVT{sfx}"))
            if made_co:
                await db.execute(delete(LeaveType).where(
                    LeaveType.name == f"LVCO{sfx}"))
            await db.execute(delete(Role).where(
                Role.name.in_([f"LVR{sfx}", f"LVH{sfx}"])))
            if made_perms:
                await db.execute(delete(Permission).where(
                    Permission.id.in_(made_perms)))
            await db.commit()


async def _login(client, w, tag):
    r = await client.post(f"{settings.API_V1_STR}/auth/login", data={
        "username": f"lv_{tag}_{w['sfx']}@t.com", "password": PW})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _mk_leave(w, *, two_step=False, days=2, emp="emp", day=10):
    """Submitted leave + approval chain (manager step [+ own-HR-role step])."""
    ids = w["ids"]
    async with SessionLocal() as db:
        lv = LeaveRequest(
            employee_id=ids[emp], leave_type_id=ids["lt"],
            start_date=date(2031, 3, day), end_date=date(2031, 3, day + days - 1),
            reason="t", status=LeaveStatus.SUBMITTED,
            created_by_user_id=ids[emp])
        db.add(lv)
        await db.flush()
        item = ApprovalItem(resource_type="leave_request",
                            resource_id=str(lv.id),
                            status=ApprovalStatus.PENDING,
                            current_step_number=1,
                            requested_by_id=ids[emp])
        db.add(item)
        await db.flush()
        db.add(ApprovalStep(approval_item_id=item.id, step_number=1,
                            approver_id=ids["mgr"],
                            status=ApprovalStatus.PENDING))
        if two_step:
            db.add(ApprovalStep(approval_item_id=item.id, step_number=2,
                                role_id=ids["hr_role"],
                                status=ApprovalStatus.PENDING))
        await db.commit()
        return lv.id, item.id


async def _used(w, emp="emp"):
    async with SessionLocal() as db:
        return (await db.execute(select(LeaveBalanceLedger.used).where(
            LeaveBalanceLedger.user_id == w["ids"][emp],
            LeaveBalanceLedger.leave_type_id == w["ids"]["lt"]
        ))).scalar_one()


async def _status(lid):
    async with SessionLocal() as db:
        return (await db.get(LeaveRequest, lid)).status


async def _notes(uid, event_type):
    async with SessionLocal() as db:
        return list((await db.execute(select(Notification).where(
            Notification.user_id == uid,
            Notification.event_type == event_type))).scalars().all())


def _a(item_id, who_path):
    base = settings.API_V1_STR
    return (f"{base}/approvals/{item_id}/action" if who_path == "generic"
            else f"{base}/leave/approvals/{item_id}/action")


@pytest.mark.parametrize("path", ["generic", "leave"])
async def test_approve_debits_ledger_once(client, world, path):
    lid, item = await _mk_leave(world)
    h = await _login(client, world, "mgr")
    r = await client.post(_a(item, path), headers=h,
                          json={"status": "approved"})
    assert r.status_code == 200, r.text
    assert await _used(world) == 2.0
    assert await _status(lid) == LeaveStatus.APPROVED
    # replay: rejected, no second debit
    r = await client.post(_a(item, path), headers=h,
                          json={"status": "approved"})
    assert r.status_code in (400, 409), r.text
    assert await _used(world) == 2.0


async def test_mixed_endpoints_replay_single_debit(client, world):
    lid, item = await _mk_leave(world)
    h = await _login(client, world, "mgr")
    assert (await client.post(_a(item, "leave"), headers=h,
                              json={"status": "approved"})).status_code == 200
    r = await client.post(_a(item, "generic"), headers=h,
                          json={"status": "approved"})
    assert r.status_code in (400, 409)
    assert await _used(world) == 2.0


async def test_concurrent_double_approval_single_debit(client, world):
    lid, item = await _mk_leave(world)
    h = await _login(client, world, "mgr")
    ha = await _login(client, world, "admin")
    rs = await asyncio.gather(
        client.post(_a(item, "generic"), headers=h, json={"status": "approved"}),
        client.post(_a(item, "leave"), headers=h, json={"status": "approved"}),
        client.post(_a(item, "generic"), headers=ha, json={"status": "approved"}),
    )
    codes = sorted(r.status_code for r in rs)
    assert codes.count(200) == 1, [r.text for r in rs]
    assert all(c in (200, 400, 409) for c in codes), codes
    assert await _used(world) == 2.0


@pytest.mark.parametrize("path", ["generic", "leave"])
async def test_reject_no_debit_and_notifies_requester(client, world, path):
    lid, item = await _mk_leave(world)
    h = await _login(client, world, "mgr")
    r = await client.post(_a(item, path), headers=h,
                          json={"status": "rejected", "comment": "no"})
    assert r.status_code == 200, r.text
    assert await _used(world) == 0.0
    assert await _status(lid) == LeaveStatus.REJECTED
    notes = await _notes(world["ids"]["emp"], "leave_rejected")
    assert len(notes) == 1 and notes[0].resource_id == str(lid)
    r = await client.post(_a(item, path), headers=h, json={"status": "rejected"})
    assert r.status_code in (400, 409)


@pytest.mark.parametrize("path", ["generic", "leave"])
async def test_two_step_notifies_next_approver_then_requester(client, world, path):
    lid, item = await _mk_leave(world, two_step=True, days=1, day=20)
    ids = world["ids"]
    hm = await _login(client, world, "mgr")
    r = await client.post(_a(item, path), headers=hm,
                          json={"status": "approved"})
    assert r.status_code == 200, r.text
    assert await _used(world) == 0.0            # not final yet
    assert await _status(lid) == LeaveStatus.SUBMITTED
    pend = await _notes(ids["hr"], "approval_pending")   # role-only step
    assert len(pend) == 1 and pend[0].resource_id == str(lid)
    hh = await _login(client, world, "hr")
    r = await client.post(_a(item, path), headers=hh,
                          json={"status": "approved"})
    assert r.status_code == 200, r.text
    assert await _used(world) == 1.0
    ok = await _notes(ids["emp"], "leave_approved")
    assert len(ok) == 1


async def test_admin_override_generic_debits_once(client, world):
    lid, item = await _mk_leave(world, two_step=True)
    ha = await _login(client, world, "admin")
    r = await client.post(_a(item, "generic"), headers=ha,
                          json={"status": "approved"})
    assert r.status_code == 200, r.text
    assert r.json()["status"].lower() == "approved"
    assert await _used(world) == 2.0
    assert await _status(lid) == LeaveStatus.APPROVED
    async with SessionLocal() as db:
        steps = (await db.execute(select(ApprovalStep).where(
            ApprovalStep.approval_item_id == item))).scalars().all()
        assert all(s.status == ApprovalStatus.APPROVED for s in steps)
    r = await client.post(_a(item, "generic"), headers=ha,
                          json={"status": "approved"})
    assert r.status_code in (400, 409)
    assert await _used(world) == 2.0


async def test_self_approval_still_blocked(client, world):
    lid, item = await _mk_leave(world)
    async with SessionLocal() as db:   # make the employee the step approver
        s = (await db.execute(select(ApprovalStep).where(
            ApprovalStep.approval_item_id == item))).scalars().first()
        s.approver_id = world["ids"]["emp"]
        await db.commit()
    h = await _login(client, world, "emp")
    r = await client.post(_a(item, "leave"), headers=h,
                          json={"status": "approved"})
    assert r.status_code == 403
    assert await _used(world) == 0.0


async def test_apply_notifies_manager(client, world):
    h = await _login(client, world, "emp")
    r = await client.post(f"{settings.API_V1_STR}/leave/apply", headers=h, json={
        "leave_type_id": world["ids"]["lt"], "start_date": "2031-05-05",
        "end_date": "2031-05-06", "reason": "trip"})
    assert r.status_code == 200, r.text
    lid = r.json()["id"]
    notes = await _notes(world["ids"]["mgr"], "leave_submitted")
    assert len(notes) == 1 and notes[0].resource_id == str(lid)
    # approve end-to-end through the real apply chain is manager -> HR role; the
    # HR step is the real HR role, so only the manager hop is exercised here.


async def test_notification_failure_does_not_break_request(client, world, monkeypatch):
    import app.services.notifications_delivery as nd

    async def boom(*a, **k):
        raise RuntimeError("delivery down")
    monkeypatch.setattr(nd, "notify", boom)
    lid, item = await _mk_leave(world)
    h = await _login(client, world, "mgr")
    r = await client.post(_a(item, "leave"), headers=h,
                          json={"status": "approved"})
    assert r.status_code == 200, r.text
    assert await _used(world) == 2.0
    assert await _notes(world["ids"]["emp"], "leave_approved") == []


@pytest.mark.parametrize("path", ["generic", "leave"])
async def test_comp_off_credits_once(client, world, path):
    ids = world["ids"]
    async with SessionLocal() as db:
        acc = CompOffAccrual(user_id=ids["emp"], holiday_date=date(2031, 1, 26),
                             worked_minutes=480, days_credited=1.0,
                             status="pending")
        db.add(acc)
        await db.flush()
        item = ApprovalItem(resource_type="comp_off_accrual",
                            resource_id=str(acc.id),
                            status=ApprovalStatus.PENDING,
                            current_step_number=1, requested_by_id=ids["emp"])
        db.add(item)
        await db.flush()
        db.add(ApprovalStep(approval_item_id=item.id, step_number=1,
                            approver_id=ids["mgr"],
                            status=ApprovalStatus.PENDING))
        await db.commit()
        item_id = item.id
    h = await _login(client, world, "mgr")
    r = await client.post(_a(item_id, path), headers=h,
                          json={"status": "approved"})
    assert r.status_code == 200, r.text
    r = await client.post(_a(item_id, path), headers=h,
                          json={"status": "approved"})
    assert r.status_code in (400, 409)
    async with SessionLocal() as db:
        bal = (await db.execute(select(LeaveBalanceLedger.balance).where(
            LeaveBalanceLedger.user_id == ids["emp"],
            LeaveBalanceLedger.leave_type_id == ids["co"]))).scalar_one()
        assert bal == 1.0
