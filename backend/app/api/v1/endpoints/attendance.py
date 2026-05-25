from datetime import datetime, timezone, date
from typing import List, Optional
from fastapi import APIRouter, Request, Query
from pydantic import BaseModel
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from app.api import deps
from app.models.attendance import Attendance
from app.models.audit import AuditLog
from app.models.hr import HolidayCalendar
from app.models.comp_off import CompOffAccrual
from app.models.approval import ApprovalItem, ApprovalStep, ApprovalStatus
from app.models.user import Role
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


async def _maybe_create_comp_off_accrual(
    db,
    *,
    user,
    attendance: Attendance,
    punch_in: datetime,
    punch_out: datetime,
) -> Optional[CompOffAccrual]:
    """If the punched-in date matches a company holiday and the worked
    duration is >= the threshold, create a comp-off accrual + approval item
    (manager → HR). Returns the created accrual or None.

    Idempotent on (user_id, holiday_date) via the table's unique constraint.
    """
    work_date = punch_in.astimezone(timezone.utc).date()

    # 1. Holiday lookup — accept location 'All' and the user's location bucket.
    # Without per-user locations wired up, we accept 'All' or 'HQ' to match
    # the existing seed data; non-mandatory holidays still count.
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

    # 2. Idempotency — skip if there's already an accrual for this date
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

    # 3. Approval workflow: manager → HR (mirrors leave-request flow)
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
        # Refuse rather than create a step with role_id=NULL — the inbox
        # query treats NULL approver+role as "any leave-approver", which
        # would let arbitrary users approve comp-offs. Caller catches and
        # logs without blocking punch-out.
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


@router.post("/mark", response_model=AttendanceRead)
async def mark_attendance(
    *,
    db: deps.DBDep,
    current_user: deps.CurrentUser,
    attendance_in: AttendanceMark,
    request: Request
):
    """
    Mark attendance for today.
    """
    # Check if already marked today (UTC)
    now = datetime.now(timezone.utc)
    today_start = now.replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    
    query = select(Attendance).where(
        and_(
            Attendance.user_id == current_user.id,
            Attendance.captured_at >= today_start
        )
    ).limit(1)
    result = await db.execute(query)
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    current_user_id = current_user.id

    db_obj = Attendance(
        user_id=current_user_id,
        mode=attendance_in.mode,
        remarks=attendance_in.remarks,
        latitude=attendance_in.latitude,
        longitude=attendance_in.longitude,
        accuracy=attendance_in.accuracy,
        captured_at=attendance_in.captured_at
    )
    db.add(db_obj)
    await db.flush()  # Get ID without expiring

    # Audit log
    audit = AuditLog(
        user_id=current_user_id,
        action="MARK_ATTENDANCE",
        resource_type="attendance",
        resource_id=str(db_obj.id),
        ip_address=request.client.host if request.client else None,
        details={
            "mode": attendance_in.mode,
            "captured_at": (attendance_in.captured_at or now).isoformat()
        }
    )
    db.add(audit)
    await db.commit()
    await db.refresh(db_obj)  # Final refresh to be safe and return fresh data

    return db_obj


@router.post("/punch-out", response_model=AttendanceRead)
async def punch_out(
    *,
    db: deps.DBDep,
    current_user: deps.CurrentUser,
    request: Request,
    body: Optional[PunchOutBody] = None,
):
    """Mark today's punch-out time. Requires an existing punch-in for today.

    Idempotent only on the first call: a second punch-out the same day
    returns 400 so HR can detect duplicate clock-out attempts.

    Optional body fields capture the user's geolocation at punch-out so
    HR has matching forensics with the punch-in record. The coords are
    written to the audit log only — no schema change on Attendance.
    """
    from fastapi import HTTPException

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    query = (
        select(Attendance)
        .where(
            and_(
                Attendance.user_id == current_user.id,
                Attendance.captured_at >= today_start,
            )
        )
        .limit(1)
    )
    attendance = (await db.execute(query)).scalar_one_or_none()
    if attendance is None:
        raise HTTPException(
            status_code=400,
            detail="You have not punched in today.",
        )
    if attendance.punch_out_time is not None:
        raise HTTPException(
            status_code=400,
            detail="You have already punched out today.",
        )

    attendance.punch_out_time = now

    audit_details = {"punch_out_time": now.isoformat()}
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

    # Comp-off trigger: holiday + worked >= threshold. Wrapped in a
    # savepoint so a bug here (or a missing HR role) cannot poison the
    # punch-out transaction — punch-out is the primary action, comp-off
    # is a derived best-effort side-effect.
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
    current_user: deps.CurrentUser
):
    """
    Check if attendance is marked for today.
    """
    now = datetime.now(timezone.utc)
    today_start = now.replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    
    query = select(Attendance).where(
        and_(
            Attendance.user_id == current_user.id,
            Attendance.captured_at >= today_start
        )
    ).limit(1)
    result = await db.execute(query)
    attendance = result.scalars().first()
    
    attendance_data = None
    if attendance:
        attendance_data = AttendanceRead.model_validate(attendance)
    
    return AttendanceToday(
        is_marked=attendance is not None,
        attendance=attendance_data
    )


@router.get("/all", response_model=List[AttendanceHRRead])
async def get_all_attendance(
    *,
    db: deps.DBDep,
    date_from: Optional[date] = Query(default=None, description="Start date (YYYY-MM-DD), defaults to today"),
    date_to: Optional[date] = Query(default=None, description="End date inclusive (YYYY-MM-DD), defaults to today"),
    current_user: deps.CurrentUser = deps.check_permissions(["hr employee read"])
):
    """
    Get attendance logs for HR/Admin. Defaults to today; accepts optional date_from/date_to range.
    """
    now = datetime.now(timezone.utc)
    if date_from is None:
        range_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        range_start = datetime(date_from.year, date_from.month, date_from.day, 0, 0, 0, tzinfo=timezone.utc)

    if date_to is None:
        range_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    else:
        range_end = datetime(date_to.year, date_to.month, date_to.day, 23, 59, 59, 999999, tzinfo=timezone.utc)

    query = select(Attendance).where(
        Attendance.captured_at >= range_start,
        Attendance.captured_at <= range_end
    ).options(selectinload(Attendance.user))
    
    result = await db.execute(query)
    attendances = result.scalars().all()
    
    output = []
    for att in attendances:
        read = AttendanceHRRead.model_validate(att)
        read.user_name = att.user.full_name
        read.user_email = att.user.email
        output.append(read)
        
    return output
