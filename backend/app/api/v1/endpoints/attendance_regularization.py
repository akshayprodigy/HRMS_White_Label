"""Attendance regularization: employees request a punch fix, a manager or
HR (ATTENDANCE_EDIT) approves it, and the Attendance row is corrected."""
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import select

from app.api import deps
from app.models.attendance import Attendance
from app.models.attendance_regularization import (
    AttendanceRegularization, RegularizationStatus,
)
from app.models.employee import Employee
from app.models.notification import Notification
from app.models.user import User
from app.schemas.attendance_regularization import (
    RegularizationCreate, RegularizationDecision, RegularizationRead,
)
from app.services.attendance_lock import assert_attendance_editable
from app.services.effective_shift import effective_shift_on
from app.services.self_approval import guard_self_approval

logger = logging.getLogger(__name__)
router = APIRouter()

ATTENDANCE_EDIT = "attendance edit"
_ALL_STATUSES = {
    v for k, v in vars(RegularizationStatus).items() if not k.startswith("_")
}


async def _get_locked(db, reg_id: int) -> AttendanceRegularization:
    """Load the request under a row lock so concurrent decide/cancel calls
    serialize and the status check below cannot be raced."""
    reg = (await db.execute(
        select(AttendanceRegularization)
        .where(AttendanceRegularization.id == reg_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )).scalars().first()
    if not reg:
        raise HTTPException(404, "Regularization request not found")
    return reg


def _as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Naive -> assume UTC; aware -> convert to UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


async def _notify(
    db, user_id: Optional[int], title: str, message: str, reg_id: int,
) -> None:
    """Best-effort in-app notification; never breaks the request."""
    if not user_id:
        return
    try:
        async with db.begin_nested():
            db.add(Notification(
                user_id=user_id, title=title, message=message,
                type="info", resource_type="attendance_regularization",
                resource_id=str(reg_id),
            ))
    except Exception:  # pragma: no cover
        logger.warning("regularization notification failed", exc_info=True)


def _row_to_read(reg, name, code) -> RegularizationRead:
    out = RegularizationRead.model_validate(reg)
    for f in ("requested_punch_in", "requested_punch_out", "decided_at", "created_at"):
        setattr(out, f, _as_utc(getattr(out, f)))
    out.requester_name = name
    out.requester_employee_code = code
    return out


async def _load_read(db, reg_id: int) -> RegularizationRead:
    row = (await db.execute(
        select(AttendanceRegularization, User.full_name, Employee.employee_id)
        .join(User, User.id == AttendanceRegularization.user_id)
        .outerjoin(Employee, Employee.user_id == User.id)
        .where(AttendanceRegularization.id == reg_id)
    )).first()
    return _row_to_read(*row)


@router.post("", response_model=RegularizationRead)
@router.post("/", response_model=RegularizationRead, include_in_schema=False)
async def create_regularization(
    *,
    db: deps.DBDep,
    obj_in: RegularizationCreate,
    current_user: deps.CurrentUser,
) -> Any:
    # Dates are UTC end-to-end (see shift_resolver / attendance work_date).
    # Allow work_date up to UTC today + 1 so users just past midnight local
    # time can still pick their local "today".
    now = datetime.now(timezone.utc)
    if obj_in.work_date > now.date() + timedelta(days=1):
        raise HTTPException(422, "work_date cannot be in the future.")
    punch_in = _as_utc(obj_in.requested_punch_in)
    punch_out = _as_utc(obj_in.requested_punch_out)
    if punch_in > now or (punch_out is not None and punch_out > now):
        raise HTTPException(422, "Punch times cannot be in the future.")
    if punch_out is not None:
        if punch_out <= punch_in:
            raise HTTPException(422, "Punch-out must be after punch-in.")
        if punch_out - punch_in > timedelta(hours=24):
            raise HTTPException(422, "Punch-in to punch-out cannot exceed 24 hours.")
    # work_date is the logical (shift-start) date; an overnight shift
    # starting on D can be punched in on D+1 (UTC), so accept both.
    if punch_in.date() not in (
        obj_in.work_date, obj_in.work_date + timedelta(days=1)
    ):
        raise HTTPException(
            422, "Punch-in must fall on work_date (or the next day for "
                 "overnight shifts).",
        )

    await assert_attendance_editable(db, obj_in.work_date)

    dup = (await db.execute(
        select(AttendanceRegularization.id).where(
            AttendanceRegularization.user_id == current_user.id,
            AttendanceRegularization.work_date == obj_in.work_date,
            AttendanceRegularization.status == RegularizationStatus.PENDING,
        )
    )).first()
    if dup:
        raise HTTPException(
            409, "A pending regularization already exists for this date."
        )

    att_id = (await db.execute(
        select(Attendance.id).where(
            Attendance.user_id == current_user.id,
            Attendance.work_date == obj_in.work_date,
        )
    )).scalars().first()

    reg = AttendanceRegularization(
        user_id=current_user.id,
        work_date=obj_in.work_date,
        attendance_id=att_id,
        requested_punch_in=punch_in,
        requested_punch_out=punch_out,
        reason=obj_in.reason,
        status=RegularizationStatus.PENDING,
    )
    db.add(reg)
    await db.flush()
    await _notify(
        db, current_user.manager_id, "Attendance regularization request",
        f"{current_user.full_name or current_user.email} requested a punch "
        f"fix for {obj_in.work_date.isoformat()}.",
        reg.id,
    )
    await db.commit()
    return await _load_read(db, reg.id)


@router.get("/my", response_model=List[RegularizationRead])
async def my_regularizations(
    db: deps.DBDep, current_user: deps.CurrentUser,
) -> Any:
    rows = (await db.execute(
        select(AttendanceRegularization, User.full_name, Employee.employee_id)
        .join(User, User.id == AttendanceRegularization.user_id)
        .outerjoin(Employee, Employee.user_id == User.id)
        .where(AttendanceRegularization.user_id == current_user.id)
        .order_by(AttendanceRegularization.created_at.desc(),
                  AttendanceRegularization.id.desc())
    )).all()
    return [_row_to_read(*r) for r in rows]


@router.get("", response_model=List[RegularizationRead])
@router.get("/", response_model=List[RegularizationRead], include_in_schema=False)
async def approver_queue(
    db: deps.DBDep,
    current_user: deps.CurrentUser,
    status: str = Query("pending"),
) -> Any:
    if status != "all" and status not in _ALL_STATUSES:
        raise HTTPException(422, "Invalid status filter.")
    q = (
        select(AttendanceRegularization, User.full_name, Employee.employee_id)
        .join(User, User.id == AttendanceRegularization.user_id)
        .outerjoin(Employee, Employee.user_id == User.id)
    )
    if status != "all":
        q = q.where(AttendanceRegularization.status == status)
    if not deps.user_has_permission(current_user, ATTENDANCE_EDIT):
        q = q.where(User.manager_id == current_user.id)
    q = q.order_by(AttendanceRegularization.created_at.desc(),
                   AttendanceRegularization.id.desc())
    rows = (await db.execute(q)).all()
    return [_row_to_read(*r) for r in rows]


@router.post("/{reg_id}/decide", response_model=RegularizationRead)
async def decide_regularization(
    *,
    db: deps.DBDep,
    reg_id: int,
    body: RegularizationDecision,
    request: Request,
    current_user: deps.CurrentUser,
) -> Any:
    # Local import: hr.py is heavy.
    # TODO(phase0-followup): move log_audit to services/audit.py (3 divergent
    # copies: hr.py, payroll.py, projects.py)
    from app.api.v1.endpoints.hr import log_audit

    reg = await _get_locked(db, reg_id)

    guard_self_approval(current_user.id, reg.user_id)

    requester = await db.get(User, reg.user_id)
    is_manager = bool(requester and requester.manager_id == current_user.id)
    if not (is_manager or deps.user_has_permission(current_user, ATTENDANCE_EDIT)):
        raise HTTPException(403, "Not authorized to decide this request.")

    if reg.status != RegularizationStatus.PENDING:
        raise HTTPException(409, f"Request is already {reg.status}.")

    note = (body.note or "").strip() or None
    now = datetime.now(timezone.utc)

    if not body.approve:
        if not note:
            raise HTTPException(422, "A note is required to reject a request.")
        reg.status = RegularizationStatus.REJECTED
        details = {
            "user_id": reg.user_id,
            "work_date": reg.work_date.isoformat(),
            "requested_punch_in": _as_utc(reg.requested_punch_in).isoformat(),
            "requested_punch_out": (
                _as_utc(reg.requested_punch_out).isoformat()
                if reg.requested_punch_out else None
            ),
            "note": note,
        }
        action = "REJECT_ATTENDANCE_REGULARIZATION"
    else:
        await assert_attendance_editable(db, reg.work_date)
        new_in = _as_utc(reg.requested_punch_in)
        new_out = _as_utc(reg.requested_punch_out)
        att = (await db.execute(
            select(Attendance).where(
                Attendance.user_id == reg.user_id,
                Attendance.work_date == reg.work_date,
            ).order_by(Attendance.captured_at)
        )).scalars().first()
        if att:
            old = {
                "punch_in_time": _as_utc(att.captured_at).isoformat(),
                "punch_out_time": (
                    _as_utc(att.punch_out_time).isoformat()
                    if att.punch_out_time else None
                ),
            }
            if new_out is None and att.punch_out_time is not None:
                new_out = _as_utc(att.punch_out_time)
            if new_out is not None and new_out <= new_in:
                raise HTTPException(
                    422, "Resulting punch-out would not be after punch-in."
                )
            att.captured_at = new_in
            att.punch_out_time = new_out
            att.edited_by_id = current_user.id
            att.edited_at = now
        else:
            old = {"punch_in_time": None, "punch_out_time": None}
            shift = (await effective_shift_on(db, reg.user_id, reg.work_date)).shift
            att = Attendance(
                user_id=reg.user_id,
                mode="regularized",
                captured_at=new_in,
                punch_out_time=new_out,
                work_date=reg.work_date,
                shift_template_id=shift.id if shift else None,
                attribution_flag=None if shift else "no_shift",
                edited_by_id=current_user.id,
                edited_at=now,
            )
            db.add(att)
        await db.flush()
        reg.attendance_id = att.id
        reg.status = RegularizationStatus.APPROVED
        details = {
            "user_id": reg.user_id,
            "work_date": reg.work_date.isoformat(),
            "old": old,
            "new": {
                "punch_in_time": new_in.isoformat(),
                "punch_out_time": new_out.isoformat() if new_out else None,
            },
            "note": note,
        }
        action = "APPROVE_ATTENDANCE_REGULARIZATION"

    reg.decided_by_id = current_user.id
    reg.decided_at = now
    reg.decision_note = note
    db.add(reg)
    await _notify(
        db, reg.user_id, f"Attendance regularization {reg.status}",
        f"Your request for {reg.work_date.isoformat()} was {reg.status}."
        + (f" Note: {note}" if note else ""),
        reg.id,
    )
    # log_audit commits: this is the single commit on decide, persisting everything above in one transaction.
    await log_audit(
        db, current_user.id, action, "attendance_regularization",
        str(reg.id), details, request,
    )
    return await _load_read(db, reg.id)


@router.post("/{reg_id}/cancel", response_model=RegularizationRead)
async def cancel_regularization(
    *, db: deps.DBDep, reg_id: int, current_user: deps.CurrentUser,
) -> Any:
    reg = await _get_locked(db, reg_id)
    if reg.user_id != current_user.id:
        raise HTTPException(403, "Only the requester can cancel this request.")
    if reg.status != RegularizationStatus.PENDING:
        raise HTTPException(409, f"Request is already {reg.status}.")
    reg.status = RegularizationStatus.CANCELLED
    await db.commit()
    return await _load_read(db, reg.id)
