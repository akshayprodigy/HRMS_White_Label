"""Deleting an account or a department must not silently cascade DOP data.
Services never commit; callers run inside retry_on_lock after taking the
reporting lock (see assignments.py)."""
from sqlalchemy import or_, select

from app.models.department import Department
from app.models.dop import (
    ActingAssignment, ManagerAssignment, Post, PostHolder,
)
from app.models.user import User
from app.services.dop.assignments import _matching, audit, snapshot
from app.services.dop.world import load_people
from app.services.org_time import local_today


def _open(model, today):
    return or_(model.ends_on.is_(None), model.ends_on >= today)


async def user_blockers(db, user_id) -> list:
    """Messages (one per kind of tie) naming what to reassign first. Live or
    future rows only: ended history never blocks."""
    today = await local_today(db)
    out: list = []
    people = await load_people(db)
    dnames = dict((await db.execute(
        select(Department.id, Department.name))).all())
    rows = (await db.execute(select(ManagerAssignment).where(
        ManagerAssignment.manager_user_id == user_id,
        ManagerAssignment.cancelled_at.is_(None),
        _open(ManagerAssignment, today)))).scalars().all()
    if rows:
        who: set = set()
        for a in rows:
            who |= set(_matching(people, a, dnames.get(a.scope_department_id)))
        who.discard(user_id)
        n = len(who)
        out.append({"type": "dop_manager",
                    "message": f"manager of {n} employee"
                               f"{'' if n == 1 else 's'} (assignment)"})
    held = (await db.execute(
        select(Post.title).join(PostHolder, PostHolder.post_id == Post.id)
        .where(PostHolder.user_id == user_id,
               _open(PostHolder, today)))).scalars().all()
    if held:
        out.append({"type": "dop_post",
                    "message": "holds post " + ", ".join(sorted(set(held)))})
    acts = (await db.execute(select(ActingAssignment).where(
        or_(ActingAssignment.acting_user_id == user_id,
            ActingAssignment.covers_user_id == user_id),
        ActingAssignment.revoked_at.is_(None),
        _open(ActingAssignment, today)))).scalars().all()
    names = dict((await db.execute(select(User.id, User.full_name))).all())
    titles = dict((await db.execute(select(Post.id, Post.title))).all())
    parts = []
    for c in acts:
        if c.acting_user_id == user_id:
            what = (names.get(c.covers_user_id) if c.covers_user_id
                    else titles.get(c.covers_post_id))
            parts.append(f"acting for {what}")
        else:
            parts.append(f"covered by {names.get(c.acting_user_id)}")
    if parts:
        out.append({"type": "dop_acting",
                    "message": ", ".join(sorted(set(parts)))})
    return out


async def audit_user_rows_removed(db, actor_id, user_id) -> None:
    """The user's own scope rows go with the account (FK cascade): record
    them in one audit row first."""
    rows = (await db.execute(select(ManagerAssignment).where(
        ManagerAssignment.scope_user_id == user_id))).scalars().all()
    if rows:
        audit(db, actor_id, "dop.assignment.removed", "user", user_id,
              {"reason": "employee deleted",
               "rows": [{"id": a.id, **snapshot(a)} for a in rows]})


async def department_blockers(db, dept_id) -> list:
    today = await local_today(db)
    out: list = []
    n = len((await db.execute(select(ManagerAssignment.id).where(
        ManagerAssignment.scope_department_id == dept_id,
        ManagerAssignment.cancelled_at.is_(None),
        _open(ManagerAssignment, today)))).all())
    if n:
        out.append(f"{n} manager assignment(s) cover this department "
                   "(end them first)")
    titles = (await db.execute(select(Post.title).where(
        Post.heads_department_id == dept_id))).scalars().all()
    if titles:
        out.append("headed by post " + ", ".join(sorted(titles))
                   + " (change the post first)")
    return out


async def audit_department_rows_removed(db, actor_id, dept_id) -> None:
    rows = (await db.execute(select(ManagerAssignment).where(
        ManagerAssignment.scope_department_id == dept_id))).scalars().all()
    if rows:
        audit(db, actor_id, "dop.assignment.removed", "department", dept_id,
              {"reason": "department deleted",
               "rows": [{"id": a.id, **snapshot(a)} for a in rows]})
