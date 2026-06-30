"""Pydantic schemas for Designation/Grade master, SalaryRevision +
RevisionCycle APIs."""
from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ----- Grade ---------------------------------------------------------


class GradeBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=40)
    rank: int = Field(0, ge=0, le=999)
    min_salary: Optional[float] = Field(None, ge=0)
    max_salary: Optional[float] = Field(None, ge=0)
    is_active: bool = True

    @model_validator(mode="after")
    def _band(self):
        if (
            self.min_salary is not None
            and self.max_salary is not None
            and self.max_salary < self.min_salary
        ):
            raise ValueError("max_salary cannot be less than min_salary")
        return self


class GradeCreate(GradeBase):
    pass


class GradeUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=40)
    rank: Optional[int] = Field(None, ge=0, le=999)
    min_salary: Optional[float] = Field(None, ge=0)
    max_salary: Optional[float] = Field(None, ge=0)
    is_active: Optional[bool] = None


class GradeRead(GradeBase):
    id: int
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


# ----- Designation ---------------------------------------------------


class DesignationBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    grade_id: Optional[int] = None
    is_active: bool = True


class DesignationCreate(DesignationBase):
    pass


class DesignationUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=120)
    grade_id: Optional[int] = None
    is_active: Optional[bool] = None


class DesignationRead(DesignationBase):
    id: int
    grade_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


# ----- RevisionCycle -------------------------------------------------


class CycleBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=160)
    effective_from: date
    budget_hike_amount: Optional[float] = Field(None, ge=0)
    notes: Optional[str] = None


class CycleCreate(CycleBase):
    pass


class CycleUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=160)
    effective_from: Optional[date] = None
    budget_hike_amount: Optional[float] = Field(None, ge=0)
    notes: Optional[str] = None


class CycleRead(CycleBase):
    id: int
    status: str
    created_at: datetime
    updated_at: datetime
    # plan-vs-actual summary
    total_revisions: int = 0
    total_hike_amount: float = 0.0
    avg_hike_percent: float = 0.0
    by_status: dict = Field(default_factory=dict)
    model_config = ConfigDict(from_attributes=True)


class CycleBulkDraftRequest(BaseModel):
    """Generate one DRAFT revision per target employee.

    Provide exactly one of `employee_ids` or `department`. Optional
    blanket hike, can be overridden per-row later in the workspace.
    """
    employee_ids: Optional[List[int]] = None
    department: Optional[str] = Field(None, min_length=1)
    revision_type: str = Field(
        "increment",
        pattern="^(increment|promotion|correction|demotion)$",
    )
    blanket_hike_percent: Optional[float] = Field(None, ge=-50, le=200)
    blanket_hike_amount: Optional[float] = None
    reason: Optional[str] = None

    @model_validator(mode="after")
    def _exactly_one_target(self):
        has_ids = bool(self.employee_ids)
        has_dept = bool(self.department)
        if has_ids == has_dept:
            raise ValueError("Provide exactly one of employee_ids or department")
        return self


class CycleBulkSubmitRequest(BaseModel):
    """Move every DRAFT revision in the cycle to PENDING for approval."""
    only_revision_ids: Optional[List[int]] = None


class BulkActionResult(BaseModel):
    affected: int
    skipped: int
    errors: List[str] = Field(default_factory=list)


# ----- SalaryRevision -----------------------------------------------


class SalaryRevisionBase(BaseModel):
    employee_id: int
    revision_type: str = Field(
        "increment",
        pattern="^(increment|promotion|correction|demotion)$",
    )
    effective_from: date
    reason: Optional[str] = None

    new_designation_id: Optional[int] = None
    new_grade_id: Optional[int] = None
    new_basic: float = Field(0.0, ge=0)
    new_conveyance: float = Field(0.0, ge=0)
    new_hra: float = Field(0.0, ge=0)
    new_other_allowance: float = Field(0.0, ge=0)
    new_ctc: float = Field(0.0, ge=0)

    cycle_id: Optional[int] = None


class SalaryRevisionCreate(SalaryRevisionBase):
    pass


class SalaryRevisionUpdate(BaseModel):
    revision_type: Optional[str] = Field(
        None,
        pattern="^(increment|promotion|correction|demotion)$",
    )
    effective_from: Optional[date] = None
    reason: Optional[str] = None
    new_designation_id: Optional[int] = None
    new_grade_id: Optional[int] = None
    new_basic: Optional[float] = Field(None, ge=0)
    new_conveyance: Optional[float] = Field(None, ge=0)
    new_hra: Optional[float] = Field(None, ge=0)
    new_other_allowance: Optional[float] = Field(None, ge=0)
    new_ctc: Optional[float] = Field(None, ge=0)


class SalaryRevisionRead(BaseModel):
    id: int
    employee_id: int
    cycle_id: Optional[int]
    revision_type: str
    effective_from: date
    reason: Optional[str] = None
    status: str

    old_designation_id: Optional[int]
    new_designation_id: Optional[int]
    old_grade_id: Optional[int]
    new_grade_id: Optional[int]
    old_basic: float
    old_conveyance: float
    old_hra: float
    old_other_allowance: float
    old_ctc: float
    new_basic: float
    new_conveyance: float
    new_hra: float
    new_other_allowance: float
    new_ctc: float
    hike_amount: float
    hike_percent: float
    band_warning: Optional[str] = None

    approval_item_id: Optional[int] = None
    rejected_reason: Optional[str] = None
    applied_at: Optional[datetime] = None
    applied_by_id: Optional[int] = None
    letter_id: Optional[int] = None
    arrears_run_id: Optional[int] = None
    arrears_amount: float
    arrears_months: int

    created_at: datetime
    updated_at: datetime

    # enrichment
    employee_full_name: Optional[str] = None
    employee_code: Optional[str] = None
    department: Optional[str] = None
    old_designation_title: Optional[str] = None
    new_designation_title: Optional[str] = None
    old_grade_name: Optional[str] = None
    new_grade_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ActionRequest(BaseModel):
    action: str = Field(..., pattern="^(approve|reject|cancel)$")
    comment: Optional[str] = Field(None, max_length=500)


class ApplyDueResult(BaseModel):
    as_of: date
    applied: int
    skipped: int
    errors: List[str] = Field(default_factory=list)


class CompensationHistoryEntry(BaseModel):
    revision_id: int
    effective_from: date
    revision_type: str
    status: str
    old_designation_title: Optional[str]
    new_designation_title: Optional[str]
    old_ctc: float
    new_ctc: float
    hike_amount: float
    hike_percent: float
    applied_at: Optional[datetime]
    letter_id: Optional[int]
