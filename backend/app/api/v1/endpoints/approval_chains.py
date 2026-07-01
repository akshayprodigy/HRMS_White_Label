"""Generic Approval-Chain admin + inbox endpoints.

This module does NOT touch the legacy `approvals.py` router (which
drives leave / OT / revision). It is a forward-looking layer that new
consumers (Expense, Travel, ...) plug into via the engine.

Mount point: `/approval-chains`

Endpoints:
- POST   /approval-chains                          admin: create
- GET    /approval-chains                          admin: list
- PUT    /approval-chains/{id}                     admin: update (chain-level fields)
- DELETE /approval-chains/{id}                     admin: soft-disable (is_active=False)
- POST   /approval-chains/{id}/steps                admin: add step
- PUT    /approval-chains/{id}/steps/{step_id}      admin: edit step
- DELETE /approval-chains/{id}/steps/{step_id}      admin: remove step
- GET    /approval-chains/preview                   admin: dry-run "what would route where"
- GET    /approval-chains/my-queue                  everyone: pending items awaiting me
- POST   /approval-chains/instances/{id}/act        act on an assigned step
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import selectinload

from app.api import deps
from app.api.v1.endpoints.hr import log_audit
from app.models.approval_chain import (
    ApprovalChain, ApprovalChainStep, ApproverType,
    ChainEntityType, ChainedApprovalInstance,
    ChainedApprovalStatus, ChainedApprovalStepInstance,
    ParallelRule, StepInstanceStatus, StepMode,
)
from app.models.expense import ExpenseClaim, ExpenseClaimStatus, TravelRequest
from app.models.notification import Notification
from app.models.user import Role, User
from app.services.approval_engine import (
    ChainSpec, RequestContext, StepSpec, advance_state, build_plan,
    pick_effective_chain, validate_bands,
)


router = APIRouter()


# ============================================================
# RBAC helpers
# ============================================================


PERM_CHAIN_ADMIN = "approval chain admin"
PERM_FINANCE_APPROVE = "finance approve"


def _has_perm(user: User, name: str) -> bool:
    if user.is_superuser:
        return True
    for role in user.roles or []:
        for perm in role.permissions or []:
            if (perm.name or "") == name:
                return True
    return False


def _is_hr_or_admin(user: User) -> bool:
    if user.is_superuser:
        return True
    role_names = [(r.name or "").lower() for r in user.roles or []]
    return any(n in role_names for n in (
        "hr", "super admin", "admin", "ceo",
    ))


def _is_finance(user: User) -> bool:
    if user.is_superuser:
        return True
    role_names = [(r.name or "").lower() for r in user.roles or []]
    return "finance" in role_names


# ============================================================
# Schemas
# ============================================================


class StepIn(BaseModel):
    step_order: int
    approver_type: str
    approver_ref: Optional[str] = None
    mode: str = StepMode.SEQUENTIAL
    parallel_rule: str = ParallelRule.ALL
    min_amount_paise: Optional[int] = None
    max_amount_paise: Optional[int] = None
    skip_if_same_person: bool = False
    skip_if_absent_days: Optional[int] = None
    label: Optional[str] = None


class ChainIn(BaseModel):
    name: str
    entity_type: str
    department: Optional[str] = None
    effective_from: date
    effective_to: Optional[date] = None
    is_active: bool = True
    auto_approve_below_paise: Optional[int] = None
    skip_if_same_person: bool = True
    notes: Optional[str] = None
    steps: List[StepIn] = Field(default_factory=list)


class ChainPatch(BaseModel):
    name: Optional[str] = None
    department: Optional[str] = None
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None
    is_active: Optional[bool] = None
    auto_approve_below_paise: Optional[int] = None
    skip_if_same_person: Optional[bool] = None
    notes: Optional[str] = None


class ActIn(BaseModel):
    action: str            # "approve" | "reject"
    comment: Optional[str] = None


# ============================================================
# Serialisers
# ============================================================


def _step_dict(s: ApprovalChainStep) -> dict:
    return {
        "id": s.id, "step_order": s.step_order,
        "approver_type": s.approver_type,
        "approver_ref": s.approver_ref,
        "mode": s.mode, "parallel_rule": s.parallel_rule,
        "min_amount_paise": s.min_amount_paise,
        "max_amount_paise": s.max_amount_paise,
        "skip_if_same_person": s.skip_if_same_person,
        "skip_if_absent_days": s.skip_if_absent_days,
        "label": s.label,
    }


def _chain_dict(c: ApprovalChain) -> dict:
    return {
        "id": c.id, "name": c.name, "entity_type": c.entity_type,
        "department": c.department, "is_active": c.is_active,
        "effective_from": c.effective_from, "effective_to": c.effective_to,
        "auto_approve_below_paise": c.auto_approve_below_paise,
        "skip_if_same_person": c.skip_if_same_person,
        "notes": c.notes,
        "steps": [_step_dict(s) for s in sorted(
            c.steps or [], key=lambda x: x.step_order
        )],
    }


def _instance_dict(i: ChainedApprovalInstance) -> dict:
    return {
        "id": i.id, "chain_id": i.chain_id,
        "entity_type": i.entity_type, "entity_id": i.entity_id,
        "submitter_id": i.submitter_id, "amount_paise": i.amount_paise,
        "status": i.status,
        "current_step_order": i.current_step_order,
        "created_at": i.created_at, "finalized_at": i.finalized_at,
    }


def _step_instance_dict(si: ChainedApprovalStepInstance) -> dict:
    return {
        "id": si.id, "instance_id": si.instance_id,
        "step_order": si.step_order,
        "approver_type": si.approver_type,
        "approver_user_id": si.approver_user_id,
        "mode": si.mode, "parallel_rule": si.parallel_rule,
        "status": si.status, "comment": si.comment,
        "actioned_at": si.actioned_at, "label": si.label,
    }


# ============================================================
# Chain admin
# ============================================================


def _steps_to_spec(steps) -> List[StepSpec]:
    return [
        StepSpec(
            step_order=s.step_order,
            approver_type=s.approver_type,
            approver_ref=s.approver_ref,
            mode=s.mode, parallel_rule=s.parallel_rule,
            min_amount_paise=s.min_amount_paise,
            max_amount_paise=s.max_amount_paise,
            skip_if_same_person=s.skip_if_same_person,
            skip_if_absent_days=s.skip_if_absent_days,
            label=s.label,
        )
        for s in steps
    ]


@router.post("/approval-chains")
async def create_chain(
    payload: ChainIn,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    if not (_is_hr_or_admin(current_user) or _has_perm(current_user, PERM_CHAIN_ADMIN)):
        raise HTTPException(403, "Chain admin only")

    # Validate bands before persist.
    step_specs = [
        StepSpec(
            step_order=s.step_order, approver_type=s.approver_type,
            approver_ref=s.approver_ref, mode=s.mode,
            parallel_rule=s.parallel_rule,
            min_amount_paise=s.min_amount_paise,
            max_amount_paise=s.max_amount_paise,
            skip_if_same_person=s.skip_if_same_person,
            skip_if_absent_days=s.skip_if_absent_days,
            label=s.label,
        )
        for s in payload.steps
    ]
    band_check = validate_bands(step_specs)
    if not band_check.ok:
        raise HTTPException(
            400,
            {
                "message": "Chain would strand requests",
                "gaps": band_check.gaps,
                "empty": band_check.empty,
                "duplicate_orders": band_check.duplicate_orders,
            },
        )

    chain = ApprovalChain(
        name=payload.name,
        entity_type=payload.entity_type,
        department=payload.department,
        is_active=payload.is_active,
        effective_from=payload.effective_from,
        effective_to=payload.effective_to,
        auto_approve_below_paise=payload.auto_approve_below_paise,
        skip_if_same_person=payload.skip_if_same_person,
        notes=payload.notes,
        created_by_id=current_user.id,
    )
    for s in payload.steps:
        chain.steps.append(ApprovalChainStep(
            step_order=s.step_order,
            approver_type=s.approver_type,
            approver_ref=s.approver_ref,
            mode=s.mode, parallel_rule=s.parallel_rule,
            min_amount_paise=s.min_amount_paise,
            max_amount_paise=s.max_amount_paise,
            skip_if_same_person=s.skip_if_same_person,
            skip_if_absent_days=s.skip_if_absent_days,
            label=s.label,
        ))
    db.add(chain)
    await db.commit()
    await db.refresh(chain)
    await db.execute(
        select(ApprovalChain).where(ApprovalChain.id == chain.id)
        .options(selectinload(ApprovalChain.steps))
    )
    await log_audit(
        db, current_user.id, "approval_chain_create",
        "approval_chain", str(chain.id),
        {"name": chain.name, "entity_type": chain.entity_type},
        request,
    )
    # Refresh to load steps.
    fresh = (await db.execute(
        select(ApprovalChain).where(ApprovalChain.id == chain.id)
        .options(selectinload(ApprovalChain.steps))
    )).scalar_one()
    return _chain_dict(fresh)


@router.get("/approval-chains")
async def list_chains(
    db: deps.DBDep,
    entity_type: Optional[str] = Query(None),
    include_inactive: bool = Query(False),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    if not (_is_hr_or_admin(current_user) or _has_perm(current_user, PERM_CHAIN_ADMIN)):
        raise HTTPException(403, "Chain admin only")
    stmt = select(ApprovalChain).options(selectinload(ApprovalChain.steps))
    if entity_type:
        stmt = stmt.where(ApprovalChain.entity_type == entity_type)
    if not include_inactive:
        stmt = stmt.where(ApprovalChain.is_active.is_(True))
    stmt = stmt.order_by(ApprovalChain.entity_type, ApprovalChain.name)
    rows = (await db.execute(stmt)).scalars().unique().all()
    return [_chain_dict(c) for c in rows]


@router.put("/approval-chains/{chain_id}")
async def update_chain(
    chain_id: int,
    payload: ChainPatch,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    if not (_is_hr_or_admin(current_user) or _has_perm(current_user, PERM_CHAIN_ADMIN)):
        raise HTTPException(403, "Chain admin only")
    chain = (await db.execute(
        select(ApprovalChain).where(ApprovalChain.id == chain_id)
        .options(selectinload(ApprovalChain.steps))
    )).scalar_one_or_none()
    if not chain:
        raise HTTPException(404, "Chain not found")

    for field, val in payload.model_dump(exclude_unset=True).items():
        setattr(chain, field, val)
    await db.commit()
    await log_audit(
        db, current_user.id, "approval_chain_update",
        "approval_chain", str(chain.id),
        payload.model_dump(exclude_unset=True), request,
    )
    return _chain_dict(chain)


@router.delete("/approval-chains/{chain_id}")
async def disable_chain(
    chain_id: int,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    if not (_is_hr_or_admin(current_user) or _has_perm(current_user, PERM_CHAIN_ADMIN)):
        raise HTTPException(403, "Chain admin only")
    chain = (await db.execute(
        select(ApprovalChain).where(ApprovalChain.id == chain_id)
    )).scalar_one_or_none()
    if not chain:
        raise HTTPException(404, "Chain not found")
    chain.is_active = False
    await db.commit()
    await log_audit(
        db, current_user.id, "approval_chain_disable",
        "approval_chain", str(chain.id), {}, request,
    )
    return {"ok": True, "id": chain.id, "is_active": chain.is_active}


@router.post("/approval-chains/{chain_id}/steps")
async def add_step(
    chain_id: int,
    payload: StepIn,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    if not (_is_hr_or_admin(current_user) or _has_perm(current_user, PERM_CHAIN_ADMIN)):
        raise HTTPException(403, "Chain admin only")
    chain = (await db.execute(
        select(ApprovalChain).where(ApprovalChain.id == chain_id)
        .options(selectinload(ApprovalChain.steps))
    )).scalar_one_or_none()
    if not chain:
        raise HTTPException(404, "Chain not found")
    step = ApprovalChainStep(
        chain_id=chain.id,
        step_order=payload.step_order,
        approver_type=payload.approver_type,
        approver_ref=payload.approver_ref,
        mode=payload.mode, parallel_rule=payload.parallel_rule,
        min_amount_paise=payload.min_amount_paise,
        max_amount_paise=payload.max_amount_paise,
        skip_if_same_person=payload.skip_if_same_person,
        skip_if_absent_days=payload.skip_if_absent_days,
        label=payload.label,
    )
    db.add(step)
    await db.flush()

    new_specs = _steps_to_spec(list(chain.steps) + [step])
    band_check = validate_bands(new_specs)
    if not band_check.ok:
        await db.rollback()
        raise HTTPException(
            400,
            {
                "message": "Adding this step would strand requests",
                "gaps": band_check.gaps,
                "duplicate_orders": band_check.duplicate_orders,
            },
        )
    await db.commit()
    await log_audit(
        db, current_user.id, "approval_chain_step_add",
        "approval_chain_step", str(step.id),
        payload.model_dump(), request,
    )
    return _step_dict(step)


@router.put("/approval-chains/{chain_id}/steps/{step_id}")
async def update_step(
    chain_id: int,
    step_id: int,
    payload: StepIn,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    if not (_is_hr_or_admin(current_user) or _has_perm(current_user, PERM_CHAIN_ADMIN)):
        raise HTTPException(403, "Chain admin only")
    step = (await db.execute(
        select(ApprovalChainStep).where(
            and_(
                ApprovalChainStep.id == step_id,
                ApprovalChainStep.chain_id == chain_id,
            )
        )
    )).scalar_one_or_none()
    if not step:
        raise HTTPException(404, "Step not found")
    for field, val in payload.model_dump().items():
        setattr(step, field, val)
    # Re-validate bands after edit.
    remaining = (await db.execute(
        select(ApprovalChainStep).where(ApprovalChainStep.chain_id == chain_id)
    )).scalars().all()
    band_check = validate_bands(_steps_to_spec(remaining))
    if not band_check.ok:
        await db.rollback()
        raise HTTPException(
            400,
            {"message": "Edit would strand requests",
             "gaps": band_check.gaps},
        )
    await db.commit()
    await log_audit(
        db, current_user.id, "approval_chain_step_update",
        "approval_chain_step", str(step.id),
        payload.model_dump(), request,
    )
    return _step_dict(step)


@router.delete("/approval-chains/{chain_id}/steps/{step_id}")
async def delete_step(
    chain_id: int,
    step_id: int,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    if not (_is_hr_or_admin(current_user) or _has_perm(current_user, PERM_CHAIN_ADMIN)):
        raise HTTPException(403, "Chain admin only")
    step = (await db.execute(
        select(ApprovalChainStep).where(
            and_(
                ApprovalChainStep.id == step_id,
                ApprovalChainStep.chain_id == chain_id,
            )
        )
    )).scalar_one_or_none()
    if not step:
        raise HTTPException(404, "Step not found")
    remaining = [
        s for s in (await db.execute(
            select(ApprovalChainStep).where(ApprovalChainStep.chain_id == chain_id)
        )).scalars().all() if s.id != step_id
    ]
    band_check = validate_bands(_steps_to_spec(remaining))
    if not band_check.ok:
        raise HTTPException(
            400,
            {"message": "Removing this step would strand requests",
             "gaps": band_check.gaps, "empty": band_check.empty},
        )
    await db.delete(step)
    await db.commit()
    await log_audit(
        db, current_user.id, "approval_chain_step_delete",
        "approval_chain_step", str(step_id), {}, request,
    )
    return {"ok": True, "id": step_id}


# ============================================================
# Preview — "for a ₹X claim from dept Y, what would route?"
# ============================================================


@router.get("/approval-chains/preview")
async def preview_route(
    db: deps.DBDep,
    entity_type: str = Query(...),
    amount_paise: int = Query(...),
    department: Optional[str] = Query(None),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    if not (_is_hr_or_admin(current_user) or _has_perm(current_user, PERM_CHAIN_ADMIN)):
        raise HTTPException(403, "Chain admin only")
    chains = (await db.execute(
        select(ApprovalChain).where(
            and_(
                ApprovalChain.entity_type == entity_type,
                ApprovalChain.is_active.is_(True),
            )
        ).options(selectinload(ApprovalChain.steps))
    )).scalars().unique().all()

    specs = [
        ChainSpec(
            id=c.id, name=c.name, entity_type=c.entity_type,
            steps=tuple(_steps_to_spec(c.steps)),
            auto_approve_below_paise=c.auto_approve_below_paise,
            skip_if_same_person=c.skip_if_same_person,
            department=c.department,
        )
        for c in chains
    ]
    picked = pick_effective_chain(
        specs, entity_type=entity_type, department=department,
    )
    if not picked:
        return {"chain": None, "plan": [], "reason": "no active chain matches"}

    ctx = RequestContext(
        submitter_id=current_user.id,
        amount_paise=amount_paise, department=department,
    )
    # Preview uses a dummy resolver — replaces user ids with type-labels so
    # the caller sees "reporting_manager" without needing seeded users.
    def _preview_resolver(step, _ctx):
        return [-1]

    plan = build_plan(picked, ctx, _preview_resolver)
    return {
        "chain": {"id": picked.id, "name": picked.name,
                  "department": picked.department},
        "plan": [
            {
                "step_order": p.step_order,
                "approver_type": p.approver_type,
                "mode": p.mode, "parallel_rule": p.parallel_rule,
                "label": p.label,
                "skip_reason": p.skip_reason,
            }
            for p in plan
        ],
    }


# ============================================================
# Runtime — resolver
# ============================================================


async def _resolve_approvers(
    db, step: StepSpec, submitter_id: int,
) -> List[int]:
    """Turn an approver_type into a list of user ids.

    - REPORTING_MANAGER: submitter's User.manager_id
    - DEPT_HEAD: users tagged with the "dept_head" role (org-wide fallback)
    - ROLE: all users with the named role
    - SPECIFIC_USER: exactly the referenced user id
    - FINANCE: users with the "finance" role
    """
    kind = step.approver_type
    if kind == ApproverType.REPORTING_MANAGER:
        row = (await db.execute(
            select(User.manager_id).where(User.id == submitter_id)
        )).scalar_one_or_none()
        return [row] if row else []
    if kind == ApproverType.DEPT_HEAD:
        stmt = (
            select(User.id)
            .join(User.roles)
            .where(Role.name == "dept_head")
        )
        return list((await db.execute(stmt)).scalars().all())
    if kind == ApproverType.ROLE:
        role_name = step.approver_ref or ""
        stmt = (
            select(User.id).join(User.roles).where(Role.name == role_name)
        )
        return list((await db.execute(stmt)).scalars().all())
    if kind == ApproverType.SPECIFIC_USER:
        try:
            uid = int(step.approver_ref or "")
        except (TypeError, ValueError):
            return []
        return [uid]
    if kind == ApproverType.FINANCE:
        stmt = (
            select(User.id).join(User.roles).where(Role.name == "finance")
        )
        return list((await db.execute(stmt)).scalars().all())
    return []


async def _drop_absent_approvers(
    db, approver_ids: List[int], window_days: int,
) -> List[int]:
    """Section M B5: check attendance for each approver in the trailing
    `window_days` and drop anyone with ZERO attended work-dates. Uses
    the engine's pure `is_approver_absent` helper for the classification
    so the decision is unit-tested.

    Safety: if the filter would return an empty list (every approver is
    out), return the ORIGINAL list so the request is not stranded — the
    caller will surface it to HR via the existing 'no_eligible_approver'
    audit path.
    """
    from datetime import date as _date, timedelta as _td
    from app.models.attendance import Attendance
    from app.services.approval_engine import (
        AbsenceCheck, filter_absent_approvers,
    )

    if not approver_ids or window_days <= 0:
        return approver_ids

    today = _date.today()
    since = today - _td(days=window_days)
    rows = (await db.execute(
        select(Attendance.user_id, Attendance.work_date).where(
            and_(
                Attendance.user_id.in_(approver_ids),
                Attendance.work_date >= since,
                Attendance.work_date <= today,
            )
        )
    )).all()
    attended_by_user: dict = {uid: set() for uid in approver_ids}
    for row in rows:
        attended_by_user.setdefault(row.user_id, set()).add(
            row.work_date.isoformat()
        )
    checks = [
        AbsenceCheck(
            user_id=uid,
            required_window_days=window_days,
            attended_work_dates=frozenset(attended_by_user.get(uid) or set()),
        )
        for uid in approver_ids
    ]
    filtered = filter_absent_approvers(checks)
    if not filtered:
        # All absent — never strand. Fall back to originals; the
        # step_instance layer records skip_reason='no_eligible_approver'
        # if the resolver still returns [], and HR can then hold/hand-
        # approve.
        return approver_ids
    return filtered


async def instantiate_for_entity(
    *,
    db,
    entity_type: str,
    entity_id: int,
    submitter: User,
    amount_paise: int,
    department: Optional[str],
    context: Optional[Dict[str, Any]] = None,
) -> ChainedApprovalInstance:
    """Public helper — the endpoint layer of *other* modules (expenses.py,
    travel.py, ...) calls this to create the approval instance for their
    submitted entity.

    Returns a persisted ChainedApprovalInstance (already committed). The
    caller should stamp `entity.approval_instance_id = instance.id` and
    commit again.
    """
    chains = (await db.execute(
        select(ApprovalChain).where(
            and_(
                ApprovalChain.entity_type == entity_type,
                ApprovalChain.is_active.is_(True),
            )
        ).options(selectinload(ApprovalChain.steps))
    )).scalars().unique().all()

    specs = [
        ChainSpec(
            id=c.id, name=c.name, entity_type=c.entity_type,
            steps=tuple(_steps_to_spec(c.steps)),
            auto_approve_below_paise=c.auto_approve_below_paise,
            skip_if_same_person=c.skip_if_same_person,
            department=c.department,
        )
        for c in chains
    ]
    picked = pick_effective_chain(
        specs, entity_type=entity_type, department=department,
    )
    if not picked:
        raise HTTPException(
            400,
            f"No active approval chain configured for entity_type={entity_type}",
        )

    ctx = RequestContext(
        submitter_id=submitter.id,
        amount_paise=amount_paise, department=department,
    )

    async def _resolver_sync(step, request_ctx):
        # `build_plan` calls resolver synchronously; we pre-resolve using
        # an outer closure below.
        raise RuntimeError("Use pre-resolved plan")

    # Pre-resolve every applicable step.
    materialized = []
    for step in picked.steps:
        if not (step.min_amount_paise or 0) <= amount_paise <= (
            step.max_amount_paise or 10**18
        ):
            continue
        approver_ids = await _resolve_approvers(db, step, submitter.id)
        skip_self = step.skip_if_same_person or picked.skip_if_same_person
        if skip_self:
            approver_ids = [u for u in approver_ids if u != submitter.id]
        # Section M B5: real skip-if-absent lookup. If a step requires
        # skip_if_absent_days > 0, check attendance for each candidate;
        # drop candidates with ZERO attended work_dates in the window.
        # NEVER strand: if the check would empty the list, keep the
        # originals and let the endpoint mark the step SKIPPED with
        # 'all_absent' so HR can intervene.
        if step.skip_if_absent_days and approver_ids:
            approver_ids = await _drop_absent_approvers(
                db, approver_ids, step.skip_if_absent_days,
            )
        materialized.append((step, approver_ids))
    materialized.sort(key=lambda t: t[0].step_order)

    threshold = picked.auto_approve_below_paise or 0
    auto_approve = threshold and amount_paise < threshold

    instance = ChainedApprovalInstance(
        chain_id=picked.id,
        entity_type=entity_type,
        entity_id=entity_id,
        submitter_id=submitter.id,
        amount_paise=amount_paise,
        context_json=context or {},
        status=(
            ChainedApprovalStatus.APPROVED
            if (auto_approve or not materialized)
            else ChainedApprovalStatus.PENDING
        ),
        current_step_order=(
            materialized[0][0].step_order if materialized else 0
        ),
        finalized_at=(
            datetime.now(timezone.utc)
            if (auto_approve or not materialized) else None
        ),
    )
    db.add(instance)
    await db.flush()

    for step, approver_ids in materialized:
        if not approver_ids:
            # No eligible approver — emit a skipped row so audit trail
            # shows why the chain landed where it did. Instance stays
            # pending on THIS step_order so HR can fix and rerun.
            db.add(ChainedApprovalStepInstance(
                instance_id=instance.id,
                step_order=step.step_order,
                approver_type=step.approver_type,
                approver_user_id=None,
                mode=step.mode, parallel_rule=step.parallel_rule,
                status=StepInstanceStatus.SKIPPED,
                comment="no_eligible_approver",
                label=step.label,
            ))
            continue
        for uid in approver_ids:
            db.add(ChainedApprovalStepInstance(
                instance_id=instance.id,
                step_order=step.step_order,
                approver_type=step.approver_type,
                approver_user_id=uid,
                mode=step.mode, parallel_rule=step.parallel_rule,
                status=StepInstanceStatus.PENDING,
                label=step.label,
            ))
            db.add(Notification(
                user_id=uid,
                title=f"Approval pending: {entity_type}",
                message=(
                    f"You have a {entity_type} approval request "
                    f"(₹{amount_paise / 100:.2f}) from user #{submitter.id}."
                ),
                type="info",
                resource_type=f"chained_approval_instance",
                resource_id=str(instance.id),
            ))
    await db.commit()
    return instance


# ============================================================
# /approval-chains/my-queue  and act
# ============================================================


async def _entity_summary(
    db, entity_type: str, entity_id: int,
) -> Optional[dict]:
    """Return a compact summary of the linked entity for the queue row."""
    if entity_type == ChainEntityType.EXPENSE:
        row = (await db.execute(
            select(ExpenseClaim).where(ExpenseClaim.id == entity_id)
            .options(selectinload(ExpenseClaim.line_items))
        )).scalar_one_or_none()
        if not row:
            return None
        return {
            "kind": "expense",
            "id": row.id, "title": row.title,
            "description": row.description,
            "amount_paise": row.total_amount_paise,
            "claim_date": row.claim_date,
            "employee_id": row.employee_id,
            "line_count": len(row.line_items),
            "out_of_policy_count": sum(
                1 for l in row.line_items if l.is_out_of_policy
            ),
        }
    if entity_type == ChainEntityType.TRAVEL:
        row = (await db.execute(
            select(TravelRequest).where(TravelRequest.id == entity_id)
        )).scalar_one_or_none()
        if not row:
            return None
        return {
            "kind": "travel",
            "id": row.id, "purpose": row.purpose,
            "from_city": row.from_city, "to_city": row.to_city,
            "start_date": row.start_date, "end_date": row.end_date,
            "amount_paise": row.estimated_cost_paise,
            "advance_requested_paise": row.advance_requested_paise,
            "employee_id": row.employee_id,
        }
    return {"kind": entity_type, "id": entity_id}


@router.get("/approval-chains/my-queue")
async def my_queue(
    db: deps.DBDep,
    entity_type: Optional[str] = Query(None),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Every pending step-instance assigned to me across all entity types."""
    stmt = (
        select(ChainedApprovalStepInstance)
        .where(
            and_(
                ChainedApprovalStepInstance.approver_user_id == current_user.id,
                ChainedApprovalStepInstance.status == StepInstanceStatus.PENDING,
            )
        )
        .order_by(ChainedApprovalStepInstance.id)
    )
    step_instances = (await db.execute(stmt)).scalars().all()
    if not step_instances:
        return []

    inst_ids = [si.instance_id for si in step_instances]
    instances = (await db.execute(
        select(ChainedApprovalInstance).where(
            ChainedApprovalInstance.id.in_(inst_ids)
        )
    )).scalars().all()
    inst_by_id = {i.id: i for i in instances}

    out: List[dict] = []
    for si in step_instances:
        inst = inst_by_id.get(si.instance_id)
        if not inst:
            continue
        # Only surface rows for instances that are currently at THIS step.
        if inst.current_step_order != si.step_order:
            continue
        if entity_type and inst.entity_type != entity_type:
            continue
        summary = await _entity_summary(
            db, inst.entity_type, inst.entity_id
        )
        out.append({
            "step_instance": _step_instance_dict(si),
            "instance": _instance_dict(inst),
            "entity": summary,
        })
    return out


@router.post("/approval-chains/instances/{instance_id}/act")
async def act_on_step(
    instance_id: int,
    payload: ActIn,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    if payload.action not in ("approve", "reject"):
        raise HTTPException(400, "action must be 'approve' or 'reject'")

    instance = (await db.execute(
        select(ChainedApprovalInstance)
        .where(ChainedApprovalInstance.id == instance_id)
        .options(selectinload(ChainedApprovalInstance.step_instances))
    )).scalar_one_or_none()
    if not instance:
        raise HTTPException(404, "Instance not found")
    if instance.status != ChainedApprovalStatus.PENDING:
        raise HTTPException(400, f"Instance is {instance.status}")

    # Find MY pending row at the current step.
    my_row = next(
        (
            si for si in instance.step_instances
            if si.approver_user_id == current_user.id
            and si.step_order == instance.current_step_order
            and si.status == StepInstanceStatus.PENDING
        ),
        None,
    )
    if not my_row:
        raise HTTPException(403, "You have no pending action on this instance")

    my_row.status = (
        StepInstanceStatus.APPROVED if payload.action == "approve"
        else StepInstanceStatus.REJECTED
    )
    my_row.comment = payload.comment
    my_row.actioned_at = datetime.now(timezone.utc)

    all_rows_dicts = [
        {
            "step_order": si.step_order,
            "status": si.status,
            "mode": si.mode,
            "parallel_rule": si.parallel_rule,
            "approver_user_id": si.approver_user_id,
        }
        for si in instance.step_instances
    ]
    outcome = advance_state(
        all_step_instances=all_rows_dicts,
        acted_step_order=instance.current_step_order,
        action=payload.action,
    )

    if outcome.finalize:
        instance.status = outcome.next_status
        instance.finalized_at = datetime.now(timezone.utc)
        # Propagate to the linked entity's status.
        if instance.entity_type == ChainEntityType.EXPENSE:
            claim = (await db.execute(
                select(ExpenseClaim).where(
                    ExpenseClaim.id == instance.entity_id
                )
            )).scalar_one_or_none()
            if claim:
                claim.status = (
                    ExpenseClaimStatus.APPROVED
                    if outcome.next_status == ChainedApprovalStatus.APPROVED
                    else ExpenseClaimStatus.REJECTED
                )
        elif instance.entity_type == ChainEntityType.TRAVEL:
            tr = (await db.execute(
                select(TravelRequest).where(
                    TravelRequest.id == instance.entity_id
                )
            )).scalar_one_or_none()
            if tr:
                tr.status = (
                    "approved"
                    if outcome.next_status == ChainedApprovalStatus.APPROVED
                    else "rejected"
                )
        # Notify submitter.
        if instance.submitter_id:
            db.add(Notification(
                user_id=instance.submitter_id,
                title=(
                    f"{instance.entity_type} {outcome.next_status}"
                ),
                message=(
                    f"Your {instance.entity_type} #{instance.entity_id} was "
                    f"{outcome.next_status} by {current_user.full_name or current_user.email}."
                ),
                type="success" if outcome.next_status == "approved" else "warning",
                resource_type="chained_approval_instance",
                resource_id=str(instance.id),
            ))
    elif outcome.advance_to_step is not None:
        instance.current_step_order = outcome.advance_to_step
        # Notify approvers at the next step.
        next_rows = [
            si for si in instance.step_instances
            if si.step_order == outcome.advance_to_step
            and si.status == StepInstanceStatus.PENDING
            and si.approver_user_id
        ]
        for si in next_rows:
            db.add(Notification(
                user_id=si.approver_user_id,
                title=f"Approval pending: {instance.entity_type}",
                message=(
                    f"You have a {instance.entity_type} approval request "
                    f"(₹{instance.amount_paise / 100:.2f}) awaiting action."
                ),
                type="info",
                resource_type="chained_approval_instance",
                resource_id=str(instance.id),
            ))

    await db.commit()
    await log_audit(
        db, current_user.id,
        f"chained_approval_{payload.action}",
        "chained_approval_step_instance", str(my_row.id),
        {
            "instance_id": instance.id,
            "entity_type": instance.entity_type,
            "entity_id": instance.entity_id,
            "outcome_status": outcome.next_status,
            "comment": payload.comment,
        },
        request,
    )
    return {
        "instance": _instance_dict(instance),
        "step_instance": _step_instance_dict(my_row),
        "finalized": outcome.finalize,
        "next_step": outcome.advance_to_step,
    }


@router.get("/approval-chains/instances/{instance_id}")
async def get_instance(
    instance_id: int,
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    instance = (await db.execute(
        select(ChainedApprovalInstance)
        .where(ChainedApprovalInstance.id == instance_id)
        .options(selectinload(ChainedApprovalInstance.step_instances))
    )).scalar_one_or_none()
    if not instance:
        raise HTTPException(404, "Instance not found")
    # Submitter, current-step approver, or HR/finance/admin may read.
    is_approver = any(
        si.approver_user_id == current_user.id
        for si in instance.step_instances
    )
    if (
        instance.submitter_id != current_user.id
        and not is_approver
        and not (_is_hr_or_admin(current_user) or _is_finance(current_user))
    ):
        raise HTTPException(403, "Not authorized")
    summary = await _entity_summary(
        db, instance.entity_type, instance.entity_id
    )
    return {
        "instance": _instance_dict(instance),
        "entity": summary,
        "step_instances": [
            _step_instance_dict(si)
            for si in sorted(
                instance.step_instances, key=lambda x: (x.step_order, x.id)
            )
        ],
    }
