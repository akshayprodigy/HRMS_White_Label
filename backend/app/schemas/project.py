from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict
from .task import TaskRead
from app.models.project import CostChangeStatus


# Milestone
class MilestoneBase(BaseModel):
    title: str
    description: Optional[str] = None
    due_date: datetime
    status: str = "pending"


class MilestoneCreate(MilestoneBase):
    project_id: int


class MilestoneRead(MilestoneBase):
    id: int
    project_id: int
    model_config = ConfigDict(from_attributes=True)


# Costing
class CostBaselineBase(BaseModel):
    amount: float
    budget_hours: Optional[float] = None
    description: Optional[str] = None
    is_active: bool = True


class CostBaselineCreate(CostBaselineBase):
    project_id: int


class CostBaselineRead(CostBaselineBase):
    id: int
    project_id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class CostChangeRequestBase(BaseModel):
    proposed_amount: float
    reason: str
    impact: Optional[str] = None


class CostChangeRequestCreate(CostChangeRequestBase):
    project_id: int
    baseline_id: Optional[int] = None


class CostChangeRequestRead(CostChangeRequestBase):
    id: int
    project_id: int
    baseline_id: Optional[int] = None
    baseline_amount: float
    percent_change: float
    status: CostChangeStatus
    created_by_id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class CostChangeAction(BaseModel):
    status: CostChangeStatus  # approved, rejected, needs_clarification
    remarks: Optional[str] = None


class ProjectBase(BaseModel):
    name: str
    description: Optional[str] = None
    code: str
    status: str = "active"


class ProjectCreate(ProjectBase):
    pass


class ProjectCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    code: Optional[str] = None
    status: str = "active"
    budget: Optional[float] = None
    budget_hours: Optional[float] = None
    end_date: Optional[datetime] = None
    client_id: Optional[int] = None


class ProjectMemberRead(BaseModel):
    id: int
    project_id: int
    user_id: int
    role: str
    user_name: Optional[str] = None
    user_email: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ProjectMemberCreate(BaseModel):
    user_id: int
    role: str = "member"


class ProjectRead(ProjectBase):
    id: int
    created_at: datetime
    client_id: Optional[int] = None
    client_name: Optional[str] = None
    manager_name: Optional[str] = None
    budget: float = 0.0
    budget_hours: Optional[float] = None
    actual_cost: float = 0.0
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    parent_project_id: Optional[int] = None
    functional_area_id: Optional[int] = None
    functional_area_code: Optional[str] = None
    functional_area_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ProjectWithTasks(ProjectRead):
    tasks: List[TaskRead] = []
