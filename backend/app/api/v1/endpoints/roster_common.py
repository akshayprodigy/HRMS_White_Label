"""Shared helpers for the roster routers."""
import asyncio
import functools
import logging
from types import SimpleNamespace
from datetime import date as pydate
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import (
    DataError, IntegrityError, OperationalError, PendingRollbackError,
)

from app.models.employee import Employee
from app.models.roster import (
    RosterEntry, RosterStatus,
)
from app.models.shift import ShiftTemplate
from app.models.user import Role, User
from app.schemas.roster import (
    RosterBulkResult,
    RosterEntryRead,
)
from app.services import roster as roster_svc
from app.services.time_rules import get_lock_rules

logger = logging.getLogger(__name__)

CONFLICT_MSG = "Roster changed concurrently; retry"
DATA_MSG = "A value is out of range or invalid"
REF_MSG = "Conflicting or invalid reference; refresh and retry"




async def entry_read(db, entry: RosterEntry) -> RosterEntryRead:
    tpl = (
        await db.get(ShiftTemplate, entry.shift_template_id)
        if entry.shift_template_id else None
    )
    u = await db.get(User, entry.employee_id)
    return RosterEntryRead(
        id=entry.id,
        employee_id=entry.employee_id,
        work_date=entry.work_date,
        shift_template_id=entry.shift_template_id,
        is_week_off=entry.is_week_off,
        status=entry.status,
        note=entry.note,
        assigned_by_id=entry.assigned_by_id,
        employee_name=u.full_name if u else None,
        shift_template_name=tpl.name if tpl else None,
        shift_start=tpl.start_time.strftime("%H:%M") if tpl else None,
        shift_end=tpl.end_time.strftime("%H:%M") if tpl else None,
    )


async def require_manage(db, user: User, employee_user_id: int) -> None:
    if not await roster_svc.can_manage_employee(db, user, employee_user_id):
        raise HTTPException(
            status_code=403,
            detail="This employee is outside your roster scope.",
        )


NO_PUBLISH_MSG = "Publishing requires HR approval for this employee"
REASON_MSG = (
    "reason required to change a published schedule (at least 3 characters)"
)
DRAFT_NOTICE = "Saved as draft: publishing requires HR approval"


def _errno(exc) -> object:
    orig = getattr(exc, "orig", None)
    return orig.args[0] if orig is not None and orig.args else None


async def _map_db_error(db, exc, msg: str):
    """Log + roll back, then return the HTTPException for a DB error that
    represents a lost race / bad data; None when it is not one of those."""
    if isinstance(exc, IntegrityError):
        logger.warning("roster IntegrityError", exc_info=True)
        await db.rollback()
        code = _errno(exc)
        if isinstance(code, int) and code != 1062:
            return HTTPException(status_code=409, detail=REF_MSG)
        return HTTPException(status_code=409, detail=msg)
    if isinstance(exc, DataError):
        logger.warning("roster DataError", exc_info=True)
        await db.rollback()
        return HTTPException(status_code=422, detail=DATA_MSG)
    if isinstance(exc, OperationalError) and roster_svc.is_lock_conflict(exc):
        logger.warning("roster lock conflict", exc_info=True)
        await db.rollback()
        return HTTPException(status_code=409, detail=msg)
    return None


async def commit_or_409(db, msg: str = CONFLICT_MSG) -> None:
    """Commit, mapping concurrency / data errors to clean HTTP errors:
    duplicate key and MariaDB 1020/1213 -> 409, other integrity errors ->
    409 (neutral message), DataError -> 422."""
    try:
        await roster_svc.flush_emergency(db)
        await db.commit()
    except (IntegrityError, DataError, OperationalError) as exc:
        mapped = await _map_db_error(db, exc, msg)
        if mapped is None:
            raise
        raise mapped from exc


_LOCK_CONFLICT_MARKERS = ("(1020,", "(1213,")


def _caused_by_lock_conflict(exc) -> bool:
    # SQLAlchemy 2.0 does not chain the original error onto
    # PendingRollbackError, but its message embeds the original exception
    # text, e.g. "... due to a previous exception during flush: (asyncmy.errors
    # .OperationalError) (1020, ...)". Match narrowly on the MariaDB codes.
    if isinstance(exc, PendingRollbackError):
        msg = str(exc)
        if any(m in msg for m in _LOCK_CONFLICT_MARKERS):
            return True
    seen = set()
    cur = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        if (isinstance(cur, OperationalError)
                and roster_svc.is_lock_conflict(cur)):
            return True
        cur = cur.__cause__ or cur.__context__
    return False


def guard_conflicts(fn):
    """Endpoint decorator: DB errors raised anywhere in the body (flush,
    autoflush, commit) that mean a lost race / bad data become 409/422 with
    a rollback. HTTPExceptions pass through untouched. The endpoint must take
    its session as the `db` keyword argument."""
    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        try:
            return await fn(*args, **kwargs)
        except (IntegrityError, DataError, OperationalError) as exc:
            mapped = await _map_db_error(kwargs["db"], exc, CONFLICT_MSG)
            if mapped is None:
                raise
            raise mapped from exc
        except PendingRollbackError as exc:
            # Session doomed by a swallowed lock conflict (1020/1213).
            if not _caused_by_lock_conflict(exc):
                raise
            logger.warning("roster lock conflict (pending rollback)",
                           exc_info=True)
            await kwargs["db"].rollback()
            raise HTTPException(
                status_code=409, detail=CONFLICT_MSG) from exc
    return wrapper


def plain_actor(user):
    """Detached stand-in for the current user (only `.id`), safe to use
    across a rollback inside a retry_on_lock body."""
    return SimpleNamespace(id=user.id)


async def retry_on_lock(db, fn, *, tries: int = 8, commit: bool = False):
    """Run `await fn()` (no args; returns plain values, nothing lazy after a
    rollback) as one transaction. MariaDB's REPEATABLE READ makes a locking
    read fail (1020/1213) when a concurrent writer committed after our
    snapshot: roll back, back off and retry on a fresh snapshot, which
    serialises writers on the same row. With commit=True the transaction is
    committed after fn. Exhausted retries and integrity errors become 409
    (the session is rolled back); other errors propagate."""
    for attempt in range(tries):
        try:
            out = await fn()
            if commit:
                await roster_svc.flush_emergency(db)
                await db.commit()
            return out
        except (OperationalError, IntegrityError) as exc:
            retry = (isinstance(exc, OperationalError)
                     and roster_svc.is_lock_conflict(exc)
                     and attempt < tries - 1)
            if retry:
                await db.rollback()
                await asyncio.sleep(0.05 * (attempt + 1))
                continue
            mapped = await _map_db_error(db, exc, "Concurrent update; retry")
            if mapped is None:
                raise
            raise mapped from exc


async def lock_row(db, stmt, msg: str = "Request already decided"):
    """Run `stmt` as a fresh-state row-locking read (FOR UPDATE). A lost
    race (MariaDB 1020/1213) rolls the session back and becomes a 409."""
    try:
        return (await db.execute(
            stmt.with_for_update().execution_options(populate_existing=True)
        )).scalars().first()
    except OperationalError as exc:
        mapped = await _map_db_error(db, exc, msg)
        if mapped is None:
            raise
        raise mapped from exc


async def lock_row_retry(db, stmt, msg: str = "Request already decided", *,
                         tries: int = 6, reload=None):
    """lock_row that survives benign lock conflicts (MariaDB 1020/1213 from a
    writer that merely touched the row, e.g. an SLA job). On a conflict it
    rolls back (fresh REPEATABLE READ snapshot), backs off and retries, so a
    still-pending row proceeds and a decided one is seen as decided by the
    caller's status check. `reload` is an optional `async fn()` that
    re-loads session objects the caller still needs (rollback expires them,
    e.g. the current user). Exhausted retries -> 409 (opt-in; lock_row itself
    is unchanged)."""
    for attempt in range(tries):
        try:
            return (await db.execute(
                stmt.with_for_update().execution_options(
                    populate_existing=True)
            )).scalars().first()
        except OperationalError as exc:
            if (roster_svc.is_lock_conflict(exc) and attempt < tries - 1):
                await db.rollback()
                await asyncio.sleep(0.05 * (attempt + 1))
                if reload is not None:
                    await reload()
                continue
            mapped = await _map_db_error(db, exc, msg)
            if mapped is None:
                raise
            raise mapped from exc


def reload_user(db, user):
    """Build a `reload` callback for lock_row_retry that re-loads `user`
    (+ roles/permissions) after a rollback expired it. The id is captured
    now: reading an expired attribute later would attempt sync IO."""
    uid = user.id

    async def _reload() -> None:
        from sqlalchemy.orm import selectinload
        await db.execute(
            select(User).where(User.id == uid).options(
                selectinload(User.roles).selectinload(Role.permissions))
            .execution_options(populate_existing=True))
    return _reload


async def lock_rows(db, stmt, msg: str = CONFLICT_MSG) -> list:
    """Like lock_row but returns every row (FOR UPDATE, fresh state)."""
    try:
        return list((await db.execute(
            stmt.with_for_update().execution_options(populate_existing=True)
        )).scalars().all())
    except OperationalError as exc:
        mapped = await _map_db_error(db, exc, msg)
        if mapped is None:
            raise
        raise mapped from exc


async def lock_user_rows(db, ids, msg: str = CONFLICT_MSG) -> None:
    """Lock the given user rows (id order) to serialize concurrent writers."""
    try:
        await db.execute(
            select(User.id).where(User.id.in_(list(ids)))
            .order_by(User.id).with_for_update()
        )
    except OperationalError as exc:
        mapped = await _map_db_error(db, exc, msg)
        if mapped is None:
            raise
        raise mapped from exc


async def validate_templates(db, ids) -> None:
    ids = {i for i in ids if i is not None}
    if not ids:
        return
    ok = set((await db.execute(
        select(ShiftTemplate.id).where(
            ShiftTemplate.id.in_(ids), ShiftTemplate.is_active.is_(True)
        )
    )).scalars().all())
    bad = sorted(ids - ok)
    if bad:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown or inactive shift template id(s): {bad}",
        )


async def write_cells(
    db, user: User, allowed: set, cells, status: str, overwrite: bool,
    result: RosterBulkResult, protect_all_published: bool = False,
    reason: str = "bulk re-plan", lock_reason: Optional[str] = None,
) -> None:
    """Write (uid, date, tpl, week_off) cells for `allowed` employees.
    Publish rights are resolved ONCE; non-publishers' cells are saved as
    draft (one message per employee) and never overwrite a live cell.
    Edits to PUBLISHED cells are recorded in history and each affected
    employee is notified once. Cells that would change the LIVE schedule
    inside the lock window are checked up front (`lock_guard`, `lock_reason`
    = the caller-supplied reason): the whole request is refused with 403
    unless the actor may override, and such cells are recorded as emergency
    changes."""
    pub = await roster_svc.publishable_subset(db, user, allowed)
    dept_by_uid = {
        e.user_id: e.department
        for e in (await db.execute(
            select(Employee).where(Employee.user_id.in_(allowed))
        )).scalars().all()
    }
    downgraded: set = set()
    skipped_pub: set = set()
    cells = list(cells)
    existing_map = (
        await roster_svc.prefetch_entries(
            db, allowed, min(c[1] for c in cells), max(c[1] for c in cells)
        ) if cells else {}
    )
    # ---- lock window pre-check (before any write) ----
    locked: set = set()
    locked_base: dict = {}
    lock_days = (await get_lock_rules(db))["lock_days"]
    if lock_days and cells:
        win = []
        for (uid, wd, tpl_id, week_off) in cells:
            if not roster_svc.in_lock_window(wd, lock_days):
                continue
            prior = existing_map.get((uid, wd))
            can_pub = uid in pub
            if prior is not None and not overwrite:
                continue  # skipped by upsert_entry
            if prior is not None and (
                not can_pub or protect_all_published
            ) and prior.status == RosterStatus.PUBLISHED:
                continue  # skipped by upsert_entry: live cell untouched
            eff = status if (can_pub or status == RosterStatus.DRAFT) \
                else RosterStatus.DRAFT
            win.append((uid, wd, tpl_id, week_off, prior, eff))
        base = await roster_svc.assignment_cells(
            db, {(w[0], w[1]) for w in win})
        guard = [
            (uid, wd,
             roster_svc.live_cell(
                 (prior.shift_template_id, prior.is_week_off, prior.status)
                 if prior is not None else None, base[(uid, wd)]),
             roster_svc.norm_cell(tpl_id, week_off)
             if eff == RosterStatus.PUBLISHED else base[(uid, wd)])
            for (uid, wd, tpl_id, week_off, prior, eff) in win
        ]
        locked = await roster_svc.lock_guard(db, user, guard, reason=lock_reason)
        locked_base = {(g[0], g[1]): (g[2], g[3]) for g in guard}
    changed: dict = {}
    for (uid, wd, tpl_id, week_off) in cells:
        prior = existing_map.get((uid, wd))
        prior_snap = (
            (prior.shift_template_id, prior.is_week_off, prior.status)
            if prior is not None else None
        )
        eff = status
        can_pub = uid in pub
        if status == RosterStatus.PUBLISHED and not can_pub:
            eff = RosterStatus.DRAFT
        with db.no_autoflush:
            _e, outcome = await roster_svc.upsert_entry(
                db,
                employee_id=uid, work_date=wd, shift_template_id=tpl_id,
                is_week_off=week_off, status=eff, actor_id=user.id,
                department=dept_by_uid.get(uid), overwrite=overwrite,
                protect_published=(not can_pub) or protect_all_published,
                existing_map=existing_map,
            )
        emerg = (uid, wd) in locked and outcome != "skipped"
        if emerg:
            old, new = locked_base[(uid, wd)]
            await db.flush()
            roster_svc.record_change(
                db, _e, employee_id=uid, work_date=wd,
                old_tpl=old[0], old_off=old[1],
                new_tpl=new[0], new_off=new[1], action="update",
                reason=lock_reason, actor_id=user.id, emergency=True,
            )
            changed.setdefault(uid, set()).add(wd)
        elif (
            outcome == "updated" and prior_snap is not None
            and prior_snap[2] == RosterStatus.PUBLISHED
        ):
            new_tpl = None if week_off else tpl_id
            if (
                (prior_snap[0], prior_snap[1]) != (new_tpl, week_off)
                or eff != RosterStatus.PUBLISHED
            ):
                roster_svc.record_change(
                    db, _e, employee_id=uid, work_date=wd,
                    old_tpl=prior_snap[0], old_off=prior_snap[1],
                    new_tpl=new_tpl, new_off=week_off, action="update",
                    reason=reason, actor_id=user.id,
                )
                changed.setdefault(uid, set()).add(wd)
        if (
            outcome == "skipped" and overwrite and not can_pub
            and prior_snap is not None
            and prior_snap[2] == RosterStatus.PUBLISHED
        ):
            skipped_pub.add(uid)
        if outcome != "skipped" and eff == RosterStatus.DRAFT and (
            status == RosterStatus.PUBLISHED and not can_pub
        ):
            downgraded.add(uid)
        if outcome == "created":
            result.created += 1
        elif outcome == "updated":
            result.updated += 1
        else:
            result.skipped += 1
    await roster_svc.notify_schedule_changed(db, changed)
    if downgraded or skipped_pub:
        nm = await names(db, downgraded | skipped_pub)
        for uid in sorted(downgraded | skipped_pub):
            who = nm.get(uid) or uid
            if uid in downgraded and uid in skipped_pub:
                what = "Saved as draft and skipped published cells"
            elif uid in skipped_pub:
                what = "Skipped published cells"
            else:
                what = "Saved as draft"
            result.errors.append(
                f"{what} for {who}: publishing requires HR approval"
            )


async def names(db, ids) -> dict:
    """User id -> display name (full name, else email)."""
    ids = {i for i in ids if i is not None}
    if not ids:
        return {}
    rows = (await db.execute(
        select(User.id, User.full_name, User.email).where(User.id.in_(ids))
    )).all()
    return {r[0]: (r[1] or r[2]) for r in rows}


def require_admin(user: User) -> None:
    if not roster_svc.is_roster_admin(user):
        raise HTTPException(status_code=403, detail="HR/admin access required.")




def check_window(start: pydate, end: pydate, max_days: int = 62) -> None:
    if start > end:
        raise HTTPException(status_code=400, detail="start must be <= end")
    if (end - start).days > max_days:
        raise HTTPException(
            status_code=400, detail=f"range too large (max {max_days} days)"
        )


