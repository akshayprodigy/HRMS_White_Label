"""Employee asset requests (Roadmap v2 Phase 5, Task 6). Mounted at
/asset-requests, NOT attendance-gated.

Employee routes need only an authenticated user with an Employee row; manager
routes need 'asset manage'. Lock order everywhere: request row -> asset row.
Writes: lock -> service -> commit_or_409 once; audit rows via db.add (never
hr.log_audit, it commits)."""
from datetime import date, datetime, timezone
from typing import Any, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import aliased, selectinload

from app.api import deps
from app.api.v1.endpoints.approval_chains import instantiate_for_entity
from app.api.v1.endpoints.hr import _get_my_employee_or_404
from app.api.v1.endpoints.roster_common import commit_or_409, guard_conflicts
from app.models.approval_chain import (
    ApprovalChain, ChainEntityType, ChainedApprovalInstance,
    ChainedApprovalStatus, StepInstanceStatus,
)
from app.models.asset import (
    Asset, AssetCategory, AssetRequest, AssetRequestStatus,
)
from app.models.audit import AuditLog
from app.models.employee import Employee
from app.models.user import User
from app.services import assets as svc
from app.services import roster as roster_svc

PERM_ASSET = "asset manage"
router = APIRouter()
_MGR = [Depends(deps.check_permissions([PERM_ASSET]))]  # manager routes only

OPEN = (AssetRequestStatus.PENDING, AssetRequestStatus.APPROVED)


def _now():
    return datetime.now(timezone.utc)


def _iso(d) -> Optional[str]:
    return d.isoformat() if d else None


# ── schemas ──────────────────────────────────────────────────────────────
class RequestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category_id: int
    reason: str = Field(max_length=1000)
    needed_by: Optional[date] = None

    @field_validator("reason")
    @classmethod
    def _reason(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 5:
            raise ValueError("reason must be at least 5 characters")
        return v

    @field_validator("needed_by")
    @classmethod
    def _needed(cls, v):
        if v is not None and v < date.today():
            raise ValueError("needed_by cannot be in the past")
        return v


class DecideIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["approve", "reject"]
    note: Optional[str] = Field(default=None, max_length=500)


class FulfilIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset_id: int
    issued_date: Optional[date] = None
    condition: Optional[str] = Field(default=None, max_length=50)
    allow_other_category: bool = False


# ── helpers ──────────────────────────────────────────────────────────────
def _out(r: AssetRequest, cat: AssetCategory, asset: Optional[Asset]) -> dict:
    return {
        "id": r.id, "status": r.status,
        "category": {"id": cat.id, "name": cat.name},
        "reason": r.reason, "needed_by": _iso(r.needed_by),
        "routed_via": "chain" if r.approval_instance_id else "direct",
        "approval_instance_id": r.approval_instance_id,
        "fulfilled_asset": ({"id": asset.id, "asset_tag": asset.asset_tag,
                             "name": asset.name} if asset else None),
        "decision_note": r.decision_note,
        "created_at": _iso(r.created_at), "decided_at": _iso(r.decided_at),
    }


async def _detail(db, rid: int) -> dict:
    db.expire_all()
    r = (await db.execute(select(AssetRequest).where(AssetRequest.id == rid)
                          .execution_options(populate_existing=True))
         ).scalars().first()
    cat = await db.get(AssetCategory, r.category_id)
    asset = (await db.get(Asset, r.fulfilled_asset_id)
             if r.fulfilled_asset_id else None)
    return _out(r, cat, asset)


async def _lock_request(db, rid: int, *, employee_id: Optional[int] = None
                        ) -> AssetRequest:
    q = select(AssetRequest).where(AssetRequest.id == rid)
    if employee_id is not None:
        q = q.where(AssetRequest.employee_id == employee_id)
    r = (await db.execute(q.with_for_update()
                          .execution_options(populate_existing=True))
         ).scalars().first()
    if r is None:
        raise HTTPException(404, "Asset request not found")
    return r


def _audit(db, actor, action: str, r: AssetRequest, details: dict) -> None:
    db.add(AuditLog(user_id=actor.id, action=action,
                    resource_type="asset_request", resource_id=str(r.id),
                    details=details))


async def _notify_managers(db, r: AssetRequest, title, msg, event,
                           exclude: Optional[int] = None) -> None:
    uids = [u for u in await svc.asset_manager_user_ids(db) if u != exclude]
    await roster_svc.notify_many(db, [
        (u, title, msg, "asset_request", str(r.id), event) for u in uids])


async def notify_managers_ready(db, r: AssetRequest) -> None:
    """Used by the approval-chain finaliser: request approved, ready to fulfil."""
    await _notify_managers(
        db, r, "Asset request ready to fulfil",
        f"Asset request #{r.id} was approved and is ready to fulfil.",
        "asset_request_approved")


async def _employee_user_id(db, employee_id: int) -> Optional[int]:
    return (await db.execute(select(Employee.user_id).where(
        Employee.id == employee_id))).scalar_one_or_none()


# ── employee routes ──────────────────────────────────────────────────────
@router.post("")
@guard_conflicts
async def create_request(
    payload: RequestIn, db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    emp = await _get_my_employee_or_404(db, current_user)
    # Serialise this employee's submissions so the duplicate check is race-free.
    await db.execute(select(Employee.id).where(Employee.id == emp.id)
                     .with_for_update())
    cat = await db.get(AssetCategory, payload.category_id)
    if cat is None or not cat.is_active:
        raise HTTPException(422, "Unknown or inactive asset category")
    dup = (await db.execute(select(AssetRequest.id).where(
        AssetRequest.employee_id == emp.id,
        AssetRequest.category_id == cat.id,
        AssetRequest.status.in_(OPEN)).limit(1).with_for_update())).first()
    if dup:
        raise HTTPException(
            409, "You already have an open request for this category")
    req = AssetRequest(
        employee_id=emp.id, category_id=cat.id, reason=payload.reason,
        needed_by=payload.needed_by, status=AssetRequestStatus.PENDING)
    db.add(req)
    await db.flush()
    chain_exists = (await db.execute(select(ApprovalChain.id).where(
        ApprovalChain.entity_type == ChainEntityType.ASSET_REQUEST,
        ApprovalChain.is_active.is_(True)).limit(1))).first() is not None
    auto_approved = False
    if chain_exists:
        # commit=False: request, instance, stamp, audit and notifications all
        # commit once below, with the employee lock held throughout.
        inst = await instantiate_for_entity(
            db=db, entity_type=ChainEntityType.ASSET_REQUEST,
            entity_id=req.id, submitter=current_user, amount_paise=0,
            department=emp.department, context={"category": cat.name}, commit=False)
        req.approval_instance_id = inst.id
        if inst.status == ChainedApprovalStatus.APPROVED:
            req.status = AssetRequestStatus.APPROVED
            req.decided_at = _now()  # decided_by_id stays NULL: system auto-approve
            auto_approved = True
    _audit(db, current_user, "ASSET_REQUEST_CREATE", req, {
        "category_id": cat.id, "routed_via": "chain" if chain_exists else "direct",
        "needed_by": _iso(req.needed_by)})
    if not chain_exists:
        await _notify_managers(
            db, req, "New asset request",
            f"{current_user.full_name or current_user.email} requested "
            f"{cat.name}: {req.reason[:200]}",
            "asset_request_submitted", exclude=current_user.id)
    elif auto_approved:
        await notify_managers_ready(db, req)
    rid = req.id
    await commit_or_409(db)
    return await _detail(db, rid)


@router.get("/my")
async def my_requests(
    db: deps.DBDep, current_user: User = Depends(deps.get_current_user),
) -> Any:
    emp = await _get_my_employee_or_404(db, current_user)
    rows = (await db.execute(
        select(AssetRequest, AssetCategory, Asset)
        .join(AssetCategory, AssetCategory.id == AssetRequest.category_id)
        .outerjoin(Asset, Asset.id == AssetRequest.fulfilled_asset_id)
        .where(AssetRequest.employee_id == emp.id)
        .order_by(AssetRequest.id.desc()))).all()
    return [_out(r, c, a) for r, c, a in rows]


@router.post("/{request_id}/cancel")
@guard_conflicts
async def cancel_request(
    request_id: int, db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    emp = await _get_my_employee_or_404(db, current_user)
    # Lock order matches the chain act route: instance -> request.
    peek = (await db.execute(select(AssetRequest.approval_instance_id).where(
        AssetRequest.id == request_id,
        AssetRequest.employee_id == emp.id))).first()
    if peek is None:
        raise HTTPException(404, "Asset request not found")
    inst = None
    if peek[0]:
        inst = (await db.execute(
            select(ChainedApprovalInstance)
            .where(ChainedApprovalInstance.id == peek[0])
            .options(selectinload(ChainedApprovalInstance.step_instances))
            .with_for_update().execution_options(populate_existing=True)
        )).scalars().first()
    req = await _lock_request(db, request_id, employee_id=emp.id)
    if req.status != AssetRequestStatus.PENDING:
        raise HTTPException(409, f"Request is {req.status}; only pending can be cancelled")
    if inst is not None:
        if inst.status != ChainedApprovalStatus.PENDING:
            raise HTTPException(409, "Request is already being finalised")
        inst.status = ChainedApprovalStatus.CANCELLED
        inst.finalized_at = _now()
        for si in inst.step_instances:
            if si.status == StepInstanceStatus.PENDING:
                si.status = StepInstanceStatus.SKIPPED
                si.comment = "cancelled_by_requester"
                si.actioned_at = _now()
    req.status = AssetRequestStatus.CANCELLED
    _audit(db, current_user, "ASSET_REQUEST_CANCEL", req, {})
    await commit_or_409(db)
    return await _detail(db, request_id)


# ── manager routes ───────────────────────────────────────────────────────
@router.get("", dependencies=_MGR)
async def list_requests(
    db: deps.DBDep,
    status: Optional[List[str]] = Query(None),
) -> Any:
    statuses = status or list(OPEN)
    bad = [s for s in statuses if s not in (
        "pending", "approved", "rejected", "fulfilled", "cancelled")]
    if bad:
        raise HTTPException(422, f"Unknown status: {bad[0]}")
    rows = (await db.execute(
        select(AssetRequest, AssetCategory, Asset, Employee, User.full_name)
        .join(AssetCategory, AssetCategory.id == AssetRequest.category_id)
        .join(Employee, Employee.id == AssetRequest.employee_id)
        .join(User, User.id == Employee.user_id)
        .outerjoin(Asset, Asset.id == AssetRequest.fulfilled_asset_id)
        .where(AssetRequest.status.in_(statuses))
        .order_by(AssetRequest.id.desc()))).all()
    out = []
    for r, c, a, e, name in rows:
        d = _out(r, c, a)
        d["employee"] = {"id": e.id, "name": name, "emp_code": e.employee_id,
                         "department": e.department}
        out.append(d)
    return out


@router.post("/{request_id}/decide", dependencies=_MGR)
@guard_conflicts
async def decide_request(
    request_id: int, payload: DecideIn, db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    req = await _lock_request(db, request_id)
    if req.approval_instance_id or (await db.execute(
            select(ChainedApprovalInstance.id).where(
                ChainedApprovalInstance.entity_type
                == ChainEntityType.ASSET_REQUEST,
                ChainedApprovalInstance.entity_id == req.id).limit(1)
    )).first():
        raise HTTPException(409, "Decide in the approval queue")
    if req.status != AssetRequestStatus.PENDING:
        raise HTTPException(409, f"Request is already {req.status}")
    approve = payload.action == "approve"
    req.status = (AssetRequestStatus.APPROVED if approve
                  else AssetRequestStatus.REJECTED)
    req.decided_by_id = current_user.id
    req.decided_at = _now()
    req.decision_note = (payload.note or "").strip() or None
    _audit(db, current_user, "ASSET_REQUEST_DECIDE", req, {
        "action": payload.action, "note": req.decision_note})
    uid = await _employee_user_id(db, req.employee_id)
    await roster_svc.notify_many(db, [(
        uid, f"Asset request {req.status}",
        f"Your asset request #{req.id} was {req.status}."
        + (f" Note: {req.decision_note}" if req.decision_note else ""),
        "asset_request", str(req.id), "asset_request_decided")])
    await commit_or_409(db)
    return await _detail(db, request_id)


@router.post("/{request_id}/fulfil", dependencies=_MGR)
@guard_conflicts
async def fulfil_request(
    request_id: int, payload: FulfilIn, db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    req = await _lock_request(db, request_id)
    if req.status != AssetRequestStatus.APPROVED:
        raise HTTPException(409, f"Request is {req.status}; only approved can be fulfilled")
    try:
        asset = await svc.get_asset_for_update(db, payload.asset_id)
        if (asset.category_id != req.category_id
                and not payload.allow_other_category):
            raise HTTPException(
                422, "Asset is not in the requested category")
        emp = await db.get(Employee, req.employee_id)
        alloc = await svc.allocate(
            db, asset=asset, employee=emp, actor=current_user,
            issued_date=payload.issued_date, condition=payload.condition,
            remarks=f"Asset request #{req.id}")
    except LookupError as e:
        raise HTTPException(404, str(e))
    except svc.AssetStateError as e:
        raise HTTPException(409, str(e))
    req.fulfilled_asset_id = asset.id
    req.allocation_id = alloc.id
    req.status = AssetRequestStatus.FULFILLED
    _audit(db, current_user, "ASSET_REQUEST_FULFIL", req, {
        "asset_id": asset.id, "allocation_id": alloc.id,
        "other_category": asset.category_id != req.category_id})
    await roster_svc.notify_many(db, [(
        emp.user_id, "Asset issued",
        f"Your asset request #{req.id} was fulfilled: {asset.asset_tag} "
        f"({asset.name}).", "asset_request", str(req.id),
        "asset_request_fulfilled")])
    await commit_or_409(db)
    return await _detail(db, request_id)
