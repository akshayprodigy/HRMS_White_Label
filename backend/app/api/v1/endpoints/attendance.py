from datetime import datetime, timezone, timedelta, date
from typing import List, Literal, Optional
from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, and_, or_
from sqlalchemy.orm import selectinload
from app.services.org_time import local_today
from app.api import deps
from app.api.v1.endpoints.roster_common import lock_user_rows, retry_on_lock
from app.models.attendance import Attendance
from app.models.audit import AuditLog
from app.models.comp_off import CompOffAccrual
from app.models.approval import ApprovalItem, ApprovalStep, ApprovalStatus
from app.models.geofence import (
    EmployeeGeoConfig, EmployeeGeoFenceLink, GeoFenceLocation,
)
from app.models.notification import Notification
from app.models.shift import ShiftTemplate
from app.models.user import Role, User as UserModel
from app.services.comp_off_accrual import create_comp_off_accrual
from app.services.effective_shift import effective_shift_on
from app.services.org_time import tz_from_name
from app.services.geofence import (
    EnforcementMode,
    GeoDecision,
    evaluate_punch,
)
from app.services.shift_resolver import (
    DEFAULT_EARLY_IN_BUFFER,
    AttributionFlag,
    resolve_work_date,
    late_in_minutes,
    early_out_minutes,
)
from app.services.time_rules import (
    get_time_rules,
    build_default_shift,
    flags_enabled,
)
from app.schemas.attendance import (
    AttendanceMark,
    AttendanceRead,
    AttendanceToday,
    AttendanceHRRead
)
from app.schemas.geofence import GeoRejectionDetail  # noqa: F401


router = APIRouter()

class PunchOutBody(BaseModel):
    """Optional geolocation snapshot at punch-out. All fields are
    best-effort — a missing GPS reading must not block the user."""
    latitude: Optional[float] = Field(
        default=None, ge=-90.0, le=90.0, allow_inf_nan=False)
    longitude: Optional[float] = Field(
        default=None, ge=-180.0, le=180.0, allow_inf_nan=False)
    accuracy: Optional[float] = None
    is_mock_location: Optional[bool] = False
    # Selfie (from POST /attendance/selfie) + on-device liveness result.
    selfie_id: Optional[int] = None
    liveness_passed: Optional[bool] = None
    liveness_score: Optional[float] = None
    # Caller; "mobile" makes the mobile selfie rule apply (record_punch_out).
    mode: Optional[Literal["web", "mobile"]] = None



# Internals live in app.services.punch (shared with offline sync); names are
# re-exported for existing importers.
from app.services.punch import (  # noqa: E402,F401
    COMP_OFF_THRESHOLD_MINUTES,
    PunchRejected,
    _attribute_punch,
    _build_rejection,
    _effective_shift_on,
    _find_open_record_for_punch_out,
    _load_geo_config_with_fences,
    _maybe_create_comp_off_accrual,
    _notify_geo_flag,
    _notify_unscheduled_login,
    record_punch_in,
    record_punch_out,
)


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

    The punch time is always SERVER time; a client `captured_at` is stored
    only as `device_captured_at` (diagnostics).

    Optional `selfie_id` (from POST /attendance/selfie), `liveness_passed`
    and `liveness_score`. 400 when the `attendance.selfie_required` rule is
    on and no selfie is supplied; liveness_passed=false is accepted but
    flagged for HR review.
    """
    uid = current_user.id
    ip = request.client.host if request.client else None

    async def run():
        # Serialize with other punches (live or offline) for this user, then
        # read fresh so two requests can't both create a row for one work_date.
        user = await db.get(UserModel, uid, populate_existing=True)
        await lock_user_rows(db, [uid])
        try:
            # Punch time is SERVER time: a client captured_at is only kept
            # (device_captured_at) for diagnostics, never trusted.
            obj, _created = await record_punch_in(
                db, user,
                mode=attendance_in.mode,
                remarks=attendance_in.remarks,
                captured_at=None,
                device_captured_at=attendance_in.captured_at,
                lat=attendance_in.latitude,
                lng=attendance_in.longitude,
                accuracy=attendance_in.accuracy,
                is_mock=bool(getattr(attendance_in, "is_mock_location", False)),
                selfie_id=attendance_in.selfie_id,
                liveness_passed=attendance_in.liveness_passed,
                liveness_score=attendance_in.liveness_score,
                ip=ip, fresh=True,
            )
        except PunchRejected:
            # Persist any audit row (STRICT geo reject) before surfacing.
            await db.commit()
            raise
        return obj

    db_obj = await retry_on_lock(db, run, commit=True)
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
    400 if a selfie is required (time rule) and none supplied.
    422 if STRICT geo policy rejects the punch-out location.
    """
    uid = current_user.id
    ip = request.client.host if request.client else None

    async def run():
        user = await db.get(UserModel, uid, populate_existing=True)
        await lock_user_rows(db, [uid])
        try:
            return await record_punch_out(
                db, user,
                lat=body.latitude if body is not None else None,
                lng=body.longitude if body is not None else None,
                accuracy=body.accuracy if body is not None else None,
                is_mock=bool(body.is_mock_location) if body is not None else False,
                selfie_id=body.selfie_id if body is not None else None,
                liveness_passed=body.liveness_passed if body is not None else None,
                liveness_score=body.liveness_score if body is not None else None,
                ip=ip, fresh=True,
                mode=body.mode if body is not None else None,
            )
        except PunchRejected:
            await db.commit()
            raise

    attendance = await retry_on_lock(db, run, commit=True)
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
    today = await local_today(db)
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

    # Resolve full shift templates in a single round-trip (names for the
    # UI + start/end/grace for late/early evaluation).
    shift_ids = {r.shift_template_id for r in rows if r.shift_template_id}
    shift_by_id: dict[int, ShiftTemplate] = {}
    if shift_ids:
        tpls = list((await db.execute(
            select(ShiftTemplate).where(ShiftTemplate.id.in_(shift_ids))
        )).scalars().all())
        shift_by_id = {t.id: t for t in tpls}

    # Section Q: org time rules. Employees with no shift snapshot are
    # evaluated against the org-default virtual shift.
    rules = await get_time_rules(db)
    tz = tz_from_name(rules.get("org.timezone"))
    evaluate = flags_enabled(rules)
    default_shift = build_default_shift(rules)

    # Bulk-resolve editor names for the HR-edit badge.
    editor_ids = {r.edited_by_id for r in rows if r.edited_by_id}
    editor_name_by_id: dict[int, str] = {}
    if editor_ids:
        editors = list((await db.execute(
            select(UserModel).where(UserModel.id.in_(editor_ids))
        )).scalars().all())
        editor_name_by_id = {u.id: u.full_name for u in editors}

    def _aware(dt):
        if dt is None:
            return None
        return dt if dt.tzinfo is not None else dt.replace(
            tzinfo=timezone.utc
        )

    output = []
    for att in rows:
        read = AttendanceHRRead.model_validate(att)
        read.user_name = att.user.full_name
        read.user_email = att.user.email
        shift = None
        if att.shift_template_id is not None:
            shift = shift_by_id.get(att.shift_template_id)
            read.shift_template_name = shift.name if shift else None
        if att.edited_by_id is not None:
            read.edited_by_name = editor_name_by_id.get(att.edited_by_id)
        if evaluate and att.work_date is not None:
            effective = shift or default_shift
            late = late_in_minutes(
                _aware(att.captured_at), att.work_date, effective, tz
            )
            early = early_out_minutes(
                _aware(att.punch_out_time), att.work_date, effective, tz
            )
            # 0 = evaluated and on-time; None = not evaluated (flags
            # disabled or no work_date). The UI must not re-guess
            # lateness from wall-clock time — night shifts punch in
            # at 22:00 and are on time.
            read.late_minutes = late
            read.early_exit_minutes = early
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
        description=(
            "Filter to a single SHIFT-attribution flag: "
            "no_shift / outside_window / ambiguous"
        ),
    ),
    geo_flag: Optional[str] = Query(
        default=None,
        description=(
            "Filter to a single GEO flag: outside_geofence / "
            "mock_location / low_accuracy. Matched against either the "
            "punch-in geo_flag or the punch-out geo_flag."
        ),
    ),
    flag_kind: Optional[str] = Query(
        default=None,
        description=(
            "When set to 'attribution', only rows with attribution_flag != "
            "NULL are returned. When 'geo', only rows with a geo_flag on "
            "either punch are returned. When 'review', only offline-synced "
            "or liveness-failed rows. Default = any."
        ),
    ),
    review_flag: Optional[str] = Query(
        default=None,
        description="Filter to offline / liveness_failed rows",
    ),
    current_user: deps.CurrentUser = deps.check_permissions(["hr employee read"]),
):
    """HR review queue: attendance records the system wasn't confident
    about — either the shift resolver (attribution_flag) or the geo
    layer (geo_flag / punch_out_geo_flag).
    """
    today = await local_today(db)
    range_start = date_from or (today - timedelta(days=30))
    range_end = date_to or today

    # OR across both dimensions by default. flag_kind narrows.
    attribution_present = Attendance.attribution_flag.is_not(None)
    # approved_remote (punch relaxed by an approved WFH / on-duty request) is
    # informational, never a review item; only an explicit geo_flag filter
    # surfaces it.
    geo_present = or_(
        Attendance.geo_flag == geo_flag,
        Attendance.punch_out_geo_flag == geo_flag,
    ) if geo_flag is not None else or_(
        and_(Attendance.geo_flag.is_not(None),
             Attendance.geo_flag != "approved_remote"),
        and_(Attendance.punch_out_geo_flag.is_not(None),
             Attendance.punch_out_geo_flag != "approved_remote"),
    )
    # Phase 3: offline-synced punches and failed liveness checks.
    review_present = or_(
        Attendance.review_flag.is_not(None), Attendance.is_offline.is_(True))
    if flag_kind == "attribution":
        flag_condition = attribution_present
    elif flag_kind == "geo":
        flag_condition = geo_present
    elif flag_kind == "review":
        flag_condition = review_present
    else:
        flag_condition = or_(attribution_present, geo_present, review_present)

    query = (
        select(Attendance)
        .where(
            Attendance.work_date >= range_start,
            Attendance.work_date <= range_end,
            flag_condition,
        )
        .options(selectinload(Attendance.user))
        .order_by(Attendance.work_date.desc(), Attendance.captured_at.desc())
    )
    if flag is not None:
        query = query.where(Attendance.attribution_flag == flag)
    if review_flag == "offline":
        query = query.where(Attendance.is_offline.is_(True))
    elif review_flag is not None:
        query = query.where(Attendance.review_flag == review_flag)
    if geo_flag is not None:
        query = query.where(or_(
            Attendance.geo_flag == geo_flag,
            Attendance.punch_out_geo_flag == geo_flag,
        ))

    rows = list((await db.execute(query)).scalars().all())

    shift_ids = {r.shift_template_id for r in rows if r.shift_template_id}
    shift_name_by_id: dict[int, str] = {}
    if shift_ids:
        tpls = list((await db.execute(
            select(ShiftTemplate).where(ShiftTemplate.id.in_(shift_ids))
        )).scalars().all())
        shift_name_by_id = {t.id: t.name for t in tpls}

    fence_ids = (
        {r.matched_fence_id for r in rows if r.matched_fence_id}
        | {r.punch_out_matched_fence_id for r in rows if r.punch_out_matched_fence_id}
    )
    fence_name_by_id: dict[int, str] = {}
    if fence_ids:
        fences = list((await db.execute(
            select(GeoFenceLocation).where(GeoFenceLocation.id.in_(fence_ids))
        )).scalars().all())
        fence_name_by_id = {f.id: f.name for f in fences}

    output = []
    for att in rows:
        read = AttendanceHRRead.model_validate(att)
        read.user_name = att.user.full_name
        read.user_email = att.user.email
        if att.shift_template_id is not None:
            read.shift_template_name = shift_name_by_id.get(
                att.shift_template_id
            )
        if att.matched_fence_id is not None:
            read.matched_fence_name = fence_name_by_id.get(
                att.matched_fence_id
            )
        if att.punch_out_matched_fence_id is not None:
            read.punch_out_matched_fence_name = fence_name_by_id.get(
                att.punch_out_matched_fence_id
            )
        output.append(read)
    return output
