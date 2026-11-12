"""Peer shift swaps (Roadmap v2 Phase 1B).

Flow: requester proposes -> counterparty accepts/declines -> a scheduler who
can approve changes for BOTH employees approves/rejects -> the two cells are
exchanged as PUBLISHED roster entries. Status machine:

  pending_peer --accept--> pending_approval --decide(approve)--> approved
       |  \\--decline--> declined             \\-decide(reject)--> rejected
       \\--cancel (requester)--> cancelled <--cancel-- pending_approval
"""
from datetime import date as pydate, datetime, timedelta, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import or_, select

from app.api import deps
from app.api.v1.endpoints.hr import log_audit
from app.api.v1.endpoints.roster_common import (
    commit_or_409, guard_conflicts, lock_row, names,
)
from app.models.employee import Employee, EmployeeStatus
from app.models.roster import RosterStatus
from app.models.shift import ShiftTemplate
from app.models.shift_swap import ShiftSwapRequest, SwapStatus
from app.models.user import User
from app.schemas.shift_swap import (
    SwapCandidate, SwapCellRead, SwapExchangedCell, SwapCreate, SwapDecision, SwapRead,
    SwapViolationRead,
)
from app.services import roster as roster_svc
from app.services import swaps as swap_svc
from app.services.effective_shift import effective_shifts_for_range

router = APIRouter()

RTYPE = "shift_swap"


def _today() -> pydate:
    return datetime.now(timezone.utc).date()


async def _read_many(
    db, rows, warnings: Optional[dict] = None, viol_names: Optional[dict] = None,
) -> List[SwapRead]:
    uids = {r.requester_id for r in rows} | {r.counterparty_id for r in rows}
    uids |= {r.decided_by_id for r in rows if r.decided_by_id}
    nm = await names(db, uids)
    tpl_ids = set()
    for r in rows:
        for side in ("a", "b"):
            for c in ((r.snapshot or {}).get(side) or {}).values():
                if c and c[0]:
                    tpl_ids.add(c[0])
    tpls = {}
    if tpl_ids:
        tpls = {t.id: t.name for t in (await db.execute(
            select(ShiftTemplate).where(ShiftTemplate.id.in_(tpl_ids))
        )).scalars().all()}

    def cell(r, side, d):
        c = (r.snapshot or {}).get(side, {}).get(d.isoformat())
        if not c:
            return None
        return SwapCellRead(
            shift_template_id=c[0], shift_name=tpls.get(c[0]),
            is_week_off=bool(c[1]))

    def read_cell(c):
        return SwapCellRead(
            shift_template_id=c[0], shift_name=tpls.get(c[0]),
            is_week_off=bool(c[1]))

    def exchanged(r):
        snap = r.snapshot or {}
        a, b = snap.get("a") or {}, snap.get("b") or {}
        res = []
        for iso in sorted(set(a) & set(b)):
            for uid, mine, theirs in (
                (r.requester_id, a[iso], b[iso]),
                (r.counterparty_id, b[iso], a[iso]),
            ):
                res.append(SwapExchangedCell(
                    user_id=uid, work_date=pydate.fromisoformat(iso),
                    before=read_cell(mine),
                    after=read_cell(swap_svc.written_cell(tuple(theirs)))))
        return res

    out = []
    for r in rows:
        out.append(SwapRead(
            id=r.id, requester_id=r.requester_id,
            requester_name=nm.get(r.requester_id),
            counterparty_id=r.counterparty_id,
            counterparty_name=nm.get(r.counterparty_id),
            requester_date=r.requester_date,
            counterparty_date=r.counterparty_date,
            reason=r.reason, status=r.status,
            requester_cell=cell(r, "a", r.requester_date),
            counterparty_cell=cell(r, "b", r.counterparty_date),
            peer_responded_at=r.peer_responded_at,
            decided_by_id=r.decided_by_id,
            decided_by_name=nm.get(r.decided_by_id),
            decided_at=r.decided_at, decision_note=r.decision_note,
            created_at=r.created_at, cells=exchanged(r),
            warnings=_viol_read((warnings or {}).get(r.id, []), nm),
        ))
    return out


def _viol_read(viols, nm) -> List[SwapViolationRead]:
    return [SwapViolationRead(
        user_id=v.user_id, employee_name=nm.get(v.user_id),
        work_date=v.work_date, rule=v.rule, message=v.message) for v in viols]


async def _read_one(db, r, warnings=None) -> SwapRead:
    return (await _read_many(db, [r], {r.id: warnings or []}))[0]


async def lock_row_ids(db, ids) -> None:
    from app.models.user import User as _U
    await lock_row_many(db, select(_U.id).where(_U.id.in_(ids)).order_by(_U.id))


async def lock_row_many(db, stmt) -> None:
    from sqlalchemy.exc import OperationalError
    from app.api.v1.endpoints.roster_common import _map_db_error
    try:
        await db.execute(stmt.with_for_update())
    except OperationalError as exc:
        mapped = await _map_db_error(db, exc, "Roster changed concurrently; retry")
        if mapped is None:
            raise
        raise mapped from exc


async def _lock_swap(db, swap_id: int) -> ShiftSwapRequest:
    s = await lock_row(
        db, select(ShiftSwapRequest).where(ShiftSwapRequest.id == swap_id),
        "Swap already decided")
    if s is None:
        raise HTTPException(status_code=404, detail="Swap request not found")
    return s


async def _cells(db, swap):
    dates = swap_svc.swap_dates(swap.requester_date, swap.counterparty_date)
    eff = await swap_svc.load_effective(
        db, swap.requester_id, swap.counterparty_id, dates[0], dates[-1])
    return (dates, swap_svc.cells_for(eff, swap.requester_id, dates),
            swap_svc.cells_for(eff, swap.counterparty_id, dates), eff)


async def _ensure_parties_active(db, swap) -> None:
    n = len((await db.execute(
        select(Employee.user_id).join(User, User.id == Employee.user_id).where(
            Employee.user_id.in_([swap.requester_id, swap.counterparty_id]),
            Employee.status == EmployeeStatus.ACTIVE,
            User.is_active.is_(True)))).all())
    if n != 2:
        raise HTTPException(
            status_code=400, detail="Both employees must be active")


async def _fire(db, uids, title, message, swap_id):
    await roster_svc.notify_many(db, [
        (u, title, message, RTYPE, str(swap_id)) for u in uids if u])


# ----------------------------- candidates -----------------------------

@router.get("/swaps/candidates", response_model=List[SwapCandidate])
async def swap_candidates(
    db: deps.DBDep,
    date: pydate = Query(...),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    today = _today()
    if date < today or date > today + timedelta(days=swap_svc.MAX_AHEAD_DAYS):
        raise HTTPException(
            status_code=400,
            detail=f"date must be within the next {swap_svc.MAX_AHEAD_DAYS} days")
    me = (await db.execute(select(Employee).where(
        Employee.user_id == current_user.id))).scalars().first()
    if me is None or not me.department:
        return []
    emps = (await db.execute(
        select(Employee.user_id, User.full_name, User.email)
        .join(User, User.id == Employee.user_id)
        .where(
            Employee.department == me.department,
            Employee.status == EmployeeStatus.ACTIVE,
            Employee.user_id.is_not(None),
            Employee.user_id != current_user.id,
            User.is_active.is_(True),
        ).order_by(User.full_name)
    )).all()
    eff = await effective_shifts_for_range(
        db, [e[0] for e in emps], date, date)
    out = []
    for uid, full, email in emps:
        es = eff[(uid, date)]
        out.append(SwapCandidate(
            user_id=uid, name=full or email,
            shift_template_id=es.shift.id if es.shift and not es.is_week_off else None,
            shift_name=es.shift.name if es.shift and not es.is_week_off else None,
            is_week_off=es.is_week_off))
    return out


# ------------------------------- create -------------------------------

@router.post("/swaps", response_model=SwapRead)
@guard_conflicts
async def create_swap(
    *,
    db: deps.DBDep,
    request: Request,
    body: SwapCreate,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    a, b = current_user.id, body.counterparty_id
    if a == b:
        raise HTTPException(
            status_code=400, detail="You cannot swap a shift with yourself")
    # Serialize concurrent creates for the same people: lock both user rows
    # (id order) before the duplicate check.
    await lock_row_ids(db, [a, b])
    me = (await db.execute(select(Employee.department).where(
        Employee.user_id == a))).first()
    cp = (await db.execute(
        select(Employee.department).join(User, User.id == Employee.user_id)
        .where(
            Employee.user_id == b, Employee.status == EmployeeStatus.ACTIVE,
            User.is_active.is_(True)))).first()
    if cp is None or me is None or not me[0] or cp[0] != me[0]:
        raise HTTPException(
            status_code=400,
            detail="Counterparty must be an active employee in your department")
    rd = body.requester_date
    cd = body.counterparty_date or rd
    swap_svc.validate_dates_open(rd, cd, _today())
    dates = swap_svc.swap_dates(rd, cd)
    eff = await swap_svc.load_effective(db, a, b, dates[0], dates[-1])
    mine = eff[(a, rd)]
    if not (mine.source == "roster" and mine.shift is not None
            and not mine.is_week_off):
        raise HTTPException(
            status_code=400,
            detail="You have no published shift on that date to hand over")
    a_cells = swap_svc.cells_for(eff, a, dates)
    b_cells = swap_svc.cells_for(eff, b, dates)
    if not swap_svc.changes_something(a_cells, b_cells, dates):
        raise HTTPException(
            status_code=400, detail="Both employees already have the same schedule")
    # No other open swap involving either party on any of these dates.
    open_rows = (await db.execute(
        select(ShiftSwapRequest).where(
            ShiftSwapRequest.status.in_(SwapStatus.OPEN),
            or_(ShiftSwapRequest.requester_id.in_([a, b]),
                ShiftSwapRequest.counterparty_id.in_([a, b])),
        ).with_for_update().execution_options(populate_existing=True)
    )).scalars().all()
    for o in open_rows:
        if {o.requester_date, o.counterparty_date} & set(dates):
            raise HTTPException(
                status_code=409,
                detail="A pending swap already involves one of these employees "
                       "on these dates")
    new_a, new_b = swap_svc.swapped_cells(a_cells, b_cells, dates)
    await swap_svc.check_leave_free(db, a, b, dates, new_a, new_b)
    swap = ShiftSwapRequest(
        requester_id=a, counterparty_id=b, requester_date=rd,
        counterparty_date=cd, reason=(body.reason or None),
        status=SwapStatus.PENDING_PEER,
        snapshot=swap_svc.make_snapshot(a_cells, b_cells),
    )
    db.add(swap)
    await db.flush()
    nm = await names(db, [a])
    await _fire(
        db, [b], "Shift swap request",
        f"{nm.get(a)} asks to swap shifts on {roster_svc.format_dates(dates)}",
        swap.id)
    await commit_or_409(db)
    await db.refresh(swap)
    await log_audit(
        db, current_user.id, "roster.swap.create", RTYPE, str(swap.id),
        {"counterparty_id": b, "dates": [d.isoformat() for d in dates]},
        request)
    return await _read_one(db, swap)


# -------------------------------- lists --------------------------------

@router.get("/swaps/my", response_model=List[SwapRead])
async def my_swaps(
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    rows = (await db.execute(
        select(ShiftSwapRequest).where(or_(
            ShiftSwapRequest.requester_id == current_user.id,
            ShiftSwapRequest.counterparty_id == current_user.id,
        )).order_by(ShiftSwapRequest.created_at.desc(), ShiftSwapRequest.id.desc())
        .limit(100)
    )).scalars().all()
    return await _read_many(db, rows)


@router.get("/swaps", response_model=List[SwapRead])
async def approver_queue(
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Swaps awaiting approval that the caller may decide (approve rights over
    BOTH employees; parties never see their own swap unless roster admin)."""
    admin = roster_svc.is_roster_admin(current_user)
    q = select(ShiftSwapRequest).where(
        ShiftSwapRequest.status == SwapStatus.PENDING_APPROVAL
    ).order_by(ShiftSwapRequest.created_at.desc(), ShiftSwapRequest.id.desc())
    if not admin:
        q = q.where(
            ShiftSwapRequest.requester_id != current_user.id,
            ShiftSwapRequest.counterparty_id != current_user.id)
    rows = (await db.execute(q.limit(500))).scalars().all()
    if not admin and rows:
        uids = {r.requester_id for r in rows} | {r.counterparty_id for r in rows}
        ok = await roster_svc.approvable_subset(db, current_user, uids)
        rows = [r for r in rows
                if r.requester_id in ok and r.counterparty_id in ok]
    return await _read_many(db, rows)


@router.get("/swaps/{swap_id}/check", response_model=List[SwapViolationRead])
async def check_swap(
    swap_id: int,
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Rule warnings (min rest, consecutive days/nights, weekly hours,
    availability) the swap would create. Advisory only."""
    swap = await db.get(ShiftSwapRequest, swap_id)
    if swap is None:
        raise HTTPException(status_code=404, detail="Swap request not found")
    parties = {swap.requester_id, swap.counterparty_id}
    if current_user.id not in parties:
        ok = await roster_svc.approvable_subset(db, current_user, parties)
        if ok != parties:
            raise HTTPException(
                status_code=403, detail="Not allowed to view this swap")
    if swap.status not in SwapStatus.OPEN:
        return []
    viols = await swap_svc.swap_warnings(db, swap)
    return _viol_read(viols, await names(db, parties))


# ----------------------------- peer response -----------------------------

@router.post("/swaps/{swap_id}/accept", response_model=SwapRead)
@guard_conflicts
async def accept_swap(
    *,
    db: deps.DBDep,
    request: Request,
    swap_id: int,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    swap = await _lock_swap(db, swap_id)
    if swap.counterparty_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="Only the counterparty can accept")
    if swap.status != SwapStatus.PENDING_PEER:
        raise HTTPException(status_code=409, detail="Swap is no longer awaiting your reply")
    d1, d2 = swap.requester_date, swap.counterparty_date
    await _ensure_parties_active(db, swap)
    if min(d1, d2) < _today():
        raise HTTPException(status_code=400, detail="A swap date is in the past")
    dates, a_cells, b_cells, _eff = await _cells(db, swap)
    if not swap_svc.snapshot_matches(swap.snapshot, a_cells, b_cells):
        raise HTTPException(
            status_code=409,
            detail="Schedule changed since the request was made")
    new_a, new_b = swap_svc.swapped_cells(a_cells, b_cells, dates)
    await swap_svc.check_leave_free(
        db, swap.requester_id, swap.counterparty_id, dates, new_a, new_b)
    swap.status = SwapStatus.PENDING_APPROVAL
    swap.peer_responded_at = datetime.now(timezone.utc)
    parties = {swap.requester_id, swap.counterparty_id}
    approvers = await roster_svc.schedule_approver_ids(db, parties)
    nm = await names(db, parties)
    await _fire(
        db, [swap.requester_id], "Shift swap accepted",
        f"{nm.get(swap.counterparty_id)} accepted your swap for "
        f"{roster_svc.format_dates(dates)}; awaiting approval", swap.id)
    await _fire(
        db, sorted(approvers), "Shift swap awaiting approval",
        f"{nm.get(swap.requester_id)} and {nm.get(swap.counterparty_id)} "
        f"agreed to swap shifts on {roster_svc.format_dates(dates)}", swap.id)
    await commit_or_409(db, "Swap already decided")
    await db.refresh(swap)
    await log_audit(
        db, current_user.id, "roster.swap.accept", RTYPE, str(swap.id), {},
        request)
    return await _read_one(db, swap)


@router.post("/swaps/{swap_id}/decline", response_model=SwapRead)
@guard_conflicts
async def decline_swap(
    *,
    db: deps.DBDep,
    request: Request,
    swap_id: int,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    swap = await _lock_swap(db, swap_id)
    if swap.counterparty_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="Only the counterparty can decline")
    if swap.status != SwapStatus.PENDING_PEER:
        raise HTTPException(status_code=409, detail="Swap is no longer awaiting your reply")
    swap.status = SwapStatus.DECLINED
    swap.peer_responded_at = datetime.now(timezone.utc)
    nm = await names(db, [current_user.id])
    await _fire(
        db, [swap.requester_id], "Shift swap declined",
        f"{nm.get(current_user.id)} declined your swap request", swap.id)
    await commit_or_409(db, "Swap already decided")
    await db.refresh(swap)
    await log_audit(
        db, current_user.id, "roster.swap.decline", RTYPE, str(swap.id), {},
        request)
    return await _read_one(db, swap)


@router.post("/swaps/{swap_id}/cancel", response_model=SwapRead)
@guard_conflicts
async def cancel_swap(
    *,
    db: deps.DBDep,
    request: Request,
    swap_id: int,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    swap = await _lock_swap(db, swap_id)
    if swap.requester_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your swap request")
    if swap.status not in SwapStatus.OPEN:
        raise HTTPException(
            status_code=409, detail="Only open swap requests can be cancelled")
    was_accepted = swap.status == SwapStatus.PENDING_APPROVAL
    swap.status = SwapStatus.CANCELLED
    if was_accepted:
        nm = await names(db, [current_user.id])
        await _fire(
            db, [swap.counterparty_id], "Shift swap cancelled",
            f"{nm.get(current_user.id)} cancelled the swap request", swap.id)
    await commit_or_409(db, "Swap already decided")
    await db.refresh(swap)
    await log_audit(
        db, current_user.id, "roster.swap.cancel", RTYPE, str(swap.id), {},
        request)
    return await _read_one(db, swap)


# ------------------------------- decision -------------------------------

@router.post("/swaps/{swap_id}/decide", response_model=SwapRead)
@guard_conflicts
async def decide_swap(
    *,
    db: deps.DBDep,
    request: Request,
    swap_id: int,
    body: SwapDecision,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    swap = await _lock_swap(db, swap_id)
    if swap.status != SwapStatus.PENDING_APPROVAL:
        raise HTTPException(status_code=409, detail="Swap is not awaiting approval")
    parties = {swap.requester_id, swap.counterparty_id}
    admin = roster_svc.is_roster_admin(current_user)
    if current_user.id in parties and not admin:
        raise HTTPException(
            status_code=403,
            detail="You cannot decide your own swap (separation of duties).")
    if (await roster_svc.approvable_subset(db, current_user, parties)) != parties:
        raise HTTPException(
            status_code=403,
            detail="Both employees must be within your approval scope.")
    warnings: list = []
    dates = swap_svc.swap_dates(swap.requester_date, swap.counterparty_date)
    nm = await names(db, parties)
    if body.action == "approve":
        await _ensure_parties_active(db, swap)
        if dates[0] < _today():
            raise HTTPException(
                status_code=400, detail="A swap date is in the past")
        dates, a_cells, b_cells, _eff = await _cells(db, swap)
        if not swap_svc.snapshot_matches(swap.snapshot, a_cells, b_cells):
            raise HTTPException(
                status_code=409,
                detail="Schedule changed since the request was made")
        new_a, new_b = swap_svc.swapped_cells(a_cells, b_cells, dates)
        await swap_svc.check_leave_free(
            db, swap.requester_id, swap.counterparty_id, dates, new_a, new_b)
        warnings = await swap_svc.swap_warnings(db, swap)
        await swap_svc.supersede_change_requests(
            db, swap, current_user.id,
            swap_svc.written_keys(swap, a_cells, b_cells))
        changed = await swap_svc.apply_swap(
            db, swap, current_user.id, a_cells, b_cells)
        await roster_svc.notify_schedule_changed(db, changed)
        swap.status = SwapStatus.APPROVED
        await _fire(
            db, sorted(parties), "Shift swap approved",
            f"Your shift swap on {roster_svc.format_dates(dates)} was approved",
            swap.id)
    else:
        swap.status = SwapStatus.REJECTED
        await _fire(
            db, sorted(parties), "Shift swap rejected",
            f"Your shift swap on {roster_svc.format_dates(dates)} was rejected"
            + (f": {body.note}" if body.note else ""), swap.id)
    swap.decided_by_id = current_user.id
    swap.decided_at = datetime.now(timezone.utc)
    swap.decision_note = body.note
    await commit_or_409(db, "Swap already decided")
    await db.refresh(swap)
    await log_audit(
        db, current_user.id, "roster.swap.decide", RTYPE, str(swap.id),
        {"action": body.action}, request)
    return await _read_one(db, swap, warnings)
