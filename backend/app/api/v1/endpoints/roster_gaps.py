"""Coverage gaps (Roadmap v2 Phase 2, Task 3).

  open --assign--> filled      (replacement gets a PUBLISHED cell)
  open --broadcast--> open     (linked open shift; filled when it fills)
  open --dismiss--> dismissed
Lock order: linked open shift, then the gap row (same as open-shift confirm).
"""
from datetime import date as pydate, datetime, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from app.api import deps
from app.api.v1.endpoints.hr import log_audit
from app.api.v1.endpoints.roster_common import (
    commit_or_409, guard_conflicts, lock_row, lock_user_rows, names,
)
from app.models.coverage_gap import CoverageGap, GapSource, GapStatus
from app.models.employee import Employee
from app.models.open_shift import OpenShift, OpenShiftStatus
from app.models.roster import RosterEntry, RosterStatus
from app.models.shift import ShiftTemplate
from app.models.user import User
from app.schemas.roster import IntId
from app.services import coverage_gaps as gap_svc
from app.services import open_shifts as os_svc
from app.services import roster as roster_svc
from app.services import swaps as swap_svc
from app.services.effective_shift import effective_shifts_for_range
from app.services.supersede import supersede_pending

router = APIRouter()
RTYPE = gap_svc.RTYPE
MAX_LIST = 500


class GapCreate(BaseModel):
    work_date: pydate
    shift_template_id: IntId
    source: str = GapSource.MANUAL
    absent_user_id: Optional[IntId] = None
    department: Optional[str] = Field(default=None, max_length=100)
    location: Optional[str] = Field(default=None, max_length=100)
    note: Optional[str] = Field(default=None, max_length=255)

    @field_validator("source")
    @classmethod
    def _src(cls, v):
        if v not in GapSource.MANUAL_ALLOWED:
            raise ValueError("source must be 'sick_call' or 'manual'")
        return v

    @field_validator("department", "location", "note")
    @classmethod
    def _blank(cls, v):
        return (v or "").strip() or None


class GapAssign(BaseModel):
    user_id: IntId


class GapBroadcast(BaseModel):
    auto_confirm: bool = False


class GapDismiss(BaseModel):
    note: Optional[str] = Field(default=None, max_length=255)


# ------------------------------- helpers -------------------------------

async def _visible_ids(db, actor: User, gaps: List[CoverageGap]) -> set:
    if roster_svc.is_roster_admin(actor):
        return {g.id for g in gaps}
    absent = {g.absent_user_id for g in gaps if g.absent_user_id}
    ok = await roster_svc.manageable_subset(db, actor, absent) if absent else set()
    heads = set(await roster_svc.scope_department_names(db, actor) or [])
    return {g.id for g in gaps if (
        g.absent_user_id in ok if g.absent_user_id
        else (g.department is not None and g.department in heads))}


async def _can_see(db, actor: User, gap: CoverageGap) -> bool:
    return gap.id in await _visible_ids(db, actor, [gap])


async def _require_see(db, actor: User, gap: CoverageGap) -> None:
    if not await _can_see(db, actor, gap):
        raise HTTPException(
            status_code=403, detail="This gap is outside your roster scope.")


async def _get(db, gap_id: int) -> CoverageGap:
    g = await db.get(CoverageGap, gap_id)
    if g is None:
        raise HTTPException(status_code=404, detail="Coverage gap not found")
    return g


async def _read_many(db, gaps: List[CoverageGap]) -> List[dict]:
    if not gaps:
        return []
    nm = await names(db, {u for g in gaps for u in (
        g.absent_user_id, g.filled_by_user_id, g.resolved_by_id)})
    tpls = {t.id: t for t in (await db.execute(select(ShiftTemplate).where(
        ShiftTemplate.id.in_({g.shift_template_id for g in gaps})))).scalars().all()}
    sids = {g.open_shift_id for g in gaps if g.open_shift_id}
    sst = {s.id: s.status for s in (await db.execute(select(OpenShift).where(
        OpenShift.id.in_(sids)))).scalars().all()} if sids else {}
    out = []
    for g in gaps:
        t = tpls.get(g.shift_template_id)
        out.append({
            "id": g.id, "work_date": g.work_date.isoformat(),
            "shift_template_id": g.shift_template_id,
            "shift_name": t.name if t else None,
            "shift_start": t.start_time.strftime("%H:%M") if t else None,
            "shift_end": t.end_time.strftime("%H:%M") if t else None,
            "department": g.department, "location": g.location,
            "absent_user_id": g.absent_user_id,
            "absent_name": nm.get(g.absent_user_id),
            "source": g.source, "source_id": g.source_id,
            "status": g.status, "open_shift_id": g.open_shift_id,
            "open_shift_status": sst.get(g.open_shift_id),
            "filled_by_user_id": g.filled_by_user_id,
            "filled_by_name": nm.get(g.filled_by_user_id),
            "resolved_by_id": g.resolved_by_id,
            "resolved_at": g.resolved_at.isoformat() if g.resolved_at else None,
            "note": g.note,
            "created_at": g.created_at.isoformat() if g.created_at else None,
        })
    return out


async def _lock_gap_chain(db, gap_id: int):
    """Lock the linked open shift (if any), then the gap. Returns
    (gap, shift|None). 404 missing; 409 if the link moved meanwhile."""
    peek = await db.get(CoverageGap, gap_id)
    if peek is None:
        raise HTTPException(status_code=404, detail="Coverage gap not found")
    shift = None
    if peek.open_shift_id:
        shift = await lock_row(
            db, select(OpenShift).where(OpenShift.id == peek.open_shift_id),
            "Coverage gap changed concurrently; retry")
    gap = await lock_row(
        db, select(CoverageGap).where(CoverageGap.id == gap_id),
        "Coverage gap changed concurrently; retry")
    if gap is None:
        raise HTTPException(status_code=404, detail="Coverage gap not found")
    if gap.open_shift_id != (shift.id if shift else None):
        raise HTTPException(
            status_code=409, detail="Coverage gap changed concurrently; retry")
    return gap, shift


def _need_open(gap: CoverageGap) -> None:
    if gap.status != GapStatus.OPEN:
        raise HTTPException(
            status_code=409, detail=f"Coverage gap is already {gap.status}")


async def _cancel_linked(db, shift: Optional[OpenShift], actor_id: int, why: str):
    if shift is not None and shift.status == OpenShiftStatus.OPEN:
        shift.status = OpenShiftStatus.CANCELLED
        await os_svc.reject_pending(
            db, shift, actor_id, why, title="Open shift cancelled")


# ------------------------------- endpoints -------------------------------

@router.get("/gaps")
async def list_gaps(
    *,
    db: deps.DBDep,
    status: Optional[str] = Query(default=None),
    date_from: Optional[pydate] = None,
    date_to: Optional[pydate] = None,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    if status is not None and status not in (
            GapStatus.OPEN, GapStatus.FILLED, GapStatus.DISMISSED):
        raise HTTPException(status_code=400, detail="invalid status")
    q = select(CoverageGap)
    if status:
        q = q.where(CoverageGap.status == status)
    if date_from:
        q = q.where(CoverageGap.work_date >= date_from)
    if date_to:
        q = q.where(CoverageGap.work_date <= date_to)
    gaps = list((await db.execute(
        q.order_by(CoverageGap.work_date, CoverageGap.id).limit(MAX_LIST)
    )).scalars().all())
    vis = await _visible_ids(db, current_user, gaps)
    return await _read_many(db, [g for g in gaps if g.id in vis])


@router.post("/gaps")
@guard_conflicts
async def create_gap(
    *,
    db: deps.DBDep,
    request: Request,
    body: GapCreate,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    if body.work_date < os_svc.today():
        raise HTTPException(status_code=400, detail="work_date cannot be in the past")
    tpl = await db.get(ShiftTemplate, body.shift_template_id)
    if tpl is None or not tpl.is_active:
        raise HTTPException(
            status_code=400, detail="Unknown or inactive shift template")
    admin = roster_svc.is_roster_admin(current_user)
    if body.absent_user_id:
        if not await roster_svc.can_manage_employee(
                db, current_user, body.absent_user_id):
            raise HTTPException(
                status_code=403, detail="This employee is outside your roster scope.")
    else:
        heads = await roster_svc.scope_department_names(db, current_user)
        if not admin and not (body.department and body.department in (heads or [])):
            raise HTTPException(
                status_code=403,
                detail="Without an absent employee, a department you head is required.")
    gap = await gap_svc.open_gap(
        db, work_date=body.work_date, shift_template_id=body.shift_template_id,
        department=body.department, location=body.location,
        absent_user_id=body.absent_user_id, source=body.source,
        note=body.note)
    await commit_or_409(db, "Coverage gap changed concurrently; retry")
    await db.refresh(gap)
    await log_audit(db, current_user.id, "roster.gap.create", RTYPE,
                    str(gap.id), {"source": body.source}, request)
    return (await _read_many(db, [gap]))[0]


@router.get("/gaps/{gap_id}/suggestions")
async def gap_suggestions(
    *,
    db: deps.DBDep,
    gap_id: int,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    gap = await _get(db, gap_id)
    await _require_see(db, current_user, gap)
    return {"gap": (await _read_many(db, [gap]))[0],
            "suggestions": await gap_svc.suggest_replacements(
                db, gap, current_user)}


@router.post("/gaps/{gap_id}/assign")
@guard_conflicts
async def assign_gap(
    *,
    db: deps.DBDep,
    request: Request,
    gap_id: int,
    body: GapAssign,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    uid = body.user_id
    admin = roster_svc.is_roster_admin(current_user)
    if not (admin or await roster_svc.can_publish_for(db, current_user, uid)):
        raise HTTPException(
            status_code=403,
            detail="You cannot publish schedules for that employee.")
    gap, shift = await _lock_gap_chain(db, gap_id)
    await _require_see(db, current_user, gap)
    _need_open(gap)
    if uid == gap.absent_user_id:
        raise HTTPException(
            status_code=400, detail="The absent employee cannot be the replacement")
    d = gap.work_date
    await lock_user_rows(db, [uid])
    entry = await lock_row(
        db, select(RosterEntry).where(
            RosterEntry.employee_id == uid, RosterEntry.work_date == d),
        "Roster changed concurrently; retry")
    if (entry is not None and entry.status == RosterStatus.PUBLISHED
            and not entry.is_week_off and entry.shift_template_id is not None):
        raise HTTPException(
            status_code=400, detail="Already scheduled to work that day")
    tshift = gap_svc.transient_shift(gap)
    reason = await os_svc.eligible_reason(db, tshift, uid, approver=current_user)
    if reason:
        raise HTTPException(status_code=400, detail=reason)
    warnings = await os_svc._claim_warnings(db, tshift, uid, entry)
    if (entry is not None and entry.status == RosterStatus.PUBLISHED
            and (entry.is_week_off or entry.shift_template_id is not None)):
        old = (entry.shift_template_id, bool(entry.is_week_off))
    else:
        eff = (await effective_shifts_for_range(db, [uid], d, d))[(uid, d)]
        old = swap_svc.cell_of(eff)
    await supersede_pending(
        db, {(uid, d)}, "coverage gap", gap.id, current_user.id, RTYPE)
    await _cancel_linked(
        db, shift, current_user.id,
        f"The open shift on {d.isoformat()} was filled directly by a scheduler")
    dept = (await db.execute(
        select(Employee.department).where(Employee.user_id == uid))).scalar()
    entry, _o = await roster_svc.upsert_entry(
        db, employee_id=uid, work_date=d,
        shift_template_id=gap.shift_template_id, is_week_off=False,
        status=RosterStatus.PUBLISHED, actor_id=current_user.id,
        department=dept, overwrite=True)
    await db.flush()
    roster_svc.record_change(
        db, entry, employee_id=uid, work_date=d, old_tpl=old[0],
        old_off=old[1], new_tpl=gap.shift_template_id, new_off=False,
        action="update", reason=f"Coverage gap #{gap.id}",
        actor_id=current_user.id)
    gap.status = GapStatus.FILLED
    gap.filled_by_user_id = uid
    gap.resolved_by_id = current_user.id
    gap.resolved_at = datetime.now(timezone.utc)
    await roster_svc.notify_schedule_changed(db, {uid: {d}})
    sched = (await gap_svc._scheduler_ids(db, gap)) - {current_user.id, uid}
    nm = await names(db, {uid, gap.absent_user_id})
    await roster_svc.notify_many(db, [
        (uid, "Covering a shift",
         f"You were assigned to cover a shift on {d.isoformat()}",
         RTYPE, str(gap.id))
    ] + [
        (s, "Coverage gap filled",
         f"{nm.get(uid) or uid} will cover the shift on {d.isoformat()}"
         + (f" for {nm[gap.absent_user_id]}" if nm.get(gap.absent_user_id) else ""),
         RTYPE, str(gap.id))
        for s in sorted(sched)])
    await commit_or_409(db, "Coverage gap changed concurrently; retry")
    await db.refresh(gap)
    await log_audit(db, current_user.id, "roster.gap.assign", RTYPE,
                    str(gap.id), {"user_id": uid}, request)
    out = (await _read_many(db, [gap]))[0]
    out["warnings"] = warnings
    return out


@router.post("/gaps/{gap_id}/broadcast")
@guard_conflicts
async def broadcast_gap(
    *,
    db: deps.DBDep,
    request: Request,
    gap_id: int,
    body: GapBroadcast,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    gap, shift = await _lock_gap_chain(db, gap_id)
    await _require_see(db, current_user, gap)
    _need_open(gap)
    if shift is not None and shift.status == OpenShiftStatus.OPEN:
        raise HTTPException(
            status_code=409, detail="This gap is already broadcast as an open shift")
    excl = {gap.absent_user_id} if gap.absent_user_id else set()
    new = await os_svc.create_open_shift(
        db, current_user, work_date=gap.work_date,
        shift_template_id=gap.shift_template_id, department=gap.department,
        location=gap.location, slots=1, note=f"Coverage gap #{gap.id}",
        auto_confirm=body.auto_confirm, exclude_user_ids=excl,
        check_scope=True)
    gap.open_shift_id = new.id
    await commit_or_409(db, "Coverage gap changed concurrently; retry")
    await db.refresh(gap)
    await log_audit(db, current_user.id, "roster.gap.broadcast", RTYPE,
                    str(gap.id), {"open_shift_id": new.id}, request)
    return (await _read_many(db, [gap]))[0]


@router.post("/gaps/{gap_id}/dismiss")
@guard_conflicts
async def dismiss_gap(
    *,
    db: deps.DBDep,
    request: Request,
    gap_id: int,
    body: GapDismiss,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    gap, shift = await _lock_gap_chain(db, gap_id)
    await _require_see(db, current_user, gap)
    _need_open(gap)
    await _cancel_linked(
        db, shift, current_user.id,
        f"The open shift on {gap.work_date.isoformat()} was cancelled")
    gap.status = GapStatus.DISMISSED
    gap.note = (body.note or "").strip() or gap.note
    gap.resolved_by_id = current_user.id
    gap.resolved_at = datetime.now(timezone.utc)
    await commit_or_409(db, "Coverage gap changed concurrently; retry")
    await db.refresh(gap)
    await log_audit(db, current_user.id, "roster.gap.dismiss", RTYPE,
                    str(gap.id), {}, request)
    return (await _read_many(db, [gap]))[0]
