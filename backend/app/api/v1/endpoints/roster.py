"""Roster planner API (W7), mounted at /roster (attendance-gated).

Write access is scoped through services/roster.py: superusers / `roster
manage` holders touch everyone, functional heads only their team. Plain
employees use the /my* + /change-requests* self-service paths.

PRECEDENCE: this is a planning layer. Published roster entries do NOT feed
attendance / overtime / payroll (those still read EmployeeShiftAssignment).
"""
from datetime import date as pydate, datetime, timedelta, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.api import deps
from app.api.v1.endpoints.hr import log_audit
from app.models.employee import Employee
from app.models.roster import (
    RosterEntry, RosterChangeRequest, RosterStatus, RosterChangeStatus,
)
from app.models.shift import EmployeeShiftAssignment, ShiftTemplate
from app.models.user import User
from app.schemas.roster import (
    RosterGridResponse, RosterBulkRequest, RosterBulkResult,
    RosterEntryInput, RosterEntryRead, RosterEntryUpdate,
    RosterChangeRequestCreate, RosterChangeRequestRead, RosterChangeDecision,
    RotationPatternCreate, RotationPatternUpdate, RotationPatternRead,
    RotationApplyRequest,
)
from app.models.rotation_pattern import RotationPattern
from app.models.coverage_requirement import CoverageRequirement
from app.models.leave import LeaveRequest, LeaveStatus
from app.schemas.roster import (
    RosterInsightsResponse, ViolationRead, CoverageCellRead,
    CoverageRequirementCreate, CoverageRequirementUpdate,
    CoverageRequirementRead,
)
from app.services import schedule_rules
from app.services.time_rules import get_time_rules
from app.services import roster as roster_svc

router = APIRouter()


# ----------------------------- helpers -----------------------------

async def _entry_read(db, entry: RosterEntry) -> RosterEntryRead:
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


async def _require_manage(db, user: User, employee_user_id: int) -> None:
    if not await roster_svc.can_manage_employee(db, user, employee_user_id):
        raise HTTPException(
            status_code=403,
            detail="This employee is outside your roster scope.",
        )


NO_PUBLISH_MSG = "Publishing requires HR approval for this employee"
DRAFT_NOTICE = "Saved as draft: publishing requires HR approval"


async def _commit_or_409(
    db, msg: str = "Roster changed concurrently; retry"
) -> None:
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail=msg)


async def _validate_templates(db, ids) -> None:
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


async def _write_cells(
    db, user: User, allowed: set, cells, status: str, overwrite: bool,
    result: RosterBulkResult,
) -> None:
    """Write (uid, date, tpl, week_off) cells for `allowed` employees.
    Publish rights are resolved ONCE; non-publishers' cells are saved as
    draft (one message per employee) and never overwrite a live cell."""
    pub = await roster_svc.publishable_subset(db, user, allowed)
    dept_by_uid = {
        e.user_id: e.department
        for e in (await db.execute(
            select(Employee).where(Employee.user_id.in_(allowed))
        )).scalars().all()
    }
    downgraded: set = set()
    cells = list(cells)
    existing_map = (
        await roster_svc.prefetch_entries(
            db, allowed, min(c[1] for c in cells), max(c[1] for c in cells)
        ) if cells else {}
    )
    for (uid, wd, tpl_id, week_off) in cells:
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
                protect_published=not can_pub, existing_map=existing_map,
            )
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
    if downgraded:
        names = {
            u.id: u.full_name for u in (await db.execute(
                select(User).where(User.id.in_(downgraded))
            )).scalars().all()
        }
        for uid in sorted(downgraded):
            result.errors.append(
                f"Saved as draft for {names.get(uid) or uid}: "
                "publishing requires HR approval"
            )


# ----------------------------- planner -----------------------------

@router.get("/plan", response_model=RosterGridResponse)
async def get_plan(
    db: deps.DBDep,
    start: pydate = Query(...),
    end: pydate = Query(...),
    department: Optional[str] = None,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    if start > end:
        raise HTTPException(status_code=400, detail="start must be <= end")
    if (end - start).days > 62:
        raise HTTPException(status_code=400, detail="range too large (max 62 days)")
    if not roster_svc.is_roster_admin(current_user):
        if not await roster_svc.scoped_employees(db, current_user):
            raise HTTPException(
                status_code=403, detail="You have no roster scope.",
            )
    return await roster_svc.build_grid(db, current_user, start, end, department)


@router.get("/insights", response_model=RosterInsightsResponse)
async def get_insights(
    db: deps.DBDep,
    start: pydate = Query(...),
    end: pydate = Query(...),
    department: Optional[str] = None,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Work-rule violations + coverage for the planner view: DRAFT and
    PUBLISHED entries both count; empty cells fall back to assignments."""
    if start > end:
        raise HTTPException(status_code=400, detail="start must be <= end")
    if (end - start).days > 62:
        raise HTTPException(status_code=400, detail="range too large (max 62 days)")
    if not roster_svc.is_roster_admin(current_user):
        if not await roster_svc.scoped_employees(db, current_user):
            raise HTTPException(
                status_code=403, detail="You have no roster scope.",
            )
    employees = await roster_svc.scoped_employees(db, current_user, department)
    uids = [e.user_id for e in employees]
    name_by_uid = {
        e.user_id: (e.user.full_name if e.user else None) for e in employees
    }
    emp_meta = {e.user_id: (e.department, e.location) for e in employees}
    w_start, w_end = start - timedelta(days=7), end + timedelta(days=1)

    templates = {t.id: t for t in (await db.execute(
        select(ShiftTemplate)
    )).scalars().all()}

    entries: dict = {}
    asg_by_user: dict = {}
    leave_days: set = set()
    if uids:
        for r in (await db.execute(
            select(RosterEntry).where(
                RosterEntry.employee_id.in_(uids),
                RosterEntry.work_date >= w_start,
                RosterEntry.work_date <= w_end,
            )
        )).scalars().all():
            entries[(r.employee_id, r.work_date)] = r
        for a in (await db.execute(
            select(EmployeeShiftAssignment).where(
                EmployeeShiftAssignment.employee_id.in_(uids),
                EmployeeShiftAssignment.effective_from <= w_end,
                or_(
                    EmployeeShiftAssignment.effective_to.is_(None),
                    EmployeeShiftAssignment.effective_to >= w_start,
                ),
            ).order_by(EmployeeShiftAssignment.effective_from.desc())
        )).scalars().all():
            asg_by_user.setdefault(a.employee_id, []).append(a)
        for lv in (await db.execute(
            select(LeaveRequest).where(
                LeaveRequest.employee_id.in_(uids),
                LeaveRequest.status == LeaveStatus.APPROVED,
                LeaveRequest.is_half_day.is_(False),
                LeaveRequest.start_date <= w_end,
                LeaveRequest.end_date >= w_start,
            )
        )).scalars().all():
            d = max(lv.start_date, w_start)
            last = min(lv.end_date, w_end)
            while d <= last:
                leave_days.add((lv.employee_id, d))
                d += timedelta(days=1)

    cells = []
    for uid in uids:
        d = w_start
        while d <= w_end:
            entry = entries.get((uid, d))
            tid = None
            if entry is not None and (entry.shift_template_id or entry.is_week_off):
                tid = entry.shift_template_id  # week-off => None => not working
            else:
                asg = next(
                    (a for a in asg_by_user.get(uid, [])
                     if a.effective_from <= d
                     and (a.effective_to is None or a.effective_to >= d)),
                    None,
                )
                if asg is not None:
                    t = templates.get(asg.shift_template_id)
                    if t is not None and d.weekday() not in (t.weekly_offs or []):
                        tid = asg.shift_template_id
            if tid is not None:
                cells.append((uid, d, tid))
            d += timedelta(days=1)

    spans = schedule_rules.build_spans(cells, templates)
    raw = await get_time_rules(db)

    def _rule(key: str) -> int:
        try:
            return max(0, int(raw.get(f"schedule.{key}", "0")))
        except (TypeError, ValueError):
            return 0

    rules = {k: _rule(k) for k in (
        "min_rest_hours", "max_consecutive_days",
        "max_consecutive_nights", "max_weekly_hours",
    )}
    viols = schedule_rules.check_rules(spans, rules)
    viols += schedule_rules.check_leave_conflicts(spans, leave_days)
    viols = [v for v in viols if start <= v.work_date <= end]
    viols.sort(key=lambda v: (v.work_date, v.user_id, v.rule))

    reqs = list((await db.execute(
        select(CoverageRequirement).where(
            CoverageRequirement.is_active.is_(True)
        )
    )).scalars().all())
    if department:
        reqs = [r for r in reqs if r.department in (None, department)]
    dates = []
    d = start
    while d <= end:
        dates.append(d)
        d += timedelta(days=1)
    in_range = [s for s in spans if start <= s.work_date <= end]
    cov = schedule_rules.compute_coverage(in_range, reqs, emp_meta, dates)

    return RosterInsightsResponse(
        violations=[
            ViolationRead(
                user_id=v.user_id, employee_name=name_by_uid.get(v.user_id),
                work_date=v.work_date, rule=v.rule, message=v.message,
            ) for v in viols
        ],
        coverage=[
            CoverageCellRead(
                date=c.date, shift_template_id=c.shift_template_id,
                shift_name=(templates[c.shift_template_id].name
                            if c.shift_template_id in templates else None),
                department=c.department, location=c.location,
                required_min=c.required_min, required_max=c.required_max,
                scheduled=c.scheduled, status=c.status,
            ) for c in cov
        ],
    )


@router.post("/bulk", response_model=RosterBulkResult)
async def bulk_plan(
    *,
    db: deps.DBDep,
    request: Request,
    body: RosterBulkRequest,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Assign a pattern (weekday->template) or explicit entries across a
    range for a scoped team. Out-of-scope employees are reported, never
    written."""
    result = RosterBulkResult()
    await _validate_templates(
        db,
        [e.shift_template_id for e in (body.entries or [])]
        + list((body.pattern or {}).values()),
    )

    # Resolve target user ids
    if body.entries is not None:
        target_ids = {e.employee_id for e in body.entries}
    elif body.employee_ids is not None:
        target_ids = set(body.employee_ids)
    else:
        emps = await roster_svc.scoped_employees(
            db, current_user, body.department
        )
        target_ids = {e.user_id for e in emps}

    # Scope-filter
    allowed = await roster_svc.manageable_subset(db, current_user, target_ids)
    result.out_of_scope.extend(sorted(target_ids - allowed))

    if not allowed:
        return result

    if body.entries is not None:
        cells = [
            (ein.employee_id, ein.work_date,
             ein.shift_template_id, ein.is_week_off)
            for ein in body.entries if ein.employee_id in allowed
        ]
    else:
        pc = roster_svc.expand_pattern(body.pattern, body.start, body.end)
        cells = [
            (uid, wd, tpl_id, week_off)
            for uid in sorted(allowed) for (wd, tpl_id, week_off) in pc
        ]
    await _write_cells(
        db, current_user, allowed, cells, body.status, body.overwrite, result
    )

    await _commit_or_409(db)
    await log_audit(
        db, current_user.id, "roster.bulk_publish",
        "roster_entry", None,
        {
            "created": result.created,
            "updated": result.updated,
            "skipped": result.skipped,
            "out_of_scope": len(result.out_of_scope),
            "start": body.start.isoformat(),
            "end": body.end.isoformat(),
            "status": body.status,
        },
        request,
    )
    return result


@router.post("/entries", response_model=RosterEntryRead)
async def upsert_single_entry(
    *,
    db: deps.DBDep,
    request: Request,
    body: RosterEntryInput,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    await _require_manage(db, current_user, body.employee_id)
    await _validate_templates(db, [body.shift_template_id])
    emp = (await db.execute(
        select(Employee).where(Employee.user_id == body.employee_id)
    )).scalars().first()
    can_pub = await roster_svc.can_publish_for(
        db, current_user, body.employee_id
    )
    eff_status = (
        body.status if body.status == RosterStatus.DRAFT or can_pub
        else RosterStatus.DRAFT
    )
    entry, outcome = await roster_svc.upsert_entry(
        db,
        employee_id=body.employee_id,
        work_date=body.work_date,
        shift_template_id=body.shift_template_id,
        is_week_off=body.is_week_off,
        status=eff_status,
        actor_id=current_user.id,
        department=emp.department if emp else None,
        overwrite=True,
        protect_published=not can_pub,
    )
    if outcome == "skipped":
        raise HTTPException(status_code=403, detail=NO_PUBLISH_MSG)
    await _commit_or_409(db)
    await db.refresh(entry)
    await log_audit(
        db, current_user.id, "roster.entry.upsert",
        "roster_entry", str(entry.id),
        {"outcome": outcome, "work_date": body.work_date.isoformat()},
        request,
    )
    read = await _entry_read(db, entry)
    if body.status == RosterStatus.PUBLISHED and eff_status != body.status:
        read.notice = DRAFT_NOTICE
    return read


@router.patch("/entries/{entry_id}", response_model=RosterEntryRead)
async def update_entry(
    *,
    db: deps.DBDep,
    request: Request,
    entry_id: int,
    body: RosterEntryUpdate,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    entry = await db.get(RosterEntry, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Roster entry not found")
    await _require_manage(db, current_user, entry.employee_id)
    changes = body.model_dump(exclude_unset=True)
    for k in ("is_week_off", "status"):
        if k in changes and changes[k] is None:
            raise HTTPException(status_code=422, detail=f"{k} cannot be null")
    if "shift_template_id" in changes:
        await _validate_templates(db, [changes["shift_template_id"]])
    if "status" in changes and changes["status"] not in (
        RosterStatus.DRAFT, RosterStatus.PUBLISHED
    ):
        raise HTTPException(
            status_code=422, detail="status must be 'draft' or 'published'"
        )
    if not await roster_svc.can_publish_for(
        db, current_user, entry.employee_id
    ) and (
        entry.status == RosterStatus.PUBLISHED
        or changes.get("status") == RosterStatus.PUBLISHED
    ):
        raise HTTPException(status_code=403, detail=NO_PUBLISH_MSG)
    if changes.get("is_week_off") is True:
        changes["shift_template_id"] = None
    elif (
        changes.get("shift_template_id") is not None
        and "is_week_off" not in changes
    ):
        changes["is_week_off"] = False
    for k, v in changes.items():
        setattr(entry, k, v)
    if entry.is_week_off:
        entry.shift_template_id = None
    entry.assigned_by_id = current_user.id
    await _commit_or_409(db)
    await db.refresh(entry)
    await log_audit(
        db, current_user.id, "roster.entry.update",
        "roster_entry", str(entry.id),
        {"changed": list(changes.keys())}, request,
    )
    return await _entry_read(db, entry)


@router.delete("/entries/{entry_id}")
async def delete_entry(
    *,
    db: deps.DBDep,
    request: Request,
    entry_id: int,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    entry = await db.get(RosterEntry, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Roster entry not found")
    await _require_manage(db, current_user, entry.employee_id)
    if entry.status == RosterStatus.PUBLISHED and not (
        await roster_svc.can_publish_for(db, current_user, entry.employee_id)
    ):
        raise HTTPException(status_code=403, detail=NO_PUBLISH_MSG)
    await db.delete(entry)
    await db.commit()
    await log_audit(
        db, current_user.id, "roster.entry.delete",
        "roster_entry", str(entry_id), {}, request,
    )
    return {"status": "deleted", "id": entry_id}


# ----------------------------- rotation patterns -----------------------------

async def _validate_cycle(db, cycle) -> None:
    await _validate_templates(db, cycle)


def _require_admin(user: User) -> None:
    if not roster_svc.is_roster_admin(user):
        raise HTTPException(status_code=403, detail="HR/admin access required.")


async def _check_name(db, name: str, exclude_id: Optional[int] = None) -> None:
    q = select(RotationPattern).where(RotationPattern.name == name)
    if exclude_id is not None:
        q = q.where(RotationPattern.id != exclude_id)
    other = (await db.execute(q)).scalars().first()
    if other is not None:
        msg = "Pattern name already exists"
        if not other.is_active:
            msg += " (inactive) \u2014 reactivate it instead"
        raise HTTPException(status_code=409, detail=msg)


@router.get("/rotations", response_model=List[RotationPatternRead])
async def list_rotations(
    db: deps.DBDep,
    include_inactive: bool = Query(False),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    admin = roster_svc.is_roster_admin(current_user)
    if not admin and not await roster_svc.scoped_employees(db, current_user):
        raise HTTPException(status_code=403, detail="You have no roster scope.")
    q = select(RotationPattern).order_by(RotationPattern.name)
    if not (admin and include_inactive):
        q = q.where(RotationPattern.is_active.is_(True))
    return list((await db.execute(q)).scalars().all())


@router.post("/rotations", response_model=RotationPatternRead)
async def create_rotation(
    *,
    db: deps.DBDep,
    request: Request,
    body: RotationPatternCreate,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    _require_admin(current_user)
    await _validate_cycle(db, body.cycle)
    await _check_name(db, body.name)
    p = RotationPattern(
        name=body.name, description=body.description,
        cycle=list(body.cycle), created_by_id=current_user.id,
    )
    db.add(p)
    await _commit_or_409(db, "Rotation name already exists")
    await db.refresh(p)
    await log_audit(
        db, current_user.id, "roster.rotation.create",
        "rotation_pattern", str(p.id), {"name": p.name}, request,
    )
    return p


@router.patch("/rotations/{rotation_id}", response_model=RotationPatternRead)
async def update_rotation(
    *,
    db: deps.DBDep,
    request: Request,
    rotation_id: int,
    body: RotationPatternUpdate,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    _require_admin(current_user)
    p = await db.get(RotationPattern, rotation_id)
    if not p:
        raise HTTPException(status_code=404, detail="Rotation pattern not found")
    changes = body.model_dump(exclude_unset=True)
    if changes.get("name") is None:
        changes.pop("name", None)
    if changes.get("cycle") is None:
        changes.pop("cycle", None)
    if changes.get("is_active") is None:
        changes.pop("is_active", None)
    if "cycle" in changes:
        await _validate_cycle(db, changes["cycle"])
    if "name" in changes:
        await _check_name(db, changes["name"], p.id)
    if changes.get("is_active") is True and "cycle" not in changes:
        await _validate_cycle(db, p.cycle)
    for k, v in changes.items():
        setattr(p, k, v)
    await _commit_or_409(db, "Rotation name already exists")
    await db.refresh(p)
    await log_audit(
        db, current_user.id, "roster.rotation.update",
        "rotation_pattern", str(p.id), {"changed": list(changes.keys())}, request,
    )
    return p


@router.delete("/rotations/{rotation_id}")
async def delete_rotation(
    *,
    db: deps.DBDep,
    request: Request,
    rotation_id: int,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    _require_admin(current_user)
    p = await db.get(RotationPattern, rotation_id)
    if not p:
        raise HTTPException(status_code=404, detail="Rotation pattern not found")
    p.is_active = False
    await db.commit()
    await log_audit(
        db, current_user.id, "roster.rotation.delete",
        "rotation_pattern", str(p.id), {}, request,
    )
    return {"status": "deactivated", "id": rotation_id}


# ------------------------ coverage requirements ------------------------

def _check_max_min(mn: int, mx: Optional[int]) -> None:
    if mx is not None and mx < mn:
        raise HTTPException(
            status_code=422, detail="max_headcount must be >= min_headcount"
        )


@router.get(
    "/coverage-requirements", response_model=List[CoverageRequirementRead]
)
async def list_coverage_requirements(
    db: deps.DBDep,
    include_inactive: bool = Query(False),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    admin = roster_svc.is_roster_admin(current_user)
    if not admin and not await roster_svc.scoped_employees(db, current_user):
        raise HTTPException(status_code=403, detail="You have no roster scope.")
    q = select(CoverageRequirement).order_by(CoverageRequirement.id)
    if not (admin and include_inactive):
        q = q.where(CoverageRequirement.is_active.is_(True))
    return list((await db.execute(q)).scalars().all())


@router.post(
    "/coverage-requirements", response_model=CoverageRequirementRead
)
async def create_coverage_requirement(
    *,
    db: deps.DBDep,
    request: Request,
    body: CoverageRequirementCreate,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    _require_admin(current_user)
    await _validate_templates(db, [body.shift_template_id])
    r = CoverageRequirement(**body.model_dump())
    db.add(r)
    await _commit_or_409(db)
    await db.refresh(r)
    await log_audit(
        db, current_user.id, "roster.coverage.create",
        "coverage_requirement", str(r.id), body.model_dump(), request,
    )
    return r


@router.patch(
    "/coverage-requirements/{req_id}", response_model=CoverageRequirementRead
)
async def update_coverage_requirement(
    *,
    db: deps.DBDep,
    request: Request,
    req_id: int,
    body: CoverageRequirementUpdate,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    _require_admin(current_user)
    r = await db.get(CoverageRequirement, req_id)
    if not r:
        raise HTTPException(status_code=404, detail="Requirement not found")
    changes = body.model_dump(exclude_unset=True)
    for k in ("shift_template_id", "min_headcount", "is_active"):
        if k in changes and changes[k] is None:
            changes.pop(k)
    if "shift_template_id" in changes:
        await _validate_templates(db, [changes["shift_template_id"]])
    _check_max_min(
        changes.get("min_headcount", r.min_headcount),
        changes["max_headcount"] if "max_headcount" in changes
        else r.max_headcount,
    )
    for k, v in changes.items():
        setattr(r, k, v)
    await _commit_or_409(db)
    await db.refresh(r)
    await log_audit(
        db, current_user.id, "roster.coverage.update",
        "coverage_requirement", str(r.id),
        {"changed": list(changes.keys())}, request,
    )
    return r


@router.delete("/coverage-requirements/{req_id}")
async def delete_coverage_requirement(
    *,
    db: deps.DBDep,
    request: Request,
    req_id: int,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    _require_admin(current_user)
    r = await db.get(CoverageRequirement, req_id)
    if not r:
        raise HTTPException(status_code=404, detail="Requirement not found")
    r.is_active = False
    await _commit_or_409(db)
    await log_audit(
        db, current_user.id, "roster.coverage.delete",
        "coverage_requirement", str(r.id), {}, request,
    )
    return {"status": "deactivated", "id": req_id}


@router.post("/rotations/{rotation_id}/apply", response_model=RosterBulkResult)
async def apply_rotation(
    *,
    db: deps.DBDep,
    request: Request,
    rotation_id: int,
    body: RotationApplyRequest,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    p = await db.get(RotationPattern, rotation_id)
    if not p:
        raise HTTPException(status_code=404, detail="Rotation pattern not found")
    if not p.is_active:
        raise HTTPException(status_code=409, detail="Rotation pattern is inactive")
    if not roster_svc.is_roster_admin(current_user) and not (
        await roster_svc.scoped_employees(db, current_user)
    ):
        raise HTTPException(status_code=403, detail="You have no roster scope.")
    await _validate_cycle(db, p.cycle)
    result = RosterBulkResult()
    if body.employee_ids is not None:
        target_ids = set(body.employee_ids)
    else:
        emps = await roster_svc.scoped_employees(
            db, current_user, body.department
        )
        target_ids = {e.user_id for e in emps}
    allowed = await roster_svc.manageable_subset(db, current_user, target_ids)
    result.out_of_scope.extend(sorted(target_ids - allowed))
    if allowed:
        offsets = body.offsets or {}
        cells = []
        for uid in sorted(allowed):
            for (wd, tpl_id, wo) in roster_svc.expand_rotation(
                p.cycle, body.anchor, body.start, body.end,
                offsets.get(uid, body.default_offset),
            ):
                cells.append((uid, wd, tpl_id, wo))
        await _write_cells(
            db, current_user, allowed, cells, body.status, body.overwrite,
            result,
        )
        await _commit_or_409(db)
    if not (result.created or result.updated):
        return result
    await log_audit(
        db, current_user.id, "roster.rotation.apply",
        "rotation_pattern", str(p.id),
        {
            "created": result.created, "updated": result.updated,
            "skipped": result.skipped,
            "out_of_scope": len(result.out_of_scope),
            "start": body.start.isoformat(), "end": body.end.isoformat(),
            "status": body.status,
        },
        request,
    )
    return result


# ----------------------------- employee self-service -----------------------------

@router.get("/my", response_model=List[RosterEntryRead])
async def my_roster(
    db: deps.DBDep,
    start: Optional[pydate] = Query(None),
    end: Optional[pydate] = Query(None),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    today = pydate.today()
    s = start or (today - timedelta(days=today.weekday()))
    e = end or (s + timedelta(days=6))
    rows = (await db.execute(
        select(RosterEntry).where(
            RosterEntry.employee_id == current_user.id,
            RosterEntry.work_date >= s,
            RosterEntry.work_date <= e,
            RosterEntry.status == RosterStatus.PUBLISHED,
        ).order_by(RosterEntry.work_date)
    )).scalars().all()
    return [await _entry_read(db, r) for r in rows]


@router.get("/my/week")
async def my_roster_week(
    db: deps.DBDep,
    start: Optional[pydate] = Query(None),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Seven-day roster outlook — RosterEntry first, then falling back to the
    effective assignment, then the org default. Mirrors shifts.get_my_week
    with holiday/leave enrichment."""
    from app.models.hr import HolidayCalendar
    from app.models.leave import LeaveRequest, LeaveStatus
    from app.services.time_rules import build_default_shift, get_time_rules

    today = pydate.today()
    week_start = start or (today - timedelta(days=today.weekday()))
    days = [week_start + timedelta(days=i) for i in range(7)]

    entries = {
        r.work_date: r
        for r in (await db.execute(
            select(RosterEntry).where(
                RosterEntry.employee_id == current_user.id,
                RosterEntry.work_date >= days[0],
                RosterEntry.work_date <= days[-1],
                RosterEntry.status == RosterStatus.PUBLISHED,
            )
        )).scalars().all()
    }
    tpl_ids = {r.shift_template_id for r in entries.values() if r.shift_template_id}
    tpls = {}
    if tpl_ids:
        for t in (await db.execute(
            select(ShiftTemplate).where(ShiftTemplate.id.in_(tpl_ids))
        )).scalars().all():
            tpls[t.id] = t

    assignments = list((await db.execute(
        select(EmployeeShiftAssignment)
        .options(selectinload(EmployeeShiftAssignment.shift_template))
        .where(
            EmployeeShiftAssignment.employee_id == current_user.id,
            EmployeeShiftAssignment.effective_from <= days[-1],
            or_(
                EmployeeShiftAssignment.effective_to.is_(None),
                EmployeeShiftAssignment.effective_to >= days[0],
            ),
        )
        .order_by(EmployeeShiftAssignment.effective_from.desc())
    )).scalars().all())

    holidays = {
        h.date: h.name
        for h in (await db.execute(
            select(HolidayCalendar).where(HolidayCalendar.date.in_(days))
        )).scalars().all()
    }
    leaves = list((await db.execute(
        select(LeaveRequest)
        .options(selectinload(LeaveRequest.leave_type))
        .where(
            LeaveRequest.employee_id == current_user.id,
            LeaveRequest.status == LeaveStatus.APPROVED,
            LeaveRequest.start_date <= days[-1],
            LeaveRequest.end_date >= days[0],
        )
    )).scalars().all())
    default_shift = build_default_shift(await get_time_rules(db))

    out = []
    for d in days:
        entry = entries.get(d)
        lv = next((l for l in leaves if l.start_date <= d <= l.end_date), None)
        if entry is not None and entry.is_week_off:
            shift = {"name": "Week off", "start_time": None,
                     "end_time": None, "is_overnight": False, "source": "roster"}
        elif entry is not None and entry.shift_template_id:
            tpl = tpls.get(entry.shift_template_id)
            shift = {
                "name": tpl.name if tpl else "Shift",
                "start_time": tpl.start_time.strftime("%H:%M") if tpl else None,
                "end_time": tpl.end_time.strftime("%H:%M") if tpl else None,
                "is_overnight": tpl.is_overnight if tpl else False,
                "source": "roster",
            }
        else:
            asg = next(
                (a for a in assignments
                 if a.effective_from <= d
                 and (a.effective_to is None or a.effective_to >= d)),
                None,
            )
            tpl = asg.shift_template if asg else None
            if tpl is not None:
                shift = {
                    "name": tpl.name,
                    "start_time": tpl.start_time.strftime("%H:%M"),
                    "end_time": tpl.end_time.strftime("%H:%M"),
                    "is_overnight": tpl.is_overnight,
                    "source": "assigned",
                }
            else:
                shift = {
                    "name": "Default hours",
                    "start_time": default_shift.start_time.strftime("%H:%M"),
                    "end_time": default_shift.end_time.strftime("%H:%M"),
                    "is_overnight": default_shift.is_overnight,
                    "source": "default",
                }
        out.append({
            "date": d.isoformat(),
            "is_today": d == today,
            "is_weekend": d.weekday() == 6,
            "holiday_name": holidays.get(d),
            "on_leave": lv is not None,
            "leave_type": (
                lv.leave_type.name if lv is not None and lv.leave_type else None
            ),
            "shift": shift,
        })
    return {"start": week_start.isoformat(), "days": out}


# ----------------------------- change requests -----------------------------

async def _cr_read(db, cr: RosterChangeRequest) -> RosterChangeRequestRead:
    u = await db.get(User, cr.employee_id)
    req_tpl = (
        await db.get(ShiftTemplate, cr.requested_shift_template_id)
        if cr.requested_shift_template_id else None
    )
    cur_tpl = (
        await db.get(ShiftTemplate, cr.current_shift_template_id)
        if cr.current_shift_template_id else None
    )
    decider = await db.get(User, cr.decided_by_id) if cr.decided_by_id else None
    return RosterChangeRequestRead(
        id=cr.id,
        employee_id=cr.employee_id,
        work_date=cr.work_date,
        current_shift_template_id=cr.current_shift_template_id,
        requested_shift_template_id=cr.requested_shift_template_id,
        requested_week_off=cr.requested_week_off,
        reason=cr.reason,
        status=cr.status,
        decided_by_id=cr.decided_by_id,
        decided_at=cr.decided_at.isoformat() if cr.decided_at else None,
        decision_note=cr.decision_note,
        employee_name=u.full_name if u else None,
        current_shift_name=cur_tpl.name if cur_tpl else None,
        requested_shift_name=req_tpl.name if req_tpl else None,
        decided_by_name=decider.full_name if decider else None,
    )


@router.post("/change-requests", response_model=RosterChangeRequestRead)
async def create_change_request(
    *,
    db: deps.DBDep,
    request: Request,
    body: RosterChangeRequestCreate,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    # One pending request per (employee, date)
    dup = (await db.execute(
        select(RosterChangeRequest).where(
            RosterChangeRequest.employee_id == current_user.id,
            RosterChangeRequest.work_date == body.work_date,
            RosterChangeRequest.status == RosterChangeStatus.PENDING,
        )
    )).scalars().first()
    if dup is not None:
        raise HTTPException(
            status_code=409,
            detail="You already have a pending request for this date.",
        )
    # Snapshot the current cell
    existing = (await db.execute(
        select(RosterEntry).where(
            RosterEntry.employee_id == current_user.id,
            RosterEntry.work_date == body.work_date,
        )
    )).scalars().first()
    cr = RosterChangeRequest(
        employee_id=current_user.id,
        roster_entry_id=existing.id if existing else None,
        work_date=body.work_date,
        current_shift_template_id=(
            existing.shift_template_id if existing else None
        ),
        requested_shift_template_id=body.requested_shift_template_id,
        requested_week_off=body.requested_week_off,
        reason=body.reason,
        status=RosterChangeStatus.PENDING,
    )
    db.add(cr)
    await db.commit()
    await db.refresh(cr)
    await log_audit(
        db, current_user.id, "roster.change.create",
        "roster_change_request", str(cr.id),
        {"work_date": body.work_date.isoformat()}, request,
    )
    return await _cr_read(db, cr)


@router.get("/change-requests/my", response_model=List[RosterChangeRequestRead])
async def my_change_requests(
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    rows = (await db.execute(
        select(RosterChangeRequest).where(
            RosterChangeRequest.employee_id == current_user.id
        ).order_by(RosterChangeRequest.created_at.desc())
    )).scalars().all()
    return [await _cr_read(db, r) for r in rows]


@router.get("/change-requests", response_model=List[RosterChangeRequestRead])
async def scoped_change_requests(
    db: deps.DBDep,
    status: Optional[str] = Query(None),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Change requests for the current user's scoped team (heads see their
    team; admins see all)."""
    admin = roster_svc.is_roster_admin(current_user)
    team_ids = (
        set() if admin
        else await roster_svc.approvable_user_ids(db, current_user)
    )
    q = select(RosterChangeRequest).order_by(
        RosterChangeRequest.created_at.desc()
    )
    if status:
        q = q.where(RosterChangeRequest.status == status)
    if not admin:
        if not team_ids:
            return []
        q = q.where(RosterChangeRequest.employee_id.in_(team_ids))
    rows = (await db.execute(q)).scalars().all()
    return [await _cr_read(db, r) for r in rows]


@router.post(
    "/change-requests/{cr_id}/decide",
    response_model=RosterChangeRequestRead,
)
async def decide_change_request(
    *,
    db: deps.DBDep,
    request: Request,
    cr_id: int,
    body: RosterChangeDecision,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    cr = await db.get(RosterChangeRequest, cr_id)
    if not cr:
        raise HTTPException(status_code=404, detail="Request not found")
    if cr.status != RosterChangeStatus.PENDING:
        raise HTTPException(status_code=400, detail="Request already decided")
    if (
        cr.employee_id == current_user.id
        and not roster_svc.is_roster_admin(current_user)
    ):
        raise HTTPException(
            status_code=403,
            detail="You cannot decide your own request (separation of duties).",
        )
    if not await roster_svc.can_approve_changes_for(
        db, current_user, cr.employee_id
    ):
        raise HTTPException(
            status_code=403,
            detail="This employee is outside your roster scope.",
        )

    if body.action == "approve":
        emp = (await db.execute(
            select(Employee).where(Employee.user_id == cr.employee_id)
        )).scalars().first()
        await roster_svc.upsert_entry(
            db,
            employee_id=cr.employee_id,
            work_date=cr.work_date,
            shift_template_id=(
                None if cr.requested_week_off
                else cr.requested_shift_template_id
            ),
            is_week_off=cr.requested_week_off,
            status=RosterStatus.PUBLISHED,
            actor_id=current_user.id,
            department=emp.department if emp else None,
            overwrite=True,
        )
        cr.status = RosterChangeStatus.APPROVED
    else:
        cr.status = RosterChangeStatus.REJECTED
    cr.decided_by_id = current_user.id
    cr.decided_at = datetime.now(timezone.utc)
    cr.decision_note = body.decision_note
    await _commit_or_409(db)
    await db.refresh(cr)
    await log_audit(
        db, current_user.id, "roster.change.decide",
        "roster_change_request", str(cr.id),
        {"action": body.action}, request,
    )
    return await _cr_read(db, cr)


@router.post(
    "/change-requests/{cr_id}/cancel",
    response_model=RosterChangeRequestRead,
)
async def cancel_change_request(
    *,
    db: deps.DBDep,
    request: Request,
    cr_id: int,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    cr = await db.get(RosterChangeRequest, cr_id)
    if not cr:
        raise HTTPException(status_code=404, detail="Request not found")
    if cr.employee_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your request")
    if cr.status != RosterChangeStatus.PENDING:
        raise HTTPException(status_code=400, detail="Only pending requests can be cancelled")
    cr.status = RosterChangeStatus.CANCELLED
    await db.commit()
    await db.refresh(cr)
    await log_audit(
        db, current_user.id, "roster.change.cancel",
        "roster_change_request", str(cr.id), {}, request,
    )
    return await _cr_read(db, cr)
