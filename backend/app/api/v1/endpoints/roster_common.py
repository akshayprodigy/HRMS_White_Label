"""Shared helpers for the roster routers."""
from datetime import date as pydate

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import DataError, IntegrityError, OperationalError

from app.models.employee import Employee
from app.models.roster import (
    RosterEntry, RosterStatus,
)
from app.models.shift import ShiftTemplate
from app.models.user import User
from app.schemas.roster import (
    RosterBulkResult,
    RosterEntryRead,
)
from app.services import roster as roster_svc




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


async def commit_or_409(
    db, msg: str = "Roster changed concurrently; retry"
) -> None:
    """Commit, mapping concurrency / data errors to clean HTTP errors:
    IntegrityError and MariaDB 1020/1213 -> 409, DataError -> 422."""
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail=msg)
    except DataError:
        await db.rollback()
        raise HTTPException(
            status_code=422, detail="A value is out of range or invalid"
        )
    except OperationalError as exc:
        if roster_svc.is_lock_conflict(exc):
            await db.rollback()
            raise HTTPException(status_code=409, detail=msg)
        raise


async def lock_row(db, stmt, msg: str = "Request already decided"):
    """Run `stmt` as a fresh-state row-locking read (FOR UPDATE). A lost
    race (MariaDB 1020/1213) rolls the session back and becomes a 409."""
    try:
        return (await db.execute(
            stmt.with_for_update().execution_options(populate_existing=True)
        )).scalars().first()
    except OperationalError as exc:
        if roster_svc.is_lock_conflict(exc):
            await db.rollback()
            raise HTTPException(status_code=409, detail=msg)
        raise


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
    reason: str = "bulk re-plan",
) -> None:
    """Write (uid, date, tpl, week_off) cells for `allowed` employees.
    Publish rights are resolved ONCE; non-publishers' cells are saved as
    draft (one message per employee) and never overwrite a live cell.
    Edits to PUBLISHED cells are recorded in history and each affected
    employee is notified once."""
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
        if (
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


