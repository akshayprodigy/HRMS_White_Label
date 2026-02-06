from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ProjectDirectExpenseCreate(BaseModel):
    expense_date: dt.date
    category: str = Field(min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=255)
    amount: float = Field(gt=0)
    vendor: str | None = Field(default=None, max_length=255)
    reference_no: str | None = Field(default=None, max_length=80)
    notes: str | None = Field(default=None, max_length=500)


class ProjectDirectExpensePublic(ORMModel):
    id: int
    project_id: int
    expense_date: dt.date
    category: str
    description: str | None
    amount: float
    vendor: str | None
    reference_no: str | None
    notes: str | None
    created_at: dt.datetime
    updated_at: dt.datetime


class ProjectRevenueCreate(BaseModel):
    revenue_date: dt.date
    category: str = Field(min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=255)
    amount: float = Field(gt=0)
    client: str | None = Field(default=None, max_length=255)
    reference_no: str | None = Field(default=None, max_length=80)
    notes: str | None = Field(default=None, max_length=500)


class ProjectRevenuePublic(ORMModel):
    id: int
    project_id: int
    revenue_date: dt.date
    category: str
    description: str | None
    amount: float
    client: str | None
    reference_no: str | None
    notes: str | None
    created_at: dt.datetime
    updated_at: dt.datetime


class ProjectFinanceListQuery(BaseModel):
    date_from: dt.date | None = None
    date_to: dt.date | None = None
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)
