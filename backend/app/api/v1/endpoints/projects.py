from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
import re
import secrets
import io
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Query
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select, and_, or_, desc, func
from sqlalchemy.orm import selectinload
from app.api import deps
from app.core.config import settings
from app.models.project import (
    Project, Milestone, CostBaseline, CostChangeRequest,
    CostChangeStatus, ProjectMember
)
from app.models.project_document import ProjectDocument
from app.models.user import User
from app.schemas.project import (
    ProjectCreateRequest,
    ProjectRead,
    ProjectMemberRead,
    ProjectMemberCreate,
    MilestoneBase, MilestoneRead,
    CostBaselineBase, CostBaselineRead,
    CostChangeRequestBase, CostChangeRequestRead,
    CostChangeAction
)
from app.schemas.user import UserRead
from app.models.audit import AuditLog

router = APIRouter()

COST_THRESHOLD = 0.1  # 10%
PROJECT_WRITE = "project write"
PROJECT_COST_APPROVE_PM = "project cost approve pm"
PROJECT_COST_APPROVE_DOP = "project cost approve dop"


# Project Members
@router.get("/users", response_model=List[UserRead])
async def list_users_for_allocation(
    *,
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user)
) -> Any:
    """List active users for PM to allocate to projects."""
    result = await db.execute(
        select(User).where(User.is_active.is_(True)).order_by(User.full_name)
    )
    return result.scalars().all()


@router.post("/{project_id}/members", response_model=ProjectMemberRead)
async def add_project_member(
    *,
    db: deps.DBDep,
    project_id: int,
    obj_in: ProjectMemberCreate,
    current_user: User = Depends(deps.get_current_user)
) -> Any:
    # Check project exists
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Check if user is manager or admin
    is_pm = (await db.execute(
        select(ProjectMember).where(
            and_(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == current_user.id,
                ProjectMember.role == "manager"
            )
        )
    )).scalar_one_or_none()
    
    if not is_pm and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Not authorized to add members")

    # Check if user already a member
    existing = (await db.execute(
        select(ProjectMember).where(
            and_(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == obj_in.user_id
            )
        )
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="User already a project member")

    member = ProjectMember(
        project_id=project_id,
        user_id=obj_in.user_id,
        role=obj_in.role
    )
    db.add(member)
    await db.commit()
    await db.refresh(member)
    
    # Manual enrichment for schema
    user_res = (await db.execute(select(User).where(User.id == member.user_id))).scalar_one()
    member.user_name = user_res.full_name
    member.user_email = user_res.email
    
    return member


@router.get("/{project_id}/members", response_model=List[ProjectMemberRead])
async def list_project_members(
    db: deps.DBDep,
    project_id: int,
    current_user: User = Depends(deps.get_current_user)
) -> Any:
    result = await db.execute(
        select(ProjectMember).where(ProjectMember.project_id == project_id)
    )
    members = result.scalars().all()
    
    # Enrich with user details
    enriched_members = []
    for m in members:
        user_res = (await db.execute(select(User).where(User.id == m.user_id))).scalar_one()
        m.user_name = user_res.full_name
        m.user_email = user_res.email
        enriched_members.append(m)
        
    return enriched_members


@router.delete("/{project_id}/members/{user_id}", status_code=204)
async def remove_project_member(
    db: deps.DBDep,
    project_id: int,
    user_id: int,
    current_user: User = Depends(deps.get_current_user)
) -> None:
    # Check project exists
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Check authorization
    is_pm = (await db.execute(
        select(ProjectMember).where(
            and_(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == current_user.id,
                ProjectMember.role == "manager"
            )
        )
    )).scalar_one_or_none()
    
    if not is_pm and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Not authorized to remove members")

    member = (await db.execute(
        select(ProjectMember).where(
            and_(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user_id
            )
        )
    )).scalar_one_or_none()
    
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    
    if member.role == "manager" and member.user_id == project.lead_id:
         raise HTTPException(status_code=400, detail="Cannot remove project lead manager")

    await db.delete(member)
    await db.commit()


async def _generate_project_code(db: deps.DBDep, name: str) -> str:
    base = re.sub(r"[^A-Z0-9]+", "", (name or "").upper())
    base = base[:8] or "PRJ"

    candidate = f"{base}{int(datetime.now(timezone.utc).timestamp())}"
    candidate = candidate[:20]

    exists = (
        await db.execute(select(Project).where(Project.code == candidate))
    ).scalar_one_or_none()
    if not exists:
        return candidate

    suffix = secrets.token_hex(2).upper()
    return f"{candidate[: (20 - len(suffix))]}{suffix}"


@router.post("/", response_model=ProjectRead)
async def create_project(
    *,
    db: deps.DBDep,
    request: Request,
    obj_in: ProjectCreateRequest,
    current_user: User = Depends(deps.check_permissions([PROJECT_WRITE])),
) -> Any:
    """Create a project and assign the creator as manager."""
    code = (obj_in.code or "").strip()
    if not code:
        code = await _generate_project_code(db, obj_in.name)

    existing = (
        await db.execute(select(Project).where(Project.code == code))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Project code already exists")

    client_name: Optional[str] = None
    if obj_in.client_id is not None:
        from app.models.bd import Account
        account = await db.get(Account, obj_in.client_id)
        if not account:
            raise HTTPException(status_code=400, detail="Client not found")
        client_name = account.name

    project = Project(
        name=obj_in.name,
        description=obj_in.description,
        code=code,
        status=obj_in.status,
        client_id=obj_in.client_id,
    )
    db.add(project)
    await db.flush()

    db.add(
        ProjectMember(
            project_id=project.id, user_id=current_user.id, role="manager"
        )
    )

    # Auto-create cost baseline if budget is provided
    if obj_in.budget and obj_in.budget > 0:
        baseline = CostBaseline(
            project_id=project.id,
            amount=obj_in.budget,
            budget_hours=obj_in.budget_hours,
            description="Initial budget",
            is_active=True,
        )
        db.add(baseline)

    log_audit(
        db,
        current_user.id,
        "CREATE",
        "project",
        str(project.id),
        {"name": project.name, "code": project.code},
        request,
    )

    await db.commit()
    await db.refresh(project)

    # Build response with budget info
    budget = obj_in.budget or 0.0
    budget_hours = obj_in.budget_hours
    return ProjectRead(
        id=project.id,
        name=project.name,
        description=project.description,
        code=project.code,
        status=project.status,
        created_at=project.created_at,
        client_id=project.client_id,
        client_name=client_name,
        budget=budget,
        budget_hours=budget_hours,
        actual_cost=0.0,
        start_date=project.created_at,
        end_date=obj_in.end_date,
    )


def log_audit(
    db: deps.DBDep,
    user_id: int,
    action: str,
    resource_type: str,
    resource_id: str,
    details: dict,
    request: Request
):
    audit_details = dict(details or {})
    audit_details["user_agent"] = request.headers.get("user-agent")
    audit = AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=audit_details,
        ip_address=request.client.host if request.client else None,
    )
    db.add(audit)


async def check_cost_approval_auth(
    db: deps.DBDep,
    db_obj: CostChangeRequest,
    current_user: User,
    user_perms: set
):
    is_dop = (
        current_user.is_superuser or PROJECT_COST_APPROVE_DOP in user_perms
    )
    is_pm = (
        current_user.is_superuser or PROJECT_COST_APPROVE_PM in user_perms
    )

    if db_obj.percent_change > COST_THRESHOLD:
        if not is_dop:
            raise HTTPException(
                status_code=403,
                detail="DOP approval required (threshold exceeded)"
            )
    else:
        if not is_dop:
            pm_exists = (await db.execute(
                select(ProjectMember).where(
                    and_(
                        ProjectMember.project_id == db_obj.project_id,
                        ProjectMember.user_id == current_user.id,
                        ProjectMember.role == "manager"
                    )
                )
            )).scalar_one_or_none()
            if not (is_pm and pm_exists):
                raise HTTPException(
                    status_code=403,
                    detail="PM approval required for this request"
                )


# Milestones
@router.post("/{project_id}/milestones", response_model=MilestoneRead)
async def create_milestone(
    *,
    db: deps.DBDep,
    project_id: int,
    obj_in: MilestoneBase,
    current_user: User = Depends(deps.check_permissions([PROJECT_WRITE]))
) -> Any:
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    db_obj = Milestone(
        project_id=project_id,
        **obj_in.model_dump()
    )
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj


@router.get("/{project_id}/milestones", response_model=List[MilestoneRead])
async def list_milestones(
    db: deps.DBDep,
    project_id: int,
    current_user: User = Depends(deps.get_current_user)
) -> Any:
    result = await db.execute(
        select(Milestone).where(Milestone.project_id == project_id)
        .order_by(Milestone.due_date)
    )
    return result.scalars().all()


# Costing
@router.post("/{project_id}/cost-baseline", response_model=CostBaselineRead)
async def set_cost_baseline(
    *,
    db: deps.DBDep,
    project_id: int,
    obj_in: CostBaselineBase,
    current_user: User = Depends(deps.check_permissions([PROJECT_WRITE]))
) -> Any:
    # Deactivate previous baselines
    await db.execute(
        CostBaseline.__table__.update()
        .where(CostBaseline.project_id == project_id)
        .values(is_active=False)
    )
    
    db_obj = CostBaseline(
        project_id=project_id,
        **obj_in.model_dump(exclude={"is_active"}),
        is_active=True
    )
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj


@router.get(
    "/{project_id}/cost-baseline", response_model=Optional[CostBaselineRead]
)
async def get_active_baseline(
    db: deps.DBDep,
    project_id: int,
    current_user: User = Depends(deps.get_current_user)
) -> Any:
    result = await db.execute(
        select(CostBaseline).where(
            and_(CostBaseline.project_id == project_id, CostBaseline.is_active)
        )
    )
    return result.scalar_one_or_none()


@router.post("/{project_id}/cost-change", response_model=CostChangeRequestRead)
async def request_cost_change(
    *,
    db: deps.DBDep,
    project_id: int,
    obj_in: CostChangeRequestBase,
    request: Request,
    current_user: User = Depends(deps.get_current_user)
) -> Any:
    # 1. Get active baseline
    result = await db.execute(
        select(CostBaseline).where(
            and_(CostBaseline.project_id == project_id, CostBaseline.is_active)
        )
    )
    baseline = result.scalar_one_or_none()
    if not baseline:
        raise HTTPException(
            status_code=400,
            detail="No active cost baseline found for this project"
        )

    # 2. Calculate percent change
    if baseline.amount == 0:
        percent_change = 1.0 if obj_in.proposed_amount > 0 else 0.0
    else:
        percent_change = (
            (obj_in.proposed_amount - baseline.amount) / baseline.amount
        )

    # 3. Create request
    db_obj = CostChangeRequest(
        project_id=project_id,
        baseline_id=baseline.id,
        baseline_amount=baseline.amount,
        proposed_amount=obj_in.proposed_amount,
        percent_change=percent_change,
        reason=obj_in.reason,
        impact=obj_in.impact,
        status=CostChangeStatus.SUBMITTED,
        created_by_id=current_user.id
    )
    db.add(db_obj)
    await db.flush()

    log_audit(
        db, current_user.id, "SUBMIT_COST_CHANGE", "cost_change",
        str(db_obj.id),
        {"percent_change": percent_change, "proposed": obj_in.proposed_amount},
        request
    )

    await db.commit()
    await db.refresh(db_obj)
    return db_obj


@router.get(
    "/cost-approvals/inbox", response_model=List[CostChangeRequestRead]
)
async def get_cost_approval_inbox(
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user)
) -> Any:
    """
    DOP Inbox: Show requests > threshold.
    PM Inbox: Show requests <= threshold for projects where they are members.
    """
    user_perms = {
        p.name for r in current_user.roles for p in r.permissions
    } or set()
    is_superuser = current_user.is_superuser

    query = select(CostChangeRequest).where(
        CostChangeRequest.status == CostChangeStatus.SUBMITTED
    )

    conditions = []

    # DOP logic: can see all above threshold
    if is_superuser or PROJECT_COST_APPROVE_DOP in user_perms:
        conditions.append(CostChangeRequest.percent_change > COST_THRESHOLD)

    # PM logic: can see below threshold for their projects
    if is_superuser or PROJECT_COST_APPROVE_PM in user_perms:
        # User projects where they are managers
        subquery = select(ProjectMember.project_id).where(
            and_(
                ProjectMember.user_id == current_user.id,
                ProjectMember.role == "manager"
            )
        )
        conditions.append(
            and_(
                CostChangeRequest.percent_change <= COST_THRESHOLD,
                CostChangeRequest.project_id.in_(subquery)
            )
        )

    if not conditions and not is_superuser:
        return []

    if not is_superuser:
        query = query.where(or_(*conditions))

    query = query.order_by(desc(CostChangeRequest.created_at))
    result = await db.execute(query)
    return result.scalars().all()


@router.post(
    "/cost-approvals/{request_id}/action",
    response_model=CostChangeRequestRead
)
async def cost_approval_action(
    *,
    db: deps.DBDep,
    request_id: int,
    obj_in: CostChangeAction,
    request: Request,
    current_user: User = Depends(deps.get_current_user)
) -> Any:
    db_obj = await db.get(CostChangeRequest, request_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Request not found")

    if db_obj.status != CostChangeStatus.SUBMITTED:
        raise HTTPException(status_code=400, detail="Already processed")

    # Authorization Check
    user_perms = {
        p.name for r in current_user.roles for p in r.permissions
    } or set()

    await check_cost_approval_auth(db, db_obj, current_user, user_perms)

    db_obj.status = obj_in.status

    if obj_in.status == CostChangeStatus.APPROVED:
        # Update project baseline
        await db.execute(
            CostBaseline.__table__.update()
            .where(CostBaseline.project_id == db_obj.project_id)
            .values(is_active=False)
        )
        new_baseline = CostBaseline(
            project_id=db_obj.project_id,
            amount=db_obj.proposed_amount,
            description=(
                f"Approved Change Request #{db_obj.id}: {db_obj.reason}"
            ),
            is_active=True
        )
        db.add(new_baseline)

    log_audit(
        db, current_user.id, f"{obj_in.status.upper()}_COST_CHANGE",
        "cost_change",
        str(request_id), {"remarks": obj_in.remarks}, request
    )

    await db.commit()
    await db.refresh(db_obj)
    return db_obj


# ─── COO Overview ──────────────────────────────────────────────────────────────

PROJECT_COO_VIEW = "project coo view"
COO_DASHBOARD_VIEW = "coo dashboard view"

COO_ELEVATED_ROLES = {
    "coo",
    "super admin",
    "admin",
    "ceo",
    "dop",
}


@router.get("/coo/overview", response_model=List[dict])
async def coo_project_overview(
    *,
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    COO cross-project monitoring dashboard.
    Returns all projects grouped with PM assignments, task completion %, and
    parent-child hierarchy. Accessible to COO, CEO, DOP, Super Admin.
    """
    from app.models.task import Task

    user_role_names = {
        str(getattr(r, "name", "")).strip().lower()
        for r in (getattr(current_user, "roles", None) or [])
    }
    user_perms = {
        p.name
        for r in (getattr(current_user, "roles", None) or [])
        for p in r.permissions
    }

    has_access = (
        current_user.is_superuser
        or bool(user_role_names & COO_ELEVATED_ROLES)
        or PROJECT_COO_VIEW in user_perms
        or COO_DASHBOARD_VIEW in user_perms
    )
    if not has_access:
        raise HTTPException(status_code=403, detail="COO access required")

    # Load all active projects
    proj_result = await db.execute(
        select(Project).where(Project.status == "active").order_by(Project.created_at.desc())
    )
    projects = proj_result.scalars().all()

    project_ids = [p.id for p in projects]

    # Load all members for these projects in one query
    mem_result = await db.execute(
        select(ProjectMember, User)
        .join(User, User.id == ProjectMember.user_id)
        .where(ProjectMember.project_id.in_(project_ids))
    )
    members_by_project: dict[int, list[dict]] = {}
    for member, user in mem_result.all():
        members_by_project.setdefault(int(member.project_id), []).append({
            "user_id": user.id,
            "user_name": user.full_name,
            "user_email": user.email,
            "role": member.role,
        })

    # Load task counts per project
    task_result = await db.execute(
        select(Task.project_id, Task.status, func.count(Task.id).label("cnt"))
        .where(Task.project_id.in_(project_ids))
        .group_by(Task.project_id, Task.status)
    )
    task_counts: dict[int, dict[str, int]] = {}
    for row in task_result.all():
        pid = int(row.project_id)
        task_counts.setdefault(pid, {})
        task_counts[pid][row.status] = int(row.cnt)

    # Build project map for parent-child linking
    proj_map = {p.id: p for p in projects}

    output = []
    for p in projects:
        total_tasks = sum(task_counts.get(p.id, {}).values())
        completed_tasks = task_counts.get(p.id, {}).get("completed", 0)
        completion_pct = (
            round((completed_tasks / total_tasks) * 100, 1) if total_tasks > 0 else 0.0
        )

        # Determine managers (PMs) for this project
        managers = [
            m for m in members_by_project.get(p.id, [])
            if m["role"] in ("manager", "owner")
        ]

        parent_name: str | None = None
        if getattr(p, "parent_project_id", None):
            parent = proj_map.get(int(p.parent_project_id))
            parent_name = parent.name if parent else None

        # Child projects of this project
        child_ids = [
            cp.id for cp in projects
            if getattr(cp, "parent_project_id", None) == p.id
        ]

        output.append({
            "id": p.id,
            "name": p.name,
            "code": p.code,
            "status": p.status,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "parent_project_id": getattr(p, "parent_project_id", None),
            "parent_project_name": parent_name,
            "child_project_ids": child_ids,
            "managers": managers,
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "completion_pct": completion_pct,
            "task_status_breakdown": task_counts.get(p.id, {}),
        })

    return output


# ─── Project Documents ───────────────────────────────────────

# Mirror the employee-document allowlist; same surface area, same
# threat model — uploaded files might later be served back, so we
# don't accept executables or arbitrary HTML.
_PROJECT_DOC_ALLOWED_MIME = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",
    "image/gif",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/plain",
}

_PROJECT_DOC_TYPES_ALLOWED = {"Workorder", "Contract", "Other"}

_DOC_MANAGE_ROLES = {
    "bd", "bd manager", "coo", "admin", "super admin", "ceo",
}


def _project_docs_dir() -> Path:
    return Path(settings.PROJECT_DOCUMENTS_DIR)


def _user_role_names(user: User) -> set[str]:
    return {(r.name or "").lower() for r in (user.roles or [])}


def _can_manage_project_docs(user: User, is_member: bool) -> bool:
    """Authorization for upload / delete on project documents.

    The user explicitly listed BD, COO, and admin/super-admin as
    permitted. Project members are also allowed because they're already
    trusted with the project's full data — this avoids HR/PM friction
    on day-to-day uploads.
    """
    if user.is_superuser:
        return True
    return is_member or bool(_user_role_names(user) & _DOC_MANAGE_ROLES)


async def _is_project_member(db, project_id: int, user_id: int) -> bool:
    row = (await db.execute(
        select(ProjectMember.id).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        ).limit(1)
    )).scalar_one_or_none()
    return row is not None


def _serialize_project_doc(doc: ProjectDocument) -> Dict[str, Any]:
    return {
        "id": doc.id,
        "project_id": doc.project_id,
        "doc_type": doc.doc_type,
        "original_filename": doc.original_filename,
        "mime_type": doc.mime_type,
        "file_size": doc.file_size,
        "remark": doc.remark,
        "uploaded_at": doc.uploaded_at.isoformat() if doc.uploaded_at else None,
        "uploaded_by_id": doc.uploaded_by_id,
        "uploaded_by_name": doc.uploaded_by.full_name if doc.uploaded_by else None,
        "download_url": f"/api/v1/projects/{doc.project_id}/documents/{doc.id}/download",
    }


def _safe_project_filename(original: str) -> tuple[str, str]:
    safe = (original or "document").replace("/", "_").replace("\\", "_").lstrip(".")[:200]
    if not safe:
        safe = "document"
    return safe, f"{uuid4().hex}_{safe}"


@router.get("/{project_id}/documents")
async def list_project_documents(
    *,
    db: deps.DBDep,
    project_id: int,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """List all documents attached to a project. Read access is intentionally
    broad — anyone who can see the project can see its documents."""
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    rows = (await db.execute(
        select(ProjectDocument)
        .where(ProjectDocument.project_id == project_id)
        .options(selectinload(ProjectDocument.uploaded_by))
        .order_by(ProjectDocument.uploaded_at.desc())
    )).scalars().all()
    return [_serialize_project_doc(d) for d in rows]


@router.post("/{project_id}/documents/upload")
async def upload_project_document(
    *,
    db: deps.DBDep,
    request: Request,
    project_id: int,
    file: UploadFile = File(...),
    doc_type: str = Query("Workorder"),
    remark: Optional[str] = Query(None),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Upload a document (workorder by default) to a project."""
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    is_member = await _is_project_member(db, project_id, current_user.id)
    if not _can_manage_project_docs(current_user, is_member):
        raise HTTPException(
            status_code=403,
            detail="You don't have permission to upload documents for this project",
        )

    if doc_type not in _PROJECT_DOC_TYPES_ALLOWED:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown document type '{doc_type}'",
        )

    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    content_type = (file.content_type or "").lower()
    if content_type and content_type not in _PROJECT_DOC_ALLOWED_MIME:
        raise HTTPException(
            status_code=400,
            detail=(
                "Unsupported file type. Allowed: PDF, JPG, PNG, WebP, HEIC, "
                "GIF, Word, Excel, or plain text."
            ),
        )

    max_bytes = int(settings.PROJECT_DOCUMENT_MAX_BYTES)
    content = await file.read()
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {max_bytes // (1024 * 1024)} MB",
        )

    docs_dir = _project_docs_dir() / str(project_id)
    docs_dir.mkdir(parents=True, exist_ok=True)
    safe_name, stored_name = _safe_project_filename(file.filename)
    (docs_dir / stored_name).write_bytes(content)

    doc = ProjectDocument(
        project_id=project_id,
        doc_type=doc_type,
        original_filename=safe_name,
        stored_filename=stored_name,
        mime_type=content_type or "application/octet-stream",
        file_size=len(content),
        remark=remark,
        uploaded_by_id=current_user.id,
    )
    db.add(doc)
    await db.flush()

    db.add(AuditLog(
        user_id=current_user.id,
        action="UPLOAD",
        resource_type="project_document",
        resource_id=str(doc.id),
        details={
            "project_id": project_id,
            "project_name": project.name,
            "doc_type": doc_type,
            "filename": safe_name,
            "size": len(content),
        },
        ip_address=request.client.host if request and request.client else None,
        user_agent=request.headers.get("user-agent") if request else None,
    ))

    await db.commit()
    await db.refresh(doc)
    # Hydrate uploaded_by for the response
    await db.refresh(doc, attribute_names=["uploaded_by"])
    return _serialize_project_doc(doc)


@router.get("/{project_id}/documents/{doc_id}/download")
async def download_project_document(
    *,
    db: deps.DBDep,
    project_id: int,
    doc_id: int,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Authenticated file download. Same read gate as the list endpoint."""
    doc = (await db.execute(
        select(ProjectDocument).where(
            ProjectDocument.id == doc_id,
            ProjectDocument.project_id == project_id,
        )
    )).scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    file_path = _project_docs_dir() / str(project_id) / doc.stored_filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File missing on disk")
    return FileResponse(
        path=str(file_path),
        filename=doc.original_filename,
        media_type=doc.mime_type or "application/octet-stream",
    )


@router.delete("/{project_id}/documents/{doc_id}", status_code=204)
async def delete_project_document(
    *,
    db: deps.DBDep,
    request: Request,
    project_id: int,
    doc_id: int,
    current_user: User = Depends(deps.get_current_user),
) -> None:
    """Delete is restricted further: the uploader, COO, admin/super-admin,
    or CEO. Project members at large can't undo someone else's upload."""
    doc = await db.get(ProjectDocument, doc_id)
    if not doc or doc.project_id != project_id:
        raise HTTPException(status_code=404, detail="Document not found")

    role_names = _user_role_names(current_user)
    privileged = bool(role_names & {"coo", "admin", "super admin", "ceo"})
    is_uploader = doc.uploaded_by_id == current_user.id
    if not (current_user.is_superuser or privileged or is_uploader):
        raise HTTPException(
            status_code=403,
            detail="Only the uploader, COO, or admin can delete this document",
        )

    file_path = _project_docs_dir() / str(project_id) / doc.stored_filename
    original = doc.original_filename

    db.add(AuditLog(
        user_id=current_user.id,
        action="DELETE",
        resource_type="project_document",
        resource_id=str(doc_id),
        details={
            "project_id": project_id,
            "doc_type": doc.doc_type,
            "filename": original,
        },
        ip_address=request.client.host if request and request.client else None,
        user_agent=request.headers.get("user-agent") if request else None,
    ))

    await db.delete(doc)
    await db.commit()

    if file_path.exists():
        try:
            file_path.unlink()
        except OSError:
            # DB row is gone — orphan file is acceptable, gets cleaned up
            # next time the project is deleted.
            pass


# ─── Bulk Upload (super admin only) ───────────────────────────────────────────

PROJECT_BULK_COL_NAME = "Project Name"
PROJECT_BULK_COL_CLIENT = "Client Name"
PROJECT_BULK_COL_CODE = "Project Code"
PROJECT_BULK_COL_DESCRIPTION = "Description"
PROJECT_BULK_COL_STATUS = "Status"
PROJECT_BULK_COL_BUDGET = "Budget"
PROJECT_BULK_COL_BUDGET_HOURS = "Budget Hours"
PROJECT_BULK_COL_END_DATE = "End Date"
PROJECT_BULK_COL_MANAGER_EMAIL = "Manager Email"

PROJECT_BULK_TEMPLATE_COLUMNS = [
    PROJECT_BULK_COL_NAME,
    PROJECT_BULK_COL_CLIENT,
    PROJECT_BULK_COL_CODE,
    PROJECT_BULK_COL_DESCRIPTION,
    PROJECT_BULK_COL_STATUS,
    PROJECT_BULK_COL_BUDGET,
    PROJECT_BULK_COL_BUDGET_HOURS,
    PROJECT_BULK_COL_END_DATE,
    PROJECT_BULK_COL_MANAGER_EMAIL,
]

PROJECT_BULK_EXAMPLE_NAMES = {"website overhaul", "mobile app v2"}


def _is_super_admin(current_user: User) -> bool:
    if current_user.is_superuser:
        return True
    role_names = _user_role_names(current_user)
    return bool(role_names & {"super admin", "admin"})


@router.get("/template")
async def download_project_template(
    current_user: User = Depends(deps.get_current_user),
) -> StreamingResponse:
    if not _is_super_admin(current_user):
        raise HTTPException(
            status_code=403,
            detail="Only super admin can access the project template",
        )

    import pandas as pd

    example_rows = [
        {
            PROJECT_BULK_COL_NAME: "Website Overhaul",
            PROJECT_BULK_COL_CLIENT: "Acme Corp",
            PROJECT_BULK_COL_CODE: "",
            PROJECT_BULK_COL_DESCRIPTION: "Redesign of corporate website",
            PROJECT_BULK_COL_STATUS: "active",
            PROJECT_BULK_COL_BUDGET: 250000,
            PROJECT_BULK_COL_BUDGET_HOURS: 200,
            PROJECT_BULK_COL_END_DATE: "2026-12-31",
            PROJECT_BULK_COL_MANAGER_EMAIL: "pm@example.com",
        },
        {
            PROJECT_BULK_COL_NAME: "Mobile App v2",
            PROJECT_BULK_COL_CLIENT: "TechStart Inc",
            PROJECT_BULK_COL_CODE: "MOBV2",
            PROJECT_BULK_COL_DESCRIPTION: "Native iOS + Android revamp",
            PROJECT_BULK_COL_STATUS: "active",
            PROJECT_BULK_COL_BUDGET: 500000,
            PROJECT_BULK_COL_BUDGET_HOURS: 400,
            PROJECT_BULK_COL_END_DATE: "2026-09-30",
            PROJECT_BULK_COL_MANAGER_EMAIL: "",
        },
    ]
    df = pd.DataFrame(example_rows, columns=PROJECT_BULK_TEMPLATE_COLUMNS)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Projects")
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": "attachment; filename=project_template.xlsx"
        },
    )


@router.post("/bulk-upload")
async def bulk_upload_projects(
    *,
    db: deps.DBDep,
    request: Request,
    file: UploadFile = File(...),
    create_missing_clients: bool = Query(
        False,
        description=(
            "When true, missing client names in the Excel are auto-created "
            "as bare Account rows (name only) and the project linked. "
            "When false (default), missing clients produce a per-row error."
        ),
    ),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    if not _is_super_admin(current_user):
        raise HTTPException(
            status_code=403,
            detail="Only super admin can bulk upload projects",
        )
    if not file.filename or not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(
            status_code=400,
            detail="Please upload an Excel file (.xlsx)",
        )

    import pandas as pd
    from app.models.bd import Account

    contents = await file.read()
    try:
        df = pd.read_excel(io.BytesIO(contents), engine="openpyxl")
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Failed to read Excel file: {e}",
        )

    df.columns = df.columns.str.strip()
    if PROJECT_BULK_COL_NAME not in df.columns:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required column: '{PROJECT_BULK_COL_NAME}'",
        )

    created = 0
    skipped = 0
    clients_created = 0
    errors: List[str] = []
    seen_codes: Dict[str, int] = {}

    def _val(row, col: str) -> Optional[str]:
        if col not in df.columns:
            return None
        raw = row.get(col)
        if raw is None:
            return None
        s = str(raw).strip()
        if not s or s.lower() == "nan":
            return None
        return s

    for idx, row in df.iterrows():
        row_num = idx + 2
        name = _val(row, PROJECT_BULK_COL_NAME)
        if not name:
            errors.append(f"Row {row_num}: Project Name is required")
            continue
        if name.lower() in PROJECT_BULK_EXAMPLE_NAMES:
            skipped += 1
            continue

        try:
            # Resolve client (required)
            client_name_val = _val(row, PROJECT_BULK_COL_CLIENT)
            client_id_val: Optional[int] = None
            if client_name_val:
                acct = (await db.execute(
                    select(Account).where(
                        func.lower(Account.name) == client_name_val.lower()
                    ).limit(1)
                )).scalar_one_or_none()
                if not acct:
                    if create_missing_clients:
                        acct = Account(name=client_name_val)
                        db.add(acct)
                        await db.flush()
                        clients_created += 1
                    else:
                        errors.append(
                            f"Row {row_num} ({name}): client "
                            f"'{client_name_val}' not found — "
                            f"add to Clients first or pass "
                            f"create_missing_clients=true"
                        )
                        continue
                client_id_val = acct.id

            # Resolve code: explicit or generated
            code = (_val(row, PROJECT_BULK_COL_CODE) or "").upper()
            if code:
                if code in seen_codes:
                    errors.append(
                        f"Row {row_num} ({name}): duplicate code "
                        f"'{code}' (also row {seen_codes[code]})"
                    )
                    continue
                exists = (await db.execute(
                    select(Project).where(Project.code == code).limit(1)
                )).scalar_one_or_none()
                if exists:
                    errors.append(
                        f"Row {row_num} ({name}): "
                        f"code '{code}' already exists"
                    )
                    continue
                seen_codes[code] = row_num
            else:
                code = await _generate_project_code(db, name)
                seen_codes[code] = row_num

            status_val = (_val(row, PROJECT_BULK_COL_STATUS) or "active").lower()

            budget_val: Optional[float] = None
            try:
                raw_budget = row.get(PROJECT_BULK_COL_BUDGET)
                if raw_budget is not None and str(raw_budget).strip() not in ("", "nan"):
                    budget_val = float(raw_budget)
            except (TypeError, ValueError):
                errors.append(
                    f"Row {row_num} ({name}): invalid Budget"
                )
                continue

            budget_hours_val: Optional[float] = None
            try:
                raw_bh = row.get(PROJECT_BULK_COL_BUDGET_HOURS)
                if raw_bh is not None and str(raw_bh).strip() not in ("", "nan"):
                    budget_hours_val = float(raw_bh)
            except (TypeError, ValueError):
                errors.append(
                    f"Row {row_num} ({name}): invalid Budget Hours"
                )
                continue

            description_val = _val(row, PROJECT_BULK_COL_DESCRIPTION)

            # Resolve manager email (optional)
            manager_id: Optional[int] = None
            manager_email = _val(row, PROJECT_BULK_COL_MANAGER_EMAIL)
            if manager_email:
                mgr = (await db.execute(
                    select(User).where(
                        func.lower(User.email) == manager_email.lower()
                    ).limit(1)
                )).scalar_one_or_none()
                if not mgr:
                    errors.append(
                        f"Row {row_num} ({name}): manager email "
                        f"'{manager_email}' not found"
                    )
                    continue
                manager_id = mgr.id

            project = Project(
                name=name,
                description=description_val,
                code=code,
                status=status_val,
                client_id=client_id_val,
            )
            db.add(project)
            await db.flush()

            # Creator is always added; manager from Excel takes the
            # "manager" role if provided, else the uploader does.
            db.add(ProjectMember(
                project_id=project.id,
                user_id=manager_id or current_user.id,
                role="manager",
            ))

            if budget_val and budget_val > 0:
                db.add(CostBaseline(
                    project_id=project.id,
                    amount=budget_val,
                    budget_hours=budget_hours_val,
                    description="Initial budget (bulk upload)",
                    is_active=True,
                ))

            log_audit(
                db, current_user.id, "BULK_CREATE", "project",
                str(project.id),
                {"name": name, "code": code, "client_id": client_id_val},
                request,
            )

            created += 1
        except HTTPException:
            raise
        except Exception as e:  # pragma: no cover - per-row guard
            errors.append(f"Row {row_num} ({name}): {e}")
            continue

    await db.commit()
    return {
        "created": created,
        "skipped": skipped,
        "clients_created": clients_created,
        "errors": errors,
    }


# ---------- Bulk import projects WITH tasks (master + sub pattern) ----------
#
# Workbook layout (one row per task, multiple rows per project):
#   SL no | Client Name | Functional Area | Project Code | Project Name |
#   Task Name | Task Value | Sub Task | Project Manager
#
# Behavior per project group (grouped by Project Code):
# - Creates one master Project + N sub-projects (one per task row)
# - Master PM = first active user with role "COO" (fallback CEO → Super Admin)
# - Each sub-project's PM = row's "Project Manager" (must have role "PM")
# - Master gets a Task per row (assignee = delivery PM); sub gets a single Task
# - CostBaselines: master = Σ task values; sub = row's task value
# - Sub Task column is intentionally ignored — PMs add subtasks in the portal

PROJ_TPL_COL_SL = "SL no"
PROJ_TPL_COL_CLIENT = "Client Name"
PROJ_TPL_COL_FA = "Functional Area"
PROJ_TPL_COL_CODE = "Project Code"
PROJ_TPL_COL_NAME = "Project Name"
PROJ_TPL_COL_TASK = "Task Name"
PROJ_TPL_COL_TASK_VALUE = "Task Value"
PROJ_TPL_COL_SUBTASK = "Sub Task"
PROJ_TPL_COL_PM = "Project Manager"
PROJ_TPL_REQUIRED_COLS = [
    PROJ_TPL_COL_CLIENT, PROJ_TPL_COL_FA, PROJ_TPL_COL_CODE,
    PROJ_TPL_COL_NAME, PROJ_TPL_COL_TASK, PROJ_TPL_COL_TASK_VALUE,
    PROJ_TPL_COL_PM,
]
PROJ_TPL_MASTER_PM_ROLES = ("COO", "CEO", "Super Admin")


def _is_admin_coo_or_super(user: User) -> bool:
    if user.is_superuser:
        return True
    role_names = _user_role_names(user)
    return bool(role_names & {"super admin", "admin", "coo"})


async def _resolve_master_pm(db: deps.DBDep) -> Optional[User]:
    """First active COO; fall back to CEO then Super Admin."""
    from app.models.user import Role as _Role
    for role_name in PROJ_TPL_MASTER_PM_ROLES:
        u = (await db.execute(
            select(User)
            .join(User.roles)
            .where(User.is_active.is_(True), _Role.name == role_name)
            .order_by(User.id)
            .limit(1)
        )).scalar_one_or_none()
        if u is not None:
            return u
    return None


async def _resolve_pm_by_name(
    db: deps.DBDep, full_name: str
) -> tuple[Optional[User], Optional[str]]:
    """Return (user, error_msg). User must be active and have role 'PM'."""
    from app.models.user import Role as _Role
    cleaned = " ".join(full_name.split())
    if not cleaned:
        return None, "PM name is blank"
    rows = (await db.execute(
        select(User)
        .join(User.roles)
        .where(
            User.is_active.is_(True),
            _Role.name == "PM",
            func.lower(User.full_name) == cleaned.lower(),
        )
    )).scalars().unique().all()
    if not rows:
        return None, (
            f"No active user with PM role named '{cleaned}'"
        )
    if len(rows) > 1:
        return None, (
            f"Multiple active PMs match name '{cleaned}' "
            f"({len(rows)} candidates) — disambiguate via Admin"
        )
    return rows[0], None


@router.get("/template-with-tasks")
async def download_project_with_tasks_template(
    current_user: User = Depends(deps.get_current_user),
) -> StreamingResponse:
    if not _is_admin_coo_or_super(current_user):
        raise HTTPException(
            status_code=403,
            detail="Only admin, super admin or COO can access this template",
        )

    import pandas as pd
    rows = [
        {
            PROJ_TPL_COL_SL: 1,
            PROJ_TPL_COL_CLIENT: "GMDC",
            PROJ_TPL_COL_FA: "GR",
            PROJ_TPL_COL_CODE: "1234",
            PROJ_TPL_COL_NAME: "Geological Report",
            PROJ_TPL_COL_TASK: "Task 1",
            PROJ_TPL_COL_TASK_VALUE: 250000,
            PROJ_TPL_COL_SUBTASK: "NA",
            PROJ_TPL_COL_PM: "Swastika Kundu",
        },
        {
            PROJ_TPL_COL_SL: 1,
            PROJ_TPL_COL_CLIENT: "GMDC",
            PROJ_TPL_COL_FA: "GR",
            PROJ_TPL_COL_CODE: "1234",
            PROJ_TPL_COL_NAME: "Geological Report",
            PROJ_TPL_COL_TASK: "Task 2",
            PROJ_TPL_COL_TASK_VALUE: 250000,
            PROJ_TPL_COL_SUBTASK: "NA",
            PROJ_TPL_COL_PM: "Sukhen Majumder",
        },
    ]
    df = pd.DataFrame(rows)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Projects")
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition":
                "attachment; filename=project_template_with_tasks.xlsx"
        },
    )


@router.post("/bulk-import-with-tasks")
async def bulk_import_projects_with_tasks(
    *,
    db: deps.DBDep,
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Bulk import legacy projects with tasks.

    Each Project Code becomes one master Project with N sub-projects
    (one per task row). See module-level comment above for details.
    """
    if not _is_admin_coo_or_super(current_user):
        raise HTTPException(
            status_code=403,
            detail="Only admin, super admin or COO can run this import",
        )
    if not file.filename or not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(
            status_code=400, detail="Please upload an Excel file (.xlsx)"
        )

    import pandas as pd
    from app.models.bd import Account
    from app.models.functional_area import FunctionalArea
    from app.models.task import Task

    contents = await file.read()
    try:
        df = pd.read_excel(io.BytesIO(contents), engine="openpyxl")
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Failed to read Excel file: {e}"
        )

    df.columns = df.columns.str.strip()
    missing = [c for c in PROJ_TPL_REQUIRED_COLS if c not in df.columns]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required columns: {', '.join(missing)}",
        )

    master_pm = await _resolve_master_pm(db)
    if master_pm is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "No active COO/CEO/Super Admin user found to assign as "
                "master project PM. Create one before running this import."
            ),
        )

    def _val(row, col: str) -> Optional[str]:
        if col not in df.columns:
            return None
        raw = row.get(col)
        if raw is None:
            return None
        s = str(raw).strip()
        if not s or s.lower() == "nan":
            return None
        return s

    def _num(row, col: str) -> tuple[Optional[float], Optional[str]]:
        raw = row.get(col)
        if raw is None or str(raw).strip() in ("", "nan"):
            return None, None
        try:
            return float(raw), None
        except (TypeError, ValueError):
            return None, f"invalid {col}"

    projects_created = 0
    subprojects_created = 0
    tasks_created = 0
    errors: List[str] = []

    # Group rows by Project Code (preserves first-occurrence ordering)
    group_order: List[str] = []
    groups: Dict[str, List[tuple[int, Any]]] = {}
    for idx, row in df.iterrows():
        code = _val(row, PROJ_TPL_COL_CODE)
        if not code:
            errors.append(f"Row {idx + 2}: Project Code is required")
            continue
        code_key = code.upper()
        if code_key not in groups:
            groups[code_key] = []
            group_order.append(code_key)
        groups[code_key].append((idx + 2, row))

    for code_key in group_order:
        rows = groups[code_key]
        first_row = rows[0][1]
        first_row_num = rows[0][0]
        proj_name = _val(first_row, PROJ_TPL_COL_NAME)
        if not proj_name:
            errors.append(
                f"Row {first_row_num} ({code_key}): Project Name is required"
            )
            continue

        # Use a savepoint per group so a failure rolls back just this group
        sp = await db.begin_nested()
        group_failed = False
        group_errors: List[str] = []
        try:
            # Resolve client (no auto-create)
            client_name = _val(first_row, PROJ_TPL_COL_CLIENT)
            if not client_name:
                group_errors.append(
                    f"Row {first_row_num}: Client Name is required"
                )
                raise ValueError("client required")
            acct = (await db.execute(
                select(Account).where(
                    func.lower(Account.name) == client_name.lower()
                ).limit(1)
            )).scalar_one_or_none()
            if not acct:
                group_errors.append(
                    f"Row {first_row_num} ({code_key}): client "
                    f"'{client_name}' not found — add to Clients first"
                )
                raise ValueError("client missing")

            # Resolve functional area (code first, then name)
            fa_input = _val(first_row, PROJ_TPL_COL_FA)
            if not fa_input:
                group_errors.append(
                    f"Row {first_row_num} ({code_key}): "
                    "Functional Area is required"
                )
                raise ValueError("fa required")
            fa = (await db.execute(
                select(FunctionalArea).where(
                    FunctionalArea.is_active.is_(True),
                    or_(
                        FunctionalArea.code == fa_input.upper(),
                        func.lower(FunctionalArea.name) == fa_input.lower(),
                    ),
                ).limit(1)
            )).scalar_one_or_none()
            if not fa:
                group_errors.append(
                    f"Row {first_row_num} ({code_key}): "
                    f"functional area '{fa_input}' not found"
                )
                raise ValueError("fa missing")

            # Resolve per-row PMs (and capture task values)
            task_rows: List[tuple[int, Any, User, float]] = []
            for row_num, row in rows:
                tname = _val(row, PROJ_TPL_COL_TASK)
                if not tname:
                    group_errors.append(
                        f"Row {row_num}: Task Name is required"
                    )
                    continue
                tvalue, err = _num(row, PROJ_TPL_COL_TASK_VALUE)
                if err:
                    group_errors.append(f"Row {row_num} ({tname}): {err}")
                    continue
                if tvalue is None or tvalue <= 0:
                    group_errors.append(
                        f"Row {row_num} ({tname}): Task Value must be > 0"
                    )
                    continue
                pm_name = _val(row, PROJ_TPL_COL_PM)
                if not pm_name:
                    group_errors.append(
                        f"Row {row_num} ({tname}): "
                        "Project Manager is required"
                    )
                    continue
                pm_user, pm_err = await _resolve_pm_by_name(db, pm_name)
                if pm_err:
                    group_errors.append(
                        f"Row {row_num} ({tname}): {pm_err}"
                    )
                    continue
                task_rows.append((row_num, row, pm_user, tvalue))

            if group_errors:
                raise ValueError("row errors")
            if not task_rows:
                group_errors.append(
                    f"Row {first_row_num} ({code_key}): "
                    "no valid task rows"
                )
                raise ValueError("no tasks")

            # Master project code uniqueness
            exists = (await db.execute(
                select(Project).where(Project.code == code_key).limit(1)
            )).scalar_one_or_none()
            if exists:
                group_errors.append(
                    f"Row {first_row_num} ({code_key}): "
                    f"project code already exists"
                )
                raise ValueError("code exists")

            # Sub-project codes — also need to be unique
            sub_codes: List[str] = []
            for idx, _ in enumerate(task_rows, 1):
                suffix = f"-{idx}"
                sub_code = (code_key[: (20 - len(suffix))] + suffix)[:20]
                sub_codes.append(sub_code)
            for sc in sub_codes:
                existing_sub = (await db.execute(
                    select(Project).where(Project.code == sc).limit(1)
                )).scalar_one_or_none()
                if existing_sub:
                    group_errors.append(
                        f"Row {first_row_num} ({code_key}): "
                        f"sub-project code '{sc}' already exists"
                    )
                    raise ValueError("sub code exists")

            # Create master
            master = Project(
                name=proj_name,
                code=code_key,
                status="active",
                client_id=acct.id,
                functional_area_id=fa.id,
            )
            db.add(master)
            await db.flush()
            db.add(ProjectMember(
                project_id=master.id,
                user_id=master_pm.id,
                role="manager",
            ))
            if current_user.id != master_pm.id:
                db.add(ProjectMember(
                    project_id=master.id,
                    user_id=current_user.id,
                    role="member",
                ))

            total_value = 0.0
            for (row_num, _row, pm_user, tvalue), sub_code in zip(
                task_rows, sub_codes
            ):
                task_title = _val(_row, PROJ_TPL_COL_TASK) or "Task"
                total_value += tvalue

                # Master task
                db.add(Task(
                    title=task_title,
                    project_id=master.id,
                    creator_id=current_user.id,
                    assignee_id=pm_user.id,
                    value=tvalue,
                ))
                tasks_created += 1

                # Sub-project
                sub_name = f"{proj_name} — {task_title}"[:100]
                sub = Project(
                    name=sub_name,
                    code=sub_code,
                    status="active",
                    client_id=acct.id,
                    functional_area_id=fa.id,
                    parent_project_id=master.id,
                )
                db.add(sub)
                await db.flush()
                subprojects_created += 1

                # Sub-project members
                db.add(ProjectMember(
                    project_id=sub.id,
                    user_id=pm_user.id,
                    role="manager",
                ))
                if current_user.id != pm_user.id:
                    db.add(ProjectMember(
                        project_id=sub.id,
                        user_id=current_user.id,
                        role="member",
                    ))
                if master_pm.id not in (pm_user.id, current_user.id):
                    db.add(ProjectMember(
                        project_id=sub.id,
                        user_id=master_pm.id,
                        role="manager",
                    ))

                # Sub-project task (delivery PM's task)
                db.add(Task(
                    title=task_title,
                    project_id=sub.id,
                    creator_id=current_user.id,
                    assignee_id=pm_user.id,
                    value=tvalue,
                ))
                tasks_created += 1

                # Sub-project cost baseline
                db.add(CostBaseline(
                    project_id=sub.id,
                    amount=tvalue,
                    description="Initial budget (bulk-import-with-tasks)",
                    is_active=True,
                ))

            # Master cost baseline = sum
            if total_value > 0:
                db.add(CostBaseline(
                    project_id=master.id,
                    amount=total_value,
                    description="Sum of task values (bulk-import-with-tasks)",
                    is_active=True,
                ))

            log_audit(
                db, current_user.id, "BULK_IMPORT_WITH_TASKS", "project",
                str(master.id),
                {
                    "code": code_key,
                    "name": proj_name,
                    "tasks": len(task_rows),
                    "total_value": total_value,
                },
                request,
            )
            projects_created += 1
        except Exception as e:
            group_failed = True
            await sp.rollback()
            if not group_errors:
                group_errors.append(
                    f"Row {first_row_num} ({code_key}): {e}"
                )
            errors.extend(group_errors)
        else:
            await sp.commit()
        finally:
            if not group_failed and not group_errors:
                pass

    await db.commit()
    return {
        "projects_created": projects_created,
        "subprojects_created": subprojects_created,
        "tasks_created": tasks_created,
        "errors": errors,
    }
