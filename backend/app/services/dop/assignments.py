"""Manager assignment writes. Services never commit.

Transaction contract (callers: Tasks 5 and 7, inside retry_on_lock):
  * a DOP writer runs in a FRESH transaction (`await db.commit()` first) and
    takes the manager_kind lock (`lock_reporting` / `create` / `end` do) as
    its first statement, before any plain read and before any other write to
    user rows;
  * lock order is always the reporting kind first, then the writer's own
    kind (`_lock_kind` does both), so writers of any kind, mirror writers
    and account deletes can never deadlock or interleave;
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
from sqlalchemy import or_, select

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
    # ONE lock order everywhere: the reporting kind first, then this kind.
    # Account deletes and mirror writers hold the reporting lock, so a
    # non-reporting write cannot interleave with them.
    await reporting_ready(db)
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


async def reporting_ready(db) -> bool:
    """Take the reporting lock like lock_reporting, but answer False (instead
    of 422) when the kind is missing or inactive. Edits that do not change a
    manager use it to skip the mirror sync rather than fail."""
    kind = (await db.execute(
        select(ManagerKind).where(ManagerKind.code == "reporting")
        .with_for_update().execution_options(populate_existing=True)
    )).scalars().first()
    return kind is not None and bool(kind.is_active)


async def _user_exists(db, uid, what):
    if (await db.execute(select(User.id).where(User.id == uid))
            ).first() is None:
        raise HTTPException(422, f"{what} not found")


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


def _prepare(scope_type, scope_user_id, scope_department_id, scope_location,
             manager_user_id, manager_post_id, starts_on, ends_on, subdomains):
    """Argument checks that need no DB. Returns (scope_location, subdomains)."""
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
    return scope_location, subs


async def create(db, *, actor_id, kind_id, scope_type, scope_user_id=None,
                 scope_department_id=None, scope_location=None,
                 manager_user_id=None, manager_post_id=None, subdomains=(),
                 starts_on, ends_on=None, note=None,
                 allow_inactive_employee=False) -> ManagerAssignment:
    scope_location, subs = _prepare(
        scope_type, scope_user_id, scope_department_id, scope_location,
        manager_user_id, manager_post_id, starts_on, ends_on, subdomains)
    kind = await _lock_kind(db, kind_id)
    if scope_user_id is not None:
        if allow_inactive_employee:       # HR edits an inactive employee
            await _user_exists(db, scope_user_id, "Employee")
        else:
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


def _do_end(db, actor_id, a, ends_on, today) -> None:
    """End (or, when it has not started, cancel) a live row and audit it.
    The caller flushes and syncs."""
    before = snapshot(a)
    if ends_on < a.starts_on:
        if a.starts_on < today:
            raise HTTPException(
                422, "It already started: end it on or after its start date")
        a.cancelled_at = datetime.now(timezone.utc)
    else:
        a.ends_on = ends_on
    audit(db, actor_id, "dop.assignment.end", "manager_assignment", a.id,
          {"before": before, "ends_on": ends_on.isoformat(),
           "cancelled": a.cancelled_at is not None})


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
    base = (await loop_baseline(db, [today])
            if kind.code == "reporting" and not a.subdomains else None)
    _do_end(db, actor_id, a, ends_on, today)
    await db.flush()
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


def _clashing(rows, subs, starts_on, ends_on) -> list:
    return [r for r in rows if subs_clash(r.subdomains, subs)
            and dates_overlap(r.starts_on, r.ends_on, starts_on, ends_on)]


def _check_replaceable(rows, starts_on, today):
    """A clashing row ends the day before the new start; one that starts on
    or after the new start is cancelled, which only works while it has not
    started. Otherwise 409, before anything is changed."""
    for r in rows:
        if starts_on - timedelta(days=1) < r.starts_on and r.starts_on < today:
            raise HTTPException(
                409, f"Assignment #{r.id} already started and cannot be "
                     "replaced cleanly: end it first")


def _continuations(clash, kept, starts_on, ends_on, new_subs, actor_id) -> list:
    """Rows that carry on what a replace would otherwise drop, as unsaved
    (old row, new row) pairs, built before the old rows change:
      * rest: the named areas of a clashing row that the new row does not
        name, from the later start to the earlier end of the two;
      * tail: the whole clashing row after the new `ends_on`.
    409 when one of them would clash with a row that stays."""
    day = timedelta(days=1)
    out = []
    for r in clash:
        old = list(r.subdomains or [])
        pieces = []
        rest = sorted(set(old) - set(new_subs))
        if rest:
            end = (ends_on if r.ends_on is None else r.ends_on
                   if ends_on is None else min(r.ends_on, ends_on))
            pieces.append((rest, max(r.starts_on, starts_on), end))
        if ends_on is not None and (r.ends_on is None or r.ends_on > ends_on):
            pieces.append((old, ends_on + day, r.ends_on))
        for subs, start, end in pieces:
            for k in kept:
                if k.scope_user_id == r.scope_user_id and subs_clash(
                        k.subdomains, subs) and dates_overlap(
                        k.starts_on, k.ends_on, start, end):
                    raise HTTPException(
                        409, f"The rest of assignment #{r.id} would overlap "
                             f"assignment #{k.id}: end that one first")
            out.append((r, ManagerAssignment(
                manager_kind_id=r.manager_kind_id, scope_type=r.scope_type,
                scope_user_id=r.scope_user_id,
                scope_department_id=r.scope_department_id,
                scope_location=r.scope_location,
                manager_user_id=r.manager_user_id,
                manager_post_id=r.manager_post_id, subdomains=subs,
                starts_on=start, ends_on=end, note=r.note,
                created_by_id=actor_id)))
    return out


def _audit_continuations(db, actor_id, pairs):
    for old, row in pairs:
        audit(db, actor_id, "dop.assignment.create", "manager_assignment",
              row.id, {**snapshot(row), "continues": old.id})


def _cont_dates(today, starts_on, pairs) -> list:
    d = _dates(today, starts_on)
    for _, row in pairs:
        if row.starts_on > today and row.starts_on not in d:
            d.append(row.starts_on)
    return d


async def replace_overlaps(db, *, actor_id, kind_id, scope_type, starts_on,
                           subdomains=(), scope_user_id=None,
                           scope_department_id=None, scope_location=None,
                           ends_on=None, **_) -> tuple:
    """End the rows a new assignment would clash with, the day before it
    starts (rows that start on or after it are cancelled, only while they
    have not started). A row that runs past the new `ends_on` continues in a
    new row after it. Returns (rows replaced, rows continued). When a
    clashing row cannot be ended cleanly, or a continuation would clash:
    409 before any change. One loop check and one sync for the scope."""
    try:
        subs = sorted(S.validate(subdomains))
    except ValueError as e:
        raise HTTPException(422, str(e))
    kind = await _lock_kind(db, kind_id)
    every = await _same_scope(
        db, kind_id, scope_type, scope_user_id, scope_department_id,
        (scope_location or "").strip() or None)
    rows = _clashing(every, subs, starts_on, ends_on)
    if not rows:
        return 0, 0
    today = await local_today(db)
    _check_replaceable(rows, starts_on, today)
    ids = {r.id for r in rows}
    pairs = _continuations(rows, [r for r in every if r.id not in ids],
                           starts_on, ends_on, subs, actor_id)
    base = (await loop_baseline(db, _cont_dates(today, starts_on, pairs))
            if kind.code == "reporting" and not subs else None)
    new = [row for _, row in pairs]
    for r in rows:
        _do_end(db, actor_id, r, starts_on - timedelta(days=1), today)
    db.add_all(new)
    await db.flush()
    _audit_continuations(db, actor_id, pairs)
    await db.flush()
    if kind.code == "reporting":
        w = await load_world(db, today)
        users = _matching(w.people, rows[0], await _dept_name(db, rows[0]))
        if base is not None:
            await assert_no_new_loops(db, base, users)
        await _sync(db, w, today, users)
    return len(rows), len(pairs)


async def _dept_name(db, a):
    if a.scope_type != "department":
        return None
    return (await db.execute(select(Department.name).where(
        Department.id == a.scope_department_id))).scalar_one_or_none()


async def create_many(db, *, actor_id, kind_id, user_ids, manager_user_id=None,
                      manager_post_id=None, subdomains=(), starts_on,
                      ends_on=None, note=None, replace=False):
    """One user-scope assignment per employee, all or nothing, in the
    caller's transaction. Loads the world twice (baseline, after) and syncs
    once, however many employees: a constant number of statements plus two
    inserts per employee (audit, assignment) and one update per changed
    manager. Returns (assignment ids in user order, rows replaced, rows continued)."""
    ids = sorted(set(user_ids))
    if not ids:
        raise HTTPException(422, "Choose at least one employee")
    _, subs = _prepare("user", ids[0], None, None, manager_user_id,
                       manager_post_id, starts_on, ends_on, subdomains)
    if manager_user_id in ids:
        raise HTTPException(422, "An employee cannot be their own manager")
    kind = await _lock_kind(db, kind_id)
    found = dict((await db.execute(select(User.id, User.is_active).where(
        User.id.in_(ids)))).all())
    bad = [i for i in ids if not found.get(i)]
    if bad:
        raise HTTPException(
            422, "Employee not found or inactive: "
                 + ", ".join(map(str, bad[:10])))
    if manager_user_id is not None:
        await _active_user(db, manager_user_id, "Manager")
    else:
        post = await db.get(Post, manager_post_id)
        if post is None or not post.is_active:
            raise HTTPException(422, "Post not found or inactive")
    today = await local_today(db)
    rows = (await db.execute(
        select(ManagerAssignment).where(
            ManagerAssignment.manager_kind_id == kind_id,
            ManagerAssignment.scope_type == "user",
            ManagerAssignment.scope_user_id.in_(ids),
            ManagerAssignment.cancelled_at.is_(None))
        .order_by(ManagerAssignment.id).with_for_update()
        .execution_options(populate_existing=True))).scalars().all()
    clash = _clashing(rows, subs, starts_on, ends_on)
    if clash and not replace:
        raise HTTPException(
            409, f"Overlaps assignment #{clash[0].id}: end that one first")
    _check_replaceable(clash, starts_on, today)
    cids = {r.id for r in clash}
    pairs = _continuations(clash, [r for r in rows if r.id not in cids],
                           starts_on, ends_on, subs, actor_id)
    base = (await loop_baseline(db, _cont_dates(today, starts_on, pairs))
            if kind.code == "reporting" and not subs else None)
    tail_rows = [row for _, row in pairs]
    for r in clash:
        _do_end(db, actor_id, r, starts_on - timedelta(days=1), today)
    new = [ManagerAssignment(
        manager_kind_id=kind_id, scope_type="user", scope_user_id=i,
        manager_user_id=manager_user_id, manager_post_id=manager_post_id,
        subdomains=subs, starts_on=starts_on, ends_on=ends_on, note=note,
        created_by_id=actor_id) for i in ids]
    db.add_all(new + tail_rows)
    await db.flush()
    for a in new:
        audit(db, actor_id, "dop.assignment.create", "manager_assignment",
              a.id, snapshot(a))
    _audit_continuations(db, actor_id, pairs)
    await db.flush()
    if kind.code == "reporting":
        w = await load_world(db, today)
        if base is not None:
            await assert_no_new_loops(db, base, ids)
        await _sync(db, w, today, ids)
    return [a.id for a in new], len(clash), len(pairs)


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
        await sync_mirror(db, [user_id], "manager edit", actor_id)
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
                     ends_on=nxt - timedelta(days=1) if nxt else None,
                     allow_inactive_employee=True)
        return
    # Clearing. A manager that no assignment governs (written by a seed or
    # script) is cleared here too; a department/location/company row that
    # applies wins, as designed.
    await db.flush()
    w = await load_world(db, today)
    await _sync(db, w, today, [user_id])
    if not _base_manager(w, user_id, today)[0]:
        u = (await db.execute(
            select(User).where(User.id == user_id).with_for_update()
            .execution_options(populate_existing=True))).scalars().first()
        if u is not None and u.manager_id is not None:
            audit(db, actor_id, "dop.manager.clear", "user", user_id,
                  {"before": u.manager_id})
            u.manager_id = None
            await db.flush()


SYNC_AUDIT_CAP = 200


def audit_sync(db, actor_id, reason, changes) -> None:
    """One `dop.manager.sync` row for a mirror change that no assignment
    write already audited (job, department/location move, holder change).
    Nothing is written when nothing changed."""
    if not changes:
        return
    audit(db, actor_id, "dop.manager.sync", "manager_mirror", reason,
          {"reason": reason, "total": len(changes),
           "changes": changes[:SYNC_AUDIT_CAP]})


async def _sync(db, w, today, user_ids, reason=None, actor_id=None) -> int:
    """Mirror for `user_ids` from the world `w` (built for `today`). Plain
    reads decide; only users whose manager_id differs are locked (id order)
    and re-checked. With `reason`, changes are audited (see audit_sync);
    direct assignment writes pass none: they audit themselves."""
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
    changes: list = []
    if diff:
        for u in (await db.execute(
                select(User).where(User.id.in_(diff)).order_by(User.id)
                .with_for_update().execution_options(populate_existing=True)
        )).scalars().all():
            if u.manager_id != want[u.id]:
                changes.append({"user_id": u.id, "from": u.manager_id,
                                "to": want[u.id]})
                u.manager_id = want[u.id]
                changed += 1
        await db.flush()
    if reason:
        audit_sync(db, actor_id, reason, changes)
    return changed


async def sync_mirror(db, user_ids=None, reason=None, actor_id=None) -> int:
    """Set User.manager_id to the base reporting manager (no acting cover).
    Returns how many users changed. Needs the reporting kind lock (taken
    here; re-locking a held row is free). Only users the assignments govern
    are touched: a manager set by a seed or script is never cleared."""
    await lock_reporting(db)
    await db.flush()
    today = await local_today(db)
    return await _sync(db, await load_world(db, today), today, user_ids,
                       reason, actor_id)


async def post_governed_users(db, post_id) -> list:
    """Users whose all-subdomain reporting manager is the holder of `post_id`
    (live or future rows). Needs the reporting kind lock (callers hold it)."""
    today = await local_today(db)
    dnames = dict((await db.execute(
        select(Department.id, Department.name))).all())
    people = await load_people(db)
    users: set = set()
    for a in (await db.execute(
            select(ManagerAssignment).join(
                ManagerKind, ManagerKind.id == ManagerAssignment.manager_kind_id)
            .where(ManagerKind.code == "reporting",
                   ManagerAssignment.manager_post_id == post_id,
                   ManagerAssignment.cancelled_at.is_(None),
                   or_(ManagerAssignment.ends_on.is_(None),
                       ManagerAssignment.ends_on >= today)))).scalars().all():
        if not a.subdomains:
            users |= set(_matching(people, a, dnames.get(a.scope_department_id)))
    return sorted(users)


async def sync_post_users(db, post_id, baseline=None, actor_id=None) -> int:
    """After a holder or post change: refuse a new reporting loop (when a
    `loop_baseline` taken after the lock is given) and resync the mirror of
    the users governed by assignments to the post. Returns users changed."""
    await lock_reporting(db)
    await db.flush()
    users = await post_governed_users(db, post_id)
    if not users:
        return 0
    if baseline is not None:
        await assert_no_new_loops(db, baseline, users)
    today = await local_today(db)
    return await _sync(db, await load_world(db, today), today, users,
                       "post holder change", actor_id)


async def has_reporting_assignment(db, user_id, w=None, today=None) -> bool:
    """Does an all-subdomain reporting assignment apply to the user today?
    Call before moving the employee (department / location change). Pass a
    world loaded under the lock (and its date) to skip loading another."""
    if w is None:
        await lock_reporting(db)
        today = await local_today(db)
        w = await load_world(db, today)
    return _base_manager(w, user_id, today)[0]


async def resync_after_move(db, user_id, had_assignment: bool,
                            w=None, today=None, actor_id=None) -> int:
    """After a department/location change: when an assignment applied before
    and none applies now, manager_id becomes NULL; otherwise the normal sync."""
    await lock_reporting(db)
    await db.flush()
    if w is None:       # only valid when nothing it was built from changed
        today = await local_today(db)
        w = await load_world(db, today)
    if had_assignment and not _base_manager(w, user_id, today)[0]:
        u = (await db.execute(
            select(User).where(User.id == user_id).with_for_update()
            .execution_options(populate_existing=True))).scalars().first()
        if u is not None and u.manager_id is not None:
            audit_sync(db, actor_id, "department/location move",
                       [{"user_id": user_id, "from": u.manager_id,
                         "to": None}])
            u.manager_id = None
            await db.flush()
            return 1
        return 0
    return await _sync(db, w, today, [user_id], "department/location move",
                       actor_id)
