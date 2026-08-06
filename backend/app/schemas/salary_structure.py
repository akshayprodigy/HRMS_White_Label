from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ---------- Salary Component ----------

class SalaryComponentBase(BaseModel):
    code: str = Field(..., min_length=1, max_length=30)
    name: str = Field(..., min_length=1, max_length=80)
    component_type: str = Field(default="earning", pattern="^(earning|deduction)$")
    slot: Optional[str] = Field(default=None, max_length=20)
    default_calc_method: str = Field(default="flat", pattern="^(flat|percent_of_basic)$")
    default_percent: Optional[float] = None
    min_percent: Optional[float] = Field(default=None, ge=0, le=100)
    max_percent: Optional[float] = Field(default=None, ge=0, le=100)
    is_taxable: bool = True
    display_order: int = 0
    is_active: bool = True

    @model_validator(mode="after")
    def _bounds_ordered(self):
        if (self.min_percent is not None and self.max_percent is not None
                and self.min_percent > self.max_percent):
            raise ValueError("min_percent cannot be greater than max_percent")
        if (self.default_percent is not None):
            if self.min_percent is not None and self.default_percent < self.min_percent:
                raise ValueError("default_percent is below min_percent")
            if self.max_percent is not None and self.default_percent > self.max_percent:
                raise ValueError("default_percent is above max_percent")
        return self


class SalaryComponentCreate(SalaryComponentBase):
    pass


class SalaryComponentUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    component_type: Optional[str] = Field(default=None, pattern="^(earning|deduction)$")
    slot: Optional[str] = Field(default=None, max_length=20)
    default_calc_method: Optional[str] = Field(default=None, pattern="^(flat|percent_of_basic)$")
    default_percent: Optional[float] = None
    min_percent: Optional[float] = Field(default=None, ge=0, le=100)
    max_percent: Optional[float] = Field(default=None, ge=0, le=100)
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

    @model_validator(mode="after")
    def _percent_requires_value(self):
        # A percent_of_basic line with no percent silently contributes zero
        # to payroll — reject it. (A flat line with value=None is allowed:
        # the basic slot uses it to mean "use the employee's own basic".)
        if self.calc_method == "percent_of_basic" and self.percent is None:
            raise ValueError("percent is required when calc_method is 'percent_of_basic'")
        return self


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
