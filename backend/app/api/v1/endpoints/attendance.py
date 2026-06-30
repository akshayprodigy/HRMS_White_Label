from datetime import datetime, timezone, timedelta, date
from typing import List, Optional
from fastapi import APIRouter, Request, Query
from pydantic import BaseModel
from sqlalchemy import select, and_, or_
from sqlalchemy.orm import selectinload
from app.api import deps
from app.models.attendance import Attendance
from app.models.audit import AuditLog
from app.models.hr import HolidayCalendar
from app.models.comp_off import CompOffAccrual
from app.models.approval import ApprovalItem, ApprovalStep, ApprovalStatus
from app.models.shift import EmployeeShiftAssignment, ShiftTemplate
from app.models.user import Role
from app.services.shift_resolver import (
    DEFAULT_EARLY_IN_BUFFER,
    AttributionFlag,
    resolve_work_date,
)
from app.schemas.attendance import (
    AttendanceMark,
    AttendanceRead,
    AttendanceToday,
    AttendanceHRRead
)


router = APIRouter()

COMP_OFF_THRESHOLD_MINUTES = 390  # 6.5 hours


class PunchOutBody(BaseModel):
    """Optional geolocation snapshot at punch-out. All fields are
    best-effort — a missing GPS reading must not block the user."""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    accuracy: Optional[float] = None


# --- shift lookup helpers -----------------------------------------------


async def _effective_shift_on(
    db, user_id: int, on_date: date
) -> Optional[ShiftTemplate]:
    """Return the active shift template for `user_id` on `on_date`,
    or None if no assignment covers that date."""
    stmt = (
        select(EmployeeShiftAssignment)
        .options(selectinload(EmployeeShiftAssignment.shift_template))
        .where(
            EmployeeShiftAssignment.employee_id == user_id,
            EmployeeShiftAssignment.effective_from <= on_date,
            or_(
                EmployeeShiftAssignment.effective_to.is_(None),
                EmployeeShiftAssignment.effective_to >= on_date,
            ),
        )
        .order_by(EmployeeShiftAssignment.effective_from.desc())
        .limit(1)
    )
    asg = (await db.execute(stmt)).scalars().first()
    return asg.shift_template if asg else None


async def _attribute_punch(
    db, user_id: int, punch_ts: datetime
):
    """Resolve work_date/shift/cross-midnight/flag for a punch.

    Returns a 4-tuple ready to assign to an Attendance row.
    """
    punch_date = punch_ts.astimezone(timezone.utc).date() if punch_ts.tzinfo else punch_ts.date()
    today_shift = await _effective_shift_on(db, user_id, punch_date)
    yesterday_shift = await _effective_shift_on(
        db, user_id, punch_date - timedelta(days=1)
    )
    result = resolve_work_date(
        punch_ts=punch_ts,
        today_shift=today_shift,
        yesterday_shift=yesterday_shift,
        early_in_buffer=DEFAULT_EARLY_IN_BUFFER,
    )
    shift_id = (
        getattr(result.shift, "id", None) if result.shift is not None else None
    )
    flag_value = result.flag.value if result.flag is not None else None
    return result.work_date, shift_id, result.is_cross_midnight, flag_value


# --- comp-off accrual ---------------------------------------------------


async def _maybe_create_comp_off_accrual(
    db,
    *,
    user,
    attendance: Attendance,
    punch_in: datetime,
    punch_out: datetime,
) -> Optional[CompOffAccrual]:
    """If the LOGICAL work-date of the attendance record matches a
    company holiday and the worked duration is >= the threshold, create
    a comp-off accrual + approval item (manager -> HR). Returns the
    created accrual or None.

    Idempotent on (user_id, holiday_date) via the table's unique
    constraint. Critically: the holiday check is against
    attendance.work_date — not the calendar date of either punch — so
    an overnight shift starting on a holiday correctly accrues comp-off
    even when the punch-out is the next morning.
    """
    # Prefer work_date (post shift-engine); fall back to calendar date
    # for any legacy code path that calls this before work_date is set.
    work_date = attendance.work_date or punch_in.astimezone(timezone.utc).date()

    holiday = (await db.execute(
        select(HolidayCalendar)
        .where(HolidayCalendar.date == work_date)
        .where(HolidayCalendar.location.in_(["All", "HQ"]))
        .limit(1)
    )).scalar_one_or_none()
    if holiday is None:
        return None

    worked_minutes = int((punch_out - punch_in).total_seconds() // 60)
    if worked_minutes < COMP_OFF_THRESHOLD_MINUTES:
        return None

    existing = (await db.execute(
        select(CompOffAccrual).where(
            and_(
                CompOffAccrual.user_id == user.id,
                CompOffAccrual.holiday_date == work_date,
            )
        ).limit(1)
    )).scalar_one_or_none()
    if existing is not None:
        return None

    accrual = CompOffAccrual(
        user_id=user.id,
        holiday_date=work_date,
        holiday_name=holiday.name,
        attendance_id=attendance.id,
        worked_minutes=worked_minutes,
        days_credited=1.0,
        status="pending",
        reason=(
            f"Worked {worked_minutes // 60}h {worked_minutes % 60:02d}m on "
            f"{holiday.name} ({work_date.isoformat()})"
        ),
    )
    db.add(accrual)
    await db.flush()

    approval_item = ApprovalItem(
        resource_type="comp_off_accrual",
        resource_id=str(accrual.id),
        status=ApprovalStatus.PENDING,
        current_step_number=1,
        requested_by_id=user.id,
    )
    db.add(approval_item)
    await db.flush()

    step_idx = 1
    if user.manager_id:
        db.add(ApprovalStep(
            approval_item_id=approval_item.id,
            step_number=step_idx,
            approver_id=user.manager_id,
            status=ApprovalStatus.PENDING,
        ))
        step_idx += 1

    hr_role = (await db.execute(
        select(Role).where(Role.name == "HR")
    )).scalar_one_or_none()
    if hr_role is None:
        raise RuntimeError(
            "HR role not configured — comp-off accrual skipped"
        )
    db.add(ApprovalStep(
        approval_item_id=approval_item.id,
        step_number=step_idx,
        role_id=hr_role.id,
        status=ApprovalStatus.PENDING,
    ))

    return accrual


# --- punch endpoints ----------------------------------------------------


def _utc_day_bounds(d: date) -> tuple[datetime, datetime]:
    start = datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=timezone.utc)
    end = start + timedelta(days=1) - timedelta(microseconds=1)
    return start, end


async def _find_open_record_for_punch_out(
    db, user_id: int, now: datetime
) -> Optional[Attendance]:
    """Find an open (no punch-out) attendance row for this user that the
    incoming punch-out call should close.

    Strategy:
      1. Look at the resolved work_date for `now` and find a punch-in
         attributed to that same work_date with no punch_out_time.
      2. Fall back to any open record in the last 24h.

    This handles overnight punch-outs: a punch-out at 06:10 on Jun 11
    for an overnight shift will resolve work_date = Jun 10 and find the
    punch-in row created the previous evening, instead of demanding the
    user "punched in today" (which would fail and create a stuck state).
    """
    work_date, _shift_id, _cm, _flag = await _attribute_punch(
        db, user_id, now
    )

    # Match by work_date first.
    stmt = (
        select(Attendance)
        .where(
            Attendance.user_id == user_id,
            Attendance.work_date == work_date,
            Attendance.punch_out_time.is_(None),
        )
        .order_by(Attendance.captured_at.desc())
        .limit(1)
    )
    rec = (await db.execute(stmt)).scalars().first()
    if rec is not None:
        return rec

    # Fallback: any open record from the last 24h. Useful for legacy
    # records (work_date may equal calendar date but the shift mid-rollout).
    since = now - timedelta(hours=24)
    stmt = (
        select(Attendance)
        .where(
            Attendance.user_id == user_id,
            Attendance.captured_at >= since,
            Attendance.punch_out_time.is_(None),
        )
        .order_by(Attendance.captured_at.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalars().first()


@router.post("/mark", response_model=AttendanceRead)
async def mark_attendance(
    *,
    db: deps.DBDep,
    current_user: deps.CurrentUser,
    attendance_in: AttendanceMark,
    request: Request,
):
    """Punch in for the current shift.

    Idempotent per LOGICAL work-date: if the user already has an
    attendance row for the resolved work_date, that row is returned
    rather than creating a duplicate. For day-shift workers this is
    equivalent to "one punch-in per calendar day" — no regression.
    """
    now = datetime.now(timezone.utc)
    captured = attendance_in.captured_at or now

    # Resolve attribution for this punch-in BEFORE checking duplicates,
    # so an overnight shift coming in just after midnight doesn't
    # accidentally create a fresh row for the next calendar day.
    work_date, shift_id, is_cross_midnight, flag = await _attribute_punch(
        db, current_user.id, captured
    )

    # Idempotency: one attendance row per (user, work_date). Returns the
    # existing row instead of erroring so the UI's "punch in" button is
    # safe to mash.
    existing = (
        await db.execute(
            select(Attendance)
            .where(
                Attendance.user_id == current_user.id,
                Attendance.work_date == work_date,
            )
            .limit(1)
        )
    ).scalars().first()
    if existing:
        return existing

    db_obj = Attendance(
        user_id=current_user.id,
        mode=attendance_in.mode,
        remarks=attendance_in.remarks,
        latitude=attendance_in.latitude,
        longitude=attendance_in.longitude,
        accuracy=attendance_in.accuracy,
        captured_at=captured,
        work_date=work_date,
        shift_template_id=shift_id,
        is_cross_midnight=is_cross_midnight,
        attribution_flag=flag,
    )
    db.add(db_obj)
    await db.flush()

    db.add(AuditLog(
        user_id=current_user.id,
        action="MARK_ATTENDANCE",
        resource_type="attendance",
        resource_id=str(db_obj.id),
        ip_address=request.client.host if request.client else None,
        details={
            "mode": attendance_in.mode,
            "captured_at": captured.isoformat(),
            "work_date": work_date.isoformat(),
            "shift_template_id": shift_id,
            "is_cross_midnight": is_cross_midnight,
            "attribution_flag": flag,
        },
    ))
    await db.commit()
    await db.refresh(db_obj)
    return db_obj


@router.post("/punch-out", response_model=AttendanceRead)
async def punch_out(
    *,
    db: deps.DBDep,
    current_user: deps.CurrentUser,
    request: Request,
    body: Optional[PunchOutBody] = None,
):
    """Close the currently-open punch.

    Resolves the work-date of the punch-out timestamp and locates the
    open attendance row attributed to that same work-date. This is what
    lets a 06:10 punch-out next morning close the night-shift row from
    the previous evening WITHOUT creating a phantom record for the
    calendar date of the punch-out.

    400 if no open record can be found (i.e. the user hasn't punched in
    for the relevant shift).
    400 if the matched record is already punched out (duplicate clock-out).
    """
    from fastapi import HTTPException

    now = datetime.now(timezone.utc)
    attendance = await _find_open_record_for_punch_out(
        db, current_user.id, now
    )
    if attendance is None:
        raise HTTPException(
            status_code=400,
            detail="You have not punched in for an open shift.",
        )
    if attendance.punch_out_time is not None:
        # This is unlikely because _find_open_record_for_punch_out
        # filters punch_out_time IS NULL, but kept for defence-in-depth.
        raise HTTPException(
            status_code=400,
            detail="You have already punched out for the current shift.",
        )

    attendance.punch_out_time = now

    # If the punch-out lands far outside the expected window for this
    # record's shift, surface that to HR via the flag (without
    # discarding any existing flag from punch-in).
    if attendance.shift_template_id is not None and attendance.attribution_flag is None:
        out_work_date, _out_shift_id, _out_cm, out_flag = await _attribute_punch(
            db, current_user.id, now
        )
        if (
            out_work_date != attendance.work_date
            or out_flag == AttributionFlag.OUTSIDE_WINDOW.value
        ):
            attendance.attribution_flag = AttributionFlag.OUTSIDE_WINDOW.value

    audit_details = {
        "punch_out_time": now.isoformat(),
        "work_date": attendance.work_date.isoformat()
        if attendance.work_date else None,
        "is_cross_midnight": attendance.is_cross_midnight,
        "attribution_flag": attendance.attribution_flag,
    }
    if body is not None and (
        body.latitude is not None or body.longitude is not None
    ):
        audit_details["geo"] = {
            "latitude": body.latitude,
            "longitude": body.longitude,
            "accuracy": body.accuracy,
        }
    db.add(AuditLog(
        user_id=current_user.id,
        action="PUNCH_OUT",
        resource_type="attendance",
        resource_id=str(attendance.id),
        ip_address=request.client.host if request.client else None,
        details=audit_details,
    ))

    # Comp-off trigger — uses attendance.work_date (logical date), so an
    # overnight shift that starts on a holiday will accrue correctly even
    # though punch-out happens the next calendar day. Wrapped in a
    # savepoint so a bug here can't poison the punch-out transaction.
    accrual = None
    accrual_error: Optional[str] = None
    try:
        async with db.begin_nested():
            accrual = await _maybe_create_comp_off_accrual(
                db,
                user=current_user,
                attendance=attendance,
                punch_in=attendance.captured_at,
                punch_out=now,
            )
    except Exception as exc:  # pragma: no cover - defensive
        accrual = None
        accrual_error = str(exc)

    if accrual_error is not None:
        db.add(AuditLog(
            user_id=current_user.id,
            action="COMP_OFF_ACCRUAL_FAILED",
            resource_type="attendance",
            resource_id=str(attendance.id),
            ip_address=request.client.host if request.client else None,
            details={"error": accrual_error},
        ))

    if accrual is not None:
        db.add(AuditLog(
            user_id=current_user.id,
            action="COMP_OFF_ACCRUAL_CREATED",
            resource_type="comp_off_accrual",
            resource_id=str(accrual.id),
            ip_address=request.client.host if request.client else None,
            details={
                "holiday_date": accrual.holiday_date.isoformat(),
                "holiday_name": accrual.holiday_name,
                "worked_minutes": accrual.worked_minutes,
                "days_credited": accrual.days_credited,
            },
        ))

    await db.commit()
    await db.refresh(attendance)
    return attendance


@router.get("/today", response_model=AttendanceToday)
async def get_today_attendance(
    *,
    db: deps.DBDep,
    current_user: deps.CurrentUser,
):
    """Check whether the user has an attendance row for the LOGICAL work-date
    of the current moment.

    For day-shift users this is equivalent to "today's calendar date" —
    no regression. For night-shift users punching in at 23:00 and again
    looking at the dashboard at 02:00, this still returns the same row.
    """
    now = datetime.now(timezone.utc)
    work_date, _shift_id, _cm, _flag = await _attribute_punch(
        db, current_user.id, now
    )

    query = (
        select(Attendance)
        .where(
            Attendance.user_id == current_user.id,
            Attendance.work_date == work_date,
        )
        .limit(1)
    )
    attendance = (await db.execute(query)).scalars().first()

    return AttendanceToday(
        is_marked=attendance is not None,
        attendance=(
            AttendanceRead.model_validate(attendance) if attendance else None
        ),
    )


@router.get("/all", response_model=List[AttendanceHRRead])
async def get_all_attendance(
    *,
    db: deps.DBDep,
    date_from: Optional[date] = Query(
        default=None, description="Start work-date (YYYY-MM-DD), default today"
    ),
    date_to: Optional[date] = Query(
        default=None, description="End work-date inclusive (YYYY-MM-DD), default today"
    ),
    current_user: deps.CurrentUser = deps.check_permissions(["hr employee read"]),
):
    """HR attendance logs filtered by LOGICAL work-date.

    Returns the shift snapshot name + cross-midnight + attribution_flag
    so the UI can render the right indicators.
    """
    today = datetime.now(timezone.utc).date()
    range_start = date_from or today
    range_end = date_to or today

    query = (
        select(Attendance)
        .where(
            Attendance.work_date >= range_start,
            Attendance.work_date <= range_end,
        )
        .options(
            selectinload(Attendance.user),
            # shift_template_id is a plain FK, we hand-load the name below
            # to keep the query fast (no nested join cost when zero
            # records have a shift assigned).
        )
    )

    rows = list((await db.execute(query)).scalars().all())

    # Resolve shift template names in a single round-trip.
    shift_ids = {r.shift_template_id for r in rows if r.shift_template_id}
    shift_name_by_id: dict[int, str] = {}
    if shift_ids:
        tpls = list((await db.execute(
            select(ShiftTemplate).where(ShiftTemplate.id.in_(shift_ids))
        )).scalars().all())
        shift_name_by_id = {t.id: t.name for t in tpls}

    output = []
    for att in rows:
        read = AttendanceHRRead.model_validate(att)
        read.user_name = att.user.full_name
        read.user_email = att.user.email
        if att.shift_template_id is not None:
            read.shift_template_name = shift_name_by_id.get(
                att.shift_template_id
            )
        output.append(read)
    return output


@router.get("/flagged", response_model=List[AttendanceHRRead])
async def get_flagged_attendance(
    *,
    db: deps.DBDep,
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    flag: Optional[str] = Query(
        default=None,
        description="Filter to a single flag: no_shift / outside_window / ambiguous",
    ),
    current_user: deps.CurrentUser = deps.check_permissions(["hr employee read"]),
):
    """HR review queue: attendance records the resolver wasn't confident
    about. Use this to find rows that need a correction request.
    """
    today = datetime.now(timezone.utc).date()
    range_start = date_from or (today - timedelta(days=30))
    range_end = date_to or today

    query = (
        select(Attendance)
        .where(
            Attendance.work_date >= range_start,
            Attendance.work_date <= range_end,
            Attendance.attribution_flag.is_not(None),
        )
        .options(selectinload(Attendance.user))
        .order_by(Attendance.work_date.desc(), Attendance.captured_at.desc())
    )
    if flag is not None:
        query = query.where(Attendance.attribution_flag == flag)

    rows = list((await db.execute(query)).scalars().all())

    shift_ids = {r.shift_template_id for r in rows if r.shift_template_id}
    shift_name_by_id: dict[int, str] = {}
    if shift_ids:
        tpls = list((await db.execute(
            select(ShiftTemplate).where(ShiftTemplate.id.in_(shift_ids))
        )).scalars().all())
        shift_name_by_id = {t.id: t.name for t in tpls}

    output = []
    for att in rows:
        read = AttendanceHRRead.model_validate(att)
        read.user_name = att.user.full_name
        read.user_email = att.user.email
        if att.shift_template_id is not None:
            read.shift_template_name = shift_name_by_id.get(
                att.shift_template_id
            )
        output.append(read)
    return output
