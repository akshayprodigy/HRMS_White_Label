"""Roster coverage requirements + insights."""
from datetime import date as pydate, timedelta
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import and_, or_, select

from app.api import deps
from app.api.v1.endpoints.hr import log_audit
from app.models.employee import Employee, EmployeeStatus
from app.models.shift import ShiftTemplate
from app.models.user import User
from app.schemas.roster import (
    RosterInsightsResponse, ViolationRead, CoverageCellRead,
    CoverageRequirementCreate, CoverageRequirementUpdate,
    CoverageRequirementRead,
)
from app.models.coverage_requirement import CoverageRequirement
from app.services import schedule_rules
from app.services.time_rules import get_schedule_rules
from app.services import roster as roster_svc

from app.api.v1.endpoints.roster_common import (
    require_admin, commit_or_409,
    validate_templates,
)

router = APIRouter()


@router.get("/insights", response_model=RosterInsightsResponse)
async def get_insights(
    db: deps.DBDep,
    start: pydate = Query(...),
    end: pydate = Query(...),
    department: Optional[str] = None,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Work-rule violations (scoped/filtered employees only) + coverage
    (counts ALL active employees matching each requirement; headcounts
    only, no names). DRAFT and PUBLISHED entries both count."""
    if start > end:
        raise HTTPException(status_code=400, detail="start must be <= end")
    if (end - start).days > 62:
        raise HTTPException(status_code=400, detail="range too large (max 62 days)")
    admin = roster_svc.is_roster_admin(current_user)
    scoped = await roster_svc.scoped_employees(db, current_user)
    if not admin and not scoped:
        raise HTTPException(status_code=403, detail="You have no roster scope.")
    viol_emps = [e for e in scoped if not department or e.department == department]
    reqs = roster_svc.visible_requirements(
        list((await db.execute(select(CoverageRequirement).where(
            CoverageRequirement.is_active.is_(True)))).scalars().all()),
        admin=admin, scoped_departments={e.department for e in scoped},
        department=department,
    )

    # Everyone counted toward coverage, independent of the viewer's scope.
    meta = {e.user_id: (e.department, e.location) for e in scoped}
    if reqs:
        conds = [
            and_(
                *([Employee.department == r.department] if r.department else []),
                *([Employee.location == r.location] if r.location else []),
            ) for r in reqs
        ]
        q = select(Employee.user_id, Employee.department, Employee.location)\
            .where(Employee.status == EmployeeStatus.ACTIVE)
        if not any(r.department is None and r.location is None for r in reqs):
            q = q.where(or_(*conds))
        for r in (await db.execute(q)).all():
            meta[r.user_id] = (r.department, r.location)

    rules = await get_schedule_rules(db)
    lookback = max(7, rules["max_consecutive_days"] + 1,
                   rules["max_consecutive_nights"] + 1)
    w_start = start - timedelta(days=lookback)
    w_end = end + timedelta(days=(6 - end.weekday()) + 1)  # Sunday of end's week, +1d for rest

    templates = {t.id: t for t in (await db.execute(
        select(ShiftTemplate))).scalars().all()}
    entries, asgs = await roster_svc.load_planner_cells(
        db, meta.keys(), w_start, w_end)
    cells, d = [], w_start
    all_days = []
    while d <= w_end:
        all_days.append(d)
        d += timedelta(days=1)
    for uid in meta:
        for d in all_days:
            tid = roster_svc.resolve_working_template(
                entries.get((uid, d)), asgs.get(uid), templates, d)
            if tid is not None:
                cells.append((uid, d, tid))
    spans = schedule_rules.build_spans(cells, templates)

    viol_ids = {e.user_id for e in viol_emps}
    name_by_uid = {e.user_id: (e.user.full_name if e.user else None)
                   for e in viol_emps}
    v_spans = [s for s in spans if s.user_id in viol_ids]
    leave = await roster_svc.approved_leave_days(db, viol_ids, w_start, w_end)
    viols = schedule_rules.check_rules(v_spans, rules, window_start=start)
    viols += schedule_rules.check_leave_conflicts(v_spans, leave)
    viols = sorted((v for v in viols if start <= v.work_date <= end),
                   key=lambda v: (v.work_date, v.user_id, v.rule))

    dates = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    cov = schedule_rules.compute_coverage(
        [s for s in spans if start <= s.work_date <= end], reqs, meta, dates)
    return RosterInsightsResponse(
        violations=[ViolationRead(
            user_id=v.user_id, employee_name=name_by_uid.get(v.user_id),
            work_date=v.work_date, rule=v.rule, message=v.message,
        ) for v in viols],
        coverage=[CoverageCellRead(
            date=c.date, shift_template_id=c.shift_template_id,
            shift_name=(templates[c.shift_template_id].name
                        if c.shift_template_id in templates else None),
            department=c.department, location=c.location,
            required_min=c.required_min, required_max=c.required_max,
            scheduled=c.scheduled, status=c.status,
        ) for c in cov],
    )


# ------------------------ coverage requirements ------------------------

async def _check_duplicate_requirement(
    db, *, department, location, shift_template_id, weekday,
    exclude_id: Optional[int] = None,
) -> None:
    def eq(col, v):
        return col.is_(None) if v is None else col == v
    q = select(CoverageRequirement.id).where(
        CoverageRequirement.is_active.is_(True),
        CoverageRequirement.shift_template_id == shift_template_id,
        eq(CoverageRequirement.department, department),
        eq(CoverageRequirement.location, location),
        eq(CoverageRequirement.weekday, weekday),
    )
    if exclude_id is not None:
        q = q.where(CoverageRequirement.id != exclude_id)
    if (await db.execute(q)).first() is not None:
        raise HTTPException(
            status_code=409,
            detail="An active requirement already exists for this "
                   "department/location/shift/weekday",
        )


def _check_max_min(mn: int, mx: Optional[int]) -> None:
    # Create is also validated by the schema; PATCH can only be checked here
    # because it needs the stored values merged with the partial update.
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
    rows = list((await db.execute(q)).scalars().all())
    if admin:
        return rows
    depts = {e.department for e in await roster_svc.scoped_employees(
        db, current_user)}
    return roster_svc.visible_requirements(
        rows, admin=False, scoped_departments=depts, department=None)


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
    require_admin(current_user)
    await validate_templates(db, [body.shift_template_id])
    await _check_duplicate_requirement(db, **body.model_dump(
        include={"department", "location", "shift_template_id", "weekday"}))
    r = CoverageRequirement(**body.model_dump())
    db.add(r)
    await commit_or_409(db)
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
    require_admin(current_user)
    r = await db.get(CoverageRequirement, req_id)
    if not r:
        raise HTTPException(status_code=404, detail="Requirement not found")
    changes = body.model_dump(exclude_unset=True)
    for k in ("shift_template_id", "min_headcount", "is_active"):
        if k in changes and changes[k] is None:
            changes.pop(k)
    if "shift_template_id" in changes:
        await validate_templates(db, [changes["shift_template_id"]])
    _check_max_min(
        changes.get("min_headcount", r.min_headcount),
        changes["max_headcount"] if "max_headcount" in changes
        else r.max_headcount,
    )
    final = {k: changes.get(k, getattr(r, k)) for k in (
        "department", "location", "shift_template_id", "weekday", "is_active")}
    if final.pop("is_active"):
        await _check_duplicate_requirement(db, exclude_id=r.id, **final)
    for k, v in changes.items():
        setattr(r, k, v)
    await commit_or_409(db)
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
    require_admin(current_user)
    r = await db.get(CoverageRequirement, req_id)
    if not r:
        raise HTTPException(status_code=404, detail="Requirement not found")
    r.is_active = False
    await commit_or_409(db)
    await log_audit(
        db, current_user.id, "roster.coverage.delete",
        "coverage_requirement", str(r.id), {}, request,
    )
    return {"status": "deactivated", "id": req_id}


