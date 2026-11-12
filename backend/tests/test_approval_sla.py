"""Approval SLA: due dates + escalation (Roadmap v2 Phase 2, Task 6)."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from _appr_world import (  # noqa: F401
    client, get_sla, login, mk_chain, mk_item, set_sla, world,
)
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.approval import ApprovalItem, ApprovalStep
from app.models.approval_chain import ChainedApprovalStepInstance
from app.models.notification import Notification
from app.services.approval_sla import escalate_overdue

API = settings.API_V1_STR


def _now():
    return datetime.now(timezone.utc)


async def _item(iid):
    async with SessionLocal() as db:
        it = (await db.execute(select(ApprovalItem).where(
            ApprovalItem.id == iid))).scalar_one()
        st = (await db.execute(select(ApprovalStep).where(
            ApprovalStep.approval_item_id == iid))).scalars().first()
        return it, st


def _utc(d):
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


async def test_due_date_stamped_on_creation(world):
    prev = await get_sla()
    try:
        await set_sla(None)  # default 48
        iid, _ = await mk_item(world, "apr")
        it, _s = await _item(iid)
        delta = _utc(it.due_date) - _now()
        assert timedelta(hours=47, minutes=50) < delta < timedelta(hours=48, minutes=1)
        await set_sla(24)
        iid, _ = await mk_item(world, "apr")
        it, _s = await _item(iid)
        assert timedelta(hours=23, minutes=50) < _utc(it.due_date) - _now() \
            < timedelta(hours=24, minutes=1)
        await set_sla(0)
        iid, _ = await mk_item(world, "apr")
        it, _s = await _item(iid)
        assert it.due_date is None
    finally:
        await set_sla(prev)


async def test_escalates_to_manager_once_per_period(world):
    ids = world["ids"]
    now = _now()
    iid, _ = await mk_item(world, "apr", due=now - timedelta(hours=1))
    async with SessionLocal() as db:
        r = await escalate_overdue(db, now, item_ids=[iid],
                                   hr_role_id=ids["hr_role"])
    assert r["legacy"] == 1
    it, st = await _item(iid)
    assert st.approver_id == ids["mgr"]
    assert st.escalated_from_id == ids["apr"] and st.escalated_at
    assert _utc(it.due_date) > now + timedelta(hours=47)
    # same period: nothing more
    async with SessionLocal() as db:
        r = await escalate_overdue(db, now + timedelta(hours=1),
                                   item_ids=[iid], hr_role_id=ids["hr_role"])
    assert r["legacy"] == 0
    # next period: manager has no manager -> HR role
    async with SessionLocal() as db:
        r = await escalate_overdue(db, now + timedelta(hours=50),
                                   item_ids=[iid], hr_role_id=ids["hr_role"])
    assert r["legacy"] == 1
    it, st = await _item(iid)
    assert st.approver_id is None and st.role_id == ids["hr_role"]
    # role-held now: no further escalation, ever
    async with SessionLocal() as db:
        r = await escalate_overdue(db, now + timedelta(hours=200),
                                   item_ids=[iid], hr_role_id=ids["hr_role"])
    assert r["legacy"] == 0
    async with SessionLocal() as db:
        n = (await db.execute(select(Notification.user_id).where(
            Notification.event_type == "approval_escalated",
            Notification.user_id.in_(
                [ids["apr"], ids["mgr"], ids["req"], ids["hr"]])
        ))).scalars().all()
    assert ids["mgr"] in n and ids["apr"] in n and ids["req"] in n
    assert ids["hr"] in n


async def test_hr_fallback_without_manager(world):
    ids = world["ids"]
    now = _now()
    iid, _ = await mk_item(world, "nom", due=now - timedelta(minutes=5))
    async with SessionLocal() as db:
        await escalate_overdue(db, now, item_ids=[iid],
                               hr_role_id=ids["hr_role"])
    _it, st = await _item(iid)
    assert st.approver_id is None and st.role_id == ids["hr_role"]
    assert st.escalated_from_id == ids["nom"]


async def test_manager_who_is_requester_is_skipped_for_hr(world):
    ids = world["ids"]
    now = _now()
    # apr's manager is mgr; mgr raised this request -> SoD: go to HR
    iid, _ = await mk_item(world, "apr", requester="mgr",
                           due=now - timedelta(hours=1))
    async with SessionLocal() as db:
        await escalate_overdue(db, now, item_ids=[iid],
                               hr_role_id=ids["hr_role"])
    _it, st = await _item(iid)
    assert st.approver_id is None and st.role_id == ids["hr_role"]


async def test_not_due_and_sla_zero_are_left_alone(world):
    ids = world["ids"]
    now = _now()
    future, _ = await mk_item(world, "apr", due=now + timedelta(hours=5))
    nodue, _ = await mk_item(world, "apr", due_none=True)
    async with SessionLocal() as db:
        r = await escalate_overdue(db, now, item_ids=[future, nodue],
                                   hr_role_id=ids["hr_role"])
    assert r["legacy"] == 0
    prev = await get_sla()
    try:
        await set_sla(0)
        past, _ = await mk_item(world, "apr", due=now - timedelta(hours=9))
        async with SessionLocal() as db:
            r = await escalate_overdue(db, now, item_ids=[past],
                                       hr_role_id=ids["hr_role"])
        assert r["legacy"] == 0
        _it, st = await _item(past)
        assert st.approver_id == ids["apr"]
    finally:
        await set_sla(prev)


async def test_chain_step_escalation(world):
    ids = world["ids"]
    now = _now()
    inst, sid = await mk_chain(world, "apr", due_at=now - timedelta(hours=2))
    inst2, sid2 = await mk_chain(world, "nom", due_at=now - timedelta(hours=2))
    async with SessionLocal() as db:
        r = await escalate_overdue(db, now, instance_ids=[inst, inst2],
                                   hr_role_id=ids["hr_role"])
    assert r["chain"] == 2
    async with SessionLocal() as db:
        s1 = await db.get(ChainedApprovalStepInstance, sid)
        s2 = await db.get(ChainedApprovalStepInstance, sid2)
    assert s1.approver_user_id == ids["mgr"]
    assert s1.escalated_from_id == ids["apr"]
    assert s2.approver_user_id == ids["hr"]
    assert _utc(s1.due_at) > now + timedelta(hours=47)
    async with SessionLocal() as db:
        r = await escalate_overdue(db, now + timedelta(hours=1),
                                   instance_ids=[inst, inst2],
                                   hr_role_id=ids["hr_role"])
    assert r["chain"] == 0


async def test_inbox_payloads_carry_overdue(client, world):
    now = _now()
    iid, _ = await mk_item(world, "apr", due=now - timedelta(hours=3))
    ok, _ = await mk_item(world, "apr", due=now + timedelta(hours=3))
    inst, _s = await mk_chain(world, "apr", due_at=now - timedelta(hours=1))
    h = await login(client, world, "apr")
    r = await client.get(f"{API}/approvals/inbox", headers=h)
    assert r.status_code == 200, r.text
    by = {x["id"]: x for x in r.json()}
    assert by[iid]["is_overdue"] is True and by[iid]["due_at"]
    assert by[ok]["is_overdue"] is False
    r = await client.get(f"{API}/approval-chains/my-queue", headers=h)
    row = next(x for x in r.json() if x["instance"]["id"] == inst)
    assert row["is_overdue"] is True and row["due_at"]
    assert row["step_instance"]["is_overdue"] is True
