from datetime import datetime, timezone, timedelta, date
from typing import Any, Optional, Annotated, Dict, Set, Tuple
from fastapi import APIRouter, HTTPException, Request, Depends, status
from sqlalchemy import select, and_, func, or_
from app.api import deps
from app.models.timesheet import (
    TimeEntry, TimerSession, TimerStatus as DBTimerStatus, TimeEntrySource
)
from app.models.user import User
from app.models.audit import AuditLog
from app.models.project import Project
from app.models.project import ProjectMember
from app.models.task import Task, Subtask
from app.schemas.timesheet import (
    TimerStart, TimerStatus, TimerSessionRead, TimeEntryRead,
    TimeEntryManual, TimesheetRead, DailyAggregation,
    MyWorkUtilizationResponse, MyWorkUtilizationItem,
    ProjectUtilizationResponse, TaskUtilizationRead, SubtaskUtilizationRead,
)

router = APIRouter()

MAX_DAILY_SECONDS = 9 * 3600
PERM_TIME_WRITE = "employee time write"
PERM_TIME_READ = "employee time read"

PROJECT_MANAGER_ROLES = {"owner", "manager"}

MSG_PROJECT_NOT_FOUND = "Project not found"
MSG_TASK_NOT_FOUND = "Task not found"
MSG_SUBTASK_NOT_FOUND = "Subtask not found"
MSG_SUBTASK_TASK_MISMATCH = "Subtask does not belong to the task."
MSG_TASK_PROJECT_MISMATCH = "Task does not belong to the project"
MSG_WORK_NOT_ASSIGNED = "This task/subtask is not assigned to you."
MSG_NO_RUNNING_TIMER = "No running timer found"
MSG_NO_PAUSED_TIMER = "No paused timer found"
MSG_NO_ACTIVE_TIMER = "No active timer found"
MSG_INVALID_TIME_RANGE = "End time must be after start time"

TimeWriteUser = Annotated[
    User, Depends(deps.check_permissions([PERM_TIME_WRITE]))
]
TimeReadUser = Annotated[
    User, Depends(deps.check_permissions([PERM_TIME_READ]))
]


def error_detail(
    code: str, message: str, details: Optional[dict] = None
) -> dict:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
        }
    }


async def require_project_manager(
    db: deps.DBDep, *, project_id: int, current_user: User
) -> None:
    if current_user.is_superuser:
        return
    query = (
        select(ProjectMember)
        .where(
            and_(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == current_user.id,
            )
        )
        .limit(1)
    )
    result = await db.execute(query)
    membership = result.scalars().first()
    if not membership or membership.role not in PROJECT_MANAGER_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=error_detail(
                "PROJECT_FORBIDDEN",
                "You do not have access to project analytics.",
            ),
        )


def get_range_window(range: str) -> Tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    if range == "weekly":
        start_dt = (now - timedelta(days=now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        end_dt = start_dt + timedelta(days=7)
        return start_dt, end_dt

    start_dt = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start_dt.month == 12:
        end_dt = start_dt.replace(year=start_dt.year + 1, month=1)
    else:
        end_dt = start_dt.replace(month=start_dt.month + 1)
    return start_dt, end_dt


async def get_user_name_map(
    db: deps.DBDep, user_ids: Set[int]
) -> Dict[int, str]:
    if not user_ids:
        return {}
    users_res = await db.execute(select(User).where(User.id.in_(user_ids)))
    return {
        u.id: (u.full_name or u.email) for u in users_res.scalars().all()
    }


async def get_project_used_seconds_map(
    db: deps.DBDep,
    *,
    project_id: int,
    start_dt: datetime,
    end_dt: datetime,
) -> Dict[Tuple[Optional[int], Optional[int]], int]:
    used_q = (
        select(
            TimeEntry.task_id,
            TimeEntry.subtask_id,
            func.sum(TimeEntry.duration_seconds),
        )
        .where(
            and_(
                TimeEntry.project_id == project_id,
                TimeEntry.start_at >= start_dt,
                TimeEntry.start_at < end_dt,
                or_(
                    TimeEntry.task_id.is_not(None),
                    TimeEntry.subtask_id.is_not(None),
                ),
            )
        )
        .group_by(TimeEntry.task_id, TimeEntry.subtask_id)
    )
    used_res = await db.execute(used_q)
    return {(t, s): int(total or 0) for (t, s, total) in used_res.all()}


async def resolve_work_item(
    db: deps.DBDep,
    *,
    project_id: int,
    task_id: Optional[int],
    subtask_id: Optional[int],
) -> Tuple[Task, Optional[Subtask]]:
    if task_id is None and subtask_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail(
                "WORK_ITEM_REQUIRED",
                "Provide task_id or subtask_id.",
            ),
        )

    task: Optional[Task] = None
    subtask: Optional[Subtask] = None

    if subtask_id is not None:
        subtask = await db.get(Subtask, subtask_id)
        if not subtask:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_detail(
                    "SUBTASK_NOT_FOUND", MSG_SUBTASK_NOT_FOUND
                ),
            )
        task = await db.get(Task, subtask.task_id)
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_detail("TASK_NOT_FOUND", MSG_TASK_NOT_FOUND),
            )

    if task_id is not None:
        task = await db.get(Task, task_id)
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_detail("TASK_NOT_FOUND", MSG_TASK_NOT_FOUND),
            )
        if subtask is not None and subtask.task_id != task.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_detail(
                    "SUBTASK_TASK_MISMATCH",
                    MSG_SUBTASK_TASK_MISMATCH,
                ),
            )

    if task is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail(
                "WORK_ITEM_REQUIRED",
                "Provide task_id or subtask_id.",
            ),
        )

    if task.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail(
                "TASK_PROJECT_MISMATCH",
                MSG_TASK_PROJECT_MISMATCH,
            ),
        )

    return task, subtask


def require_assigned_to_user(
    *,
    user_id: int,
    task: Task,
    subtask: Optional[Subtask],
) -> None:
    assigned_user_id: Optional[int] = None
    if subtask is not None and subtask.assignee_id is not None:
        assigned_user_id = subtask.assignee_id
    elif task.assignee_id is not None:
        assigned_user_id = task.assignee_id

    if assigned_user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=error_detail(
                "WORK_NOT_ASSIGNED",
                MSG_WORK_NOT_ASSIGNED,
                {
                    "task_id": task.id,
                    "subtask_id": subtask.id if subtask else None,
                },
            ),
        )


async def fetch_time_entries(
    db: deps.DBDep,
    *,
    user_id: int,
    start_dt: datetime,
    end_dt: datetime,
) -> list[TimeEntry]:
    query = (
        select(TimeEntry)
        .where(
            and_(
                TimeEntry.user_id == user_id,
                TimeEntry.start_at >= start_dt,
                TimeEntry.start_at < end_dt,
            )
        )
        .order_by(TimeEntry.start_at.asc())
    )
    result = await db.execute(query)
    return list(result.scalars().all())


def init_daily_map(
    *, start_dt: datetime, end_dt: datetime
) -> dict[date, dict[str, Any]]:
    daily_map: dict[date, dict[str, Any]] = {}
    curr = start_dt
    while curr < end_dt:
        daily_map[curr.date()] = {"total": 0, "entries": []}
        curr += timedelta(days=1)
    return daily_map


def accumulate_timesheet_entries(
    *,
    entries: list[TimeEntry],
    daily_map: dict[date, dict[str, Any]],
) -> tuple[int, dict[int, dict[str, Any]]]:
    project_totals: dict[int, dict[str, Any]] = {}
    total_seconds = 0

    for entry in entries:
        total_seconds += entry.duration_seconds
        day_date = entry.start_at.date()
        if day_date in daily_map:
            daily_map[day_date]["total"] += entry.duration_seconds
            daily_map[day_date]["entries"].append(entry)

        pid = entry.project_id
        if pid not in project_totals:
            project_totals[pid] = {
                "project_id": pid,
                "project_name": f"Project {pid}",
                "total_seconds": 0,
            }
        project_totals[pid]["total_seconds"] += entry.duration_seconds

    return total_seconds, project_totals


async def enrich_timesheet_project_names(
    db: deps.DBDep,
    *,
    project_totals: dict[int, dict[str, Any]],
    daily_map: dict[date, dict[str, Any]],
) -> None:
    if not project_totals:
        return

    p_query = select(Project).where(Project.id.in_(project_totals.keys()))
    p_res = await db.execute(p_query)
    p_map = {p.id: p.name for p in p_res.scalars().all()}
    for pid, name in p_map.items():
        project_totals[pid]["project_name"] = name

    for daily_info in daily_map.values():
        for entry in daily_info["entries"]:
            setattr(
                entry,
                "project_name",
                p_map.get(entry.project_id, f"Project {entry.project_id}"),
            )


def build_daily_aggregations(
    *, daily_map: dict[date, dict[str, Any]]
) -> list[DailyAggregation]:
    return [
        DailyAggregation(
            day=day_key,
            total_seconds=int(data["total"]),
            entries=data["entries"],
        )
        for day_key, data in sorted(daily_map.items())
    ]


async def build_my_timesheet_response(
    db: deps.DBDep,
    *,
    user_id: int,
    range: str,
) -> TimesheetRead:
    start_dt, end_dt = get_range_window(range)
    entries = await fetch_time_entries(
        db,
        user_id=user_id,
        start_dt=start_dt,
        end_dt=end_dt,
    )
    daily_map = init_daily_map(start_dt=start_dt, end_dt=end_dt)
    total_seconds, project_totals = accumulate_timesheet_entries(
        entries=entries,
        daily_map=daily_map,
    )
    await enrich_timesheet_project_names(
        db,
        project_totals=project_totals,
        daily_map=daily_map,
    )
    daily_data = build_daily_aggregations(daily_map=daily_map)
    return TimesheetRead(
        start_date=start_dt.date(),
        end_date=(end_dt - timedelta(days=1)).date(),
        total_seconds=total_seconds,
        projects=list(project_totals.values()),
        daily_data=daily_data,
    )


async def get_user_used_seconds_map(
    db: deps.DBDep,
    *,
    user_id: int,
    start_dt: datetime,
    end_dt: datetime,
) -> Dict[Tuple[Optional[int], Optional[int]], int]:
    agg_q = (
        select(
            TimeEntry.task_id,
            TimeEntry.subtask_id,
            func.sum(TimeEntry.duration_seconds),
        )
        .where(
            and_(
                TimeEntry.user_id == user_id,
                TimeEntry.start_at >= start_dt,
                TimeEntry.start_at < end_dt,
                or_(
                    TimeEntry.task_id.is_not(None),
                    TimeEntry.subtask_id.is_not(None),
                ),
            )
        )
        .group_by(TimeEntry.task_id, TimeEntry.subtask_id)
    )
    agg_res = await db.execute(agg_q)
    return {(t, s): int(total or 0) for (t, s, total) in agg_res.all()}


async def get_project_name_map(
    db: deps.DBDep,
    *,
    project_ids: Set[int],
) -> Dict[int, str]:
    if not project_ids:
        return {}
    proj_res = await db.execute(
        select(Project).where(Project.id.in_(project_ids))
    )
    return {p.id: p.name for p in proj_res.scalars().all()}


async def get_tasks_by_ids(
    db: deps.DBDep,
    *,
    task_ids: Set[int],
) -> Dict[int, Task]:
    if not task_ids:
        return {}
    res = await db.execute(select(Task).where(Task.id.in_(task_ids)))
    tasks = res.scalars().all()
    return {t.id: t for t in tasks}


def build_my_utilization_items(
    *,
    assigned_tasks: list[Task],
    assigned_subtasks: list[Subtask],
    subtask_parent_task_map: Dict[int, Task],
    project_name_map: Dict[int, str],
    used_map: Dict[Tuple[Optional[int], Optional[int]], int],
) -> tuple[list[MyWorkUtilizationItem], int]:
    items: list[MyWorkUtilizationItem] = []
    total_used_seconds = 0

    for task in assigned_tasks:
        used_seconds = used_map.get((task.id, None), 0)
        total_used_seconds += used_seconds
        items.append(
            MyWorkUtilizationItem(
                project_id=task.project_id,
                project_name=project_name_map.get(
                    task.project_id, f"Project {task.project_id}"
                ),
                task_id=task.id,
                task_title=task.title,
                subtask_id=None,
                subtask_title=None,
                estimated_hours=(
                    float(task.estimated_hours)
                    if task.estimated_hours is not None
                    else None
                ),
                used_seconds=used_seconds,
                used_hours=round(used_seconds / 3600, 4),
            )
        )

    for subtask in assigned_subtasks:
        parent = subtask_parent_task_map.get(subtask.task_id)
        if not parent:
            continue

        used_seconds = used_map.get((parent.id, subtask.id), 0)
        total_used_seconds += used_seconds
        items.append(
            MyWorkUtilizationItem(
                project_id=parent.project_id,
                project_name=project_name_map.get(
                    parent.project_id, f"Project {parent.project_id}"
                ),
                task_id=parent.id,
                task_title=parent.title,
                subtask_id=subtask.id,
                subtask_title=subtask.title,
                estimated_hours=(
                    float(subtask.estimated_hours)
                    if subtask.estimated_hours is not None
                    else None
                ),
                used_seconds=used_seconds,
                used_hours=round(used_seconds / 3600, 4),
            )
        )

    items.sort(key=lambda i: (i.project_id, i.task_id, i.subtask_id or 0))
    return items, total_used_seconds


async def build_my_work_utilization_response(
    db: deps.DBDep,
    *,
    user_id: int,
    range: str,
) -> MyWorkUtilizationResponse:
    start_dt, end_dt = get_range_window(range)

    task_q = select(Task).where(Task.assignee_id == user_id)
    subtask_q = select(Subtask).where(Subtask.assignee_id == user_id)
    task_res = await db.execute(task_q)
    subtask_res = await db.execute(subtask_q)
    assigned_tasks = list(task_res.scalars().all())
    assigned_subtasks = list(subtask_res.scalars().all())

    used_map = await get_user_used_seconds_map(
        db,
        user_id=user_id,
        start_dt=start_dt,
        end_dt=end_dt,
    )

    st_task_ids: Set[int] = {st.task_id for st in assigned_subtasks}
    subtask_parent_task_map = await get_tasks_by_ids(db, task_ids=st_task_ids)

    project_ids: Set[int] = {t.project_id for t in assigned_tasks}
    project_ids |= {t.project_id for t in subtask_parent_task_map.values()}
    project_name_map = await get_project_name_map(db, project_ids=project_ids)

    items, total_used_seconds = build_my_utilization_items(
        assigned_tasks=assigned_tasks,
        assigned_subtasks=assigned_subtasks,
        subtask_parent_task_map=subtask_parent_task_map,
        project_name_map=project_name_map,
        used_map=used_map,
    )
    return MyWorkUtilizationResponse(
        start_date=start_dt.date(),
        end_date=(end_dt - timedelta(days=1)).date(),
        total_used_seconds=total_used_seconds,
        items=items,
    )


async def fetch_project_tasks_and_subtasks(
    db: deps.DBDep, *, project_id: int
) -> tuple[list[Task], list[Subtask]]:
    tasks_res = await db.execute(
        select(Task).where(Task.project_id == project_id)
    )
    tasks = list(tasks_res.scalars().all())
    task_ids = [t.id for t in tasks]
    if not task_ids:
        return tasks, []
    subtasks_res = await db.execute(
        select(Subtask).where(Subtask.task_id.in_(task_ids))
    )
    return tasks, list(subtasks_res.scalars().all())


def group_subtasks_by_task_id(
    subtasks: list[Subtask],
) -> Dict[int, list[Subtask]]:
    grouped: Dict[int, list[Subtask]] = {}
    for st in subtasks:
        grouped.setdefault(st.task_id, []).append(st)
    for st_list in grouped.values():
        st_list.sort(key=lambda s: s.id)
    return grouped


def build_task_utilization(
    *,
    task: Task,
    subtasks: list[Subtask],
    used_map: Dict[Tuple[Optional[int], Optional[int]], int],
    user_map: Dict[int, str],
) -> tuple[TaskUtilizationRead, float, int]:
    used_task_seconds = used_map.get((task.id, None), 0)
    used_subtask_seconds = 0
    st_reads: list[SubtaskUtilizationRead] = []

    for st in subtasks:
        st_used = used_map.get((task.id, st.id), 0)
        used_subtask_seconds += st_used
        # For utilization preview, only include top-level subtasks to avoid
        # showing parent+child items in a flat list. Totals still include all.
        if st.parent_subtask_id is not None:
            continue

        st_reads.append(
            SubtaskUtilizationRead(
                id=st.id,
                title=st.title,
                estimated_hours=(
                    float(st.estimated_hours)
                    if st.estimated_hours is not None
                    else None
                ),
                assignee_id=st.assignee_id,
                assignee_name=(
                    user_map.get(st.assignee_id)
                    if st.assignee_id is not None
                    else None
                ),
                used_seconds=st_used,
                used_hours=round(st_used / 3600, 4),
            )
        )

    used_total_seconds = used_task_seconds + used_subtask_seconds
    if task.estimated_hours is not None:
        estimated = float(task.estimated_hours)
        estimated_hours_opt: Optional[float] = float(task.estimated_hours)
    else:
        estimated = 0.0
        estimated_hours_opt = None
    task_read = TaskUtilizationRead(
        id=task.id,
        title=task.title,
        estimated_hours=estimated_hours_opt,
        assignee_id=task.assignee_id,
        assignee_name=(
            user_map.get(task.assignee_id)
            if task.assignee_id is not None
            else None
        ),
        used_task_seconds=used_task_seconds,
        used_subtask_seconds=used_subtask_seconds,
        used_total_seconds=used_total_seconds,
        used_total_hours=round(used_total_seconds / 3600, 4),
        subtasks=st_reads,
    )
    return task_read, estimated, used_total_seconds


async def build_project_utilization_response(
    db: deps.DBDep,
    *,
    project: Project,
    range: str,
) -> ProjectUtilizationResponse:
    start_dt, end_dt = get_range_window(range)
    tasks, subtasks = await fetch_project_tasks_and_subtasks(
        db, project_id=project.id
    )
    subtasks_by_task = group_subtasks_by_task_id(subtasks)
    used_map = await get_project_used_seconds_map(
        db,
        project_id=project.id,
        start_dt=start_dt,
        end_dt=end_dt,
    )

    user_ids: Set[int] = {
        t.assignee_id for t in tasks if t.assignee_id is not None
    }
    user_ids |= {
        st.assignee_id for st in subtasks if st.assignee_id is not None
    }
    user_map = await get_user_name_map(db, user_ids)

    task_reads: list[TaskUtilizationRead] = []
    total_estimated_hours = 0.0
    total_used_seconds = 0
    for task in sorted(tasks, key=lambda x: x.id):
        task_read, task_est, used_total_seconds = build_task_utilization(
            task=task,
            subtasks=subtasks_by_task.get(task.id, []),
            used_map=used_map,
            user_map=user_map,
        )
        task_reads.append(task_read)
        total_estimated_hours += task_est
        total_used_seconds += used_total_seconds

    return ProjectUtilizationResponse(
        project_id=project.id,
        project_name=project.name,
        total_estimated_hours=round(total_estimated_hours, 4),
        total_used_seconds=total_used_seconds,
        total_used_hours=round(total_used_seconds / 3600, 4),
        tasks=task_reads,
    )


def as_utc_aware(dt: datetime) -> datetime:
    """Normalize DB datetimes to UTC-aware.

    MySQL stores DATETIME without tzinfo; SQLAlchemy returns naive datetimes
    even when `timezone=True`. Timer math expects aware datetimes.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


async def get_user_logged_seconds_on_date(
    db: deps.DBDep, user_id: int, target_date: date
) -> int:
    """Calculate total seconds logged by user on a specific date (UTC)."""
    day_start = datetime.combine(target_date, datetime.min.time()).replace(
        tzinfo=timezone.utc
    )
    day_end = day_start + timedelta(days=1)

    finished_query = select(func.sum(TimeEntry.duration_seconds)).where(
        and_(
            TimeEntry.user_id == user_id,
            TimeEntry.start_at >= day_start,
            TimeEntry.start_at < day_end,
        )
    )
    finished_result = await db.execute(finished_query)
    finished_seconds = int(finished_result.scalar() or 0)

    session_seconds = 0
    if target_date == datetime.now(timezone.utc).date():
        session_query = select(TimerSession).where(
            and_(
                TimerSession.user_id == user_id,
                TimerSession.status != DBTimerStatus.STOPPED,
            )
        )
        session_result = await db.execute(session_query)
        active_session: TimerSession | None = session_result.scalars().first()

        if active_session is not None:
            session_seconds = active_session.accumulated_seconds
            if active_session.status == DBTimerStatus.RUNNING:
                now = datetime.now(timezone.utc)
                delta = (
                    now - as_utc_aware(active_session.last_state_change_at)
                ).total_seconds()
                session_seconds += int(delta)

    return finished_seconds + session_seconds


@router.get("/timer/status", response_model=TimerStatus)
async def get_timer_status(
    *,
    db: deps.DBDep,
    current_user: deps.CurrentUser,
) -> Any:
    """Get current active/paused timer status for the user."""
    query = select(TimerSession).where(
        and_(
            TimerSession.user_id == current_user.id,
            TimerSession.status != DBTimerStatus.STOPPED
        )
    ).limit(1)
    result = await db.execute(query)
    session = result.scalars().first()
    if not session:
        return TimerStatus(is_active=False)
    
    now = datetime.now(timezone.utc)
    duration = session.accumulated_seconds
    if session.status == DBTimerStatus.RUNNING:
        duration += int(
            (now - as_utc_aware(session.last_state_change_at)).total_seconds()
        )

    # Auto-stop if timer has been running beyond 9 hours
    if duration >= MAX_DAILY_SECONDS and session.status == DBTimerStatus.RUNNING:
        capped_duration = MAX_DAILY_SECONDS
        # Check already logged today to cap correctly
        logged_today = await get_user_logged_seconds_on_date(
            db, current_user.id, date.today()
        )
        final_duration = max(0, min(capped_duration, MAX_DAILY_SECONDS - logged_today))

        session.status = DBTimerStatus.STOPPED
        session.stopped_at = now
        session.last_state_change_at = now

        entry = TimeEntry(
            user_id=current_user.id,
            project_id=session.project_id,
            task_id=session.task_id,
            subtask_id=session.subtask_id,
            start_at=session.started_at,
            end_at=now,
            duration_seconds=final_duration,
            source=TimeEntrySource.TIMER,
            created_by_user_id=current_user.id,
        )
        db.add(entry)
        await db.commit()

        return TimerStatus(
            is_active=False,
            auto_stopped=True,
            auto_stop_reason=f"Timer auto-stopped at {MAX_DAILY_SECONDS // 3600} hour daily limit.",
        )

    return TimerStatus(
        is_active=True,
        session=TimerSessionRead.model_validate(session),
        current_duration_seconds=max(0, duration)
    )


@router.post("/timer/start", response_model=TimerSessionRead)
async def start_timer(
    *,
    db: deps.DBDep,
    current_user: TimeWriteUser,
    timer_in: TimerStart,
    request: Request
) -> Any:
    """Start a new timer. Exactly one active timer per employee."""
    query = select(TimerSession).where(
        and_(
            TimerSession.user_id == current_user.id,
            TimerSession.status != DBTimerStatus.STOPPED
        )
    ).limit(1)
    result = await db.execute(query)
    if result.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "ACTIVE_TIMER_EXISTS",
                    "message": "Active timer exists. Stop it first."
                }
            }
        )
    
    # Check 9 hour daily limit
    current_total = await get_user_logged_seconds_on_date(
        db, current_user.id, date.today()
    )
    if current_total >= MAX_DAILY_SECONDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "DAILY_LIMIT_REACHED",
                    "message": "Maximum daily allowance (9 hours) reached."
                }
            }
        )

    project = await db.get(Project, timer_in.project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_detail("PROJECT_NOT_FOUND", MSG_PROJECT_NOT_FOUND),
        )

    task, subtask = await resolve_work_item(
        db,
        project_id=timer_in.project_id,
        task_id=timer_in.task_id,
        subtask_id=timer_in.subtask_id,
    )
    require_assigned_to_user(
        user_id=current_user.id,
        task=task,
        subtask=subtask,
    )
    now = datetime.now(timezone.utc)
    db_obj = TimerSession(
        user_id=current_user.id,
        project_id=timer_in.project_id,
        task_id=task.id if task else None,
        subtask_id=subtask.id if subtask else None,
        status=DBTimerStatus.RUNNING,
        started_at=now,
        last_state_change_at=now,
        notes=timer_in.notes
    )
    db.add(db_obj)
    await db.flush()
    audit = AuditLog(
        user_id=current_user.id,
        action="TIMER_START",
        resource_type="timer",
        resource_id=str(db_obj.id),
        ip_address=request.client.host if request.client else None,
        details={
            "project_id": timer_in.project_id,
            "task_id": task.id if task else None,
            "subtask_id": subtask.id if subtask else None,
        },
    )
    db.add(audit)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj


@router.post(
    "/timer/pause",
    response_model=TimerSessionRead,
    responses={
        404: {
            "description": MSG_NO_RUNNING_TIMER,
        }
    },
)
async def pause_timer(
    *,
    db: deps.DBDep,
    current_user: TimeWriteUser,
    request: Request
) -> Any:
    """Pause current running timer."""
    query = select(TimerSession).where(
        and_(
            TimerSession.user_id == current_user.id,
            TimerSession.status == DBTimerStatus.RUNNING
        )
    ).limit(1)
    result = await db.execute(query)
    session = result.scalars().first()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_detail("NO_RUNNING_TIMER", MSG_NO_RUNNING_TIMER),
        )
    now = datetime.now(timezone.utc)
    # Update accumulated seconds before pausing
    delta = int(
        (now - as_utc_aware(session.last_state_change_at)).total_seconds()
    )
    session.accumulated_seconds += max(0, delta)
    session.status = DBTimerStatus.PAUSED
    session.paused_at = now
    session.last_state_change_at = now
    audit = AuditLog(
        user_id=current_user.id,
        action="TIMER_PAUSE",
        resource_type="timer",
        resource_id=str(session.id),
        ip_address=request.client.host if request.client else None
    )
    db.add(audit)
    await db.commit()
    await db.refresh(session)
    return session


@router.post(
    "/timer/resume",
    response_model=TimerSessionRead,
    responses={
        404: {
            "description": MSG_NO_PAUSED_TIMER,
        }
    },
)
async def resume_timer(
    *,
    db: deps.DBDep,
    current_user: TimeWriteUser,
    request: Request
) -> Any:
    """Resume a paused timer."""
    query = select(TimerSession).where(
        and_(
            TimerSession.user_id == current_user.id,
            TimerSession.status == DBTimerStatus.PAUSED
        )
    ).limit(1)
    result = await db.execute(query)
    session = result.scalars().first()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_detail("NO_PAUSED_TIMER", MSG_NO_PAUSED_TIMER),
        )
    
    # Check 9 hour daily limit
    current_total = await get_user_logged_seconds_on_date(
        db, current_user.id, date.today()
    )
    if current_total >= MAX_DAILY_SECONDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "DAILY_LIMIT_REACHED",
                    "message": "Maximum daily allowance (9 hours) reached."
                }
            }
        )

    now = datetime.now(timezone.utc)
    session.status = DBTimerStatus.RUNNING
    session.last_state_change_at = now
    audit = AuditLog(
        user_id=current_user.id,
        action="TIMER_RESUME",
        resource_type="timer",
        resource_id=str(session.id),
        ip_address=request.client.host if request.client else None
    )
    db.add(audit)
    await db.commit()
    await db.refresh(session)
    return session


@router.post(
    "/timer/stop",
    response_model=TimeEntryRead,
    responses={
        404: {
            "description": MSG_NO_ACTIVE_TIMER,
        }
    },
)
async def stop_timer(
    *,
    db: deps.DBDep,
    current_user: TimeWriteUser,
    request: Request
) -> Any:
    """Stop current timer and create a TimeEntry."""
    query = select(TimerSession).where(
        and_(
            TimerSession.user_id == current_user.id,
            TimerSession.status != DBTimerStatus.STOPPED
        )
    ).limit(1)
    result = await db.execute(query)
    session = result.scalars().first()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_detail("NO_ACTIVE_TIMER", MSG_NO_ACTIVE_TIMER),
        )
    now = datetime.now(timezone.utc)
    duration = session.accumulated_seconds
    if session.status == DBTimerStatus.RUNNING:
        duration += int(
            (now - as_utc_aware(session.last_state_change_at)).total_seconds()
        )
    
    # Enforce 9 hour limit on stopping (cap duration)
    logged_on_date = await get_user_logged_seconds_on_date(
        db, current_user.id, date.today()
    )
    if logged_on_date > MAX_DAILY_SECONDS:
        excess = logged_on_date - MAX_DAILY_SECONDS
        duration = max(0, duration - excess)

    session.status = DBTimerStatus.STOPPED
    session.stopped_at = now
    session.last_state_change_at = now
    
    entry = TimeEntry(
        user_id=current_user.id,
        project_id=session.project_id,
        task_id=session.task_id,
        subtask_id=session.subtask_id,
        start_at=session.started_at,
        end_at=now,
        duration_seconds=max(0, duration),
        source=TimeEntrySource.TIMER,
        created_by_user_id=current_user.id
    )
    db.add(entry)
    await db.flush()
    audit = AuditLog(
        user_id=current_user.id,
        action="TIMER_STOP",
        resource_type="timer",
        resource_id=str(session.id),
        ip_address=request.client.host if request.client else None,
        details={"duration_seconds": duration}
    )
    db.add(audit)
    await db.commit()
    await db.refresh(entry)
    return entry


@router.post(
    "/time-entries/manual",
    response_model=TimeEntryRead,
    responses={
        400: {
            "description": MSG_INVALID_TIME_RANGE,
        }
    },
)
async def create_manual_entry(
    *,
    db: deps.DBDep,
    current_user: TimeWriteUser,
    entry_in: TimeEntryManual,
    request: Request
) -> Any:
    """Create a manual time entry. Manual reason is required."""
    duration = int((entry_in.end_at - entry_in.start_at).total_seconds())
    if duration <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail(
                "INVALID_TIME_RANGE",
                MSG_INVALID_TIME_RANGE,
            ),
        )
    
    # Check 9 hour daily limit
    current_total = await get_user_logged_seconds_on_date(
        db, current_user.id, entry_in.start_at.date()
    )
    if current_total + duration > MAX_DAILY_SECONDS:
        remaining = max(0, MAX_DAILY_SECONDS - current_total)
        remaining_hrs = remaining / 3600
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "DAILY_LIMIT_EXCEEDED",
                    "message": (
                        f"Daily limit exceed for {entry_in.start_at.date()}. "
                        f"You can only log {remaining_hrs:.2f} more hours."
                    )
                }
            }
        )

    project = await db.get(Project, entry_in.project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_detail("PROJECT_NOT_FOUND", MSG_PROJECT_NOT_FOUND),
        )

    task, subtask = await resolve_work_item(
        db,
        project_id=entry_in.project_id,
        task_id=entry_in.task_id,
        subtask_id=entry_in.subtask_id,
    )
    require_assigned_to_user(
        user_id=current_user.id,
        task=task,
        subtask=subtask,
    )

    entry = TimeEntry(
        user_id=current_user.id,
        project_id=entry_in.project_id,
        task_id=task.id,
        subtask_id=subtask.id if subtask else None,
        start_at=entry_in.start_at,
        end_at=entry_in.end_at,
        duration_seconds=duration,
        source=TimeEntrySource.MANUAL,
        manual_reason=entry_in.manual_reason,
        created_by_user_id=current_user.id,
    )
    db.add(entry)
    await db.flush()
    audit = AuditLog(
        user_id=current_user.id,
        action="MANUAL_TIME_ENTRY",
        resource_type="timesheet",
        resource_id=str(entry.id),
        ip_address=request.client.host if request.client else None
    )
    db.add(audit)
    await db.commit()
    await db.refresh(entry)
    return entry


@router.get("/my", response_model=TimesheetRead)
async def get_my_timesheet(
    *,
    db: deps.DBDep,
    current_user: TimeReadUser,
    range: str = "weekly"
) -> Any:
    """Get personal timesheet with daily aggregations."""
    return await build_my_timesheet_response(
        db,
        user_id=current_user.id,
        range=range,
    )


@router.get("/utilization/my", response_model=MyWorkUtilizationResponse)
async def get_my_work_utilization(
    *,
    db: deps.DBDep,
    current_user: TimeReadUser,
    range: str = "weekly",
) -> Any:
    return await build_my_work_utilization_response(
        db,
        user_id=current_user.id,
        range=range,
    )


@router.get(
    "/utilization/project/{project_id}",
    response_model=ProjectUtilizationResponse,
)
async def get_project_utilization(
    *,
    db: deps.DBDep,
    current_user: TimeReadUser,
    project_id: int,
    range: str = "monthly",
) -> Any:
    await require_project_manager(
        db, project_id=project_id, current_user=current_user
    )

    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_detail("PROJECT_NOT_FOUND", "Project not found"),
        )

    return await build_project_utilization_response(
        db,
        project=project,
        range=range,
    )
