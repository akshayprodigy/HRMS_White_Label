"""Roster planner DTOs (W7)."""
from datetime import date as pydate
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


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


class RosterEntryInput(BaseModel):
    employee_id: int  # user id
    work_date: pydate
    shift_template_id: Optional[int] = None
    is_week_off: bool = False


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

    model_config = ConfigDict(from_attributes=True)


class RosterEntryUpdate(BaseModel):
    shift_template_id: Optional[int] = None
    is_week_off: Optional[bool] = None
    status: Optional[str] = None
    note: Optional[str] = None


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
