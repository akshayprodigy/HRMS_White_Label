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


# ---------------------------------------------------------------- review fixes
from sqlalchemy import insert, update  # noqa: E402

from app.core.security import get_password_hash  # noqa: E402
from app.models.approval_chain import ChainedApprovalInstance  # noqa: E402
from app.models.leave import LeaveRequest, LeaveStatus  # noqa: E402
from app.models.user import User, user_roles  # noqa: E402


async def _mk_hr2(world):
    async with SessionLocal() as db:
        u = User(email=f"aw_hr2_{world['sfx']}@t.com", full_name="AW hr2",
                 hashed_password=get_password_hash("x"), is_active=True)
        db.add(u)
        await db.flush()
        await db.execute(insert(user_roles).values(
            user_id=u.id, role_id=world["ids"]["hr_role"]))
        await db.commit()
        return u.id


async def test_chain_hr_pick_excludes_overdue_original(world):
    ids = world["ids"]
    now = _now()
    hr2 = await _mk_hr2(world)
    assert ids["hr"] < hr2   # original is the lowest-id HR user
    inst, sid = await mk_chain(world, "hr", due_at=now - timedelta(hours=2))
    async with SessionLocal() as db:
        r = await escalate_overdue(db, now, instance_ids=[inst],
                                   hr_role_id=ids["hr_role"])
    assert r["chain"] == 1
    async with SessionLocal() as db:
        si = await db.get(ChainedApprovalStepInstance, sid)
    assert si.approver_user_id == hr2 and si.escalated_from_id == ids["hr"]


async def test_chain_manager_already_at_step_falls_to_hr(world):
    ids = world["ids"]
    now = _now()
    inst, sid = await mk_chain(world, "apr", due_at=now - timedelta(hours=2))
    async with SessionLocal() as db:  # parallel/all: mgr also holds a row
        si = await db.get(ChainedApprovalStepInstance, sid)
        si.mode, si.parallel_rule = "parallel", "all"
        db.add(ChainedApprovalStepInstance(
            instance_id=inst, step_order=1, approver_type="specific_user",
            approver_user_id=ids["mgr"], mode="parallel", parallel_rule="all",
            status="approved"))
        await db.commit()
    async with SessionLocal() as db:
        await escalate_overdue(db, now, instance_ids=[inst],
                               hr_role_id=ids["hr_role"])
    async with SessionLocal() as db:
        rows = (await db.execute(select(ChainedApprovalStepInstance).where(
            ChainedApprovalStepInstance.instance_id == inst))).scalars().all()
    held = sorted(r.approver_user_id for r in rows)
    assert held == sorted([ids["mgr"], ids["hr"]])   # no duplicate holder
    assert len(rows) == 2
    from app.services.approval_engine import advance_state
    mine = next(r for r in rows if r.approver_user_id == ids["hr"])
    d = [{"step_order": r.step_order, "status": r.status if r is not mine
          else "approved", "mode": r.mode, "parallel_rule": r.parallel_rule,
          "approver_user_id": r.approver_user_id} for r in rows]
    out = advance_state(all_step_instances=d, acted_step_order=1,
                        action="approve")
    assert out.finalize and out.next_status == "approved"


async def test_legacy_sod_uses_real_owner_not_null_requester(world):
    ids = world["ids"]
    now = _now()
    # requested_by_id NULL; the leave's employee is apr's manager (mgr)
    async with SessionLocal() as db:
        lv = LeaveRequest(
            employee_id=ids["mgr"], leave_type_id=ids["lt"],
            start_date=now.date(), end_date=now.date(), reason="t",
            status=LeaveStatus.SUBMITTED, created_by_user_id=ids["mgr"])
        db.add(lv)
        await db.flush()
        item = ApprovalItem(resource_type="leave_request",
                            resource_id=str(lv.id), status="pending",
                            current_step_number=1, requested_by_id=None,
                            due_date=now - timedelta(hours=1))
        db.add(item)
        await db.flush()
        db.add(ApprovalStep(approval_item_id=item.id, step_number=1,
                            approver_id=ids["apr"], status="pending"))
        await db.commit()
        iid = item.id
    async with SessionLocal() as db:
        await escalate_overdue(db, now, item_ids=[iid],
                               hr_role_id=ids["hr_role"])
    _it, st = await _item(iid)
    assert st.approver_id is None and st.role_id == ids["hr_role"]


async def test_no_ping_pong_legacy_and_chain(world):
    ids = world["ids"]
    now = _now()
    async with SessionLocal() as db:   # apr <-> mgr are each other's manager
        await db.execute(update(User).where(User.id == ids["mgr"]).values(
            manager_id=ids["apr"]))
        await db.commit()
    iid, _ = await mk_item(world, "apr", due=now - timedelta(hours=1))
    inst, sid = await mk_chain(world, "apr", due_at=now - timedelta(hours=1))
    async with SessionLocal() as db:
        await escalate_overdue(db, now, item_ids=[iid], instance_ids=[inst],
                               hr_role_id=ids["hr_role"])
    _it, st = await _item(iid)
    assert st.approver_id == ids["mgr"]
    later = now + timedelta(hours=50)
    async with SessionLocal() as db:
        await escalate_overdue(db, later, item_ids=[iid], instance_ids=[inst],
                               hr_role_id=ids["hr_role"])
    _it, st = await _item(iid)
    assert st.approver_id is None and st.role_id == ids["hr_role"]
    async with SessionLocal() as db:
        si = await db.get(ChainedApprovalStepInstance, sid)
    assert si.approver_user_id == ids["hr"]     # not bounced back to apr
    assert si.escalated_from_id == ids["mgr"]


async def test_sla_zero_leaves_due_date_null_and_hook_note(world):
    prev = await get_sla()
    try:
        await set_sla(0)
        iid, _ = await mk_item(world, "apr")
        it, _s = await _item(iid)
        assert it.due_date is None
    finally:
        await set_sla(prev)
