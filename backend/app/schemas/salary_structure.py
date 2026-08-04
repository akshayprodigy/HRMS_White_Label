from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------- Salary Component ----------

class SalaryComponentBase(BaseModel):
    code: str = Field(..., min_length=1, max_length=30)
    name: str = Field(..., min_length=1, max_length=80)
    component_type: str = Field(default="earning", pattern="^(earning|deduction)$")
    slot: Optional[str] = Field(default=None, max_length=20)
    default_calc_method: str = Field(default="flat", pattern="^(flat|percent_of_basic)$")
    default_percent: Optional[float] = None
    is_taxable: bool = True
    display_order: int = 0
    is_active: bool = True


class SalaryComponentCreate(SalaryComponentBase):
    pass


class SalaryComponentUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    component_type: Optional[str] = Field(default=None, pattern="^(earning|deduction)$")
    slot: Optional[str] = Field(default=None, max_length=20)
    default_calc_method: Optional[str] = Field(default=None, pattern="^(flat|percent_of_basic)$")
    default_percent: Optional[float] = None
    is_taxable: Optional[bool] = None
    display_order: Optional[int] = None
    is_active: Optional[bool] = None


class SalaryComponentRead(SalaryComponentBase):
    id: int
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


# ---------- Salary Template Component (line) ----------

class SalaryTemplateComponentBase(BaseModel):
    component_id: int
    calc_method: str = Field(default="flat", pattern="^(flat|percent_of_basic)$")
    value: Optional[float] = None
    percent: Optional[float] = None
    display_order: int = 0


class SalaryTemplateComponentRead(SalaryTemplateComponentBase):
    id: int
    template_id: int
    model_config = ConfigDict(from_attributes=True)


# ---------- Salary Template ----------

class SalaryTemplateBase(BaseModel):
    code: str = Field(..., min_length=1, max_length=30)
    name: str = Field(..., min_length=1, max_length=80)
    description: Optional[str] = Field(default=None, max_length=255)
    is_active: bool = True


class SalaryTemplateCreate(SalaryTemplateBase):
    # Optional inline lines on create.
    components: List[SalaryTemplateComponentBase] = Field(default_factory=list)


class SalaryTemplateUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    description: Optional[str] = Field(default=None, max_length=255)
    is_active: Optional[bool] = None


class SalaryTemplateRead(SalaryTemplateBase):
    id: int
    created_at: datetime
    updated_at: datetime
    components: List[SalaryTemplateComponentRead] = Field(default_factory=list)
    model_config = ConfigDict(from_attributes=True)
