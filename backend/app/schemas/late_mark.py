from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class LateMarkRuleBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    scope: str = Field(default="org_default", pattern="^(org_default|shift)$")
    shift_template_id: Optional[int] = None
    grace_minutes: int = Field(default=10, ge=0, le=240)
    lates_per_deduction: int = Field(default=3, ge=1, le=60)
    deduction_days_per_block: float = Field(default=1.0, gt=0, le=31)
    # Cascade tiers (paid leave types absorbed before LOP). None = straight to LOP.
    first_leave_type_id: Optional[int] = None
    second_leave_type_id: Optional[int] = None
    is_active: bool = True


class LateMarkRuleCreate(LateMarkRuleBase):
    pass


class LateMarkRuleUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    scope: Optional[str] = Field(default=None, pattern="^(org_default|shift)$")
    shift_template_id: Optional[int] = None
    grace_minutes: Optional[int] = Field(default=None, ge=0, le=240)
    lates_per_deduction: Optional[int] = Field(default=None, ge=1, le=60)
    deduction_days_per_block: Optional[float] = Field(default=None, gt=0, le=31)
    first_leave_type_id: Optional[int] = None
    second_leave_type_id: Optional[int] = None
    is_active: Optional[bool] = None


class LateMarkRuleRead(LateMarkRuleBase):
    id: int
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class LateMarkDeductionRead(BaseModel):
    id: int
    user_id: int
    full_name: Optional[str] = None
    year: int
    month: int
    late_count: int
    deducted_days: float
    cl_days: float
    pl_days: float
    lop_days: float
    payroll_run_id: Optional[int] = None
    model_config = ConfigDict(from_attributes=True)
