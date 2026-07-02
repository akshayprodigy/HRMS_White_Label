from datetime import date, datetime, time
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


VALID_WEEKDAYS = {0, 1, 2, 3, 4, 5, 6}  # Python convention: Mon=0..Sun=6


class ShiftTemplateBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    start_time: time
    end_time: time
    break_minutes: int = Field(60, ge=0, le=8 * 60)
    grace_in_minutes: int = Field(10, ge=0, le=120)
    grace_out_minutes: int = Field(10, ge=0, le=120)
    full_day_hours: float = Field(9.0, gt=0.0, le=24.0)
    half_day_hours: float = Field(4.5, gt=0.0, le=24.0)
    weekly_offs: List[int] = Field(default_factory=list)
    is_active: bool = True

    @field_validator("weekly_offs")
    @classmethod
    def _validate_weekly_offs(cls, v: List[int]) -> List[int]:
        bad = [d for d in v if d not in VALID_WEEKDAYS]
        if bad:
            raise ValueError(
                "weekly_offs must contain weekday integers 0..6 (Mon..Sun); "
                f"got {bad}"
            )
        # de-duplicate but preserve order
        seen = set()
        return [d for d in v if not (d in seen or seen.add(d))]

    @model_validator(mode="after")
    def _half_day_le_full_day(self):
        if self.half_day_hours > self.full_day_hours:
            raise ValueError("half_day_hours cannot exceed full_day_hours")
        if self.start_time == self.end_time:
            raise ValueError("start_time and end_time cannot be equal")
        return self


class ShiftTemplateCreate(ShiftTemplateBase):
    pass


class ShiftTemplateUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    break_minutes: Optional[int] = Field(default=None, ge=0, le=8 * 60)
    grace_in_minutes: Optional[int] = Field(default=None, ge=0, le=120)
    grace_out_minutes: Optional[int] = Field(default=None, ge=0, le=120)
    full_day_hours: Optional[float] = Field(default=None, gt=0.0, le=24.0)
    half_day_hours: Optional[float] = Field(default=None, gt=0.0, le=24.0)
    weekly_offs: Optional[List[int]] = None
    is_active: Optional[bool] = None

    @field_validator("weekly_offs")
    @classmethod
    def _validate_weekly_offs(cls, v: Optional[List[int]]) -> Optional[List[int]]:
        if v is None:
            return v
        bad = [d for d in v if d not in VALID_WEEKDAYS]
        if bad:
            raise ValueError(
                "weekly_offs must contain weekday integers 0..6 (Mon..Sun); "
                f"got {bad}"
            )
        seen = set()
        return [d for d in v if not (d in seen or seen.add(d))]


class ShiftTemplateRead(ShiftTemplateBase):
    id: int
    is_overnight: bool
    created_at: datetime
    updated_at: datetime
    created_by_id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class EmployeeShiftAssignmentBase(BaseModel):
    employee_id: int
    shift_template_id: int
    effective_from: date
    effective_to: Optional[date] = None
    note: Optional[str] = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def _date_order(self):
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to cannot be before effective_from")
        return self


class EmployeeShiftAssignmentCreate(EmployeeShiftAssignmentBase):
    pass


class EmployeeShiftAssignmentUpdate(BaseModel):
    shift_template_id: Optional[int] = None
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None
    note: Optional[str] = Field(default=None, max_length=255)


class EmployeeShiftAssignmentRead(EmployeeShiftAssignmentBase):
    id: int
    assigned_by_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    # Enrichment for table rows (read-only convenience).
    employee_name: Optional[str] = None
    employee_email: Optional[str] = None
    employee_department: Optional[str] = None
    shift_template_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class BulkAssignTargets(BaseModel):
    """Provide ONE of: employee_ids, or department (string match on Employee.department)."""
    employee_ids: Optional[List[int]] = None
    department: Optional[str] = Field(default=None, min_length=1, max_length=100)


class BulkAssignRequest(BulkAssignTargets):
    shift_template_id: int
    effective_from: date
    effective_to: Optional[date] = None
    note: Optional[str] = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def _exactly_one_target(self):
        has_ids = bool(self.employee_ids)
        has_dept = bool(self.department)
        if has_ids == has_dept:
            raise ValueError(
                "Provide exactly one of employee_ids or department"
            )
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to cannot be before effective_from")
        return self


class BulkAssignResult(BaseModel):
    assigned: int
    skipped: int
    failed: int
    errors: List[str] = Field(default_factory=list)


class EffectiveShiftResponse(BaseModel):
    employee_id: int
    on_date: date
    shift: Optional[ShiftTemplateRead] = None
    assignment_id: Optional[int] = None


# ---- Section R: shift change requests ------------------------------------


class ShiftChangeRequestCreate(BaseModel):
    requested_shift_template_id: int
    effective_from: date
    reason: str = Field(min_length=5, max_length=500)


class ShiftChangeRequestRead(BaseModel):
    id: int
    user_id: int
    user_name: Optional[str] = None
    current_shift_template_id: Optional[int] = None
    current_shift_name: Optional[str] = None
    requested_shift_template_id: int
    requested_shift_name: Optional[str] = None
    effective_from: date
    reason: str
    status: str
    approval_instance_id: Optional[int] = None
    created_at: datetime
    decided_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
