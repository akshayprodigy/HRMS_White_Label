"""Shared creation of a manual attendance row (HR manual entry and the
supervisor bulk-mark fallback share this so shift attribution, payroll lock
and duplicate rules cannot drift)."""
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app.core.datetime_utils import as_utc
from app.models.attendance import Attendance
from app.services.attendance_lock import assert_attendance_editable


class ManualAttendanceExists(HTTPException):
    """A record already exists for (user, work_date)."""

    def __init__(self, work_date: date):
        super().__init__(
            status_code=409,
            detail=("An attendance record already exists for "
                    f"{work_date.isoformat()} — edit it instead."))


async def create_manual_attendance_row(
    db, actor, user_id: int, work_date: date, punch_in: datetime,
    punch_out: Optional[datetime], reason: str, mode: str = "manual",
) -> Attendance:
    """Validate and add (flush) one attendance row. Callers audit/commit.

    Raises 409 (payroll lock / existing row) or 422 (punch-out order).
    `reason` is validated by the caller; it is not stored on the row."""
    # Serialize with concurrent writers for this user, then read FRESH
    # (locking reads see rows committed after the request snapshot,
    # including punches). No unique constraint: a day may hold several
    # punch sessions, so the lock + locking read is the guard.
    from app.api.v1.endpoints.roster_common import lock_user_rows
    await lock_user_rows(db, [user_id])
    await assert_attendance_editable(db, work_date, fresh=True)

    punch_in = as_utc(punch_in)
    punch_out = as_utc(punch_out)
    if punch_out is not None and punch_out <= punch_in:
        raise HTTPException(
            status_code=422, detail="Punch-out must be after punch-in.")

    try:
        existing = (await db.execute(
            select(Attendance).where(
                Attendance.user_id == user_id,
                Attendance.work_date == work_date,
            ).with_for_update().execution_options(populate_existing=True)
        )).scalars().first()
    except OperationalError as exc:
        # MariaDB 1020: a row for this user/day was committed after our
        # snapshot -> it exists now.
        if getattr(exc.orig, "args", (None,))[0] != 1020:
            raise
        raise ManualAttendanceExists(work_date) from exc
    if existing:
        raise ManualAttendanceExists(work_date)

    # Snapshot the employee's shift for correct late/early evaluation.
    from app.api.v1.endpoints.attendance import _effective_shift_on
    shift = await _effective_shift_on(db, user_id, work_date)

    att = Attendance(
        user_id=user_id,
        mode=mode,
        captured_at=punch_in,
        punch_out_time=punch_out,
        work_date=work_date,
        shift_template_id=shift.id if shift else None,
        attribution_flag=None if shift else "no_shift",
        edited_by_id=actor.id,
        edited_at=datetime.now(timezone.utc),
    )
    db.add(att)
    await db.flush()
    return att
