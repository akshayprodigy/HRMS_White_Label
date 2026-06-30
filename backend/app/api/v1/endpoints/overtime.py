"""Overtime + Night-shift allowance endpoints.

CRUD for the two rule masters, recompute over a date-range, per-employee
OT approval queue, monthly summary report, and the employee self-view.

Payroll injection is NOT here — that's wired in payroll.generate_draft so
that the lines appear in the existing line editor and payslip flow.
"""
import calendar as _cal
from datetime import date, datetime, timezone
from typing import Any, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import selectinload

from app.api import deps
from app.api.v1.endpoints.hr import log_audit
from app.models.approval import ApprovalItem, ApprovalStatus, ApprovalStep
from app.models.attendance import Attendance
from app.models.employee import Employee
from app.models.hr import HolidayCalendar
from app.models.notification import Notification
from app.models.overtime import (
    DayType as DayTypeConst,
    NightAllowanceEntry,
    NightShiftAllowanceRule,
    OvertimeEntry,
    OvertimeRule,
    OvertimeScope,
    OvertimeStatus,
)
from app.models.payroll import PayrollRun, PayrollRunStatus
from app.models.shift import EmployeeShiftAssignment, ShiftTemplate
from app.models.user import User
from app.schemas.overtime import (
    NightAllowanceEntryRead,
    NightRuleCreate,
    NightRuleRead,
    NightRuleUpdate,
    OvertimeActionRequest,
    OvertimeEntryRead,
    OvertimeMonthlySummary,
    OvertimeRuleCreate,
    OvertimeRuleRead,
    OvertimeRuleUpdate,
    RecomputeRequest,
    RecomputeResult,
)
from app.services.overtime import (
    DayType as DayTypeEnum,
    HOURLY_RATE_BASIS_DOC,
    classify_day_type,
    compute_night_allowance,
    compute_overtime,
)
from app.services.shift_resolver import worked_hours as compute_worked_hours

router = APIRouter()


PERM_RULE_WRITE = "overtime rule write"   # Manage rules
PERM_APPROVE = "overtime approve"          # Approve/reject OT entries
PERM_VIEW_ALL = "overtime view all"        # See everyone's entries (HR/admin)


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------


def _enrich_rule(rule: OvertimeRule) -> dict:
    name = (
        rule.shift_template.name if getattr(rule, "shift_template", None)
        else None
    )
    return {**rule.__dict__, "shift_template_name": name}


def _enrich_night_rule(rule: NightShiftAllowanceRule) -> dict:
    name = (
        rule.shift_template.name if getattr(rule, "shift_template", None)
        else None
    )
    return {**rule.__dict__, "shift_template_name": name}


async def _pick_ot_rule(
    db, shift_id: Optional[int]
) -> Optional[OvertimeRule]:
    """Per-shift rule wins; org_default is the fallback. is_active only."""
    if shift_id is not None:
        per_shift = (await db.execute(
            select(OvertimeRule).where(
                and_(
                    OvertimeRule.shift_template_id == shift_id,
                    OvertimeRule.scope == OvertimeScope.SHIFT,
                    OvertimeRule.is_active.is_(True),
                )
            ).limit(1)
        )).scalar_one_or_none()
        if per_shift is not None:
            return per_shift
    org = (await db.execute(
        select(OvertimeRule).where(
            and_(
                OvertimeRule.scope == OvertimeScope.ORG_DEFAULT,
                OvertimeRule.is_active.is_(True),
            )
        ).limit(1)
    )).scalar_one_or_none()
    return org


async def _pick_night_rule(
    db, shift_id: Optional[int]
) -> Optional[NightShiftAllowanceRule]:
    if shift_id is not None:
        per_shift = (await db.execute(
            select(NightShiftAllowanceRule).where(
                and_(
                    NightShiftAllowanceRule.shift_template_id == shift_id,
                    NightShiftAllowanceRule.scope == OvertimeScope.SHIFT,
                    NightShiftAllowanceRule.is_active.is_(True),
                )
            ).limit(1)
        )).scalar_one_or_none()
        if per_shift is not None:
            return per_shift
    org = (await db.execute(
        select(NightShiftAllowanceRule).where(
            and_(
                NightShiftAllowanceRule.scope == OvertimeScope.ORG_DEFAULT,
                NightShiftAllowanceRule.is_active.is_(True),
            )
        ).limit(1)
    )).scalar_one_or_none()
    return org


async def _load_holidays(
    db, start: date, end: date
) -> set[date]:
    rows = (await db.execute(
        select(HolidayCalendar.date).where(
            and_(
                HolidayCalendar.date >= start,
                HolidayCalendar.date <= end,
                HolidayCalendar.location.in_(["All", "HQ"]),
            )
        )
    )).scalars().all()
    return set(rows)


async def _basic_for(db, user_id: int) -> float:
    """Basic salary from Employee. Zero when not set — drives no-rule
    no-regression because OT amount becomes zero too."""
    emp = (await db.execute(
        select(Employee).where(Employee.user_id == user_id)
    )).scalar_one_or_none()
    if emp is None:
        return 0.0
    return float(emp.salary or 0.0)


def _month_window(work_date: date) -> Tuple[date, date]:
    days = _cal.monthrange(work_date.year, work_date.month)[1]
    return (
        date(work_date.year, work_date.month, 1),
        date(work_date.year, work_date.month, days),
    )


async def _monthly_used_minutes(
    db, user_id: int, work_date: date, exclude_entry_id: Optional[int],
) -> int:
    start, end = _month_window(work_date)
    stmt = select(func.coalesce(func.sum(OvertimeEntry.ot_minutes), 0)).where(
        and_(
            OvertimeEntry.user_id == user_id,
            OvertimeEntry.work_date >= start,
            OvertimeEntry.work_date <= end,
            OvertimeEntry.status.in_([
                OvertimeStatus.APPROVED, OvertimeStatus.AUTO_APPROVED,
                OvertimeStatus.PENDING,
            ]),
        )
    )
    if exclude_entry_id is not None:
        stmt = stmt.where(OvertimeEntry.id != exclude_entry_id)
    return int((await db.execute(stmt)).scalar() or 0)


# ----------------------------------------------------------------------
# OvertimeRule CRUD
# ----------------------------------------------------------------------


@router.get("/meta")
async def get_meta(
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Surface the hourly-rate basis so the rules-admin page can show it
    inline and auditors can see policy at a glance."""
    return {
        "hourly_rate_basis": HOURLY_RATE_BASIS_DOC,
        "ot_status_values": [
            OvertimeStatus.PENDING, OvertimeStatus.APPROVED,
            OvertimeStatus.REJECTED, OvertimeStatus.AUTO_APPROVED,
        ],
    }


@router.get("/rules", response_model=List[OvertimeRuleRead])
async def list_ot_rules(
    db: deps.DBDep,
    include_inactive: bool = Query(False),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    stmt = select(OvertimeRule).options(
        selectinload(OvertimeRule.shift_template)
    )
    if not include_inactive:
        stmt = stmt.where(OvertimeRule.is_active.is_(True))
    rows = (await db.execute(stmt)).scalars().all()
    return [
        OvertimeRuleRead.model_validate(_enrich_rule(r)) for r in rows
    ]


@router.post("/rules", response_model=OvertimeRuleRead)
async def create_ot_rule(
    payload: OvertimeRuleCreate,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_RULE_WRITE])),
) -> Any:
    if payload.scope == OvertimeScope.SHIFT:
        tmpl = await db.get(ShiftTemplate, payload.shift_template_id)
        if tmpl is None:
            raise HTTPException(404, "Shift template not found")
    obj = OvertimeRule(**payload.model_dump(), created_by_id=current_user.id)
    db.add(obj)
    await db.flush()
    await log_audit(
        db, current_user.id, "OT_RULE_CREATE", "overtime_rule",
        str(obj.id), payload.model_dump(), request,
    )
    await db.commit()
    await db.refresh(obj, ["shift_template"])
    return OvertimeRuleRead.model_validate(_enrich_rule(obj))


@router.patch("/rules/{rule_id}", response_model=OvertimeRuleRead)
async def update_ot_rule(
    rule_id: int,
    payload: OvertimeRuleUpdate,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_RULE_WRITE])),
) -> Any:
    rule = await db.get(OvertimeRule, rule_id)
    if rule is None:
        raise HTTPException(404, "Rule not found")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(rule, k, v)
    await db.flush()
    await log_audit(
        db, current_user.id, "OT_RULE_UPDATE", "overtime_rule",
        str(rule_id), data, request,
    )
    await db.commit()
    await db.refresh(rule, ["shift_template"])
    return OvertimeRuleRead.model_validate(_enrich_rule(rule))


@router.delete("/rules/{rule_id}")
async def delete_ot_rule(
    rule_id: int,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_RULE_WRITE])),
) -> Any:
    rule = await db.get(OvertimeRule, rule_id)
    if rule is None:
        raise HTTPException(404, "Rule not found")
    # Soft-deactivate (don't break historical entry FK).
    rule.is_active = False
    await log_audit(
        db, current_user.id, "OT_RULE_DEACTIVATE", "overtime_rule",
        str(rule_id), {}, request,
    )
    await db.commit()
    return {"message": "Rule deactivated"}


# ----------------------------------------------------------------------
# Night-rule CRUD
# ----------------------------------------------------------------------


@router.get("/night-rules", response_model=List[NightRuleRead])
async def list_night_rules(
    db: deps.DBDep,
    include_inactive: bool = Query(False),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    stmt = select(NightShiftAllowanceRule).options(
        selectinload(NightShiftAllowanceRule.shift_template)
    )
    if not include_inactive:
        stmt = stmt.where(NightShiftAllowanceRule.is_active.is_(True))
    rows = (await db.execute(stmt)).scalars().all()
    return [
        NightRuleRead.model_validate(_enrich_night_rule(r)) for r in rows
    ]


@router.post("/night-rules", response_model=NightRuleRead)
async def create_night_rule(
    payload: NightRuleCreate,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_RULE_WRITE])),
) -> Any:
    if payload.scope == OvertimeScope.SHIFT:
        tmpl = await db.get(ShiftTemplate, payload.shift_template_id)
        if tmpl is None:
            raise HTTPException(404, "Shift template not found")
    obj = NightShiftAllowanceRule(
        **payload.model_dump(), created_by_id=current_user.id
    )
    db.add(obj)
    await db.flush()
    await log_audit(
        db, current_user.id, "NIGHT_RULE_CREATE", "night_shift_allowance_rule",
        str(obj.id), payload.model_dump(mode="json"), request,
    )
    await db.commit()
    await db.refresh(obj, ["shift_template"])
    return NightRuleRead.model_validate(_enrich_night_rule(obj))


@router.patch("/night-rules/{rule_id}", response_model=NightRuleRead)
async def update_night_rule(
    rule_id: int,
    payload: NightRuleUpdate,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_RULE_WRITE])),
) -> Any:
    rule = await db.get(NightShiftAllowanceRule, rule_id)
    if rule is None:
        raise HTTPException(404, "Rule not found")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(rule, k, v)
    await db.flush()
    await log_audit(
        db, current_user.id, "NIGHT_RULE_UPDATE",
        "night_shift_allowance_rule", str(rule_id),
        {k: (v.isoformat() if hasattr(v, "isoformat") else v)
         for k, v in data.items()},
        request,
    )
    await db.commit()
    await db.refresh(rule, ["shift_template"])
    return NightRuleRead.model_validate(_enrich_night_rule(rule))


@router.delete("/night-rules/{rule_id}")
async def delete_night_rule(
    rule_id: int,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_RULE_WRITE])),
) -> Any:
    rule = await db.get(NightShiftAllowanceRule, rule_id)
    if rule is None:
        raise HTTPException(404, "Rule not found")
    rule.is_active = False
    await log_audit(
        db, current_user.id, "NIGHT_RULE_DEACTIVATE",
        "night_shift_allowance_rule", str(rule_id), {}, request,
    )
    await db.commit()
    return {"message": "Rule deactivated"}


# ----------------------------------------------------------------------
# entries — list / approve / reject
# ----------------------------------------------------------------------


def _user_can_view_all(user: User) -> bool:
    if user.is_superuser:
        return True
    role_names = [(r.name or "").lower() for r in user.roles or []]
    if any(n in role_names for n in ("hr", "super admin", "admin")):
        return True
    for role in user.roles or []:
        for perm in role.permissions or []:
            if (perm.name or "") in (PERM_VIEW_ALL, PERM_APPROVE, PERM_RULE_WRITE):
                return True
    return False


async def _enrich_entry_row(db, e: OvertimeEntry) -> OvertimeEntryRead:
    user_name = None
    user = await db.get(User, e.user_id)
    if user is not None:
        user_name = user.full_name
    tmpl_name = None
    if e.shift_template_id:
        tmpl = await db.get(ShiftTemplate, e.shift_template_id)
        tmpl_name = tmpl.name if tmpl else None
    # Derive worked hours from the original attendance for context.
    worked = None
    if e.attendance_id:
        att = await db.get(Attendance, e.attendance_id)
        if att is not None and att.punch_out_time:
            sh = await db.get(ShiftTemplate, e.shift_template_id) if e.shift_template_id else None
            worked = compute_worked_hours(att.captured_at, att.punch_out_time, sh)
    data = {
        c.name: getattr(e, c.name) for c in e.__table__.columns
    }
    data["user_full_name"] = user_name
    data["shift_template_name"] = tmpl_name
    data["worked_hours"] = round(worked, 2) if worked is not None else None
    return OvertimeEntryRead.model_validate(data)


@router.get("/entries", response_model=List[OvertimeEntryRead])
async def list_ot_entries(
    db: deps.DBDep,
    start: Optional[date] = Query(None),
    end: Optional[date] = Query(None),
    status: Optional[str] = Query(
        None, pattern="^(pending|approved|rejected|auto_approved)$"
    ),
    user_id: Optional[int] = Query(None),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    stmt = select(OvertimeEntry)
    if start is not None:
        stmt = stmt.where(OvertimeEntry.work_date >= start)
    if end is not None:
        stmt = stmt.where(OvertimeEntry.work_date <= end)
    if status is not None:
        stmt = stmt.where(OvertimeEntry.status == status)

    view_all = _user_can_view_all(current_user)
    if not view_all:
        # Employee: see only own.
        stmt = stmt.where(OvertimeEntry.user_id == current_user.id)
    elif user_id is not None:
        stmt = stmt.where(OvertimeEntry.user_id == user_id)

    stmt = stmt.order_by(OvertimeEntry.work_date.desc(), OvertimeEntry.id.desc())
    rows = (await db.execute(stmt)).scalars().all()
    out: List[OvertimeEntryRead] = []
    for r in rows:
        out.append(await _enrich_entry_row(db, r))
    return out


@router.get("/entries/my", response_model=List[OvertimeEntryRead])
async def my_ot_entries(
    db: deps.DBDep,
    start: Optional[date] = Query(None),
    end: Optional[date] = Query(None),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    stmt = select(OvertimeEntry).where(OvertimeEntry.user_id == current_user.id)
    if start is not None:
        stmt = stmt.where(OvertimeEntry.work_date >= start)
    if end is not None:
        stmt = stmt.where(OvertimeEntry.work_date <= end)
    stmt = stmt.order_by(OvertimeEntry.work_date.desc())
    rows = (await db.execute(stmt)).scalars().all()
    return [await _enrich_entry_row(db, r) for r in rows]


@router.get("/night-entries", response_model=List[NightAllowanceEntryRead])
async def list_night_entries(
    db: deps.DBDep,
    start: Optional[date] = Query(None),
    end: Optional[date] = Query(None),
    user_id: Optional[int] = Query(None),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    stmt = select(NightAllowanceEntry)
    if start is not None:
        stmt = stmt.where(NightAllowanceEntry.work_date >= start)
    if end is not None:
        stmt = stmt.where(NightAllowanceEntry.work_date <= end)
    view_all = _user_can_view_all(current_user)
    if not view_all:
        stmt = stmt.where(NightAllowanceEntry.user_id == current_user.id)
    elif user_id is not None:
        stmt = stmt.where(NightAllowanceEntry.user_id == user_id)
    stmt = stmt.order_by(
        NightAllowanceEntry.work_date.desc(), NightAllowanceEntry.id.desc()
    )
    rows = (await db.execute(stmt)).scalars().all()
    out: List[NightAllowanceEntryRead] = []
    for r in rows:
        user_name = None
        user = await db.get(User, r.user_id)
        if user is not None:
            user_name = user.full_name
        data = {c.name: getattr(r, c.name) for c in r.__table__.columns}
        data["user_full_name"] = user_name
        out.append(NightAllowanceEntryRead.model_validate(data))
    return out


@router.get("/night-entries/my", response_model=List[NightAllowanceEntryRead])
async def my_night_entries(
    db: deps.DBDep,
    start: Optional[date] = Query(None),
    end: Optional[date] = Query(None),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    stmt = select(NightAllowanceEntry).where(
        NightAllowanceEntry.user_id == current_user.id
    )
    if start is not None:
        stmt = stmt.where(NightAllowanceEntry.work_date >= start)
    if end is not None:
        stmt = stmt.where(NightAllowanceEntry.work_date <= end)
    stmt = stmt.order_by(NightAllowanceEntry.work_date.desc())
    rows = (await db.execute(stmt)).scalars().all()
    out: List[NightAllowanceEntryRead] = []
    for r in rows:
        data = {c.name: getattr(r, c.name) for c in r.__table__.columns}
        data["user_full_name"] = current_user.full_name
        out.append(NightAllowanceEntryRead.model_validate(data))
    return out


def _user_can_approve(user: User, employee_manager_id: Optional[int]) -> bool:
    if user.is_superuser:
        return True
    role_names = [(r.name or "").lower() for r in user.roles or []]
    if "hr" in role_names or "super admin" in role_names or "admin" in role_names:
        return True
    for role in user.roles or []:
        for perm in role.permissions or []:
            if (perm.name or "") == PERM_APPROVE:
                return True
    if employee_manager_id is not None and user.id == employee_manager_id:
        return True
    return False


@router.post("/entries/{entry_id}/action", response_model=OvertimeEntryRead)
async def action_ot_entry(
    entry_id: int,
    payload: OvertimeActionRequest,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    entry = await db.get(OvertimeEntry, entry_id)
    if entry is None:
        raise HTTPException(404, "OT entry not found")
    if entry.status in (OvertimeStatus.APPROVED, OvertimeStatus.AUTO_APPROVED):
        raise HTTPException(400, f"Entry is already {entry.status}")
    if entry.payroll_run_id is not None:
        raise HTTPException(
            400, "Entry has been injected into a payroll run already"
        )

    # Manager-or-HR gate.
    employee = await db.get(User, entry.user_id)
    mgr_id = getattr(employee, "manager_id", None)
    if not _user_can_approve(current_user, mgr_id):
        raise HTTPException(403, "Not authorized to action this OT entry")

    now = datetime.now(timezone.utc)
    if payload.action == "approve":
        entry.status = OvertimeStatus.APPROVED
        entry.approver_id = current_user.id
        entry.approved_at = now
        action_label = "OT_APPROVE"
        notif_title = "Overtime approved"
        notif_msg = (
            f"Your OT for {entry.work_date} ({entry.ot_minutes} min) was approved."
        )
        notif_type = "success"
    else:
        entry.status = OvertimeStatus.REJECTED
        entry.approver_id = current_user.id
        entry.approved_at = now
        entry.rejection_reason = payload.comment or None
        action_label = "OT_REJECT"
        notif_title = "Overtime rejected"
        notif_msg = (
            f"Your OT for {entry.work_date} was rejected"
            + (f": {payload.comment}" if payload.comment else "")
        )
        notif_type = "warning"

    # Notify employee.
    db.add(Notification(
        user_id=entry.user_id,
        title=notif_title, message=notif_msg, type=notif_type,
        resource_type="overtime_entry", resource_id=str(entry.id),
    ))

    # Update the linked Approvals item, if any, for parity with the
    # central Approvals inbox.
    if entry.approval_item_id is not None:
        item = await db.execute(
            select(ApprovalItem).where(
                ApprovalItem.id == entry.approval_item_id
            ).options(selectinload(ApprovalItem.steps))
        )
        item = item.scalar_one_or_none()
        if item is not None:
            for step in item.steps:
                if step.status == ApprovalStatus.PENDING:
                    step.status = (
                        ApprovalStatus.APPROVED if payload.action == "approve"
                        else ApprovalStatus.REJECTED
                    )
                    step.approver_id = current_user.id
                    step.actioned_at = now
                    step.comment = payload.comment or step.comment
            item.status = (
                ApprovalStatus.APPROVED if payload.action == "approve"
                else ApprovalStatus.REJECTED
            )

    await log_audit(
        db, current_user.id, action_label, "overtime_entry",
        str(entry.id),
        {
            "ot_minutes": entry.ot_minutes,
            "ot_amount": entry.ot_amount,
            "comment": payload.comment,
        },
        request,
    )
    await db.commit()
    await db.refresh(entry)
    return await _enrich_entry_row(db, entry)


# ----------------------------------------------------------------------
# recompute
# ----------------------------------------------------------------------


async def _resolve_one(
    db,
    *,
    user_id: int,
    work_date: date,
    attendance: Optional[Attendance],
    holiday_set: set[date],
    requested_by_id: int,
) -> Tuple[int, int, int]:
    """Compute (and upsert) one OT entry + one night entry for the
    (user, work_date) pair.

    Returns (ot_state, night_state, ot_minutes_used_for_running_total)
    where states are 0=skipped(finalized), 1=created, 2=updated.
    """
    # Locate any existing entries.
    ot_existing = (await db.execute(
        select(OvertimeEntry).where(
            and_(
                OvertimeEntry.user_id == user_id,
                OvertimeEntry.work_date == work_date,
            )
        )
    )).scalar_one_or_none()
    night_existing = (await db.execute(
        select(NightAllowanceEntry).where(
            and_(
                NightAllowanceEntry.user_id == user_id,
                NightAllowanceEntry.work_date == work_date,
            )
        )
    )).scalar_one_or_none()

    # Hard guard: do not touch finalized entries.
    if (
        (ot_existing is not None and ot_existing.payroll_run_id is not None)
        or (
            night_existing is not None
            and night_existing.payroll_run_id is not None
        )
    ):
        return (0, 0, ot_existing.ot_minutes if ot_existing else 0)

    if attendance is None:
        return (0, 0, ot_existing.ot_minutes if ot_existing else 0)

    shift = None
    if attendance.shift_template_id:
        shift = await db.get(ShiftTemplate, attendance.shift_template_id)

    basic = await _basic_for(db, user_id)
    ot_rule = await _pick_ot_rule(db, attendance.shift_template_id)
    night_rule = await _pick_night_rule(db, attendance.shift_template_id)

    # OT computation.
    worked = compute_worked_hours(
        attendance.captured_at, attendance.punch_out_time, shift,
    )
    day_type = classify_day_type(
        work_date, shift, holiday_set
    )
    monthly_used = await _monthly_used_minutes(
        db, user_id, work_date,
        exclude_entry_id=ot_existing.id if ot_existing else None,
    )
    ot = compute_overtime(
        worked_hours=worked, basic_salary=basic,
        rule=ot_rule, shift=shift,
        day_type=day_type,
        monthly_minutes_used=monthly_used,
    )

    ot_state = 0
    if ot.ot_minutes > 0 and ot_rule is not None:
        status = (
            OvertimeStatus.PENDING if ot_rule.requires_approval
            else OvertimeStatus.AUTO_APPROVED
        )
        if ot_existing is None:
            new_ot = OvertimeEntry(
                user_id=user_id, work_date=work_date,
                attendance_id=attendance.id,
                shift_template_id=attendance.shift_template_id,
                rule_id=ot_rule.id,
                ot_minutes=ot.ot_minutes, ot_amount=ot.ot_amount,
                hourly_rate_used=ot.hourly_rate_used,
                multiplier_used=ot.multiplier_used,
                day_type=str(ot.day_type.value),
                status=status,
            )
            db.add(new_ot)
            await db.flush()
            ot_existing = new_ot
            ot_state = 1
        else:
            if (
                ot_existing.ot_minutes != ot.ot_minutes
                or ot_existing.ot_amount != ot.ot_amount
                or ot_existing.day_type != ot.day_type.value
                or ot_existing.rule_id != ot_rule.id
                or ot_existing.multiplier_used != ot.multiplier_used
            ):
                ot_existing.attendance_id = attendance.id
                ot_existing.shift_template_id = attendance.shift_template_id
                ot_existing.rule_id = ot_rule.id
                ot_existing.ot_minutes = ot.ot_minutes
                ot_existing.ot_amount = ot.ot_amount
                ot_existing.hourly_rate_used = ot.hourly_rate_used
                ot_existing.multiplier_used = ot.multiplier_used
                ot_existing.day_type = str(ot.day_type.value)
                if ot_existing.status not in (
                    OvertimeStatus.APPROVED, OvertimeStatus.AUTO_APPROVED,
                ):
                    ot_existing.status = status
                ot_state = 2

        # Create approval-engine row when needed (manager-step only;
        # HR can also action via the OT approval queue).
        if (
            ot_existing.status == OvertimeStatus.PENDING
            and ot_existing.approval_item_id is None
        ):
            emp = await db.get(User, user_id)
            item = ApprovalItem(
                resource_type="overtime_entry",
                resource_id=str(ot_existing.id),
                status=ApprovalStatus.PENDING,
                current_step_number=1,
                requested_by_id=user_id,
            )
            db.add(item)
            await db.flush()
            step = ApprovalStep(
                approval_item_id=item.id,
                step_number=1,
                approver_id=getattr(emp, "manager_id", None) or requested_by_id,
                status=ApprovalStatus.PENDING,
            )
            db.add(step)
            ot_existing.approval_item_id = item.id
            # Notify the manager.
            if getattr(emp, "manager_id", None):
                db.add(Notification(
                    user_id=emp.manager_id,
                    title="Overtime awaiting approval",
                    message=(
                        f"{emp.full_name} logged {ot.ot_minutes} OT minutes "
                        f"on {work_date}."
                    ),
                    type="info",
                    resource_type="overtime_entry",
                    resource_id=str(ot_existing.id),
                ))

    elif ot_existing is not None and ot.ot_minutes == 0:
        # Rule recompute zeroed this entry; soft-reset minutes/amount and
        # leave the row for auditability (never delete).
        if ot_existing.ot_minutes != 0:
            ot_existing.ot_minutes = 0
            ot_existing.ot_amount = 0.0
            ot_existing.attendance_id = attendance.id
            ot_state = 2

    # Night allowance.
    night = compute_night_allowance(
        punch_in=attendance.captured_at,
        punch_out=attendance.punch_out_time,
        work_date=work_date, rule=night_rule,
    )
    night_state = 0
    if night.night_minutes > 0 and night_rule is not None:
        if night_existing is None:
            db.add(NightAllowanceEntry(
                user_id=user_id, work_date=work_date,
                attendance_id=attendance.id, rule_id=night_rule.id,
                night_minutes=night.night_minutes, amount=night.amount,
                payout_model_used=str(night.payout_model_used.value),
            ))
            night_state = 1
        else:
            if (
                night_existing.night_minutes != night.night_minutes
                or night_existing.amount != night.amount
                or night_existing.rule_id != night_rule.id
            ):
                night_existing.attendance_id = attendance.id
                night_existing.rule_id = night_rule.id
                night_existing.night_minutes = night.night_minutes
                night_existing.amount = night.amount
                night_existing.payout_model_used = str(
                    night.payout_model_used.value
                )
                night_state = 2
    elif night_existing is not None and night.night_minutes == 0:
        if night_existing.night_minutes != 0:
            night_existing.night_minutes = 0
            night_existing.amount = 0.0
            night_state = 2

    return (ot_state, night_state, ot.ot_minutes)


@router.post("/recompute", response_model=RecomputeResult)
async def recompute(
    payload: RecomputeRequest,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_RULE_WRITE])),
) -> Any:
    """Re-evaluate OT + night-allowance for every attendance row in the
    period. Never touches entries that have a payroll_run_id (already
    rolled into a finalized payroll run)."""
    if payload.end_date < payload.start_date:
        raise HTTPException(400, "end_date cannot be before start_date")

    # Holidays for the whole window.
    holiday_set = await _load_holidays(db, payload.start_date, payload.end_date)

    # Pull all attendance rows in the window, scoped to user_ids if given.
    att_q = select(Attendance).where(
        and_(
            Attendance.work_date >= payload.start_date,
            Attendance.work_date <= payload.end_date,
        )
    )
    if payload.user_ids:
        att_q = att_q.where(Attendance.user_id.in_(payload.user_ids))
    att_rows = (await db.execute(att_q)).scalars().all()

    created_ot = updated_ot = skipped_ot = 0
    created_night = updated_night = skipped_night = 0

    for att in att_rows:
        ot_state, night_state, _ = await _resolve_one(
            db, user_id=att.user_id, work_date=att.work_date,
            attendance=att, holiday_set=holiday_set,
            requested_by_id=current_user.id,
        )
        if ot_state == 1: created_ot += 1
        elif ot_state == 2: updated_ot += 1
        elif ot_state == 0 and att.work_date in {
            r.work_date for r in att_rows
            if r.user_id == att.user_id
        }:
            # only count skip when an entry actually existed and was
            # locked by a payroll run
            existing = (await db.execute(
                select(OvertimeEntry).where(
                    and_(
                        OvertimeEntry.user_id == att.user_id,
                        OvertimeEntry.work_date == att.work_date,
                        OvertimeEntry.payroll_run_id.isnot(None),
                    )
                )
            )).scalar_one_or_none()
            if existing is not None:
                skipped_ot += 1
        if night_state == 1: created_night += 1
        elif night_state == 2: updated_night += 1

    # Independent skip count for night-entries.
    night_skipped_q = await db.execute(
        select(func.count(NightAllowanceEntry.id)).where(
            and_(
                NightAllowanceEntry.work_date >= payload.start_date,
                NightAllowanceEntry.work_date <= payload.end_date,
                NightAllowanceEntry.payroll_run_id.isnot(None),
            )
        )
    )
    skipped_night = int(night_skipped_q.scalar() or 0)

    await log_audit(
        db, current_user.id, "OT_RECOMPUTE", "overtime_entry", "*",
        {
            "start": payload.start_date.isoformat(),
            "end": payload.end_date.isoformat(),
            "user_ids": payload.user_ids,
            "ot_created": created_ot, "ot_updated": updated_ot,
            "ot_skipped_finalized": skipped_ot,
            "night_created": created_night, "night_updated": updated_night,
            "night_skipped_finalized": skipped_night,
        },
        request,
    )
    await db.commit()

    return RecomputeResult(
        period_start=payload.start_date, period_end=payload.end_date,
        ot_entries_created=created_ot, ot_entries_updated=updated_ot,
        ot_entries_skipped_finalized=skipped_ot,
        night_entries_created=created_night,
        night_entries_updated=updated_night,
        night_entries_skipped_finalized=skipped_night,
    )


# ----------------------------------------------------------------------
# monthly summary report
# ----------------------------------------------------------------------


@router.get("/summary", response_model=List[OvertimeMonthlySummary])
async def monthly_summary(
    db: deps.DBDep,
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2000, le=2200),
    department: Optional[str] = Query(None),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    if not _user_can_view_all(current_user):
        raise HTTPException(403, "Not authorized")

    days = _cal.monthrange(year, month)[1]
    start = date(year, month, 1)
    end = date(year, month, days)

    ot_q = select(
        OvertimeEntry.user_id,
        OvertimeEntry.status,
        func.coalesce(func.sum(OvertimeEntry.ot_minutes), 0).label("mins"),
        func.coalesce(func.sum(OvertimeEntry.ot_amount), 0.0).label("amt"),
    ).where(
        and_(OvertimeEntry.work_date >= start, OvertimeEntry.work_date <= end)
    ).group_by(OvertimeEntry.user_id, OvertimeEntry.status)
    ot_rows = (await db.execute(ot_q)).all()

    night_q = select(
        NightAllowanceEntry.user_id,
        func.coalesce(func.sum(NightAllowanceEntry.night_minutes), 0).label("mins"),
        func.coalesce(func.sum(NightAllowanceEntry.amount), 0.0).label("amt"),
    ).where(
        and_(
            NightAllowanceEntry.work_date >= start,
            NightAllowanceEntry.work_date <= end,
        )
    ).group_by(NightAllowanceEntry.user_id)
    night_rows = (await db.execute(night_q)).all()
    night_by_user = {r.user_id: (int(r.mins), float(r.amt)) for r in night_rows}

    # Aggregate per user.
    per_user: dict = {}
    for uid, status, mins, amt in ot_rows:
        d = per_user.setdefault(uid, {
            "total_min": 0, "total_amt": 0.0,
            "approved_min": 0, "approved_amt": 0.0,
            "pending_min": 0, "pending_amt": 0.0,
            "rejected_min": 0, "rejected_amt": 0.0,
        })
        d["total_min"] += int(mins)
        d["total_amt"] += float(amt)
        if status in (OvertimeStatus.APPROVED, OvertimeStatus.AUTO_APPROVED):
            d["approved_min"] += int(mins)
            d["approved_amt"] += float(amt)
        elif status == OvertimeStatus.PENDING:
            d["pending_min"] += int(mins)
            d["pending_amt"] += float(amt)
        elif status == OvertimeStatus.REJECTED:
            d["rejected_min"] += int(mins)
            d["rejected_amt"] += float(amt)

    # Include users that have only night entries.
    for uid in night_by_user:
        per_user.setdefault(uid, {
            "total_min": 0, "total_amt": 0.0,
            "approved_min": 0, "approved_amt": 0.0,
            "pending_min": 0, "pending_amt": 0.0,
            "rejected_min": 0, "rejected_amt": 0.0,
        })

    # Resolve user / department.
    user_ids = list(per_user.keys())
    users_map = {}
    dept_map = {}
    if user_ids:
        users_q = select(User).where(User.id.in_(user_ids))
        for u in (await db.execute(users_q)).scalars().all():
            users_map[u.id] = u
        emps_q = select(Employee.user_id, Employee.department).where(
            Employee.user_id.in_(user_ids)
        )
        for uid, dept in (await db.execute(emps_q)).all():
            dept_map[uid] = dept

    out: List[OvertimeMonthlySummary] = []
    for uid, d in per_user.items():
        if department and dept_map.get(uid) != department:
            continue
        nm, na = night_by_user.get(uid, (0, 0.0))
        out.append(OvertimeMonthlySummary(
            user_id=uid,
            user_full_name=getattr(users_map.get(uid), "full_name", None),
            department=dept_map.get(uid),
            month=month, year=year,
            total_ot_minutes=d["total_min"], total_ot_amount=round(d["total_amt"], 2),
            approved_minutes=d["approved_min"], approved_amount=round(d["approved_amt"], 2),
            pending_minutes=d["pending_min"], pending_amount=round(d["pending_amt"], 2),
            rejected_minutes=d["rejected_min"], rejected_amount=round(d["rejected_amt"], 2),
            night_minutes=nm, night_amount=round(na, 2),
        ))
    out.sort(key=lambda r: (r.department or "", r.user_full_name or ""))
    return out
