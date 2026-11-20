"""Employee optional-holiday picks (Phase 6A Task 6). Mounted at /holidays,
NOT attendance-gated. Lock order: chain instance -> pick row. Writes: lock ->
service -> commit_or_409 once."""
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.api import deps
from app.api.v1.endpoints.approval_chains import instantiate_for_entity
from app.api.v1.endpoints.roster_common import (
    commit_or_409, guard_conflicts, lock_row_retry, reload_user,
)
from app.models.approval_chain import (
    ApprovalChain, ChainEntityType, ChainedApprovalInstance,
    ChainedApprovalStatus,
)
from app.models.employee import Employee
from app.models.hr import HolidayCalendar
from app.models.optional_holiday import OptionalHolidayPick, PickStatus
from app.models.user import User
from app.services import holidays as holidays_svc
from app.services import optional_holidays as svc
from app.services import roster as roster_svc
from app.services.org_time import local_today
from app.services.self_approval import guard_self_approval

router = APIRouter()
PERM_HR = "hr employee write"
PERM_HR_READ = "hr employee read"
PERM_LEAVE = "leave approve"


class PickIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    holiday_id: int
    reason: Optional[str] = Field(default=None, max_length=1000)


class DecideIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approve: bool
    note: Optional[str] = Field(default=None, max_length=500)


def _iso(d) -> Optional[str]:
    return d.isoformat() if d else None


def _is_hr(user: User) -> bool:
    return deps.user_has_permission(user, PERM_HR)


def _pick_out(p: OptionalHolidayPick, hol: Optional[HolidayCalendar],
              name: Optional[str] = None) -> dict:
    return {
        "id": p.id, "status": p.status, "year": p.year,
        "holiday": ({"id": hol.id, "name": hol.name, "date": _iso(hol.date),
                     "location": hol.location} if hol else None),
        "user_id": p.user_id, "user_name": name, "reason": p.reason,
        "decision_note": p.decision_note,
        "created_at": _iso(p.created_at), "decided_at": _iso(p.decided_at),
    }


async def _chain_instance_id(db, pick_id: int) -> Optional[int]:
    return (await db.execute(
        select(ChainedApprovalInstance.id).where(
            ChainedApprovalInstance.entity_type
            == ChainEntityType.OPTIONAL_HOLIDAY,
            ChainedApprovalInstance.entity_id == pick_id)
        .order_by(ChainedApprovalInstance.id.desc()).limit(1)
    )).scalar_one_or_none()


async def _detail(db, pid: int) -> dict:
    db.expire_all()
    p = (await db.execute(select(OptionalHolidayPick).where(
        OptionalHolidayPick.id == pid)
        .execution_options(populate_existing=True))).scalars().one()
    hol = await db.get(HolidayCalendar, p.holiday_id)
    d = _pick_out(p, hol)
    d["routed_via"] = ("chain" if await _chain_instance_id(db, p.id)
                       else "direct")
    return d


@router.get("/my")
async def my_holidays(
    db: deps.DBDep, year: Optional[int] = Query(None, ge=2000, le=2100),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    year = year or (await local_today(db)).year
    loc = await svc.user_location(db, current_user.id)
    from datetime import date as _d
    hols = (await db.execute(
        select(HolidayCalendar).where(
            HolidayCalendar.date >= _d(year, 1, 1),
            HolidayCalendar.date <= _d(year, 12, 31))
        .order_by(HolidayCalendar.date, HolidayCalendar.id))).scalars().all()
    picks = {p.holiday_id: p for p in (await db.execute(
        select(OptionalHolidayPick).where(
            OptionalHolidayPick.user_id == current_user.id,
            OptionalHolidayPick.year == year,
            OptionalHolidayPick.status.in_(PickStatus.ACTIVE))
        .order_by(OptionalHolidayPick.id))).scalars().all()}
    q = await svc.quota(db)
    out = []
    for h in hols:
        if not holidays_svc.applies(h.location, loc):
            continue
        p = picks.get(h.id) if h.is_optional else None
        out.append({
            "id": h.id, "name": h.name, "date": _iso(h.date),
            "location": h.location, "is_optional": bool(h.is_optional),
            "pick": {"id": p.id, "status": p.status} if p else None})
    n = len(picks)
    return {"quota": q, "used": n, "remaining": max(q - n, 0),
            "year": year, "holidays": out}


@router.post("/picks", status_code=201)
@guard_conflicts
async def create_pick(
    payload: PickIn, db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    uid, uname = current_user.id, current_user.full_name or current_user.email
    pick = await svc.create_pick(
        db, user=current_user, holiday_id=payload.holiday_id,
        reason=payload.reason)
    hol = await db.get(HolidayCalendar, pick.holiday_id)
    chain_exists = (await db.execute(select(ApprovalChain.id).where(
        ApprovalChain.entity_type == ChainEntityType.OPTIONAL_HOLIDAY,
        ApprovalChain.is_active.is_(True)).limit(1))).first() is not None
    if chain_exists:
        dept = (await db.execute(select(Employee.department).where(
            Employee.user_id == uid))).scalar_one_or_none()
        inst = await instantiate_for_entity(
            db=db, entity_type=ChainEntityType.OPTIONAL_HOLIDAY,
            entity_id=pick.id, submitter=current_user, amount_paise=0,
            department=dept, context={"holiday": hol.name}, commit=False)
        if inst.status == ChainedApprovalStatus.APPROVED:
            await svc.finalize(db, pick, approved=True, actor=None,
                               note=None)
    else:
        ids = await svc.direct_approver_ids(db, uid)
        await roster_svc.notify_many(db, [(
            u, "Optional holiday request",
            f"{uname} picked optional holiday {hol.name} "
            f"({hol.date.isoformat()}).",
            svc.RT, str(pick.id), "optional_holiday_submitted") for u in ids])
    pid = pick.id
    await commit_or_409(db)
    return await _detail(db, pid)


async def _lock_pick(db, pid: int, current_user: User) -> OptionalHolidayPick:
    p = await lock_row_retry(
        db, select(OptionalHolidayPick).where(OptionalHolidayPick.id == pid),
        reload=reload_user(db, current_user))
    if p is None:
        raise HTTPException(404, "Pick not found")
    return p


@router.post("/picks/{pick_id}/cancel")
@guard_conflicts
async def cancel_pick(
    pick_id: int, db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    hr = _is_hr(current_user)
    actor = current_user
    owner = (await db.execute(select(OptionalHolidayPick.user_id).where(
        OptionalHolidayPick.id == pick_id))).scalar_one_or_none()
    if owner is None or (owner != actor.id and not hr):
        raise HTTPException(404, "Pick not found")
    iid = await _chain_instance_id(db, pick_id)
    if iid:  # lock order: instance -> pick
        await lock_row_retry(
            db, select(ChainedApprovalInstance).where(
                ChainedApprovalInstance.id == iid),
            reload=reload_user(db, actor))
    pick = await _lock_pick(db, pick_id, actor)
    await svc.cancel(db, pick, actor=actor, is_hr=hr)
    await commit_or_409(db)
    return await _detail(db, pick_id)


@router.get("/picks")
async def list_picks(
    db: deps.DBDep, status: Optional[str] = None,
    year: Optional[int] = Query(None, ge=2000, le=2100),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    q = (select(OptionalHolidayPick, HolidayCalendar, User.full_name)
         .join(HolidayCalendar, HolidayCalendar.id == OptionalHolidayPick.holiday_id)
         .join(User, User.id == OptionalHolidayPick.user_id))
    if not (_is_hr(current_user)
            or deps.user_has_permission(current_user, PERM_HR_READ)):
        has_reports = (await db.execute(select(User.id).where(
            User.manager_id == current_user.id).limit(1))).first()
        if not has_reports:
            raise HTTPException(403, "Not allowed")
        q = q.where(User.manager_id == current_user.id)
    if status:
        if status not in (PickStatus.PENDING, PickStatus.APPROVED,
                          PickStatus.REJECTED, PickStatus.CANCELLED):
            raise HTTPException(422, f"Unknown status: {status}")
        q = q.where(OptionalHolidayPick.status == status)
    if year:
        q = q.where(OptionalHolidayPick.year == year)
    rows = (await db.execute(q.order_by(OptionalHolidayPick.id.desc()))).all()
    return [_pick_out(p, h, n) for p, h, n in rows]


@router.post("/picks/{pick_id}/decide")
@guard_conflicts
async def decide_pick(
    pick_id: int, payload: DecideIn, db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    actor = current_user
    pick = await _lock_pick(db, pick_id, actor)
    if await _chain_instance_id(db, pick.id):
        raise HTTPException(409, "decide via approvals")
    guard_self_approval(actor.id, pick.user_id)
    mgr = (await db.execute(select(User.manager_id).where(
        User.id == pick.user_id))).scalar_one_or_none()
    if not (mgr == actor.id or _is_hr(actor)
            or deps.user_has_permission(actor, PERM_LEAVE)):
        raise HTTPException(403, "Not authorized to decide this pick")
    await svc.finalize(db, pick, approved=payload.approve, actor=actor,
                       note=payload.note)
    await commit_or_409(db)
    return await _detail(db, pick_id)
