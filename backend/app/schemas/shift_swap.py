from datetime import date as pydate, datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from app.core.datetime_utils import as_utc
from app.schemas.roster import IntId


class SwapCreate(BaseModel):
    counterparty_id: IntId
    requester_date: pydate
    counterparty_date: Optional[pydate] = None
    reason: Optional[str] = Field(default=None, max_length=500)


class SwapDecision(BaseModel):
    action: str
    note: Optional[str] = Field(default=None, max_length=500)

    @field_validator("action")
    @classmethod
    def _action(cls, v: str) -> str:
        if v not in ("approve", "reject"):
            raise ValueError("action must be 'approve' or 'reject'")
        return v


class SwapCellRead(BaseModel):
    shift_template_id: Optional[int] = None
    shift_name: Optional[str] = None
    is_week_off: bool = False


class SwapExchangedCell(BaseModel):
    user_id: int
    work_date: pydate
    before: SwapCellRead
    after: SwapCellRead


class SwapViolationRead(BaseModel):
    user_id: int
    employee_name: Optional[str] = None
    work_date: pydate
    rule: str
    message: str


class SwapRead(BaseModel):
    id: int
    requester_id: int
    requester_name: Optional[str] = None
    counterparty_id: int
    counterparty_name: Optional[str] = None
    requester_date: pydate
    counterparty_date: pydate
    reason: Optional[str] = None
    status: str
    # requester's shift on requester_date / counterparty's on counterparty_date
    requester_cell: Optional[SwapCellRead] = None
    counterparty_cell: Optional[SwapCellRead] = None
    peer_responded_at: Optional[datetime] = None
    decided_by_id: Optional[int] = None
    decided_by_name: Optional[str] = None
    decided_at: Optional[datetime] = None
    decision_note: Optional[str] = None
    created_at: Optional[datetime] = None
    cells: List[SwapExchangedCell] = []
    warnings: List[SwapViolationRead] = []
    # Relative to the caller; only set on /swaps/my.
    direction: Optional[str] = None

    @field_validator("peer_responded_at", "decided_at", "created_at")
    @classmethod
    def _utc(cls, v):
        return as_utc(v)


class SwapCandidate(BaseModel):
    user_id: int
    name: Optional[str] = None
    shift_template_id: Optional[int] = None
    shift_name: Optional[str] = None
    is_week_off: bool = False
