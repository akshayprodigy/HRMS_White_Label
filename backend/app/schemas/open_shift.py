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
    # False for the viewer's own claim unless they are a roster admin.
    can_decide: bool = True

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
    # caller may cancel it (creator or roster admin)
    can_cancel: bool = False
    created_by_id: Optional[int] = None
    created_by_name: Optional[str] = None
    source_drop_id: Optional[int] = None
    created_at: Optional[datetime] = None
    my_claim_id: Optional[int] = None
    my_claim_status: Optional[str] = None
    claims: List[OpenShiftClaimRead] = []
    warnings: List[str] = []

    @field_validator("created_at")
    @classmethod
    def _utc(cls, v):
        return as_utc(v)


class DropCreate(BaseModel):
    work_date: pydate
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def _reason(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3:
            raise ValueError("reason must be at least 3 characters")
        return v


class DropDecision(BaseModel):
    action: str
    note: Optional[str] = Field(default=None, max_length=500)
    # None = default (post when the approver is allowed to).
    post_open_shift: Optional[bool] = None

    @field_validator("action")
    @classmethod
    def _action(cls, v: str) -> str:
        if v not in ("approve", "reject"):
            raise ValueError("action must be 'approve' or 'reject'")
        return v


class DropRead(BaseModel):
    id: int
    user_id: int
    user_name: Optional[str] = None
    work_date: pydate
    shift_template_id: int
    shift_name: Optional[str] = None
    shift_start: Optional[str] = None
    shift_end: Optional[str] = None
    reason: str
    status: str
    post_open_shift: bool
    open_shift_id: Optional[int] = None
    # Set on the decide response when an open shift was wanted by default
    # but could not be posted.
    open_shift_skipped_reason: Optional[str] = None
    decided_by_id: Optional[int] = None
    decided_by_name: Optional[str] = None
    decided_at: Optional[datetime] = None
    decision_note: Optional[str] = None
    created_at: Optional[datetime] = None

    @field_validator("decided_at", "created_at")
    @classmethod
    def _utc(cls, v):
        return as_utc(v)
