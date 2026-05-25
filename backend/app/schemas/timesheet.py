from datetime import datetime, date
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, field_validator
import enum


class ProjectBase(BaseModel):
    name: str
    description: Optional[str] = None
    status: str = "active"


class ProjectRead(ProjectBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


class TimerStatusEnum(str, enum.Enum):
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"


class TimeEntrySource(str, enum.Enum):
    TIMER = "timer"
    MANUAL = "manual"


class TimerStart(BaseModel):
    project_id: int
    task_id: Optional[int] = None
    subtask_id: Optional[int] = None
    notes: Optional[str] = None


class TimerSessionRead(BaseModel):
    id: int
    user_id: int
    project_id: int
    task_id: Optional[int] = None
    subtask_id: Optional[int] = None
    status: TimerStatusEnum
    started_at: datetime
    paused_at: Optional[datetime] = None
    stopped_at: Optional[datetime] = None
    accumulated_seconds: int = 0
    last_state_change_at: datetime
    notes: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class TimerStatus(BaseModel):
    is_active: bool
    session: Optional[TimerSessionRead] = None
    current_duration_seconds: int = 0
    auto_stopped: bool = False
    auto_stop_reason: Optional[str] = None


class TimeEntryManual(BaseModel):
    project_id: int
    task_id: Optional[int] = None
    subtask_id: Optional[int] = None
    start_at: datetime
    end_at: datetime
    manual_reason: str

    @field_validator("manual_reason")
    @classmethod
    def reason_required(cls, v: str) -> str:
        if not v or len(v.strip()) == 0:
            raise ValueError("Manual reason is required")
        return v


class TimeEntryRead(BaseModel):
    id: int
    user_id: int
    project_id: int
    project_name: Optional[str] = None
    task_id: Optional[int] = None
    subtask_id: Optional[int] = None
    start_at: datetime
    end_at: datetime
    duration_seconds: int
    source: TimeEntrySource
    manual_reason: Optional[str] = None
    is_manual: bool = False  # For frontend convenience
    
    model_config = ConfigDict(from_attributes=True)

    @field_validator("is_manual", mode="before")
    @classmethod
    def set_is_manual(cls, v: bool, info) -> bool:
        # Pydantic v2: use info.data
        return info.data.get("source") == TimeEntrySource.MANUAL


class DailyAggregation(BaseModel):
    day: date
    total_seconds: int
    entries: List[TimeEntryRead]


class TimesheetRead(BaseModel):
    start_date: date
    end_date: date
    total_seconds: int
    # {project_id: int, project_name: str, total_seconds: int}
    projects: List[dict]
    daily_data: List[DailyAggregation]


class WeeklyAggregation(BaseModel):
    start_date: date
    end_date: date
    total_weekly_seconds: int
    daily_data: List[DailyAggregation]


class MyWorkUtilizationItem(BaseModel):
    project_id: int
    project_name: str
    task_id: int
    task_title: str
    subtask_id: Optional[int] = None
    subtask_title: Optional[str] = None
    estimated_hours: Optional[float] = None
    used_seconds: int
    used_hours: float


class MyWorkUtilizationResponse(BaseModel):
    start_date: date
    end_date: date
    total_used_seconds: int
    items: List[MyWorkUtilizationItem]


class SubtaskUtilizationRead(BaseModel):
    id: int
    title: str
    estimated_hours: Optional[float] = None
    assignee_id: Optional[int] = None
    assignee_name: Optional[str] = None
    used_seconds: int
    used_hours: float


class TaskUtilizationRead(BaseModel):
    id: int
    title: str
    estimated_hours: Optional[float] = None
    assignee_id: Optional[int] = None
    assignee_name: Optional[str] = None
    used_task_seconds: int
    used_subtask_seconds: int
    used_total_seconds: int
    used_total_hours: float
    subtasks: List[SubtaskUtilizationRead]


class ProjectUtilizationResponse(BaseModel):
    project_id: int
    project_name: str
    total_estimated_hours: float
    total_used_seconds: int
    total_used_hours: float
    tasks: List[TaskUtilizationRead]
