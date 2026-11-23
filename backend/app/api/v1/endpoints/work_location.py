"""On-duty / client-visit / WFH requests (Phase 6A Task 7). Mounted at
/work-location-requests, NOT attendance-gated. Lock order: chain instance ->
request row. Writes: lock -> service -> commit once."""
from datetime import date
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.api import deps
from app.api.v1.endpoints.roster_common import (
    guard_conflicts, plain_actor, reload_user, retry_on_lock,
)
from app.models.approval_chain import ChainEntityType, ChainedApprovalInstance
from app.models.user import User
from app.models.work_location import (
    WorkLocationKind, WorkLocationRequest, WorkLocationStatus,
)
from app.services import chain_routing
from app.services import roster as roster_svc
from app.services import work_location as svc
from app.services.self_approval import guard_self_approval

router = APIRouter()
PERM_HR = "hr employee write"
PERM_HR_READ = "hr employee read"
PERM_LEAVE = "leave approve"
_STATUSES = (WorkLocationStatus.PENDING, WorkLocationStatus.APPROVED,
             WorkLocationStatus.REJECTED, WorkLocationStatus.CANCELLED)


class RequestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str
    start_date: date
    end_date: date
    day_portion: str = "full"
    place: Optional[str] = Field(default=None, max_length=200)
    purpose: str = Field(max_length=1000)


class DecideIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approve: bool
    note: Optional[str] = Field(default=None, max_length=500)


def _iso(d) -> Optional[str]:
    return d.isoformat() if d else None


def _is_hr(user: User) -> bool:
    return deps.user_has_permission(user, PERM_HR)


def _out(r: WorkLocationRequest, name: Optional[str] = None,
         routed_via: str = "direct") -> dict:
    return {
        "id": r.id, "user_id": r.user_id, "user_name": name,
        "kind": r.kind, "start_date": _iso(r.start_date),
        "end_date": _iso(r.end_date), "day_portion": r.day_portion,
        "place": r.place, "purpose": r.purpose, "status": r.status,
        "routed_via": routed_via, "summary": svc.req_summary(r),
        "decided_by_id": r.decided_by_id, "decision_note": r.decision_note,
        "created_at": _iso(r.created_at), "decided_at": _iso(r.decided_at),
    }


async def _chained_ids(db, ids) -> set:
    return await chain_routing.chained_ids(
        db, ChainEntityType.WORK_LOCATION, ids)


async def _chain_instance_id(db, rid: int) -> Optional[int]:
    return await chain_routing.chain_instance_id(
        db, ChainEntityType.WORK_LOCATION, rid)


async def _detail(db, rid: int) -> dict:
    db.expire_all()
    r = (await db.execute(select(WorkLocationRequest).where(
        WorkLocationRequest.id == rid)
        .execution_options(populate_existing=True))).scalars().one()
    name = (await db.execute(select(User.full_name).where(
        User.id == r.user_id))).scalar_one_or_none()
    return _out(r, name, "chain" if await _chain_instance_id(db, rid)
                else "direct")


def _check_status(status: Optional[str]) -> None:
    if status and status not in _STATUSES:
        raise HTTPException(422, f"Unknown status: {status}")


@router.post("", status_code=201)
@guard_conflicts
async def create_request(
    payload: RequestIn, db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    uid, uname = current_user.id, current_user.full_name or current_user.email
    reload = reload_user(db, current_user)

    async def body() -> int:
        # Fresh transaction: user-row lock first, then ONE user-scoped read.
        await db.commit()
        await db.execute(select(User.id).where(User.id == uid)
                         .with_for_update())
        await reload()
        req = await svc.create(
            db, user=current_user, kind=payload.kind,
            start_date=payload.start_date, end_date=payload.end_date,
            day_portion=payload.day_portion, place=payload.place,
            purpose=payload.purpose)
        async def notify_direct(ids) -> None:
            await roster_svc.notify_many(db, [(
                u, "Work-location request",
                f"{uname} requested {svc.req_summary(req)}.",
                svc.RT, str(req.id), "work_location_submitted")
                for u in ids])

        await chain_routing.route_submission(
            db, entity_type=ChainEntityType.WORK_LOCATION, entity_id=req.id,
            submitter=current_user, context={"kind": req.kind},
            audit=lambda via: svc.audit_create(db, uid, req, via),
            notify_direct=notify_direct)
        return req.id

    rid = await retry_on_lock(db, body, commit=True)
    return await _detail(db, rid)


@router.get("/my")
async def my_requests(
    db: deps.DBDep, status: Optional[str] = None,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    _check_status(status)
    q = select(WorkLocationRequest).where(
        WorkLocationRequest.user_id == current_user.id)
    if status:
        q = q.where(WorkLocationRequest.status == status)
    rows = (await db.execute(q.order_by(WorkLocationRequest.id.desc())
                             )).scalars().all()
    chained = await _chained_ids(db, [r.id for r in rows])
    return [_out(r, current_user.full_name,
                 "chain" if r.id in chained else "direct") for r in rows]


@router.post("/{request_id}/cancel")
@guard_conflicts
async def cancel_request(
    request_id: int, db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    hr = _is_hr(current_user)
    aid = current_user.id
    actor = plain_actor(current_user)

    async def body() -> int:
        owner = (await db.execute(select(WorkLocationRequest.user_id).where(
            WorkLocationRequest.id == request_id))).scalar_one_or_none()
        if owner is None or (owner != aid and not hr):
            raise HTTPException(404, "Request not found")
        iid = await _chain_instance_id(db, request_id)
        inst = None
        if iid:  # lock order: instance -> request (a retry redoes both)
            inst = (await db.execute(
                select(ChainedApprovalInstance).where(
                    ChainedApprovalInstance.id == iid)
                .with_for_update().execution_options(populate_existing=True)
            )).scalars().first()
        req = (await db.execute(
            select(WorkLocationRequest).where(
                WorkLocationRequest.id == request_id)
            .with_for_update().execution_options(populate_existing=True)
        )).scalars().first()
        if req is None:
            raise HTTPException(404, "Request not found")
        await svc.cancel(db, req, actor=actor, is_hr=hr, inst=inst)
        return request_id

    await retry_on_lock(db, body, commit=True)
    return await _detail(db, request_id)


@router.get("")
async def list_requests(
    db: deps.DBDep, status: Optional[str] = None, kind: Optional[str] = None,
    from_: Optional[date] = Query(None, alias="from"),
    to: Optional[date] = None, user_id: Optional[int] = None,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    q = (select(WorkLocationRequest, User.full_name)
         .join(User, User.id == WorkLocationRequest.user_id))
    if not (_is_hr(current_user)
            or deps.user_has_permission(current_user, PERM_HR_READ)
            or deps.user_has_permission(current_user, PERM_LEAVE)
            or current_user.is_superuser):
        has_reports = (await db.execute(select(User.id).where(
            User.manager_id == current_user.id).limit(1))).first()
        if not has_reports:
            raise HTTPException(403, "Not allowed")
        q = q.where(User.manager_id == current_user.id)
    _check_status(status)
    if status:
        q = q.where(WorkLocationRequest.status == status)
    if kind:
        if kind not in WorkLocationKind.ALL:
            raise HTTPException(422, f"Unknown kind: {kind}")
        q = q.where(WorkLocationRequest.kind == kind)
    if from_:
        q = q.where(WorkLocationRequest.end_date >= from_)
    if to:
        q = q.where(WorkLocationRequest.start_date <= to)
    if user_id:
        q = q.where(WorkLocationRequest.user_id == user_id)
    rows = (await db.execute(q.order_by(WorkLocationRequest.id.desc()))).all()
    chained = await _chained_ids(db, [r.id for r, _ in rows])
    return [_out(r, n, "chain" if r.id in chained else "direct")
            for r, n in rows]


@router.post("/{request_id}/decide")
@guard_conflicts
async def decide_request(
    request_id: int, payload: DecideIn, db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    aid = current_user.id
    actor = plain_actor(current_user)
    privileged = (_is_hr(current_user) or current_user.is_superuser
                  or deps.user_has_permission(current_user, PERM_LEAVE))

    async def body() -> int:
        req = (await db.execute(
            select(WorkLocationRequest).where(
                WorkLocationRequest.id == request_id)
            .with_for_update().execution_options(populate_existing=True)
        )).scalars().first()
        if req is None:
            raise HTTPException(404, "Request not found")
        if await _chain_instance_id(db, req.id):
            raise HTTPException(409, "decide via approvals")
        guard_self_approval(aid, req.user_id)
        mgr = (await db.execute(select(User.manager_id).where(
            User.id == req.user_id))).scalar_one_or_none()
        if not (mgr == aid or privileged):
            raise HTTPException(403, "Not authorized to decide this request")
        await svc.finalize(db, req, approved=payload.approve, actor=actor,
                           note=payload.note)
        return request_id

    await retry_on_lock(db, body, commit=True)
    return await _detail(db, request_id)
