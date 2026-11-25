"""Manager assignment writes. Services never commit.

Transaction contract (callers: Tasks 5 and 7, inside retry_on_lock):
  * a DOP writer runs in a FRESH transaction (`await db.commit()` first) and
    takes the manager_kind lock (`lock_reporting` / `create` / `end` do) as
    its first statement, before any plain read and before any other write to
    user rows;
  * the kind row serialises all writers of a kind, so every plain read made
    after the lock sees the latest committed data (the snapshot starts after
    the lock is granted);
  * EVERY caller (endpoints, scheduler job, Task 6/7 services) wraps the
    whole transaction in retry_on_lock, never a bare commit;
  * the loop check compares worlds before and after the change
    (`loop_baseline` + `assert_no_new_loops`): only a loop through a user
    whose base manager changed is refused, old loops never block. A change
    that moves reporting managers by other means (post holders) takes the
    baseline after the lock, changes, then calls assert_no_new_loops;
  * MariaDB (REPEATABLE READ + innodb_snapshot_isolation) does not return the
    latest row from a locking read of a row that changed after our snapshot:
    it raises 1020. retry_on_lock catches that and retries on a new snapshot.
"""
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


async def lock_reporting(db) -> ManagerKind:
    """Take the reporting kind's lock in one statement (by code)."""
    kind = (await db.execute(
        select(ManagerKind).where(ManagerKind.code == "reporting")
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
    """Live-or-future (not cancelled) rows of one kind at exactly one scope
    target, locked. Location is compared normalised, in Python."""
    q = select(ManagerAssignment).where(
        ManagerAssignment.manager_kind_id == kind_id,
        ManagerAssignment.scope_type == scope_type,
        ManagerAssignment.cancelled_at.is_(None))
    if scope_type == "user":
        q = q.where(ManagerAssignment.scope_user_id == user_id)
    elif scope_type == "department":
        q = q.where(ManagerAssignment.scope_department_id == dept_id)
    rows = (await db.execute(
        q.order_by(ManagerAssignment.id).with_for_update()
        .execution_options(populate_existing=True))).scalars().all()
    if scope_type == "location":
        rows = [r for r in rows if R.norm(r.scope_location) == R.norm(loc)]
    return rows


def _base_manager(w, uid, on):
    """(applies, manager) for the all-subdomain reporting manager on a date:
    assignment plus post holder, no acting cover, never oneself."""
    a = R.find_assignment(w, "reporting", uid, "", on)
    if a is None:
        return False, None
    mgr = (R.holder_of(w, a.manager_post_id, on)
           if a.manager_post_id else a.manager_user_id)
    return True, (None if mgr == uid else mgr)


def _mgr_map(w, users, on) -> dict:
    return {x: _base_manager(w, x, on)[1] for x in users}


def _on_loop(mgr, u) -> bool:
    """Is u on a reporting loop? `mgr` maps user -> base manager."""
    seen, cur = {u}, mgr(u)
    while cur is not None:
        if cur == u:
            return True
        if cur in seen:                # a loop that does not include u
            return False
        seen.add(cur)
        cur = mgr(cur)
    return False


async def loop_baseline(db, dates) -> dict:
    """Worlds (date -> World) to compare against after a change. Take it
    AFTER the lock and BEFORE the first write; works for any caller
    (assignments, post holders, ...)."""
    return {d: await load_world(db, d) for d in dates}


async def assert_no_new_loops(db, baseline, user_ids=None) -> dict:
    """422 when the change made since `baseline` creates a reporting loop:
    a loop (on any baseline date) through a user whose base reporting
    manager changed. Loops that already existed, and loops that do not
    contain a changed user, never block. `user_ids` limits who is looked at
    (default: everyone). Returns the after-worlds (date -> World)."""
    after = {}
    for on, wb in baseline.items():
        wa = await load_world(db, on)
        after[on] = wa
        users = (sorted(set(user_ids) & set(wa.people))
                 if user_ids is not None else sorted(wa.people))
        if not users:
            continue
        mb, ma = _mgr_map(wb, users, on), _mgr_map(wa, users, on)
        memo: dict = {}

        def mgr(x, wa=wa, on=on, memo=memo):
            if x not in memo:
                memo[x] = _base_manager(wa, x, on)[1]
            return memo[x]
        for u in users:
            if mb[u] != ma[u] and _on_loop(mgr, u):
                raise HTTPException(
                    422, "This would make a reporting loop (a manager would "
                         "report to their own report)")
    return after


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
    dept_name = None
    if scope_department_id is not None:
        dept_name = (await db.execute(select(Department.name).where(
            Department.id == scope_department_id))).scalar_one_or_none()
        if dept_name is None:
            raise HTTPException(422, "Department not found")
    if manager_user_id is not None:
        await _active_user(db, manager_user_id, "Manager")
    else:
        post = await db.get(Post, manager_post_id)
        if post is None or not post.is_active:
            raise HTTPException(422, "Post not found or inactive")
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
    today = await local_today(db)
    base = (await loop_baseline(db, _dates(today, starts_on))
            if kind.code == "reporting" and not subs else None)
    db.add(a)
    await db.flush()
    audit(db, actor_id, "dop.assignment.create", "manager_assignment", a.id,
          snapshot(a))
    if kind.code == "reporting":
        w = await load_world(db, today)
        users = _matching(w.people, a, dept_name)
        if base is not None:
            await assert_no_new_loops(db, base, users)
        await _sync(db, w, today, users)
    return a


async def end(db, *, actor_id, assignment_id, ends_on) -> ManagerAssignment:
    rk = await lock_reporting(db)
    kind_id = (await db.execute(select(ManagerAssignment.manager_kind_id)
               .where(ManagerAssignment.id == assignment_id))
               ).scalar_one_or_none()      # immutable column
    if kind_id is None:
        raise HTTPException(404, "Assignment not found")
    kind = rk if kind_id == rk.id else await _lock_kind(db, kind_id)
    a = (await db.execute(
        select(ManagerAssignment).where(ManagerAssignment.id == assignment_id)
        .with_for_update().execution_options(populate_existing=True)
    )).scalars().one()
    if a.cancelled_at is not None:
        if ends_on < a.starts_on:
            return a                       # same request again: nothing to do
        raise HTTPException(409, "Assignment was already removed")
    if a.ends_on == ends_on:
        return a
    if a.ends_on is not None and ends_on > a.ends_on:
        raise HTTPException(
            422, "It already ends earlier: create a new assignment instead")
    today = await local_today(db)
    before = snapshot(a)
    base = (await loop_baseline(db, [today])
            if kind.code == "reporting" and not a.subdomains else None)
    if ends_on < a.starts_on:
        if a.starts_on < today:
            raise HTTPException(
                422, "It already started: end it on or after its start date")
        a.cancelled_at = datetime.now(timezone.utc)
    else:
        a.ends_on = ends_on
    await db.flush()
    audit(db, actor_id, "dop.assignment.end", "manager_assignment", a.id,
          {"before": before, "ends_on": ends_on.isoformat(),
           "cancelled": a.cancelled_at is not None})
    if kind.code == "reporting":
        w = await load_world(db, today)
        dept_name = None
        if a.scope_type == "department":
            dept_name = (await db.execute(select(Department.name).where(
                Department.id == a.scope_department_id))).scalar_one_or_none()
        users = _matching(w.people, a, dept_name)
        if base is not None:
            await assert_no_new_loops(db, base, users)
        await _sync(db, w, today, users)
    return a


def _dates(today, starts_on=None) -> list:
    return [today] + ([starts_on] if starts_on and starts_on > today else [])


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
    """HR/admin edits of one employee's manager. Does nothing when a live
    all-subdomain row already names this manager. Otherwise ends the rows
    live today and starts a new one today, ending it the day before the next
    scheduled row; scheduled rows stay."""
    kind = await lock_reporting(db)
    today = await local_today(db)
    rows = [r for r in await _same_scope(db, kind.id, "user", user_id,
                                         None, None)
            if not r.subdomains and (r.ends_on is None or r.ends_on >= today)]
    live = [r for r in rows if r.starts_on <= today]
    if manager_id is not None and any(
            r.manager_user_id == manager_id for r in live):
        await sync_mirror(db, [user_id])
        return
    future = [r for r in rows if r.starts_on > today]
    for r in sorted(live, key=lambda r: r.id):
        await end(db, actor_id=actor_id, assignment_id=r.id,
                  ends_on=today - timedelta(days=1))
    if manager_id is not None:
        nxt = min((r.starts_on for r in future), default=None)
        await create(db, actor_id=actor_id, kind_id=kind.id,
                     scope_type="user", scope_user_id=user_id,
                     manager_user_id=manager_id, starts_on=today,
                     ends_on=nxt - timedelta(days=1) if nxt else None)
    else:
        await sync_mirror(db, [user_id])


async def _sync(db, w, today, user_ids) -> int:
    """Mirror for `user_ids` from the world `w` (built for `today`). Plain
    reads decide; only users whose manager_id differs are locked (id order)
    and re-checked."""
    dnames = dict((await db.execute(
        select(Department.id, Department.name))).all())
    # Governed: an all-subdomain reporting row that has started applies (or
    # applied, when ended or cancelled) to the user. A future row or a row
    # limited to named subdomains never governs manager_id.
    governed: set = set()
    for row in (await db.execute(
            select(ManagerAssignment).join(
                ManagerKind, ManagerKind.id == ManagerAssignment.manager_kind_id)
            .where(ManagerKind.code == "reporting",
                   ManagerAssignment.starts_on <= today))).scalars().all():
        if not row.subdomains:
            governed |= set(_matching(
                w.people, row, dnames.get(row.scope_department_id)))
    want: dict = {}
    for uid in (sorted(w.people) if user_ids is None else sorted(set(user_ids))):
        if uid not in w.people:
            continue
        applies, mgr = _base_manager(w, uid, today)
        if applies or uid in governed:
            want[uid] = mgr
    if not want:
        return 0
    cur = dict((await db.execute(select(User.id, User.manager_id).where(
        User.id.in_(list(want))))).all())
    diff = sorted(i for i in want if cur.get(i) != want[i] and i in cur)
    changed = 0
    if diff:
        for u in (await db.execute(
                select(User).where(User.id.in_(diff)).order_by(User.id)
                .with_for_update().execution_options(populate_existing=True)
        )).scalars().all():
            if u.manager_id != want[u.id]:
                u.manager_id = want[u.id]
                changed += 1
        await db.flush()
    return changed


async def sync_mirror(db, user_ids=None) -> int:
    """Set User.manager_id to the base reporting manager (no acting cover).
    Returns how many users changed. Needs the reporting kind lock (taken
    here; re-locking a held row is free). Only users the assignments govern
    are touched: a manager set by a seed or script is never cleared."""
    await lock_reporting(db)
    await db.flush()
    today = await local_today(db)
    return await _sync(db, await load_world(db, today), today, user_ids)


async def has_reporting_assignment(db, user_id) -> bool:
    """Does an all-subdomain reporting assignment apply to the user today?
    Call before moving the employee (department / location change)."""
    await lock_reporting(db)
    today = await local_today(db)
    w = await load_world(db, today)
    return _base_manager(w, user_id, today)[0]


async def resync_after_move(db, user_id, had_assignment: bool) -> int:
    """After a department/location change: when an assignment applied before
    and none applies now, manager_id becomes NULL; otherwise the normal sync."""
    await lock_reporting(db)
    await db.flush()
    today = await local_today(db)
    w = await load_world(db, today)
    if had_assignment and not _base_manager(w, user_id, today)[0]:
        u = (await db.execute(
            select(User).where(User.id == user_id).with_for_update()
            .execution_options(populate_existing=True))).scalars().first()
        if u is not None and u.manager_id is not None:
            u.manager_id = None
            await db.flush()
            return 1
        return 0
    return await _sync(db, w, today, [user_id])
