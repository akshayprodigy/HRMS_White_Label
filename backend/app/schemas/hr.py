from datetime import datetime, date
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict


class HolidayCalendarBase(BaseModel):
    name: str
    date: date
    location: str
    is_optional: bool = False
    description: Optional[str] = None


class HolidayCalendarCreate(HolidayCalendarBase):
    pass


class HolidayCalendarRead(HolidayCalendarBase):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PolicyDocumentBase(BaseModel):
    title: str
    description: Optional[str] = None
    file_url: str
    version: str = "1.0"
    is_active: bool = True


class PolicyDocumentCreate(PolicyDocumentBase):
    pass


class PolicyDocumentRead(PolicyDocumentBase):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PolicyAcknowledgementBase(BaseModel):
    policy_id: int


class PolicyAcknowledgementCreate(PolicyAcknowledgementBase):
    pass


class PolicyAcknowledgementRead(PolicyAcknowledgementBase):
    id: int
    user_id: int
    acknowledged_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LetterGenerateRequest(BaseModel):
    employee_id: int
    letter_type: str
    # Optional overrides for template data
    date: Optional[date] = None
    designation: Optional[str] = None
    department: Optional[str] = None
    joining_date: Optional[date] = None
    ctc: Optional[str] = None
    posting_location: Optional[str] = None
    confirmation_date: Optional[date] = None
    last_working_date: Optional[date] = None
    resignation_date: Optional[date] = None
    relieving_date: Optional[date] = None
    cessation_cause: Optional[str] = None
    performance_rating: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None


class EmployeeLetterRead(BaseModel):
    id: int
    employee_id: int
    letter_type: str
    reference_number: Optional[str] = None
    generated_at: datetime
    generated_by_id: int
    file_url: Optional[str] = None
    status: str

    model_config = ConfigDict(from_attributes=True)


class LetterTemplateBase(BaseModel):
    name: str
    category: str = "custom"
    description: Optional[str] = None
    body: str
    is_active: bool = True


class LetterTemplateCreate(LetterTemplateBase):
    pass


class LetterTemplateUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    body: Optional[str] = None
    is_active: Optional[bool] = None


class LetterTemplateRead(LetterTemplateBase):
    id: int
    created_by_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LetterTemplateGenerateRequest(BaseModel):
    employee_id: int
    title: Optional[str] = None
    extra_context: Optional[Dict[str, str]] = None
    date: Optional[date] = None


class LetterTemplatePreviewRequest(BaseModel):
    employee_id: int
    extra_context: Optional[Dict[str, str]] = None
    date: Optional[date] = None


class LetterPreviewResponse(BaseModel):
    rendered_body: str
    missing_placeholders: List[str]
    reference_number: Optional[str] = None


class LetterSendRequest(BaseModel):
    to_email: Optional[str] = None
    subject: Optional[str] = None
    message: Optional[str] = None


class ActivityItem(BaseModel):
    name: str
    identifier: str
    action: str
    type: str
    time: str


class HRDashboardStats(BaseModel):
    total_employees: int
    active_requisitions: int
    pending_actions: int
    avg_working_hours: str
    attendance_rate: float
    requisition_trend: str
    onboarding_count: int
    attendance_trends: List[Dict[str, Any]]
    leave_trends: List[Dict[str, Any]]
    activities: List[ActivityItem]
    # Real operational counters (all DB-derived).
    joined_this_month: int = 0
    today_present: int = 0
    today_on_leave: int = 0
    active_employees: int = 0
