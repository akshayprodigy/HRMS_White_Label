"""Scheduling delegation DTOs (Roadmap v2 Phase 1A)."""
from datetime import date as pydate, datetime
from typing import Annotated, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.datetime_utils import as_utc

IntId = Annotated[int, Field(ge=1, le=2**31 - 1)]


class DelegationCreate(BaseModel):
    grantee_id: IntId
    scope_type: str
    scope_value: Optional[str] = Field(None, max_length=100)
    employee_ids: List[IntId] = Field(default_factory=list)
    can_publish: bool = False
    can_approve_changes: bool = False
    can_emergency_override: bool = False
    valid_from: pydate
    valid_to: Optional[pydate] = None
    note: Optional[str] = Field(None, max_length=255)


class DelegationUpdate(BaseModel):
    can_publish: Optional[bool] = None
    can_approve_changes: Optional[bool] = None
    can_emergency_override: Optional[bool] = None
    valid_from: Optional[pydate] = None
    valid_to: Optional[pydate] = None
    note: Optional[str] = Field(None, max_length=255)


class DelegationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    grantee_id: int
    grantee_name: Optional[str] = None
    scope_type: str
    scope_value: Optional[str] = None
    employee_ids: List[int] = Field(default_factory=list)
    can_publish: bool
    can_approve_changes: bool
    can_emergency_override: bool = False
    valid_from: pydate
    valid_to: Optional[pydate] = None
    revoked_at: Optional[datetime] = None
    granted_by_id: Optional[int] = None
    granted_by_name: Optional[str] = None
    note: Optional[str] = None
    created_at: Optional[datetime] = None
    covered_count: int = 0

    @field_validator("revoked_at", "created_at", mode="after")
    @classmethod
    def _utc(cls, v):
        return as_utc(v)


class DelegationPreviewRow(BaseModel):
    user_id: int
    full_name: Optional[str] = None
    department: Optional[str] = None
