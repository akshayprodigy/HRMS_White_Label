from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class EmploymentTypeBase(BaseModel):
    code: str = Field(..., min_length=1, max_length=20)
    name: str = Field(..., min_length=1, max_length=60)
    is_on_payroll: bool = True
    statutory_enabled: bool = True
    flat_tds_rate: Optional[float] = None
    is_active: bool = True


class EmploymentTypeCreate(EmploymentTypeBase):
    pass


class EmploymentTypeUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=60)
    is_on_payroll: Optional[bool] = None
    statutory_enabled: Optional[bool] = None
    flat_tds_rate: Optional[float] = None
    is_active: Optional[bool] = None


class EmploymentTypeRead(EmploymentTypeBase):
    id: int
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)
