"""Scheduling delegation DTOs (Roadmap v2 Phase 1A)."""
from datetime import date as pydate, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class DelegationCreate(BaseModel):
    grantee_id: int
    scope_type: str
    scope_value: Optional[str] = Field(None, max_length=100)
    employee_ids: List[int] = Field(default_factory=list)
    can_publish: bool = False
    can_approve_changes: bool = False
    valid_from: pydate
    valid_to: Optional[pydate] = None
    note: Optional[str] = Field(None, max_length=255)


class DelegationUpdate(BaseModel):
    can_publish: Optional[bool] = None
    can_approve_changes: Optional[bool] = None
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
    valid_from: pydate
    valid_to: Optional[pydate] = None
    revoked_at: Optional[datetime] = None
    granted_by_id: Optional[int] = None
    granted_by_name: Optional[str] = None
    note: Optional[str] = None
    created_at: Optional[datetime] = None
    covered_count: int = 0


class DelegationPreviewRow(BaseModel):
    user_id: int
    full_name: Optional[str] = None
    department: Optional[str] = None
