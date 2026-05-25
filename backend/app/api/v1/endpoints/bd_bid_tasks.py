from __future__ import annotations

from pathlib import Path
from decimal import Decimal
from datetime import datetime, timezone
from typing import Any, Optional, List, Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.requests import Request
from fastapi.responses import FileResponse
from sqlalchemy import select, and_, func, delete
from sqlalchemy.orm import selectinload

from app.api import deps
from app.core.config import settings
from app.models.audit import AuditLog
from app.models.bd import (
    Lead,
    EstimateVersion,
    EstimateResourceLine,
    LeadDocument,
)
from app.models.user import User, Role, user_roles
from app.models.bid_task import (
    LeadBidTask,
    LeadBidTaskAssignment,
    LeadBidTaskAssignmentDocument,
    LeadBidTaskReview,
    LeadBidTaskReviewLine,
    LeadBidTaskReviewStatus,
    BidLineItem,
)
from app.schemas.bid_tasks import (
    LeadBidTaskCreate,
    LeadBidTaskRead,
    LeadBidTaskAssignmentCreate,
    LeadBidTaskAssignmentRead,
    BidTaskAssignmentDocumentRead,
    LeadBidTaskReviewUpsert,
    LeadBidTaskReviewRead,
    LeadBidTaskReviewRevisionRequest,
    LeadBidEvaluationsResponse,
    LeadBidTaskWithAssignments,
    LeadBidTaskReviewSummary,
    MyBidRequestItem,
    PMSubmissionsSummaryResponse,
)
from app.schemas.error import ErrorResponse
from app.schemas.bd import EstimateVersionDetailed


_COMMON_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorResponse, "description": "Bad request"},
    403: {"model": ErrorResponse, "description": "Forbidden"},
    404: {"model": ErrorResponse, "description": "Not found"},
    409: {"model": ErrorResponse, "description": "Conflict"},
}


router = APIRouter(responses=_COMMON_ERROR_RESPONSES)

BID_TASK_READ = "bd bid task read"
BID_TASK_WRITE = "bd bid task write"
BID_REVIEW_READ = "bd bid review read"
BID_REVIEW_WRITE = "bd bid review write"
BD_ESTIMATE_WRITE = "bd estimate write"

ERR_VERSION_LEAD_MISMATCH_MSG = "Estimate version does not belong to this lead"


def _recompute_estimate_totals(
    version: EstimateVersion,
    resource_lines: list[EstimateResourceLine],
) -> None:
    total_cost = Decimal(
        sum(
            Decimal(str(float(line.cost_decimal or 0)))
            for line in resource_lines
        )
    )
    version.total_cost_decimal = float(total_cost)

    cost_with_contingency = total_cost * Decimal(
        1 + (float(version.contingency_percent or 0.0) / 100)
    )
    margin = float(version.margin_percent or 0.0)
    if margin >= 100:
        version.total_price_decimal = float(cost_with_contingency * 2)
    else:
        version.total_price_decimal = float(
            cost_with_contingency / Decimal(1 - margin / 100)
        )


async def _get_lead_assignment_ids(db: deps.DBDep, lead_id: int) -> list[int]:
    assignment_rows = await db.execute(
        select(LeadBidTaskAssignment.id)
        .join(LeadBidTask)
        .where(LeadBidTask.lead_id == lead_id)
    )
    return [int(x) for x in assignment_rows.scalars().all()]


async def _get_latest_reviews_by_assignment(
    *,
    db: deps.DBDep,
    assignment_ids: list[int],
    estimate_version_id: int,
    status: LeadBidTaskReviewStatus,
) -> dict[int, LeadBidTaskReview]:
    if not assignment_ids:
        return {}

    reviews_q = (
        select(LeadBidTaskReview)
        .where(
            and_(
                LeadBidTaskReview.assignment_id.in_(assignment_ids),
                LeadBidTaskReview.estimate_version_id == estimate_version_id,
                LeadBidTaskReview.status == status,
            )
        )
        .options(selectinload(LeadBidTaskReview.lines))
        .order_by(
            LeadBidTaskReview.assignment_id,
            LeadBidTaskReview.revision_number.desc(),
        )
    )
    reviews_res = await db.execute(reviews_q)
    all_reviews = reviews_res.scalars().unique().all()

    latest: dict[int, LeadBidTaskReview] = {}
    for review in all_reviews:
        if review.assignment_id not in latest:
            latest[review.assignment_id] = review
    return latest


def _aggregate_role_totals(
    reviews: list[LeadBidTaskReview],
) -> tuple[dict[str, dict[str, float]], list[dict[str, Any]]]:
    role_totals: dict[str, dict[str, float]] = {}
    included_reviews: list[dict[str, Any]] = []

    for review in reviews:
        included_reviews.append(
            {
                "review_id": review.id,
                "assignment_id": review.assignment_id,
                "revision_number": review.revision_number,
            }
        )
        for line in review.lines:
            # Aggregate by line-item title (task/subtask). Role is optional.
            # Note: EstimateResourceLine.role_name is VARCHAR(100), so we
            # clamp.
            title = (line.title or "").strip() or "Uncategorized"
            if len(title) > 100:
                title = title[:100]

            bucket = role_totals.get(title) or {"hours": 0.0, "cost": 0.0}
            bucket["hours"] += float(line.hours or 0)
            bucket["cost"] += float(line.cost or 0)
            role_totals[title] = bucket

    return role_totals, included_reviews


def _resource_lines_from_role_totals(
    *,
    estimate_version_id: int,
    role_totals: dict[str, dict[str, float]],
) -> list[EstimateResourceLine]:
    new_resource_lines: list[EstimateResourceLine] = []
    for role_name in sorted(role_totals.keys(), key=lambda s: s.lower()):
        hours = float(role_totals[role_name]["hours"] or 0)
        cost = float(role_totals[role_name]["cost"] or 0)
        rate = float(cost / hours) if hours > 0 else 0.0
        new_resource_lines.append(
            EstimateResourceLine(
                version_id=estimate_version_id,
                role_name=role_name,
                quantity=1.0,
                hours=hours,
                rate=rate,
                cost_decimal=cost,
            )
        )
    return new_resource_lines


async def _ensure_lead_has_estimate_version(
    *,
    db: deps.DBDep,
    request: Request,
    lead: Lead,
    current_user: User,
) -> Optional[int]:
    """Ensure a lead has at least one estimate version.

    PM bid-requests are keyed by estimate_version_id; if a lead has no
    EstimateVersion rows yet, PMs won't see assigned bid tasks.
    """

    existing_id = (
        await db.execute(
            select(EstimateVersion.id)
            .where(EstimateVersion.lead_id == lead.id)
            .order_by(EstimateVersion.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if existing_id is not None:
        return int(existing_id)

    if not (
        current_user.is_superuser
        or _user_has_permission(current_user, BD_ESTIMATE_WRITE)
    ):
        raise HTTPException(
            status_code=400,
            detail=_err(
                "ESTIMATE_VERSION_REQUIRED",
                "Create an estimate version before assigning PMs",
                {"lead_id": lead.id},
            ),
        )

    max_v = (
        await db.execute(
            select(func.max(EstimateVersion.version_number)).where(
                EstimateVersion.lead_id == lead.id
            )
        )
    ).scalar() or 0

    version = EstimateVersion(
        lead_id=lead.id,
        version_number=int(max_v) + 1,
        name="Initial Estimate",
        currency="INR",
        created_by_id=current_user.id,
    )
    db.add(version)
    await db.flush()

    _log_audit(
        db=db,
        request=request,
        user_id=current_user.id,
        action="bd.estimate.auto_create",
        resource_type="estimate_version",
        resource_id=str(version.id),
        details={"lead_id": lead.id, "estimate_version_id": version.id},
    )

    return int(version.id)


def _user_has_permission(user: User, permission_name: str) -> bool:
    roles = getattr(user, "roles", None) or []
    for role in roles:
        perms = getattr(role, "permissions", None) or []
        for perm in perms:
            if getattr(perm, "name", None) == permission_name:
                return True
    return False


def _err(code: str, message: str, details: Optional[dict] = None) -> dict:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
        }
    }


def _doc_download_url(*, assignment_id: int, doc_id: int) -> str:
    return (
        f"/bd/bid-task-assignments/{assignment_id}/documents/{doc_id}/download"
    )


def _as_assignment_document(
    *,
    assignment_id: int,
    doc: LeadDocument,
) -> BidTaskAssignmentDocumentRead:
    return BidTaskAssignmentDocumentRead(
        id=doc.id,
        file_name=doc.file_name,
        mime_type=doc.mime_type,
        file_size=doc.file_size,
        uploaded_at=doc.uploaded_at,
        download_url=_doc_download_url(
            assignment_id=assignment_id,
            doc_id=doc.id,
        ),
    )


async def _get_existing_assignment_ids_by_pm(
    *,
    db: deps.DBDep,
    bid_task_id: int,
) -> dict[int, int]:
    existing = await db.execute(
        select(
            LeadBidTaskAssignment.pm_user_id,
            LeadBidTaskAssignment.id,
        ).where(LeadBidTaskAssignment.bid_task_id == bid_task_id)
    )
    return {int(pm_id): int(a_id) for pm_id, a_id in existing.all()}


async def _resolve_assignment_ids_for_pm_users(
    *,
    db: deps.DBDep,
    bid_task_id: int,
    pm_user_ids: list[int],
    assigned_by_id: int,
    deadline: Optional[datetime] = None,
) -> tuple[list[LeadBidTaskAssignment], list[int]]:
    existing_by_pm = await _get_existing_assignment_ids_by_pm(
        db=db,
        bid_task_id=bid_task_id,
    )

    created: list[LeadBidTaskAssignment] = []
    affected_assignment_ids: list[int] = []

    for pm_user_id in pm_user_ids:
        existing_id = existing_by_pm.get(int(pm_user_id))
        if existing_id is not None:
            affected_assignment_ids.append(int(existing_id))
            continue

        assignment = LeadBidTaskAssignment(
            bid_task_id=bid_task_id,
            pm_user_id=int(pm_user_id),
            assigned_by_id=assigned_by_id,
            deadline=deadline,
        )
        db.add(assignment)
        created.append(assignment)

    await db.flush()

    if created:
        affected_assignment_ids.extend([int(a.id) for a in created])

    return created, affected_assignment_ids


def _normalize_int_ids(values: list[int] | None) -> list[int]:
    if not values:
        return []
    return list(dict.fromkeys(int(x) for x in values if int(x) > 0))


async def _validate_lead_documents_belong_to_lead(
    *,
    db: deps.DBDep,
    lead_id: int,
    lead_document_ids: list[int],
) -> None:
    if not lead_document_ids:
        return

    docs_res = await db.execute(
        select(LeadDocument).where(
            LeadDocument.id.in_(lead_document_ids),
            LeadDocument.lead_id == lead_id,
        )
    )
    docs = docs_res.scalars().all()
    if len(docs) != len(lead_document_ids):
        raise HTTPException(
            status_code=400,
            detail=_err(
                "INVALID_DOCUMENTS",
                "One or more documents are invalid for this lead",
                {"lead_id": lead_id, "lead_document_ids": lead_document_ids},
            ),
        )


async def _attach_documents_to_assignments(
    *,
    db: deps.DBDep,
    affected_assignment_ids: list[int],
    lead_document_ids: list[int],
) -> None:
    if not affected_assignment_ids or not lead_document_ids:
        return

    existing_links_res = await db.execute(
        select(
            LeadBidTaskAssignmentDocument.assignment_id,
            LeadBidTaskAssignmentDocument.lead_document_id,
        ).where(
            LeadBidTaskAssignmentDocument.assignment_id.in_(
                affected_assignment_ids
            ),
            LeadBidTaskAssignmentDocument.lead_document_id.in_(
                lead_document_ids
            ),
        )
    )
    existing_pairs = {
        (int(a_id), int(d_id)) for a_id, d_id in existing_links_res.all()
    }

    new_links: list[LeadBidTaskAssignmentDocument] = []
    for assignment_id in affected_assignment_ids:
        for doc_id in lead_document_ids:
            if (int(assignment_id), int(doc_id)) in existing_pairs:
                continue
            new_links.append(
                LeadBidTaskAssignmentDocument(
                    assignment_id=int(assignment_id),
                    lead_document_id=int(doc_id),
                )
            )

    if new_links:
        db.add_all(new_links)
        await db.flush()


def _assignment_not_found_exc(assignment_id: int) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail=_err(
            "ASSIGNMENT_NOT_FOUND",
            "Bid task assignment not found",
            {"assignment_id": assignment_id},
        ),
    )


def _review_not_found_exc(review_id: int) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail=_err(
            "REVIEW_NOT_FOUND",
            "Bid task review not found",
            {"review_id": review_id},
        ),
    )


def _bid_task_not_found_exc(
    *,
    bid_task_id: int,
    lead_id: Optional[int] = None,
) -> HTTPException:
    details: dict[str, Any] = {"bid_task_id": bid_task_id}
    if lead_id is not None:
        details["lead_id"] = lead_id
    return HTTPException(
        status_code=404,
        detail=_err(
            "BID_TASK_NOT_FOUND",
            "Bid task not found",
            details,
        ),
    )


def _lead_not_found_exc(lead_id: int) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail=_err(
            "LEAD_NOT_FOUND",
            "Lead not found",
            {"lead_id": lead_id},
        ),
    )


def _estimate_not_found_exc(version_id: int) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail=_err(
            "ESTIMATE_NOT_FOUND",
            "Estimate not found",
            {"estimate_version_id": version_id},
        ),
    )


def _lead_forbidden_exc(lead_id: int) -> HTTPException:
    return HTTPException(
        status_code=403,
        detail=_err(
            "FORBIDDEN",
            "Not authorized to access this lead",
            {"lead_id": lead_id},
        ),
    )


def _log_audit(
    *,
    db: deps.DBDep,
    request: Request,
    user_id: int,
    action: str,
    resource_type: str,
    resource_id: Optional[str],
    details: dict,
) -> None:
    db.add(
        AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            ip_address=getattr(request.client, "host", None),
        )
    )


async def _user_can_access_lead(
    db: deps.DBDep,
    current_user: User,
    lead: Lead,
) -> bool:
    if current_user.is_superuser:
        return True

    # Owner or subordinate owner
    result = await db.execute(
        select(User.id).where(User.manager_id == current_user.id)
    )
    subordinate_ids = list(result.scalars().all())

    if lead.owner_user_id == current_user.id:
        return True
    if subordinate_ids and lead.owner_user_id in subordinate_ids:
        return True

    # PM assigned via bid task assignment
    assigned_pm = await db.execute(
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
    if assigned_pm.scalar_one_or_none() is not None:
        return True

    return False


async def _ensure_assignment_access(
    db: deps.DBDep, current_user: User, assignment: LeadBidTaskAssignment
) -> Optional[HTTPException]:
    if current_user.is_superuser:
        return None

    if assignment.pm_user_id == current_user.id:
        return None

    # BD owner/subordinate can access via lead
    task = await db.get(LeadBidTask, assignment.bid_task_id)
    if not task:
        return _bid_task_not_found_exc(bid_task_id=assignment.bid_task_id)

    lead = await db.get(Lead, task.lead_id)
    if not lead:
        return _lead_not_found_exc(task.lead_id)

    allowed = await _user_can_access_lead(db, current_user, lead)
    if not allowed:
        return _lead_forbidden_exc(lead.id)

    return None


def _compute_totals(lines: list[LeadBidTaskReviewLine]) -> tuple[float, float]:
    total_hours = float(sum(float(line.hours or 0) for line in lines))
    total_cost = float(sum(float(line.cost or 0) for line in lines))
    return total_hours, total_cost


def _as_task_with_assignments(
    task: LeadBidTask,
    assignments: list[LeadBidTaskAssignment],
) -> LeadBidTaskWithAssignments:
    return LeadBidTaskWithAssignments(
        task=LeadBidTaskRead.model_validate(task, from_attributes=True),
        assignments=[
            LeadBidTaskAssignmentRead.model_validate(a, from_attributes=True)
            for a in assignments
        ],
    )


def _as_review_summaries(
    assignments: list[LeadBidTaskAssignment],
    latest_by_assignment: dict[int, LeadBidTaskReview],
) -> list[LeadBidTaskReviewSummary]:
    out: list[LeadBidTaskReviewSummary] = []
    for a in assignments:
        latest = latest_by_assignment.get(a.id)
        latest_review = (
            LeadBidTaskReviewRead.model_validate(latest, from_attributes=True)
            if latest
            else None
        )
        out.append(
            LeadBidTaskReviewSummary(
                assignment=LeadBidTaskAssignmentRead.model_validate(
                    a, from_attributes=True
                ),
                latest_review=latest_review,
            )
        )
    return out


async def _resolve_bid_task_title_description(
    *,
    db: deps.DBDep,
    task_in: LeadBidTaskCreate,
) -> tuple[str, str | None]:
    template: BidLineItem | None = None
    if task_in.template_id is not None:
        template = await db.get(BidLineItem, task_in.template_id)
        if not template or not template.is_active:
            raise HTTPException(
                status_code=400,
                detail=_err(
                    "INVALID_TEMPLATE",
                    "Invalid or inactive bid line item",
                    {"template_id": task_in.template_id},
                ),
            )

    title = (task_in.title or "").strip()
    if not title and template is not None:
        title = (template.title or "").strip()
    if not title:
        raise HTTPException(
            status_code=400,
            detail=_err("VALIDATION_ERROR", "Task title is required"),
        )

    description = (task_in.description or "").strip() or None
    if description is None and template is not None:
        description = (template.description or "").strip() or None

    return title, description


@router.post(
    "/leads/{lead_id}/bid-tasks",
    response_model=LeadBidTaskRead,
    responses=_COMMON_ERROR_RESPONSES,
)
async def create_lead_bid_task(
    *,
    db: deps.DBDep,
    request: Request,
    lead_id: int,
    task_in: LeadBidTaskCreate,
    current_user: Annotated[
        User, Depends(deps.check_permissions([BID_TASK_WRITE]))
    ],
) -> Any:
    lead = await db.get(Lead, lead_id)
    if not lead:
        raise _lead_not_found_exc(lead_id)
    if not await _user_can_access_lead(db, current_user, lead):
        raise _lead_forbidden_exc(lead_id)

    title, description = await _resolve_bid_task_title_description(
        db=db,
        task_in=task_in,
    )

    task = LeadBidTask(
        lead_id=lead_id,
        title=title,
        description=description,
        bd_estimated_hours=task_in.bd_estimated_hours,
        bd_estimated_cost=task_in.bd_estimated_cost,
        created_by_id=current_user.id,
    )
    db.add(task)
    await db.flush()

    _log_audit(
        db=db,
        request=request,
        user_id=current_user.id,
        action="bd.bid_task.create",
        resource_type="lead_bid_task",
        resource_id=str(task.id),
        details={"lead_id": lead_id, "title": title},
    )

    await db.commit()
    await db.refresh(task)
    return task


@router.get(
    "/leads/{lead_id}/bid-tasks",
    response_model=List[LeadBidTaskWithAssignments],
    responses=_COMMON_ERROR_RESPONSES,
)
async def list_lead_bid_tasks(
    *,
    db: deps.DBDep,
    lead_id: int,
    current_user: Annotated[
        User, Depends(deps.check_permissions([BID_TASK_READ]))
    ],
) -> Any:
    lead = await db.get(Lead, lead_id)
    if not lead:
        raise _lead_not_found_exc(lead_id)
    if not await _user_can_access_lead(db, current_user, lead):
        raise _lead_forbidden_exc(lead_id)

    q = (
        select(LeadBidTask)
        .where(
            and_(
                LeadBidTask.lead_id == lead_id,
                LeadBidTask.is_archived.is_(False),
            )
        )
        .options(
            selectinload(LeadBidTask.assignments).selectinload(
                LeadBidTaskAssignment.pm_user
            )
        )
        .order_by(LeadBidTask.id)
    )
    res = await db.execute(q)
    tasks = res.scalars().unique().all()

    out: list[LeadBidTaskWithAssignments] = []
    for task in tasks:
        assignments = task.assignments
        is_pm_view = (
            not current_user.is_superuser
            and not _user_has_permission(current_user, BID_TASK_WRITE)
        )
        if is_pm_view and assignments:
            assignments = [
                a for a in assignments if a.pm_user_id == current_user.id
            ]
        out.append(
            LeadBidTaskWithAssignments(
                task=LeadBidTaskRead.model_validate(
                    task, from_attributes=True
                ),
                assignments=[
                    LeadBidTaskAssignmentRead.model_validate(
                        a, from_attributes=True
                    )
                    for a in assignments
                ],
            )
        )

    return out


@router.post(
    "/leads/{lead_id}/bid-tasks/{bid_task_id}/assign",
    response_model=List[LeadBidTaskAssignmentRead],
    responses=_COMMON_ERROR_RESPONSES,
)
async def assign_bid_task_to_pms(
    *,
    db: deps.DBDep,
    request: Request,
    lead_id: int,
    bid_task_id: int,
    assign_in: LeadBidTaskAssignmentCreate,
    current_user: Annotated[
        User, Depends(deps.check_permissions([BID_TASK_WRITE]))
    ],
) -> Any:
    lead = await db.get(Lead, lead_id)
    if not lead:
        raise _lead_not_found_exc(lead_id)
    if not await _user_can_access_lead(db, current_user, lead):
        raise _lead_forbidden_exc(lead_id)

    task = await db.get(LeadBidTask, bid_task_id)
    if not task or task.lead_id != lead_id:
        raise _bid_task_not_found_exc(bid_task_id=bid_task_id, lead_id=lead_id)

    delivery_pm_user_id = assign_in.delivery_pm_user_id
    if delivery_pm_user_id is not None:
        pm_user = await db.get(User, int(delivery_pm_user_id))
        if not pm_user:
            raise HTTPException(
                status_code=404,
                detail=_err(
                    "PM_NOT_FOUND",
                    "Delivery PM not found",
                    {"delivery_pm_user_id": delivery_pm_user_id},
                ),
            )
        task.delivery_pm_user_id = int(delivery_pm_user_id)
        db.add(task)

    # PM bid-request boards depend on estimate versions; ensure one exists.
    await _ensure_lead_has_estimate_version(
        db=db,
        request=request,
        lead=lead,
        current_user=current_user,
    )

    pm_user_ids = list(dict.fromkeys(assign_in.pm_user_ids))
    if not pm_user_ids:
        raise HTTPException(
            status_code=400,
            detail=_err("VALIDATION_ERROR", "pm_user_ids is required"),
        )

    pm_user_ids = _normalize_int_ids(pm_user_ids)

    if delivery_pm_user_id is not None:
        if int(delivery_pm_user_id) not in set(pm_user_ids):
            raise HTTPException(
                status_code=400,
                detail=_err(
                    "VALIDATION_ERROR",
                    "delivery_pm_user_id must be one of pm_user_ids",
                    {
                        "delivery_pm_user_id": int(delivery_pm_user_id),
                        "pm_user_ids": pm_user_ids,
                    },
                ),
            )
    _, affected_assignment_ids = await _resolve_assignment_ids_for_pm_users(
        db=db,
        bid_task_id=bid_task_id,
        pm_user_ids=pm_user_ids,
        assigned_by_id=current_user.id,
        deadline=assign_in.deadline,
    )

    lead_document_ids = _normalize_int_ids(assign_in.lead_document_ids)
    await _validate_lead_documents_belong_to_lead(
        db=db,
        lead_id=lead_id,
        lead_document_ids=lead_document_ids,
    )
    await _attach_documents_to_assignments(
        db=db,
        affected_assignment_ids=affected_assignment_ids,
        lead_document_ids=lead_document_ids,
    )

    _log_audit(
        db=db,
        request=request,
        user_id=current_user.id,
        action="bd.bid_task.assign",
        resource_type="lead_bid_task",
        resource_id=str(bid_task_id),
        details={
            "lead_id": lead_id,
            "pm_user_ids": pm_user_ids,
            "lead_document_ids": lead_document_ids,
            "affected_assignment_ids": affected_assignment_ids,
            "delivery_pm_user_id": delivery_pm_user_id,
        },
    )

    await db.commit()

    if not affected_assignment_ids:
        return []

    # Reload with pm user for response
    ids = affected_assignment_ids
    q = (
        select(LeadBidTaskAssignment)
        .where(LeadBidTaskAssignment.id.in_(ids))
        .options(selectinload(LeadBidTaskAssignment.pm_user))
    )
    res = await db.execute(q)
    return [
        LeadBidTaskAssignmentRead.model_validate(
            a, from_attributes=True
        )
        for a in res.scalars().all()
    ]


@router.post(
    "/leads/{lead_id}/bid-tasks/assign-unassigned-to-coo",
    response_model=List[LeadBidTaskAssignmentRead],
    responses=_COMMON_ERROR_RESPONSES,
)
async def assign_unassigned_to_coo(
    *,
    db: deps.DBDep,
    request: Request,
    lead_id: int,
    current_user: Annotated[
        User, Depends(deps.check_permissions([BID_TASK_WRITE]))
    ],
) -> Any:
    """Assign all unassigned bid tasks for a lead to the COO user."""
    lead = await db.get(Lead, lead_id)
    if not lead:
        raise _lead_not_found_exc(lead_id)
    if not await _user_can_access_lead(db, current_user, lead):
        raise _lead_forbidden_exc(lead_id)

    # Find COO user
    coo_q = (
        select(User)
        .join(user_roles, user_roles.c.user_id == User.id)
        .join(Role, Role.id == user_roles.c.role_id)
        .where(func.lower(Role.name) == "coo")
        .limit(1)
    )
    coo_user = (await db.execute(coo_q)).scalar_one_or_none()
    if not coo_user:
        raise HTTPException(
            status_code=404,
            detail=_err("COO_NOT_FOUND", "No user with COO role found", {}),
        )

    # Get unassigned tasks
    all_tasks_q = select(LeadBidTask).where(
        and_(LeadBidTask.lead_id == lead_id, LeadBidTask.is_archived.is_(False))
    )
    all_tasks = (await db.execute(all_tasks_q)).scalars().all()

    assigned_ids_q = (
        select(LeadBidTaskAssignment.bid_task_id)
        .where(
            LeadBidTaskAssignment.bid_task_id.in_([t.id for t in all_tasks])
        )
        .distinct()
    )
    assigned_ids = set((await db.execute(assigned_ids_q)).scalars().all())

    unassigned_tasks = [t for t in all_tasks if t.id not in assigned_ids]
    if not unassigned_tasks:
        raise HTTPException(
            status_code=400,
            detail=_err(
                "NO_UNASSIGNED", "All bid tasks are already assigned", {}
            ),
        )

    # Ensure estimate version exists
    await _ensure_lead_has_estimate_version(
        db=db, request=request, lead=lead, current_user=current_user
    )

    new_assignments = []
    for task in unassigned_tasks:
        task.delivery_pm_user_id = coo_user.id
        assignment = LeadBidTaskAssignment(
            bid_task_id=task.id,
            pm_user_id=coo_user.id,
            assigned_by_id=current_user.id,
        )
        db.add(assignment)
        new_assignments.append(assignment)

    _log_audit(
        db=db,
        request=request,
        user_id=current_user.id,
        action="bd.bid_task.assign_unassigned_to_coo",
        resource_type="lead",
        resource_id=str(lead_id),
        details={
            "coo_user_id": coo_user.id,
            "task_count": len(unassigned_tasks),
        },
    )
    await db.commit()

    for a in new_assignments:
        await db.refresh(a)

    q = (
        select(LeadBidTaskAssignment)
        .where(
            LeadBidTaskAssignment.id.in_([a.id for a in new_assignments])
        )
        .options(selectinload(LeadBidTaskAssignment.pm_user))
    )
    res = await db.execute(q)
    return [
        LeadBidTaskAssignmentRead.model_validate(a, from_attributes=True)
        for a in res.scalars().all()
    ]


@router.post(
    "/leads/{lead_id}/bid-tasks/{bid_task_id}/archive",
    responses=_COMMON_ERROR_RESPONSES,
)
async def archive_bid_task(
    *,
    db: deps.DBDep,
    request: Request,
    lead_id: int,
    bid_task_id: int,
    current_user: Annotated[
        User, Depends(deps.check_permissions([BID_TASK_WRITE]))
    ],
) -> Any:
    """Archive a bid task (soft delete). Archived tasks are excluded from finalization."""
    lead = await db.get(Lead, lead_id)
    if not lead:
        raise _lead_not_found_exc(lead_id)

    task = await db.get(LeadBidTask, bid_task_id)
    if not task or task.lead_id != lead_id:
        raise HTTPException(status_code=404, detail="Bid task not found")

    task.is_archived = True
    _log_audit(
        db=db,
        request=request,
        user_id=current_user.id,
        action="bd.bid_task.archive",
        resource_type="lead_bid_task",
        resource_id=str(bid_task_id),
        details={"lead_id": lead_id},
    )
    await db.commit()
    return {"message": "Bid task archived", "bid_task_id": bid_task_id}


@router.delete(
    "/leads/{lead_id}/bid-tasks/{bid_task_id}",
    responses=_COMMON_ERROR_RESPONSES,
)
async def delete_bid_task(
    *,
    db: deps.DBDep,
    request: Request,
    lead_id: int,
    bid_task_id: int,
    current_user: Annotated[
        User, Depends(deps.check_permissions([BID_TASK_WRITE]))
    ],
) -> Any:
    """Delete a bid task. Only allowed if it has no assignments."""
    lead = await db.get(Lead, lead_id)
    if not lead:
        raise _lead_not_found_exc(lead_id)

    task = await db.get(LeadBidTask, bid_task_id)
    if not task or task.lead_id != lead_id:
        raise HTTPException(status_code=404, detail="Bid task not found")

    assignment_count = (
        await db.execute(
            select(func.count(LeadBidTaskAssignment.id)).where(
                LeadBidTaskAssignment.bid_task_id == bid_task_id
            )
        )
    ).scalar() or 0

    if assignment_count > 0:
        raise HTTPException(
            status_code=409,
            detail=_err(
                "HAS_ASSIGNMENTS",
                "Cannot delete a bid task that has PM assignments. Archive it instead.",
                {"assignment_count": assignment_count},
            ),
        )

    await db.delete(task)
    _log_audit(
        db=db,
        request=request,
        user_id=current_user.id,
        action="bd.bid_task.delete",
        resource_type="lead_bid_task",
        resource_id=str(bid_task_id),
        details={"lead_id": lead_id},
    )
    await db.commit()
    return {"message": "Bid task deleted", "bid_task_id": bid_task_id}


@router.get(
    "/bid-task-assignments/{assignment_id}/documents",
    response_model=List[BidTaskAssignmentDocumentRead],
    responses=_COMMON_ERROR_RESPONSES,
)
async def list_assignment_documents(
    *,
    db: deps.DBDep,
    assignment_id: int,
    current_user: Annotated[
        User, Depends(deps.check_permissions([BID_TASK_READ]))
    ],
) -> Any:
    assignment = await db.get(LeadBidTaskAssignment, assignment_id)
    if not assignment:
        raise _assignment_not_found_exc(assignment_id)
    exc = await _ensure_assignment_access(db, current_user, assignment)
    if exc:
        raise exc

    q = (
        select(LeadDocument)
        .join(
            LeadBidTaskAssignmentDocument,
            LeadBidTaskAssignmentDocument.lead_document_id
            == LeadDocument.id,
        )
        .where(LeadBidTaskAssignmentDocument.assignment_id == assignment_id)
        .order_by(LeadDocument.uploaded_at.desc(), LeadDocument.id.desc())
    )
    res = await db.execute(q)
    docs = res.scalars().all()
    return [
        _as_assignment_document(assignment_id=assignment_id, doc=d)
        for d in docs
    ]


@router.get(
    "/bid-task-assignments/{assignment_id}/documents/{doc_id}/download",
    responses=_COMMON_ERROR_RESPONSES,
)
async def download_assignment_document(
    *,
    db: deps.DBDep,
    assignment_id: int,
    doc_id: int,
    current_user: Annotated[
        User, Depends(deps.check_permissions([BID_TASK_READ]))
    ],
) -> Any:
    assignment = await db.get(LeadBidTaskAssignment, assignment_id)
    if not assignment:
        raise _assignment_not_found_exc(assignment_id)
    exc = await _ensure_assignment_access(db, current_user, assignment)
    if exc:
        raise exc

    q = (
        select(LeadDocument)
        .join(
            LeadBidTaskAssignmentDocument,
            LeadBidTaskAssignmentDocument.lead_document_id
            == LeadDocument.id,
        )
        .where(
            LeadBidTaskAssignmentDocument.assignment_id == assignment_id,
            LeadDocument.id == doc_id,
        )
    )
    doc = (await db.execute(q)).scalar_one_or_none()
    if not doc:
        raise HTTPException(
            status_code=404,
            detail=_err(
                "DOCUMENT_NOT_FOUND",
                "Document not attached to this assignment",
                {"assignment_id": assignment_id, "doc_id": doc_id},
            ),
        )

    base = Path(settings.LEAD_DOCUMENTS_DIR)
    abs_path = base / doc.storage_path
    if not abs_path.exists():
        raise HTTPException(
            status_code=404,
            detail=_err(
                "FILE_NOT_FOUND",
                "Stored file is missing",
                {"doc_id": doc_id},
            ),
        )

    return FileResponse(
        path=str(abs_path),
        media_type=doc.mime_type or "application/octet-stream",
        filename=doc.file_name,
    )


@router.get(
    "/bid-task-assignments/{assignment_id}/reviews/latest",
    response_model=LeadBidTaskReviewRead,
    responses=_COMMON_ERROR_RESPONSES,
)
async def get_or_create_latest_review(
    *,
    db: deps.DBDep,
    assignment_id: int,
    estimate_version_id: Annotated[int, Query(ge=1)],
    current_user: Annotated[
        User, Depends(deps.check_permissions([BID_REVIEW_READ]))
    ],
) -> Any:
    assignment = await db.get(LeadBidTaskAssignment, assignment_id)
    if not assignment:
        raise _assignment_not_found_exc(assignment_id)
    exc = await _ensure_assignment_access(db, current_user, assignment)
    if exc:
        raise exc

    version = await db.get(EstimateVersion, estimate_version_id)
    if not version:
        raise _estimate_not_found_exc(estimate_version_id)

    # Ensure the estimate belongs to the same lead
    task = await db.get(LeadBidTask, assignment.bid_task_id)
    if not task or version.lead_id != task.lead_id:
        raise HTTPException(
            status_code=400,
            detail=_err(
                "VERSION_LEAD_MISMATCH",
                ERR_VERSION_LEAD_MISMATCH_MSG,
                {
                    "assignment_id": assignment_id,
                    "estimate_version_id": estimate_version_id,
                },
            ),
        )

    q = (
        select(LeadBidTaskReview)
        .where(
            and_(
                LeadBidTaskReview.assignment_id == assignment_id,
                LeadBidTaskReview.estimate_version_id == estimate_version_id,
            )
        )
        .options(selectinload(LeadBidTaskReview.lines))
        .order_by(LeadBidTaskReview.revision_number.desc())
        .limit(1)
    )
    res = await db.execute(q)
    latest = res.scalars().first()
    if latest:
        return latest

    # Pre-populate with BD's estimates if available
    bd_hours = float(task.bd_estimated_hours or 0) if task else 0.0
    bd_cost = float(task.bd_estimated_cost or 0) if task else 0.0

    review = LeadBidTaskReview(
        assignment_id=assignment_id,
        estimate_version_id=estimate_version_id,
        revision_number=1,
        status=LeadBidTaskReviewStatus.DRAFT,
        currency=version.currency,
        total_hours=bd_hours,
        total_cost=bd_cost,
        created_by_id=current_user.id,
    )
    db.add(review)
    await db.flush()

    # Seed a review line from BD's estimate so PM has a starting point
    if bd_hours > 0 or bd_cost > 0:
        seed_line = LeadBidTaskReviewLine(
            review_id=review.id,
            title=task.title if task else "Estimated scope",
            hours=bd_hours,
            cost=bd_cost,
            sort_order=0,
        )
        db.add(seed_line)

    await db.commit()

    q2 = (
        select(LeadBidTaskReview)
        .where(LeadBidTaskReview.id == review.id)
        .options(selectinload(LeadBidTaskReview.lines))
    )
    res2 = await db.execute(q2)
    return res2.scalar_one()


@router.put(
    "/bid-task-reviews/{review_id}",
    response_model=LeadBidTaskReviewRead,
    responses=_COMMON_ERROR_RESPONSES,
)
async def upsert_review(
    *,
    db: deps.DBDep,
    review_id: int,
    review_in: LeadBidTaskReviewUpsert,
    current_user: Annotated[
        User, Depends(deps.check_permissions([BID_REVIEW_WRITE]))
    ],
) -> Any:
    q = (
        select(LeadBidTaskReview)
        .where(LeadBidTaskReview.id == review_id)
        .options(selectinload(LeadBidTaskReview.lines))
    )
    res = await db.execute(q)
    review = res.scalar_one_or_none()
    if not review:
        raise _review_not_found_exc(review_id)

    assignment = await db.get(LeadBidTaskAssignment, review.assignment_id)
    if not assignment:
        raise _assignment_not_found_exc(review.assignment_id)

    exc = await _ensure_assignment_access(db, current_user, assignment)
    if exc:
        raise exc

    if review.status == LeadBidTaskReviewStatus.SUBMITTED:
        raise HTTPException(
            status_code=409,
            detail=_err(
                "REVIEW_LOCKED",
                "Submitted review cannot be edited",
                {"review_id": review_id},
            ),
        )

    review.pm_notes = review_in.pm_notes

    # Replace line items
    for existing in review.lines:
        await db.delete(existing)

    new_lines: list[LeadBidTaskReviewLine] = []
    for idx, line_in in enumerate(review_in.lines):
        new_lines.append(
            LeadBidTaskReviewLine(
                review_id=review.id,
                title=line_in.title.strip(),
                role=(line_in.role.strip() if line_in.role else None),
                description=line_in.description,
                hours=line_in.hours,
                cost=line_in.cost,
                sort_order=line_in.sort_order if line_in.sort_order else idx,
            )
        )

    db.add_all(new_lines)
    await db.flush()

    # Refresh relationships in-memory
    review.lines = new_lines
    total_hours, total_cost = _compute_totals(new_lines)
    review.total_hours = total_hours
    review.total_cost = total_cost

    await db.commit()

    q2 = (
        select(LeadBidTaskReview)
        .where(LeadBidTaskReview.id == review.id)
        .options(selectinload(LeadBidTaskReview.lines))
    )
    res2 = await db.execute(q2)
    return res2.scalar_one()


@router.get(
    "/bid-task-reviews/{review_id}",
    response_model=LeadBidTaskReviewRead,
    responses=_COMMON_ERROR_RESPONSES,
)
async def get_review(
    *,
    db: deps.DBDep,
    review_id: int,
    current_user: Annotated[
        User, Depends(deps.check_permissions([BID_REVIEW_READ]))
    ],
) -> Any:
    q = (
        select(LeadBidTaskReview)
        .where(LeadBidTaskReview.id == review_id)
        .options(selectinload(LeadBidTaskReview.lines))
    )
    res = await db.execute(q)
    review = res.scalar_one_or_none()
    if not review:
        raise _review_not_found_exc(review_id)

    assignment = await db.get(LeadBidTaskAssignment, review.assignment_id)
    if not assignment:
        raise _assignment_not_found_exc(review.assignment_id)

    exc = await _ensure_assignment_access(db, current_user, assignment)
    if exc:
        raise exc

    return review


@router.post(
    "/bid-task-reviews/{review_id}/submit",
    response_model=LeadBidTaskReviewRead,
    responses=_COMMON_ERROR_RESPONSES,
)
async def submit_review(
    *,
    db: deps.DBDep,
    request: Request,
    review_id: int,
    current_user: Annotated[
        User, Depends(deps.check_permissions([BID_REVIEW_WRITE]))
    ],
) -> Any:
    q = (
        select(LeadBidTaskReview)
        .where(LeadBidTaskReview.id == review_id)
        .options(selectinload(LeadBidTaskReview.lines))
    )
    res = await db.execute(q)
    review = res.scalar_one_or_none()
    if not review:
        raise _review_not_found_exc(review_id)

    assignment = await db.get(LeadBidTaskAssignment, review.assignment_id)
    if not assignment:
        raise _assignment_not_found_exc(review.assignment_id)

    exc = await _ensure_assignment_access(db, current_user, assignment)
    if exc:
        raise exc

    if not review.lines:
        raise HTTPException(
            status_code=400,
            detail=_err(
                "VALIDATION_ERROR",
                "Add at least one line item before submitting",
                {"review_id": review_id},
            ),
        )

    review.status = LeadBidTaskReviewStatus.SUBMITTED
    review.submitted_at = datetime.now(timezone.utc)

    _log_audit(
        db=db,
        request=request,
        user_id=current_user.id,
        action="bd.bid_review.submit",
        resource_type="lead_bid_task_review",
        resource_id=str(review.id),
        details={
            "review_id": review.id,
            "assignment_id": review.assignment_id,
            "estimate_version_id": review.estimate_version_id,
            "revision_number": review.revision_number,
        },
    )

    await db.commit()

    q2 = (
        select(LeadBidTaskReview)
        .where(LeadBidTaskReview.id == review.id)
        .options(selectinload(LeadBidTaskReview.lines))
    )
    res2 = await db.execute(q2)
    return res2.scalar_one()


@router.post(
    "/bid-task-reviews/{review_id}/request-revision",
    response_model=LeadBidTaskReviewRead,
    responses=_COMMON_ERROR_RESPONSES,
)
async def request_revision(
    *,
    db: deps.DBDep,
    request: Request,
    review_id: int,
    rev_in: LeadBidTaskReviewRevisionRequest,
    current_user: Annotated[
        User, Depends(deps.check_permissions([BID_TASK_WRITE]))
    ],
) -> Any:
    q = (
        select(LeadBidTaskReview)
        .where(LeadBidTaskReview.id == review_id)
        .options(selectinload(LeadBidTaskReview.lines))
    )
    res = await db.execute(q)
    review = res.scalar_one_or_none()
    if not review:
        raise _review_not_found_exc(review_id)

    assignment = await db.get(LeadBidTaskAssignment, review.assignment_id)
    if not assignment:
        raise _assignment_not_found_exc(review.assignment_id)

    # Ensure BD has lead access
    task = await db.get(LeadBidTask, assignment.bid_task_id)
    if not task:
        raise _bid_task_not_found_exc(bid_task_id=assignment.bid_task_id)
    lead = await db.get(Lead, task.lead_id)
    if not lead:
        raise _lead_not_found_exc(task.lead_id)
    if not await _user_can_access_lead(db, current_user, lead):
        raise _lead_forbidden_exc(lead.id)

    # Create next revision copying existing lines
    next_rev_q = await db.execute(
        select(func.max(LeadBidTaskReview.revision_number)).where(
            and_(
                LeadBidTaskReview.assignment_id == review.assignment_id,
                LeadBidTaskReview.estimate_version_id
                == review.estimate_version_id,
            )
        )
    )
    max_rev = next_rev_q.scalar_one() or 0
    next_revision_number = int(max_rev) + 1

    new_review = LeadBidTaskReview(
        assignment_id=review.assignment_id,
        estimate_version_id=review.estimate_version_id,
        revision_number=next_revision_number,
        status=LeadBidTaskReviewStatus.DRAFT,
        currency=review.currency,
        total_hours=review.total_hours,
        total_cost=review.total_cost,
        pm_notes=review.pm_notes,
        bd_notes=rev_in.bd_notes,
        created_by_id=assignment.pm_user_id,
        previous_review_id=review.id,
    )
    db.add(new_review)
    await db.flush()

    copied_lines: list[LeadBidTaskReviewLine] = []
    for line in review.lines:
        copied_lines.append(
            LeadBidTaskReviewLine(
                review_id=new_review.id,
                title=line.title,
                role=line.role,
                description=line.description,
                hours=line.hours,
                cost=line.cost,
                sort_order=line.sort_order,
            )
        )
    db.add_all(copied_lines)

    _log_audit(
        db=db,
        request=request,
        user_id=current_user.id,
        action="bd.bid_review.request_revision",
        resource_type="lead_bid_task_review",
        resource_id=str(new_review.id),
        details={
            "from_review_id": review.id,
            "to_review_id": new_review.id,
            "estimate_version_id": review.estimate_version_id,
            "revision_number": next_revision_number,
        },
    )

    await db.commit()

    q2 = (
        select(LeadBidTaskReview)
        .where(LeadBidTaskReview.id == new_review.id)
        .options(selectinload(LeadBidTaskReview.lines))
    )
    res2 = await db.execute(q2)
    return res2.scalar_one()


@router.get(
    "/leads/{lead_id}/bid-evaluations",
    response_model=LeadBidEvaluationsResponse,
    responses=_COMMON_ERROR_RESPONSES,
)
async def get_bid_evaluations(
    *,
    db: deps.DBDep,
    lead_id: int,
    estimate_version_id: Annotated[int, Query(ge=1)],
    current_user: Annotated[
        User, Depends(deps.check_permissions([BID_REVIEW_READ]))
    ],
) -> Any:
    lead = await db.get(Lead, lead_id)
    if not lead:
        raise _lead_not_found_exc(lead_id)
    if not await _user_can_access_lead(db, current_user, lead):
        raise _lead_forbidden_exc(lead_id)

    version = await db.get(EstimateVersion, estimate_version_id)
    if not version:
        raise _estimate_not_found_exc(estimate_version_id)
    if version.lead_id != lead_id:
        raise HTTPException(
            status_code=400,
            detail=_err(
                "VERSION_LEAD_MISMATCH",
                ERR_VERSION_LEAD_MISMATCH_MSG,
                {
                    "lead_id": lead_id,
                    "estimate_version_id": estimate_version_id,
                },
            ),
        )

    tasks_q = (
        select(LeadBidTask)
        .where(LeadBidTask.lead_id == lead_id)
        .options(
            selectinload(LeadBidTask.assignments).selectinload(
                LeadBidTaskAssignment.pm_user
            )
        )
    )
    tasks_res = await db.execute(tasks_q)
    tasks = tasks_res.scalars().unique().all()

    # Latest reviews per assignment
    reviews_q = (
        select(LeadBidTaskReview)
        .join(LeadBidTaskAssignment)
        .join(LeadBidTask, LeadBidTaskAssignment.bid_task_id == LeadBidTask.id)
        .where(
            and_(
                LeadBidTask.lead_id == lead_id,
                LeadBidTaskReview.estimate_version_id == estimate_version_id,
            )
        )
        .options(
            selectinload(LeadBidTaskReview.lines),
            selectinload(LeadBidTaskReview.assignment).selectinload(
                LeadBidTaskAssignment.pm_user
            ),
        )
        .order_by(
            LeadBidTaskReview.assignment_id,
            LeadBidTaskReview.revision_number.desc(),
        )
    )
    reviews_res = await db.execute(reviews_q)
    all_reviews = reviews_res.scalars().unique().all()

    latest_by_assignment: dict[int, LeadBidTaskReview] = {}
    for r in all_reviews:
        if r.assignment_id not in latest_by_assignment:
            latest_by_assignment[r.assignment_id] = r

    task_out: list[LeadBidTaskWithAssignments] = []
    review_out: list[LeadBidTaskReviewSummary] = []

    for task in tasks:
        assignments = task.assignments
        is_pm_view = (
            not current_user.is_superuser
            and not _user_has_permission(current_user, BID_TASK_WRITE)
        )
        if is_pm_view and assignments:
            assignments = [
                a for a in assignments if a.pm_user_id == current_user.id
            ]

        task_out.append(_as_task_with_assignments(task, assignments))
        review_out.extend(
            _as_review_summaries(assignments, latest_by_assignment)
        )

    return LeadBidEvaluationsResponse(
        lead_id=lead_id,
        estimate_version_id=estimate_version_id,
        tasks=task_out,
        reviews=review_out,
    )


@router.get(
    "/leads/{lead_id}/estimates/{estimate_version_id}/pm-submissions-summary",
    response_model=PMSubmissionsSummaryResponse,
    responses=_COMMON_ERROR_RESPONSES,
)
async def get_pm_submissions_summary(
    *,
    db: deps.DBDep,
    lead_id: int,
    estimate_version_id: int,
    current_user: Annotated[
        User, Depends(deps.check_permissions([BD_ESTIMATE_WRITE]))
    ],
) -> Any:
    lead = await db.get(Lead, lead_id)
    if not lead:
        raise _lead_not_found_exc(lead_id)
    if not await _user_can_access_lead(db, current_user, lead):
        raise _lead_forbidden_exc(lead_id)

    version = await db.get(EstimateVersion, estimate_version_id)
    if not version:
        raise _estimate_not_found_exc(estimate_version_id)
    if version.lead_id != lead_id:
        raise HTTPException(
            status_code=400,
            detail=_err(
                "VERSION_LEAD_MISMATCH",
                ERR_VERSION_LEAD_MISMATCH_MSG,
                {
                    "lead_id": lead_id,
                    "estimate_version_id": estimate_version_id,
                },
            ),
        )

    assignment_ids = await _get_lead_assignment_ids(db, lead_id)
    if not assignment_ids:
        return PMSubmissionsSummaryResponse(
            lead_id=lead_id,
            estimate_version_id=estimate_version_id,
            included_reviews=[],
            role_totals=[],
        )

    latest_submitted_by_assignment = (
        await _get_latest_reviews_by_assignment(
            db=db,
            assignment_ids=assignment_ids,
            estimate_version_id=estimate_version_id,
            status=LeadBidTaskReviewStatus.ACCEPTED,
        )
    )
    if not latest_submitted_by_assignment:
        return PMSubmissionsSummaryResponse(
            lead_id=lead_id,
            estimate_version_id=estimate_version_id,
            included_reviews=[],
            role_totals=[],
        )

    role_totals, included_reviews = _aggregate_role_totals(
        list(latest_submitted_by_assignment.values())
    )
    role_totals_list: list[dict[str, Any]] = []
    for role_name in sorted(role_totals.keys(), key=lambda s: s.lower()):
        hours = float(role_totals[role_name]["hours"] or 0)
        cost = float(role_totals[role_name]["cost"] or 0)
        rate = float(cost / hours) if hours > 0 else 0.0
        role_totals_list.append(
            {"role": role_name, "hours": hours, "cost": cost, "rate": rate}
        )

    return PMSubmissionsSummaryResponse.model_validate(
        {
            "lead_id": lead_id,
            "estimate_version_id": estimate_version_id,
            "included_reviews": included_reviews,
            "role_totals": role_totals_list,
        }
    )


@router.post(
    "/leads/{lead_id}/estimates/{estimate_version_id}/apply-pm-submissions",
    response_model=EstimateVersionDetailed,
    responses=_COMMON_ERROR_RESPONSES,
)
async def apply_pm_submissions_to_estimate(
    *,
    db: deps.DBDep,
    request: Request,
    lead_id: int,
    estimate_version_id: int,
    current_user: Annotated[
        User, Depends(deps.check_permissions([BD_ESTIMATE_WRITE]))
    ],
) -> Any:
    lead = await db.get(Lead, lead_id)
    if not lead:
        raise _lead_not_found_exc(lead_id)
    if not await _user_can_access_lead(db, current_user, lead):
        raise _lead_forbidden_exc(lead_id)

    version = await db.get(EstimateVersion, estimate_version_id)
    if not version:
        raise _estimate_not_found_exc(estimate_version_id)
    if version.lead_id != lead_id:
        raise HTTPException(
            status_code=400,
            detail=_err(
                "VERSION_LEAD_MISMATCH",
                ERR_VERSION_LEAD_MISMATCH_MSG,
                {
                    "lead_id": lead_id,
                    "estimate_version_id": estimate_version_id,
                },
            ),
        )

    # Check for unassigned bid tasks — all must be assigned before finalization
    all_tasks_q = select(LeadBidTask.id, LeadBidTask.title).where(
        and_(LeadBidTask.lead_id == lead_id, LeadBidTask.is_archived.is_(False))
    )
    all_tasks_res = await db.execute(all_tasks_q)
    all_tasks = all_tasks_res.all()

    assigned_task_ids_q = (
        select(LeadBidTaskAssignment.bid_task_id)
        .where(
            LeadBidTaskAssignment.bid_task_id.in_([t.id for t in all_tasks])
        )
        .distinct()
    )
    assigned_task_ids = set(
        (await db.execute(assigned_task_ids_q)).scalars().all()
    )
    unassigned = [
        {"id": t.id, "title": t.title}
        for t in all_tasks
        if t.id not in assigned_task_ids
    ]
    if unassigned:
        raise HTTPException(
            status_code=400,
            detail=_err(
                "UNASSIGNED_BID_TASKS",
                f"{len(unassigned)} bid task(s) are not assigned to any PM. "
                "Assign them or use 'Assign to COO' before finalizing.",
                {"unassigned_tasks": unassigned},
            ),
        )

    assignment_ids = await _get_lead_assignment_ids(db, lead_id)
    if not assignment_ids:
        raise HTTPException(
            status_code=400,
            detail=_err(
                "NO_ASSIGNMENTS",
                "No PM assignments found for this lead",
                {"lead_id": lead_id},
            ),
        )

    latest_submitted_by_assignment = (
        await _get_latest_reviews_by_assignment(
            db=db,
            assignment_ids=assignment_ids,
            estimate_version_id=estimate_version_id,
            status=LeadBidTaskReviewStatus.ACCEPTED,
        )
    )
    if not latest_submitted_by_assignment:
        raise HTTPException(
            status_code=400,
            detail=_err(
                "NO_SUBMISSIONS",
                "No submitted PM reviews found for this estimate version",
                {
                    "lead_id": lead_id,
                    "estimate_version_id": estimate_version_id,
                },
            ),
        )

    role_totals, included_reviews = _aggregate_role_totals(
        list(latest_submitted_by_assignment.values())
    )

    # Clean sync: replace resource lines with aggregated role totals.
    await db.execute(
        delete(EstimateResourceLine).where(
            EstimateResourceLine.version_id == estimate_version_id
        )
    )

    new_resource_lines = _resource_lines_from_role_totals(
        estimate_version_id=estimate_version_id,
        role_totals=role_totals,
    )

    db.add_all(new_resource_lines)
    await db.flush()

    _recompute_estimate_totals(version, new_resource_lines)

    _log_audit(
        db=db,
        request=request,
        user_id=current_user.id,
        action="bd.estimate.apply_pm_submissions",
        resource_type="estimate_version",
        resource_id=str(estimate_version_id),
        details={
            "lead_id": lead_id,
            "estimate_version_id": estimate_version_id,
            "included_reviews": included_reviews,
            "roles": role_totals,
            "mode": "clean_sync_replace",
        },
    )

    await db.commit()

    q = (
        select(EstimateVersion)
        .where(EstimateVersion.id == estimate_version_id)
        .options(
            selectinload(EstimateVersion.phases),
            selectinload(EstimateVersion.resource_lines),
        )
    )
    updated = (await db.execute(q)).scalar_one()
    return EstimateVersionDetailed.model_validate(
        updated,
        from_attributes=True,
    )


@router.get(
    "/bid-requests/my",
    response_model=List[MyBidRequestItem],
    responses=_COMMON_ERROR_RESPONSES,
)
async def my_bid_requests(
    *,
    db: deps.DBDep,
    estimate_version_id: Annotated[Optional[int], Query(ge=1)] = None,
    current_user: Annotated[
        User, Depends(deps.check_permissions([BID_TASK_READ]))
    ],
) -> Any:
    # List tasks assigned to the current PM.
    # IMPORTANT: show assignments even before any review is created.

    version_id_expr: Any
    join_version_target: Any
    join_version_on: Any

    if estimate_version_id is None:
        latest_version = (
            select(
                EstimateVersion.lead_id.label("lead_id"),
                func.max(EstimateVersion.id).label("estimate_version_id"),
            )
            .group_by(EstimateVersion.lead_id)
            .subquery()
        )
        version_id_expr = latest_version.c.estimate_version_id
        join_version_target = latest_version
        join_version_on = latest_version.c.lead_id == Lead.id
    else:
        version_id_expr = EstimateVersion.id
        join_version_target = EstimateVersion
        join_version_on = and_(
            EstimateVersion.lead_id == Lead.id,
            EstimateVersion.id == estimate_version_id,
        )

    q = (
        select(
            Lead.id.label("lead_id"),
            Lead.title.label("lead_title"),
            Lead.lead_id.label("lead_code"),
            version_id_expr.label("estimate_version_id"),
            LeadBidTask.id.label("bid_task_id"),
            LeadBidTask.title.label("bid_task_title"),
            LeadBidTask.bd_estimated_hours.label(
                "bd_estimated_hours"
            ),
            LeadBidTask.bd_estimated_cost.label(
                "bd_estimated_cost"
            ),
            LeadBidTaskAssignment.id.label("assignment_id"),
            LeadBidTaskAssignment.deadline.label("deadline"),
            LeadBidTaskReview.status.label("latest_review_status"),
            LeadBidTaskReview.revision_number.label(
                "latest_revision_number"
            ),
            LeadBidTaskReview.updated_at.label("updated_at"),
            LeadBidTaskAssignment.created_at.label(
                "assignment_created_at"
            ),
        )
        .join(LeadBidTask, LeadBidTask.lead_id == Lead.id)
        .join(
            LeadBidTaskAssignment,
            LeadBidTaskAssignment.bid_task_id == LeadBidTask.id,
        )
        .join(join_version_target, join_version_on)
        .outerjoin(
            LeadBidTaskReview,
            and_(
                LeadBidTaskReview.assignment_id
                == LeadBidTaskAssignment.id,
                LeadBidTaskReview.estimate_version_id == version_id_expr,
            ),
        )
        .where(LeadBidTaskAssignment.pm_user_id == current_user.id)
        .order_by(
            LeadBidTaskAssignment.id,
            LeadBidTaskReview.revision_number.desc(),
        )
    )

    rows = (await db.execute(q)).all()
    latest: dict[int, Any] = {}
    for row in rows:
        if row.assignment_id not in latest:
            latest[row.assignment_id] = row

    assignment_ids = [int(a_id) for a_id in latest.keys()]
    docs_by_assignment: dict[int, list[LeadDocument]] = {}
    if assignment_ids:
        q_docs = (
            select(
                LeadBidTaskAssignmentDocument.assignment_id,
                LeadDocument,
            )
            .join(
                LeadDocument,
                LeadDocument.id
                == LeadBidTaskAssignmentDocument.lead_document_id,
            )
            .where(
                LeadBidTaskAssignmentDocument.assignment_id.in_(
                    assignment_ids
                )
            )
            .order_by(
                LeadDocument.uploaded_at.desc(),
                LeadDocument.id.desc(),
            )
        )

        for a_id, doc in (await db.execute(q_docs)).all():
            docs_by_assignment.setdefault(int(a_id), []).append(doc)

    out: list[MyBidRequestItem] = []
    for r in latest.values():
        mapping = dict(r._mapping)
        if mapping.get("latest_review_status") is None:
            mapping["latest_review_status"] = LeadBidTaskReviewStatus.DRAFT
        if mapping.get("latest_revision_number") is None:
            mapping["latest_revision_number"] = 0
        if mapping.get("updated_at") is None:
            mapping["updated_at"] = mapping.get("assignment_created_at")
        mapping.pop("assignment_created_at", None)

        assignment_id = int(mapping["assignment_id"])
        mapping["documents"] = [
            _as_assignment_document(assignment_id=assignment_id, doc=d)
            for d in docs_by_assignment.get(assignment_id, [])
        ]
        out.append(MyBidRequestItem(**mapping))

    return out


@router.post(
    "/bid-task-reviews/{review_id}/accept",
    response_model=LeadBidTaskReviewRead,
    responses=_COMMON_ERROR_RESPONSES,
)
async def accept_review(
    *,
    db: deps.DBDep,
    request: Request,
    review_id: int,
    current_user: Annotated[
        User, Depends(deps.check_permissions([BID_TASK_WRITE]))
    ],
) -> Any:
    """BD accepts a submitted PM review. Marks it ACCEPTED so it feeds into the estimate."""
    q = (
        select(LeadBidTaskReview)
        .where(LeadBidTaskReview.id == review_id)
        .options(selectinload(LeadBidTaskReview.lines))
    )
    res = await db.execute(q)
    review = res.scalar_one_or_none()
    if not review:
        raise _review_not_found_exc(review_id)

    if review.status != LeadBidTaskReviewStatus.SUBMITTED:
        raise HTTPException(
            status_code=409,
            detail=_err(
                "REVIEW_NOT_SUBMITTED",
                "Only SUBMITTED reviews can be accepted",
                {"review_id": review_id, "current_status": review.status},
            ),
        )

    # Verify BD has lead access
    assignment = await db.get(LeadBidTaskAssignment, review.assignment_id)
    if not assignment:
        raise _assignment_not_found_exc(review.assignment_id)
    task = await db.get(LeadBidTask, assignment.bid_task_id)
    if not task:
        raise _bid_task_not_found_exc(bid_task_id=assignment.bid_task_id)
    lead = await db.get(Lead, task.lead_id)
    if not lead:
        raise _lead_not_found_exc(task.lead_id)
    if not await _user_can_access_lead(db, current_user, lead):
        raise _lead_forbidden_exc(lead.id)

    review.status = LeadBidTaskReviewStatus.ACCEPTED
    await db.flush()

    # Auto-sync estimate resource lines from all accepted reviews for this version
    version = await db.get(EstimateVersion, review.estimate_version_id)
    if version:
        assignment_ids = await _get_lead_assignment_ids(db, lead.id)
        accepted_by_assignment = await _get_latest_reviews_by_assignment(
            db=db,
            assignment_ids=assignment_ids,
            estimate_version_id=review.estimate_version_id,
            status=LeadBidTaskReviewStatus.ACCEPTED,
        )
        if accepted_by_assignment:
            role_totals, _ = _aggregate_role_totals(list(accepted_by_assignment.values()))
            await db.execute(
                delete(EstimateResourceLine).where(
                    EstimateResourceLine.version_id == review.estimate_version_id
                )
            )
            new_lines = _resource_lines_from_role_totals(
                estimate_version_id=review.estimate_version_id,
                role_totals=role_totals,
            )
            db.add_all(new_lines)
            await db.flush()
            _recompute_estimate_totals(version, new_lines)

    _log_audit(
        db=db,
        request=request,
        user_id=current_user.id,
        action="bd.bid_review.accept",
        resource_type="lead_bid_task_review",
        resource_id=str(review.id),
        details={
            "review_id": review.id,
            "assignment_id": review.assignment_id,
            "estimate_version_id": review.estimate_version_id,
        },
    )

    await db.commit()

    q2 = (
        select(LeadBidTaskReview)
        .where(LeadBidTaskReview.id == review.id)
        .options(selectinload(LeadBidTaskReview.lines))
    )
    return (await db.execute(q2)).scalar_one()
