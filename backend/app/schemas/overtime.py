"""Pydantic schemas for OT + night-allowance APIs."""
from datetime import date, datetime, time
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ----- OvertimeRule --------------------------------------------------


class OvertimeRuleBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    scope: str = Field("org_default", pattern="^(org_default|shift)$")
    shift_template_id: Optional[int] = None
    ot_basis: str = Field(
        "beyond_shift_hours",
        pattern="^(beyond_shift_hours|beyond_threshold)$",
    )
    daily_threshold_hours: Optional[float] = Field(None, gt=0.0, le=24.0)
    ot_rate_multiplier: float = Field(1.5, gt=0.0, le=10.0)
    weekly_off_multiplier: float = Field(2.0, gt=0.0, le=10.0)
    holiday_multiplier: float = Field(2.0, gt=0.0, le=10.0)
    min_ot_minutes: int = Field(30, ge=0, le=12 * 60)
    daily_ot_cap_minutes: int = Field(240, ge=0, le=12 * 60)
    monthly_ot_cap_minutes: Optional[int] = Field(None, ge=0, le=200 * 60)
    rounding_minutes: int = Field(30, ge=1, le=60)
    requires_approval: bool = True
    is_active: bool = True

    @model_validator(mode="after")
    def _consistency(self):
        if self.scope == "shift" and self.shift_template_id is None:
            raise ValueError("shift_template_id is required when scope='shift'")
        if self.scope == "org_default" and self.shift_template_id is not None:
            raise ValueError("shift_template_id must be null when scope='org_default'")
        if (
            self.ot_basis == "beyond_threshold"
            and self.daily_threshold_hours is None
        ):
            raise ValueError(
                "daily_threshold_hours is required when ot_basis='beyond_threshold'"
            )
        return self


class OvertimeRuleCreate(OvertimeRuleBase):
    pass


class OvertimeRuleUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    scope: Optional[str] = Field(None, pattern="^(org_default|shift)$")
    shift_template_id: Optional[int] = None
    ot_basis: Optional[str] = Field(
        None, pattern="^(beyond_shift_hours|beyond_threshold)$"
    )
    daily_threshold_hours: Optional[float] = Field(None, gt=0.0, le=24.0)
    ot_rate_multiplier: Optional[float] = Field(None, gt=0.0, le=10.0)
    weekly_off_multiplier: Optional[float] = Field(None, gt=0.0, le=10.0)
    holiday_multiplier: Optional[float] = Field(None, gt=0.0, le=10.0)
    min_ot_minutes: Optional[int] = Field(None, ge=0, le=12 * 60)
    daily_ot_cap_minutes: Optional[int] = Field(None, ge=0, le=12 * 60)
    monthly_ot_cap_minutes: Optional[int] = Field(None, ge=0, le=200 * 60)
    rounding_minutes: Optional[int] = Field(None, ge=1, le=60)
    requires_approval: Optional[bool] = None
    is_active: Optional[bool] = None


class OvertimeRuleRead(OvertimeRuleBase):
    id: int
    created_at: datetime
    updated_at: datetime
    created_by_id: Optional[int] = None
    shift_template_name: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


# ----- NightShiftAllowanceRule --------------------------------------


class NightRuleBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    scope: str = Field("org_default", pattern="^(org_default|shift)$")
    shift_template_id: Optional[int] = None
    payout_model: str = Field("flat", pattern="^(flat|hourly)$")
    flat_amount: float = Field(0.0, ge=0.0)
    hourly_rate: float = Field(0.0, ge=0.0)
    night_window_start: time
    night_window_end: time
    min_night_minutes: int = Field(60, ge=0, le=12 * 60)
    is_active: bool = True

    @model_validator(mode="after")
    def _consistency(self):
        if self.scope == "shift" and self.shift_template_id is None:
            raise ValueError("shift_template_id is required when scope='shift'")
        if self.scope == "org_default" and self.shift_template_id is not None:
            raise ValueError("shift_template_id must be null when scope='org_default'")
        if self.payout_model == "flat" and self.flat_amount <= 0:
            raise ValueError("flat_amount must be > 0 when payout_model='flat'")
        if self.payout_model == "hourly" and self.hourly_rate <= 0:
            raise ValueError("hourly_rate must be > 0 when payout_model='hourly'")
        if self.night_window_start == self.night_window_end:
            raise ValueError("night_window_start and night_window_end cannot be equal")
        return self


class NightRuleCreate(NightRuleBase):
    pass


class NightRuleUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    scope: Optional[str] = Field(None, pattern="^(org_default|shift)$")
    shift_template_id: Optional[int] = None
    payout_model: Optional[str] = Field(None, pattern="^(flat|hourly)$")
    flat_amount: Optional[float] = Field(None, ge=0.0)
    hourly_rate: Optional[float] = Field(None, ge=0.0)
    night_window_start: Optional[time] = None
    night_window_end: Optional[time] = None
    min_night_minutes: Optional[int] = Field(None, ge=0, le=12 * 60)
    is_active: Optional[bool] = None


class NightRuleRead(NightRuleBase):
    id: int
    created_at: datetime
    updated_at: datetime
    created_by_id: Optional[int] = None
    shift_template_name: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


# ----- entries ------------------------------------------------------


class OvertimeEntryRead(BaseModel):
    id: int
    user_id: int
    work_date: date
    attendance_id: Optional[int]
    shift_template_id: Optional[int]
    rule_id: Optional[int]
    ot_minutes: int
    ot_amount: float
    hourly_rate_used: float
    multiplier_used: float
    day_type: str
    status: str
    approver_id: Optional[int]
    approved_at: Optional[datetime]
    approval_item_id: Optional[int]
    rejection_reason: Optional[str]
    payroll_run_id: Optional[int]
    computed_at: datetime
    updated_at: datetime
    # enrichment
    user_full_name: Optional[str] = None
    shift_template_name: Optional[str] = None
    worked_hours: Optional[float] = None
    model_config = ConfigDict(from_attributes=True)


class OvertimeActionRequest(BaseModel):
    """HR/manager action on an OT entry."""
    action: str = Field(..., pattern="^(approve|reject)$")
    comment: Optional[str] = Field(None, max_length=500)


class NightAllowanceEntryRead(BaseModel):
    id: int
    user_id: int
    work_date: date
    attendance_id: Optional[int]
    rule_id: Optional[int]
    night_minutes: int
    amount: float
    payout_model_used: str
    payroll_run_id: Optional[int]
    computed_at: datetime
    updated_at: datetime
    user_full_name: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


# ----- recompute / summary ------------------------------------------


class RecomputeRequest(BaseModel):
    start_date: date
    end_date: date
    user_ids: Optional[List[int]] = None  # None = all employees

    @model_validator(mode="after")
    def _date_order(self):
        if self.end_date < self.start_date:
            raise ValueError("end_date cannot be before start_date")
        return self


class RecomputeResult(BaseModel):
    period_start: date
    period_end: date
    ot_entries_created: int
    ot_entries_updated: int
    ot_entries_skipped_finalized: int
    night_entries_created: int
    night_entries_updated: int
    night_entries_skipped_finalized: int


class OvertimeMonthlySummary(BaseModel):
    user_id: int
    user_full_name: Optional[str] = None
    department: Optional[str] = None
    month: int
    year: int
    total_ot_minutes: int
    total_ot_amount: float
    approved_minutes: int
    approved_amount: float
    pending_minutes: int
    pending_amount: float
    rejected_minutes: int
    rejected_amount: float
    night_minutes: int
    night_amount: float
