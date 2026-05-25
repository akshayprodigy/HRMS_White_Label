from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field


class SubtaskBase(BaseModel):
    title: str
    is_completed: bool = False
    estimated_hours: Optional[float] = Field(default=None, ge=0)


class SubtaskCreate(SubtaskBase):
    parent_subtask_id: Optional[int] = None
    assignee_id: Optional[int] = None
    assignee_email: Optional[str] = None


class SubtaskRead(SubtaskBase):
    id: int
    task_id: int
    parent_subtask_id: Optional[int] = None
    assignee_id: Optional[int] = None
    model_config = ConfigDict(from_attributes=True)


class TaskCommentBase(BaseModel):
    content: str


class TaskCommentCreate(TaskCommentBase):
    subtask_id: Optional[int] = None


class TaskCommentRead(TaskCommentBase):
    id: int
    created_at: datetime
    user_id: int
    subtask_id: Optional[int] = None
    model_config = ConfigDict(from_attributes=True)


class TaskAttachmentRead(BaseModel):
    id: int
    file_name: str
    file_path: str
    file_type: Optional[str] = None
    file_size: Optional[int] = None
    uploaded_at: datetime
    uploader_id: int
    model_config = ConfigDict(from_attributes=True)


class TaskBase(BaseModel):
    title: str
    description: Optional[str] = None
    status: str = "todo"
    priority: str = "medium"
    due_date: Optional[datetime] = None
    estimated_hours: Optional[float] = Field(default=None, ge=0)


class TaskCreate(TaskBase):
    project_id: int
    estimated_hours: float = Field(ge=0)
    assignee_id: Optional[int] = None
    assignee_email: Optional[str] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    due_date: Optional[datetime] = None
    estimated_hours: Optional[float] = Field(default=None, ge=0)
    assignee_id: Optional[int] = None


class TaskRead(TaskBase):
    id: int
    project_id: int
    project_name: Optional[str] = None
    creator_id: int
    assignee_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    actual_hours: float = 0.0

    subtasks: List[SubtaskRead] = []
    model_config = ConfigDict(from_attributes=True)


class TaskDetail(TaskRead):
    comments: List[TaskCommentRead] = []
    attachments: List[TaskAttachmentRead] = []


# ── Task Completion Workflow ─────────────────────────────────────────────────

class TaskCompletionDocumentRead(BaseModel):
    id: int
    request_id: int
    file_name: str
    file_size: Optional[int] = None
    mime_type: Optional[str] = None
    uploaded_by_id: int
    uploaded_at: datetime
    model_config = ConfigDict(from_attributes=True)


class TaskCompletionRequestCreate(BaseModel):
    notes: str = Field(..., min_length=1, max_length=2000)
    subtask_id: Optional[int] = None


class TaskCompletionReviewAction(BaseModel):
    action: str = Field(..., pattern="^(approve|reject|on_hold)$")
    reviewer_notes: str = Field(..., min_length=1, max_length=2000)


class TaskCompletionRequestRead(BaseModel):
    id: int
    task_id: int
    subtask_id: Optional[int] = None
    subtask_title: Optional[str] = None
    submitted_by_id: int
    submitted_by_name: Optional[str] = None
    status: str
    notes: Optional[str] = None
    reviewer_notes: Optional[str] = None
    reviewed_by_id: Optional[int] = None
    reviewed_by_name: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    documents: List[TaskCompletionDocumentRead] = []
    model_config = ConfigDict(from_attributes=True)


class TaskTimeSummary(BaseModel):
    task_id: int
    estimated_hours: Optional[float] = None
    actual_hours: float
    requests: List[TaskCompletionRequestRead] = []
