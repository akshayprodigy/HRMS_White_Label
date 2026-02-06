from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class OrganizationPublic(ORMModel):
    id: int
    code: str
    name: str
    is_active: bool
    created_at: dt.datetime
    updated_at: dt.datetime


class OrganizationCreate(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=255)
    is_active: bool = True


class OrganizationUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=50)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    is_active: bool | None = None


class SitePublic(ORMModel):
    id: int
    organization_id: int
    code: str
    name: str
    is_active: bool
    created_at: dt.datetime
    updated_at: dt.datetime


class SiteCreate(BaseModel):
    organization_id: int
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=255)
    is_active: bool = True


class SiteUpdate(BaseModel):
    organization_id: int | None = None
    code: str | None = Field(default=None, min_length=1, max_length=50)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    is_active: bool | None = None


class ProjectPublic(ORMModel):
    id: int
    organization_id: int
    site_id: int | None = None
    code: str
    name: str
    is_active: bool
    created_at: dt.datetime
    updated_at: dt.datetime


class ProjectCreate(BaseModel):
    organization_id: int
    site_id: int | None = None
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=255)
    is_active: bool = True


class ProjectUpdate(BaseModel):
    organization_id: int | None = None
    site_id: int | None = None
    code: str | None = Field(default=None, min_length=1, max_length=50)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    is_active: bool | None = None


class CostCenterPublic(ORMModel):
    id: int
    organization_id: int
    code: str
    name: str
    is_active: bool
    created_at: dt.datetime
    updated_at: dt.datetime


class CostCenterCreate(BaseModel):
    organization_id: int
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=255)
    is_active: bool = True


class CostCenterUpdate(BaseModel):
    organization_id: int | None = None
    code: str | None = Field(default=None, min_length=1, max_length=50)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    is_active: bool | None = None
