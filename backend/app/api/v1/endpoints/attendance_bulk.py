"""Supervisor bulk mark-present (Roadmap v2 Phase 2, Task 9): fallback when
the punch system is down. Mounted WITHOUT verify_attendance (see api.py)."""
import json
import uuid
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app.api import deps
from app.api.v1.endpoints.hr import (
    ATTENDANCE_EDIT, _require_reason, json_serial,
)
from app.api.v1.endpoints.roster_common import (
    commit_or_409, guard_conflicts, lock_user_rows,
)
from app.core.datetime_utils import as_utc
from app.models.audit import AuditLog
from app.models.employee import Employee, EmployeeStatus
from app.models.user import User
from app.schemas.attendance import AttendanceBulkMark, AttendanceBulkResponse
from app.services import coverage_gaps as gap_svc
from app.services import roster as roster_svc
from app.services.attendance_lock import assert_attendance_editable
from app.services.org_time import local_to_utc, local_today_for, org_tz
from app.services.manual_attendance import (
    ManualAttendanceExists, create_manual_attendance_row,
)

router = APIRouter()

MODE = "manual_bulk"
SUPERVISOR_WINDOW_DAYS = 2  # [today-2, today], org-local dates


def parse_time_input(
    raw: str, work_date: date, tz: tzinfo = timezone.utc,
) -> datetime:
    """'HH:MM' -> that org-local wall-clock time on work_date, as UTC;
    otherwise an ISO datetime (naive treated as UTC)."""
    s = (raw or "").strip()
    try:
        if len(s) <= 5 and ":" in s:
            h, m = s.split(":")
            return local_to_utc(work_date, time(int(h), int(m)), tz)
        return as_utc(datetime.fromisoformat(s.replace("Z", "+00:00")))
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid time {raw!r}: use HH:MM or an ISO datetime.")


class _BatchConflict(Exception):
    """A lock conflict rolled back the whole transaction: abort the batch."""

    def __init__(self, exc: HTTPException):
        self.exc = exc


@router.post("/bulk-mark", response_model=AttendanceBulkResponse)
@guard_conflicts
async def bulk_mark_present(
    *,
    db: deps.DBDep,
    body: AttendanceBulkMark,
    request: Request,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    reason = _require_reason(body.reason)
    is_hr = deps.user_has_permission(current_user, ATTENDANCE_EDIT)
    tz = await org_tz(db)
    today = local_today_for(tz)
    if not is_hr:
        if not (await roster_svc.scoped_employees(db, current_user)
                or roster_svc.is_roster_admin(current_user)):
            raise HTTPException(
                status_code=403, detail="Not enough permissions: attendance edit")
        if not (today - timedelta(days=SUPERVISOR_WINDOW_DAYS)
                <= body.work_date <= today):
            raise HTTPException(
                status_code=403,
                detail="Supervisors can mark attendance only for today and "
                       f"the previous {SUPERVISOR_WINDOW_DAYS} days.")
    if body.work_date > today:
        raise HTTPException(
            status_code=422, detail="Cannot mark attendance for a future date.")

    punch_in = parse_time_input(body.punch_in_time, body.work_date, tz)
    punch_out = None
    if body.punch_out_time:
        punch_out = parse_time_input(body.punch_out_time, body.work_date, tz)
        if punch_out <= punch_in and len(body.punch_out_time.strip()) <= 5:
            if punch_out == punch_in:
                raise HTTPException(
                    status_code=422,
                    detail="Punch-out must be after punch-in.")
            punch_out += timedelta(days=1)  # HH:MM past midnight (night shift)
    if punch_out is not None and punch_out <= punch_in:
        raise HTTPException(
            status_code=422, detail="Punch-out must be after punch-in.")
    now = datetime.now(timezone.utc)
    if punch_in > now + timedelta(minutes=5):
        raise HTTPException(
            status_code=422, detail="Punch-in cannot be in the future.")
    if punch_out is not None and punch_out - punch_in > timedelta(hours=24):
        raise HTTPException(
            status_code=422,
            detail="Punch-out must be within 24 hours of punch-in.")
    if not is_hr:
        day0 = local_to_utc(body.work_date, time(0), tz)
        if not (day0 <= punch_in <= day0 + timedelta(days=1, hours=12)):
            raise HTTPException(
                status_code=422,
                detail="Punch-in must fall on the work date (or before noon "
                       "the next day for night shifts).")

    ids = list(dict.fromkeys(body.user_ids))
    allowed = set(ids) if is_hr else await roster_svc.manageable_subset(
        db, current_user, set(ids))
    active = set((await db.execute(select(Employee.user_id).where(
        Employee.user_id.in_(ids),
        Employee.status == EmployeeStatus.ACTIVE))).scalars().all())

    batch_id = uuid.uuid4().hex
    results = []
    for uid in ids:
        if uid not in allowed:
            results.append({"user_id": uid, "status": "out_of_scope",
                            "message": "Outside your roster scope."})
            continue
        if uid not in active:
            results.append({"user_id": uid, "status": "error",
                            "message": "Not an active employee."})
            continue
        try:
            # Savepoint per user. log_audit only db.add()s (no commit), so
            # the audit row rolls back with the savepoint on failure and is
            # committed with the batch by the single commit below.
            async with db.begin_nested():
                try:
                    await lock_user_rows(db, [uid])
                except HTTPException as exc:  # 1020/1213: txn already rolled back
                    raise _BatchConflict(exc) from exc
                try:
                    await assert_attendance_editable(
                        db, body.work_date, fresh=True)
                except HTTPException as exc:
                    results.append({"user_id": uid, "status": "locked",
                                    "message": exc.detail})
                    continue
                att = await create_manual_attendance_row(
                    db, current_user, uid, body.work_date, punch_in,
                    punch_out, reason, mode=MODE)
                dismissed = await gap_svc.dismiss_noshow_gap_if_present(
                    db, uid, body.work_date, current_user.id)
                # NOT hr.log_audit: it commits, which would break the batch's
                # single-transaction atomicity (and the savepoint rollback).
                db.add(AuditLog(
                    user_id=current_user.id, action="BULK_MARK_ATTENDANCE",
                    resource_type="attendance", resource_id=str(att.id),
                    details=json.loads(json.dumps({
                        "user_id": uid, "work_date": body.work_date,
                        "punch_in_time": punch_in, "punch_out_time": punch_out,
                        "reason": reason, "batch_id": batch_id,
                        "gaps_dismissed": dismissed}, default=json_serial)),
                    ip_address=request.client.host if request.client else None))
            results.append({"user_id": uid, "status": "created",
                            "attendance_id": att.id})
        except _BatchConflict as bc:
            raise bc.exc
        except OperationalError:
            # lock conflict / deadlock: MariaDB rolled the whole transaction
            # back, so earlier 'created' results would be lies. Abort (409 via
            # guard_conflicts) and let the caller retry the batch.
            raise
        except ManualAttendanceExists as exc:
            results.append({"user_id": uid, "status": "skipped_existing",
                            "message": exc.detail})
        except HTTPException as exc:
            results.append({"user_id": uid, "status": "error",
                            "message": str(exc.detail)})
        except Exception:  # one failure must not abort the batch
            results.append({"user_id": uid, "status": "error",
                            "message": "Unexpected error; not marked."})
    await commit_or_409(db)
    counts = {k: 0 for k in (
        "created", "skipped_existing", "out_of_scope", "locked", "error")}
    for r in results:
        counts[r["status"]] += 1
    return {"batch_id": batch_id, "work_date": body.work_date,
            "results": results, "counts": counts}
