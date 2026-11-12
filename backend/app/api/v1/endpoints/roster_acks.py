"""Acknowledgement of emergency (lock-window) schedule changes
(Roadmap v2 Phase 2, Task 4).

`ScheduleChangeAck` rows are created by `roster_svc.flush_emergency` for each
emergency change; the employee acknowledges their own, schedulers see who has
not yet.
"""
from datetime import datetime, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select

from app.api import deps
from app.api.v1.endpoints.roster_common import (
    commit_or_409, guard_conflicts, lock_row, names,
)
from app.models.roster import RosterEntryHistory, ScheduleChangeAck
from app.models.shift import ShiftTemplate
from app.models.user import User
from app.services import roster as roster_svc

router = APIRouter()


class AckRead(BaseModel):
    id: int
    history_id: int
    employee_id: int
    employee_name: Optional[str] = None
    work_date: Any
    old_shift_name: Optional[str] = None
    old_is_week_off: bool = False
    new_shift_name: Optional[str] = None
    new_is_week_off: bool = False
    reason: Optional[str] = None
    changed_by_name: Optional[str] = None
    changed_at: Optional[datetime] = None
    acknowledged_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


async def _read(db, rows) -> List[AckRead]:
    """rows = [(ack, history)]"""
    if not rows:
        return []
    nm = await names(db, {a.user_id for a, _h in rows}
                     | {h.changed_by_id for _a, h in rows})
    tids = {t for _a, h in rows
            for t in (h.old_shift_template_id, h.new_shift_template_id)
            if t is not None}
    tpl = {}
    if tids:
        tpl = {t.id: t.name for t in (await db.execute(
            select(ShiftTemplate).where(ShiftTemplate.id.in_(tids))
        )).scalars().all()}
    out = []
    for a, h in rows:
        out.append(AckRead(
            id=a.id, history_id=h.id, employee_id=a.user_id,
            employee_name=nm.get(a.user_id), work_date=h.work_date,
            old_shift_name=tpl.get(h.old_shift_template_id),
            old_is_week_off=h.old_is_week_off,
            new_shift_name=tpl.get(h.new_shift_template_id),
            new_is_week_off=h.new_is_week_off, reason=h.reason,
            changed_by_name=nm.get(h.changed_by_id), changed_at=h.changed_at,
            acknowledged_at=a.acknowledged_at, created_at=a.created_at))
    return out


@router.get("/my/acks", response_model=List[AckRead])
async def my_pending_acks(
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Emergency schedule changes the caller still has to acknowledge."""
    rows = (await db.execute(
        select(ScheduleChangeAck, RosterEntryHistory)
        .join(RosterEntryHistory,
              RosterEntryHistory.id == ScheduleChangeAck.history_id)
        .where(ScheduleChangeAck.user_id == current_user.id,
               ScheduleChangeAck.acknowledged_at.is_(None))
        .order_by(RosterEntryHistory.work_date, ScheduleChangeAck.id)
        .limit(200)
    )).all()
    return await _read(db, [(a, h) for a, h in rows])


@router.post("/my/acks/{ack_id}", response_model=AckRead)
@guard_conflicts
async def acknowledge(
    *,
    db: deps.DBDep,
    request: Request,
    ack_id: int,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    ack = await lock_row(
        db, select(ScheduleChangeAck).where(ScheduleChangeAck.id == ack_id))
    if ack is None:
        raise HTTPException(status_code=404, detail="Acknowledgement not found")
    if ack.user_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="You can only acknowledge your own changes")
    if ack.acknowledged_at is None:
        ack.acknowledged_at = datetime.now(timezone.utc)
    await commit_or_409(db)
    await db.refresh(ack)
    h = await db.get(RosterEntryHistory, ack.history_id)
    return (await _read(db, [(ack, h)]))[0]


@router.get("/acks", response_model=List[AckRead])
async def scoped_acks(
    db: deps.DBDep,
    status: str = Query("pending", pattern="^(pending|acknowledged|all)$"),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Acknowledgements for the schedulers' scope (admins: everyone)."""
    q = (
        select(ScheduleChangeAck, RosterEntryHistory)
        .join(RosterEntryHistory,
              RosterEntryHistory.id == ScheduleChangeAck.history_id)
        .order_by(RosterEntryHistory.work_date.desc(), ScheduleChangeAck.id.desc())
        .limit(500)
    )
    if status == "pending":
        q = q.where(ScheduleChangeAck.acknowledged_at.is_(None))
    elif status == "acknowledged":
        q = q.where(ScheduleChangeAck.acknowledged_at.is_not(None))
    if not roster_svc.is_roster_admin(current_user):
        ids = {e.user_id for e in await roster_svc.scoped_employees(
            db, current_user)}
        if not ids:
            raise HTTPException(status_code=403, detail="You have no roster scope.")
        q = q.where(ScheduleChangeAck.user_id.in_(ids))
    rows = (await db.execute(q)).all()
    return await _read(db, [(a, h) for a, h in rows])
