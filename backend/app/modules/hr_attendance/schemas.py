from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class AttendanceEntryCreate(BaseModel):
    employee_id: int
    project_id: int
    work_date: dt.date
    hours: float = Field(gt=0)
    hourly_rate: float = Field(ge=0)
    notes: str | None = Field(default=None, max_length=500)


class AttendanceEntryPublic(ORMModel):
    id: int
    employee_id: int
    project_id: int
    work_date: dt.date
    hours: float
    hourly_rate: float
    notes: str | None
    created_at: dt.datetime
    updated_at: dt.datetime


class AttendanceEntryListQuery(BaseModel):
    project_id: int | None = None
    employee_id: int | None = None
    date_from: dt.date | None = None
    date_to: dt.date | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)
