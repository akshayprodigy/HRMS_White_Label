"""Out-of-office approval delegation endpoints (Task 6).

Mounted at prefix "" : /me/approval-delegations (own) and
/approval-delegations (HR / admin: everyone's).

Rules: a delegate sees and may act on pending steps whose named approver is
the delegator (legacy ApprovalStep.approver_id, chain approver_user_id, HR
leave inbox) while the delegation is live. Delegations are direct only
(A->B, B->C does not let C act for A). Separation of duties still applies to
the delegate (cannot approve their own request).
"""
from datetime import date
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import or_, select

from app.api import deps
from app.api.v1.endpoints.approval_chains import _is_hr_or_admin
from app.models.approver_delegation import ApproverDelegation
from app.models.user import User
from app.services.approver_delegation import (
    active_delegators, today_utc, user_names,
)

router = APIRouter()


class DelegationIn(BaseModel):
    delegate_id: int
    starts_on: Optional[date] = None
    ends_on: Optional[date] = None
    only_when_on_leave: bool = False
    note: Optional[str] = Field(None, max_length=255)


def _dict(d: ApproverDelegation, names: dict, live: set) -> dict:
    today = today_utc()
    revoked = d.revoked_at is not None
    expired = d.ends_on is not None and d.ends_on < today
    return {
        "id": d.id, "user_id": d.user_id,
        "user_name": names.get(d.user_id),
        "delegate_id": d.delegate_id,
        "delegate_name": names.get(d.delegate_id),
        "starts_on": d.starts_on, "ends_on": d.ends_on,
        "only_when_on_leave": d.only_when_on_leave, "note": d.note,
        "created_at": d.created_at, "revoked_at": d.revoked_at,
        "status": ("revoked" if revoked else "expired" if expired
                   else "active" if d.id in live
                   else "scheduled" if d.starts_on > today
                   else "waiting_for_leave" if d.only_when_on_leave
                   else "inactive"),
    }


async def _render(db, rows: List[ApproverDelegation]) -> list:
    names = await user_names(db, [x for r in rows
                                  for x in (r.user_id, r.delegate_id)])
    live: set = set()
    for did in {r.delegate_id for r in rows}:
        live |= {d.id for d in (await active_delegators(db, did)).values()}
    return [_dict(r, names, live) for r in rows]


@router.get("/me/approval-delegations")
async def my_delegations(
    db: deps.DBDep, current_user: User = Depends(deps.get_current_user),
) -> Any:
    mine = (await db.execute(
        select(ApproverDelegation).where(
            ApproverDelegation.user_id == current_user.id,
            ApproverDelegation.revoked_at.is_(None))
        .order_by(ApproverDelegation.id.desc()))).scalars().all()
    to_me = (await db.execute(
        select(ApproverDelegation).where(
            ApproverDelegation.delegate_id == current_user.id,
            ApproverDelegation.revoked_at.is_(None))
        .order_by(ApproverDelegation.id.desc()))).scalars().all()
    return {"mine": await _render(db, list(mine)),
            "delegated_to_me": await _render(db, list(to_me))}


@router.get("/me/approval-delegations/candidates")
async def delegate_candidates(
    db: deps.DBDep, q: str = "",
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Active colleagues to pick as a delegate (name/email search, max 20)."""
    stmt = select(User.id, User.full_name, User.email).where(
        User.is_active.is_(True), User.id != current_user.id)
    q = q.strip()
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(User.full_name.ilike(like),
                              User.email.ilike(like)))
    rows = (await db.execute(
        stmt.order_by(User.full_name, User.id).limit(20))).all()
    return [{"id": r[0], "name": r[1] or r[2], "email": r[2]} for r in rows]


@router.post("/me/approval-delegations", status_code=201)
async def create_delegation(
    payload: DelegationIn, db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    if payload.delegate_id == current_user.id:
        raise HTTPException(400, "You cannot delegate to yourself")
    delegate = await db.get(User, payload.delegate_id)
    if delegate is None or not delegate.is_active:
        raise HTTPException(400, "Delegate not found or inactive")
    starts = payload.starts_on or today_utc()
    if payload.ends_on and payload.ends_on < starts:
        raise HTTPException(400, "End date is before the start date")
    far = date.max
    for ex in (await db.execute(select(ApproverDelegation).where(
            ApproverDelegation.user_id == current_user.id,
            ApproverDelegation.delegate_id == delegate.id,
            ApproverDelegation.revoked_at.is_(None)))).scalars().all():
        if ex.starts_on <= (payload.ends_on or far) and \
                starts <= (ex.ends_on or far):
            raise HTTPException(
                409, "You already have a delegation to this person that "
                     "overlaps these dates")
    d = ApproverDelegation(
        user_id=current_user.id, delegate_id=delegate.id, starts_on=starts,
        ends_on=payload.ends_on,
        only_when_on_leave=payload.only_when_on_leave,
        note=(payload.note or None))
    db.add(d)
    await db.flush()
    from app.services.notifications_delivery import notify
    who = current_user.full_name or current_user.email
    try:
        async with db.begin_nested():
            await notify(
                db, user_id=delegate.id, event_type="approval_delegated",
                title=f"{who} delegated approvals to you",
                message=(f"{who} is out of office from {starts}"
                         + (f" to {payload.ends_on}" if payload.ends_on
                            else "")
                         + ". Their pending approvals will appear in your "
                           "inbox marked 'acting for'."),
                resource_type="approver_delegation", resource_id=str(d.id))
    except Exception:  # pragma: no cover
        pass
    await db.commit()
    return (await _render(db, [d]))[0]


@router.delete("/me/approval-delegations/{delegation_id}")
async def revoke_delegation(
    delegation_id: int, db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    from datetime import datetime, timezone
    d = await db.get(ApproverDelegation, delegation_id)
    if d is None or d.user_id != current_user.id:
        raise HTTPException(404, "Delegation not found")
    if d.revoked_at is None:
        d.revoked_at = datetime.now(timezone.utc)
        await db.commit()
    return (await _render(db, [d]))[0]


@router.get("/approval-delegations")
async def all_delegations(
    db: deps.DBDep, include_revoked: bool = False,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """HR / admin: every delegation."""
    if not _is_hr_or_admin(current_user):
        raise HTTPException(403, "HR access required")
    q = select(ApproverDelegation).order_by(ApproverDelegation.id.desc())
    if not include_revoked:
        q = q.where(ApproverDelegation.revoked_at.is_(None))
    return await _render(db, list((await db.execute(q)).scalars().all()))
