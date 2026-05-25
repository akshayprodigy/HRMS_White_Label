from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, EmailStr
from app.models.recruitment import (
    RequisitionPriority, 
    RequisitionStatus, 
    EmploymentType,
    ApplicantStatus
)


class RequisitionBase(BaseModel):
    title: str
    department: str
    positions_count: int = 1
    priority: RequisitionPriority = RequisitionPriority.MEDIUM
    employment_type: EmploymentType = EmploymentType.FULL_TIME
    reason: Optional[str] = None
    budget_range: Optional[str] = None
    job_description: str
    qualifications: Optional[str] = None


class RequisitionCreate(RequisitionBase):
    pass


class RequisitionUpdate(BaseModel):
    title: Optional[str] = None
    department: Optional[str] = None
    positions_count: Optional[int] = None
    priority: Optional[RequisitionPriority] = None
    employment_type: Optional[EmploymentType] = None
    reason: Optional[str] = None
    budget_range: Optional[str] = None
    job_description: Optional[str] = None
    qualifications: Optional[str] = None
    status: Optional[RequisitionStatus] = None


class InterviewBase(BaseModel):
    interview_type: str = "technical"
    scheduled_at: datetime
    interviewer_id: int
    round_number: int = 1
    notes: Optional[str] = None


class InterviewCreate(InterviewBase):
    applicant_id: int


class InterviewRead(InterviewBase):
    id: int
    status: str
    feedback: Optional[str] = None
    rating: Optional[int] = None
    
    model_config = ConfigDict(from_attributes=True)


class ApplicantBase(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    phone: Optional[str] = None
    source: Optional[str] = None
    experience_years: Optional[float] = None


class ApplicantCreate(ApplicantBase):
    requisition_id: int


class ApplicantRead(ApplicantBase):
    id: int
    requisition_id: int
    status: ApplicantStatus
    resume_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class ApplicantWithInterviews(ApplicantRead):
    interviews: List[InterviewRead] = []


class RequisitionRead(RequisitionBase):
    id: int
    req_id: str
    status: RequisitionStatus
    creator_id: int
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class RequisitionWithApplicants(RequisitionRead):
    applicants: List[ApplicantRead] = []
