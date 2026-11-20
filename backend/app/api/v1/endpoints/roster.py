"""Roster planner API (W7), mounted at /roster (attendance-gated).

Write access is scoped through services/roster.py: superusers / `roster
manage` holders touch everyone, functional heads only their team. Plain
employees use the /my* + /change-requests* self-service paths.

PRECEDENCE: PUBLISHED roster entries drive attendance via
services/effective_shift.py (a published cell overrides the standing
EmployeeShiftAssignment for that day). DRAFT entries are planning-only and
never affect attendance.
"""
from datetime import date as pydate, datetime, timedelta, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from app.services.org_time import local_today
from app.api import deps
from app.api.v1.endpoints.hr import log_audit
from app.models.employee import Employee
from app.models.leave import LeaveRequest, LeaveStatus
from app.models.roster import (
    RosterEntry, RosterChangeRequest, RosterStatus, RosterChangeStatus,
)
from app.models.shift import EmployeeShiftAssignment, ShiftTemplate
from app.models.user import User
from app.schemas.roster import (
    RosterGridResponse, RosterBulkRequest, RosterBulkResult,
    RosterEntryInput, RosterEntrySingleInput, RosterEntryRead, RosterEntryUpdate,
    RosterChangeRequestCreate, RosterChangeRequestRead, RosterChangeDecision,
)
from app.services import roster as roster_svc
from app.api.v1.endpoints.roster_common import (
    entry_read, require_manage, commit_or_409, guard_conflicts, lock_row, check_window,
    validate_templates, write_cells, NO_PUBLISH_MSG, REASON_MSG, DRAFT_NOTICE,
)

router = APIRouter()


async def _live_transition(
    db, uid: int, wd: pydate, prior_snap, new_status: str,
    new_tpl: Optional[int], new_off: bool,
):
    """(old_live, new_live) cells the employee sees before/after a write of
    one cell, for the lock-window check. `prior_snap` = (tpl, off, status)
    of the existing row or None."""
    base = (await roster_svc.assignment_cells(db, {(uid, wd)}))[(uid, wd)]
    old = roster_svc.live_cell(prior_snap, base)
    new = (
        roster_svc.norm_cell(new_tpl, new_off)
        if new_status == RosterStatus.PUBLISHED else base
    )
    return old, new


# ----------------------------- planner -----------------------------

@router.get("/plan", response_model=RosterGridResponse)
async def get_plan(
    db: deps.DBDep,
    start: pydate = Query(...),
    end: pydate = Query(...),
    department: Optional[str] = None,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    check_window(start, end)
    scoped = await roster_svc.scoped_employees(db, current_user)
    if not scoped and not roster_svc.is_roster_admin(current_user):
        raise HTTPException(
            status_code=403, detail="You have no roster scope.",
        )
    emps = [e for e in scoped if not department or e.department == department]
    return await roster_svc.build_grid(
        db, current_user, start, end, department, employees=emps
    )



@router.post("/bulk", response_model=RosterBulkResult)
@guard_conflicts
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
    await validate_templates(
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
        # A blank explicit entry (no shift, not week-off) has no meaning
        # (cells are cleared via DELETE): skip it, never create a row.
        kept = [c for c in cells if c[2] is not None or c[3]]
        result.skipped += len(cells) - len(kept)
        cells = kept
    else:
        pc = roster_svc.expand_pattern(body.pattern, body.start, body.end)
        cells = [
            (uid, wd, tpl_id, week_off)
            for uid in sorted(allowed) for (wd, tpl_id, week_off) in pc
        ]
    await write_cells(
        db, current_user, allowed, cells, body.status, body.overwrite, result,
        reason=roster_svc.clean_reason(body.reason) or "bulk re-plan",
        lock_reason=body.reason,
    )

    await commit_or_409(db)
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
@guard_conflicts
async def upsert_single_entry(
    *,
    db: deps.DBDep,
    request: Request,
    body: RosterEntrySingleInput,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    await require_manage(db, current_user, body.employee_id)
    await validate_templates(db, [body.shift_template_id])
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
    prior = (await db.execute(
        select(RosterEntry).where(
            RosterEntry.employee_id == body.employee_id,
            RosterEntry.work_date == body.work_date,
        )
    )).scalars().first()
    prior_snap = (
        (prior.shift_template_id, prior.is_week_off, prior.status)
        if prior is not None else None
    )
    reason = roster_svc.clean_reason(body.reason)
    live_change = (
        can_pub and prior_snap is not None
        and prior_snap[2] == RosterStatus.PUBLISHED
        and roster_svc.edit_changes_live(
            prior_snap[0], prior_snap[1], body.shift_template_id,
            body.is_week_off, eff_status == RosterStatus.PUBLISHED,
        )
    )
    if live_change and reason is None:
        raise HTTPException(status_code=422, detail=REASON_MSG)
    old_live, new_live = await _live_transition(
        db, body.employee_id, body.work_date, prior_snap,
        eff_status, body.shift_template_id, body.is_week_off,
    )
    if prior_snap is not None and prior_snap[2] == RosterStatus.PUBLISHED \
            and not can_pub:
        raise HTTPException(status_code=403, detail=NO_PUBLISH_MSG)
    locked = await roster_svc.lock_guard(
        db, current_user,
        [(body.employee_id, body.work_date, old_live, new_live)],
        reason=reason,
    )
    emergency = bool(locked)
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
    if live_change or emergency:
        new_tpl = None if body.is_week_off else body.shift_template_id
        new_off = body.is_week_off
        if emergency:  # history shows what the employee actually sees
            new_tpl, new_off = new_live
        await db.flush()
        roster_svc.record_change(
            db, entry, employee_id=body.employee_id,
            work_date=body.work_date,
            old_tpl=old_live[0] if emergency else prior_snap[0],
            old_off=old_live[1] if emergency else prior_snap[1],
            new_tpl=new_tpl, new_off=new_off, action="update",
            reason=reason, actor_id=current_user.id, emergency=emergency,
        )
        await roster_svc.notify_schedule_changed(
            db, {body.employee_id: {body.work_date}}
        )
    await commit_or_409(db)
    await db.refresh(entry)
    await log_audit(
        db, current_user.id, "roster.entry.upsert",
        "roster_entry", str(entry.id),
        {"outcome": outcome, "work_date": body.work_date.isoformat()},
        request,
    )
    read = await entry_read(db, entry)
    if body.status == RosterStatus.PUBLISHED and eff_status != body.status:
        read.notice = DRAFT_NOTICE
    return read


@router.patch("/entries/{entry_id}", response_model=RosterEntryRead)
@guard_conflicts
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
    await require_manage(db, current_user, entry.employee_id)
    changes = body.model_dump(exclude_unset=True)
    reason = changes.pop("reason", None)
    for k in ("is_week_off", "status"):
        if k in changes and changes[k] is None:
            raise HTTPException(status_code=422, detail=f"{k} cannot be null")
    if "shift_template_id" in changes:
        await validate_templates(db, [changes["shift_template_id"]])
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
    if not (
        changes.get("is_week_off", entry.is_week_off)
        or changes.get("shift_template_id", entry.shift_template_id)
    ):
        raise HTTPException(
            status_code=422,
            detail="A cell needs a shift template or week-off",
        )
    was_published = entry.status == RosterStatus.PUBLISHED
    reason = roster_svc.clean_reason(reason)
    old_tpl, old_off = entry.shift_template_id, entry.is_week_off
    live_change = was_published and roster_svc.edit_changes_live(
        old_tpl, old_off,
        changes.get("shift_template_id", old_tpl),
        changes.get("is_week_off", old_off),
        changes.get("status", entry.status) == RosterStatus.PUBLISHED,
    )
    if live_change and reason is None:
        raise HTTPException(status_code=422, detail=REASON_MSG)
    n_tpl = changes.get("shift_template_id", old_tpl)
    n_off = changes.get("is_week_off", old_off)
    if n_off:
        n_tpl = None
    old_live, new_live = await _live_transition(
        db, entry.employee_id, entry.work_date,
        (old_tpl, old_off, entry.status),
        changes.get("status", entry.status), n_tpl, n_off,
    )
    locked = await roster_svc.lock_guard(
        db, current_user,
        [(entry.employee_id, entry.work_date, old_live, new_live)],
        reason=reason,
    )
    emergency = bool(locked)
    for k, v in changes.items():
        setattr(entry, k, v)
    if entry.is_week_off:
        entry.shift_template_id = None
    entry.assigned_by_id = current_user.id
    if live_change or emergency:
        roster_svc.record_change(
            db, entry, employee_id=entry.employee_id,
            work_date=entry.work_date,
            old_tpl=old_live[0] if emergency else old_tpl,
            old_off=old_live[1] if emergency else old_off,
            new_tpl=new_live[0] if emergency else entry.shift_template_id,
            new_off=new_live[1] if emergency else entry.is_week_off,
            action="update", reason=reason, actor_id=current_user.id,
            emergency=emergency,
        )
        await roster_svc.notify_schedule_changed(
            db, {entry.employee_id: {entry.work_date}}
        )
    await commit_or_409(db)
    await db.refresh(entry)
    await log_audit(
        db, current_user.id, "roster.entry.update",
        "roster_entry", str(entry.id),
        {"changed": list(changes.keys())}, request,
    )
    return await entry_read(db, entry)


@router.delete("/entries/{entry_id}")
@guard_conflicts
async def delete_entry(
    *,
    db: deps.DBDep,
    request: Request,
    entry_id: int,
    reason: Optional[str] = Query(None, max_length=500),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    entry = await db.get(RosterEntry, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Roster entry not found")
    await require_manage(db, current_user, entry.employee_id)
    if entry.status == RosterStatus.PUBLISHED:
        if not await roster_svc.can_publish_for(
            db, current_user, entry.employee_id
        ):
            raise HTTPException(status_code=403, detail=NO_PUBLISH_MSG)
        reason = roster_svc.clean_reason(reason)
        if reason is None:
            raise HTTPException(status_code=422, detail=REASON_MSG)
        old_live, new_live = await _live_transition(
            db, entry.employee_id, entry.work_date,
            (entry.shift_template_id, entry.is_week_off, entry.status),
            RosterStatus.DRAFT, None, False,
        )
        locked = await roster_svc.lock_guard(
            db, current_user,
            [(entry.employee_id, entry.work_date, old_live, new_live)],
            reason=reason,
        )
        roster_svc.record_change(
            db, None, employee_id=entry.employee_id,
            work_date=entry.work_date,
            old_tpl=entry.shift_template_id, old_off=entry.is_week_off,
            new_tpl=None, new_off=False, action="delete", reason=reason,
            actor_id=current_user.id, emergency=bool(locked),
        )
        await roster_svc.notify_schedule_changed(
            db, {entry.employee_id: {entry.work_date}}
        )
    await db.delete(entry)
    await commit_or_409(db)
    await log_audit(
        db, current_user.id, "roster.entry.delete",
        "roster_entry", str(entry_id), {}, request,
    )
    return {"status": "deleted", "id": entry_id}



# ----------------------------- employee self-service -----------------------------

@router.get("/my", response_model=List[RosterEntryRead])
async def my_roster(
    db: deps.DBDep,
    start: Optional[pydate] = Query(None),
    end: Optional[pydate] = Query(None),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    today = await local_today(db)
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
    return [await entry_read(db, r) for r in rows]


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
    from app.services.time_rules import build_default_shift, get_time_rules

    today = await local_today(db)
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
                "shift_template_id": entry.shift_template_id,
                "transport_required": bool(entry.transport_required),
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
                    "shift_template_id": tpl.id,
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


async def _lock_cr(db, cr_id: int):
    """Row-lock the change request (fresh state) so status checks and the
    decision are atomic against concurrent decide/cancel."""
    return await lock_row(
        db, select(RosterChangeRequest).where(RosterChangeRequest.id == cr_id)
    )


@router.post("/change-requests", response_model=RosterChangeRequestRead)
@guard_conflicts
async def create_change_request(
    *,
    db: deps.DBDep,
    request: Request,
    body: RosterChangeRequestCreate,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    if not body.requested_week_off:
        await validate_templates(db, [body.requested_shift_template_id])
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
    await commit_or_409(db)
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
@guard_conflicts
async def decide_change_request(
    *,
    db: deps.DBDep,
    request: Request,
    cr_id: int,
    body: RosterChangeDecision,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    cr = await _lock_cr(db, cr_id)
    if not cr:
        raise HTTPException(status_code=404, detail="Request not found")
    if cr.status != RosterChangeStatus.PENDING:
        raise HTTPException(status_code=409, detail="Request already decided")
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
        if not cr.requested_week_off:
            await validate_templates(db, [cr.requested_shift_template_id])
        emp = (await db.execute(
            select(Employee).where(Employee.user_id == cr.employee_id)
        )).scalars().first()
        prior = (await db.execute(
            select(RosterEntry).where(
                RosterEntry.employee_id == cr.employee_id,
                RosterEntry.work_date == cr.work_date,
            )
        )).scalars().first()
        prior_snap = (
            (prior.shift_template_id, prior.is_week_off, prior.status)
            if prior is not None else None
        )
        new_tpl = (
            None if cr.requested_week_off else cr.requested_shift_template_id
        )
        cr_reason = (roster_svc.clean_reason(cr.reason)
                     or f"approved change request #{cr.id}")
        # Lock window: the employee requested this change -> exempt.
        _e, _o = await roster_svc.upsert_entry(
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
        was_live = (
            prior_snap is not None and prior_snap[2] == RosterStatus.PUBLISHED
        )
        live_changed = was_live and (prior_snap[0], prior_snap[1]) != (
            new_tpl, cr.requested_week_off)
        if live_changed:
            roster_svc.record_change(
                db, _e, employee_id=cr.employee_id, work_date=cr.work_date,
                old_tpl=prior_snap[0], old_off=prior_snap[1],
                new_tpl=new_tpl, new_off=cr.requested_week_off,
                action="update", reason=cr_reason,
                actor_id=current_user.id,
            )
        if live_changed or not was_live:
            await roster_svc.notify_schedule_changed(
                db, {cr.employee_id: {cr.work_date}}
            )
        cr.status = RosterChangeStatus.APPROVED
    else:
        cr.status = RosterChangeStatus.REJECTED
    cr.decided_by_id = current_user.id
    cr.decided_at = datetime.now(timezone.utc)
    cr.decision_note = body.decision_note
    await commit_or_409(db)
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
@guard_conflicts
async def cancel_change_request(
    *,
    db: deps.DBDep,
    request: Request,
    cr_id: int,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    cr = await _lock_cr(db, cr_id)
    if not cr:
        raise HTTPException(status_code=404, detail="Request not found")
    if cr.employee_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your request")
    if cr.status != RosterChangeStatus.PENDING:
        raise HTTPException(status_code=409, detail="Only pending requests can be cancelled")
    cr.status = RosterChangeStatus.CANCELLED
    await commit_or_409(db, "Request already decided")
    await db.refresh(cr)
    await log_audit(
        db, current_user.id, "roster.change.cancel",
        "roster_change_request", str(cr.id), {}, request,
    )
    return await _cr_read(db, cr)


