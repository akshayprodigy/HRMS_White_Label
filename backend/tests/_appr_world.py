"""Shared fixtures for the Task 6 approval tests (SLA / delegation / bulk).

Users (all uuid-suffixed): mgr (manager of apr), apr (approver), dlg
(delegate), oth (other), req (requester), hr (holds the test HR role), nom
(approver with no manager). Teardown leaves zero rows behind.
"""
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, insert, select

from app.api import deps
from app.core.config import settings
from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.main import create_app
from app.models.approval import ApprovalItem, ApprovalStatus, ApprovalStep
from app.models.approval_chain import (
    ChainedApprovalInstance, ChainedApprovalStepInstance,
)
from app.models.approver_delegation import ApproverDelegation
from app.models.audit import AuditLog
from app.models.leave import (
    LeaveBalanceLedger, LeaveRequest, LeaveStatus, LeaveType,
)
from app.models.notification import Notification
from app.models.notification_channel import NotificationDelivery
from app.models.system import SystemSetting
from app.models.user import Permission, Role, User, role_permissions, user_roles

PW = "test@12345"
TAGS = ("mgr", "apr", "dlg", "oth", "req", "hr", "nom")


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
    made_perm = None
    try:
        async with SessionLocal() as db:
            role = Role(name=f"AWR{sfx}", description="t")
            hr_role = Role(name=f"AWH{sfx}", description="t")
            db.add_all([role, hr_role])
            await db.flush()
            p = (await db.execute(select(Permission).where(
                Permission.name == "leave approve"))).scalar_one_or_none()
            if p is None:
                p = Permission(name="leave approve", description="t")
                db.add(p)
                await db.flush()
                made_perm = p.id
            await db.execute(insert(role_permissions).values(
                role_id=role.id, permission_id=p.id))

            def mk(tag, **kw):
                return User(email=f"aw_{tag}_{sfx}@t.com",
                            full_name=f"AW {tag}",
                            hashed_password=get_password_hash(PW),
                            is_active=True, **kw)
            mgr = mk("mgr")
            db.add(mgr)
            await db.flush()
            users = {"mgr": mgr}
            for tag in ("apr", "dlg", "oth", "req", "hr", "nom"):
                kw = {"manager_id": mgr.id} if tag == "apr" else {}
                users[tag] = mk(tag, **kw)
                db.add(users[tag])
            await db.flush()
            for tag in ("mgr", "apr", "dlg", "oth", "req", "nom"):
                await db.execute(insert(user_roles).values(
                    user_id=users[tag].id, role_id=role.id))
            await db.execute(insert(user_roles).values(
                user_id=users["hr"].id, role_id=hr_role.id))
            lt = LeaveType(name=f"AWT{sfx}", unpaid_allowed=False)
            db.add(lt)
            await db.flush()
            db.add(LeaveBalanceLedger(user_id=users["req"].id,
                                      leave_type_id=lt.id,
                                      balance=20.0, used=0.0))
            await db.commit()
            ids = {t: u.id for t, u in users.items()}
            ids.update(lt=lt.id, role=role.id, hr_role=hr_role.id)
        yield {"ids": ids, "sfx": sfx, "n": [0]}
    finally:
        async with SessionLocal() as db:
            uids = list((await db.execute(select(User.id).where(
                User.email.like(f"aw\\_%\\_{sfx}@t.com")))).scalars().all())
            nids = list((await db.execute(select(Notification.id).where(
                Notification.user_id.in_(uids)))).scalars().all())
            if nids:
                await db.execute(delete(NotificationDelivery).where(
                    NotificationDelivery.notification_id.in_(nids)))
            await db.execute(delete(NotificationDelivery).where(
                NotificationDelivery.recipient_user_id.in_(uids)))
            await db.execute(delete(Notification).where(
                Notification.user_id.in_(uids)))
            lids = [str(i) for i in (await db.execute(select(LeaveRequest.id)
                    .where(LeaveRequest.employee_id.in_(uids)))).scalars().all()]
            items = list((await db.execute(select(ApprovalItem.id).where(
                (ApprovalItem.resource_id.like(f"{sfx}%"))
                | (ApprovalItem.requested_by_id.in_(uids))
                | (ApprovalItem.resource_id.in_(lids or ["-"]))
            ))).scalars().all())
            if items:
                await db.execute(delete(ApprovalStep).where(
                    ApprovalStep.approval_item_id.in_(items)))
                await db.execute(delete(ApprovalItem).where(
                    ApprovalItem.id.in_(items)))
            insts = list((await db.execute(select(ChainedApprovalInstance.id)
                    .where(ChainedApprovalInstance.submitter_id.in_(uids))
                    )).scalars().all())
            if insts:
                await db.execute(delete(ChainedApprovalStepInstance).where(
                    ChainedApprovalStepInstance.instance_id.in_(insts)))
                await db.execute(delete(ChainedApprovalInstance).where(
                    ChainedApprovalInstance.id.in_(insts)))
            await db.execute(delete(AuditLog).where(
                AuditLog.user_id.in_(uids)))
            await db.execute(delete(ApproverDelegation).where(
                (ApproverDelegation.user_id.in_(uids))
                | (ApproverDelegation.delegate_id.in_(uids))))
            await db.execute(delete(LeaveRequest).where(
                LeaveRequest.employee_id.in_(uids)))
            await db.execute(delete(LeaveBalanceLedger).where(
                LeaveBalanceLedger.user_id.in_(uids)))
            await db.execute(delete(user_roles).where(
                user_roles.c.user_id.in_(uids)))
            await db.execute(delete(User).where(User.id.in_(uids)))
            await db.execute(delete(LeaveType).where(
                LeaveType.name == f"AWT{sfx}"))
            await db.execute(delete(Role).where(
                Role.name.in_([f"AWR{sfx}", f"AWH{sfx}"])))
            if made_perm:
                await db.execute(delete(Permission).where(
                    Permission.id == made_perm))
            await db.commit()


async def login(client, w, tag):
    r = await client.post(f"{settings.API_V1_STR}/auth/login", data={
        "username": f"aw_{tag}_{w['sfx']}@t.com", "password": PW})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def mk_item(w, approver, requester="req", *, due=None, role_id=None,
                  rtype="sla_test", steps=1, due_none=False):
    """A pending generic ApprovalItem whose step 1 is held by `approver`
    (a tag, or None with `role_id`). Returns (item_id, step_ids)."""
    ids = w["ids"]
    w["n"][0] += 1
    async with SessionLocal() as db:
        item = ApprovalItem(
            resource_type=rtype, resource_id=f"{w['sfx']}{w['n'][0]}",
            status=ApprovalStatus.PENDING, current_step_number=1,
            requested_by_id=ids[requester])
        db.add(item)
        await db.flush()
        sids = []
        for n in range(1, steps + 1):
            st = ApprovalStep(
                approval_item_id=item.id, step_number=n,
                approver_id=ids[approver] if approver else None,
                role_id=role_id, status=ApprovalStatus.PENDING)
            db.add(st)
            await db.flush()
            sids.append(st.id)
        if due is not None or due_none:
            item.due_date = due
        await db.commit()
        return item.id, sids


async def mk_chain(w, approver, submitter="req", *, due_at=None):
    """A pending chain instance with one pending step held by `approver`."""
    ids = w["ids"]
    w["n"][0] += 1
    async with SessionLocal() as db:
        inst = ChainedApprovalInstance(
            chain_id=None, entity_type="expense",
            entity_id=990000000 + w["n"][0], submitter_id=ids[submitter],
            amount_paise=1000, status="pending", current_step_order=1)
        db.add(inst)
        await db.flush()
        si = ChainedApprovalStepInstance(
            instance_id=inst.id, step_order=1, approver_type="specific_user",
            approver_user_id=ids[approver], mode="sequential",
            parallel_rule="all", status="pending", due_at=due_at)
        db.add(si)
        await db.flush()
        await db.commit()
        return inst.id, si.id


async def set_sla(value):
    """Set approvals.sla_hours (None = remove the setting). Caller restores."""
    async with SessionLocal() as db:
        row = await db.get(SystemSetting, "approvals.sla_hours")
        if value is None:
            if row:
                await db.delete(row)
        elif row:
            row.value = str(value)
        else:
            db.add(SystemSetting(key="approvals.sla_hours", value=str(value),
                                 description="t"))
        await db.commit()


async def get_sla():
    async with SessionLocal() as db:
        row = await db.get(SystemSetting, "approvals.sla_hours")
        return row.value if row else None


async def mk_delegation(w, user, delegate, *, starts=None, ends=None,
                        only_leave=False, revoked=False):
    ids = w["ids"]
    async with SessionLocal() as db:
        d = ApproverDelegation(
            user_id=ids[user], delegate_id=ids[delegate],
            starts_on=starts or date.today() - timedelta(days=1),
            ends_on=ends, only_when_on_leave=only_leave,
            revoked_at=datetime.now(timezone.utc) if revoked else None)
        db.add(d)
        await db.commit()
        return d.id
