from typing import Any, List, Optional, Annotated
from datetime import datetime, timezone, date, timedelta, time
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
import secrets
import hashlib
from sqlalchemy import select, and_, or_, func, delete
from sqlalchemy.orm import selectinload

from app.api import deps
from app.models.bd import (
    Lead, ActivityLog, LeadStage, EstimateVersion, EstimatePhase,
    EstimateResourceLine, EstimateStatus, ProposalSnapshot, QuotationVersion
)
from app.models.bd import Account
from app.models.user import User, Role, Permission
from app.schemas.user import UserLinkRead
from app.models.audit import AuditLog
from app.models.approval import ApprovalItem, ApprovalStep, ApprovalStatus
from app.models.project import Project, ProjectMember, Milestone, CostBaseline
from app.models.bid_task import (
    LeadBidTask,
    LeadBidTaskAssignment,
    LeadBidTaskReview,
    LeadBidTaskReviewStatus,
)
from app.models.task import Task, Subtask
from app.schemas.approval import ApprovalItemRead
from app.schemas.bd import (
    LeadRead, LeadCreate, LeadUpdate, LeadNested,
    ActivityLogRead, ActivityLogCreate, PipelineSummary,
    PipelineStageSummary, EstimateVersionDetailed, EstimateVersionRead,
    EstimateVersionCreate, EstimateVersionUpdate, EstimateCompareResponse,
    EstimateCompareItem, ProposalSnapshotRead, QuotationVersionRead,
    LeadToProjectConvert,
    BDDashboard, EstimateAccuracyReport,
    EstimateSubmitRequest,
)
from app.schemas.project import ProjectRead

_COMMON_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"description": "Bad request"},
    401: {"description": "Unauthorized"},
    403: {"description": "Forbidden"},
    404: {"description": "Not found"},
    409: {"description": "Conflict"},
    500: {"description": "Internal server error"},
}

router = APIRouter(responses=_COMMON_ERROR_RESPONSES)

_CONVERT_LEAD_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"description": "Bad request"},
    403: {"description": "Forbidden"},
    404: {"description": "Not found"},
}

BD_LEAD_READ = "bd lead read"
BD_LEAD_WRITE = "bd lead write"
BD_ESTIMATE_READ = "bd estimate read"
BD_ESTIMATE_WRITE = "bd estimate write"
BD_CONVERT_PROJECT = "bd convert to project"
BD_REPORT_VIEW = "bd report view"
EXEC_REPORT_VIEW = "executive report view"
LEAD_NOT_FOUND = "Lead not found"
ESTIMATE_NOT_FOUND = "Estimate not found"
QUOTATION_NOT_FOUND = "Quotation not found"
NOT_AUTHORIZED = "Not authorized"

LEAD_ESTIMATE_APPROVE = "lead estimate approve"


def _user_has_permission(user: User, permission_name: str) -> bool:
    roles = getattr(user, "roles", None) or []
    for role in roles:
        perms = getattr(role, "permissions", None) or []
        for perm in perms:
            if getattr(perm, "name", None) == permission_name:
                return True
    return False


def _quotation_not_found_exc(quotation_id: int) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "error": {
                "code": "QUOTATION_NOT_FOUND",
                "message": QUOTATION_NOT_FOUND,
                "details": {"quotation_id": quotation_id},
            }
        },
    )


async def get_subordinate_ids(db: deps.DBDep, manager_id: int) -> List[int]:
    """Helper to get all subordinate IDs recursively or just direct ones."""
    # For now, let's get direct subordinates to keep it simple
    result = await db.execute(
        select(User.id).where(User.manager_id == manager_id)
    )
    return list(result.scalars().all())


async def generate_unique_lead_id(db: deps.DBDep) -> str:
    """Generate a short, unique lead_id.

    Keeps within DB constraints (<= 20 chars).
    """
    prefix = datetime.now(timezone.utc).strftime("LD%y%m%d")
    for _ in range(100):
        suffix = f"{secrets.randbelow(10000):04d}"
        candidate = f"{prefix}{suffix}"  # e.g. LD2603050421
        existing = await db.execute(
            select(Lead.id).where(Lead.lead_id == candidate)
        )
        if existing.scalar_one_or_none() is None:
            return candidate
    raise RuntimeError("Unable to generate unique lead id")


async def _user_can_access_lead(
    db: deps.DBDep,
    current_user: User,
    lead: Lead,
) -> bool:
    if current_user.is_superuser:
        return True

    subordinate_ids = await get_subordinate_ids(db, current_user.id)
    if lead.owner_user_id == current_user.id:
        return True
    if subordinate_ids and lead.owner_user_id in subordinate_ids:
        return True

    assigned_check = await db.execute(
        select(EstimatePhase.id)
        .join(EstimateVersion, EstimatePhase.version_id == EstimateVersion.id)
        .where(
            and_(
                EstimateVersion.lead_id == lead.id,
                EstimatePhase.assigned_user_id == current_user.id,
            )
        )
        .limit(1)
    )
    if assigned_check.scalar_one_or_none() is not None:
        return True

    bid_task_assigned = await db.execute(
        select(LeadBidTaskAssignment.id)
        .join(LeadBidTask, LeadBidTaskAssignment.bid_task_id == LeadBidTask.id)
        .where(
            and_(
                LeadBidTask.lead_id == lead.id,
                LeadBidTaskAssignment.pm_user_id == current_user.id,
            )
        )
        .limit(1)
    )
    return bid_task_assigned.scalar_one_or_none() is not None


@router.get(
    "/dashboard",
    response_model=BDDashboard,
    responses=_COMMON_ERROR_RESPONSES,
)
async def get_bd_dashboard(
    db: deps.DBDep,
    current_user: Annotated[
        User,
        Depends(deps.check_permissions([BD_REPORT_VIEW])),
    ],
) -> Any:
    """
    Consolidated BD dashboard data including funnel, win/loss,
    and pipeline metrics.
    """
    # 1. Pipeline Summary (Reuse or similar logic)
    query = select(Lead)
    result = await db.execute(query)
    all_leads = result.scalars().all()

    pipeline_stages = []
    total_val = 0.0
    total_weighted = 0.0

    for stage in LeadStage:
        leads_in_stage = [ld for ld in all_leads if ld.stage == stage]
        count = len(leads_in_stage)
        val = sum(ld.estimated_value for ld in leads_in_stage)
        # Assuming probability from lead or stage-based fallback
        # (Lead has probability_percent)
        weighted = sum(
            ld.estimated_value * (ld.probability_percent / 100)
            for ld in leads_in_stage
        )

        pipeline_stages.append(
            PipelineStageSummary(
                stage=stage,
                count=count,
                total_value=val,
                weighted_value=weighted,
            )
        )
        total_val += val
        total_weighted += weighted

    pipeline = PipelineSummary(
        stages=pipeline_stages,
        total_count=len(all_leads),
        total_value=total_val,
        total_weighted_value=total_weighted
    )

    # 2. Closes this month
    now = datetime.now(timezone.utc)
    first_day = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    # Simple next month calc
    if now.month == 12:
        next_month = first_day.replace(year=now.year + 1, month=1)
    else:
        next_month = first_day.replace(month=now.month + 1)

    expected_closes = [
        ld for ld in all_leads
        if ld.expected_close_date
        and first_day.date() <= ld.expected_close_date < next_month.date()
        and ld.stage not in [LeadStage.WON, LeadStage.LOST]
    ]

    # 3. Win/Loss metrics (All time or rolling? Let's do all time for now)
    wins = [ld for ld in all_leads if ld.stage == LeadStage.WON]
    losses = [ld for ld in all_leads if ld.stage == LeadStage.LOST]
    
    total_decided = len(wins) + len(losses)
    win_rate = (len(wins) / total_decided * 100) if total_decided > 0 else 0.0

    # 4. Average Sales Cycle
    # Days from creation to WON status
    cycle_days = []
    for lead_won in wins:
        # Assuming updated_at is when it was moved to WON
        # (This is an approximation)
        delta = lead_won.updated_at - lead_won.created_at
        cycle_days.append(delta.days)
    
    avg_cycle = sum(cycle_days) / len(cycle_days) if cycle_days else 0.0

    return BDDashboard(
        pipeline=pipeline,
        expected_closes_this_month=len(expected_closes),
        win_count=len(wins),
        loss_count=len(losses),
        avg_sales_cycle_days=avg_cycle,
        win_rate_percent=win_rate,
    )


@router.get(
    "/reports/estimate-accuracy",
    response_model=EstimateAccuracyReport,
    responses=_COMMON_ERROR_RESPONSES,
)
async def get_estimate_accuracy_report(
    db: deps.DBDep,
    current_user: Annotated[
        User,
        Depends(deps.check_permissions([EXEC_REPORT_VIEW])),
    ],
) -> Any:
    """Calculate variance between approved estimates and project baselines."""
    # 1. Get all projects that came from a lead
    query = select(Project).where(Project.lead_id.is_not(None)).options(
        selectinload(Project.cost_baselines),
        selectinload(Project.lead).selectinload(Lead.estimates)
    )
    result = await db.execute(query)
    projects = result.scalars().all()

    variances = []
    for p in projects:
        if not p.lead:
            continue
        # Approved estimate for this lead (triggered conversion)
        approved_version = next(
            (
                v
                for v in p.lead.estimates
                if v.status == EstimateStatus.APPROVED
            ),
            None
        )
        if not approved_version:
            continue

        # Get actual active baseline (the current source of truth for budget)
        active_baseline = next(
            (b for b in p.cost_baselines if b.is_active),
            None,
        )
        if not active_baseline:
            continue

        est_price = float(approved_version.total_price_decimal)
        curr_price = float(active_baseline.amount)

        if est_price > 0:
            # Positive variance means cost overrun / scope expansion
            # Negative variance means delivered under budget
            variance = ((curr_price - est_price) / est_price) * 100
            variances.append(variance)

    avg_variance = sum(variances) / len(variances) if variances else 0.0

    return EstimateAccuracyReport(
        total_estimates=len(variances),
        avg_variance_percent=avg_variance,
    )


@router.get(
    "/pipeline",
    response_model=PipelineSummary,
    responses=_COMMON_ERROR_RESPONSES,
)
async def get_pipeline_summary(
    db: deps.DBDep,
    current_user: Annotated[
        User,
        Depends(deps.check_permissions([BD_LEAD_READ])),
    ],
) -> Any:
    # Build filter based on RLS
    filters = []
    if not current_user.is_superuser:
        subordinate_ids = await get_subordinate_ids(db, current_user.id)
        query_filters = [Lead.owner_user_id == current_user.id]
        if subordinate_ids:
            query_filters.append(Lead.owner_user_id.in_(subordinate_ids))
        filters.append(or_(*query_filters))

    # Aggregate by stage
    query = select(
        Lead.stage,
        func.count(Lead.id).label("lead_count"),
        func.sum(Lead.estimated_value).label("stage_total"),
        func.sum(
            Lead.estimated_value * Lead.probability_percent / 100
        ).label("stage_weighted")
    ).group_by(Lead.stage)

    if filters:
        query = query.where(and_(*filters))

    result = await db.execute(query)
    rows = result.all()

    stage_summaries = []
    total_count = 0
    total_value = 0.0
    total_weighted_value = 0.0

    # Initialize all stages with 0
    stage_data = {
        stage: {"count": 0, "total_value": 0.0, "weighted_value": 0.0}
        for stage in LeadStage
    }

    for row in rows:
        lead_count = int(row.lead_count or 0)
        stage_total = float(row.stage_total or 0)
        stage_weighted = float(row.stage_weighted or 0)

        stage_data[row.stage] = {
            "count": lead_count,
            "total_value": stage_total,
            "weighted_value": stage_weighted
        }
        total_count += lead_count
        total_value += stage_total
        total_weighted_value += stage_weighted

    for stage, data in stage_data.items():
        stage_summaries.append(PipelineStageSummary(
            stage=stage,
            count=int(data["count"]),
            total_value=data["total_value"],
            weighted_value=data["weighted_value"]
        ))

    return PipelineSummary(
        stages=stage_summaries,
        total_count=total_count,
        total_value=total_value,
        total_weighted_value=total_weighted_value
    )


@router.get(
    "/leads",
    response_model=List[LeadRead],
    responses=_COMMON_ERROR_RESPONSES,
)
async def list_leads(
    db: deps.DBDep,
    current_user: Annotated[
        User,
        Depends(deps.check_permissions([BD_LEAD_READ])),
    ],
    stage: Annotated[Optional[LeadStage], Query()] = None,
    owner_id: Annotated[Optional[int], Query()] = None,
    start_date: Annotated[Optional[datetime], Query()] = None,
    end_date: Annotated[Optional[datetime], Query()] = None,
    skip: int = 0,
    limit: int = 100
) -> Any:
    query = select(Lead)

    filters = []
    if stage:
        filters.append(Lead.stage == stage)
    if owner_id:
        filters.append(Lead.owner_user_id == owner_id)
    if start_date:
        filters.append(Lead.created_at >= start_date)
    if end_date:
        filters.append(Lead.created_at <= end_date)

    # Row Level Access
    # CEO, COO, Admin, BD Manager, DOP see ALL leads.
    _full_access_roles = {"ceo", "coo", "super admin", "admin", "dop", "bd manager"}
    _user_role_names = {
        str(getattr(r, "name", "")).strip().lower()
        for r in (getattr(current_user, "roles", None) or [])
    }
    _has_full_access = current_user.is_superuser or bool(_user_role_names & _full_access_roles)

    if not _has_full_access:
        subordinate_ids = await get_subordinate_ids(db, current_user.id)
        # Regular BD: own leads + subordinates' leads + estimate-assigned leads
        query_filters = [Lead.owner_user_id == current_user.id]
        if subordinate_ids:
            query_filters.append(Lead.owner_user_id.in_(subordinate_ids))

        assigned_lead_ids = (
            select(EstimateVersion.lead_id)
            .join(
                EstimatePhase,
                EstimatePhase.version_id == EstimateVersion.id,
            )
            .where(EstimatePhase.assigned_user_id == current_user.id)
        )
        query_filters.append(Lead.id.in_(assigned_lead_ids))

        filters.append(or_(*query_filters))

    if filters:
        query = query.where(and_(*filters))

    query = query.offset(skip).limit(limit).order_by(Lead.updated_at.desc())
    result = await db.execute(query)
    return result.scalars().all()


@router.post(
    "/leads",
    response_model=LeadRead,
    responses=_COMMON_ERROR_RESPONSES,
)
async def create_lead(
    *,
    db: deps.DBDep,
    lead_in: LeadCreate,
    current_user: Annotated[
        User,
        Depends(deps.check_permissions([BD_LEAD_WRITE])),
    ],
) -> Any:
    owner_user_id = lead_in.owner_user_id or current_user.id
    if not current_user.is_superuser and owner_user_id != current_user.id:
        subordinate_ids = await get_subordinate_ids(db, current_user.id)
        if owner_user_id not in subordinate_ids:
            raise HTTPException(
                status_code=403,
                detail="Not authorized to assign lead to this user",
            )

    lead_id = lead_in.lead_id
    if lead_id:
        existing = await db.execute(
            select(Lead.id).where(Lead.lead_id == lead_id)
        )
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=400,
                detail="Lead ID already exists",
            )
    else:
        try:
            lead_id = await generate_unique_lead_id(db)
        except RuntimeError as exc:
            raise HTTPException(
                status_code=500,
                detail=str(exc),
            ) from exc

    account_id = lead_in.account_id
    if not account_id and lead_in.account_name:
        existing_acc = await db.execute(
            select(Account).where(
                func.lower(Account.name)
                == lead_in.account_name.lower()
            )
        )
        acc = existing_acc.scalar_one_or_none()
        if not acc:
            acc = Account(name=lead_in.account_name)
            db.add(acc)
            await db.flush()
        account_id = acc.id

    payload = lead_in.model_dump(exclude={"account_name"}, exclude_unset=True)
    payload.update(
        {
            "lead_id": lead_id,
            "owner_user_id": owner_user_id,
            "account_id": account_id,
        }
    )

    db_obj = Lead(**payload)
    db.add(db_obj)

    # Audit log
    audit = AuditLog(
        user_id=current_user.id,
        action="create_lead",
        resource_type="lead",
        resource_id=lead_id,
        details={"title": lead_in.title, "account_id": account_id}
    )
    db.add(audit)

    await db.commit()
    await db.refresh(db_obj)
    return db_obj


@router.get(
    "/leads/{id}",
    response_model=LeadNested,
    responses=_COMMON_ERROR_RESPONSES,
)
async def get_lead(
    id: int,
    db: deps.DBDep,
    current_user: Annotated[
        User,
        Depends(deps.check_permissions([BD_LEAD_READ])),
    ],
) -> Any:
    query = select(Lead).where(Lead.id == id).options(
        selectinload(Lead.account),
        selectinload(Lead.contact),
        selectinload(Lead.activities)
    )
    result = await db.execute(query)
    lead = result.scalar_one_or_none()

    if not lead:
        raise HTTPException(status_code=404, detail=LEAD_NOT_FOUND)

    # Row Level Access Check
    if not await _user_can_access_lead(db, current_user, lead):
        raise HTTPException(
            status_code=403,
            detail="Not authorized to view this lead",
        )

    return lead


@router.patch(
    "/leads/{id}",
    response_model=LeadRead,
    responses=_COMMON_ERROR_RESPONSES,
)
async def update_lead(
    id: int,
    lead_in: LeadUpdate,
    db: deps.DBDep,
    current_user: Annotated[
        User,
        Depends(deps.check_permissions([BD_LEAD_WRITE])),
    ],
) -> Any:
    lead = await db.get(Lead, id)
    if not lead:
        raise HTTPException(status_code=404, detail=LEAD_NOT_FOUND)

    # Row Level Access Check
    if not current_user.is_superuser:
        subordinate_ids = await get_subordinate_ids(db, current_user.id)
        if (
            lead.owner_user_id != current_user.id and
            lead.owner_user_id not in subordinate_ids
        ):
            raise HTTPException(
                status_code=403,
                detail="Not authorized to update this lead"
            )

    update_data = lead_in.model_dump(exclude_unset=True)

    # Enforce conversion workflow for WON so that PM assignment and
    # project creation happen atomically.
    if update_data.get("stage") == LeadStage.WON:
        raise HTTPException(
            status_code=400,
            detail="Use convert-to-project to mark a lead as WON",
        )

    # Audit stage change
    if "stage" in update_data and update_data["stage"] != lead.stage:
        audit = AuditLog(
            user_id=current_user.id,
            action="update_lead_stage",
            resource_type="lead",
            resource_id=lead.lead_id,
            details={
                "old_stage": lead.stage,
                "new_stage": update_data["stage"]
            }
        )
        db.add(audit)

    for field in update_data:
        setattr(lead, field, update_data[field])

    db.add(lead)

    # General update audit
    audit = AuditLog(
        user_id=current_user.id,
        action="update_lead",
        resource_type="lead",
        resource_id=lead.lead_id,
        details={"updated_fields": list(update_data.keys())}
    )
    db.add(audit)

    await db.commit()
    await db.refresh(lead)
    return lead


@router.post(
    "/leads/{id}/activities",
    response_model=ActivityLogRead,
    responses=_COMMON_ERROR_RESPONSES,
)
async def create_lead_activity(
    id: int,
    activity_in: ActivityLogCreate,
    db: deps.DBDep,
    current_user: Annotated[
        User,
        Depends(deps.check_permissions([BD_LEAD_WRITE])),
    ],
) -> Any:
    lead = await db.get(Lead, id)
    if not lead:
        raise HTTPException(status_code=404, detail=LEAD_NOT_FOUND)

    # Row Level Access Check
    if not current_user.is_superuser:
        subordinate_ids = await get_subordinate_ids(db, current_user.id)
        if (
            lead.owner_user_id != current_user.id and
            lead.owner_user_id not in subordinate_ids
        ):
            raise HTTPException(status_code=403, detail=NOT_AUTHORIZED)

    db_obj = ActivityLog(
        **activity_in.model_dump(),
        lead_id=id,
        created_by_id=current_user.id
    )
    db.add(db_obj)

    # Audit log
    audit = AuditLog(
        user_id=current_user.id,
        action="add_lead_activity",
        resource_type="lead",
        resource_id=lead.lead_id,
        details={"type": activity_in.type, "summary": activity_in.summary}
    )
    db.add(audit)

    await db.commit()
    await db.refresh(db_obj)
    return db_obj


@router.get(
    "/leads/{id}/activities",
    response_model=List[ActivityLogRead],
    responses=_COMMON_ERROR_RESPONSES,
)
async def get_lead_activities(
    id: int,
    db: deps.DBDep,
    current_user: Annotated[
        User,
        Depends(deps.check_permissions([BD_LEAD_READ])),
    ],
) -> Any:
    lead = await db.get(Lead, id)
    if not lead:
        raise HTTPException(status_code=404, detail=LEAD_NOT_FOUND)

    # Row Level Access Check
    if not await _user_can_access_lead(db, current_user, lead):
        raise HTTPException(status_code=403, detail=NOT_AUTHORIZED)

    result = await db.execute(
        select(ActivityLog)
        .where(ActivityLog.lead_id == id)
        .order_by(ActivityLog.created_at.desc())
    )
    return result.scalars().all()


# --- Estimate Endpoints ---

def calculate_estimate_totals(
    version: EstimateVersion,
    resource_lines: List[EstimateResourceLine] | None = None,
) -> None:
    """Server-side calculation of estimate totals."""
    if resource_lines is not None:
        lines = resource_lines
    else:
        lines = version.resource_lines
    total_cost = Decimal(sum(line.cost_decimal for line in lines))
    version.total_cost_decimal = float(total_cost)

    # contingency calculation
    cost_with_contingency = total_cost * Decimal(
        1 + (version.contingency_percent or 0.0) / 100
    )

    # margin calculation: price = cost / (1 - margin)
    margin = (version.margin_percent or 0.0)
    if margin >= 100:
        # Fallback: avoid division by ~zero.
        version.total_price_decimal = float(cost_with_contingency * 2)
    else:
        version.total_price_decimal = float(
            cost_with_contingency
            / Decimal(1 - margin / 100)
        )


@router.post(
    "/leads/{id}/estimates",
    response_model=EstimateVersionDetailed,
    responses=_COMMON_ERROR_RESPONSES,
)
async def create_estimate(
    *,
    id: int,
    db: deps.DBDep,
    estimate_in: EstimateVersionCreate,
    current_user: Annotated[
        User,
        Depends(deps.check_permissions([BD_ESTIMATE_WRITE])),
    ],
) -> Any:
    lead = await db.get(Lead, id)
    if not lead:
        raise HTTPException(status_code=404, detail=LEAD_NOT_FOUND)

    if not await _user_can_access_lead(db, current_user, lead):
        raise HTTPException(status_code=403, detail=NOT_AUTHORIZED)

    # Get latest version number
    result = await db.execute(
        select(func.max(EstimateVersion.version_number))
        .where(EstimateVersion.lead_id == id)
    )
    max_v = result.scalar() or 0

    db_version = EstimateVersion(
        lead_id=id,
        version_number=max_v + 1,
        name=estimate_in.name,
        assumptions=estimate_in.assumptions,
        scope_included=estimate_in.scope_included,
        scope_excluded=estimate_in.scope_excluded,
        currency=estimate_in.currency,
        contingency_percent=estimate_in.contingency_percent,
        margin_percent=estimate_in.margin_percent,
        created_by_id=current_user.id
    )
    db.add(db_version)

    # Add phases
    for p_in in estimate_in.phases:
        phase = EstimatePhase(**p_in.model_dump(), version=db_version)
        db.add(phase)

    # Add resource lines
    added_lines = []
    for r_in in estimate_in.resource_lines:
        line = EstimateResourceLine(**r_in.model_dump(), version=db_version)
        db.add(line)
        added_lines.append(line)

    # Calculate totals
    calculate_estimate_totals(db_version, resource_lines=added_lines)

    # Audit log
    audit = AuditLog(
        user_id=current_user.id,
        action="create_estimate",
        resource_type="estimate",
        resource_id=f"LEAD-{lead.lead_id}-V{db_version.version_number}",
        details={"name": estimate_in.name},
    )
    db.add(audit)

    await db.flush()
    db_version_id = db_version.id

    await db.commit()

    # Eager load for the response schema
    query = (
        select(EstimateVersion)
        .where(EstimateVersion.id == db_version_id)
        .options(
            selectinload(EstimateVersion.phases),
            selectinload(EstimateVersion.resource_lines),
        )
    )
    result = await db.execute(query)
    return result.scalar_one()


@router.get(
    "/leads/{id}/estimates",
    response_model=List[EstimateVersionRead],
    responses=_COMMON_ERROR_RESPONSES,
)
async def list_lead_estimates(
    id: int,
    db: deps.DBDep,
    current_user: Annotated[
        User,
        Depends(deps.check_permissions([BD_ESTIMATE_READ])),
    ],
) -> Any:
    lead = await db.get(Lead, id)
    if not lead:
        raise HTTPException(status_code=404, detail=LEAD_NOT_FOUND)

    if not await _user_can_access_lead(db, current_user, lead):
        raise HTTPException(status_code=403, detail=NOT_AUTHORIZED)

    result = await db.execute(
        select(EstimateVersion)
        .where(EstimateVersion.lead_id == id)
        .order_by(EstimateVersion.version_number.desc())
    )
    return result.scalars().all()


@router.get(
    "/users/project-managers",
    response_model=List[UserLinkRead],
    responses=_COMMON_ERROR_RESPONSES,
)
async def list_project_managers_for_bd(
    db: deps.DBDep,
    current_user: Annotated[
        User,
        Depends(deps.check_permissions([BD_LEAD_READ])),
    ],
) -> Any:
    """List active users who can act as Project Managers.

    Used by BD for assignment/conversion.
    """
    result = await db.execute(
        select(User)
        .join(User.roles)
        .where(and_(User.is_active.is_(True), Role.name == "PM"))
        .order_by(User.full_name)
    )
    users = result.scalars().unique().all()
    return [UserLinkRead.model_validate(u) for u in users]


@router.get(
    "/users/coo-users",
    response_model=List[UserLinkRead],
    responses=_COMMON_ERROR_RESPONSES,
)
async def list_coo_users_for_bd(
    db: deps.DBDep,
    current_user: Annotated[
        User,
        Depends(deps.check_permissions([BD_LEAD_READ])),
    ],
) -> Any:
    """Active users eligible to be a project's portfolio manager.

    Primary: COO. CEO and Super Admin are accepted as fallbacks so the
    conversion flow doesn't break in a setup where no dedicated COO has
    been assigned yet — they outrank COO and can stand in.

    Lead-agnostic. For conversion screens prefer
    /bd/leads/{id}/eligible-portfolio-managers which applies BD scoping.
    """
    portfolio_roles = ("COO", "CEO", "Super Admin", "Admin")
    result = await db.execute(
        select(User)
        .join(User.roles)
        .where(and_(User.is_active.is_(True), Role.name.in_(portfolio_roles)))
        .order_by(User.full_name)
    )
    users = result.scalars().unique().all()
    return [UserLinkRead.model_validate(u) for u in users]


PORTFOLIO_BASE_ROLES = ("COO", "CEO", "Super Admin", "Admin")
BD_ROLE_NAME = "Business Developer"


async def _eligible_portfolio_managers(
    db: deps.DBDep,
    current_user: User,
    lead: Lead,
) -> List[User]:
    """Compute the eligible portfolio-manager list for a (selector, lead).

    Rules:
    - Always: active users with COO / CEO / Super Admin / Admin role.
    - If the selector is a Business Developer: the only BD allowed is
      the selector themselves (and only if active).
    - If the selector is NOT a BD: also include the lead's owning user
      if they are an active BD.
    """
    selector_role_names = {
        (r.name or "").strip() for r in (current_user.roles or [])
    }
    base = (await db.execute(
        select(User)
        .join(User.roles)
        .where(and_(User.is_active.is_(True), Role.name.in_(PORTFOLIO_BASE_ROLES)))
    )).scalars().unique().all()
    pool: dict[int, User] = {u.id: u for u in base}

    selector_is_bd = BD_ROLE_NAME in selector_role_names
    if selector_is_bd:
        if current_user.is_active:
            pool[current_user.id] = current_user
    elif lead.owner_user_id:
        owner = await db.get(User, lead.owner_user_id)
        if owner and owner.is_active:
            owner_roles = {
                (r.name or "").strip() for r in (owner.roles or [])
            }
            if BD_ROLE_NAME in owner_roles:
                pool[owner.id] = owner

    return sorted(pool.values(), key=lambda u: (u.full_name or "").lower())


@router.get(
    "/leads/{id}/eligible-portfolio-managers",
    response_model=List[UserLinkRead],
    responses=_COMMON_ERROR_RESPONSES,
)
async def list_eligible_portfolio_managers(
    id: int,
    db: deps.DBDep,
    current_user: Annotated[
        User,
        Depends(deps.check_permissions([BD_LEAD_READ])),
    ],
) -> Any:
    """Eligible portfolio managers for converting THIS lead.

    Returns COO/CEO/Admin/Super Admin always, plus the lead's owning BD
    (or the selector themselves if the selector is a BD).
    """
    lead = await _load_lead_for_conversion(db=db, lead_id=id)
    if not lead:
        raise HTTPException(status_code=404, detail=LEAD_NOT_FOUND)
    if not await _user_can_access_lead(db, current_user, lead):
        raise HTTPException(status_code=403, detail="Not authorized")

    users = await _eligible_portfolio_managers(db, current_user, lead)
    return [UserLinkRead.model_validate(u) for u in users]


@router.get(
    "/users/estimate-approvers",
    response_model=List[UserLinkRead],
    responses=_COMMON_ERROR_RESPONSES,
)
async def list_estimate_approvers_for_bd(
    db: deps.DBDep,
    current_user: Annotated[
        User,
        Depends(deps.check_permissions([BD_ESTIMATE_READ])),
    ],
) -> Any:
    """List active users who can approve lead estimate value."""
    result = await db.execute(
        select(User)
        .join(User.roles)
        .join(Role.permissions)
        .where(
            and_(
                User.is_active.is_(True),
                Permission.name == LEAD_ESTIMATE_APPROVE,
            )
        )
        .order_by(User.full_name)
    )
    users = result.scalars().unique().all()
    return [UserLinkRead.model_validate(u) for u in users]


@router.get(
    "/estimates/{version_id}",
    response_model=EstimateVersionDetailed,
    responses=_COMMON_ERROR_RESPONSES,
)
async def get_estimate(
    version_id: int,
    db: deps.DBDep,
    current_user: Annotated[
        User,
        Depends(deps.check_permissions([BD_ESTIMATE_READ])),
    ],
) -> Any:
    query = select(EstimateVersion).where(
        EstimateVersion.id == version_id
    ).options(
        selectinload(EstimateVersion.phases),
        selectinload(EstimateVersion.resource_lines)
    )
    result = await db.execute(query)
    version = result.scalar_one_or_none()
    if not version:
        raise HTTPException(status_code=404, detail=ESTIMATE_NOT_FOUND)

    lead = await db.get(Lead, version.lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail=LEAD_NOT_FOUND)
    if not await _user_can_access_lead(db, current_user, lead):
        raise HTTPException(status_code=403, detail=NOT_AUTHORIZED)
    return version


@router.patch(
    "/estimates/{version_id}",
    response_model=EstimateVersionDetailed,
    responses=_COMMON_ERROR_RESPONSES,
)
async def update_estimate(
    *,
    version_id: int,
    db: deps.DBDep,
    estimate_in: EstimateVersionUpdate,
    current_user: Annotated[
        User,
        Depends(deps.check_permissions([BD_ESTIMATE_WRITE])),
    ],
) -> Any:
    query = select(EstimateVersion).where(
        EstimateVersion.id == version_id
    ).options(
        selectinload(EstimateVersion.phases),
        selectinload(EstimateVersion.resource_lines)
    )
    result = await db.execute(query)
    version = result.scalar_one_or_none()
    if not version:
        raise HTTPException(status_code=404, detail=ESTIMATE_NOT_FOUND)

    lead = await db.get(Lead, version.lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail=LEAD_NOT_FOUND)
    if not await _user_can_access_lead(db, current_user, lead):
        raise HTTPException(status_code=403, detail=NOT_AUTHORIZED)

    if version.status not in [EstimateStatus.DRAFT]:
        raise HTTPException(
            status_code=400,
            detail="Only draft estimates can be edited"
        )

    # Update basic fields
    update_data = estimate_in.model_dump(
        exclude_unset=True,
        exclude={'phases', 'resource_lines'}
    )
    for field, value in update_data.items():
        setattr(version, field, value)

    # Update phases if provided
    if estimate_in.phases is not None:
        # Simple implementation: clear and recreate
        await db.execute(
            delete(EstimatePhase).where(EstimatePhase.version_id == version_id)
        )
        for p_in in estimate_in.phases:
            phase = EstimatePhase(**p_in.model_dump(), version_id=version_id)
            db.add(phase)

    # Update resource lines if provided
    updated_lines = None
    if estimate_in.resource_lines is not None:
        await db.execute(
            delete(EstimateResourceLine).where(
                EstimateResourceLine.version_id == version_id
            )
        )
        updated_lines = []
        for r_in in estimate_in.resource_lines:
            line = EstimateResourceLine(
                **r_in.model_dump(),
                version_id=version_id
            )
            db.add(line)
            updated_lines.append(line)

    # Re-calculate
    calculate_estimate_totals(version, resource_lines=updated_lines)

    # Audit
    audit = AuditLog(
        user_id=current_user.id,
        action="update_estimate",
        resource_type="estimate",
        resource_id=f"ID-{version_id}",
        details={"name": version.name}
    )
    db.add(audit)

    await db.commit()

    # Eager load for return
    q = (
        select(EstimateVersion)
        .where(EstimateVersion.id == version_id)
        .options(
            selectinload(EstimateVersion.phases),
            selectinload(EstimateVersion.resource_lines),
        )
    )
    res = await db.execute(q)
    return res.scalar_one()


@router.post(
    "/estimates/{version_id}/submit",
    response_model=EstimateVersionRead,
    responses=_COMMON_ERROR_RESPONSES,
)
async def submit_estimate(
    version_id: int,
    submit_in: EstimateSubmitRequest,
    db: deps.DBDep,
    current_user: Annotated[
        User,
        Depends(deps.check_permissions([BD_ESTIMATE_WRITE])),
    ],
) -> Any:
    version = await db.get(EstimateVersion, version_id)
    if not version:
        raise HTTPException(status_code=404, detail=ESTIMATE_NOT_FOUND)

    lead = await db.get(Lead, version.lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail=LEAD_NOT_FOUND)
    if not await _user_can_access_lead(db, current_user, lead):
        raise HTTPException(status_code=403, detail=NOT_AUTHORIZED)

    # Check for existing pending approval
    pending_query = select(ApprovalItem).where(
        and_(
            ApprovalItem.resource_type == "estimate",
            ApprovalItem.resource_id == str(version_id),
            ApprovalItem.status == ApprovalStatus.PENDING
        )
    )
    p_res = await db.execute(pending_query)
    if p_res.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail="There is already a pending approval for this estimate"
        )

    # Validate chosen initial approver is eligible.
    approver = await db.get(User, submit_in.approver_id)
    if not approver or not approver.is_active:
        raise HTTPException(
            status_code=400,
            detail="Selected approver not found or inactive",
        )
    if not (
        approver.is_superuser
        or _user_has_permission(approver, LEAD_ESTIMATE_APPROVE)
    ):
        raise HTTPException(
            status_code=400,
            detail="Selected approver is not eligible to approve estimates",
        )

    approval_item = ApprovalItem(
        resource_type="estimate",
        resource_id=str(version_id),
        status=ApprovalStatus.PENDING,
        requested_by_id=current_user.id
    )
    db.add(approval_item)
    await db.flush()

    # Step 1: explicitly assigned approver (single-step-at-a-time flow).
    db.add(
        ApprovalStep(
            approval_item_id=approval_item.id,
            step_number=1,
            approver_id=approver.id,
            status=ApprovalStatus.PENDING,
        )
    )

    version.status = EstimateStatus.SUBMITTED

    # Audit
    audit = AuditLog(
        user_id=current_user.id,
        action="submit_estimate",
        resource_type="estimate",
        resource_id=f"ID-{version_id}",
        details={
            "name": version.name,
            "approval_item_id": approval_item.id,
            "initial_approver_id": approver.id,
        }
    )
    db.add(audit)

    await db.commit()
    await db.refresh(version)
    return version


@router.get(
    "/leads/{id}/estimate-approvals",
    response_model=List[ApprovalItemRead],
    responses=_COMMON_ERROR_RESPONSES,
)
async def get_lead_estimate_approvals(
    id: int,
    db: deps.DBDep,
    current_user: Annotated[
        User,
        Depends(deps.check_permissions([BD_ESTIMATE_READ])),
    ],
) -> Any:
    """List all approval requests for estimates related to this lead."""
    v_query = select(EstimateVersion.id).where(EstimateVersion.lead_id == id)
    v_res = await db.execute(v_query)
    v_ids = [str(vid) for vid in v_res.scalars().all()]

    if not v_ids:
        return []

    a_query = select(ApprovalItem).where(
        and_(
            ApprovalItem.resource_type == "estimate",
            ApprovalItem.resource_id.in_(v_ids)
        )
    ).options(selectinload(ApprovalItem.steps))

    result = await db.execute(a_query)
    return result.scalars().all()


@router.post(
    "/estimates/{version_id}/archive",
    response_model=EstimateVersionRead,
    responses=_COMMON_ERROR_RESPONSES,
)
async def archive_estimate(
    version_id: int,
    db: deps.DBDep,
    current_user: Annotated[
        User,
        Depends(deps.check_permissions([BD_ESTIMATE_WRITE])),
    ],
) -> Any:
    version = await db.get(EstimateVersion, version_id)
    if not version:
        raise HTTPException(status_code=404, detail=ESTIMATE_NOT_FOUND)

    lead = await db.get(Lead, version.lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail=LEAD_NOT_FOUND)
    if not await _user_can_access_lead(db, current_user, lead):
        raise HTTPException(status_code=403, detail=NOT_AUTHORIZED)

    version.status = EstimateStatus.ARCHIVED

    await db.commit()
    await db.refresh(version)
    return version


@router.get(
    "/estimates/{version_id}/compare",
    response_model=EstimateCompareResponse,
    responses=_COMMON_ERROR_RESPONSES,
)
async def compare_estimates(
    version_id: int,
    other_id: int,
    db: deps.DBDep,
    current_user: Annotated[
        User,
        Depends(deps.check_permissions([BD_ESTIMATE_READ])),
    ],
) -> Any:
    async def get_detailed(vid):
        q = select(EstimateVersion).where(
            EstimateVersion.id == vid
        ).options(
            selectinload(EstimateVersion.phases),
            selectinload(EstimateVersion.resource_lines)
        )
        res = await db.execute(q)
        return res.scalar_one_or_none()

    v_a = await get_detailed(version_id)
    v_b = await get_detailed(other_id)

    if not v_a or not v_b:
        raise HTTPException(
            status_code=404,
            detail="One or both estimates not found"
        )

    lead_a = await db.get(Lead, v_a.lead_id)
    lead_b = await db.get(Lead, v_b.lead_id)
    if not lead_a or not lead_b:
        raise HTTPException(status_code=404, detail=LEAD_NOT_FOUND)
    if not await _user_can_access_lead(db, current_user, lead_a):
        raise HTTPException(status_code=403, detail=NOT_AUTHORIZED)
    if not await _user_can_access_lead(db, current_user, lead_b):
        raise HTTPException(status_code=403, detail=NOT_AUTHORIZED)

    def to_compare_item(v):
        return EstimateCompareItem(
            id=v.id,
            version_number=v.version_number,
            name=v.name,
            status=v.status,
            total_cost=v.total_cost_decimal,
            total_price=v.total_price_decimal,
            margin_percent=v.margin_percent,
            contingency_percent=v.contingency_percent,
            resource_count=len(v.resource_lines),
            phase_count=len(v.phases)
        )

    return EstimateCompareResponse(
        version_a=v_a,
        version_b=v_b,
        summary_a=to_compare_item(v_a),
        summary_b=to_compare_item(v_b)
    )


@router.post(
    "/estimates/{version_id}/generate-proposal",
    response_model=ProposalSnapshotRead,
    responses=_COMMON_ERROR_RESPONSES,
)
async def generate_proposal_snapshot(
    version_id: int,
    db: deps.DBDep,
    current_user: Annotated[
        User,
        Depends(deps.check_permissions([BD_ESTIMATE_READ])),
    ],
) -> Any:
    """
    Renders the estimate into a stable JSON snapshot for proposal generation.
    """
    query = select(EstimateVersion).where(
        EstimateVersion.id == version_id
    ).options(
        selectinload(EstimateVersion.phases),
        selectinload(EstimateVersion.resource_lines),
        selectinload(EstimateVersion.lead).selectinload(Lead.account),
        selectinload(EstimateVersion.lead).selectinload(Lead.contact)
    )
    result = await db.execute(query)
    version = result.scalar_one_or_none()

    if not version:
        raise HTTPException(status_code=404, detail=ESTIMATE_NOT_FOUND)

    if not await _user_can_access_lead(db, current_user, version.lead):
        raise HTTPException(status_code=403, detail=NOT_AUTHORIZED)

    # Render data payload
    snapshot_data = {
        "proposal_info": {
            "version_name": version.name,
            "version_number": version.version_number,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "generated_by": current_user.full_name
        },
        "lead_info": {
            "title": version.lead.title,
            "account": (
                version.lead.account.name if version.lead.account else "N/A"
            ),
            "contact": (
                version.lead.contact.full_name
                if version.lead.contact else "N/A"
            )
        },
        "financial_summary": {
            "total_price": float(version.total_price_decimal),
            "currency": version.currency,
            "margin_percent": version.margin_percent,
            "contingency_percent": version.contingency_percent
        },
        "scope": {
            "included": version.scope_included,
            "excluded": version.scope_excluded,
            "assumptions": version.assumptions
        },
        "phases": [
            {
                "name": p.phase_name,
                "duration": p.duration_days,
                "description": p.description
            } for p in version.phases
        ]
    }

    db_obj = ProposalSnapshot(
        version_id=version_id,
        snapshot_data=snapshot_data
    )
    db.add(db_obj)

    # Audit
    audit = AuditLog(
        user_id=current_user.id,
        action="generate_proposal",
        resource_type="estimate",
        resource_id=f"ID-{version_id}",
        details={"snapshot_id": db_obj.id}
    )
    db.add(audit)

    await db.commit()
    await db.refresh(db_obj)
    return db_obj


@router.get(
    "/estimates/{version_id}/quotations",
    response_model=List[QuotationVersionRead],
    responses=_COMMON_ERROR_RESPONSES,
)
async def list_quotation_versions(
    version_id: int,
    db: deps.DBDep,
    current_user: Annotated[
        User,
        Depends(deps.check_permissions([BD_ESTIMATE_READ])),
    ],
) -> Any:
    version = await db.get(EstimateVersion, version_id)
    if not version:
        raise HTTPException(status_code=404, detail=ESTIMATE_NOT_FOUND)
    lead = await db.get(Lead, version.lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail=LEAD_NOT_FOUND)
    if not await _user_can_access_lead(db, current_user, lead):
        raise HTTPException(status_code=403, detail=NOT_AUTHORIZED)

    q = (
        select(QuotationVersion)
        .where(QuotationVersion.estimate_version_id == version_id)
        .order_by(QuotationVersion.version_number.desc())
    )
    res = await db.execute(q)
    return list(res.scalars().all())


@router.post(
    "/estimates/{version_id}/quotations",
    response_model=QuotationVersionRead,
    responses=_COMMON_ERROR_RESPONSES,
)
async def generate_quotation_pdf(
    version_id: int,
    db: deps.DBDep,
    current_user: Annotated[
        User,
        Depends(deps.check_permissions([BD_ESTIMATE_WRITE])),
    ],
) -> Any:
    from app.services.quotation_pdf import render_quotation_pdf

    query = select(EstimateVersion).where(
        EstimateVersion.id == version_id
    ).options(
        selectinload(EstimateVersion.phases),
        selectinload(EstimateVersion.resource_lines),
        selectinload(EstimateVersion.lead).selectinload(Lead.account),
        selectinload(EstimateVersion.lead).selectinload(Lead.contact)
    )
    result = await db.execute(query)
    version = result.scalar_one_or_none()
    if not version:
        raise HTTPException(status_code=404, detail=ESTIMATE_NOT_FOUND)

    if not await _user_can_access_lead(db, current_user, version.lead):
        raise HTTPException(status_code=403, detail=NOT_AUTHORIZED)

    max_res = await db.execute(
        select(func.max(QuotationVersion.version_number)).where(
            QuotationVersion.estimate_version_id == version_id
        )
    )
    next_number = (max_res.scalar_one_or_none() or 0) + 1

    snapshot_data = {
        "proposal_info": {
            "version_name": version.name,
            "version_number": version.version_number,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "generated_by": current_user.full_name,
            "quotation_version": next_number,
        },
        "lead_info": {
            "title": version.lead.title,
            "account": (
                version.lead.account.name if version.lead.account else "N/A"
            ),
            "contact": (
                version.lead.contact.full_name
                if version.lead.contact else "N/A"
            )
        },
        "financial_summary": {
            "total_price": float(version.total_price_decimal),
            "currency": version.currency,
            "margin_percent": version.margin_percent,
            "contingency_percent": version.contingency_percent
        },
        "scope": {
            "included": version.scope_included,
            "excluded": version.scope_excluded,
            "assumptions": version.assumptions
        },
        "phases": [
            {
                "name": p.phase_name,
                "duration": p.duration_days,
                "description": p.description
            } for p in version.phases
        ]
    }

    pdf_bytes = render_quotation_pdf(snapshot_data)
    sha = hashlib.sha256(pdf_bytes).hexdigest()
    filename = f"quotation_estimate_{version_id}_qv{next_number}.pdf"

    db_obj = QuotationVersion(
        estimate_version_id=version_id,
        version_number=next_number,
        status="generated",
        filename=filename,
        mime_type="application/pdf",
        sha256=sha,
        snapshot_data=snapshot_data,
        pdf_data=pdf_bytes,
        created_by_id=current_user.id
    )
    db.add(db_obj)

    audit = AuditLog(
        user_id=current_user.id,
        action="generate_quotation_pdf",
        resource_type="estimate",
        resource_id=f"ID-{version_id}",
        details={"quotation_version": next_number}
    )
    db.add(audit)

    await db.flush()
    audit.details = {
        "quotation_id": db_obj.id,
        "quotation_version": next_number,
    }
    await db.commit()
    await db.refresh(db_obj)
    return db_obj


@router.get(
    "/quotations/{quotation_id}",
    response_model=QuotationVersionRead,
    responses=_COMMON_ERROR_RESPONSES,
)
async def get_quotation_metadata(
    quotation_id: int,
    db: deps.DBDep,
    current_user: Annotated[
        User,
        Depends(deps.check_permissions([BD_ESTIMATE_READ])),
    ],
) -> Any:
    quotation = await db.get(QuotationVersion, quotation_id)
    if not quotation:
        raise _quotation_not_found_exc(quotation_id)

    version = await db.get(EstimateVersion, quotation.estimate_version_id)
    if not version:
        raise HTTPException(status_code=404, detail=ESTIMATE_NOT_FOUND)
    lead = await db.get(Lead, version.lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail=LEAD_NOT_FOUND)
    if not await _user_can_access_lead(db, current_user, lead):
        raise HTTPException(status_code=403, detail=NOT_AUTHORIZED)

    return quotation


@router.get(
    "/quotations/{quotation_id}/pdf",
    responses=_COMMON_ERROR_RESPONSES,
)
async def download_quotation_pdf(
    quotation_id: int,
    db: deps.DBDep,
    current_user: Annotated[
        User,
        Depends(deps.check_permissions([BD_ESTIMATE_READ])),
    ],
) -> Any:
    quotation = await db.get(QuotationVersion, quotation_id)
    if not quotation:
        raise _quotation_not_found_exc(quotation_id)

    version = await db.get(EstimateVersion, quotation.estimate_version_id)
    if not version:
        raise HTTPException(status_code=404, detail=ESTIMATE_NOT_FOUND)
    lead = await db.get(Lead, version.lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail=LEAD_NOT_FOUND)
    if not await _user_can_access_lead(db, current_user, lead):
        raise HTTPException(status_code=403, detail=NOT_AUTHORIZED)

    audit = AuditLog(
        user_id=current_user.id,
        action="download_quotation_pdf",
        resource_type="quotation",
        resource_id=f"ID-{quotation_id}",
        details={"estimate_version_id": quotation.estimate_version_id}
    )
    db.add(audit)
    await db.commit()

    headers = {
        "Content-Disposition": f"attachment; filename=\"{quotation.filename}\""
    }
    return Response(
        content=quotation.pdf_data,
        media_type=quotation.mime_type or "application/pdf",
        headers=headers,
    )


async def _load_lead_for_conversion(
    *,
    db: deps.DBDep,
    lead_id: int,
) -> Lead | None:
    query = select(Lead).where(Lead.id == lead_id).options(
        selectinload(Lead.estimates).selectinload(EstimateVersion.phases)
    )
    return (await db.execute(query)).scalar_one_or_none()


def _get_approved_estimate_version(lead: Lead) -> EstimateVersion | None:
    return next(
        (
            v
            for v in (lead.estimates or [])
            if v.status == EstimateStatus.APPROVED
        ),
        None,
    )


async def _ensure_project_code_available(
    *,
    db: deps.DBDep,
    project_code: str,
) -> None:
    existing_code = (
        await db.execute(
            select(Project.id).where(Project.code == project_code)
        )
    ).scalar_one_or_none()
    if existing_code is not None:
        raise HTTPException(
            status_code=400,
            detail="Project code already exists",
        )


async def _ensure_lead_not_already_converted(
    *,
    db: deps.DBDep,
    lead_id: int,
) -> None:
    existing_project = (
        await db.execute(select(Project).where(Project.lead_id == lead_id))
    ).scalar_one_or_none()
    if existing_project:
        raise HTTPException(
            status_code=400,
            detail=(
                "Lead is already converted to a project "
                f"(project_id={existing_project.id})"
            ),
        )


async def _create_project_and_initial_members(
    *,
    db: deps.DBDep,
    lead: Lead,
    project_code: str,
    project_manager_id: int,
    converter_user_id: int,
) -> Project:
    project = Project(
        name=lead.title,
        description=lead.notes,
        code=project_code,
        status="active",
        lead_id=lead.id,
    )
    db.add(project)
    await db.flush()

    db.add(
        ProjectMember(
            project_id=project.id,
            user_id=project_manager_id,
            role="manager",
        )
    )

    # Bidder/converter must be able to see the full scope.
    if converter_user_id != project_manager_id:
        db.add(
            ProjectMember(
                project_id=project.id,
                user_id=converter_user_id,
                role="manager",
            )
        )

    return project


async def _create_pm_project_for_bid_task(
    *,
    db: deps.DBDep,
    lead: Lead,
    master_project_code: str,
    bid_task: LeadBidTask,
    converter_user_id: int,
    master_manager_user_id: int,
    default_pm_id: int,
    master_project_id: int,
) -> Project:
    assignee_id = _choose_bid_task_assignee_id(
        bid_task=bid_task,
        default_pm_id=default_pm_id,
    )

    # Group child projects by master code; stay within <= 20 chars.
    suffix = f"-{int(bid_task.id)}"
    child_code = (master_project_code[: (20 - len(suffix))] + suffix)[:20]
    await _ensure_project_code_available(db=db, project_code=child_code)

    name = f"{lead.title} — {bid_task.title}".strip()
    if len(name) > 100:
        name = name[:100]

    project = Project(
        name=name,
        description=bid_task.description or lead.notes,
        code=child_code,
        status="active",
        lead_id=lead.id,
        parent_project_id=master_project_id,
    )
    db.add(project)
    await db.flush()

    db.add(
        ProjectMember(
            project_id=project.id,
            user_id=int(assignee_id),
            role="manager",
        )
    )

    if converter_user_id != int(assignee_id):
        db.add(
            ProjectMember(
                project_id=project.id,
                user_id=int(converter_user_id),
                role="member",
            )
        )

    if (
        int(master_manager_user_id) != int(assignee_id)
        and int(master_manager_user_id) != int(converter_user_id)
    ):
        db.add(
            ProjectMember(
                project_id=project.id,
                user_id=int(master_manager_user_id),
                role="manager",
            )
        )

    # Seed a single task inside the PM project.
    await _seed_tasks_from_bid_tasks(
        db=db,
        project_id=int(project.id),
        creator_id=int(converter_user_id),
        default_pm_id=int(assignee_id),
        bid_tasks=[bid_task],
    )

    return project


def _milestone_due_date(
    *,
    start_date: date,
    phase: EstimatePhase,
) -> datetime:
    offset = phase.start_offset_days or 0
    days_to_due = offset + phase.duration_days
    start_dt = datetime.combine(start_date, time.min)
    due_timestamp = start_dt + timedelta(days=days_to_due)
    return due_timestamp.replace(tzinfo=timezone.utc)


def _create_baseline_from_estimate(
    *,
    db: deps.DBDep,
    project_id: int,
    approved_version: EstimateVersion,
) -> None:
    baseline_desc = (
        "Initial baseline from approved estimate "
        f"V{approved_version.version_number}"
    )
    db.add(
        CostBaseline(
            project_id=project_id,
            amount=float(approved_version.total_price_decimal),
            description=baseline_desc,
            is_active=True,
        )
    )


def _create_milestones_from_estimate(
    *,
    db: deps.DBDep,
    project_id: int,
    approved_version: EstimateVersion,
    start_date: date,
) -> None:
    for phase in approved_version.phases:
        db.add(
            Milestone(
                project_id=project_id,
                title=phase.phase_name,
                description=phase.description,
                due_date=_milestone_due_date(
                    start_date=start_date,
                    phase=phase,
                ),
                status="pending",
            )
        )


async def _load_bid_tasks_for_conversion(
    *,
    db: deps.DBDep,
    lead_id: int,
) -> list[LeadBidTask]:
    bid_tasks_query = (
        select(LeadBidTask)
        .where(LeadBidTask.lead_id == lead_id)
        .options(
            selectinload(LeadBidTask.assignments)
            .selectinload(LeadBidTaskAssignment.reviews)
            .selectinload(LeadBidTaskReview.lines)
        )
        .order_by(LeadBidTask.id)
    )
    return list((await db.execute(bid_tasks_query)).scalars().all())


def _choose_bid_task_assignee_id(
    *,
    bid_task: LeadBidTask,
    default_pm_id: int,
) -> int:
    delivery_pm_user_id = getattr(bid_task, "delivery_pm_user_id", None)
    if delivery_pm_user_id is not None:
        return int(delivery_pm_user_id)

    pm_ids = [int(a.pm_user_id) for a in (bid_task.assignments or [])]
    pm_ids = list(dict.fromkeys(pm_ids))
    if len(pm_ids) == 1:
        return pm_ids[0]

    return int(default_pm_id)


def _latest_accepted_review_for_bid_task(
    *,
    bid_task: LeadBidTask,
) -> LeadBidTaskReview | None:
    accepted_reviews: list[LeadBidTaskReview] = []
    for a in (bid_task.assignments or []):
        for r in (a.reviews or []):
            if r.status == LeadBidTaskReviewStatus.ACCEPTED:
                accepted_reviews.append(r)
    if not accepted_reviews:
        return None

    return max(
        accepted_reviews,
        key=lambda r: (
            int(r.revision_number or 0),
            r.updated_at or r.created_at,
            int(r.id or 0),
        ),
    )


def _seeded_task_title_description(
    *,
    bid_task: LeadBidTask,
    latest_review: LeadBidTaskReview | None,
) -> tuple[str, str | None, float | None]:
    seeded_description = bid_task.description
    hours_str: str | None = None
    task_hours_val: float | None = None

    if latest_review is not None:
        hours_val = float(latest_review.total_hours or 0)
        task_hours_val = hours_val
        hours_str = f"{hours_val:.2f}".rstrip("0").rstrip(".")
        suffix = f"\n\nEstimated hours: {hours_str}h"
        seeded_description = (seeded_description or "") + suffix

    seeded_title = bid_task.title
    if hours_str:
        seeded_title = f"{seeded_title} ({hours_str}h)"

    return seeded_title, seeded_description, task_hours_val


def _seed_subtasks_from_review(
    *,
    db: deps.DBDep,
    seeded_task_id: int,
    latest_review: LeadBidTaskReview,
) -> None:
    for line in (latest_review.lines or []):
        line_hours = float(getattr(line, "hours", 0) or 0)
        if line_hours > 0:
            line_hours_str = f"{line_hours:.2f}".rstrip("0").rstrip(".")
            sub_title = f"{line.title} • {line_hours_str}h"
        else:
            sub_title = line.title
        db.add(
            Subtask(
                title=sub_title,
                task_id=seeded_task_id,
                estimated_hours=line_hours or None,
            )
        )


async def _seed_tasks_from_bid_tasks(
    *,
    db: deps.DBDep,
    project_id: int,
    creator_id: int,
    default_pm_id: int,
    bid_tasks: list[LeadBidTask],
) -> set[int]:
    member_user_ids: set[int] = set()

    for bid_task in bid_tasks:
        assignee_id = _choose_bid_task_assignee_id(
            bid_task=bid_task,
            default_pm_id=default_pm_id,
        )
        member_user_ids.add(int(assignee_id))

        latest_review = _latest_accepted_review_for_bid_task(
            bid_task=bid_task,
        )

        seeded_title, seeded_description, task_hours_val = (
            _seeded_task_title_description(
                bid_task=bid_task,
                latest_review=latest_review,
            )
        )

        seeded_task = Task(
            title=seeded_title,
            description=seeded_description,
            project_id=project_id,
            creator_id=creator_id,
            assignee_id=assignee_id,
            estimated_hours=task_hours_val,
            status="todo",
            priority="medium",
        )
        db.add(seeded_task)
        await db.flush()

        if latest_review is not None:
            _seed_subtasks_from_review(
                db=db,
                seeded_task_id=int(seeded_task.id),
                latest_review=latest_review,
            )

    return member_user_ids


async def _seed_master_scope_tasks_from_bid_tasks(
    *,
    db: deps.DBDep,
    project_id: int,
    creator_id: int,
    master_assignee_id: int,
    bid_tasks: list[LeadBidTask],
) -> None:
    """Seed full-scope tasks into the master project without leaking access.

    The master project is intended to be visible only to the bidder and
    elevated roles. Delivery PMs should not become members of the master
    project purely because they are assignees on bid tasks.
    """
    for bid_task in bid_tasks:
        latest_review = _latest_accepted_review_for_bid_task(
            bid_task=bid_task,
        )

        seeded_title, seeded_description, task_hours_val = (
            _seeded_task_title_description(
                bid_task=bid_task,
                latest_review=latest_review,
            )
        )

        seeded_task = Task(
            title=seeded_title,
            description=seeded_description,
            project_id=project_id,
            creator_id=creator_id,
            assignee_id=int(master_assignee_id),
            estimated_hours=task_hours_val,
            status="todo",
            priority="medium",
        )
        db.add(seeded_task)
        await db.flush()

        if latest_review is not None:
            _seed_subtasks_from_review(
                db=db,
                seeded_task_id=int(seeded_task.id),
                latest_review=latest_review,
            )


async def _ensure_project_members(
    *,
    db: deps.DBDep,
    project_id: int,
    user_ids: set[int],
) -> None:
    if not user_ids:
        return

    existing_member_rows = (
        await db.execute(
            select(ProjectMember.user_id).where(
                ProjectMember.project_id == project_id
            )
        )
    ).scalars().all()
    existing_member_ids = {int(x) for x in existing_member_rows}

    for uid in user_ids:
        if int(uid) in existing_member_ids:
            continue
        db.add(
            ProjectMember(
                project_id=project_id,
                user_id=int(uid),
                role="member",
            )
        )


@router.post(
    "/leads/{id}/convert-to-project",
    response_model=ProjectRead,
    responses=_CONVERT_LEAD_ERROR_RESPONSES,
)
async def convert_lead_to_project(
    id: int,
    convert_in: LeadToProjectConvert,
    db: deps.DBDep,
    current_user: Annotated[
        User, Depends(deps.check_permissions([BD_CONVERT_PROJECT]))
    ],
) -> Any:
    """
    Converts a lead into a Project and marks it as WON.
    Requires at least one APPROVED estimate version.
    """
    lead = await _load_lead_for_conversion(db=db, lead_id=id)
    if not lead:
        raise HTTPException(status_code=404, detail=LEAD_NOT_FOUND)
    if not await _user_can_access_lead(db, current_user, lead):
        raise HTTPException(status_code=403, detail="Not authorized")

    if lead.stage not in (LeadStage.NEGOTIATION, LeadStage.WON):
        raise HTTPException(
            status_code=400,
            detail="Lead must be in NEGOTIATION or WON stage to convert",
        )

    await _ensure_lead_not_already_converted(db=db, lead_id=int(lead.id))

    pm_user = await db.get(User, int(convert_in.project_manager_id))
    if not pm_user:
        raise HTTPException(
            status_code=404,
            detail="Project manager not found",
        )

    eligible = await _eligible_portfolio_managers(db, current_user, lead)
    if int(convert_in.project_manager_id) not in {int(u.id) for u in eligible}:
        raise HTTPException(
            status_code=403,
            detail=(
                "Selected portfolio manager is not eligible for this lead. "
                "Choose COO / CEO / Admin / Super Admin or "
                "(if you are a BD) yourself."
            ),
        )

    await _ensure_project_code_available(
        db=db,
        project_code=convert_in.project_code,
    )

    approved_version = _get_approved_estimate_version(lead)
    if not approved_version:
        raise HTTPException(
            status_code=400,
            detail="Lead must have an APPROVED estimate version to convert",
        )

    if lead.stage != LeadStage.WON:
        lead.stage = LeadStage.WON
        db.add(lead)

    project = await _create_project_and_initial_members(
        db=db,
        lead=lead,
        project_code=convert_in.project_code,
        project_manager_id=int(convert_in.project_manager_id),
        converter_user_id=int(current_user.id),
    )

    _create_baseline_from_estimate(
        db=db,
        project_id=int(project.id),
        approved_version=approved_version,
    )

    _create_milestones_from_estimate(
        db=db,
        project_id=int(project.id),
        approved_version=approved_version,
        start_date=convert_in.start_date,
    )

    bid_tasks = await _load_bid_tasks_for_conversion(
        db=db,
        lead_id=int(lead.id),
    )

    # Seed full-scope tasks into the master project without adding
    # delivery PMs as members of the master project.
    await _seed_master_scope_tasks_from_bid_tasks(
        db=db,
        project_id=int(project.id),
        creator_id=int(current_user.id),
        master_assignee_id=int(convert_in.project_manager_id),
        bid_tasks=bid_tasks,
    )
    seeded_member_ids = {
        int(convert_in.project_manager_id),
        int(current_user.id),
    }

    # Create one project per bid task for delivery PMs.
    for bid_task in bid_tasks:
        await _create_pm_project_for_bid_task(
            db=db,
            lead=lead,
            master_project_code=str(project.code),
            bid_task=bid_task,
            converter_user_id=int(current_user.id),
            master_manager_user_id=int(convert_in.project_manager_id),
            default_pm_id=int(convert_in.project_manager_id),
            master_project_id=int(project.id),
        )

    await _ensure_project_members(
        db=db,
        project_id=int(project.id),
        user_ids=seeded_member_ids,
    )

    # Audit Log
    audit = AuditLog(
        user_id=current_user.id,
        action="convert_lead",
        resource_type="lead",
        resource_id=lead.lead_id,
        details={
            "project_id": project.id,
            "project_code": project.code,
            "estimate_version_id": approved_version.id
        }
    )
    db.add(audit)

    await db.commit()
    await db.refresh(project)
    return project
