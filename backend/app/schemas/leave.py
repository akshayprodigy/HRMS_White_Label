from datetime import datetime, date
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, computed_field
from app.models.leave import LeaveStatus, HalfDaySession

class LeaveTypeBase(BaseModel):
    name: str
    code: Optional[str] = None
    description: Optional[str] = None
    unpaid_allowed: bool = False

class LeaveTypeCreate(LeaveTypeBase):
    annual_quota: Optional[float] = None
    max_carry_forward: Optional[float] = None
    max_accumulation: Optional[float] = None
    max_consecutive_days: Optional[int] = None
    allow_half_day: bool = True
    requires_medical_cert_after: Optional[int] = None
    is_cumulative: bool = True
    use_within_days: Optional[int] = None
    max_per_month: Optional[int] = None
    max_per_year: Optional[int] = None

class LeaveTypeUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    unpaid_allowed: Optional[bool] = None

class LeaveTypeRead(LeaveTypeBase):
    id: int
    annual_quota: Optional[float] = None
    max_carry_forward: Optional[float] = None
    max_accumulation: Optional[float] = None
    max_consecutive_days: Optional[int] = None
    allow_half_day: bool = True
    requires_medical_cert_after: Optional[int] = None
    is_cumulative: bool = True
    use_within_days: Optional[int] = None
    max_per_month: Optional[int] = None
    max_per_year: Optional[int] = None
    model_config = ConfigDict(from_attributes=True)

class LeaveBalanceRead(BaseModel):
    leave_type: LeaveTypeRead
    balance: float
    used: float
    model_config = ConfigDict(from_attributes=True)

    @computed_field
    def total(self) -> float:
        return self.balance

    @computed_field
    def remaining(self) -> float:
        return self.balance - self.used

class LeaveRequestBase(BaseModel):
    leave_type_id: int
    start_date: date
    end_date: date
    is_half_day: bool = False
    half_day_session: Optional[HalfDaySession] = None
    reason: str
    emergency_contact: Optional[str] = None
    attachment_url: Optional[str] = None

class LeaveRequestCreate(LeaveRequestBase):
    pass

class LeaveRequestRead(LeaveRequestBase):
    id: int
    employee_id: int
    status: LeaveStatus
    created_at: datetime
    created_by_user_id: int
    leave_type: LeaveTypeRead
    model_config = ConfigDict(from_attributes=True)

    @computed_field
    def total_days(self) -> float:
        if self.is_half_day:
            return 0.5
        return (self.end_date - self.start_date).days + 1.0
