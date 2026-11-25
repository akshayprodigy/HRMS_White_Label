"""Manager assignment writes. Never commits. All writes of one kind are
serialised by locking its manager_kind row (cheap: admin-only, rare)."""
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select

from app.models.audit import AuditLog
from app.models.department import Department
from app.models.dop import ManagerAssignment, ManagerKind, Post
from app.models.user import User
from app.services.dop import resolver as R
from app.services.dop import subdomains as S
from app.services.dop.world import load_people, load_world
from app.services.org_time import local_today

SCOPES = ("user", "department", "location", "company")


def audit(db, actor_id, action, rtype, rid, details):
    db.add(AuditLog(user_id=actor_id, action=action, resource_type=rtype,
                    resource_id=str(rid), details=details))


def snapshot(a: ManagerAssignment) -> dict:
    return {
        "kind_id": a.manager_kind_id, "scope_type": a.scope_type,
        "scope_user_id": a.scope_user_id,
        "scope_department_id": a.scope_department_id,
        "scope_location": a.scope_location,
        "manager_user_id": a.manager_user_id,
        "manager_post_id": a.manager_post_id,
        "subdomains": list(a.subdomains or []),
        "starts_on": a.starts_on.isoformat(),
        "ends_on": a.ends_on.isoformat() if a.ends_on else None}


def dates_overlap(s1, e1, s2, e2) -> bool:
    return (e2 is None or s1 <= e2) and (e1 is None or s2 <= e1)


def subs_clash(a, b) -> bool:
    """Two 'all' rows clash, two named rows clash when they share one;
    'all' and named coexist (named wins)."""
    a, b = set(a or ()), set(b or ())
    return (not a and not b) or bool(a & b)


async def _lock_kind(db, kind_id) -> ManagerKind:
    kind = (await db.execute(
        select(ManagerKind).where(ManagerKind.id == kind_id)
        .with_for_update().execution_options(populate_existing=True)
    )).scalars().first()
    if kind is None or not kind.is_active:
        raise HTTPException(422, "Unknown or inactive manager kind")
    return kind


async def _active_user(db, uid, what):
    u = (await db.execute(select(User.id, User.is_active).where(
        User.id == uid))).first()
    if u is None or not u.is_active:
        raise HTTPException(422, f"{what} not found or inactive")


async def _same_scope(db, kind_id, scope_type, user_id, dept_id, loc):
    rows = (await db.execute(
        select(ManagerAssignment).where(
            ManagerAssignment.manager_kind_id == kind_id,
            ManagerAssignment.scope_type == scope_type,
            ManagerAssignment.cancelled_at.is_(None))
        # locking read: HR edits reach here mid-transaction, and a plain read
        # would use their older snapshot (writers hold the kind row, so no
        # gap-lock deadlock between them)
        .with_for_update()
        .execution_options(populate_existing=True))).scalars().all()
    return [r for r in rows
            if r.scope_user_id == user_id and r.scope_department_id == dept_id
            and R.norm(r.scope_location) == R.norm(loc)]


async def _assert_no_cycle(db, user_id, manager_id):
    seen, cur = {user_id}, manager_id
    while cur is not None:
        if cur in seen:
            raise HTTPException(
                422, "This would make a reporting loop (the manager reports "
                     "to this employee)")
        seen.add(cur)
        cur = (await db.execute(select(User.manager_id).where(
            User.id == cur))).scalar_one_or_none()


async def create(db, *, actor_id, kind_id, scope_type, scope_user_id=None,
                 scope_department_id=None, scope_location=None,
                 manager_user_id=None, manager_post_id=None, subdomains=(),
                 starts_on, ends_on=None, note=None) -> ManagerAssignment:
    if scope_type not in SCOPES:
        raise HTTPException(422, "Unknown scope")
    scope_location = (scope_location or "").strip() or None
    given = {"user": scope_user_id, "department": scope_department_id,
             "location": scope_location}
    if [k for k, v in given.items() if v is not None] != (
            [] if scope_type == "company" else [scope_type]):
        raise HTTPException(422, f"Scope '{scope_type}' needs exactly its own target")
    if (manager_user_id is None) == (manager_post_id is None):
        raise HTTPException(422, "Choose a person or a post as the manager")
    if ends_on is not None and ends_on < starts_on:
        raise HTTPException(422, "End date is before the start date")
    try:
        subs = sorted(S.validate(subdomains))
    except ValueError as e:
        raise HTTPException(422, str(e))
    kind = await _lock_kind(db, kind_id)
    if scope_user_id is not None:
        await _active_user(db, scope_user_id, "Employee")
        if scope_user_id == manager_user_id:
            raise HTTPException(422, "An employee cannot be their own manager")
    if scope_department_id is not None and (
            await db.get(Department, scope_department_id)) is None:
        raise HTTPException(422, "Department not found")
    if manager_user_id is not None:
        await _active_user(db, manager_user_id, "Manager")
    else:
        post = await db.get(Post, manager_post_id)
        if post is None or not post.is_active:
            raise HTTPException(422, "Post not found or inactive")
    if kind.code == "reporting" and scope_type == "user" and manager_user_id:
        await _assert_no_cycle(db, scope_user_id, manager_user_id)
    for r in await _same_scope(db, kind_id, scope_type, scope_user_id,
                               scope_department_id, scope_location):
        if subs_clash(r.subdomains, subs) and dates_overlap(
                r.starts_on, r.ends_on, starts_on, ends_on):
            raise HTTPException(
                409, f"Overlaps assignment #{r.id}: end that one first")
    a = ManagerAssignment(
        manager_kind_id=kind_id, scope_type=scope_type,
        scope_user_id=scope_user_id, scope_department_id=scope_department_id,
        scope_location=scope_location, manager_user_id=manager_user_id,
        manager_post_id=manager_post_id, subdomains=subs,
        starts_on=starts_on, ends_on=ends_on, note=note,
        created_by_id=actor_id)
    db.add(a)
    await db.flush()
    audit(db, actor_id, "dop.assignment.create", "manager_assignment", a.id,
          snapshot(a))
    if kind.code == "reporting":
        await sync_mirror(db, await affected_users(db, a))
    return a


async def end(db, *, actor_id, assignment_id, ends_on) -> ManagerAssignment:
    kind_id = (await db.execute(select(ManagerAssignment.manager_kind_id)
               .where(ManagerAssignment.id == assignment_id))
               ).scalar_one_or_none()
    if kind_id is None:
        raise HTTPException(404, "Assignment not found")
    kind = (await db.execute(select(ManagerKind).where(
        ManagerKind.id == kind_id).with_for_update())).scalars().one()
    a = (await db.execute(
        select(ManagerAssignment).where(ManagerAssignment.id == assignment_id)
        .with_for_update().execution_options(populate_existing=True)
    )).scalars().one()
    if a.cancelled_at is not None:
        raise HTTPException(409, "Assignment was already removed")
    if a.ends_on is not None and ends_on > a.ends_on:
        raise HTTPException(
            422, "It already ends earlier: create a new assignment instead")
    before = snapshot(a)
    if ends_on < a.starts_on:
        a.cancelled_at = datetime.now(timezone.utc)
    else:
        a.ends_on = ends_on
    await db.flush()
    audit(db, actor_id, "dop.assignment.end", "manager_assignment", a.id,
          {"before": before, "ends_on": ends_on.isoformat(),
           "cancelled": a.cancelled_at is not None})
    if kind.code == "reporting":
        await sync_mirror(db, await affected_users(db, a))
    return a


def _matching(people: dict, a, dept_name) -> list:
    """Users a scope matches, by the resolver's own rules (the same Person
    data, whitespace/case-normalised)."""
    if a.scope_type == "user":
        return [a.scope_user_id]
    if a.scope_type == "company":
        return sorted(people)
    if a.scope_type == "department":
        want, field = R.norm(dept_name), "department"
    else:
        want, field = R.norm(a.scope_location), "location"
    return sorted(i for i, p in people.items()
                  if want and R.norm(getattr(p, field)) == want)


async def affected_users(db, a) -> list:
    dept = None
    if a.scope_type == "department":
        dept = (await db.execute(select(Department.name).where(
            Department.id == a.scope_department_id))).scalar_one_or_none()
    return _matching(await load_people(db), a, dept)


async def set_reporting_manager(db, *, actor_id, user_id, manager_id) -> None:
    """HR/admin edits of one employee's manager: end the current user-scoped
    all-subdomain reporting row and start a new one today."""
    today = await local_today(db)
    kind_id = (await db.execute(select(ManagerKind.id).where(
        ManagerKind.code == "reporting"))).scalar_one()
    await _lock_kind(db, kind_id)
    for r in await _same_scope(db, kind_id, "user", user_id, None, None):
        if r.subdomains or (r.ends_on is not None and r.ends_on < today):
            continue
        if r.manager_user_id == manager_id and manager_id is not None \
                and r.starts_on <= today and r.ends_on is None:
            await sync_mirror(db, [user_id])
            return
        await end(db, actor_id=actor_id, assignment_id=r.id,
                  ends_on=today - timedelta(days=1))
    if manager_id is not None:
        await create(db, actor_id=actor_id, kind_id=kind_id,
                     scope_type="user", scope_user_id=user_id,
                     manager_user_id=manager_id, starts_on=today)
    else:
        await sync_mirror(db, [user_id])


async def sync_mirror(db, user_ids=None) -> int:
    """Set User.manager_id to the base reporting manager (no acting cover).
    Returns how many users changed. Only users the assignments govern are
    touched: a manager set by a seed or script is never cleared."""
    await db.flush()
    today = await local_today(db)
    # latest committed data: callers hold the kind lock, so nothing moves
    w = await load_world(db, today, fresh=True)
    q = (select(User).order_by(User.id).with_for_update()
         .execution_options(populate_existing=True))
    if user_ids is not None:
        q = q.where(User.id.in_(list(user_ids)))
    # A user is governed once any reporting assignment that has started (or
    # was cancelled the day it started) applied to them. A future-dated row
    # has not governed anyone yet.
    governed: set = set()
    rows = (await db.execute(
        select(ManagerAssignment).join(
            ManagerKind, ManagerKind.id == ManagerAssignment.manager_kind_id)
        .where(ManagerKind.code == "reporting",
               ManagerAssignment.starts_on <= today)
        .with_for_update().execution_options(populate_existing=True)
    )).scalars().all()
    dnames = dict((await db.execute(
        select(Department.id, Department.name))).all())
    for row in rows:
        governed |= set(_matching(
            w.people, row, dnames.get(row.scope_department_id)))
    changed = 0
    for u in (await db.execute(q)).scalars().all():
        a = R.find_assignment(w, "reporting", u.id, "", today)
        if a is None and u.id not in governed:
            continue
        mgr = None
        if a is not None:
            mgr = (R.holder_of(w, a.manager_post_id, today)
                   if a.manager_post_id else a.manager_user_id)
        if mgr == u.id:
            mgr = None
        if u.manager_id != mgr:
            u.manager_id = mgr
            changed += 1
    await db.flush()
    return changed
