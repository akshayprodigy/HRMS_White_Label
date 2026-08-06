"""Roster planner service (W7).

All scope enforcement lives here so every roster endpoint shares one
definition of "who can a planner touch": superusers / `roster manage`
holders see everyone; functional heads (F1) see only the employees in the
departments they head. `employee_id` throughout is a User id, matching
EmployeeShiftAssignment.
"""
from __future__ import annotations

from datetime import date as pydate, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.department import Department
from app.models.employee import Employee, EmployeeStatus
from app.models.roster import RosterEntry, RosterStatus
from app.models.shift import EmployeeShiftAssignment, ShiftTemplate
from app.models.user import User
from app.services import functional_head as fh

PERM_ROSTER = "roster manage"


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


async def scoped_employees(
    db: AsyncSession, user: User, department: Optional[str] = None
) -> List[Employee]:
    """Active Employee rows (user eager-loaded) the user may plan for."""
    dept_names = await scope_department_names(db, user)
    q = (
        select(Employee)
        .options(selectinload(Employee.user))
        .where(Employee.status == EmployeeStatus.ACTIVE)
    )
    if dept_names is not None:
        if not dept_names:
            return []
        q = q.where(Employee.department.in_(dept_names))
    if department:
        q = q.where(Employee.department == department)
    return list((await db.execute(q)).scalars().all())


async def can_manage_employee(
    db: AsyncSession, user: User, employee_user_id: int
) -> bool:
    if is_roster_admin(user):
        return True
    emp = (await db.execute(
        select(Employee).where(Employee.user_id == employee_user_id)
    )).scalars().first()
    if emp is None:
        return False
    return await fh.is_head_of(db, user, emp)


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
) -> Tuple[RosterEntry, str]:
    """Create or update the single roster cell for (employee, date). Returns
    (entry, 'created'|'updated'|'skipped')."""
    existing = (await db.execute(
        select(RosterEntry).where(
            RosterEntry.employee_id == employee_id,
            RosterEntry.work_date == work_date,
        )
    )).scalars().first()
    if existing is not None:
        if not overwrite:
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
    return entry, "created"


def _hhmm(t) -> Optional[str]:
    return t.strftime("%H:%M") if t is not None else None


async def build_grid(
    db: AsyncSession,
    user: User,
    start: pydate,
    end: pydate,
    department: Optional[str] = None,
):
    """Employees x dates grid. Cells prefer a RosterEntry; empty cells fall
    back to the effective EmployeeShiftAssignment (DISPLAY ONLY) so planners
    see the current baseline. No phantom rows are written on read."""
    from app.schemas.roster import (
        RosterGridResponse, RosterGridRow, RosterCell, ShiftTemplateLite,
    )

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

    # One query for all roster entries in the window.
    entries_by_key: Dict[Tuple[int, pydate], RosterEntry] = {}
    if user_ids:
        rows = (await db.execute(
            select(RosterEntry).where(
                RosterEntry.employee_id.in_(user_ids),
                RosterEntry.work_date >= start,
                RosterEntry.work_date <= end,
            )
        )).scalars().all()
        for r in rows:
            entries_by_key[(r.employee_id, r.work_date)] = r

    # One query for all assignments overlapping the window (fallback).
    asg_by_user: Dict[int, list] = {}
    if user_ids:
        arows = (await db.execute(
            select(EmployeeShiftAssignment)
            .where(
                EmployeeShiftAssignment.employee_id.in_(user_ids),
                EmployeeShiftAssignment.effective_from <= end,
                or_(
                    EmployeeShiftAssignment.effective_to.is_(None),
                    EmployeeShiftAssignment.effective_to >= start,
                ),
            )
            .order_by(EmployeeShiftAssignment.effective_from.desc())
        )).scalars().all()
        for a in arows:
            asg_by_user.setdefault(a.employee_id, []).append(a)

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
            asg = next(
                (a for a in asg_by_user.get(uid, [])
                 if a.effective_from <= dt
                 and (a.effective_to is None or a.effective_to >= dt)),
                None,
            )
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
    )
