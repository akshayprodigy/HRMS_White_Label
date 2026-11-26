"""Posts and their holders. Never commits (see the transaction contract in
assignments.py). Lock order: reporting kind, post row, user rows. Callers
run in a fresh transaction inside retry_on_lock."""
from contextlib import asynccontextmanager
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

from app.models.audit import AuditLog
from app.models.department import Department
from app.models.dop import ActingAssignment, ManagerAssignment, Post, PostHolder
from app.services.dop.assignments import (
    _active_user, audit, dates_overlap, lock_reporting,
    loop_baseline, post_governed_users, sync_post_users,
)
from app.services.org_time import local_today

FIELDS = ("code", "title", "department_id", "location", "parent_post_id",
          "heads_department_id", "is_active")
MAXLEN = {"code": 40, "title": 120, "location": 100}


def snapshot(p) -> dict:
    return {k: getattr(p, k) for k in FIELDS}


def _holder_snapshot(h) -> dict:
    return {"holder_id": h.id, "user_id": h.user_id,
            "starts_on": h.starts_on.isoformat(),
            "ends_on": h.ends_on.isoformat() if h.ends_on else None}


def _clean(data: dict) -> dict:
    out = dict(data)
    for f in ("code", "title"):
        if f in out:
            v = (out[f] or "").strip() if isinstance(out[f], str) else ""
            if not v:
                raise HTTPException(422, f"{f.capitalize()} is required")
            out[f] = v
    if "location" in out:
        out["location"] = (out["location"] or "").strip() or None
    for f, n in MAXLEN.items():
        if out.get(f) and len(out[f]) > n:
            raise HTTPException(422, f"{f.capitalize()} is longer than {n}")
    if "is_active" in out and not isinstance(out["is_active"], bool):
        raise HTTPException(422, "is_active must be true or false")
    return out


async def _lock(db, post_id) -> Post:
    p = (await db.execute(select(Post).where(Post.id == post_id)
         .with_for_update().execution_options(populate_existing=True)
         )).scalars().first()
    if p is None:
        raise HTTPException(404, "Post not found")
    return p


async def _validate(db, data, post_id=None):
    if "code" in data and (await db.execute(select(Post.id).where(
            Post.code == data["code"], Post.id != (post_id or 0))
            )).first():
        raise HTTPException(409, "Post code already exists")
    for f in ("department_id", "heads_department_id"):
        if data.get(f) and await db.get(Department, data[f]) is None:
            raise HTTPException(422, "Department not found")
    if data.get("heads_department_id") and (await db.execute(
            select(Post.id).where(
                Post.heads_department_id == data["heads_department_id"],
                Post.id != (post_id or 0)))).first():
        raise HTTPException(409, "That department already has a head post")
    cur, seen = data.get("parent_post_id"), {post_id}
    while cur is not None:
        if cur in seen:
            raise HTTPException(422, "Posts cannot report in a loop")
        seen.add(cur)
        row = (await db.execute(select(Post.id, Post.parent_post_id).where(
            Post.id == cur))).first()
        if row is None:
            raise HTTPException(422, "Parent post not found")
        cur = row.parent_post_id


@asynccontextmanager
async def _unique_guard(db):
    """Writes inside run in a savepoint: a unique-key race (post code, head
    department) becomes a 409 and the surrounding transaction stays usable."""
    try:
        async with db.begin_nested():
            yield
            await db.flush()
    except IntegrityError as e:
        code = e.orig.args[0] if getattr(e.orig, "args", None) else None
        if code == 1062:
            raise HTTPException(
                409, "Post code or head department already used")
        if code == 1452:
            raise HTTPException(
                422, "Department or parent post no longer exists")
        raise


async def create(db, *, actor_id, code, title, **kw) -> Post:
    data = _clean({"code": code, "title": title,
                   **{k: v for k, v in kw.items() if k in FIELDS}})
    await _validate(db, data)
    p = Post(**data)
    async with _unique_guard(db):
        db.add(p)
    audit(db, actor_id, "dop.post.create", "post", p.id, snapshot(p))
    return p


async def update(db, *, actor_id, post_id, changes) -> Post:
    await lock_reporting(db)           # a post edit can change managers
    p = await _lock(db, post_id)
    changes = _clean({k: v for k, v in changes.items() if k in FIELDS})
    await _validate(db, changes, post_id)
    today = await local_today(db)
    deactivating = changes.get("is_active") is False and p.is_active
    reactivating = changes.get("is_active") is True and not p.is_active
    if deactivating:
        if (await db.execute(select(ManagerAssignment.id).where(
                ManagerAssignment.manager_post_id == post_id,
                ManagerAssignment.cancelled_at.is_(None),
                or_(ManagerAssignment.ends_on.is_(None),
                    ManagerAssignment.ends_on >= today)))).first():
            raise HTTPException(
                409, "Post is used as a manager: end those assignments first")
        if (await db.execute(select(ActingAssignment.id).where(
                ActingAssignment.covers_post_id == post_id,
                ActingAssignment.revoked_at.is_(None),
                or_(ActingAssignment.ends_on.is_(None),
                    ActingAssignment.ends_on >= today)))).first():
            raise HTTPException(
                409, "Post has an acting cover: revoke it first")
    base = (await loop_baseline(db, [today])
            if reactivating and await post_governed_users(db, post_id)
            else None)
    before = {k: getattr(p, k) for k in changes}
    async with _unique_guard(db):
        for k, v in changes.items():
            setattr(p, k, v)
    audit(db, actor_id, "dop.post.update", "post", p.id,
          {"before": before, "after": changes})
    if reactivating:
        await sync_post_users(db, post_id, base, actor_id=actor_id)
    return p


async def history(db, post_id) -> list:
    return list((await db.execute(
        select(PostHolder).where(PostHolder.post_id == post_id)
        .order_by(PostHolder.starts_on, PostHolder.id)
        .execution_options(populate_existing=True))).scalars().all())


async def _baseline(db, post_id, today, *extra):
    if not await post_governed_users(db, post_id):
        return None
    dates = [today] + sorted({d for d in extra if d and d > today})
    return await loop_baseline(db, dates)


async def assign_holder(db, *, actor_id, post_id, user_id, starts_on,
                        ends_on=None) -> PostHolder:
    """Start a holder. The open-ended current holder ends the day before
    (only for an open-ended new holder; temporary cover is an acting cover);
    a start in the future leaves today's mirror alone."""
    if ends_on is not None and ends_on < starts_on:
        raise HTTPException(422, "End date is before the start date")
    await lock_reporting(db)
    p = await _lock(db, post_id)
    if not p.is_active:
        raise HTTPException(422, "Post is inactive")
    await _active_user(db, user_id, "Holder")
    today = await local_today(db)
    to_end = []
    for h in await history(db, post_id):
        if not dates_overlap(h.starts_on, h.ends_on, starts_on, ends_on):
            continue
        if h.ends_on is None and h.starts_on < starts_on:
            to_end.append(h)
        elif h.starts_on == starts_on:
            raise HTTPException(
                409, "A holder starts that same day: " + (
                    "remove them first" if h.starts_on >= today
                    else "end them first"))
        else:
            raise HTTPException(409, "Someone already holds the post then")
    if to_end and ends_on is not None:
        raise HTTPException(
            409, "Use an acting cover for temporary cover, or end the "
                 "current holder first")
    if to_end and starts_on < today:
        raise HTTPException(422, "A handover cannot start in the past")
    base = await _baseline(db, post_id, today, starts_on,
                           ends_on + timedelta(days=1) if ends_on else None)
    before = [(h, _holder_snapshot(h)) for h in to_end]
    for h in to_end:
        h.ends_on = starts_on - timedelta(days=1)
    h = PostHolder(post_id=post_id, user_id=user_id, starts_on=starts_on,
                   ends_on=ends_on, created_by_id=actor_id)
    db.add(h)
    await db.flush()
    audit(db, actor_id, "dop.post.holder", "post", post_id,
          _holder_snapshot(h))
    for old, snap in before:
        audit(db, actor_id, "dop.post.holder_end", "post", post_id,
              {"before": snap, "after": _holder_snapshot(old),
               "truncated_by": h.id})
    await sync_post_users(db, post_id, base, actor_id=actor_id)
    return h


async def _holder(db, post_id, holder_id) -> PostHolder:
    h = next((x for x in await history(db, post_id) if x.id == holder_id), None)
    if h is None:
        raise HTTPException(404, "Holder not found")
    return h


async def end_holder(db, *, actor_id, post_id, holder_id, ends_on):
    await lock_reporting(db)
    await _lock(db, post_id)
    h = await _holder(db, post_id, holder_id)
    if ends_on < h.starts_on or (h.ends_on and ends_on > h.ends_on):
        raise HTTPException(
            422, "End date is outside the holding period (to undo a holder "
                 "that has not started, remove it)")
    today = await local_today(db)
    before = _holder_snapshot(h)
    base = await _baseline(db, post_id, today)
    h.ends_on = ends_on
    await db.flush()
    audit(db, actor_id, "dop.post.holder_end", "post", post_id,
          {"before": before, "ends_on": ends_on.isoformat()})
    await sync_post_users(db, post_id, base, actor_id=actor_id)
    return h


async def _truncated_by(db, post_id, prev_id, holder_id) -> bool:
    """Does the audit trail say holder `prev_id` was ended by `holder_id`'s
    handover?"""
    rows = (await db.execute(select(AuditLog.details).where(
        AuditLog.action == "dop.post.holder_end",
        AuditLog.resource_type == "post",
        AuditLog.resource_id == str(post_id)))).scalars().all()
    return any(isinstance(d, dict) and d.get("truncated_by") == holder_id
               and (d.get("before") or {}).get("holder_id") == prev_id
               for d in rows)


async def remove_holder(db, *, actor_id, post_id, holder_id,
                        reopen_previous=False) -> None:
    """Delete a wrongly entered holder that starts today or later. By
    default the holder it replaced stays ended; with reopen_previous that
    holder is reopened (until the next later holder, else open-ended) when
    this holder's handover is what ended them."""
    await lock_reporting(db)
    p = await _lock(db, post_id)
    hist = await history(db, post_id)
    h = next((x for x in hist if x.id == holder_id), None)
    if h is None:
        raise HTTPException(404, "Holder not found")
    today = await local_today(db)
    if h.starts_on < today:
        raise HTTPException(
            422, "That holder already started: end them instead")
    prev = None
    if reopen_previous:
        day = h.starts_on - timedelta(days=1)
        prev = next((x for x in hist if x.id != h.id and x.ends_on == day),
                    None)
        if prev is None or not await _truncated_by(
                db, post_id, prev.id, h.id):
            raise HTTPException(
                409, "The previous holder was not ended by this handover")
        if not p.is_active:
            raise HTTPException(422, "Post is inactive")
        await _active_user(db, prev.user_id, "Previous holder")
    snap = _holder_snapshot(h)
    base = await _baseline(db, post_id, today, h.starts_on)
    await db.delete(h)
    await db.flush()
    audit(db, actor_id, "dop.post.holder_remove", "post", post_id, snap)
    if prev is not None:
        before = _holder_snapshot(prev)
        later = [x.starts_on for x in hist
                 if x.id not in (h.id, prev.id) and x.starts_on > h.starts_on]
        prev.ends_on = (min(later) - timedelta(days=1)) if later else None
        await db.flush()
        audit(db, actor_id, "dop.post.holder_end", "post", post_id,
              {"before": before, "after": _holder_snapshot(prev),
               "reopened_by_removal_of": holder_id})
    await sync_post_users(db, post_id, base, actor_id=actor_id)
