"""Live operations board (Roadmap v2 Phase 1B, Task 9). Read-only."""
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.api import deps
from app.models.coverage_gap import CoverageGap, GapSource
from app.models.roster import RosterEntry, RosterStatus
from app.models.user import User
from app.services import live_ops
from app.services import roster as roster_svc

router = APIRouter()

MAX_EMPLOYEES = 2000


@router.get("/live")
async def live_board(
    *,
    db: deps.DBDep,
    department: Optional[str] = None,
    location: Optional[str] = None,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    scoped = await roster_svc.scoped_employees(db, current_user)
    if not scoped and not roster_svc.is_roster_admin(current_user):
        raise HTTPException(status_code=403, detail="You have no roster scope.")
    cands = [e for e in scoped if e.user_id is not None
             and (not department or e.department == department)
             and (not location or e.location == location)]
    allowed = await roster_svc.manageable_subset(
        db, current_user, {e.user_id for e in cands})
    ids = [e.user_id for e in cands if e.user_id in allowed]
    if len(ids) > MAX_EMPLOYEES:
        raise HTTPException(
            status_code=400,
            detail=f"Too many employees ({len(ids)}); filter by department "
                   f"or location (max {MAX_EMPLOYEES}).")
    now = datetime.now(timezone.utc)
    rows = await live_ops.live_board(db, ids, now)
    noshow = [r for r in rows if r.alerted]
    gaps = {}
    if noshow:
        for g in (await db.execute(select(CoverageGap).where(
                CoverageGap.source == GapSource.NO_SHOW,
                CoverageGap.absent_user_id.in_({r.user_id for r in noshow}),
                CoverageGap.work_date.in_({r.work_date for r in noshow})))
                ).scalars().all():
            gaps[(g.absent_user_id, g.work_date)] = g
    transport: set = set()
    if rows:
        transport = {(u, d) for u, d in (await db.execute(
            select(RosterEntry.employee_id, RosterEntry.work_date).where(
                RosterEntry.employee_id.in_({r.user_id for r in rows}),
                RosterEntry.work_date.in_({r.work_date for r in rows}),
                RosterEntry.status == RosterStatus.PUBLISHED,
                RosterEntry.transport_required.is_(True),
                RosterEntry.shift_template_id.is_not(None)))).all()}
    counts = {s.value: 0 for s in live_ops.LiveStatus}
    for r in rows:
        counts[r.status.value] += 1
    return {
        "now": now.isoformat(),
        "counts": counts,
        "rows": [{
            "user_id": r.user_id, "name": r.name,
            "department": r.department, "location": r.location,
            "work_date": r.work_date.isoformat(),
            "shift_template_id": r.shift_template_id,
            "shift_name": r.shift_name,
            "start": r.start.isoformat() if r.start else None,
            "end": r.end.isoformat() if r.end else None,
            "start_hhmm": r.start_hhmm, "end_hhmm": r.end_hhmm,
            "status": r.status.value, "late_minutes": r.late_minutes,
            "punch_in": r.punch_in.isoformat() if r.punch_in else None,
            "punch_out": r.punch_out.isoformat() if r.punch_out else None,
            "late_notice_eta": r.late_notice_eta.isoformat()
            if r.late_notice_eta else None,
            "late_notice_reason": r.late_notice_reason,
            "transport_required": (r.user_id, r.work_date) in transport,
            "alerted": r.alerted, "half_day_leave": r.half_day_leave,
            "remote_kind": r.remote_kind,
            "gap_id": gaps[(r.user_id, r.work_date)].id
            if (r.user_id, r.work_date) in gaps else None,
            "gap_status": gaps[(r.user_id, r.work_date)].status
            if (r.user_id, r.work_date) in gaps else None,
        } for r in rows],
    }
