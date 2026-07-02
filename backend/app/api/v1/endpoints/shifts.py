"""Shift Templates & Employee Shift Assignments.

Foundation of the 24x7 shift engine. CRUD for templates, single + bulk
assignment to employees, and an `effective shift on date` lookup.

This module is intentionally limited to data + assignment management.
Attendance computation, cross-midnight punch handling, and roster
auto-rotation are out of scope for this iteration.
"""
from datetime import date as date_cls
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import and_, or_, select, func
from sqlalchemy.orm import selectinload

from app.api import deps
from app.api.v1.endpoints.hr import log_audit
from app.models.employee import Employee
from app.models.shift import EmployeeShiftAssignment, ShiftTemplate
from app.models.user import User
from app.schemas.shift import (
    BulkAssignRequest,
    BulkAssignResult,
    EffectiveShiftResponse,
    EmployeeShiftAssignmentCreate,
    EmployeeShiftAssignmentRead,
    EmployeeShiftAssignmentUpdate,
    ShiftTemplateCreate,
    ShiftTemplateRead,
    ShiftTemplateUpdate,
)

router = APIRouter()

PERM_TEMPLATE_WRITE = "shift template write"
PERM_ASSIGN = "shift assign"


# ----------------------------- helpers -----------------------------


def _is_overnight(start, end) -> bool:
    return end <= start


def _enrich_assignment(
    asg: EmployeeShiftAssignment,
) -> EmployeeShiftAssignmentRead:
    """Build the read DTO with denormalized employee/template fields."""
    emp_user = getattr(asg, "employee", None)
    emp_record = getattr(emp_user, "employee", None) if emp_user else None
    tpl = getattr(asg, "shift_template", None)
    return EmployeeShiftAssignmentRead(
        id=asg.id,
        employee_id=asg.employee_id,
        shift_template_id=asg.shift_template_id,
        effective_from=asg.effective_from,
        effective_to=asg.effective_to,
        note=asg.note,
        assigned_by_id=asg.assigned_by_id,
        created_at=asg.created_at,
        updated_at=asg.updated_at,
        employee_name=getattr(emp_user, "full_name", None) if emp_user else None,
        employee_email=getattr(emp_user, "email", None) if emp_user else None,
        employee_department=getattr(emp_record, "department", None)
        if emp_record
        else None,
        shift_template_name=getattr(tpl, "name", None) if tpl else None,
    )


async def _find_overlapping(
    db,
    employee_id: int,
    new_from: date_cls,
    new_to: Optional[date_cls],
    exclude_id: Optional[int] = None,
) -> List[EmployeeShiftAssignment]:
    """Return existing assignments for the employee that overlap [new_from, new_to]."""
    stmt = select(EmployeeShiftAssignment).where(
        EmployeeShiftAssignment.employee_id == employee_id,
    )
    if exclude_id is not None:
        stmt = stmt.where(EmployeeShiftAssignment.id != exclude_id)

    # existing.to IS NULL OR existing.to >= new_from
    not_ended_before_new = or_(
        EmployeeShiftAssignment.effective_to.is_(None),
        EmployeeShiftAssignment.effective_to >= new_from,
    )
    # existing.from <= new_to OR new_to IS NULL
    if new_to is None:
        not_started_after_new = (
            EmployeeShiftAssignment.effective_from
            == EmployeeShiftAssignment.effective_from
        )  # always true
    else:
        not_started_after_new = (
            EmployeeShiftAssignment.effective_from <= new_to
        )

    stmt = stmt.where(and_(not_ended_before_new, not_started_after_new))
    return list((await db.execute(stmt)).scalars().all())


# ----------------------------- ShiftTemplate CRUD -----------------------------


@router.get("/templates", response_model=List[ShiftTemplateRead])
async def list_templates(
    db: deps.DBDep,
    include_inactive: bool = Query(False),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """List shift templates. Read open to any authenticated user (used by pickers)."""
    stmt = select(ShiftTemplate)
    if not include_inactive:
        stmt = stmt.where(ShiftTemplate.is_active.is_(True))
    stmt = stmt.order_by(ShiftTemplate.name)
    return list((await db.execute(stmt)).scalars().all())


@router.get("/templates/{template_id}", response_model=ShiftTemplateRead)
async def get_template(
    template_id: int,
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    obj = await db.get(ShiftTemplate, template_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Shift template not found")
    return obj


@router.post("/templates", response_model=ShiftTemplateRead)
async def create_template(
    *,
    db: deps.DBDep,
    payload: ShiftTemplateCreate,
    request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_TEMPLATE_WRITE])),
) -> Any:
    # uniqueness pre-check (case-insensitive name)
    clash = (
        await db.execute(
            select(ShiftTemplate).where(
                func.lower(ShiftTemplate.name) == payload.name.strip().lower()
            )
        )
    ).scalars().first()
    if clash is not None:
        raise HTTPException(
            status_code=400,
            detail=f"Shift template '{payload.name}' already exists",
        )

    obj = ShiftTemplate(
        name=payload.name.strip(),
        start_time=payload.start_time,
        end_time=payload.end_time,
        is_overnight=_is_overnight(payload.start_time, payload.end_time),
        break_minutes=payload.break_minutes,
        grace_in_minutes=payload.grace_in_minutes,
        grace_out_minutes=payload.grace_out_minutes,
        full_day_hours=payload.full_day_hours,
        half_day_hours=payload.half_day_hours,
        weekly_offs=payload.weekly_offs,
        is_active=payload.is_active,
        created_by_id=current_user.id,
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)

    await log_audit(
        db,
        current_user.id,
        "shift_template.create",
        "shift_template",
        str(obj.id),
        {"name": obj.name, "is_overnight": obj.is_overnight},
        request,
    )
    return obj


@router.patch("/templates/{template_id}", response_model=ShiftTemplateRead)
async def update_template(
    *,
    template_id: int,
    db: deps.DBDep,
    payload: ShiftTemplateUpdate,
    request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_TEMPLATE_WRITE])),
) -> Any:
    obj = await db.get(ShiftTemplate, template_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Shift template not found")

    data = payload.model_dump(exclude_unset=True)

    # Cross-field validation when both times present (one may be from existing obj).
    new_start = data.get("start_time", obj.start_time)
    new_end = data.get("end_time", obj.end_time)
    if new_start == new_end:
        raise HTTPException(
            status_code=400,
            detail="start_time and end_time cannot be equal",
        )
    new_full = data.get("full_day_hours", obj.full_day_hours)
    new_half = data.get("half_day_hours", obj.half_day_hours)
    if new_half > new_full:
        raise HTTPException(
            status_code=400,
            detail="half_day_hours cannot exceed full_day_hours",
        )

    if "name" in data:
        name = data["name"].strip()
        if not name:
            raise HTTPException(status_code=400, detail="name cannot be blank")
        clash = (
            await db.execute(
                select(ShiftTemplate).where(
                    func.lower(ShiftTemplate.name) == name.lower(),
                    ShiftTemplate.id != template_id,
                )
            )
        ).scalars().first()
        if clash is not None:
            raise HTTPException(
                status_code=400, detail=f"Shift template '{name}' already exists"
            )
        data["name"] = name

    for k, v in data.items():
        setattr(obj, k, v)
    obj.is_overnight = _is_overnight(obj.start_time, obj.end_time)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)

    await log_audit(
        db,
        current_user.id,
        "shift_template.update",
        "shift_template",
        str(obj.id),
        {"updated_fields": list(data.keys())},
        request,
    )
    return obj


@router.delete(
    "/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_template(
    *,
    template_id: int,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_TEMPLATE_WRITE])),
) -> None:
    obj = await db.get(ShiftTemplate, template_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Shift template not found")
    in_use = (
        await db.execute(
            select(func.count())
            .select_from(EmployeeShiftAssignment)
            .where(EmployeeShiftAssignment.shift_template_id == template_id)
        )
    ).scalar_one()
    if in_use:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot delete '{obj.name}' — {in_use} assignment(s) still "
                "reference it. Deactivate instead."
            ),
        )
    await db.delete(obj)
    await db.commit()
    await log_audit(
        db,
        current_user.id,
        "shift_template.delete",
        "shift_template",
        str(template_id),
        {"name": obj.name},
        request,
    )
    return None


# ----------------------------- Assignments -----------------------------


@router.get("/assignments", response_model=List[EmployeeShiftAssignmentRead])
async def list_assignments(
    db: deps.DBDep,
    employee_id: Optional[int] = Query(None),
    shift_template_id: Optional[int] = Query(None),
    department: Optional[str] = Query(None),
    as_of_date: Optional[date_cls] = Query(
        None,
        description="If set, only assignments active on this date are returned.",
    ),
    include_ended: bool = Query(
        True,
        description="If False, only ongoing (effective_to IS NULL) assignments.",
    ),
    current_user: User = Depends(deps.check_permissions([PERM_ASSIGN])),
) -> Any:
    stmt = (
        select(EmployeeShiftAssignment)
        .options(
            selectinload(EmployeeShiftAssignment.employee).selectinload(
                User.employee
            ),
            selectinload(EmployeeShiftAssignment.shift_template),
        )
        .order_by(EmployeeShiftAssignment.effective_from.desc())
    )
    if employee_id is not None:
        stmt = stmt.where(EmployeeShiftAssignment.employee_id == employee_id)
    if shift_template_id is not None:
        stmt = stmt.where(
            EmployeeShiftAssignment.shift_template_id == shift_template_id
        )
    if not include_ended:
        stmt = stmt.where(EmployeeShiftAssignment.effective_to.is_(None))
    if as_of_date is not None:
        stmt = stmt.where(
            EmployeeShiftAssignment.effective_from <= as_of_date,
            or_(
                EmployeeShiftAssignment.effective_to.is_(None),
                EmployeeShiftAssignment.effective_to >= as_of_date,
            ),
        )
    if department:
        # Filter by Employee.department string (loose match — Employee table
        # uses a string column, not an FK to Department).
        stmt = stmt.join(
            Employee, Employee.user_id == EmployeeShiftAssignment.employee_id
        ).where(Employee.department == department)

    rows = list((await db.execute(stmt)).scalars().all())
    return [_enrich_assignment(r) for r in rows]


@router.post("/assignments", response_model=EmployeeShiftAssignmentRead)
async def create_assignment(
    *,
    db: deps.DBDep,
    payload: EmployeeShiftAssignmentCreate,
    request: Request,
    close_previous: bool = Query(
        True,
        description=(
            "If True, any existing open-ended assignment for the employee is "
            "auto-closed the day before this one starts (smooth reassignment). "
            "If False, overlapping assignments cause a 409."
        ),
    ),
    current_user: User = Depends(deps.check_permissions([PERM_ASSIGN])),
) -> Any:
    # Validate target employee exists.
    target = await db.get(User, payload.employee_id)
    if not target:
        raise HTTPException(status_code=404, detail="Employee user not found")

    tpl = await db.get(ShiftTemplate, payload.shift_template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="Shift template not found")
    if not tpl.is_active:
        raise HTTPException(
            status_code=400,
            detail=f"Shift template '{tpl.name}' is inactive",
        )

    overlapping = await _find_overlapping(
        db, payload.employee_id, payload.effective_from, payload.effective_to
    )
    if overlapping and close_previous:
        # Auto-close: shrink each overlapping open-ended assignment so its
        # effective_to is the day before this new one starts. If shrinking
        # would invert dates (existing.from > new.from - 1), refuse.
        from datetime import timedelta

        prior_end = payload.effective_from - timedelta(days=1)
        for o in overlapping:
            if o.effective_from > prior_end:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Cannot close existing assignment #{o.id}: it starts "
                        f"on {o.effective_from} which is after the proposed "
                        f"new-prior-end {prior_end}."
                    ),
                )
            o.effective_to = prior_end
            db.add(o)
    elif overlapping:
        ids = ", ".join(f"#{o.id}" for o in overlapping)
        raise HTTPException(
            status_code=409,
            detail=(
                f"Overlapping assignment(s) exist for employee {payload.employee_id}: {ids}. "
                "Close them first or call again with close_previous=true."
            ),
        )

    obj = EmployeeShiftAssignment(
        employee_id=payload.employee_id,
        shift_template_id=payload.shift_template_id,
        effective_from=payload.effective_from,
        effective_to=payload.effective_to,
        note=payload.note,
        assigned_by_id=current_user.id,
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)

    # Re-load relationships for enrichment.
    fresh = (
        await db.execute(
            select(EmployeeShiftAssignment)
            .options(
                selectinload(EmployeeShiftAssignment.employee).selectinload(
                    User.employee
                ),
                selectinload(EmployeeShiftAssignment.shift_template),
            )
            .where(EmployeeShiftAssignment.id == obj.id)
        )
    ).scalars().first()

    await log_audit(
        db,
        current_user.id,
        "shift_assignment.create",
        "employee_shift_assignment",
        str(obj.id),
        {
            "employee_id": obj.employee_id,
            "shift_template_id": obj.shift_template_id,
            "effective_from": obj.effective_from.isoformat(),
            "effective_to": obj.effective_to.isoformat()
            if obj.effective_to
            else None,
            "closed_prior": [o.id for o in overlapping] if close_previous else [],
        },
        request,
    )
    return _enrich_assignment(fresh) if fresh else _enrich_assignment(obj)


@router.patch(
    "/assignments/{assignment_id}", response_model=EmployeeShiftAssignmentRead
)
async def update_assignment(
    *,
    assignment_id: int,
    db: deps.DBDep,
    payload: EmployeeShiftAssignmentUpdate,
    request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_ASSIGN])),
) -> Any:
    obj = await db.get(EmployeeShiftAssignment, assignment_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Assignment not found")

    data = payload.model_dump(exclude_unset=True)

    new_from = data.get("effective_from", obj.effective_from)
    new_to = data.get("effective_to", obj.effective_to)
    if new_to is not None and new_to < new_from:
        raise HTTPException(
            status_code=400,
            detail="effective_to cannot be before effective_from",
        )

    if "shift_template_id" in data:
        tpl = await db.get(ShiftTemplate, data["shift_template_id"])
        if not tpl:
            raise HTTPException(
                status_code=404, detail="Shift template not found"
            )

    overlapping = await _find_overlapping(
        db, obj.employee_id, new_from, new_to, exclude_id=obj.id
    )
    if overlapping:
        ids = ", ".join(f"#{o.id}" for o in overlapping)
        raise HTTPException(
            status_code=409,
            detail=(
                f"Update would overlap existing assignment(s) for the employee: {ids}."
            ),
        )

    for k, v in data.items():
        setattr(obj, k, v)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)

    fresh = (
        await db.execute(
            select(EmployeeShiftAssignment)
            .options(
                selectinload(EmployeeShiftAssignment.employee).selectinload(
                    User.employee
                ),
                selectinload(EmployeeShiftAssignment.shift_template),
            )
            .where(EmployeeShiftAssignment.id == obj.id)
        )
    ).scalars().first()

    await log_audit(
        db,
        current_user.id,
        "shift_assignment.update",
        "employee_shift_assignment",
        str(obj.id),
        {"updated_fields": list(data.keys())},
        request,
    )
    return _enrich_assignment(fresh) if fresh else _enrich_assignment(obj)


@router.delete(
    "/assignments/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_assignment(
    *,
    assignment_id: int,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_ASSIGN])),
) -> None:
    obj = await db.get(EmployeeShiftAssignment, assignment_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Assignment not found")
    await db.delete(obj)
    await db.commit()
    await log_audit(
        db,
        current_user.id,
        "shift_assignment.delete",
        "employee_shift_assignment",
        str(assignment_id),
        {
            "employee_id": obj.employee_id,
            "shift_template_id": obj.shift_template_id,
        },
        request,
    )
    return None


@router.post("/assignments/bulk", response_model=BulkAssignResult)
async def bulk_assign(
    *,
    db: deps.DBDep,
    payload: BulkAssignRequest,
    request: Request,
    close_previous: bool = Query(True),
    current_user: User = Depends(deps.check_permissions([PERM_ASSIGN])),
) -> Any:
    """Bulk-assign a single shift template to many employees.

    Targets: provide EITHER `employee_ids` OR `department` (string match
    on `employee.department`). Per-employee failures are reported
    individually and do not abort the rest.
    """
    tpl = await db.get(ShiftTemplate, payload.shift_template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="Shift template not found")
    if not tpl.is_active:
        raise HTTPException(
            status_code=400,
            detail=f"Shift template '{tpl.name}' is inactive",
        )

    # Resolve target employee user_ids.
    target_user_ids: List[int] = []
    if payload.employee_ids:
        target_user_ids = list({int(x) for x in payload.employee_ids})
    elif payload.department:
        rows = (
            await db.execute(
                select(Employee.user_id).where(
                    Employee.department == payload.department,
                    Employee.status == "active",
                )
            )
        ).scalars().all()
        target_user_ids = list({int(x) for x in rows})

    if not target_user_ids:
        return BulkAssignResult(
            assigned=0, skipped=0, failed=0, errors=["No target employees resolved"]
        )

    from datetime import timedelta

    assigned = 0
    skipped = 0
    failed = 0
    errors: List[str] = []
    created_ids: List[int] = []

    for uid in target_user_ids:
        try:
            overlapping = await _find_overlapping(
                db, uid, payload.effective_from, payload.effective_to
            )
            # If the only "overlap" is the SAME template starting on the same
            # day (idempotent re-assign), skip rather than error.
            same_already = [
                o
                for o in overlapping
                if o.shift_template_id == payload.shift_template_id
                and o.effective_from == payload.effective_from
            ]
            if same_already:
                skipped += 1
                continue
            if overlapping:
                if close_previous:
                    prior_end = payload.effective_from - timedelta(days=1)
                    bad = [o for o in overlapping if o.effective_from > prior_end]
                    if bad:
                        failed += 1
                        ids = ", ".join(f"#{o.id}" for o in bad)
                        errors.append(
                            f"Employee {uid}: cannot close prior assignment(s) {ids} — "
                            "they start on/after the new assignment."
                        )
                        continue
                    for o in overlapping:
                        o.effective_to = prior_end
                        db.add(o)
                else:
                    failed += 1
                    ids = ", ".join(f"#{o.id}" for o in overlapping)
                    errors.append(
                        f"Employee {uid}: overlapping assignment(s) {ids}"
                    )
                    continue

            obj = EmployeeShiftAssignment(
                employee_id=uid,
                shift_template_id=payload.shift_template_id,
                effective_from=payload.effective_from,
                effective_to=payload.effective_to,
                note=payload.note,
                assigned_by_id=current_user.id,
            )
            db.add(obj)
            await db.flush()
            created_ids.append(obj.id)
            assigned += 1
        except Exception as e:  # noqa: BLE001
            failed += 1
            errors.append(f"Employee {uid}: {e}")

    await db.commit()

    await log_audit(
        db,
        current_user.id,
        "shift_assignment.bulk_assign",
        "employee_shift_assignment",
        ",".join(str(i) for i in created_ids) or "-",
        {
            "shift_template_id": payload.shift_template_id,
            "target_employee_ids": target_user_ids,
            "department": payload.department,
            "assigned": assigned,
            "skipped": skipped,
            "failed": failed,
        },
        request,
    )

    return BulkAssignResult(
        assigned=assigned, skipped=skipped, failed=failed, errors=errors
    )


# ----------------------------- Effective shift -----------------------------


async def _effective_for(
    db, employee_id: int, on_date: date_cls
) -> Optional[EmployeeShiftAssignment]:
    """Return the single assignment active on the given date for the employee, if any."""
    stmt = (
        select(EmployeeShiftAssignment)
        .options(selectinload(EmployeeShiftAssignment.shift_template))
        .where(
            EmployeeShiftAssignment.employee_id == employee_id,
            EmployeeShiftAssignment.effective_from <= on_date,
            or_(
                EmployeeShiftAssignment.effective_to.is_(None),
                EmployeeShiftAssignment.effective_to >= on_date,
            ),
        )
        .order_by(EmployeeShiftAssignment.effective_from.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalars().first()


@router.get("/effective", response_model=EffectiveShiftResponse)
async def get_effective_shift(
    db: deps.DBDep,
    employee_id: int = Query(...),
    on_date: date_cls = Query(..., description="Date to evaluate the shift on"),
    current_user: User = Depends(deps.check_permissions([PERM_ASSIGN])),
) -> Any:
    asg = await _effective_for(db, employee_id, on_date)
    return EffectiveShiftResponse(
        employee_id=employee_id,
        on_date=on_date,
        shift=ShiftTemplateRead.model_validate(asg.shift_template)
        if asg
        else None,
        assignment_id=asg.id if asg else None,
    )


@router.get("/my/current", response_model=EffectiveShiftResponse)
async def get_my_current_shift(
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    today = date_cls.today()
    asg = await _effective_for(db, current_user.id, today)
    return EffectiveShiftResponse(
        employee_id=current_user.id,
        on_date=today,
        shift=ShiftTemplateRead.model_validate(asg.shift_template)
        if asg
        else None,
        assignment_id=asg.id if asg else None,
    )


@router.get("/my/history", response_model=List[EmployeeShiftAssignmentRead])
async def get_my_shift_history(
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    rows = list(
        (
            await db.execute(
                select(EmployeeShiftAssignment)
                .options(
                    selectinload(EmployeeShiftAssignment.shift_template),
                    selectinload(EmployeeShiftAssignment.employee).selectinload(
                        User.employee
                    ),
                )
                .where(EmployeeShiftAssignment.employee_id == current_user.id)
                .order_by(EmployeeShiftAssignment.effective_from.desc())
            )
        ).scalars().all()
    )
    return [_enrich_assignment(r) for r in rows]


# ===========================================================================
# Section R: shift change requests (employee-initiated, Manager -> HR)
# ===========================================================================

from datetime import datetime, timezone as _tz  # noqa: E402

from app.models.approval_chain import (  # noqa: E402
    ChainedApprovalStatus, ChainEntityType,
)
from app.models.shift import (  # noqa: E402
    ShiftChangeRequest, ShiftChangeStatus,
)
from app.schemas.shift import (  # noqa: E402
    ShiftChangeRequestCreate, ShiftChangeRequestRead,
)
from app.services.shift_change import apply_shift_change  # noqa: E402


async def _change_request_read(
    db, req: ShiftChangeRequest
) -> ShiftChangeRequestRead:
    read = ShiftChangeRequestRead.model_validate(req)
    user = await db.get(User, req.user_id)
    read.user_name = user.full_name if user else None
    if req.current_shift_template_id:
        cur = await db.get(ShiftTemplate, req.current_shift_template_id)
        read.current_shift_name = cur.name if cur else None
    tgt = await db.get(ShiftTemplate, req.requested_shift_template_id)
    read.requested_shift_name = tgt.name if tgt else None
    return read


@router.post("/change-requests", response_model=ShiftChangeRequestRead)
async def create_change_request(
    *,
    db: deps.DBDep,
    payload: ShiftChangeRequestCreate,
    request: Request,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Employee requests a shift change (routed Manager -> HR via the
    chain engine; approvers act in their approvals queue)."""
    today = datetime.now(_tz.utc).date()
    if payload.effective_from <= today:
        raise HTTPException(
            422, "effective_from must be a future date."
        )

    shift = await db.get(ShiftTemplate, payload.requested_shift_template_id)
    if not shift or not shift.is_active:
        raise HTTPException(404, "Requested shift template not found")

    pending = (await db.execute(
        select(ShiftChangeRequest).where(
            ShiftChangeRequest.user_id == current_user.id,
            ShiftChangeRequest.status == ShiftChangeStatus.PENDING,
        )
    )).scalars().first()
    if pending:
        raise HTTPException(
            409,
            "You already have a pending shift change request — cancel it "
            "before submitting another.",
        )

    # Snapshot the shift currently effective on the change date.
    current = (await db.execute(
        select(EmployeeShiftAssignment).where(
            EmployeeShiftAssignment.employee_id == current_user.id,
            EmployeeShiftAssignment.effective_from <= payload.effective_from,
            or_(
                EmployeeShiftAssignment.effective_to.is_(None),
                EmployeeShiftAssignment.effective_to
                >= payload.effective_from,
            ),
        ).order_by(EmployeeShiftAssignment.effective_from.desc()).limit(1)
    )).scalars().first()
    if current and current.shift_template_id == shift.id:
        raise HTTPException(
            422, "You are already on that shift for the requested date."
        )

    req = ShiftChangeRequest(
        user_id=current_user.id,
        current_shift_template_id=(
            current.shift_template_id if current else None
        ),
        requested_shift_template_id=shift.id,
        effective_from=payload.effective_from,
        reason=payload.reason.strip(),
    )
    db.add(req)
    await db.flush()

    emp = (await db.execute(
        select(Employee).where(Employee.user_id == current_user.id)
    )).scalars().first()
    from app.api.v1.endpoints.approval_chains import instantiate_for_entity
    instance = await instantiate_for_entity(
        db=db,
        entity_type=ChainEntityType.SHIFT_CHANGE,
        entity_id=req.id,
        submitter=current_user,
        amount_paise=0,
        department=(emp.department if emp else None),
        context={
            "requested_shift": shift.name,
            "effective_from": payload.effective_from.isoformat(),
        },
    )
    req.approval_instance_id = instance.id
    # Auto-approve short-circuit (e.g. no applicable steps).
    if instance.status == ChainedApprovalStatus.APPROVED:
        await apply_shift_change(db, req)

    await log_audit(
        db, current_user.id, "SHIFT_CHANGE_REQUEST",
        "shift_change_request", str(req.id),
        {
            "requested_shift_template_id": shift.id,
            "effective_from": payload.effective_from.isoformat(),
            "instance_id": instance.id,
        },
        request,
    )
    await db.commit()
    await db.refresh(req)
    return await _change_request_read(db, req)


@router.get(
    "/change-requests/my", response_model=List[ShiftChangeRequestRead]
)
async def my_change_requests(
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    rows = (await db.execute(
        select(ShiftChangeRequest)
        .where(ShiftChangeRequest.user_id == current_user.id)
        .order_by(ShiftChangeRequest.created_at.desc())
    )).scalars().all()
    return [await _change_request_read(db, r) for r in rows]


@router.get("/change-requests", response_model=List[ShiftChangeRequestRead])
async def list_change_requests(
    db: deps.DBDep,
    status_filter: Optional[str] = Query(default=None, alias="status"),
    current_user: User = Depends(deps.check_permissions([PERM_ASSIGN])),
) -> Any:
    stmt = select(ShiftChangeRequest).order_by(
        ShiftChangeRequest.created_at.desc()
    )
    if status_filter:
        stmt = stmt.where(ShiftChangeRequest.status == status_filter)
    rows = (await db.execute(stmt)).scalars().all()
    return [await _change_request_read(db, r) for r in rows]


@router.post(
    "/change-requests/{request_id}/cancel",
    response_model=ShiftChangeRequestRead,
)
async def cancel_change_request(
    *,
    db: deps.DBDep,
    request_id: int,
    request: Request,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    req = await db.get(ShiftChangeRequest, request_id)
    if not req:
        raise HTTPException(404, "Request not found")
    if req.user_id != current_user.id:
        raise HTTPException(403, "You may only cancel your own request")
    if req.status != ShiftChangeStatus.PENDING:
        raise HTTPException(400, f"Request is already {req.status}")

    req.status = ShiftChangeStatus.CANCELLED
    req.decided_at = datetime.now(_tz.utc)
    if req.approval_instance_id:
        from app.models.approval_chain import ChainedApprovalInstance
        inst = await db.get(
            ChainedApprovalInstance, req.approval_instance_id
        )
        if inst and inst.status == ChainedApprovalStatus.PENDING:
            inst.status = ChainedApprovalStatus.CANCELLED
            inst.finalized_at = datetime.now(_tz.utc)

    await log_audit(
        db, current_user.id, "SHIFT_CHANGE_CANCEL",
        "shift_change_request", str(req.id), {}, request,
    )
    await db.commit()
    await db.refresh(req)
    return await _change_request_read(db, req)
