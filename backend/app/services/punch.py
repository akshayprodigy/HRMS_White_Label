"""Shared punch-in / punch-out internals (Roadmap v2 Phase 3, Task 2).

Both the live endpoints (POST /attendance/mark, /punch-out) and the offline
batch sync (POST /attendance/offline-sync) call these so shift attribution,
geofence, mock-location handling, flags, comp-off accrual and notifications
stay identical. The live endpoints own the commit; these only flush.
"""
from datetime import datetime, timezone, timedelta, date
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select, and_
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.datetime_utils import as_utc
from app.models.attendance import Attendance, AttendanceSelfie
from app.models.audit import AuditLog
from app.models.comp_off import CompOffAccrual
from app.models.geofence import EmployeeGeoConfig, EmployeeGeoFenceLink
from app.models.hr import HolidayCalendar
from app.models.notification import Notification
from app.models.shift import ShiftTemplate
from app.models.user import Role, User as UserModel
from app.schemas.geofence import GeoRejectionDetail
from app.services.comp_off_accrual import create_comp_off_accrual
from app.services.effective_shift import effective_shift_on
from app.services.geofence import EnforcementMode, GeoDecision, evaluate_punch
from app.services.shift_resolver import (
    DEFAULT_EARLY_IN_BUFFER,
    AttributionFlag,
    resolve_work_date,
)
from app.services.time_rules import get_time_rules

COMP_OFF_THRESHOLD_MINUTES = 390  # 6.5 hours

# --- geo helpers --------------------------------------------------------


async def _load_geo_config_with_fences(
    db, user_id: int
):
    """Return (geo_enabled, EnforcementMode, [active fences]) for the user.

    Returns (False, STRICT, []) when no config exists. Callers can then
    rely on the resolver's no-fence backward-compat path to short-circuit.
    """
    stmt = (
        select(EmployeeGeoConfig)
        .where(EmployeeGeoConfig.user_id == user_id)
        .options(
            selectinload(EmployeeGeoConfig.fences)
            .selectinload(EmployeeGeoFenceLink.fence),
        )
    )
    cfg = (await db.execute(stmt)).scalars().first()
    if cfg is None:
        return False, EnforcementMode.STRICT, []

    mode = (
        EnforcementMode.STRICT
        if cfg.enforcement_mode == EnforcementMode.STRICT.value
        else EnforcementMode.ALLOW_WITH_FLAG
    )
    fences = [
        link.fence
        for link in cfg.fences
        if link.fence is not None and link.fence.is_active
    ]
    return cfg.geo_enabled, mode, fences


def _build_rejection(decision: GeoDecision, fences) -> HTTPException:
    """Wrap a STRICT-rejection decision into a 422 with a structured body."""
    detail = GeoRejectionDetail(
        error=decision.reason_code or "OUTSIDE_GEOFENCE",
        message=decision.reason or "Punch rejected by geo policy.",
        nearest_fence_id=(
            decision.matched_fence.id
            if decision.matched_fence is not None else None
        ),
        nearest_fence_name=(
            decision.matched_fence.name
            if decision.matched_fence is not None else None
        ),
        distance_to_fence_meters=decision.distance_m,
        allowed_fence_ids=[f.id for f in fences],
    )
    return HTTPException(
        status_code=422,
        detail=detail.model_dump(),
    )


async def _notify_geo_flag(
    db,
    *,
    employee: "UserModel",
    attendance_id: int,
    decision: GeoDecision,
    when: str,  # 'punch_in' | 'punch_out'
) -> None:
    """In-app notification to manager + every HR user when a geo flag is set.

    Best-effort — failures are swallowed; never block a punch on
    notification delivery.
    """
    if decision.geo_flag is None:
        return
    title = f"Geo-flagged attendance ({decision.geo_flag.value})"
    distance_part = (
        f" {int(round(decision.distance_m))}m from "
        f"{decision.matched_fence.name}"
        if decision.matched_fence is not None
        and decision.distance_m is not None
        else ""
    )
    message = (
        f"{employee.full_name or employee.email} {when.replace('_', '-')}: "
        f"{decision.reason or decision.geo_flag.value}.{distance_part}"
    )

    recipient_ids: set[int] = set()
    if getattr(employee, "manager_id", None):
        recipient_ids.add(int(employee.manager_id))

    hr_role = (await db.execute(
        select(Role).where(Role.name == "HR")
    )).scalars().first()
    if hr_role is not None:
        # Find users who have the HR role assigned.
        hr_users = (await db.execute(
            select(UserModel)
            .join(UserModel.roles)
            .where(Role.id == hr_role.id, UserModel.is_active.is_(True))
        )).scalars().all()
        for u in hr_users:
            recipient_ids.add(int(u.id))

    # Don't ping the employee themselves about their own flag.
    recipient_ids.discard(int(employee.id))

    for uid in recipient_ids:
        db.add(Notification(
            user_id=uid,
            title=title,
            message=message,
            type="warning",
            resource_type="attendance",
            resource_id=str(attendance_id),
        ))


async def _notify_unscheduled_login(
    db, *, employee: "UserModel", attendance_id: int, work_date, flag: str,
) -> None:
    """W8: alert HR + the functional head when someone logs in with no
    scheduled shift (NO_SHIFT) or outside their shift window (OUTSIDE_WINDOW).
    Best-effort — never blocks the punch. Deep-links to Attendance review."""
    from app.models.employee import Employee
    from app.services.functional_head import resolve_head_for_department

    label = "no scheduled shift" if flag == "no_shift" else "outside shift window"
    title = "Unscheduled login"
    message = (
        f"{employee.full_name or employee.email} logged in on {work_date} "
        f"with {label}."
    )

    recipient_ids: set[int] = set()
    hr_role = (await db.execute(select(Role).where(Role.name == "HR"))).scalars().first()
    if hr_role is not None:
        hr_users = (await db.execute(
            select(UserModel).join(UserModel.roles)
            .where(Role.id == hr_role.id, UserModel.is_active.is_(True))
        )).scalars().all()
        recipient_ids.update(int(u.id) for u in hr_users)

    # Functional head of the employee's department.
    emp = (await db.execute(
        select(Employee).where(Employee.user_id == employee.id)
    )).scalars().first()
    if emp and emp.department:
        head = await resolve_head_for_department(db, emp.department)
        if head is not None:
            recipient_ids.add(int(head.id))

    recipient_ids.discard(int(employee.id))
    for uid in recipient_ids:
        db.add(Notification(
            user_id=uid, title=title, message=message, type="warning",
            resource_type="attendance", resource_id=str(attendance_id),
            event_type="attendance_unscheduled",
        ))


# --- shift lookup helpers -----------------------------------------------


async def _effective_shift_on(
    db, user_id: int, on_date: date
) -> Optional[ShiftTemplate]:
    """Return the effective shift template for `user_id` on `on_date`
    (published roster overrides assignment; roster week-off -> None)."""
    return (await effective_shift_on(db, user_id, on_date)).shift


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
    holiday_name: Optional[str] = holiday.name if holiday is not None else None
    if holiday is None:
        # Optional: working a rostered / scheduled week-off earns comp-off
        # too, behind a time rule (default off).
        rules = await get_time_rules(db)
        if rules.get("attendance.weekoff_comp_off_enabled", "0").strip() != "1":
            return None
        eff = await effective_shift_on(db, user.id, work_date)
        if not eff.is_week_off:
            return None
        holiday_name = "Week-off work"

    worked_minutes = int(
        (as_utc(punch_out) - as_utc(punch_in)).total_seconds() // 60)
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

    return await create_comp_off_accrual(
        db,
        user=user,
        work_date=work_date,
        holiday_name=holiday_name,
        attendance_id=attendance.id,
        worked_minutes=worked_minutes,
        reason=(
            f"Worked {worked_minutes // 60}h {worked_minutes % 60:02d}m on "
            f"{holiday_name} ({work_date.isoformat()})"
        ),
    )


class PunchRejected(HTTPException):
    """A punch refused by policy (STRICT geofence, missing selfie, ...).
    The live endpoints commit pending audit rows before re-raising; the
    offline sync catches it inside the item's savepoint and reports it."""


async def _fresh_one(db, stmt, fresh: bool):
    """First row of `stmt`. fresh=True uses a locking read so a row
    committed after our REPEATABLE READ snapshot is still seen (MariaDB
    1020 -> 409, the caller retries)."""
    if fresh:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    try:
        return (await db.execute(stmt)).scalars().first()
    except OperationalError as exc:
        from app.services.roster import is_lock_conflict
        if is_lock_conflict(exc):
            raise HTTPException(
                status_code=409, detail="Concurrent update; retry") from exc
        raise


async def _find_open_record_for_punch_out(
    db, user_id: int, now: datetime, fresh: bool = False
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
    rec = await _fresh_one(db, (
        select(Attendance)
        .where(
            Attendance.user_id == user_id,
            Attendance.work_date == work_date,
            Attendance.punch_out_time.is_(None),
        )
        .order_by(Attendance.captured_at.desc())
        .limit(1)
    ), fresh)
    if rec is not None:
        return rec
    since = now - timedelta(hours=24)
    return await _fresh_one(db, (
        select(Attendance)
        .where(
            Attendance.user_id == user_id,
            Attendance.captured_at >= since,
            Attendance.punch_out_time.is_(None),
        )
        .order_by(Attendance.captured_at.desc())
        .limit(1)
    ), fresh)


# --- selfie -------------------------------------------------------------


async def claim_selfie(db, user, selfie_id: Optional[int]) -> Optional[str]:
    """Validate that `selfie_id` was uploaded by `user` and is unused, mark
    it used and return its stored filename. None when no selfie supplied.
    Not-found and not-yours share one message (no id probing)."""
    if selfie_id is None:
        return None
    row = await _fresh_one(db, select(AttendanceSelfie).where(
        AttendanceSelfie.id == selfie_id,
        AttendanceSelfie.user_id == user.id,
    ), True)
    if row is None:
        raise PunchRejected(status_code=400, detail="Invalid selfie_id")
    if row.used_at is not None:
        raise PunchRejected(
            status_code=400, detail="This selfie is already attached to a punch")
    row.used_at = datetime.now(timezone.utc)
    return row.filename


def _selfie_required(rules) -> bool:
    return str(rules.get("attendance.selfie_required", "0")).strip() == "1"


def _review_flag(liveness_passed: Optional[bool], is_offline: bool,
                 current: Optional[str] = None) -> Optional[str]:
    if liveness_passed is False or current == "liveness_failed":
        return "liveness_failed"
    return "offline" if (is_offline or current == "offline") else None


# --- punch in -----------------------------------------------------------


async def record_punch_in(
    db, user, *, mode: str = "web", remarks: Optional[str] = None,
    captured_at: Optional[datetime] = None,
    lat: Optional[float] = None, lng: Optional[float] = None,
    accuracy: Optional[float] = None, is_mock: bool = False,
    selfie_id: Optional[int] = None, liveness_passed: Optional[bool] = None,
    liveness_score: Optional[float] = None, is_offline: bool = False,
    client_uuid: Optional[str] = None, ip: Optional[str] = None,
    fresh: bool = False,
) -> tuple[Attendance, bool]:
    """Punch in. Returns (row, created). Idempotent per logical work-date:
    an existing row for the resolved work_date is returned, created=False.
    Flushes only. Raises PunchRejected (policy) / HTTPException."""
    now = datetime.now(timezone.utc)
    captured = captured_at or now

    # Resolve attribution BEFORE checking duplicates, so an overnight shift
    # coming in just after midnight doesn't create a fresh next-day row.
    work_date, shift_id, is_cross_midnight, flag = await _attribute_punch(
        db, user.id, captured
    )
    existing = await _fresh_one(db, (
        select(Attendance)
        .where(Attendance.user_id == user.id,
               Attendance.work_date == work_date)
        .limit(1)
    ), fresh)
    if existing:
        return existing, False

    rules = await get_time_rules(db)
    if _selfie_required(rules) and selfie_id is None:
        raise PunchRejected(
            status_code=400, detail="A selfie is required to punch in.")

    geo_enabled, mode_enf, allowed_fences = await _load_geo_config_with_fences(
        db, user.id
    )
    decision = evaluate_punch(
        punch_lat=lat, punch_lng=lng, accuracy_m=accuracy,
        is_mock_location=is_mock, fences=allowed_fences,
        enforcement_mode=mode_enf, geo_enabled=geo_enabled,
    )
    if not decision.allowed:
        db.add(AuditLog(
            user_id=user.id,
            action="STRICT_GEO_REJECT_PUNCH_IN",
            resource_type="attendance",
            resource_id="-",
            ip_address=ip,
            details={
                "reason_code": decision.reason_code,
                "reason": decision.reason,
                "distance_to_fence_meters": decision.distance_m,
                "nearest_fence_id": (
                    decision.matched_fence.id
                    if decision.matched_fence else None
                ),
                "is_mock_location": is_mock,
                "punch_latitude": lat,
                "punch_longitude": lng,
            },
        ))
        exc = _build_rejection(decision, allowed_fences)
        raise PunchRejected(status_code=exc.status_code, detail=exc.detail)

    selfie_file = await claim_selfie(db, user, selfie_id)

    db_obj = Attendance(
        user_id=user.id,
        mode=mode,
        remarks=remarks,
        latitude=lat,
        longitude=lng,
        accuracy=accuracy,
        captured_at=captured,
        work_date=work_date,
        shift_template_id=shift_id,
        is_cross_midnight=is_cross_midnight,
        attribution_flag=flag,
        is_mock_location=is_mock,
        matched_fence_id=(
            decision.matched_fence.id if decision.matched_fence else None
        ),
        distance_to_fence_meters=decision.distance_m,
        geo_flag=decision.geo_flag.value if decision.geo_flag else None,
        selfie_url=selfie_file,
        liveness_passed=liveness_passed,
        liveness_score=liveness_score,
        is_offline=is_offline,
        client_uuid=client_uuid,
        device_captured_at=captured if is_offline else None,
        review_flag=_review_flag(liveness_passed, is_offline),
    )
    db.add(db_obj)
    await db.flush()

    details = {
        "mode": mode,
        "captured_at": captured.isoformat(),
        "work_date": work_date.isoformat(),
        "shift_template_id": shift_id,
        "is_cross_midnight": is_cross_midnight,
        "attribution_flag": flag,
        "geo_flag": db_obj.geo_flag,
        "matched_fence_id": db_obj.matched_fence_id,
        "distance_to_fence_meters": db_obj.distance_to_fence_meters,
        "is_mock_location": is_mock,
    }
    if is_offline:
        details["is_offline"] = True
        details["client_uuid"] = client_uuid
    if liveness_passed is False:
        details["liveness_passed"] = False
    db.add(AuditLog(
        user_id=user.id, action="MARK_ATTENDANCE", resource_type="attendance",
        resource_id=str(db_obj.id), ip_address=ip, details=details,
    ))

    if is_mock:
        db.add(AuditLog(
            user_id=user.id, action="MOCK_LOCATION_PUNCH_IN",
            resource_type="attendance", resource_id=str(db_obj.id),
            ip_address=ip, details={"latitude": lat, "longitude": lng},
        ))
    if db_obj.geo_flag is not None:
        try:
            await _notify_geo_flag(
                db, employee=user, attendance_id=db_obj.id,
                decision=decision, when="punch_in",
            )
        except Exception:  # pragma: no cover - defensive
            pass
    # W8: unscheduled-login alert (no shift / outside window). Best-effort.
    if flag in ("no_shift", "outside_window"):
        try:
            await _notify_unscheduled_login(
                db, employee=user, attendance_id=db_obj.id,
                work_date=work_date, flag=flag,
            )
        except Exception:  # pragma: no cover - defensive
            pass
    return db_obj, True


# --- punch out ----------------------------------------------------------


async def record_punch_out(
    db, user, *, at: Optional[datetime] = None,
    lat: Optional[float] = None, lng: Optional[float] = None,
    accuracy: Optional[float] = None, is_mock: bool = False,
    selfie_id: Optional[int] = None, liveness_passed: Optional[bool] = None,
    liveness_score: Optional[float] = None, is_offline: bool = False,
    client_uuid: Optional[str] = None, ip: Optional[str] = None,
    fresh: bool = False,
) -> Attendance:
    """Close the open punch as of `at` (default now). Flushes only.
    400 no open punch (offline: none that started before `at`), 400 missing
    selfie, 422 STRICT geo rejection."""
    now = datetime.now(timezone.utc)
    at = at or now
    attendance = await _find_open_record_for_punch_out(
        db, user.id, at, fresh=fresh
    )
    if attendance is None:
        raise PunchRejected(
            status_code=400,
            detail="You have not punched in for an open shift.",
        )
    if attendance.punch_out_time is not None:
        raise PunchRejected(
            status_code=400,
            detail="You have already punched out for the current shift.",
        )
    if is_offline and as_utc(attendance.captured_at) >= as_utc(at):
        raise PunchRejected(
            status_code=400,
            detail="No open punch started before this punch-out.",
        )

    rules = await get_time_rules(db)
    if _selfie_required(rules) and selfie_id is None:
        raise PunchRejected(
            status_code=400, detail="A selfie is required to punch out.")

    geo_enabled, mode, allowed_fences = await _load_geo_config_with_fences(
        db, user.id
    )
    out_decision = evaluate_punch(
        punch_lat=lat, punch_lng=lng, accuracy_m=accuracy,
        is_mock_location=is_mock, fences=allowed_fences,
        enforcement_mode=mode, geo_enabled=geo_enabled,
    )
    if not out_decision.allowed:
        db.add(AuditLog(
            user_id=user.id,
            action="STRICT_GEO_REJECT_PUNCH_OUT",
            resource_type="attendance",
            resource_id=str(attendance.id),
            ip_address=ip,
            details={
                "reason_code": out_decision.reason_code,
                "reason": out_decision.reason,
                "distance_to_fence_meters": out_decision.distance_m,
                "nearest_fence_id": (
                    out_decision.matched_fence.id
                    if out_decision.matched_fence else None
                ),
                "is_mock_location": is_mock,
            },
        ))
        exc = _build_rejection(out_decision, allowed_fences)
        raise PunchRejected(status_code=exc.status_code, detail=exc.detail)

    selfie_file = await claim_selfie(db, user, selfie_id)

    attendance.punch_out_time = at
    attendance.punch_out_latitude = lat
    attendance.punch_out_longitude = lng
    attendance.punch_out_accuracy = accuracy
    attendance.punch_out_is_mock = is_mock
    attendance.punch_out_matched_fence_id = (
        out_decision.matched_fence.id if out_decision.matched_fence else None
    )
    attendance.punch_out_distance_to_fence_meters = out_decision.distance_m
    attendance.punch_out_geo_flag = (
        out_decision.geo_flag.value if out_decision.geo_flag else None
    )
    attendance.punch_out_selfie_url = selfie_file
    attendance.punch_out_liveness_passed = liveness_passed
    attendance.punch_out_liveness_score = liveness_score
    if client_uuid is not None:
        attendance.punch_out_client_uuid = client_uuid
    if is_offline:
        attendance.is_offline = True
    attendance.review_flag = _review_flag(
        liveness_passed, is_offline, attendance.review_flag)

    # If the punch-out lands far outside the expected window for this
    # record's shift, surface that to HR via the flag (without
    # discarding any existing flag from punch-in).
    if attendance.shift_template_id is not None and attendance.attribution_flag is None:
        out_work_date, _out_shift_id, _out_cm, out_flag = await _attribute_punch(
            db, user.id, at
        )
        if (
            out_work_date != attendance.work_date
            or out_flag == AttributionFlag.OUTSIDE_WINDOW.value
        ):
            attendance.attribution_flag = AttributionFlag.OUTSIDE_WINDOW.value

    audit_details = {
        "punch_out_time": at.isoformat(),
        "work_date": attendance.work_date.isoformat()
        if attendance.work_date else None,
        "is_cross_midnight": attendance.is_cross_midnight,
        "attribution_flag": attendance.attribution_flag,
        "punch_out_geo_flag": attendance.punch_out_geo_flag,
        "punch_out_matched_fence_id": attendance.punch_out_matched_fence_id,
        "punch_out_distance_to_fence_meters":
            attendance.punch_out_distance_to_fence_meters,
        "punch_out_is_mock": is_mock,
    }
    if lat is not None or lng is not None:
        audit_details["geo"] = {
            "latitude": lat, "longitude": lng, "accuracy": accuracy,
        }
    if is_offline:
        audit_details["is_offline"] = True
        audit_details["client_uuid"] = client_uuid
    if liveness_passed is False:
        audit_details["liveness_passed"] = False
    db.add(AuditLog(
        user_id=user.id, action="PUNCH_OUT", resource_type="attendance",
        resource_id=str(attendance.id), ip_address=ip, details=audit_details,
    ))
    if is_mock:
        db.add(AuditLog(
            user_id=user.id, action="MOCK_LOCATION_PUNCH_OUT",
            resource_type="attendance", resource_id=str(attendance.id),
            ip_address=ip, details={"latitude": lat, "longitude": lng},
        ))
    if attendance.punch_out_geo_flag is not None:
        try:
            await _notify_geo_flag(
                db, employee=user, attendance_id=attendance.id,
                decision=out_decision, when="punch_out",
            )
        except Exception:  # pragma: no cover - defensive
            pass

    # Comp-off trigger — uses attendance.work_date (logical date). Wrapped in
    # a savepoint so a bug here can't poison the punch-out transaction.
    accrual = None
    accrual_error: Optional[str] = None
    try:
        async with db.begin_nested():
            accrual = await _maybe_create_comp_off_accrual(
                db, user=user, attendance=attendance,
                punch_in=attendance.captured_at, punch_out=at,
            )
    except Exception as exc:  # pragma: no cover - defensive
        accrual = None
        accrual_error = str(exc)

    if accrual_error is not None:
        db.add(AuditLog(
            user_id=user.id, action="COMP_OFF_ACCRUAL_FAILED",
            resource_type="attendance", resource_id=str(attendance.id),
            ip_address=ip, details={"error": accrual_error},
        ))
    if accrual is not None:
        db.add(AuditLog(
            user_id=user.id, action="COMP_OFF_ACCRUAL_CREATED",
            resource_type="comp_off_accrual", resource_id=str(accrual.id),
            ip_address=ip,
            details={
                "holiday_date": accrual.holiday_date.isoformat(),
                "holiday_name": accrual.holiday_name,
                "worked_minutes": accrual.worked_minutes,
                "days_credited": accrual.days_credited,
            },
        ))
    return attendance
