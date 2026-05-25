from collections import defaultdict
from pathlib import Path
from typing import Any, Annotated, List, Optional
from uuid import uuid4
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select, and_, func, or_
from sqlalchemy.orm import selectinload

from app.api import deps
from app.core.config import settings
from app.models.task import (
    Task, Subtask, TaskComment,
    TaskCompletionRequest, TaskCompletionDocument,
)
from app.models.project import Project, ProjectMember
from app.models.timesheet import TimeEntry
from app.models.user import User
from app.schemas.task import (
    TaskRead, TaskDetail, TaskCommentCreate, TaskCommentRead,
    SubtaskRead, TaskCreate, SubtaskCreate,
    TaskCompletionRequestCreate, TaskCompletionReviewAction,
    TaskCompletionRequestRead, TaskTimeSummary,
    TaskCompletionDocumentRead,
)
from app.schemas.project import ProjectWithTasks, ProjectRead

router = APIRouter()

MSG_NOT_AUTHORIZED = "Not authorized"
MSG_NOT_ENOUGH_PERMISSIONS = "Not enough permissions"
MSG_PROJECT_NOT_FOUND = "Project not found"
MSG_TASK_NOT_FOUND = "Task not found"
MSG_SUBTASK_NOT_FOUND = "Subtask not found"
MSG_SUBTASK_PARENT_NOT_FOUND = "Parent subtask not found"
MSG_ASSIGNEE_NOT_FOUND = "Assignee not found"
MSG_SUBTASK_TITLE_REQUIRED = "Subtask title is required"
MSG_INVALID_STATUS = "Invalid status"
MSG_ESTIMATED_HOURS_MIN_0 = "estimated_hours must be >= 0"
MSG_SUBTASK_CHILDREN_EXCEED = "Children subtask hours exceed parent"

MSG_TASK_CREATE_FORBIDDEN = "Not authorized to create tasks in this project"

PROJECT_MANAGER_ROLES = {"owner", "manager"}

ELEVATED_SCOPE_ROLES = {
    "admin",
    "super admin",
    "cto",
    "dop",
    "coo",
    "operations head",
    "ops head",
    "operations",
}


def _is_elevated_scope_user(user: deps.CurrentUser) -> bool:
    roles = getattr(user, "roles", None) or []
    names = {str(getattr(r, "name", "")).strip().lower() for r in roles}
    return bool(names & ELEVATED_SCOPE_ROLES)


async def _has_task_access(
    *,
    db: deps.DBDep,
    task: Task,
    current_user: deps.CurrentUser,
) -> bool:
    if current_user.is_superuser:
        return True

    if _is_elevated_scope_user(current_user):
        return True

    pm_role = (
        await db.execute(
            select(ProjectMember.role).where(
                and_(
                    ProjectMember.project_id == task.project_id,
                    ProjectMember.user_id == current_user.id,
                )
            )
        )
    ).scalar_one_or_none()

    if pm_role is None:
        return False

    if pm_role in PROJECT_MANAGER_ROLES:
        return True

    if task.assignee_id == current_user.id:
        return True

    subtask_assigned = (
        await db.execute(
            select(Subtask.id)
            .where(
                and_(
                    Subtask.task_id == task.id,
                    Subtask.assignee_id == current_user.id,
                )
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    return subtask_assigned is not None


async def _parent_capacity_and_filter(
    db: deps.DBDep,
    *,
    task: Task,
    parent_subtask_id: int | None,
) -> tuple[float | None, Any | None, str | None]:
    if parent_subtask_id is None:
        task_hours = (
            float(task.estimated_hours)
            if task.estimated_hours is not None
            else None
        )
        where = and_(
            Subtask.task_id == task.id,
            Subtask.parent_subtask_id.is_(None),
        )
        return task_hours, where, None

    parent_subtask = await db.get(Subtask, parent_subtask_id)
    if not parent_subtask or parent_subtask.task_id != task.id:
        return None, None, MSG_SUBTASK_PARENT_NOT_FOUND
    parent_hours = (
        float(parent_subtask.estimated_hours)
        if parent_subtask.estimated_hours is not None
        else None
    )
    return parent_hours, Subtask.parent_subtask_id == parent_subtask_id, None


async def _children_hours_exceed_error(
    db: deps.DBDep,
    *,
    subtask_id: int,
    new_parent_hours: float,
) -> str | None:
    child_sum = await db.execute(
        select(func.coalesce(func.sum(Subtask.estimated_hours), 0)).where(
            Subtask.parent_subtask_id == subtask_id
        )
    )
    children_hours = float(child_sum.scalar_one() or 0)
    if children_hours > float(new_parent_hours or 0) + 1e-6:
        return (
            f"{MSG_SUBTASK_CHILDREN_EXCEED}. "
            f"Children total: {children_hours:.2f}h"
        )
    return None


async def _sibling_hours_exceed_error(
    db: deps.DBDep,
    *,
    task: Task,
    parent_subtask_id: int | None,
    new_hours: float,
    exclude_subtask_id: int | None,
) -> str | None:
    parent_hours, where, err = await _parent_capacity_and_filter(
        db,
        task=task,
        parent_subtask_id=parent_subtask_id,
    )
    if err:
        return err
    if parent_hours is None or where is None:
        return None

    if exclude_subtask_id is not None:
        where = and_(where, Subtask.id != exclude_subtask_id)

    existing_sum = await db.execute(
        select(
            func.coalesce(func.sum(Subtask.estimated_hours), 0)
        ).where(where)
    )
    existing_hours = float(existing_sum.scalar_one() or 0)
    if existing_hours + float(new_hours or 0) <= parent_hours + 1e-6:
        return None
    remaining = max(parent_hours - existing_hours, 0)
    return (
        "Subtask hours exceed parent estimated hours. "
        f"Remaining: {remaining:.2f}h"
    )


@router.get("/my-pending-actions-count")
async def get_my_pending_actions_count(
    db: deps.DBDep,
    current_user: deps.CurrentUser,
) -> Any:
    """
    Count of the current user's tasks that have a PM-reviewed completion request
    (rejected or on_hold) with no subsequent pending request — i.e. tasks where
    the PM has responded and the employee needs to take action.
    """
    # Find tasks assigned to this user that have a rejected/on_hold request
    # but no currently pending request
    subq_pending = (
        select(TaskCompletionRequest.task_id)
        .where(TaskCompletionRequest.status == "pending")
    ).scalar_subquery()

    rows = (await db.execute(
        select(func.count(func.distinct(TaskCompletionRequest.task_id)))
        .join(Task, Task.id == TaskCompletionRequest.task_id)
        .where(
            and_(
                Task.assignee_id == current_user.id,
                Task.status != "completed",
                TaskCompletionRequest.submitted_by_id == current_user.id,
                TaskCompletionRequest.status.in_(["rejected", "on_hold"]),
                ~TaskCompletionRequest.task_id.in_(subq_pending),
            )
        )
    )).scalar()
    return {"count": rows or 0}


@router.get("/my-tasks", response_model=List[ProjectWithTasks])
async def get_my_tasks(
    db: deps.DBDep,
    current_user: deps.CurrentUser
) -> Any:
    """
    Get all tasks assigned to the current user, grouped by project.
    """
    query = (
        select(Task)
        .outerjoin(Subtask, Subtask.task_id == Task.id)
        .where(
            or_(
                Task.assignee_id == current_user.id,
                Subtask.assignee_id == current_user.id,
            )
        )
        .options(
            selectinload(Task.subtasks),
            selectinload(Task.project),
        )
        .distinct()
        .order_by(Task.project_id, Task.id)
    )

    result = await db.execute(query)
    tasks = result.scalars().all()
    if not tasks:
        return []

    tasks_by_project_id: dict[int, list[Task]] = defaultdict(list)
    projects_by_id: dict[int, Project] = {}

    for task in tasks:
        if task.project_id is not None:
            tasks_by_project_id[task.project_id].append(task)
        if task.project is not None:
            projects_by_id[task.project.id] = task.project

    # Fetch actual logged hours per task in a single query
    task_ids = [t.id for t in tasks]
    hours_rows = (
        await db.execute(
            select(TimeEntry.task_id, func.sum(TimeEntry.duration_seconds))
            .where(TimeEntry.task_id.in_(task_ids))
            .group_by(TimeEntry.task_id)
        )
    ).all()
    actual_hours_by_task: dict[int, float] = {
        row[0]: round(float(row[1]) / 3600, 2) for row in hours_rows
    }

    response: list[ProjectWithTasks] = []
    for project_id, project_tasks in tasks_by_project_id.items():
        project = projects_by_id.get(project_id)
        if project is None:
            continue

        task_reads = []
        for t in project_tasks:
            t_read = TaskRead.model_validate(t, from_attributes=True)
            t_read.actual_hours = actual_hours_by_task.get(t.id, 0.0)
            task_reads.append(t_read)

        project_base = ProjectRead.model_validate(project, from_attributes=True)
        project_out = ProjectWithTasks(
            **project_base.model_dump(),
            tasks=task_reads,
        )
        response.append(project_out)

    return response


@router.post(
    "/",
    response_model=TaskRead,
    responses={
        403: {"description": MSG_TASK_CREATE_FORBIDDEN},
        404: {"description": "Project/assignee not found"},
    },
)
async def create_task(
    *,
    db: deps.DBDep,
    task_in: TaskCreate,
    current_user: deps.CurrentUser
) -> Any:
    """
    Create a new task in a project.
    """
    # Check if project exists
    project = await db.get(Project, task_in.project_id)
    if not project:
        raise HTTPException(
            status_code=404,
            detail=MSG_PROJECT_NOT_FOUND,
        )
        
    # Check if current user is a member of the project or admin
    pm_query = select(ProjectMember).where(
        and_(
            ProjectMember.project_id == task_in.project_id,
            ProjectMember.user_id == current_user.id
        )
    )
    pm_result = await db.execute(pm_query)
    is_member = pm_result.scalar_one_or_none()
    
    if not is_member and not current_user.is_superuser:
        raise HTTPException(
            status_code=403,
            detail=MSG_TASK_CREATE_FORBIDDEN,
        )

    assignee_id = task_in.assignee_id
    if assignee_id is None and task_in.assignee_email:
        user = (
            await db.execute(
                select(User).where(User.email == task_in.assignee_email)
            )
        ).scalar_one_or_none()
        if not user:
            raise HTTPException(
                status_code=404,
                detail=MSG_ASSIGNEE_NOT_FOUND,
            )
        assignee_id = user.id

    task_data = task_in.model_dump(exclude={"assignee_email"})
    task_data["assignee_id"] = assignee_id

    task = Task(**task_data, creator_id=current_user.id)
    db.add(task)
    await db.flush()
    tid = task.id
    await db.commit()
    
    # Eager load for response
    q = select(Task).where(Task.id == tid).options(
        selectinload(Task.subtasks)
    )
    res = await db.execute(q)
    return res.scalar_one()


@router.get(
    "/project/{project_id}",
    response_model=List[TaskRead],
    responses={
        403: {"description": MSG_NOT_AUTHORIZED},
        404: {"description": MSG_PROJECT_NOT_FOUND},
    },
)
async def list_tasks_by_project(
    project_id: int,
    db: deps.DBDep,
    current_user: deps.CurrentUser,
) -> Any:
    """List tasks for a project (Execution Board).

    Allowed for project members and super admins.
    """
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail=MSG_PROJECT_NOT_FOUND)

    pm_role: str | None = None
    if (
        not current_user.is_superuser
        and not _is_elevated_scope_user(current_user)
    ):
        pm_role = (
            await db.execute(
                select(ProjectMember.role).where(
                    and_(
                        ProjectMember.project_id == project_id,
                        ProjectMember.user_id == current_user.id,
                    )
                )
            )
        ).scalar_one_or_none()

        if pm_role is None:
            raise HTTPException(status_code=403, detail=MSG_NOT_AUTHORIZED)

    query = select(Task).where(Task.project_id == project_id)

    if (
        not current_user.is_superuser
        and pm_role not in PROJECT_MANAGER_ROLES
    ):
        query = (
            query.outerjoin(Subtask, Subtask.task_id == Task.id)
            .where(
                or_(
                    Task.assignee_id == current_user.id,
                    Subtask.assignee_id == current_user.id,
                )
            )
            .distinct()
        )

    query = query.options(selectinload(Task.subtasks)).order_by(Task.id)
    result = await db.execute(query)
    return result.scalars().all()


@router.get(
    "/{task_id}",
    response_model=TaskDetail,
    responses={
        403: {"description": MSG_NOT_ENOUGH_PERMISSIONS},
        404: {"description": MSG_TASK_NOT_FOUND},
    },
)
async def get_task_detail(
    task_id: int,
    db: deps.DBDep,
    current_user: deps.CurrentUser
) -> Any:
    """
    Get detailed task information including comments and subtasks.
    """
    query = select(Task).where(
        Task.id == task_id
    ).options(
        selectinload(Task.subtasks),
        selectinload(Task.comments).selectinload(TaskComment.user),
        selectinload(Task.attachments)
    )
    result = await db.execute(query)
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail=MSG_TASK_NOT_FOUND)

    if not await _has_task_access(
        db=db,
        task=task,
        current_user=current_user,
    ):
        raise HTTPException(
            status_code=403,
            detail=MSG_NOT_ENOUGH_PERMISSIONS,
        )
            
    return task


@router.post(
    "/{task_id}/subtasks",
    response_model=SubtaskRead,
    responses={
        400: {"description": "Validation error"},
        403: {"description": MSG_NOT_ENOUGH_PERMISSIONS},
        404: {"description": "Task/assignee not found"},
    },
)
async def create_subtask(
    task_id: int,
    subtask_in: SubtaskCreate,
    db: deps.DBDep,
    current_user: deps.CurrentUser,
) -> Any:
    """Create a new subtask (deliverable item) inside a task.

    Allowed for the task assignee, task creator, project members (PMs), and
    super admins.
    """
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail=MSG_TASK_NOT_FOUND)

    if not await _has_task_access(
        db=db,
        task=task,
        current_user=current_user,
    ):
        raise HTTPException(
            status_code=403,
            detail=MSG_NOT_ENOUGH_PERMISSIONS,
        )

    title = (subtask_in.title or "").strip()
    if not title:
        raise HTTPException(
            status_code=400,
            detail=MSG_SUBTASK_TITLE_REQUIRED,
        )

    assignee_id = subtask_in.assignee_id
    if assignee_id is None and subtask_in.assignee_email:
        user = (
            await db.execute(
                select(User).where(User.email == subtask_in.assignee_email)
            )
        ).scalar_one_or_none()
        if not user:
            raise HTTPException(
                status_code=404,
                detail=MSG_ASSIGNEE_NOT_FOUND,
            )
        assignee_id = user.id

    parent_subtask_id = subtask_in.parent_subtask_id
    new_hours = float(subtask_in.estimated_hours or 0)

    sib_err = await _sibling_hours_exceed_error(
        db,
        task=task,
        parent_subtask_id=parent_subtask_id,
        new_hours=new_hours,
        exclude_subtask_id=None,
    )
    if sib_err == MSG_SUBTASK_PARENT_NOT_FOUND:
        raise HTTPException(status_code=404, detail=sib_err)
    if sib_err:
        raise HTTPException(status_code=400, detail=sib_err)

    subtask = Subtask(
        title=title,
        is_completed=subtask_in.is_completed,
        estimated_hours=subtask_in.estimated_hours,
        task_id=task_id,
        parent_subtask_id=parent_subtask_id,
        assignee_id=assignee_id,
    )
    db.add(subtask)
    await db.commit()
    await db.refresh(subtask)
    return subtask


@router.patch(
    "/{task_id}/status",
    response_model=TaskRead,
    responses={
        400: {"description": MSG_INVALID_STATUS},
        403: {"description": MSG_NOT_AUTHORIZED},
        404: {"description": MSG_TASK_NOT_FOUND},
    },
)
async def update_task_status(
    task_id: int,
    status_in: str,
    db: deps.DBDep,
    current_user: deps.CurrentUser
) -> Any:
    """
    Update task status.
    """
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail=MSG_TASK_NOT_FOUND)
        
    if (
        task.assignee_id != current_user.id
        and task.creator_id != current_user.id
    ):
        raise HTTPException(status_code=403, detail=MSG_NOT_AUTHORIZED)
        
    if status_in not in ["todo", "in_progress", "review", "completed"]:
        raise HTTPException(status_code=400, detail=MSG_INVALID_STATUS)
        
    task.status = status_in
    await db.commit()
    # Eager-load relationships required by TaskRead to avoid async lazy-loading
    # during response serialization.
    q = (
        select(Task)
        .where(Task.id == task_id)
        .options(selectinload(Task.subtasks))
    )
    res = await db.execute(q)
    return res.scalar_one()


@router.post(
    "/{task_id}/comments",
    response_model=TaskCommentRead,
    responses={
        404: {"description": MSG_TASK_NOT_FOUND},
    },
)
async def add_task_comment(
    task_id: int,
    comment_in: TaskCommentCreate,
    db: deps.DBDep,
    current_user: deps.CurrentUser
) -> Any:
    """
    Add a comment to a task.
    """
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail=MSG_TASK_NOT_FOUND)
        
    comment = TaskComment(
        content=comment_in.content,
        task_id=task_id,
        subtask_id=comment_in.subtask_id,
        user_id=current_user.id
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)
    return comment


class SubtaskUpdate(BaseModel):
    title: str | None = None
    is_completed: bool | None = None
    estimated_hours: float | None = None
    assignee_id: int | None = None
    assignee_email: str | None = None


def _clean_title(title: str | None) -> tuple[str | None, str | None]:
    if title is None:
        return None, None
    cleaned = title.strip()
    if not cleaned:
        return None, MSG_SUBTASK_TITLE_REQUIRED
    return cleaned, None


async def _resolve_assignee_id(
    db: deps.DBDep,
    *,
    assignee_id: int | None,
    assignee_email: str | None,
) -> tuple[int | None, str | None]:
    if assignee_id is not None:
        return assignee_id, None
    if not assignee_email:
        return None, None
    user = (
        await db.execute(select(User).where(User.email == assignee_email))
    ).scalar_one_or_none()
    if not user:
        return None, MSG_ASSIGNEE_NOT_FOUND
    return int(user.id), None


async def _subtask_hours_error(
    db: deps.DBDep,
    *,
    task: Task,
    subtask: Subtask,
    new_hours: float,
) -> str | None:
    sib_err = await _sibling_hours_exceed_error(
        db,
        task=task,
        parent_subtask_id=subtask.parent_subtask_id,
        new_hours=new_hours,
        exclude_subtask_id=subtask.id,
    )
    if sib_err:
        return sib_err

    child_err = await _children_hours_exceed_error(
        db,
        subtask_id=subtask.id,
        new_parent_hours=float(new_hours or 0),
    )
    if child_err:
        return child_err
    return None


@router.patch(
    "/subtasks/{subtask_id}",
    response_model=SubtaskRead,
    responses={
        400: {"description": "Validation error"},
        403: {"description": MSG_NOT_ENOUGH_PERMISSIONS},
        404: {"description": "Task/subtask/assignee not found"},
    },
)
async def toggle_subtask(
    subtask_id: int,
    toggle: SubtaskUpdate,
    db: deps.DBDep,
    current_user: deps.CurrentUser
) -> Any:
    """Update subtask fields (completion/title/hours/assignee)."""
    subtask = await db.get(Subtask, subtask_id)
    if not subtask:
        raise HTTPException(status_code=404, detail=MSG_SUBTASK_NOT_FOUND)

    task = await db.get(Task, subtask.task_id)
    if not task:
        raise HTTPException(status_code=404, detail=MSG_TASK_NOT_FOUND)

    if not await _has_task_access(
        db=db,
        task=task,
        current_user=current_user,
    ):
        raise HTTPException(status_code=403, detail=MSG_NOT_ENOUGH_PERMISSIONS)

    cleaned_title, title_err = _clean_title(toggle.title)
    if title_err:
        raise HTTPException(status_code=400, detail=title_err)
    if cleaned_title is not None:
        subtask.title = cleaned_title

    if toggle.is_completed is not None:
        subtask.is_completed = toggle.is_completed

    assignee_id, assignee_err = await _resolve_assignee_id(
        db,
        assignee_id=toggle.assignee_id,
        assignee_email=toggle.assignee_email,
    )
    if assignee_err:
        raise HTTPException(status_code=404, detail=assignee_err)
    if toggle.assignee_id is not None or toggle.assignee_email is not None:
        subtask.assignee_id = assignee_id

    if toggle.estimated_hours is not None:
        if toggle.estimated_hours < 0:
            raise HTTPException(
                status_code=400,
                detail=MSG_ESTIMATED_HOURS_MIN_0,
            )
        hours_err = await _subtask_hours_error(
            db,
            task=task,
            subtask=subtask,
            new_hours=float(toggle.estimated_hours or 0),
        )
        if hours_err:
            raise HTTPException(status_code=400, detail=hours_err)
        subtask.estimated_hours = toggle.estimated_hours
    await db.commit()
    await db.refresh(subtask)
    return subtask


# ── Task Completion Workflow ─────────────────────────────────────────────────

def _safe_filename_completion(name: str) -> str:
    return "".join(c for c in name if c.isalnum() or c in "._- ")[:200] or "file"


def _completion_docs_dir() -> Path:
    return Path(settings.TASK_COMPLETION_DOCS_DIR)


def _req_to_read(req: TaskCompletionRequest) -> TaskCompletionRequestRead:
    subtask = getattr(req, "subtask", None)
    return TaskCompletionRequestRead(
        id=int(req.id),
        task_id=int(req.task_id),
        subtask_id=int(req.subtask_id) if req.subtask_id else None,
        subtask_title=getattr(subtask, "title", None),
        submitted_by_id=int(req.submitted_by_id),
        submitted_by_name=getattr(req.submitted_by, "full_name", None),
        status=str(req.status),
        notes=req.notes,
        reviewer_notes=req.reviewer_notes,
        reviewed_by_id=int(req.reviewed_by_id) if req.reviewed_by_id else None,
        reviewed_by_name=getattr(req.reviewed_by, "full_name", None),
        reviewed_at=req.reviewed_at,
        created_at=req.created_at,
        updated_at=req.updated_at,
        documents=[
            TaskCompletionDocumentRead(
                id=int(d.id),
                request_id=int(d.request_id),
                file_name=d.file_name,
                file_size=d.file_size,
                mime_type=d.mime_type,
                uploaded_by_id=int(d.uploaded_by_id),
                uploaded_at=d.uploaded_at,
            )
            for d in (req.documents or [])
        ],
    )


async def _load_completion_request(
    db: deps.DBDep, request_id: int
) -> TaskCompletionRequest:
    q = (
        select(TaskCompletionRequest)
        .where(TaskCompletionRequest.id == request_id)
        .options(
            selectinload(TaskCompletionRequest.submitted_by),
            selectinload(TaskCompletionRequest.reviewed_by),
            selectinload(TaskCompletionRequest.documents),
            selectinload(TaskCompletionRequest.subtask),
        )
    )
    row = (await db.execute(q)).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Completion request not found")
    return row


@router.post(
    "/{task_id}/completion-requests",
    response_model=TaskCompletionRequestRead,
)
async def submit_completion_request(
    task_id: int,
    body: TaskCompletionRequestCreate,
    db: deps.DBDep,
    current_user: deps.CurrentUser,
) -> Any:
    """Employee submits a task-completion request to the PM."""
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail=MSG_TASK_NOT_FOUND)

    if task.status == "completed":
        raise HTTPException(status_code=409, detail="Task is already completed")

    # Check if this user already has a pending request for this specific work item
    # (main task when subtask_id is None, or the specific subtask)
    pending = (
        await db.execute(
            select(TaskCompletionRequest).where(
                and_(
                    TaskCompletionRequest.task_id == task_id,
                    TaskCompletionRequest.submitted_by_id == current_user.id,
                    TaskCompletionRequest.status == "pending",
                    TaskCompletionRequest.subtask_id == body.subtask_id,
                )
            )
        )
    ).scalar_one_or_none()
    if pending:
        item_label = "subtask" if body.subtask_id else "task"
        raise HTTPException(status_code=409, detail=f"You already have a pending approval request for this {item_label}")

    if body.subtask_id is not None:
        subtask = await db.get(Subtask, body.subtask_id)
        if not subtask or subtask.task_id != task_id:
            raise HTTPException(status_code=400, detail="Subtask does not belong to this task")

    req = TaskCompletionRequest(
        task_id=task_id,
        subtask_id=body.subtask_id,
        submitted_by_id=int(current_user.id),
        status="pending",
        notes=body.notes,
    )
    db.add(req)
    await db.commit()
    return _req_to_read(await _load_completion_request(db, int(req.id)))


@router.get(
    "/{task_id}/completion-requests",
    response_model=List[TaskCompletionRequestRead],
)
async def list_completion_requests(
    task_id: int,
    db: deps.DBDep,
    current_user: deps.CurrentUser,
) -> Any:
    """List all completion requests for a task (full history)."""
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail=MSG_TASK_NOT_FOUND)

    if not await _has_task_access(db=db, task=task, current_user=current_user):
        raise HTTPException(status_code=403, detail=MSG_NOT_AUTHORIZED)

    q = (
        select(TaskCompletionRequest)
        .where(TaskCompletionRequest.task_id == task_id)
        .options(
            selectinload(TaskCompletionRequest.submitted_by),
            selectinload(TaskCompletionRequest.reviewed_by),
            selectinload(TaskCompletionRequest.documents),
            selectinload(TaskCompletionRequest.subtask),
        )
        .order_by(TaskCompletionRequest.created_at)
    )
    rows = (await db.execute(q)).scalars().all()
    return [_req_to_read(r) for r in rows]


@router.post(
    "/{task_id}/completion-requests/{request_id}/review",
    response_model=TaskCompletionRequestRead,
)
async def review_completion_request(
    task_id: int,
    request_id: int,
    body: TaskCompletionReviewAction,
    db: deps.DBDep,
    current_user: deps.CurrentUser,
) -> Any:
    """PM approves, rejects, or puts on hold a completion request."""
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail=MSG_TASK_NOT_FOUND)

    pm_role = (
        await db.execute(
            select(ProjectMember.role).where(
                and_(
                    ProjectMember.project_id == task.project_id,
                    ProjectMember.user_id == current_user.id,
                )
            )
        )
    ).scalar_one_or_none()

    if pm_role not in PROJECT_MANAGER_ROLES and not current_user.is_superuser and not _is_elevated_scope_user(current_user):
        raise HTTPException(status_code=403, detail="Only a project manager can review completion requests")

    req = await _load_completion_request(db, request_id)
    if req.task_id != task_id:
        raise HTTPException(status_code=404, detail="Completion request not found")

    if req.status != "pending":
        raise HTTPException(status_code=409, detail=f"Request is already {req.status}")

    status_map = {"approve": "approved", "reject": "rejected", "on_hold": "on_hold"}
    req.status = status_map[body.action]
    req.reviewer_notes = body.reviewer_notes
    req.reviewed_by_id = int(current_user.id)
    req.reviewed_at = datetime.now(timezone.utc)

    if body.action == "approve":
        task.status = "completed"

    await db.commit()
    return _req_to_read(await _load_completion_request(db, request_id))


@router.post(
    "/{task_id}/completion-requests/{request_id}/documents",
    response_model=TaskCompletionDocumentRead,
)
async def upload_completion_document(
    task_id: int,
    request_id: int,
    file: Annotated[UploadFile, File(...)],
    db: deps.DBDep,
    current_user: deps.CurrentUser,
) -> Any:
    """Attach an evidence document to a completion request."""
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail=MSG_TASK_NOT_FOUND)

    req = await _load_completion_request(db, request_id)
    if req.task_id != task_id:
        raise HTTPException(status_code=404, detail="Completion request not found")

    if req.submitted_by_id != current_user.id and not _is_elevated_scope_user(current_user):
        raise HTTPException(status_code=403, detail=MSG_NOT_AUTHORIZED)

    content = await file.read()
    if len(content) > settings.TASK_COMPLETION_DOC_MAX_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 25 MB)")

    dest_dir = _completion_docs_dir() / str(task_id) / str(request_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    filename = _safe_filename_completion(file.filename or "file")
    stored_name = f"{uuid4().hex}_{filename}"
    dest = dest_dir / stored_name
    dest.write_bytes(content)

    doc = TaskCompletionDocument(
        request_id=request_id,
        file_name=file.filename or filename,
        file_path=str(dest.relative_to(_completion_docs_dir())),
        file_size=len(content),
        mime_type=file.content_type,
        uploaded_by_id=int(current_user.id),
        uploaded_at=datetime.now(timezone.utc),
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return TaskCompletionDocumentRead.model_validate(doc, from_attributes=True)


@router.get(
    "/{task_id}/time-summary",
    response_model=TaskTimeSummary,
)
async def get_task_time_summary(
    task_id: int,
    db: deps.DBDep,
    current_user: deps.CurrentUser,
    subtask_id: Optional[int] = None,
) -> Any:
    """Actual logged hours vs estimated, plus full completion request history.
    Pass subtask_id to narrow the time total to a specific subtask."""
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail=MSG_TASK_NOT_FOUND)

    if not await _has_task_access(db=db, task=task, current_user=current_user):
        raise HTTPException(status_code=403, detail=MSG_NOT_AUTHORIZED)

    time_filter = [TimeEntry.task_id == task_id]
    if subtask_id is not None:
        time_filter.append(TimeEntry.subtask_id == subtask_id)

    total_seconds = (
        await db.execute(
            select(func.coalesce(func.sum(TimeEntry.duration_seconds), 0)).where(
                *time_filter
            )
        )
    ).scalar_one()
    actual_hours = round(float(total_seconds) / 3600, 2)

    req_rows = (
        await db.execute(
            select(TaskCompletionRequest)
            .where(TaskCompletionRequest.task_id == task_id)
            .options(
                selectinload(TaskCompletionRequest.submitted_by),
                selectinload(TaskCompletionRequest.reviewed_by),
                selectinload(TaskCompletionRequest.documents),
                selectinload(TaskCompletionRequest.subtask),
            )
            .order_by(TaskCompletionRequest.created_at)
        )
    ).scalars().all()

    # If a subtask_id was given, use that subtask's estimated_hours instead
    estimated: Optional[float] = None
    if subtask_id is not None:
        subtask = await db.get(Subtask, subtask_id)
        if subtask and subtask.estimated_hours is not None:
            estimated = float(subtask.estimated_hours)
    elif task.estimated_hours is not None:
        estimated = float(task.estimated_hours)

    return TaskTimeSummary(
        task_id=task_id,
        estimated_hours=estimated,
        actual_hours=actual_hours,
        requests=[_req_to_read(r) for r in req_rows],
    )
