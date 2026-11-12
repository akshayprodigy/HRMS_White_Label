from datetime import date as pydate, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.datetime_utils import as_utc
from app.schemas.roster import IntId


class AvailabilityCreate(BaseModel):
    kind: str
    weekday: Optional[int] = Field(default=None, ge=0, le=6)
    specific_date: Optional[pydate] = None
    shift_template_id: Optional[IntId] = None
    valid_from: Optional[pydate] = None
    valid_to: Optional[pydate] = None
    note: Optional[str] = Field(default=None, max_length=255)

    @field_validator("kind")
    @classmethod
    def _kind(cls, v: str) -> str:
        if v not in ("unavailable", "preferred"):
            raise ValueError("kind must be 'unavailable' or 'preferred'")
        return v


class AvailabilityUpdate(BaseModel):
    kind: Optional[str] = None
    weekday: Optional[int] = Field(default=None, ge=0, le=6)
    specific_date: Optional[pydate] = None
    shift_template_id: Optional[IntId] = None
    valid_from: Optional[pydate] = None
    valid_to: Optional[pydate] = None
    note: Optional[str] = Field(default=None, max_length=255)

    @field_validator("kind")
    @classmethod
    def _kind(cls, v):
        if v is not None and v not in ("unavailable", "preferred"):
            raise ValueError("kind must be 'unavailable' or 'preferred'")
        return v


class AvailabilityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    employee_name: Optional[str] = None
    kind: str
    weekday: Optional[int] = None
    specific_date: Optional[pydate] = None
    shift_template_id: Optional[int] = None
    valid_from: Optional[pydate] = None
    valid_to: Optional[pydate] = None
    note: Optional[str] = None
    created_at: Optional[datetime] = None

    @field_validator("created_at")
    @classmethod
    def _utc(cls, v):
        return as_utc(v)
