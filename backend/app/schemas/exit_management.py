from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, field_validator


# ─── Resignation ──────────────────────────────────────────────

class ResignationSubmit(BaseModel):
    reason: str
    reason_details: Optional[str] = None


class ResignationAccept(BaseModel):
    last_working_day: Optional[date] = None  # HR can override


class ResignationRead(BaseModel):
    id: int
    employee_id: int
    reason: str
    reason_details: Optional[str] = None
    status: str
    resignation_date: date
    last_working_day: date
    notice_period_days: int
    accepted_by_id: Optional[int] = None
    accepted_at: Optional[datetime] = None
    released_by_id: Optional[int] = None
    released_at: Optional[datetime] = None
    withdrawn_at: Optional[datetime] = None
    hr_note: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    # Nested info
    employee_name: Optional[str] = None
    employee_emp_id: Optional[str] = None
    department: Optional[str] = None
    designation: Optional[str] = None
    accepted_by_name: Optional[str] = None
    released_by_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# ─── Exit Interview ───────────────────────────────────────────

class ExitInterviewSubmit(BaseModel):
    # Reason checkboxes
    reason_career: bool = False
    reason_studies: bool = False
    reason_personal: bool = False
    reason_relocation: bool = False
    reason_health: bool = False
    reason_work_environment: bool = False
    reason_compensation: bool = False
    reason_relationship: bool = False
    reason_role_mismatch: bool = False
    reason_other: Optional[str] = None
    reason_explanation: Optional[str] = None

    # Ratings 1-5
    rating_job_satisfaction: Optional[int] = None
    rating_work_life_balance: Optional[int] = None
    rating_team_cooperation: Optional[int] = None
    rating_management_communication: Optional[int] = None
    rating_training_development: Optional[int] = None
    rating_career_growth: Optional[int] = None
    rating_compensation: Optional[int] = None
    rating_company_culture: Optional[int] = None

    # Open feedback
    feedback_liked_most: Optional[str] = None
    feedback_liked_least: Optional[str] = None
    feedback_suggestions: Optional[str] = None

    @field_validator(
        "rating_job_satisfaction", "rating_work_life_balance",
        "rating_team_cooperation", "rating_management_communication",
        "rating_training_development", "rating_career_growth",
        "rating_compensation", "rating_company_culture",
        mode="before"
    )
    @classmethod
    def validate_rating(cls, v):
        if v is not None and (v < 1 or v > 5):
            raise ValueError("Rating must be between 1 and 5")
        return v


class ExitInterviewHRRemarks(BaseModel):
    hr_remarks: str


class ExitInterviewRead(BaseModel):
    id: int
    resignation_id: int
    employee_id: int

    reason_career: bool
    reason_studies: bool
    reason_personal: bool
    reason_relocation: bool
    reason_health: bool
    reason_work_environment: bool
    reason_compensation: bool
    reason_relationship: bool
    reason_role_mismatch: bool
    reason_other: Optional[str] = None
    reason_explanation: Optional[str] = None

    rating_job_satisfaction: Optional[int] = None
    rating_work_life_balance: Optional[int] = None
    rating_team_cooperation: Optional[int] = None
    rating_management_communication: Optional[int] = None
    rating_training_development: Optional[int] = None
    rating_career_growth: Optional[int] = None
    rating_compensation: Optional[int] = None
    rating_company_culture: Optional[int] = None

    feedback_liked_most: Optional[str] = None
    feedback_liked_least: Optional[str] = None
    feedback_suggestions: Optional[str] = None

    hr_remarks: Optional[str] = None
    submitted_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ─── Clearance ────────────────────────────────────────────────

class ClearanceItemCreate(BaseModel):
    item_name: str


class ClearanceItemRead(BaseModel):
    id: int
    item_name: str
    is_cleared: bool
    remarks: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ClearanceItemUpdate(BaseModel):
    is_cleared: bool
    remarks: Optional[str] = None


class ClearanceRequestCreate(BaseModel):
    department: str
    assigned_to_id: int
    items: List[ClearanceItemCreate] = []


class ClearanceRequestRead(BaseModel):
    id: int
    resignation_id: int
    department: str
    assigned_to_id: int
    assigned_to_name: Optional[str] = None
    status: str
    remarks: Optional[str] = None
    cleared_at: Optional[datetime] = None
    created_at: datetime
    items: List[ClearanceItemRead] = []

    model_config = ConfigDict(from_attributes=True)


class ClearanceAction(BaseModel):
    status: str  # "cleared" or "flagged"
    remarks: Optional[str] = None
    items: Optional[List[ClearanceItemUpdate]] = None


class InitiateClearance(BaseModel):
    clearances: List[ClearanceRequestCreate]


# ─── Combined Exit Details ────────────────────────────────────

class ExitDetailsRead(BaseModel):
    resignation: ResignationRead
    exit_interview: Optional[ExitInterviewRead] = None
    clearance_requests: List[ClearanceRequestRead] = []
    days_remaining: Optional[int] = None
    all_cleared: bool = False
