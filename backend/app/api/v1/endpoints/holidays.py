"""Employee optional-holiday picks (Phase 6A Task 6). Mounted at /holidays,
NOT attendance-gated. Lock order: chain instance -> pick row. Writes: lock ->
service -> commit_or_409 once."""
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.api import deps
from app.api.v1.endpoints.roster_common import (
    guard_conflicts, plain_actor, reload_user, retry_on_lock,
)
from app.models.approval_chain import ChainEntityType, ChainedApprovalInstance
from app.models.hr import HolidayCalendar
from app.models.optional_holiday import OptionalHolidayPick, PickStatus
from app.models.user import User
from app.services import chain_routing
from app.services import holidays as holidays_svc
from app.services import optional_holidays as svc
from app.services import roster as roster_svc
from app.services.org_time import local_today
from app.services.self_approval import guard_self_approval

router = APIRouter()
PERM_HR = "hr employee write"
PERM_HR_READ = "hr employee read"


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


def _is_privileged(user: User) -> bool:
    """Org-wide deciders: 'hr employee write' holders (superusers hold every
    permission). A 'leave approve' holder is only a manager: their direct
    reports."""
    return _is_hr(user)


def _can_decide(viewer: User, privileged: bool, p: OptionalHolidayPick,
                owner_manager_id: Optional[int], routed_via: str) -> bool:
    """Mirrors decide_pick: pending, direct path, never one's own pick, and
    the viewer is the owner's manager or privileged."""
    return (p.status == PickStatus.PENDING and routed_via == "direct"
            and p.user_id != viewer.id
            and (privileged or owner_manager_id == viewer.id))


def _pick_out(p: OptionalHolidayPick, hol: Optional[HolidayCalendar],
              name: Optional[str] = None, routed_via: str = "direct",
              can_decide: bool = False) -> dict:
    return {
        "can_decide": can_decide,
        "id": p.id, "status": p.status, "year": p.year,
        "routed_via": routed_via,
        "holiday": ({"id": hol.id, "name": hol.name, "date": _iso(hol.date),
                     "location": hol.location} if hol else None),
        "user_id": p.user_id, "user_name": name, "reason": p.reason,
        "decision_note": p.decision_note,
        "created_at": _iso(p.created_at), "decided_at": _iso(p.decided_at),
    }


async def _chain_instance_id(db, pick_id: int) -> Optional[int]:
    return await chain_routing.chain_instance_id(
        db, ChainEntityType.OPTIONAL_HOLIDAY, pick_id)


async def _detail(db, pid: int, viewer: Optional[User] = None) -> dict:
    db.expire_all()
    p = (await db.execute(select(OptionalHolidayPick).where(
        OptionalHolidayPick.id == pid)
        .execution_options(populate_existing=True))).scalars().one()
    hol = await db.get(HolidayCalendar, p.holiday_id)
    via = "chain" if await _chain_instance_id(db, p.id) else "direct"
    cd = False
    if viewer is not None:
        mgr = (await db.execute(select(User.manager_id).where(
            User.id == p.user_id))).scalar_one_or_none()
        cd = _can_decide(viewer, _is_privileged(viewer), p, mgr, via)
    return _pick_out(p, hol, None, via, cd)


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
    # Latest pick per holiday in ANY status (so a rejection stays visible);
    # quota counts PENDING+APPROVED only. An active pick is always the latest
    # (create_pick refuses a duplicate while one is active).
    picks = {p.holiday_id: p for p in (await db.execute(
        select(OptionalHolidayPick).where(
            OptionalHolidayPick.user_id == current_user.id,
            OptionalHolidayPick.year == year)
        .order_by(OptionalHolidayPick.id))).scalars().all()}
    q = await svc.quota(db)
    out = []
    for h in hols:
        # keep holidays with an active pick even if the location no longer
        # applies, so `used` matches the list
        if h.id not in picks and not holidays_svc.applies(h.location, loc):
            continue
        p = picks.get(h.id) if h.is_optional else None
        out.append({
            "id": h.id, "name": h.name, "date": _iso(h.date),
            "location": h.location, "is_optional": bool(h.is_optional),
            "pick": ({"id": p.id, "status": p.status,
                      "decision_note": p.decision_note} if p else None)})
    n = sum(1 for p in picks.values() if p.status in PickStatus.ACTIVE)
    return {"quota": q, "used": n, "remaining": max(q - n, 0),
            "year": year, "holidays": out}


@router.post("/picks", status_code=201)
@guard_conflicts
async def create_pick(
    payload: PickIn, db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    uid, uname = current_user.id, current_user.full_name or current_user.email
    reload = reload_user(db, current_user)

    async def body() -> int:
        # Fresh transaction: take the user-row lock BEFORE any consistent
        # read so the user-scoped quota/duplicate read below sees committed
        # state (no locking of other users' pick rows).
        await db.commit()
        await db.execute(select(User.id).where(User.id == uid)
                         .with_for_update())
        await reload()
        pick = await svc.create_pick(
            db, user=current_user, holiday_id=payload.holiday_id,
            reason=payload.reason)
        hol = await svc.holiday_of(db, pick)
        async def notify_direct(ids) -> None:
            await roster_svc.notify_many(db, [(
                u, "Optional holiday request",
                f"{uname} picked optional holiday {hol.name} "
                f"({hol.date.isoformat()}).",
                svc.RT, str(pick.id), "optional_holiday_submitted")
                for u in ids])

        await chain_routing.route_submission(
            db, entity_type=ChainEntityType.OPTIONAL_HOLIDAY,
            entity_id=pick.id, submitter=current_user,
            context={"holiday": hol.name},
            audit=lambda via: svc.audit_create(db, uid, pick, via),
            notify_direct=notify_direct)
        return pick.id

    pid = await retry_on_lock(db, body, commit=True)
    return await _detail(db, pid, current_user)


@router.post("/picks/{pick_id}/cancel")
@guard_conflicts
async def cancel_pick(
    pick_id: int, db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    hr = _is_hr(current_user)
    aid = current_user.id
    actor = plain_actor(current_user)

    async def body() -> int:
        owner = (await db.execute(select(OptionalHolidayPick.user_id).where(
            OptionalHolidayPick.id == pick_id))).scalar_one_or_none()
        if owner is None or (owner != aid and not hr):
            raise HTTPException(404, "Pick not found")
        iid = await _chain_instance_id(db, pick_id)
        inst = None
        if iid:  # lock order: instance -> pick (a retry redoes both)
            inst = (await db.execute(
                select(ChainedApprovalInstance).where(
                    ChainedApprovalInstance.id == iid)
                .with_for_update().execution_options(populate_existing=True)
            )).scalars().first()
        pick = (await db.execute(
            select(OptionalHolidayPick).where(
                OptionalHolidayPick.id == pick_id)
            .with_for_update().execution_options(populate_existing=True)
        )).scalars().first()
        if pick is None:
            raise HTTPException(404, "Pick not found")
        await svc.cancel(db, pick, actor=actor, is_hr=hr, inst=inst)
        return pick_id

    await retry_on_lock(db, body, commit=True)
    return await _detail(db, pick_id, current_user)


@router.get("/picks")
async def list_picks(
    db: deps.DBDep, status: Optional[str] = None,
    year: Optional[int] = Query(None, ge=2000, le=2100),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    q = (select(OptionalHolidayPick, HolidayCalendar, User.full_name,
                User.manager_id)
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
    chained = set((await db.execute(
        select(ChainedApprovalInstance.entity_id).where(
            ChainedApprovalInstance.entity_type
            == ChainEntityType.OPTIONAL_HOLIDAY,
            ChainedApprovalInstance.entity_id.in_([r[0].id for r in rows]))
    )).scalars().all()) if rows else set()
    priv = _is_privileged(current_user)
    out = []
    for p, h, n, mgr in rows:
        via = "chain" if p.id in chained else "direct"
        out.append(_pick_out(p, h, n, via,
                             _can_decide(current_user, priv, p, mgr, via)))
    return out


@router.post("/picks/{pick_id}/decide")
@guard_conflicts
async def decide_pick(
    pick_id: int, payload: DecideIn, db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    aid = current_user.id
    actor = plain_actor(current_user)
    privileged = _is_privileged(current_user)

    async def body() -> int:
        pick = (await db.execute(
            select(OptionalHolidayPick).where(
                OptionalHolidayPick.id == pick_id)
            .with_for_update().execution_options(populate_existing=True)
        )).scalars().first()
        if pick is None:
            raise HTTPException(404, "Pick not found")
        if await _chain_instance_id(db, pick.id):
            raise HTTPException(409, "decide via approvals")
        guard_self_approval(aid, pick.user_id)
        mgr = (await db.execute(select(User.manager_id).where(
            User.id == pick.user_id))).scalar_one_or_none()
        if not (mgr == aid or privileged):
            raise HTTPException(403, "Not authorized to decide this pick")
        await svc.finalize(db, pick, approved=payload.approve, actor=actor,
                           note=payload.note)
        return pick_id

    await retry_on_lock(db, body, commit=True)
    return await _detail(db, pick_id, current_user)
