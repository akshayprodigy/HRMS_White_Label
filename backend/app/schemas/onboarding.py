from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict
from app.models.onboarding import OnboardingStatus

class OnboardingTaskRead(BaseModel):
    id: int
    step_number: int
    title: str
    description: Optional[str] = None
    status: OnboardingStatus
    actor_role: str
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class OnboardingProcessRead(BaseModel):
    id: int
    applicant_id: int
    status: OnboardingStatus
    started_at: datetime
    completed_at: Optional[datetime] = None
    current_step: int
    tasks: List[OnboardingTaskRead]
    
    # Extra fields for UI convenience
    applicant_name: Optional[str] = None
    role_title: Optional[str] = None
    department: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class OnboardingCreate(BaseModel):
    applicant_id: int

class OnboardingUpdate(BaseModel):
    status: Optional[OnboardingStatus] = None
    current_step: Optional[int] = None

class OnboardingTaskUpdate(BaseModel):
    status: OnboardingStatus
