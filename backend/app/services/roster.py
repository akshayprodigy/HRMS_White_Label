"""Roster planner service (W7).

All scope enforcement lives here so every roster endpoint shares one
definition of "who can a planner touch": superusers / `roster manage`
holders see everyone; functional heads (F1) see only the employees in the
departments they head. `employee_id` throughout is a User id, matching
EmployeeShiftAssignment.
"""
from __future__ import annotations

import logging
from datetime import date as pydate, datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy import or_, select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.department import Department
from app.models.employee import Employee, EmployeeStatus
from app.models.leave import LeaveRequest, LeaveStatus
from app.models.notification import Notification
from app.models.roster import RosterEntry, RosterEntryHistory, RosterStatus
from app.models.schedule_delegation import DelegationScope, ScheduleDelegation
from app.models.shift import EmployeeShiftAssignment, ShiftTemplate
from app.models.user import User

PERM_ROSTER = "roster manage"
logger = logging.getLogger(__name__)


def is_roster_admin(user: User) -> bool:
    if user.is_superuser:
        return True
    return any(
        p.name == PERM_ROSTER
        for r in user.roles
        for p in r.permissions
    )


async def scope_department_names(
    db: AsyncSession, user: User
) -> Optional[List[str]]:
    """None => admin (all departments). Otherwise the department names this
    user heads (as head or deputy)."""
    if is_roster_admin(user):
        return None
    names = (await db.execute(
        select(Department.name).where(
            or_(
                Department.head_user_id == user.id,
                Department.deputy_head_user_id == user.id,
            )
        )
    )).scalars().all()
    return list(names)


async def resolve_scope_user_ids(
    db: AsyncSession,
    scope_type: str,
    scope_value: Optional[str] = None,
    employee_ids: Optional[List[int]] = None,
    grantee_id: Optional[int] = None,
) -> set:
    """User ids covered by a delegation scope. One query at most. When
    `grantee_id` is given the grantee is never part of their own scope."""
    ids = await _resolve_scope(db, scope_type, scope_value, employee_ids, grantee_id)
    if grantee_id is not None:
        ids.discard(grantee_id)
    return ids


async def _active_employee_user_ids(db: AsyncSession, ids: set) -> set:
    """Subset of `ids` that are User ids of ACTIVE Employees."""
    if not ids:
        return set()
    return set((await db.execute(
        select(Employee.user_id).where(
            Employee.user_id.in_(ids),
            Employee.status == EmployeeStatus.ACTIVE,
        )
    )).scalars().all())


async def _resolve_scope(
    db: AsyncSession,
    scope_type: str,
    scope_value: Optional[str],
    employee_ids: Optional[List[int]],
    grantee_id: Optional[int],
) -> set:
    if scope_type == DelegationScope.EMPLOYEES:
        want = {int(i) for i in (employee_ids or [])}
        return await _active_employee_user_ids(db, want)
    if scope_type == DelegationScope.DEPARTMENT and scope_value:
        col = Employee.department
    elif scope_type == DelegationScope.LOCATION and scope_value:
        col = Employee.location
    elif scope_type == DelegationScope.TEAM and grantee_id is not None:
        rows = set((await db.execute(
            select(User.id).where(User.manager_id == grantee_id)
        )).scalars().all())
        return await _active_employee_user_ids(db, rows)
    else:
        return set()
    rows = (await db.execute(
        select(Employee.user_id).where(
            col == scope_value,
            Employee.status == EmployeeStatus.ACTIVE,
            Employee.user_id.is_not(None),
        )
    )).scalars().all()
    return set(rows)


async def active_delegations(
    db: AsyncSession, user: User, on: Optional[pydate] = None
) -> List[ScheduleDelegation]:
    # Validity dates are evaluated in UTC (project convention).
    on = on or datetime.now(timezone.utc).date()
    return list((await db.execute(
        select(ScheduleDelegation).where(
            ScheduleDelegation.grantee_id == user.id,
            ScheduleDelegation.revoked_at.is_(None),
            ScheduleDelegation.valid_from <= on,
            or_(
                ScheduleDelegation.valid_to.is_(None),
                ScheduleDelegation.valid_to >= on,
            ),
        )
    )).scalars().all())


async def delegation_user_ids(
    db: AsyncSession, d: ScheduleDelegation
) -> set:
    return await resolve_scope_user_ids(
        db, d.scope_type, d.scope_value, d.employee_ids, d.grantee_id
    )


async def delegated_user_ids(db: AsyncSession, user: User) -> set:
    ids: set = set()
    for d in await active_delegations(db, user):
        ids |= await delegation_user_ids(db, d)
    return ids


async def scoped_employees(
    db: AsyncSession, user: User, department: Optional[str] = None
) -> List[Employee]:
    """Active Employee rows (user eager-loaded) the user may plan for:
    admin => all; else heads' departments plus delegated employees."""
    dept_names = await scope_department_names(db, user)
    q = (
        select(Employee)
        .options(selectinload(Employee.user))
        .where(Employee.status == EmployeeStatus.ACTIVE)
    )
    if dept_names is not None:
        delegated = await delegated_user_ids(db, user)
        conds = []
        if dept_names:
            conds.append(Employee.department.in_(dept_names))
        if delegated:
            conds.append(Employee.user_id.in_(delegated))
        if not conds:
            return []
        q = q.where(or_(*conds))
    if department:
        q = q.where(Employee.department == department)
    return list((await db.execute(q)).scalars().all())


async def _scope_user_ids(
    db: AsyncSession, user: User, flag: Optional[str], within: Optional[set] = None,
) -> set:
    """User ids a non-admin `user` may act on: ACTIVE employees of the
    departments they head, plus those covered by an active delegation (with
    `flag` set when given). `within` optionally restricts the lookup."""
    ok: set = set()
    dept_names = await scope_department_names(db, user)
    if dept_names:
        q = select(Employee.user_id).where(
            Employee.department.in_(dept_names),
            Employee.status == EmployeeStatus.ACTIVE,
            Employee.user_id.is_not(None),
        )
        if within is not None:
            q = q.where(Employee.user_id.in_(within))
        ok |= set((await db.execute(q)).scalars().all())
    for d in await active_delegations(db, user):
        if within is not None and within <= ok:
            break
        if flag is None or getattr(d, flag):
            ok |= await delegation_user_ids(db, d)
    return ok if within is None else ok & within


async def _subset(
    db: AsyncSession, user: User, user_ids, flag: Optional[str]
) -> set:
    """Subset of `user_ids` (User ids) that `user` may act on. Admin: all."""
    ids = set(user_ids)
    if not ids or is_roster_admin(user):
        return ids
    return await _scope_user_ids(db, user, flag, ids)


async def manageable_subset(db: AsyncSession, user: User, user_ids) -> set:
    return await _subset(db, user, user_ids, None)


async def publishable_subset(db: AsyncSession, user: User, user_ids) -> set:
    """Heads/admins publish directly; delegates only with `can_publish`."""
    return await _subset(db, user, user_ids, "can_publish")


async def approvable_subset(db: AsyncSession, user: User, user_ids) -> set:
    return await _subset(db, user, user_ids, "can_approve_changes")


async def can_manage_employee(
    db: AsyncSession, user: User, employee_user_id: int
) -> bool:
    return employee_user_id in await manageable_subset(db, user, {employee_user_id})


async def can_publish_for(
    db: AsyncSession, user: User, employee_user_id: int
) -> bool:
    return employee_user_id in await publishable_subset(db, user, {employee_user_id})


async def can_approve_changes_for(
    db: AsyncSession, user: User, employee_user_id: int
) -> bool:
    return employee_user_id in await approvable_subset(db, user, {employee_user_id})


async def approvable_user_ids(db: AsyncSession, user: User) -> set:
    """All user ids whose change requests `user` may decide (non-admin)."""
    ids = await _scope_user_ids(db, user, "can_approve_changes")
    ids.discard(user.id)
    return ids


async def schedule_approver_ids(db: AsyncSession, employee_user_ids: set) -> set:
    """Users who can actually decide a swap between these employees, i.e.
    exactly those the decide endpoint accepts. Candidates (delegates whose
    scope touches any of them, heads/deputies of their departments) are
    filtered to ACTIVE users with approvable_subset == all employees. If none
    qualify, ACTIVE roster admins. The employees themselves are excluded."""
    from app.models.user import Permission, Role

    ids = set(employee_user_ids)
    cands: set = set()
    today = datetime.now(timezone.utc).date()
    for d in (await db.execute(
        select(ScheduleDelegation).where(
            ScheduleDelegation.can_approve_changes.is_(True),
            ScheduleDelegation.revoked_at.is_(None),
            ScheduleDelegation.valid_from <= today,
            or_(ScheduleDelegation.valid_to.is_(None),
                ScheduleDelegation.valid_to >= today),
        )
    )).scalars().all():
        if ids & await delegation_user_ids(db, d):
            cands.add(d.grantee_id)
    depts = set((await db.execute(
        select(Employee.department).where(Employee.user_id.in_(ids))
    )).scalars().all()) if ids else set()
    depts.discard(None)
    if depts:
        for h in (await db.execute(
            select(Department.head_user_id, Department.deputy_head_user_id)
            .where(Department.name.in_(depts))
        )).all():
            cands |= {x for x in h if x}
    cands -= ids
    out: set = set()
    for uid in sorted(cands):
        u = await db.get(User, uid)
        if u is None or not u.is_active:
            continue
        if await approvable_subset(db, u, ids) == ids:
            out.add(uid)
    if out:
        return out
    admins = set((await db.execute(
        select(User.id).where(User.is_active.is_(True), User.is_superuser.is_(True))
    )).scalars().all())
    admins |= set((await db.execute(
        select(User.id).join(User.roles).join(Role.permissions)
        .where(User.is_active.is_(True), Permission.name == PERM_ROSTER)
    )).scalars().all())
    return admins - ids


def expand_pattern(
    pattern: Dict[int, Optional[int]], start: pydate, end: pydate
) -> List[Tuple[pydate, Optional[int], bool]]:
    """Weekday->template map applied across [start, end]. A weekday absent
    from the pattern is left untouched; a weekday mapped to None becomes an
    explicit week-off."""
    out: List[Tuple[pydate, Optional[int], bool]] = []
    d = start
    while d <= end:
        if d.weekday() in pattern:
            tpl = pattern[d.weekday()]
            out.append((d, tpl, tpl is None))
        d += timedelta(days=1)
    return out


def expand_rotation(
    cycle: List[Optional[int]], anchor: pydate, start: pydate, end: pydate,
    offset: int = 0,
) -> List[Tuple[pydate, Optional[int], bool]]:
    """Day d gets cycle[((d - anchor).days + offset) % len(cycle)]. Returns
    (date, template_id, is_week_off) for every day in [start, end]; a None
    cycle slot is a week-off."""
    n = len(cycle)
    out: List[Tuple[pydate, Optional[int], bool]] = []
    d = start
    while d <= end:
        tpl = cycle[((d - anchor).days + offset) % n]
        out.append((d, tpl, tpl is None))
        d += timedelta(days=1)
    return out


async def upsert_entry(
    db: AsyncSession,
    *,
    employee_id: int,
    work_date: pydate,
    shift_template_id: Optional[int],
    is_week_off: bool,
    status: str,
    actor_id: Optional[int],
    department: Optional[str],
    overwrite: bool,
    protect_published: bool = False,
    existing_map: Optional[Dict[Tuple[int, pydate], RosterEntry]] = None,
) -> Tuple[RosterEntry, str]:
    """Create or update the single roster cell for (employee, date). Returns
    (entry, 'created'|'updated'|'skipped'). A week-off cell never carries a
    shift template. When `existing_map` is given it is used instead of a
    per-cell SELECT (and newly created entries are added to it)."""
    if is_week_off:
        shift_template_id = None
    key = (employee_id, work_date)
    if existing_map is not None:
        existing = existing_map.get(key)
    else:
        existing = (await db.execute(
            select(RosterEntry).where(
                RosterEntry.employee_id == employee_id,
                RosterEntry.work_date == work_date,
            )
        )).scalars().first()
    if existing is not None:
        if not overwrite:
            return existing, "skipped"
        if protect_published and existing.status == RosterStatus.PUBLISHED:
            # A non-publisher must not alter (or downgrade) a live cell.
            return existing, "skipped"
        existing.shift_template_id = shift_template_id
        existing.is_week_off = is_week_off
        existing.status = status
        existing.assigned_by_id = actor_id
        if department is not None:
            existing.department = department
        return existing, "updated"
    entry = RosterEntry(
        employee_id=employee_id,
        work_date=work_date,
        shift_template_id=shift_template_id,
        is_week_off=is_week_off,
        status=status,
        department=department,
        assigned_by_id=actor_id,
    )
    db.add(entry)
    if existing_map is not None:
        existing_map[key] = entry
    return entry, "created"


async def prefetch_entries(
    db: AsyncSession, user_ids, start: pydate, end: pydate, chunk: int = 500
) -> Dict[Tuple[int, pydate], RosterEntry]:
    out: Dict[Tuple[int, pydate], RosterEntry] = {}
    ids = sorted(set(user_ids))
    for i in range(0, len(ids), chunk):
        rows = (await db.execute(
            select(RosterEntry).where(
                RosterEntry.employee_id.in_(ids[i:i + chunk]),
                RosterEntry.work_date >= start,
                RosterEntry.work_date <= end,
            )
        )).scalars().all()
        for r in rows:
            out[(r.employee_id, r.work_date)] = r
    return out


async def load_planner_cells(
    db: AsyncSession, user_ids, start: pydate, end: pydate, chunk: int = 500
):
    """Batched, column-only load of everything needed to resolve planner
    cells. Returns (entries_by_(uid, date), assignments_by_uid); entries
    carry id/employee_id/work_date/shift_template_id/is_week_off/status and
    assignments are ordered newest effective_from first."""
    entries: Dict[Tuple[int, pydate], object] = {}
    asgs: Dict[int, list] = {}
    ids = sorted(set(user_ids))
    for i in range(0, len(ids), chunk):
        part = ids[i:i + chunk]
        for r in (await db.execute(
            select(
                RosterEntry.id, RosterEntry.employee_id, RosterEntry.work_date,
                RosterEntry.shift_template_id, RosterEntry.is_week_off,
                RosterEntry.status,
            ).where(
                RosterEntry.employee_id.in_(part),
                RosterEntry.work_date >= start,
                RosterEntry.work_date <= end,
            )
        )).all():
            entries[(r.employee_id, r.work_date)] = r
        for a in (await db.execute(
            select(
                EmployeeShiftAssignment.employee_id,
                EmployeeShiftAssignment.shift_template_id,
                EmployeeShiftAssignment.effective_from,
                EmployeeShiftAssignment.effective_to,
            ).where(
                EmployeeShiftAssignment.employee_id.in_(part),
                EmployeeShiftAssignment.effective_from <= end,
                or_(
                    EmployeeShiftAssignment.effective_to.is_(None),
                    EmployeeShiftAssignment.effective_to >= start,
                ),
            ).order_by(EmployeeShiftAssignment.effective_from.desc())
        )).all():
            asgs.setdefault(a.employee_id, []).append(a)
    return entries, asgs


def active_assignment(asgs, d: pydate):
    return next(
        (a for a in asgs
         if a.effective_from <= d
         and (a.effective_to is None or a.effective_to >= d)),
        None,
    )


def resolve_working_template(
    entry, asgs, templates, d: pydate
) -> Optional[int]:
    """Template id the employee actually works on `d`, else None.
    Planner semantics (drafts count): a week-off entry is never working; an
    entry with a template wins; a blank entry or no entry falls back to the
    assignment (not working on the template's weekly off)."""
    if entry is not None:
        if entry.is_week_off:
            return None
        if entry.shift_template_id is not None:
            return entry.shift_template_id
    asg = active_assignment(asgs or (), d)
    if asg is None:
        return None
    t = templates.get(asg.shift_template_id)
    if t is None or d.weekday() in (t.weekly_offs or []):
        return None
    return asg.shift_template_id


async def approved_leave_days(
    db: AsyncSession, user_ids, start: pydate, end: pydate, chunk: int = 500
) -> set:
    """(user_id, date) pairs covered by APPROVED full-day leave."""
    out: set = set()
    ids = sorted(set(user_ids))
    for i in range(0, len(ids), chunk):
        for lv in (await db.execute(
            select(
                LeaveRequest.employee_id, LeaveRequest.start_date,
                LeaveRequest.end_date,
            ).where(
                LeaveRequest.employee_id.in_(ids[i:i + chunk]),
                LeaveRequest.status == LeaveStatus.APPROVED,
                LeaveRequest.is_half_day.is_(False),
                LeaveRequest.start_date <= end,
                LeaveRequest.end_date >= start,
            )
        )).all():
            d = max(lv.start_date, start)
            last = min(lv.end_date, end)
            while d <= last:
                out.add((lv.employee_id, d))
                d += timedelta(days=1)
    return out


def visible_requirements(
    reqs, *, admin: bool, scoped_departments, department: Optional[str]
):
    """Coverage requirements a viewer may see: admin => all (optionally
    narrowed to `department` or all-department ones); others => those whose
    department is NULL or one of their scoped departments."""
    out = []
    for r in reqs:
        if department and r.department not in (None, department):
            continue
        if not admin and r.department is not None \
                and r.department not in scoped_departments:
            continue
        out.append(r)
    return out


def _hhmm(t) -> Optional[str]:
    return t.strftime("%H:%M") if t is not None else None


async def build_grid(
    db: AsyncSession,
    user: User,
    start: pydate,
    end: pydate,
    department: Optional[str] = None,
    employees: Optional[List[Employee]] = None,
):
    """Employees x dates grid. Cells prefer a RosterEntry; empty cells fall
    back to the effective EmployeeShiftAssignment (DISPLAY ONLY) so planners
    see the current baseline. No phantom rows are written on read."""
    from app.schemas.roster import (
        RosterGridResponse, RosterGridRow, RosterCell, ShiftTemplateLite,
    )

    if employees is None:
        employees = await scoped_employees(db, user, department)
    admin = is_roster_admin(user)
    user_ids = [e.user_id for e in employees]

    dates: List[pydate] = []
    d = start
    while d <= end:
        dates.append(d)
        d += timedelta(days=1)

    templates = list((await db.execute(
        select(ShiftTemplate).where(ShiftTemplate.is_active.is_(True))
        .order_by(ShiftTemplate.name)
    )).scalars().all())
    tpl_by_id = {t.id: t for t in templates}

    entries_by_key, asg_by_user = await load_planner_cells(
        db, user_ids, start, end
    )

    grid_rows: List[RosterGridRow] = []
    for emp in employees:
        uid = emp.user_id
        cells: List[RosterCell] = []
        for dt in dates:
            entry = entries_by_key.get((uid, dt))
            if entry is not None:
                tpl = tpl_by_id.get(entry.shift_template_id)
                cells.append(RosterCell(
                    work_date=dt,
                    shift_template_id=entry.shift_template_id,
                    is_week_off=entry.is_week_off,
                    status=entry.status,
                    entry_id=entry.id,
                    source="roster",
                    shift_name=tpl.name if tpl else None,
                ))
                continue
            # Fallback: effective assignment for the date (display only).
            asg = active_assignment(asg_by_user.get(uid, []), dt)
            if asg is not None:
                tpl = tpl_by_id.get(asg.shift_template_id)
                cells.append(RosterCell(
                    work_date=dt,
                    shift_template_id=asg.shift_template_id,
                    is_week_off=False,
                    status=None,
                    entry_id=None,
                    source="assignment",
                    shift_name=tpl.name if tpl else None,
                ))
            else:
                cells.append(RosterCell(work_date=dt, source="empty"))
        grid_rows.append(RosterGridRow(
            employee_id=uid,
            full_name=emp.user.full_name if emp.user else None,
            department=emp.department,
            designation=emp.designation,
            in_scope=True,
            cells=cells,
        ))

    pub = await publishable_subset(db, user, set(user_ids))
    can_pub = admin or (bool(user_ids) and set(user_ids) <= pub)

    return RosterGridResponse(
        start=start,
        end=end,
        dates=dates,
        shift_templates=[
            ShiftTemplateLite(
                id=t.id, name=t.name,
                start_time=_hhmm(t.start_time), end_time=_hhmm(t.end_time),
                is_overnight=t.is_overnight,
            ) for t in templates
        ],
        rows=grid_rows,
        is_admin=admin,
        can_publish=can_pub,
    )


# ---------------- change history / notifications / publish ----------------

def record_change(
    db: AsyncSession, entry: Optional[RosterEntry], *,
    employee_id: int, work_date: pydate,
    old_tpl: Optional[int], old_off: bool,
    new_tpl: Optional[int], new_off: bool,
    action: str, reason: Optional[str], actor_id: Optional[int],
) -> RosterEntryHistory:
    """Add one history row (caller commits). For deletes pass entry=None."""
    row = RosterEntryHistory(
        employee_id=employee_id, work_date=work_date,
        roster_entry_id=entry.id if entry is not None else None,
        old_shift_template_id=old_tpl, old_is_week_off=bool(old_off),
        new_shift_template_id=new_tpl, new_is_week_off=bool(new_off),
        action=action, reason=reason[:500] if reason else None,
        changed_by_id=actor_id,
    )
    db.add(row)
    return row


def edit_changes_live(
    old_tpl: Optional[int], old_off: bool,
    new_tpl: Optional[int], new_off: bool, still_published: bool,
) -> bool:
    """True when an edit to a PUBLISHED cell alters what the employee sees
    (shift/week-off differs, or the cell leaves the live schedule)."""
    if new_off:
        new_tpl = None
    return (old_tpl, bool(old_off)) != (new_tpl, bool(new_off)) \
        or not still_published


def clean_reason(reason: Optional[str]) -> Optional[str]:
    r = (reason or "").strip()
    return r if len(r) >= 3 else None


def format_dates(dates) -> str:
    """Compact list: consecutive days collapse to 'a to b'; after 10 dates
    shown, '+N more'."""
    ds = sorted(set(dates))
    runs: List[List[pydate]] = []
    for d in ds:
        if runs and (d - runs[-1][-1]).days == 1:
            runs[-1].append(d)
        else:
            runs.append([d])
    parts: List[str] = []
    shown = 0
    for r in runs:
        if shown >= 10:
            break
        take = r[: 10 - shown]
        shown += len(take)
        parts.append(
            take[0].isoformat() if len(take) == 1
            else f"{take[0].isoformat()} to {take[-1].isoformat()}"
        )
    out = ", ".join(parts)
    if len(ds) > shown:
        out += f" +{len(ds) - shown} more"
    return out


async def notify(
    db: AsyncSession, user_id: Optional[int], title: str, message: str,
    resource_type: str = "roster", resource_id: Optional[str] = None,
) -> None:
    """Best-effort in-app notification; never breaks the request."""
    if not user_id:
        return
    try:
        async with db.begin_nested():
            db.add(Notification(
                user_id=user_id, title=title[:200], message=message[:1000],
                type="info", resource_type=resource_type,
                resource_id=resource_id,
            ))
    except Exception:  # pragma: no cover
        logger.warning("roster notification failed", exc_info=True)


async def notify_many(db: AsyncSession, rows) -> None:
    """Best-effort batch of in-app notifications. `rows` are
    (user_id, title, message, resource_type, resource_id) tuples. One
    savepoint for the whole batch; if it fails, fall back to per-row so one
    bad row cannot drop the rest."""
    rows = [r for r in rows if r[0]]
    if not rows:
        return
    objs = [
        Notification(
            user_id=uid, title=title[:200], message=msg[:1000], type="info",
            resource_type=rtype, resource_id=rid,
        ) for (uid, title, msg, rtype, rid) in rows
    ]
    try:
        async with db.begin_nested():
            db.add_all(objs)
        return
    except Exception:  # pragma: no cover
        logger.warning("roster batch notification failed", exc_info=True)
    for (uid, title, msg, rtype, rid) in rows:
        await notify(db, uid, title, msg, rtype, rid)


async def notify_schedule_changed(
    db: AsyncSession, changed: Dict[int, set]
) -> None:
    """One notification per affected employee."""
    await notify_many(db, [
        (uid, "Schedule changed",
         f"Your schedule changed for {format_dates(changed[uid])}",
         "roster", None)
        for uid in sorted(changed)
    ])


def is_lock_conflict(exc: Exception) -> bool:
    """MariaDB 1020 (snapshot isolation: row changed since our snapshot) or
    1213 (deadlock): a concurrent writer won; the caller can retry."""
    orig = getattr(exc, "orig", None)
    return bool(orig is not None and orig.args and orig.args[0] in (1020, 1213))


async def publish_drafts(
    db: AsyncSession, actor: User, user_ids, start: pydate, end: pydate,
) -> dict:
    """Flip DRAFT -> PUBLISHED in [start, end] for the employees in
    `user_ids` that `actor` may publish for. Drafts are row-locked (ordered
    by id) and only rows actually locked as DRAFT get a history row, so a
    concurrent publish of the same window is a no-op for the loser. Writes
    one notification per employee. Caller commits."""
    ids = sorted(set(user_ids))
    pub = await publishable_subset(db, actor, ids)
    pub_ids = sorted(pub)
    todo: List[RosterEntry] = []
    try:
        for i in range(0, len(pub_ids), 500):
            todo.extend((await db.execute(
                select(RosterEntry).where(
                    RosterEntry.employee_id.in_(pub_ids[i:i + 500]),
                    RosterEntry.work_date >= start,
                    RosterEntry.work_date <= end,
                    RosterEntry.status == RosterStatus.DRAFT,
                ).order_by(RosterEntry.id).with_for_update()
                .execution_options(populate_existing=True)
            )).scalars().all())
    except OperationalError as exc:
        # a concurrent publish won; the caller can retry.
        if is_lock_conflict(exc):
            await db.rollback()
            raise HTTPException(
                status_code=409, detail="Roster changed concurrently; retry"
            )
        raise
    others = [i for i in ids if i not in pub]
    not_permitted: set = set()
    for i in range(0, len(others), 500):
        not_permitted |= set((await db.execute(
            select(RosterEntry.employee_id).where(
                RosterEntry.employee_id.in_(others[i:i + 500]),
                RosterEntry.work_date >= start,
                RosterEntry.work_date <= end,
                RosterEntry.status == RosterStatus.DRAFT,
            ).distinct()
        )).scalars().all())
    now = datetime.now(timezone.utc)
    for i in range(0, len(todo), 500):
        await db.execute(
            update(RosterEntry)
            .where(
                RosterEntry.id.in_([d.id for d in todo[i:i + 500]]),
                RosterEntry.status == RosterStatus.DRAFT,
            )
            .values(status=RosterStatus.PUBLISHED, updated_at=now)
            .execution_options(synchronize_session=False)
        )
    db.add_all([
        RosterEntryHistory(
            employee_id=d.employee_id, work_date=d.work_date,
            roster_entry_id=d.id,
            old_shift_template_id=None, old_is_week_off=False,
            new_shift_template_id=d.shift_template_id,
            new_is_week_off=d.is_week_off,
            action="publish", reason=None, changed_by_id=actor.id,
        ) for d in todo
    ])
    employees = sorted({d.employee_id for d in todo})
    await notify_many(db, [
        (uid, "Schedule published",
         f"Your schedule for {start.isoformat()}\u2013{end.isoformat()} "
         "is published", "roster", None)
        for uid in employees
    ])
    return {
        "published": len(todo),
        "employees": len(employees),
        "not_permitted": sorted(not_permitted),
    }
