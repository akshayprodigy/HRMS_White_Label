"""Running-late notices (Roadmap v2 Phase 2, Task 2).

An employee with a shift today (or an overnight shift from yesterday that is
still running) who has not punched in can tell their schedulers when they
expect to arrive. Times are org-local wall-clock (org.timezone) like the rest of the roster.
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select

from app.api import deps
from app.api.v1.endpoints.roster_common import (
    guard_conflicts, lock_user_rows, retry_on_lock,
)
from app.models.attendance import Attendance
from app.models.late_notice import LateNotice
from app.models.user import User
from app.services import live_ops
from app.services import roster as roster_svc
from app.services.org_time import local_today_for, org_tz

router = APIRouter()

MAX_LATE_MINUTES = 240
NOTIFY_THROTTLE = timedelta(minutes=5)


def _now() -> datetime:  # patched in tests
    return datetime.now(timezone.utc)


class RunningLate(BaseModel):
    minutes_late: Optional[int] = Field(None, ge=5, le=MAX_LATE_MINUTES)
    expected_at: Optional[datetime] = None
    reason: Optional[str] = Field(None, max_length=255)

    @model_validator(mode="after")
    def _one_of(self):
        if (self.minutes_late is None) == (self.expected_at is None):
            raise ValueError("provide exactly one of minutes_late or expected_at")
        return self


def _aware(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


async def _relevant_row(db, uid: int, now: datetime):
    """The caller's live row for the shift that is relevant now, or None."""
    rows = await live_ops.live_board(db, [uid], now)
    r = rows[0] if rows else None
    if r is None or r.shift_template_id is None or r.start is None:
        return None
    return r


def _out(n: Optional[LateNotice], row=None) -> dict:
    if n is None or n.cleared_at is not None:
        return {"notice": None}
    return {"notice": {
        "work_date": n.work_date.isoformat(),
        "expected_at": _aware(n.expected_at).isoformat(),
        "eta_hhmm": _aware(n.expected_at).strftime("%H:%M"),
        "reason": n.reason,
        "created_at": _aware(n.created_at).isoformat(),
    }}


@router.get("/my/running-late")
async def get_running_late(
    db: deps.DBDep, current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Current notice for the relevant shift plus whether one can be posted."""
    uid = current_user.id
    now = _now()
    r = await _relevant_row(db, uid, now)
    if r is None:
        return {**_out(None), "can_post": False}
    n = (await db.execute(select(LateNotice).where(
        LateNotice.user_id == uid,
        LateNotice.work_date == r.work_date))).scalar_one_or_none()
    can = (r.punch_in is None and r.status != live_ops.LiveStatus.ON_LEAVE
           and now < r.end)
    return {**_out(n), "can_post": can, "work_date": r.work_date.isoformat(),
            "shift_name": r.shift_name, "shift_start": r.start.isoformat(),
            "shift_end": r.end.isoformat()}


async def _notify_schedulers(db, uid, r, now, text, n) -> None:
    recips = (await live_ops._alert_recipients(
        db, [r], local_today_for(await org_tz(db), now))).get(
        uid, set())
    await roster_svc.notify_many(db, [
        (rid, "Running late", text, "roster", None) for rid in sorted(recips)])
    n.last_notified_at = now


def _throttled_ok(n: Optional[LateNotice], now: datetime) -> bool:
    return (n is None or n.last_notified_at is None
            or now - _aware(n.last_notified_at) >= NOTIFY_THROTTLE)


async def _lock_state(db, uid, now):
    """Locking (current) reads of the caller's notices and attendance for
    yesterday/today, done BEFORE any plain read of those tables so MariaDB
    does not raise 1020 against a stale snapshot. Returns
    ({work_date: LateNotice}, {work_dates with a punch})."""
    today = local_today_for(await org_tz(db), now)
    days = [today - timedelta(days=1), today]
    notices = {n.work_date: n for n in (await db.execute(
        select(LateNotice).where(LateNotice.user_id == uid,
                                 LateNotice.work_date.in_(days))
        .with_for_update().execution_options(populate_existing=True)
    )).scalars().all()}
    punched = {d for (d,) in (await db.execute(
        select(Attendance.work_date).where(
            Attendance.user_id == uid, Attendance.work_date.in_(days))
        .with_for_update())).all()}
    return notices, punched


@router.post("/my/running-late")
@guard_conflicts
async def post_running_late(
    *, db: deps.DBDep, body: RunningLate,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    uid, who = current_user.id, current_user.full_name or current_user.email
    return await retry_on_lock(db, lambda: _post(db, uid, who, body))


async def _post(db, uid: int, who: str, body: RunningLate) -> Any:
    now = _now()
    tz = await org_tz(db)
    await lock_user_rows(db, [uid])
    notices, punched = await _lock_state(db, uid, now)
    r = await _relevant_row(db, uid, now)
    if r is None:
        raise HTTPException(400, "You have no shift today to be late for.")
    if r.status == live_ops.LiveStatus.ON_LEAVE:
        raise HTTPException(400, "You are on leave for this shift.")
    if r.punch_in is not None or r.work_date in punched:
        raise HTTPException(400, "You have already punched in for this shift.")
    if now >= r.end:
        raise HTTPException(400, "This shift has already ended.")
    base = max(now, r.start).replace(microsecond=0)
    if body.expected_at is not None:
        eta = _aware(body.expected_at).replace(microsecond=0)
    else:
        eta = base + timedelta(minutes=body.minutes_late)
    if eta < r.start or eta > r.end:
        raise HTTPException(
            400, "Expected arrival must be within your shift "
                 f"({r.start_hhmm}-{r.end_hhmm}).")
    if eta - base > timedelta(minutes=MAX_LATE_MINUTES):
        raise HTTPException(
            400, f"Expected arrival can be at most {MAX_LATE_MINUTES} minutes away.")
    reason = (body.reason or "").strip() or None
    n = notices.get(r.work_date)
    changed = (n is None or n.cleared_at is not None
               or _aware(n.expected_at) != eta)
    if n is None:
        n = LateNotice(user_id=uid, work_date=r.work_date,
                       expected_at=eta, reason=reason, created_at=now)
        db.add(n)
    else:
        n.expected_at, n.reason, n.cleared_at = eta, reason, None
    n.posted_at = now
    await db.flush()
    if changed and _throttled_ok(n, now):
        await _notify_schedulers(
            db, uid, r, now,
            f"{who} is running late for {r.shift_name or 'their shift'} "
            f"({r.start_hhmm}); expected by {eta.astimezone(tz).strftime('%H:%M')}."
            + (f" Reason: {reason}" if reason else ""), n)
    await db.commit()
    await db.refresh(n)
    return _out(n)


@router.delete("/my/running-late")
@guard_conflicts
async def clear_running_late(
    *, db: deps.DBDep, current_user: User = Depends(deps.get_current_user),
) -> Any:
    uid, who = current_user.id, current_user.full_name or current_user.email
    return await retry_on_lock(db, lambda: _clear(db, uid, who))


async def _clear(db, uid: int, who: str) -> Any:
    now = _now()
    await lock_user_rows(db, [uid])
    notices, _ = await _lock_state(db, uid, now)
    r = await _relevant_row(db, uid, now)
    if r is not None:
        n = notices.get(r.work_date)
        if n is not None and n.cleared_at is None:
            n.cleared_at = now  # row kept so the notify throttle survives
            if _throttled_ok(n, now):
                await _notify_schedulers(
                    db, uid, r, now,
                    f"{who} is no longer running late for "
                    f"{r.shift_name or 'their shift'} ({r.start_hhmm}).", n)
            await db.commit()
    return _out(None)
