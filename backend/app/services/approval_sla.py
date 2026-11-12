"""Approval SLA + escalation (Roadmap v2 Phase 2, Task 6).

`approvals.sla_hours` (default 48; 0 = off) is the time an approver has to
act. Legacy `ApprovalItem.due_date` is stamped on insert (see the
`before_insert` hook in models/approval.py) and re-stamped when the item
advances to its next step; chain step instances carry `due_at`.

Escalation job: a pending, overdue step is re-routed to the approver's
active manager (never the requester -> SoD), else to the HR role. The due
date is pushed forward one SLA period, so a step escalates at most once per
period. Steps already sitting with a role (nobody to escalate from) and
sla_hours = 0 are left alone.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from sqlalchemy import select

from app.models.system import SystemSetting

logger = logging.getLogger(__name__)

SLA_KEY = "approvals.sla_hours"
SLA_DEFAULT = 48
SLA_MAX = 720
HR_ROLE_NAME = "HR"


def _parse(raw) -> int:
    try:
        v = int(str(raw).strip())
        if 0 <= v <= SLA_MAX:
            return v
    except (TypeError, ValueError):
        pass
    return SLA_DEFAULT


def sla_hours_sync(connection) -> int:
    """Read the SLA from inside a flush hook (sync connection)."""
    raw = connection.execute(
        select(SystemSetting.value).where(SystemSetting.key == SLA_KEY)
    ).scalar_one_or_none()
    return SLA_DEFAULT if raw is None else _parse(raw)


async def sla_hours(db) -> int:
    row = await db.get(SystemSetting, SLA_KEY)
    return SLA_DEFAULT if row is None else _parse(row.value)


def due_from(now: datetime, hours: int) -> Optional[datetime]:
    if not hours:
        return None
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now + timedelta(hours=hours)


def as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def is_overdue(due: Optional[datetime], now: Optional[datetime] = None) -> bool:
    due = as_utc(due)
    return bool(due and due < (now or datetime.now(timezone.utc)))


async def next_due(db, now: Optional[datetime] = None) -> Optional[datetime]:
    return due_from(now or datetime.now(timezone.utc), await sla_hours(db))


async def _hr_role_id(db, hr_role_id: Optional[int]) -> Optional[int]:
    if hr_role_id is not None:
        return hr_role_id
    from app.models.user import Role
    return (await db.execute(
        select(Role.id).where(Role.name == HR_ROLE_NAME)
    )).scalar_one_or_none()


async def _escalation_target(db, approver_id: int, owner_id: Optional[int],
                             exclude: Iterable[Optional[int]] = ()):
    """Active manager of `approver_id` to escalate to, or None. Never the
    request's real owner (SoD), the approver themself, nor anyone in
    `exclude` (users already holding the step, and the previous approver
    this step was escalated from, which prevents A<->B ping-pong)."""
    from app.models.user import User
    approver = await db.get(User, approver_id)
    mid = getattr(approver, "manager_id", None)
    barred = {owner_id, approver_id, *exclude}
    if not mid or mid in barred:
        return None
    mgr = await db.get(User, mid)
    return mgr if mgr is not None and mgr.is_active else None


async def _notify(db, uid: int, title: str, message: str, rtype: str, rid: str):
    from app.services.notifications_delivery import notify
    try:
        async with db.begin_nested():
            await notify(
                db, user_id=uid, event_type="approval_escalated",
                title=title, message=message, resource_type=rtype,
                resource_id=rid, notif_type="warning",
                context={"title": title, "message": message})
    except Exception:  # pragma: no cover
        logger.warning("escalation notification failed", exc_info=True)


async def escalate_overdue(
    db, now: Optional[datetime] = None, *,
    item_ids: Optional[Iterable[int]] = None,
    instance_ids: Optional[Iterable[int]] = None,
    hr_role_id: Optional[int] = None,
) -> dict:
    """Escalate overdue pending steps. `item_ids` / `instance_ids` scope the
    run (tests); None = everything. Each step is its own transaction."""
    from app.models.approval import ApprovalItem, ApprovalStatus, ApprovalStep
    from app.models.approval_chain import (
        ChainedApprovalInstance, ChainedApprovalStatus,
        ChainedApprovalStepInstance, StepInstanceStatus,
    )
    from app.services.leave_approval import step_approver_ids
    from app.services.self_approval import resolve_approval_owner_id
    from app.models.user import User, user_roles

    now = as_utc(now) if now else datetime.now(timezone.utc)
    hours = await sla_hours(db)
    res = {"legacy": 0, "chain": 0, "skipped": 0, "failed": 0}
    if hours == 0:
        return res
    new_due = due_from(now, hours)
    hr_rid = await _hr_role_id(db, hr_role_id)

    # ---- legacy engine
    q = (select(ApprovalItem.id).where(
        ApprovalItem.status == ApprovalStatus.PENDING,
        ApprovalItem.due_date.is_not(None),
        ApprovalItem.due_date <= now))
    if item_ids is not None:
        q = q.where(ApprovalItem.id.in_(list(item_ids)))
    for iid in (await db.execute(q.order_by(ApprovalItem.id))).scalars().all():
        try:
            item = (await db.execute(
                select(ApprovalItem).where(ApprovalItem.id == iid)
                .with_for_update()
                .execution_options(populate_existing=True))).scalar_one()
            if (item.status != ApprovalStatus.PENDING or item.due_date is None
                    or as_utc(item.due_date) > now):
                continue  # raced
            step = (await db.execute(select(ApprovalStep).where(
                ApprovalStep.approval_item_id == iid,
                ApprovalStep.step_number == item.current_step_number,
                ApprovalStep.status == ApprovalStatus.PENDING,
            ).execution_options(populate_existing=True))).scalars().first()
            if step is None or not step.approver_id:
                res["skipped"] += 1  # role-held: nobody further to escalate to
                await db.rollback()
                continue
            original = step.approver_id
            owner_id = await resolve_approval_owner_id(db, item)
            mgr = await _escalation_target(
                db, original, owner_id, [step.escalated_from_id])
            if mgr is not None:
                step.approver_id = mgr.id
            elif hr_rid is not None:
                step.approver_id = None
                step.role_id = hr_rid
            else:
                res["skipped"] += 1
                await db.rollback()
                continue
            step.escalated_at = now
            step.escalated_from_id = original
            item.due_date = new_due
            await db.flush()
            title = "Approval escalated to you"
            msg = (f"A {item.resource_type} request overdue with another "
                   f"approver now needs your action.")
            for uid in await step_approver_ids(db, step):
                await _notify(db, uid, title, msg, item.resource_type,
                              str(item.resource_id))
            await _notify(
                db, original, "Approval escalated",
                f"Your pending {item.resource_type} approval was overdue and "
                f"has been escalated.", item.resource_type,
                str(item.resource_id))
            if item.requested_by_id:
                await _notify(
                    db, item.requested_by_id, "Your request was escalated",
                    f"Your {item.resource_type} request was overdue and has "
                    f"been escalated to the next approver.",
                    item.resource_type, str(item.resource_id))
            await db.commit()
            res["legacy"] += 1
        except Exception:
            await db.rollback()
            res["failed"] += 1
            logger.error("escalation of approval item %s failed", iid,
                         exc_info=True)

    # ---- chain engine
    cq = (select(ChainedApprovalStepInstance.id)
          .join(ChainedApprovalInstance,
                ChainedApprovalInstance.id
                == ChainedApprovalStepInstance.instance_id)
          .where(
              ChainedApprovalStepInstance.status == StepInstanceStatus.PENDING,
              ChainedApprovalStepInstance.due_at.is_not(None),
              ChainedApprovalStepInstance.due_at <= now,
              ChainedApprovalStepInstance.approver_user_id.is_not(None),
              ChainedApprovalInstance.status == ChainedApprovalStatus.PENDING,
              ChainedApprovalInstance.current_step_order
              == ChainedApprovalStepInstance.step_order))
    if instance_ids is not None:
        cq = cq.where(ChainedApprovalStepInstance.instance_id.in_(
            list(instance_ids)))
    for sid in (await db.execute(
            cq.order_by(ChainedApprovalStepInstance.id))).scalars().all():
        try:
            si = (await db.execute(
                select(ChainedApprovalStepInstance)
                .where(ChainedApprovalStepInstance.id == sid)
                .with_for_update()
                .execution_options(populate_existing=True))).scalar_one()
            if (si.status != StepInstanceStatus.PENDING or si.due_at is None
                    or as_utc(si.due_at) > now or not si.approver_user_id):
                continue
            inst = await db.get(ChainedApprovalInstance, si.instance_id)
            original = si.approver_user_id
            taken = {r.approver_user_id for r in (await db.execute(
                select(ChainedApprovalStepInstance).where(
                    ChainedApprovalStepInstance.instance_id == inst.id,
                    ChainedApprovalStepInstance.step_order
                    == si.step_order))).scalars().all()} - {None}
            barred = taken | {original, si.escalated_from_id, inst.submitter_id}
            target = await _escalation_target(
                db, original, inst.submitter_id, barred)
            target_id = target.id if target is not None else None
            if target_id is None and hr_rid is not None:
                target_id = (await db.execute(
                    select(User.id).join(
                        user_roles, user_roles.c.user_id == User.id)
                    .where(user_roles.c.role_id == hr_rid,
                           User.is_active.is_(True),
                           User.id.not_in(barred - {None}))
                    .order_by(User.id).limit(1)
                )).scalar_one_or_none()
            if target_id is None:
                res["skipped"] += 1
                await db.rollback()
                continue
            si.approver_user_id = target_id
            si.escalated_at = now
            si.escalated_from_id = original
            si.due_at = new_due
            await db.flush()
            rid = str(inst.id)
            await _notify(
                db, target_id, "Approval escalated to you",
                f"A {inst.entity_type} approval overdue with another "
                f"approver now needs your action.",
                "chained_approval_instance", rid)
            await _notify(
                db, original, "Approval escalated",
                f"Your pending {inst.entity_type} approval was overdue and "
                f"has been escalated.", "chained_approval_instance", rid)
            if inst.submitter_id:
                await _notify(
                    db, inst.submitter_id, "Your request was escalated",
                    f"Your {inst.entity_type} request was overdue and has "
                    f"been escalated.", "chained_approval_instance", rid)
            await db.commit()
            res["chain"] += 1
        except Exception:
            await db.rollback()
            res["failed"] += 1
            logger.error("escalation of chain step %s failed", sid,
                         exc_info=True)
    return res
