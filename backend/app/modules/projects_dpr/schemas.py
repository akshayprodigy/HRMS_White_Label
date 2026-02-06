from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class DprDrillingLineCreate(BaseModel):
    line_no: int = Field(ge=1)
    location: str | None = Field(default=None, max_length=255)
    meters_drilled: float = Field(gt=0)
    recovered_meters: float | None = Field(default=None, ge=0)


class DprActivityLineCreate(BaseModel):
    line_no: int = Field(ge=1)
    activity: str = Field(min_length=1, max_length=255)
    hours: float | None = Field(default=None, ge=0)
    remarks: str | None = Field(default=None, max_length=500)


class DprConsumptionLineCreate(BaseModel):
    line_no: int = Field(ge=1)
    item_id: int | None = None
    uom_id: int | None = None
    qty: float = Field(gt=0)
    remarks: str | None = Field(default=None, max_length=500)


class DprCreate(BaseModel):
    project_id: int
    dpr_date: dt.date
    shift: str | None = Field(default=None, max_length=20)
    remarks: str | None = Field(default=None, max_length=500)

    drilling_lines: list[DprDrillingLineCreate] = Field(min_length=1)
    activity_lines: list[DprActivityLineCreate] = Field(default_factory=list)
    consumption_lines: list[DprConsumptionLineCreate] = Field(
        default_factory=list
    )


class DprDrillingLinePublic(ORMModel):
    id: int
    header_id: int
    line_no: int
    location: str | None
    meters_drilled: float
    recovered_meters: float | None
    created_at: dt.datetime
    updated_at: dt.datetime


class DprActivityLinePublic(ORMModel):
    id: int
    header_id: int
    line_no: int
    activity: str
    hours: float | None
    remarks: str | None
    created_at: dt.datetime
    updated_at: dt.datetime


class DprConsumptionLinePublic(ORMModel):
    id: int
    header_id: int
    line_no: int
    item_id: int | None
    uom_id: int | None
    qty: float
    remarks: str | None
    created_at: dt.datetime
    updated_at: dt.datetime


class DprHeaderPublic(ORMModel):
    id: int
    project_id: int
    dpr_date: dt.date
    shift: str | None
    remarks: str | None
    created_at: dt.datetime
    updated_at: dt.datetime

    drilling_lines: list[DprDrillingLinePublic] = []
    activity_lines: list[DprActivityLinePublic] = []
    consumption_lines: list[DprConsumptionLinePublic] = []


class DprMetricsPublic(BaseModel):
    dpr_id: int
    meters_drilled_total: float
    recovered_meters_total: float
    recovery_percent: float


class DprListQuery(BaseModel):
    project_id: int | None = None
    date_from: dt.date | None = None
    date_to: dt.date | None = None
    include_lines: bool = False
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)
