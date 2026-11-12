"""Open shifts (Roadmap v2 Phase 1B).

A scheduler posts an open shift (template + date, optional department /
location filter, N slots). Eligible employees claim it; a scheduler who can
publish for the claimant confirms (or the shift auto-confirms the first
claimant). Confirming writes a PUBLISHED roster cell.

  open --(last slot approved)--> filled
  open --cancel--> cancelled
  claim: pending -> approved | rejected | withdrawn
"""
from datetime import date as pydate, datetime, timedelta, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import and_, or_, select

from app.api import deps
from app.api.v1.endpoints.hr import log_audit
from app.api.v1.endpoints.roster_common import (
    check_window, commit_or_409, guard_conflicts, lock_row, names,
)
from app.models.employee import Employee, EmployeeStatus
from app.models.open_shift import (
    ClaimStatus, OpenShift, OpenShiftClaim, OpenShiftStatus,
)
from app.models.shift import ShiftTemplate
from app.models.user import User
from app.schemas.open_shift import (
    ClaimDecision, OpenShiftClaimRead, OpenShiftCreate, OpenShiftRead,
)
from app.services import open_shifts as os_svc
from app.services import roster as roster_svc

router = APIRouter()

RTYPE = os_svc.RTYPE
AVAILABLE_DAYS = 60


async def _read_many(
    db, shifts, viewer: User, full_claims: bool,
    warnings: Optional[List[str]] = None,
) -> List[OpenShiftRead]:
    ids = [s.id for s in shifts]
    claims = list((await db.execute(
        select(OpenShiftClaim).where(OpenShiftClaim.open_shift_id.in_(ids))
        .order_by(OpenShiftClaim.id)
    )).scalars().all()) if ids else []
    uids = {c.user_id for c in claims} | {
        s.created_by_id for s in shifts if s.created_by_id}
    nm = await names(db, uids)
    tpls = {t.id: t for t in (await db.execute(select(ShiftTemplate).where(
        ShiftTemplate.id.in_({s.shift_template_id for s in shifts})
    ))).scalars().all()} if shifts else {}
    by_shift: dict = {}
    for c in claims:
        by_shift.setdefault(c.open_shift_id, []).append(c)
    reasons: dict = {}
    visible: dict = {}
    if full_claims:
        # Non-admin, non-creator viewers only see claims of people they can
        # publish for (plus their own).
        admin = roster_svc.is_roster_admin(viewer)
        ok = None if admin else await roster_svc.publishable_subset(
            db, viewer, {c.user_id for c in claims})
        for s in shifts:
            cs = by_shift.get(s.id, [])
            if ok is not None and s.created_by_id != viewer.id:
                cs = [c for c in cs if c.user_id in ok or c.user_id == viewer.id]
            visible[s.id] = cs
        pairs = [(s, c.user_id) for s in shifts
                 if s.status == OpenShiftStatus.OPEN
                 for c in visible[s.id] if c.status == ClaimStatus.PENDING]
        m = await os_svc.eligibility_matrix(db, pairs, approver=viewer)
        for (sid, uid), why in m.items():
            reasons.setdefault(sid, {})[uid] = why
    out = []
    for s in shifts:
        mine = next((c for c in by_shift.get(s.id, [])
                     if c.user_id == viewer.id), None)
        shown = visible[s.id] if full_claims else ([mine] if mine else [])
        t = tpls.get(s.shift_template_id)
        out.append(OpenShiftRead(
            id=s.id, work_date=s.work_date,
            shift_template_id=s.shift_template_id,
            shift_name=t.name if t else None,
            shift_start=t.start_time.strftime("%H:%M") if t else None,
            shift_end=t.end_time.strftime("%H:%M") if t else None,
            department=s.department, location=s.location, slots=s.slots,
            filled=s.filled, note=s.note, status=s.status,
            auto_confirm=s.auto_confirm, created_by_id=s.created_by_id,
            created_by_name=nm.get(s.created_by_id),
            source_drop_id=s.source_drop_id, created_at=s.created_at,
            my_claim_id=mine.id if mine else None,
            my_claim_status=mine.status if mine else None,
            claims=[OpenShiftClaimRead(
                id=c.id, open_shift_id=c.open_shift_id, user_id=c.user_id,
                user_name=nm.get(c.user_id), status=c.status,
                decided_by_id=c.decided_by_id, decided_at=c.decided_at,
                created_at=c.created_at,
                eligibility_reason=(reasons.get(s.id) or {}).get(c.user_id),
            ) for c in shown],
            warnings=list(warnings or []),
        ))
    return out


async def _lock_shift(db, shift_id: int) -> OpenShift:
    s = await lock_row(
        db, select(OpenShift).where(OpenShift.id == shift_id),
        "Open shift changed concurrently; retry")
    if s is None:
        raise HTTPException(status_code=404, detail="Open shift not found")
    return s


async def _lock_claim(db, claim_id: int):
    """Lock the claim's open shift first (same order as claim/decide), then
    the claim itself. Returns (shift, claim)."""
    peek = (await db.execute(select(OpenShiftClaim.open_shift_id).where(
        OpenShiftClaim.id == claim_id))).scalar()
    if peek is None:
        raise HTTPException(status_code=404, detail="Claim not found")
    shift = await _lock_shift(db, peek)
    claim = await lock_row(
        db, select(OpenShiftClaim).where(OpenShiftClaim.id == claim_id),
        "Claim already decided")
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")
    return shift, claim


def _can_manage_shift(user: User, shift: OpenShift) -> bool:
    return roster_svc.is_roster_admin(user) or shift.created_by_id == user.id


# -------------------------------- create --------------------------------

@router.post("/open-shifts", response_model=OpenShiftRead)
@guard_conflicts
async def create_open_shift(
    *,
    db: deps.DBDep,
    request: Request,
    body: OpenShiftCreate,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    shift = await os_svc.create_open_shift(
        db, current_user, work_date=body.work_date,
        shift_template_id=body.shift_template_id, department=body.department,
        location=body.location, slots=body.slots, note=body.note,
        auto_confirm=body.auto_confirm)
    await commit_or_409(db)
    await db.refresh(shift)
    await log_audit(
        db, current_user.id, "roster.open_shift.create", RTYPE, str(shift.id),
        {"work_date": body.work_date.isoformat(),
         "shift_template_id": body.shift_template_id, "slots": body.slots},
        request)
    return (await _read_many(db, [shift], current_user, True))[0]


# -------------------------------- lists --------------------------------

@router.get("/open-shifts", response_model=List[OpenShiftRead])
async def list_open_shifts(
    db: deps.DBDep,
    start: Optional[pydate] = Query(None),
    end: Optional[pydate] = Query(None),
    status: Optional[str] = Query(None),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    start = start or os_svc.today()
    end = end or (start + timedelta(days=30))
    check_window(start, end)
    if status and status not in (
        OpenShiftStatus.OPEN, OpenShiftStatus.FILLED, OpenShiftStatus.CANCELLED
    ):
        raise HTTPException(status_code=400, detail="Invalid status filter")
    q = select(OpenShift).where(
        OpenShift.work_date >= start, OpenShift.work_date <= end
    ).order_by(OpenShift.work_date, OpenShift.id)
    if status:
        q = q.where(OpenShift.status == status)
    if not roster_svc.is_roster_admin(current_user):
        q = q.where(OpenShift.created_by_id == current_user.id)
    rows = (await db.execute(q.limit(500))).scalars().all()
    return await _read_many(db, rows, current_user, True)


@router.get("/open-shifts/available", response_model=List[OpenShiftRead])
async def available_open_shifts(
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Open shifts in the next 60 days the caller may claim, plus any the
    caller already has a pending claim on (so it can be withdrawn)."""
    today = os_svc.today()
    me = (await db.execute(
        select(Employee).join(User, User.id == Employee.user_id).where(
            Employee.user_id == current_user.id,
            Employee.status == EmployeeStatus.ACTIVE,
            User.is_active.is_(True)))).scalars().first()
    if me is None:
        return []
    pending = set((await db.execute(
        select(OpenShiftClaim.open_shift_id).where(
            OpenShiftClaim.user_id == current_user.id,
            OpenShiftClaim.status == ClaimStatus.PENDING))).scalars().all())
    # Department / location prefilter in SQL; the rules then run in one batch.
    fits = and_(
        or_(OpenShift.department.is_(None),
            OpenShift.department == me.department),
        or_(OpenShift.location.is_(None),
            OpenShift.location == (me.location or "")))
    shifts = (await db.execute(
        select(OpenShift).where(
            OpenShift.status == OpenShiftStatus.OPEN,
            OpenShift.work_date >= today,
            OpenShift.work_date <= today + timedelta(days=AVAILABLE_DAYS),
            or_(fits, OpenShift.id.in_(pending)) if pending else fits,
        ).order_by(OpenShift.work_date, OpenShift.id).limit(500)
    )).scalars().all()
    m = await os_svc.eligibility_matrix(
        db, [(s, current_user.id) for s in shifts])
    keep = [s for s in shifts
            if s.id in pending or m[(s.id, current_user.id)] is None]
    return await _read_many(db, keep, current_user, False)


# -------------------------------- claim --------------------------------

@router.post("/open-shifts/{shift_id}/claim", response_model=OpenShiftRead)
@guard_conflicts
async def claim_open_shift(
    *,
    db: deps.DBDep,
    request: Request,
    shift_id: int,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    shift = await _lock_shift(db, shift_id)
    if shift.status != OpenShiftStatus.OPEN:
        raise HTTPException(status_code=409, detail="Open shift is no longer open")
    reason = await os_svc.eligible_reason(db, shift, current_user.id)
    if reason:
        raise HTTPException(status_code=400, detail=reason)
    # Claims on this shift are serialized by the shift lock, so a locking
    # read of the existing claim is race-free.
    existing = await lock_row(
        db, select(OpenShiftClaim).where(
            OpenShiftClaim.open_shift_id == shift.id,
            OpenShiftClaim.user_id == current_user.id))
    if existing is not None and existing.status != ClaimStatus.WITHDRAWN:
        raise HTTPException(
            status_code=409, detail="You have already claimed this shift")
    if existing is not None:  # re-claim after withdrawing
        existing.status = ClaimStatus.PENDING
        existing.decided_by_id = None
        existing.decided_at = None
        existing.created_at = datetime.now(timezone.utc)
        claim = existing
    else:
        claim = OpenShiftClaim(
            open_shift_id=shift.id, user_id=current_user.id,
            status=ClaimStatus.PENDING)
        db.add(claim)
    await db.flush()
    warns: List[str] = []
    if shift.auto_confirm:
        warns = await os_svc.confirm_claim(
            db, shift, claim, shift.created_by_id)
    elif shift.created_by_id and shift.created_by_id != current_user.id:
        nm = await names(db, [current_user.id])
        await roster_svc.notify(
            db, shift.created_by_id, "Open shift claimed",
            f"{nm.get(current_user.id)} claimed the open shift on "
            f"{shift.work_date.isoformat()}", RTYPE, str(shift.id))
    await commit_or_409(db)
    await db.refresh(shift)
    await log_audit(
        db, current_user.id, "roster.open_shift.claim", RTYPE, str(shift.id),
        {"claim_id": claim.id, "auto_confirmed": bool(shift.auto_confirm)},
        request)
    return (await _read_many(
        db, [shift], current_user, False, warnings=warns))[0]


@router.post("/open-shifts/claims/{claim_id}/withdraw",
             response_model=OpenShiftRead)
@guard_conflicts
async def withdraw_claim(
    *,
    db: deps.DBDep,
    request: Request,
    claim_id: int,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    shift, claim = await _lock_claim(db, claim_id)
    if claim.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your claim")
    if claim.status != ClaimStatus.PENDING:
        raise HTTPException(
            status_code=409, detail="Only pending claims can be withdrawn")
    claim.status = ClaimStatus.WITHDRAWN
    claim.decided_at = datetime.now(timezone.utc)
    await commit_or_409(db, "Claim already decided")
    await db.refresh(shift)
    await log_audit(
        db, current_user.id, "roster.open_shift.withdraw", RTYPE,
        str(shift.id), {"claim_id": claim_id}, request)
    return (await _read_many(db, [shift], current_user, False))[0]


# ------------------------------- decision -------------------------------

@router.post("/open-shifts/claims/{claim_id}/decide",
             response_model=OpenShiftRead)
@guard_conflicts
async def decide_claim(
    *,
    db: deps.DBDep,
    request: Request,
    claim_id: int,
    body: ClaimDecision,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    shift, claim = await _lock_claim(db, claim_id)
    admin = roster_svc.is_roster_admin(current_user)
    if claim.user_id == current_user.id and not admin:
        raise HTTPException(
            status_code=403,
            detail="You cannot decide your own claim (separation of duties).")
    if not (admin or await roster_svc.can_publish_for(
            db, current_user, claim.user_id)):
        raise HTTPException(
            status_code=403, detail="This employee is outside your scope.")
    if claim.status != ClaimStatus.PENDING:
        raise HTTPException(status_code=409, detail="Claim already decided")
    warns: List[str] = []
    if body.action == "approve":
        warns = await os_svc.confirm_claim(
            db, shift, claim, current_user.id, approver=current_user)
    else:
        claim.status = ClaimStatus.REJECTED
        claim.decided_by_id = current_user.id
        claim.decided_at = datetime.now(timezone.utc)
        await roster_svc.notify(
            db, claim.user_id, "Open shift claim rejected",
            f"Your claim for the open shift on {shift.work_date.isoformat()} "
            f"was not approved", RTYPE, str(shift.id))
    await commit_or_409(db, "Claim already decided")
    await db.refresh(shift)
    await log_audit(
        db, current_user.id, "roster.open_shift.decide", RTYPE, str(shift.id),
        {"claim_id": claim_id, "action": body.action}, request)
    return (await _read_many(
        db, [shift], current_user, True, warnings=warns))[0]


# -------------------------------- cancel --------------------------------

@router.post("/open-shifts/{shift_id}/cancel", response_model=OpenShiftRead)
@guard_conflicts
async def cancel_open_shift(
    *,
    db: deps.DBDep,
    request: Request,
    shift_id: int,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    shift = await _lock_shift(db, shift_id)
    if not _can_manage_shift(current_user, shift):
        raise HTTPException(
            status_code=403, detail="Only the scheduler who posted it can cancel")
    if shift.status != OpenShiftStatus.OPEN:
        raise HTTPException(
            status_code=409, detail="Only open shifts can be cancelled")
    shift.status = OpenShiftStatus.CANCELLED
    await os_svc.reject_pending(
        db, shift, current_user.id,
        f"The open shift on {shift.work_date.isoformat()} was cancelled",
        title="Open shift cancelled")
    await commit_or_409(db, "Open shift changed concurrently; retry")
    await db.refresh(shift)
    await log_audit(
        db, current_user.id, "roster.open_shift.cancel", RTYPE, str(shift.id),
        {}, request)
    return (await _read_many(db, [shift], current_user, True))[0]
