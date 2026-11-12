"""Running-late notices (Roadmap v2 Phase 2, Task 2).

An employee with a shift today (or an overnight shift from yesterday that is
still running) who has not punched in can tell their schedulers when they
expect to arrive. Times are UTC wall-clock like the rest of the roster.
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import delete, select

from app.api import deps
from app.api.v1.endpoints.roster_common import guard_conflicts, lock_user_rows
from app.models.late_notice import LateNotice
from app.models.user import User
from app.services import live_ops
from app.services import roster as roster_svc

router = APIRouter()


class RunningLate(BaseModel):
    minutes_late: Optional[int] = Field(None, ge=5, le=240)
    expected_at: Optional[datetime] = None
    reason: Optional[str] = Field(None, max_length=255)

    @model_validator(mode="after")
    def _one_of(self):
        if (self.minutes_late is None) == (self.expected_at is None):
            raise ValueError("provide exactly one of minutes_late or expected_at")
        return self


def _aware(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


async def _relevant_row(db, user: User, now: datetime):
    """The caller's live row for the shift that is relevant now, or None."""
    rows = await live_ops.live_board(db, [user.id], now)
    r = rows[0] if rows else None
    if r is None or r.shift_template_id is None or r.start is None:
        return None
    return r


def _out(n: Optional[LateNotice], row=None) -> dict:
    if n is None:
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
    now = datetime.now(timezone.utc)
    r = await _relevant_row(db, current_user, now)
    if r is None:
        return {**_out(None), "can_post": False}
    n = (await db.execute(select(LateNotice).where(
        LateNotice.user_id == current_user.id,
        LateNotice.work_date == r.work_date))).scalar_one_or_none()
    can = (r.punch_in is None and r.status != live_ops.LiveStatus.ON_LEAVE
           and now < r.end)
    return {**_out(n), "can_post": can, "work_date": r.work_date.isoformat(),
            "shift_name": r.shift_name, "shift_start": r.start.isoformat(),
            "shift_end": r.end.isoformat()}


@router.post("/my/running-late")
@guard_conflicts
async def post_running_late(
    *, db: deps.DBDep, body: RunningLate,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    now = datetime.now(timezone.utc)
    await lock_user_rows(db, [current_user.id])
    r = await _relevant_row(db, current_user, now)
    if r is None:
        raise HTTPException(400, "You have no shift today to be late for.")
    if r.status == live_ops.LiveStatus.ON_LEAVE:
        raise HTTPException(400, "You are on leave for this shift.")
    if r.punch_in is not None:
        raise HTTPException(400, "You have already punched in for this shift.")
    if now >= r.end:
        raise HTTPException(400, "This shift has already ended.")
    if body.expected_at is not None:
        eta = _aware(body.expected_at).replace(microsecond=0)
    else:
        eta = max(now, r.start).replace(microsecond=0) + timedelta(
            minutes=body.minutes_late)
    if eta < r.start or eta > r.end:
        raise HTTPException(
            400, "Expected arrival must be within your shift "
                 f"({r.start_hhmm}-{r.end_hhmm} UTC).")
    reason = (body.reason or "").strip() or None
    n = (await db.execute(select(LateNotice).where(
        LateNotice.user_id == current_user.id,
        LateNotice.work_date == r.work_date))).scalar_one_or_none()
    if n is None:
        n = LateNotice(user_id=current_user.id, work_date=r.work_date,
                       expected_at=eta, reason=reason)
        db.add(n)
    else:
        n.expected_at, n.reason = eta, reason
        n.created_at = now
    await db.flush()
    recips = (await live_ops._alert_recipients(db, [r], now.date())).get(
        current_user.id, set())
    who = current_user.full_name or current_user.email
    msg = (f"{who} is running late for {r.shift_name or 'their shift'} "
           f"({r.start_hhmm}); expected by {eta.strftime('%H:%M')} UTC."
           + (f" Reason: {reason}" if reason else ""))
    await roster_svc.notify_many(db, [
        (rid, "Running late", msg, "roster", None) for rid in sorted(recips)])
    await db.commit()
    await db.refresh(n)
    return _out(n)


@router.delete("/my/running-late")
@guard_conflicts
async def clear_running_late(
    *, db: deps.DBDep, current_user: User = Depends(deps.get_current_user),
) -> Any:
    now = datetime.now(timezone.utc)
    r = await _relevant_row(db, current_user, now)
    if r is not None:
        await db.execute(delete(LateNotice).where(
            LateNotice.user_id == current_user.id,
            LateNotice.work_date == r.work_date))
        await db.commit()
    return _out(None)
