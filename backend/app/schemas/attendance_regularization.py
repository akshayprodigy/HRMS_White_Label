from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RegularizationCreate(BaseModel):
    work_date: date
    requested_punch_in: datetime
    requested_punch_out: Optional[datetime] = None
    reason: str = Field(..., max_length=2000)

    @field_validator("reason")
    @classmethod
    def _reason_not_blank(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("reason must not be blank")
        return v


class RegularizationDecision(BaseModel):
    approve: bool
    note: Optional[str] = Field(default=None, max_length=2000)


class RegularizationRead(BaseModel):
    id: int
    user_id: int
    work_date: date
    attendance_id: Optional[int] = None
    requested_punch_in: datetime
    requested_punch_out: Optional[datetime] = None
    reason: str
    status: str
    decided_by_id: Optional[int] = None
    decided_at: Optional[datetime] = None
    decision_note: Optional[str] = None
    created_at: datetime
    requester_name: Optional[str] = None
    requester_employee_code: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)
