"""Selfie upload/view + offline punch batch sync (Roadmap v2 Phase 3, Task 2).

Mounted under /attendance WITHOUT the attendance gate: offline-sync IS the
punch (an employee with no punch yet today must be able to call it) and the
selfie is uploaded just before punching. Auth is required; every route only
touches the caller's own data (HR may view selfies).
"""
import math
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError, OperationalError

from app.api import deps
from app.api.v1.endpoints.roster_common import lock_user_rows, retry_on_lock
from app.core.config import settings
from app.core.datetime_utils import as_utc
from app.models.attendance import Attendance, AttendanceSelfie
from app.models.user import User
from app.schemas.attendance import (
    OfflinePunchResult, OfflineSyncRequest, OfflineSyncResponse,
)
from app.models.audit import AuditLog
from app.services import punch as punch_svc
from app.services.attendance_lock import assert_attendance_editable
from app.services.roster import is_lock_conflict
from app.services.time_rules import get_time_rules

logger = logging.getLogger(__name__)
router = APIRouter()

FUTURE_SKEW = timedelta(minutes=2)
DEFAULT_OFFLINE_MAX_HOURS = 12
MAX_UNATTACHED_SELFIES = 20

_SELFIE_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
_MEDIA = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}


def _looks_like(ext: str, head: bytes) -> bool:
    if ext == "jpg":
        return head.startswith(b"\xff\xd8\xff")
    if ext == "png":
        return head.startswith(b"\x89PNG\r\n\x1a\n")
    return head[:4] == b"RIFF" and head[8:12] == b"WEBP"


def _selfie_dir() -> Path:
    return Path(settings.ATTENDANCE_SELFIE_DIR)


@router.post("/selfie")
async def upload_selfie(
    *,
    db: deps.DBDep,
    current_user: deps.CurrentUser,
    file: UploadFile = File(...),
) -> Any:
    """Upload a punch selfie (jpeg/png/webp, <= 3 MB). Returns `selfie_id`
    to pass on /attendance/mark, /punch-out or an offline-sync item. Only
    the uploader can attach it, once."""
    ext = _SELFIE_TYPES.get((file.content_type or "").lower())
    if ext is None:
        raise HTTPException(
            status_code=400, detail="Only JPEG, PNG or WebP images are allowed")
    pending = (await db.execute(
        select(func.count(AttendanceSelfie.id)).where(
            AttendanceSelfie.user_id == current_user.id,
            AttendanceSelfie.used_at.is_(None)))).scalar_one()
    if pending >= MAX_UNATTACHED_SELFIES:
        raise HTTPException(
            status_code=429,
            detail="Too many unattached selfies; attach or wait for cleanup")
    d = _selfie_dir()
    d.mkdir(parents=True, exist_ok=True)
    stored = f"{uuid4().hex}.{ext}"
    dest = d / stored
    max_bytes = int(settings.ATTENDANCE_SELFIE_MAX_BYTES)
    total = 0
    head = b""
    try:
        with dest.open("wb") as f:
            while True:
                chunk = await file.read(256 * 1024)
                if not chunk:
                    break
                if not head:
                    head = chunk[:16]
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(
                        status_code=413, detail="Selfie exceeds the 3 MB limit")
                f.write(chunk)
        if total == 0 or not _looks_like(ext, head):
            raise HTTPException(
                status_code=400,
                detail="File content does not match the declared image type")
        row = AttendanceSelfie(
            user_id=current_user.id, filename=stored,
            content_type=_MEDIA[ext], size=total)
        db.add(row)
        await db.commit()
    except BaseException:
        dest.unlink(missing_ok=True)
        raise
    return {"selfie_id": row.id, "size": total, "content_type": _MEDIA[ext]}


@router.get("/{attendance_id}/selfie")
async def view_selfie(
    *,
    db: deps.DBDep,
    current_user: deps.CurrentUser,
    attendance_id: int,
    side: Literal["in", "out"] = Query(default="in"),
) -> Any:
    """Stream the punch selfie. HR ('hr employee read') or the record's owner."""
    att = await db.get(Attendance, attendance_id)
    if att is None:
        raise HTTPException(status_code=404, detail="Selfie not found")
    if att.user_id != current_user.id and not deps.user_has_permission(
        current_user, "hr employee read"
    ):
        # 404, not 403: don't confirm that a record/selfie exists.
        raise HTTPException(status_code=404, detail="Selfie not found")
    name = att.selfie_url if side == "in" else att.punch_out_selfie_url
    path = _selfie_dir() / name if name else None
    if path is None or "/" in name or not path.is_file():
        raise HTTPException(status_code=404, detail="Selfie not found")
    db.add(AuditLog(
        user_id=current_user.id, action="SELFIE_VIEW",
        resource_type="attendance", resource_id=str(att.id),
        details={"side": side, "owner_id": att.user_id}))
    await db.commit()
    return FileResponse(
        path, media_type=_MEDIA.get(path.suffix.lstrip("."), "image/jpeg"),
        headers={"Cache-Control": "private, no-store",
                 "X-Content-Type-Options": "nosniff"})


def _coord_ok(v, limit: float) -> bool:
    return v is None or (math.isfinite(v) and -limit <= v <= limit)


def _reason(exc: HTTPException) -> str:
    d = exc.detail
    if isinstance(d, dict):
        return str(d.get("error") or d.get("message") or "rejected")
    return str(d)


@router.post("/offline-sync", response_model=OfflineSyncResponse)
async def offline_sync(
    *,
    db: deps.DBDep,
    current_user: deps.CurrentUser,
    request: Request,
    body: OfflineSyncRequest,
) -> Any:
    """Sync punches captured offline (<= 50). Processed in captured_at order;
    each item runs in its own savepoint and gets a result (created |
    duplicate | rejected + reason) returned in REQUEST order. Idempotent by
    client_uuid. Accepted only if captured <= now + 2 min and within
    `attendance.offline_max_hours` (default 12) of now. Rows are flagged
    for HR review (`is_offline`, `review_flag`).

    `rejected` is TERMINAL: the server will not accept that item later, so the
    client should drop it from its queue (reasons: captured_in_future,
    captured_too_old, payroll_locked, already_punched_in, invalid_client_uuid,
    selfie/policy/geofence errors, no open punch). `duplicate` means the
    server already has it (safe to drop). Only a failed request (network /
    5xx / 409 retry) should be retried."""
    uid = current_user.id
    ip = request.client.host if request.client else None

    async def run() -> list[OfflinePunchResult]:
        # A retry rolls the session back: reload the user fresh.
        user = await db.get(User, uid, populate_existing=True)
        await lock_user_rows(db, [uid])
        rules = await get_time_rules(db)
        try:
            max_h = int(str(rules.get("attendance.offline_max_hours")).strip())
        except ValueError:
            max_h = DEFAULT_OFFLINE_MAX_HOURS
        now = datetime.now(timezone.utc)
        oldest = now - timedelta(hours=max_h)

        order = sorted(
            range(len(body.punches)),
            key=lambda i: (as_utc(body.punches[i].captured_at),
                           body.punches[i].kind == "out", i))
        out: dict[int, OfflinePunchResult] = {}
        seen: dict[str, int] = {}
        for i in order:
            it = body.punches[i]
            cap = as_utc(it.captured_at)

            def res(status, reason=None, att_id=None):
                return OfflinePunchResult(
                    client_uuid=it.client_uuid, kind=it.kind, status=status,
                    reason=reason, attendance_id=att_id)

            if it.client_uuid in seen:  # repeated inside one batch
                out[i] = res("duplicate", att_id=seen[it.client_uuid])
                continue
            dup = await punch_svc._fresh_one(db, select(Attendance).where(or_(
                Attendance.client_uuid == it.client_uuid,
                Attendance.punch_out_client_uuid == it.client_uuid)), True)
            if dup is not None:
                if dup.user_id != uid:  # never reveal other users' rows
                    out[i] = res("rejected", "invalid_client_uuid")
                else:
                    out[i] = res("duplicate", att_id=dup.id)
                continue
            # Per-item (not whole-batch) coordinate validation; null is ok.
            if not (_coord_ok(it.latitude, 90.0)
                    and _coord_ok(it.longitude, 180.0)):
                out[i] = res("rejected", "invalid_coordinates")
                continue
            if cap > now + FUTURE_SKEW:
                out[i] = res("rejected", "captured_in_future")
                continue
            if cap < oldest:
                out[i] = res("rejected", "captured_too_old")
                continue
            # Payroll lock: same rule as HR punch edits (409 -> rejected).
            try:
                if it.kind == "in":
                    wd = (await punch_svc._attribute_punch(db, uid, cap))[0]
                else:
                    open_rec = await punch_svc._find_open_record_for_punch_out(
                        db, uid, cap, fresh=True)
                    wd = open_rec.work_date if open_rec is not None else None
                if wd is not None:
                    await assert_attendance_editable(db, wd, fresh=True)
            except HTTPException as exc:
                if exc.status_code == 409:
                    out[i] = res("rejected", "payroll_locked")
                    continue
                raise
            try:
                async with db.begin_nested():
                    try:
                        common = dict(
                            lat=it.latitude, lng=it.longitude,
                            accuracy=it.accuracy,
                            is_mock=bool(it.is_mock_location),
                            selfie_id=it.selfie_id,
                            liveness_passed=it.liveness_passed,
                            liveness_score=it.liveness_score,
                            is_offline=True, client_uuid=it.client_uuid,
                            ip=ip, fresh=True)
                        if it.kind == "in":
                            att, created = await punch_svc.record_punch_in(
                                db, user, mode="mobile", captured_at=cap,
                                **common)
                            r = (res("created", att_id=att.id) if created else
                                 res("rejected", "already_punched_in", att.id))
                        else:
                            att = await punch_svc.record_punch_out(
                                db, user, at=cap, **common)
                            r = res("created", att_id=att.id)
                    except punch_svc.PunchRejected as exc:
                        # Caught inside the savepoint so the STRICT-geo
                        # audit row it added is kept.
                        r = res("rejected", _reason(exc))
            except IntegrityError:
                r = res("duplicate")  # concurrent same-client_uuid insert
            except OperationalError as exc:
                if is_lock_conflict(exc):
                    raise
                logger.exception("offline-sync item failed")
                r = res("rejected", "internal_error")
            except HTTPException as exc:
                r = res("rejected", _reason(exc))
            except Exception:  # pragma: no cover - isolate bad items
                logger.exception("offline-sync item failed")
                r = res("rejected", "internal_error")
            out[i] = r
            if r.status == "created":
                seen[it.client_uuid] = r.attendance_id
        return [out[i] for i in range(len(body.punches))]

    results = await retry_on_lock(db, run, commit=True)
    counts: dict[str, int] = {}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
    return OfflineSyncResponse(results=results, counts=counts)
