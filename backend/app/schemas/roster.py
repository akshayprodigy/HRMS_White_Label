"""Roster planner DTOs (W7)."""
from datetime import date as pydate, datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator


class RosterCell(BaseModel):
    work_date: pydate
    shift_template_id: Optional[int] = None
    is_week_off: bool = False
    status: Optional[str] = None
    entry_id: Optional[int] = None
    # Display-only fallback source when there is no RosterEntry for the cell:
    # 'roster' | 'assignment' | 'default' | 'empty'.
    source: str = "empty"
    shift_name: Optional[str] = None


class RosterGridRow(BaseModel):
    employee_id: int  # user id
    full_name: Optional[str] = None
    department: Optional[str] = None
    designation: Optional[str] = None
    in_scope: bool = True
    cells: List[RosterCell] = Field(default_factory=list)


class ShiftTemplateLite(BaseModel):
    id: int
    name: str
    start_time: str
    end_time: str
    is_overnight: bool = False

    model_config = ConfigDict(from_attributes=True)


class RosterGridResponse(BaseModel):
    start: pydate
    end: pydate
    dates: List[pydate]
    shift_templates: List[ShiftTemplateLite]
    rows: List[RosterGridRow]
    is_admin: bool = False
    can_publish: bool = False


class RosterEntryInput(BaseModel):
    employee_id: int  # user id
    work_date: pydate
    shift_template_id: Optional[int] = None
    is_week_off: bool = False
    status: str = "published"  # back-compat default; may be downgraded
    reason: Optional[str] = Field(default=None, max_length=500)

    @field_validator("status")
    @classmethod
    def _status(cls, v: str) -> str:
        if v not in ("draft", "published"):
            raise ValueError("status must be 'draft' or 'published'")
        return v


class RosterBulkRequest(BaseModel):
    employee_ids: Optional[List[int]] = None  # None => whole scoped team
    department: Optional[str] = None
    start: pydate
    end: pydate
    status: str = "published"
    overwrite: bool = True
    # EXACTLY ONE of pattern | entries.
    # pattern: weekday int (Mon=0..Sun=6) -> template_id | None (None=week-off)
    pattern: Optional[Dict[int, Optional[int]]] = None
    entries: Optional[List[RosterEntryInput]] = None

    @field_validator("status")
    @classmethod
    def _status(cls, v: str) -> str:
        if v not in ("draft", "published"):
            raise ValueError("status must be 'draft' or 'published'")
        return v

    @model_validator(mode="after")
    def _check(self) -> "RosterBulkRequest":
        if self.start > self.end:
            raise ValueError("start must be <= end")
        if (self.end - self.start).days > 62:
            raise ValueError("range too large (max 62 days)")
        has_pattern = self.pattern is not None
        has_entries = self.entries is not None
        if has_pattern == has_entries:
            raise ValueError("provide exactly one of 'pattern' or 'entries'")
        return self


class RosterBulkResult(BaseModel):
    created: int = 0
    updated: int = 0
    skipped: int = 0
    out_of_scope: List[int] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)


class RosterEntryRead(BaseModel):
    id: int
    employee_id: int
    work_date: pydate
    shift_template_id: Optional[int] = None
    is_week_off: bool
    status: str
    note: Optional[str] = None
    assigned_by_id: Optional[int] = None
    employee_name: Optional[str] = None
    shift_template_name: Optional[str] = None
    shift_start: Optional[str] = None
    shift_end: Optional[str] = None
    notice: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class RosterEntryUpdate(BaseModel):
    shift_template_id: Optional[int] = None
    is_week_off: Optional[bool] = None
    status: Optional[str] = None
    note: Optional[str] = None
    reason: Optional[str] = Field(default=None, max_length=500)


class RosterChangeRequestCreate(BaseModel):
    work_date: pydate
    requested_shift_template_id: Optional[int] = None
    requested_week_off: bool = False
    reason: str = Field(..., min_length=5, max_length=500)


class RosterChangeDecision(BaseModel):
    action: str = Field(..., pattern="^(approve|reject)$")
    decision_note: Optional[str] = Field(default=None, max_length=500)


class RosterChangeRequestRead(BaseModel):
    id: int
    employee_id: int
    work_date: pydate
    current_shift_template_id: Optional[int] = None
    requested_shift_template_id: Optional[int] = None
    requested_week_off: bool
    reason: str
    status: str
    decided_by_id: Optional[int] = None
    decided_at: Optional[str] = None
    decision_note: Optional[str] = None
    employee_name: Optional[str] = None
    current_shift_name: Optional[str] = None
    requested_shift_name: Optional[str] = None
    decided_by_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class RotationPatternBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    description: Optional[str] = Field(default=None, max_length=255)
    cycle: List[Optional[StrictInt]] = Field(..., min_length=1, max_length=56)


class RotationPatternCreate(RotationPatternBase):
    pass


class RotationPatternUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    description: Optional[str] = Field(default=None, max_length=255)
    cycle: Optional[List[Optional[StrictInt]]] = Field(
        default=None, min_length=1, max_length=56
    )
    is_active: Optional[bool] = None


class RotationPatternRead(RotationPatternBase):
    id: int
    is_active: bool
    created_by_id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class RotationApplyRequest(BaseModel):
    employee_ids: Optional[List[int]] = None  # None => whole scoped team
    department: Optional[str] = None
    start: pydate
    end: pydate
    anchor: pydate
    offsets: Optional[Dict[int, int]] = None  # user id -> offset
    default_offset: int = Field(default=0, ge=-1000, le=1000)
    overwrite: bool = True
    status: str = "draft"

    @field_validator("status")
    @classmethod
    def _status(cls, v: str) -> str:
        if v not in ("draft", "published"):
            raise ValueError("status must be 'draft' or 'published'")
        return v

    @field_validator("offsets")
    @classmethod
    def _offsets(cls, v):
        if v and any(abs(o) > 1000 for o in v.values()):
            raise ValueError("offsets must be within -1000..1000")
        return v

    @model_validator(mode="after")
    def _check(self) -> "RotationApplyRequest":
        if self.start > self.end:
            raise ValueError("start must be <= end")
        if (self.end - self.start).days > 62:
            raise ValueError("range too large (max 62 days)")
        return self


# ---- work-rule insights + coverage requirements (Phase 1A) ----

class ViolationRead(BaseModel):
    user_id: int
    employee_name: Optional[str] = None
    work_date: pydate
    rule: str
    message: str


class CoverageCellRead(BaseModel):
    date: pydate
    shift_template_id: int
    shift_name: Optional[str] = None
    department: Optional[str] = None
    location: Optional[str] = None
    required_min: int
    required_max: Optional[int] = None
    scheduled: int
    status: str


class RosterInsightsResponse(BaseModel):
    violations: List[ViolationRead] = Field(default_factory=list)
    coverage: List[CoverageCellRead] = Field(default_factory=list)


class CoverageRequirementBase(BaseModel):
    department: Optional[str] = Field(default=None, max_length=100)
    location: Optional[str] = Field(default=None, max_length=100)
    shift_template_id: StrictInt
    weekday: Optional[StrictInt] = Field(default=None, ge=0, le=6)
    min_headcount: StrictInt = Field(..., ge=0)
    max_headcount: Optional[StrictInt] = Field(default=None, ge=0)


class CoverageRequirementCreate(CoverageRequirementBase):
    @model_validator(mode="after")
    def _max_ge_min(self):
        if (self.max_headcount is not None
                and self.max_headcount < self.min_headcount):
            raise ValueError("max_headcount must be >= min_headcount")
        return self


class CoverageRequirementUpdate(BaseModel):
    department: Optional[str] = Field(default=None, max_length=100)
    location: Optional[str] = Field(default=None, max_length=100)
    shift_template_id: Optional[StrictInt] = None
    weekday: Optional[StrictInt] = Field(default=None, ge=0, le=6)
    min_headcount: Optional[StrictInt] = Field(default=None, ge=0)
    max_headcount: Optional[StrictInt] = Field(default=None, ge=0)
    is_active: Optional[bool] = None


class CoverageRequirementRead(CoverageRequirementBase):
    id: int
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


# ---------------- publish lifecycle / history / copy ----------------

class RosterPublishBody(BaseModel):
    start: pydate
    end: pydate
    department: Optional[str] = Field(default=None, max_length=100)
    employee_ids: Optional[List[int]] = None


class RosterPublishResult(BaseModel):
    published: int = 0
    employees: int = 0
    not_permitted: List[int] = Field(default_factory=list)


class PublishRequestCreate(RosterPublishBody):
    note: Optional[str] = Field(default=None, max_length=500)


class PublishRequestDecision(BaseModel):
    approve: bool
    note: Optional[str] = Field(default=None, max_length=500)


class PublishRequestRead(BaseModel):
    id: int
    requested_by_id: int
    requester_name: Optional[str] = None
    start: pydate
    end: pydate
    department: Optional[str] = None
    employee_ids: List[int] = Field(default_factory=list)
    note: Optional[str] = None
    status: str
    decided_by_id: Optional[int] = None
    decided_at: Optional[datetime] = None
    decision_note: Optional[str] = None
    created_at: datetime
    draft_count: Optional[int] = None
    publish_result: Optional[RosterPublishResult] = None
    message: Optional[str] = None


class RosterCopyRequest(BaseModel):
    source_start: pydate
    source_end: pydate
    target_start: pydate
    department: Optional[str] = Field(default=None, max_length=100)
    employee_ids: Optional[List[int]] = None
    overwrite: bool = False


class RosterHistoryRead(BaseModel):
    id: int
    employee_id: int
    employee_name: Optional[str] = None
    work_date: pydate
    old_shift_template_id: Optional[int] = None
    old_shift_name: Optional[str] = None
    old_is_week_off: bool = False
    new_shift_template_id: Optional[int] = None
    new_shift_name: Optional[str] = None
    new_is_week_off: bool = False
    action: str
    reason: Optional[str] = None
    changed_by_id: Optional[int] = None
    changed_by_name: Optional[str] = None
    changed_at: datetime
