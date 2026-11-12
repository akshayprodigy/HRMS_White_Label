from datetime import date as pydate, datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from app.core.datetime_utils import as_utc
from app.schemas.roster import IntId


class OpenShiftCreate(BaseModel):
    work_date: pydate
    shift_template_id: IntId
    department: Optional[str] = Field(default=None, max_length=100)
    location: Optional[str] = Field(default=None, max_length=100)
    slots: int = Field(default=1, ge=1, le=50)
    note: Optional[str] = Field(default=None, max_length=255)
    auto_confirm: bool = False

    @field_validator("department", "location", "note")
    @classmethod
    def _blank(cls, v):
        v = (v or "").strip()
        return v or None


class ClaimDecision(BaseModel):
    action: str

    @field_validator("action")
    @classmethod
    def _action(cls, v: str) -> str:
        if v not in ("approve", "reject"):
            raise ValueError("action must be 'approve' or 'reject'")
        return v


class OpenShiftClaimRead(BaseModel):
    id: int
    open_shift_id: int
    user_id: int
    user_name: Optional[str] = None
    status: str
    decided_by_id: Optional[int] = None
    decided_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    # Why the claimant could not be confirmed right now (pending claims only).
    eligibility_reason: Optional[str] = None

    @field_validator("decided_at", "created_at")
    @classmethod
    def _utc(cls, v):
        return as_utc(v)


class OpenShiftRead(BaseModel):
    id: int
    work_date: pydate
    shift_template_id: int
    shift_name: Optional[str] = None
    shift_start: Optional[str] = None
    shift_end: Optional[str] = None
    department: Optional[str] = None
    location: Optional[str] = None
    slots: int
    filled: int
    note: Optional[str] = None
    status: str
    auto_confirm: bool
    created_by_id: Optional[int] = None
    created_by_name: Optional[str] = None
    source_drop_id: Optional[int] = None
    created_at: Optional[datetime] = None
    my_claim_id: Optional[int] = None
    my_claim_status: Optional[str] = None
    claims: List[OpenShiftClaimRead] = []

    @field_validator("created_at")
    @classmethod
    def _utc(cls, v):
        return as_utc(v)
