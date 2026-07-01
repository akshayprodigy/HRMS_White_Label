"""Expense & Travel endpoints — first consumer of the generic chain
engine.

Money in paise. Category master is CRUD-able by HR. Employees submit
claims + travel requests → the chain engine routes them → Finance
reimburses (direct or via a payroll injection).
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import selectinload

from app.api import deps
from app.api.v1.endpoints.approval_chains import (
    _is_finance, _is_hr_or_admin, instantiate_for_entity,
)
from app.api.v1.endpoints.hr import log_audit
from app.models.approval_chain import (
    ChainEntityType, ChainedApprovalInstance, ChainedApprovalStatus,
)
from app.models.employee import Employee
from app.models.expense import (
    ExpenseCategory, ExpenseClaim, ExpenseClaimStatus,
    ExpenseLineItem, ReimbursementMode, TravelRequest, TravelRequestStatus,
)
from app.models.notification import Notification
from app.models.user import User
from app.services.expense import (
    LineItemInput, decide_reimbursement, evaluate_policy,
    reconcile_travel_advance, sum_line_items,
)


router = APIRouter()


# ============================================================
# RBAC helpers
# ============================================================


PERM_CATEGORY_ADMIN = "expense category admin"
PERM_FINANCE_REIMBURSE = "finance reimburse"


def _has_perm(user: User, name: str) -> bool:
    if user.is_superuser:
        return True
    for role in user.roles or []:
        for perm in role.permissions or []:
            if (perm.name or "") == name:
                return True
    return False


async def _employee_for(
    db, user_id: int,
) -> Optional[Employee]:
    return (await db.execute(
        select(Employee).where(Employee.user_id == user_id)
    )).scalar_one_or_none()


async def _team_user_ids(db, manager_user_id: int) -> List[int]:
    rows = (await db.execute(
        select(User.id).where(User.manager_id == manager_user_id)
    )).scalars().all()
    return list(rows)


# ============================================================
# Categories
# ============================================================


class CategoryIn(BaseModel):
    name: str
    code: Optional[str] = None
    is_active: bool = True
    per_diem_cap_paise: Optional[int] = None
    receipt_required_above_paise: Optional[int] = None
    policy_mode: str = "warn"
    notes: Optional[str] = None


def _category_dict(c: ExpenseCategory) -> dict:
    return {
        "id": c.id, "name": c.name, "code": c.code,
        "is_active": c.is_active,
        "per_diem_cap_paise": c.per_diem_cap_paise,
        "receipt_required_above_paise": c.receipt_required_above_paise,
        "policy_mode": c.policy_mode, "notes": c.notes,
    }


@router.get("/categories")
async def list_categories(
    db: deps.DBDep,
    include_inactive: bool = Query(False),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    stmt = select(ExpenseCategory).order_by(ExpenseCategory.name)
    if not include_inactive:
        stmt = stmt.where(ExpenseCategory.is_active.is_(True))
    rows = (await db.execute(stmt)).scalars().all()
    return [_category_dict(c) for c in rows]


@router.post("/categories")
async def create_category(
    payload: CategoryIn,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    if not (_is_hr_or_admin(current_user) or _has_perm(current_user, PERM_CATEGORY_ADMIN)):
        raise HTTPException(403, "Category admin only")
    cat = ExpenseCategory(**payload.model_dump())
    db.add(cat)
    await db.commit()
    await db.refresh(cat)
    await log_audit(
        db, current_user.id, "expense_category_create",
        "expense_category", str(cat.id), payload.model_dump(), request,
    )
    return _category_dict(cat)


@router.put("/categories/{cat_id}")
async def update_category(
    cat_id: int,
    payload: CategoryIn,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    if not (_is_hr_or_admin(current_user) or _has_perm(current_user, PERM_CATEGORY_ADMIN)):
        raise HTTPException(403, "Category admin only")
    cat = (await db.execute(
        select(ExpenseCategory).where(ExpenseCategory.id == cat_id)
    )).scalar_one_or_none()
    if not cat:
        raise HTTPException(404, "Category not found")
    for k, v in payload.model_dump().items():
        setattr(cat, k, v)
    await db.commit()
    await log_audit(
        db, current_user.id, "expense_category_update",
        "expense_category", str(cat.id), payload.model_dump(), request,
    )
    return _category_dict(cat)


# ============================================================
# Expense claim CRUD + submit
# ============================================================


class LineIn(BaseModel):
    category_id: int
    amount_paise: int
    line_date: Optional[date] = None
    description: Optional[str] = None
    receipt_url: Optional[str] = None


class ClaimIn(BaseModel):
    title: str
    description: Optional[str] = None
    claim_date: date
    project_id: Optional[int] = None
    cost_center: Optional[str] = None
    linked_travel_request_id: Optional[int] = None
    line_items: List[LineIn] = Field(default_factory=list)


def _line_dict(l: ExpenseLineItem) -> dict:
    return {
        "id": l.id, "category_id": l.category_id,
        "amount_paise": l.amount_paise,
        "line_date": l.line_date,
        "description": l.description, "receipt_url": l.receipt_url,
        "is_out_of_policy": l.is_out_of_policy,
        "policy_flag_reason": l.policy_flag_reason,
    }


def _claim_dict(c: ExpenseClaim) -> dict:
    return {
        "id": c.id, "employee_id": c.employee_id,
        "submitter_id": c.submitter_id,
        "title": c.title, "description": c.description,
        "claim_date": c.claim_date,
        "project_id": c.project_id, "cost_center": c.cost_center,
        "total_amount_paise": c.total_amount_paise,
        "status": c.status,
        "approval_instance_id": c.approval_instance_id,
        "reimbursement_mode": c.reimbursement_mode,
        "reimbursed_at": c.reimbursed_at,
        "reimbursed_reference": c.reimbursed_reference,
        "payroll_run_id": c.payroll_run_id,
        "linked_travel_request_id": c.linked_travel_request_id,
        "policy_flags_json": c.policy_flags_json or {},
        "created_at": c.created_at,
        "submitted_at": c.submitted_at,
        "line_items": [_line_dict(l) for l in c.line_items],
    }


async def _apply_policy(
    db, lines: List[LineIn],
) -> List[dict]:
    """Return per-line policy dicts (flag list + severity)."""
    cat_ids = [l.category_id for l in lines]
    cats = (await db.execute(
        select(ExpenseCategory).where(ExpenseCategory.id.in_(cat_ids))
    )).scalars().all()
    by_id = {c.id: c for c in cats}

    inputs: List[LineItemInput] = []
    for l in lines:
        c = by_id.get(l.category_id)
        inputs.append(LineItemInput(
            amount_paise=l.amount_paise,
            category_name=(c.name if c else ""),
            has_receipt=bool(l.receipt_url),
            line_date=l.line_date.isoformat() if l.line_date else None,
            per_diem_cap_paise=(c.per_diem_cap_paise if c else None),
            receipt_required_above_paise=(
                c.receipt_required_above_paise if c else None
            ),
            policy_mode=(c.policy_mode if c else "warn"),
        ))
    report = evaluate_policy(inputs)
    per_line = report.by_line()
    out = []
    for idx, l in enumerate(lines):
        flags = per_line.get(idx, [])
        out.append({
            "is_out_of_policy": bool(flags),
            "reason": "; ".join(f.reason for f in flags) or None,
            "severity": "block" if any(f.severity == "block" for f in flags)
                        else ("warn" if flags else None),
        })
    return out


@router.get("/claims")
async def list_claims(
    db: deps.DBDep,
    status_filter: Optional[str] = Query(None, alias="status"),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    stmt = select(ExpenseClaim).options(selectinload(ExpenseClaim.line_items))
    if status_filter:
        stmt = stmt.where(ExpenseClaim.status == status_filter)

    if not (_is_hr_or_admin(current_user) or _is_finance(current_user)):
        team = await _team_user_ids(db, current_user.id)
        # Employees see own; managers see own + team (via submitter_id).
        stmt = stmt.where(
            or_(
                ExpenseClaim.submitter_id == current_user.id,
                ExpenseClaim.submitter_id.in_(team) if team else False,
            )
        )
    stmt = stmt.order_by(ExpenseClaim.claim_date.desc(), ExpenseClaim.id.desc())
    rows = (await db.execute(stmt)).scalars().unique().all()
    return [_claim_dict(c) for c in rows]


@router.post("/claims")
async def create_claim(
    payload: ClaimIn,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    emp = await _employee_for(db, current_user.id)
    if not emp:
        raise HTTPException(400, "No employee record for this user")
    if not payload.line_items:
        raise HTTPException(400, "At least one line item required")

    total = sum_line_items([
        LineItemInput(amount_paise=l.amount_paise, category_name="",
                      has_receipt=bool(l.receipt_url))
        for l in payload.line_items
    ])
    policy_out = await _apply_policy(db, payload.line_items)

    claim = ExpenseClaim(
        employee_id=emp.id,
        submitter_id=current_user.id,
        title=payload.title, description=payload.description,
        claim_date=payload.claim_date,
        project_id=payload.project_id,
        cost_center=payload.cost_center,
        linked_travel_request_id=payload.linked_travel_request_id,
        total_amount_paise=total,
        status=ExpenseClaimStatus.DRAFT,
        policy_flags_json={"lines": policy_out},
    )
    for idx, l in enumerate(payload.line_items):
        flag = policy_out[idx]
        claim.line_items.append(ExpenseLineItem(
            category_id=l.category_id,
            amount_paise=l.amount_paise,
            line_date=l.line_date, description=l.description,
            receipt_url=l.receipt_url,
            is_out_of_policy=flag["is_out_of_policy"],
            policy_flag_reason=flag["reason"],
        ))
    db.add(claim)
    await db.commit()
    await db.refresh(claim)
    fresh = (await db.execute(
        select(ExpenseClaim).where(ExpenseClaim.id == claim.id)
        .options(selectinload(ExpenseClaim.line_items))
    )).scalar_one()
    await log_audit(
        db, current_user.id, "expense_claim_draft",
        "expense_claim", str(fresh.id),
        {"total_paise": total, "line_count": len(payload.line_items)},
        request,
    )
    return _claim_dict(fresh)


@router.post("/claims/{claim_id}/submit")
async def submit_claim(
    claim_id: int,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    claim = (await db.execute(
        select(ExpenseClaim).where(ExpenseClaim.id == claim_id)
        .options(selectinload(ExpenseClaim.line_items))
    )).scalar_one_or_none()
    if not claim:
        raise HTTPException(404, "Claim not found")
    if claim.submitter_id != current_user.id:
        raise HTTPException(403, "You may only submit your own claim")
    if claim.status != ExpenseClaimStatus.DRAFT:
        raise HTTPException(400, f"Claim status is {claim.status}")

    # Block-mode policy violations block submission.
    flags = (claim.policy_flags_json or {}).get("lines", [])
    if any(f.get("severity") == "block" for f in flags):
        raise HTTPException(
            400,
            "Claim contains block-mode policy violations. Fix lines "
            "or split into a separate claim.",
        )
    # Section K Item 2: receipt-required-above ALWAYS blocks at submit
    # (irrespective of category policy_mode). Re-run the policy engine
    # against the persisted lines to catch missing receipts even when
    # category.policy_mode is 'warn'.
    from app.services.expense import LineItemInput, evaluate_policy
    cat_ids = [ln.category_id for ln in claim.line_items if ln.category_id]
    cats = (await db.execute(
        select(ExpenseCategory).where(ExpenseCategory.id.in_(cat_ids))
    )).scalars().all()
    cat_by_id = {c.id: c for c in cats}
    submit_inputs = []
    for ln in claim.line_items:
        c = cat_by_id.get(ln.category_id) if ln.category_id else None
        submit_inputs.append(LineItemInput(
            amount_paise=ln.amount_paise,
            category_name=(c.name if c else ""),
            has_receipt=bool(ln.receipt_url),
            per_diem_cap_paise=(c.per_diem_cap_paise if c else None),
            receipt_required_above_paise=(
                c.receipt_required_above_paise if c else None
            ),
            policy_mode=(c.policy_mode if c else "warn"),
        ))
    submit_report = evaluate_policy(submit_inputs)
    receipt_missing = [
        f for f in submit_report.flags if "Receipt" in f.reason
    ]
    if receipt_missing:
        raise HTTPException(
            400,
            "Lines require receipts before submit: "
            + "; ".join(f"line #{f.line_index + 1}" for f in receipt_missing),
        )

    emp = await _employee_for(db, current_user.id)
    dept = emp.department if emp else None
    instance = await instantiate_for_entity(
        db=db,
        entity_type=ChainEntityType.EXPENSE,
        entity_id=claim.id,
        submitter=current_user,
        amount_paise=claim.total_amount_paise,
        department=dept,
        context={"claim_title": claim.title},
    )
    claim.approval_instance_id = instance.id
    claim.status = ExpenseClaimStatus.SUBMITTED
    claim.submitted_at = datetime.now(timezone.utc)
    # Auto-approve short-circuit — engine may have finalized already.
    if instance.status == ChainedApprovalStatus.APPROVED:
        claim.status = ExpenseClaimStatus.APPROVED
    await db.commit()

    await log_audit(
        db, current_user.id, "expense_claim_submit",
        "expense_claim", str(claim.id),
        {"instance_id": instance.id, "amount_paise": claim.total_amount_paise},
        request,
    )
    return _claim_dict(claim)


@router.post("/claims/{claim_id}/cancel")
async def cancel_claim(
    claim_id: int,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    claim = (await db.execute(
        select(ExpenseClaim).where(ExpenseClaim.id == claim_id)
        .options(selectinload(ExpenseClaim.line_items))
    )).scalar_one_or_none()
    if not claim:
        raise HTTPException(404, "Claim not found")
    if claim.submitter_id != current_user.id:
        raise HTTPException(403, "You may only cancel your own claim")
    if claim.status in (ExpenseClaimStatus.REIMBURSED,
                        ExpenseClaimStatus.PUSHED_TO_PAYROLL):
        raise HTTPException(400, "Cannot cancel a reimbursed claim")
    claim.status = ExpenseClaimStatus.CANCELLED
    await db.commit()
    await log_audit(
        db, current_user.id, "expense_claim_cancel",
        "expense_claim", str(claim.id), {}, request,
    )
    return _claim_dict(claim)


# ============================================================
# Finance queue + reimburse
# ============================================================


class ReimburseIn(BaseModel):
    mode: str = "direct"          # "direct" | "payroll"
    reference: Optional[str] = None
    payroll_run_id: Optional[int] = None


@router.get("/finance/queue")
async def finance_queue(
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    if not (_is_finance(current_user) or _is_hr_or_admin(current_user)):
        raise HTTPException(403, "Finance only")
    stmt = (
        select(ExpenseClaim)
        .where(ExpenseClaim.status == ExpenseClaimStatus.APPROVED)
        .options(selectinload(ExpenseClaim.line_items))
        .order_by(ExpenseClaim.claim_date.desc())
    )
    rows = (await db.execute(stmt)).scalars().unique().all()
    return [_claim_dict(c) for c in rows]


@router.post("/claims/{claim_id}/reimburse")
async def reimburse_claim(
    claim_id: int,
    payload: ReimburseIn,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    if not (_is_finance(current_user) or _is_hr_or_admin(current_user)):
        raise HTTPException(403, "Finance only")
    claim = (await db.execute(
        select(ExpenseClaim).where(ExpenseClaim.id == claim_id)
        .options(selectinload(ExpenseClaim.line_items))
    )).scalar_one_or_none()
    if not claim:
        raise HTTPException(404, "Claim not found")

    decision = decide_reimbursement(
        claim_status=claim.status,
        reimbursement_mode=claim.reimbursement_mode,
        reimbursed_at=claim.reimbursed_at,
        payroll_run_id=claim.payroll_run_id,
        requested_mode=payload.mode,
    )
    if not decision.can_reimburse:
        raise HTTPException(400, decision.reason or "Cannot reimburse")

    claim.reimbursement_mode = decision.mode
    if payload.mode == "direct":
        claim.reimbursed_at = datetime.now(timezone.utc)
        claim.reimbursed_reference = payload.reference
        claim.status = ExpenseClaimStatus.REIMBURSED
    else:  # payroll
        if not payload.payroll_run_id:
            raise HTTPException(
                400, "payroll_run_id is required for mode=payroll",
            )
        claim.payroll_run_id = payload.payroll_run_id
        claim.status = ExpenseClaimStatus.PUSHED_TO_PAYROLL
    await db.commit()

    # Notify the submitter.
    if claim.submitter_id:
        db.add(Notification(
            user_id=claim.submitter_id,
            title=f"Expense reimbursed via {decision.mode}",
            message=(
                f"Your expense claim '{claim.title}' has been "
                f"reimbursed via {decision.mode}."
            ),
            type="success",
            resource_type="expense_claim",
            resource_id=str(claim.id),
        ))
        await db.commit()
    await log_audit(
        db, current_user.id, "expense_reimburse",
        "expense_claim", str(claim.id),
        {"mode": decision.mode, "reference": payload.reference,
         "payroll_run_id": payload.payroll_run_id},
        request,
    )
    return _claim_dict(claim)


# ============================================================
# Travel requests
# ============================================================


class TravelIn(BaseModel):
    purpose: str
    from_city: str
    to_city: str
    start_date: date
    end_date: date
    estimated_cost_paise: int = 0
    advance_requested_paise: int = 0
    notes: Optional[str] = None


def _travel_dict(t: TravelRequest) -> dict:
    return {
        "id": t.id, "employee_id": t.employee_id,
        "submitter_id": t.submitter_id,
        "purpose": t.purpose,
        "from_city": t.from_city, "to_city": t.to_city,
        "start_date": t.start_date, "end_date": t.end_date,
        "estimated_cost_paise": t.estimated_cost_paise,
        "advance_requested_paise": t.advance_requested_paise,
        "advance_paid_paise": t.advance_paid_paise,
        "status": t.status,
        "approval_instance_id": t.approval_instance_id,
        "notes": t.notes,
        "created_at": t.created_at,
        "submitted_at": t.submitted_at,
    }


@router.get("/travel")
async def list_travel(
    db: deps.DBDep,
    status_filter: Optional[str] = Query(None, alias="status"),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    stmt = select(TravelRequest)
    if status_filter:
        stmt = stmt.where(TravelRequest.status == status_filter)
    if not (_is_hr_or_admin(current_user) or _is_finance(current_user)):
        team = await _team_user_ids(db, current_user.id)
        stmt = stmt.where(
            or_(
                TravelRequest.submitter_id == current_user.id,
                TravelRequest.submitter_id.in_(team) if team else False,
            )
        )
    stmt = stmt.order_by(TravelRequest.start_date.desc(), TravelRequest.id.desc())
    rows = (await db.execute(stmt)).scalars().all()
    return [_travel_dict(t) for t in rows]


@router.post("/travel")
async def create_travel(
    payload: TravelIn,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    emp = await _employee_for(db, current_user.id)
    if not emp:
        raise HTTPException(400, "No employee record for this user")
    if payload.end_date < payload.start_date:
        raise HTTPException(400, "end_date must be >= start_date")
    tr = TravelRequest(
        employee_id=emp.id,
        submitter_id=current_user.id,
        purpose=payload.purpose,
        from_city=payload.from_city, to_city=payload.to_city,
        start_date=payload.start_date, end_date=payload.end_date,
        estimated_cost_paise=payload.estimated_cost_paise,
        advance_requested_paise=payload.advance_requested_paise,
        notes=payload.notes,
        status=TravelRequestStatus.DRAFT,
    )
    db.add(tr)
    await db.commit()
    await db.refresh(tr)
    await log_audit(
        db, current_user.id, "travel_draft",
        "travel_request", str(tr.id), payload.model_dump(), request,
    )
    return _travel_dict(tr)


@router.post("/travel/{trip_id}/submit")
async def submit_travel(
    trip_id: int,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    tr = (await db.execute(
        select(TravelRequest).where(TravelRequest.id == trip_id)
    )).scalar_one_or_none()
    if not tr:
        raise HTTPException(404, "Travel request not found")
    if tr.submitter_id != current_user.id:
        raise HTTPException(403, "You may only submit your own request")
    if tr.status != TravelRequestStatus.DRAFT:
        raise HTTPException(400, f"Request status is {tr.status}")

    emp = await _employee_for(db, current_user.id)
    dept = emp.department if emp else None
    # Route on estimated cost + advance (whichever is larger).
    routing_amount = max(tr.estimated_cost_paise, tr.advance_requested_paise)
    instance = await instantiate_for_entity(
        db=db,
        entity_type=ChainEntityType.TRAVEL,
        entity_id=tr.id,
        submitter=current_user,
        amount_paise=routing_amount,
        department=dept,
        context={"purpose": tr.purpose},
    )
    tr.approval_instance_id = instance.id
    tr.status = TravelRequestStatus.SUBMITTED
    tr.submitted_at = datetime.now(timezone.utc)
    if instance.status == ChainedApprovalStatus.APPROVED:
        tr.status = TravelRequestStatus.APPROVED
    await db.commit()
    await log_audit(
        db, current_user.id, "travel_submit",
        "travel_request", str(tr.id),
        {"instance_id": instance.id, "amount_paise": routing_amount},
        request,
    )
    return _travel_dict(tr)


class AdvanceReconcileIn(BaseModel):
    actual_spend_paise: int


@router.post("/travel/{trip_id}/reconcile-advance")
async def reconcile_travel(
    trip_id: int,
    payload: AdvanceReconcileIn,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    if not (_is_finance(current_user) or _is_hr_or_admin(current_user)):
        raise HTTPException(403, "Finance only")
    tr = (await db.execute(
        select(TravelRequest).where(TravelRequest.id == trip_id)
    )).scalar_one_or_none()
    if not tr:
        raise HTTPException(404, "Travel request not found")
    r = reconcile_travel_advance(
        advance_paid_paise=tr.advance_paid_paise,
        actual_spend_paise=payload.actual_spend_paise,
    )
    tr.status = TravelRequestStatus.COMPLETED
    await db.commit()
    await log_audit(
        db, current_user.id, "travel_reconcile",
        "travel_request", str(tr.id),
        {
            "actual_spend_paise": payload.actual_spend_paise,
            "advance_paid_paise": tr.advance_paid_paise,
            "balance_paise": r.balance_paise,
            "surplus_paise": r.surplus_paise,
        },
        request,
    )
    return {
        "travel": _travel_dict(tr),
        "reconciliation": {
            "advance_paid_paise": r.advance_paid_paise,
            "actual_spend_paise": r.actual_spend_paise,
            "balance_paise": r.balance_paise,
            "surplus_paise": r.surplus_paise,
            "needs_recovery": r.needs_recovery,
            "needs_topup": r.needs_topup,
        },
    }
