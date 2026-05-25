from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict
from app.models.approval import ApprovalStatus

class ApprovalStepRead(BaseModel):
    id: int
    step_number: int
    approver_id: Optional[int]
    role_id: Optional[int]
    status: ApprovalStatus
    comment: Optional[str]
    actioned_at: Optional[datetime]
    model_config = ConfigDict(from_attributes=True)

class ApprovalItemRead(BaseModel):
    id: int
    resource_type: str
    resource_id: str
    status: ApprovalStatus
    current_step_number: int
    requested_by_id: Optional[int]
    requested_by_name: Optional[str] = None
    created_at: datetime
    due_date: Optional[datetime]
    steps: List[ApprovalStepRead]
    model_config = ConfigDict(from_attributes=True)

class ApprovalAction(BaseModel):
    status: ApprovalStatus  # APPROVED, REJECTED, CHANGES_REQUESTED
    comment: Optional[str] = None
    next_approver_id: Optional[int] = None
