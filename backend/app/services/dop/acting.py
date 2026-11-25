"""Acting covers. Never commits (see the transaction contract in
assignments.py; callers use a fresh transaction inside retry_on_lock).
Every write locks the covered user or post row first, which serialises
covers of one target. Acting covers do not touch User.manager_id."""
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select

from app.models.dop import ActingAssignment, Post
from app.models.user import User
from app.services.dop import subdomains as S
from app.services.dop.assignments import (
    _active_user, audit, dates_overlap, subs_clash,
)
from app.services.org_time import local_today


def snapshot(c) -> dict:
    return {"covers_user_id": c.covers_user_id,
            "covers_post_id": c.covers_post_id,
            "acting_user_id": c.acting_user_id,
            "subdomains": list(c.subdomains or []),
            "starts_on": c.starts_on.isoformat(),
            "ends_on": c.ends_on.isoformat() if c.ends_on else None,
            "original_can_act": c.original_can_act,
            "only_when_on_leave": c.only_when_on_leave}


async def _lock_target(db, user_id, post_id) -> bool:
    """Lock the covered row; returns whether it is active."""
    if user_id is not None:
        row = (await db.execute(select(User.id, User.is_active).where(
            User.id == user_id).with_for_update())).first()
    else:
        row = (await db.execute(select(Post.id, Post.is_active).where(
            Post.id == post_id).with_for_update())).first()
    if row is None:
        raise HTTPException(422, "Covered person or post not found")
    return bool(row[1])


async def _siblings(db, user_id, post_id, skip=0):
    return (await db.execute(
        select(ActingAssignment).where(
            ActingAssignment.covers_user_id.is_(None) if user_id is None
            else ActingAssignment.covers_user_id == user_id,
            ActingAssignment.covers_post_id.is_(None) if post_id is None
            else ActingAssignment.covers_post_id == post_id,
            ActingAssignment.revoked_at.is_(None),
            ActingAssignment.id != skip)
        .order_by(ActingAssignment.id).with_for_update()
        .execution_options(populate_existing=True))).scalars().all()


def _check_overlap(rows, subs, starts_on, ends_on):
    for r in rows:
        if subs_clash(r.subdomains, subs) and dates_overlap(
                r.starts_on, r.ends_on, starts_on, ends_on):
            raise HTTPException(409, f"Overlaps acting cover #{r.id}")


def _check_reason(reason):
    if reason is not None and len(reason) > 255:
        raise HTTPException(422, "Reason is longer than 255")


async def create(db, *, actor_id, acting_user_id, starts_on, ends_on=None,
                 covers_user_id=None, covers_post_id=None, subdomains=(),
                 original_can_act=False, only_when_on_leave=False,
                 reason=None) -> ActingAssignment:
    if (covers_user_id is None) == (covers_post_id is None):
        raise HTTPException(422, "Choose the person or the post to cover")
    if covers_user_id == acting_user_id:
        raise HTTPException(422, "A person cannot act for themselves")
    if ends_on is not None and ends_on < starts_on:
        raise HTTPException(422, "End date is before the start date")
    _check_reason(reason)
    try:
        subs = sorted(S.validate(subdomains))
    except ValueError as e:
        raise HTTPException(422, str(e))
    active = await _lock_target(db, covers_user_id, covers_post_id)
    if not active:
        raise HTTPException(
            422, "The covered " + ("person" if covers_user_id else "post")
            + " is inactive")
    await _active_user(db, acting_user_id, "Acting person")
    if ends_on is not None and ends_on < await local_today(db):
        raise HTTPException(422, "The cover already ended")
    _check_overlap(await _siblings(db, covers_user_id, covers_post_id), subs,
                   starts_on, ends_on)
    c = ActingAssignment(
        covers_user_id=covers_user_id, covers_post_id=covers_post_id,
        acting_user_id=acting_user_id, subdomains=subs, starts_on=starts_on,
        ends_on=ends_on, original_can_act=original_can_act,
        only_when_on_leave=only_when_on_leave, reason=reason,
        created_by_id=actor_id)
    db.add(c)
    await db.flush()
    audit(db, actor_id, "dop.acting.create", "acting_assignment", c.id,
          snapshot(c))
    return c


async def _locked(db, cover_id) -> ActingAssignment:
    row = (await db.execute(select(
        ActingAssignment.covers_user_id, ActingAssignment.covers_post_id)
        .where(ActingAssignment.id == cover_id))).first()
    if row is None:
        raise HTTPException(404, "Acting cover not found")
    await _lock_target(db, row[0], row[1])
    c = (await db.execute(select(ActingAssignment).where(
        ActingAssignment.id == cover_id).with_for_update()
        .execution_options(populate_existing=True))).scalars().one()
    if c.revoked_at is not None:
        raise HTTPException(409, "Acting cover was already ended")
    return c


async def update(db, *, actor_id, cover_id, **changes) -> ActingAssignment:
    """Only original_can_act, ends_on and reason can change."""
    c = await _locked(db, cover_id)
    before = snapshot(c)
    changes = {k: v for k, v in changes.items()
               if k in ("original_can_act", "ends_on", "reason")}
    if "reason" in changes:
        _check_reason(changes["reason"])
    if "ends_on" in changes:
        e = changes["ends_on"]
        if e is not None and e < c.starts_on:
            raise HTTPException(422, "End date is before the start date")
        _check_overlap(await _siblings(db, c.covers_user_id,
                                       c.covers_post_id, c.id),
                       c.subdomains, c.starts_on, e)
    for k, v in changes.items():
        setattr(c, k, v)
    await db.flush()
    audit(db, actor_id, "dop.acting.update", "acting_assignment", c.id,
          {"before": before, "after": snapshot(c)})
    return c


async def revoke(db, *, actor_id, cover_id) -> ActingAssignment:
    c = await _locked(db, cover_id)
    c.revoked_at = datetime.now(timezone.utc)
    c.revoked_by_id = actor_id
    await db.flush()
    audit(db, actor_id, "dop.acting.revoke", "acting_assignment", c.id,
          snapshot(c))
    return c
