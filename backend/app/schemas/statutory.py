"""Pydantic schemas for statutory filings."""
from datetime import date, datetime
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ----- EmployerIdentifier -------------------------------------------


class EmployerIdentifierBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=160)
    pf_establishment_code: Optional[str] = None
    pf_extension: Optional[str] = None
    esic_employer_code: Optional[str] = None
    tan: Optional[str] = None
    pan: Optional[str] = None
    lin: Optional[str] = None
    default_pt_state: Optional[str] = None
    address_line: Optional[str] = None
    is_active: bool = True


class EmployerIdentifierCreate(EmployerIdentifierBase):
    pass


class EmployerIdentifierUpdate(BaseModel):
    name: Optional[str] = None
    pf_establishment_code: Optional[str] = None
    pf_extension: Optional[str] = None
    esic_employer_code: Optional[str] = None
    tan: Optional[str] = None
    pan: Optional[str] = None
    lin: Optional[str] = None
    default_pt_state: Optional[str] = None
    address_line: Optional[str] = None
    is_active: Optional[bool] = None


class EmployerIdentifierRead(EmployerIdentifierBase):
    id: int
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


# ----- StatutoryConfig ----------------------------------------------


class StatutoryConfigBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    effective_from: date
    is_active: bool = True

    pf_employee_rate: float = Field(12.0, ge=0, le=100)
    pf_employer_rate: float = Field(12.0, ge=0, le=100)
    eps_rate: float = Field(8.33, ge=0, le=100)
    pf_wage_ceiling: float = Field(15000.0, ge=0)
    eps_wage_ceiling: float = Field(15000.0, ge=0)
    edli_rate: float = Field(0.5, ge=0, le=100)
    edli_wage_ceiling: float = Field(15000.0, ge=0)
    epf_admin_rate: float = Field(0.5, ge=0, le=100)

    esic_employee_rate: float = Field(0.75, ge=0, le=100)
    esic_employer_rate: float = Field(3.25, ge=0, le=100)
    esic_wage_ceiling: float = Field(21000.0, ge=0)

    notes: Optional[str] = None

    @model_validator(mode="after")
    def _eps_le_pf_employer(self):
        if self.eps_rate > self.pf_employer_rate:
            raise ValueError("eps_rate cannot exceed pf_employer_rate")
        return self


class StatutoryConfigCreate(StatutoryConfigBase):
    pass


class StatutoryConfigUpdate(BaseModel):
    name: Optional[str] = None
    effective_from: Optional[date] = None
    is_active: Optional[bool] = None
    pf_employee_rate: Optional[float] = Field(None, ge=0, le=100)
    pf_employer_rate: Optional[float] = Field(None, ge=0, le=100)
    eps_rate: Optional[float] = Field(None, ge=0, le=100)
    pf_wage_ceiling: Optional[float] = Field(None, ge=0)
    eps_wage_ceiling: Optional[float] = Field(None, ge=0)
    edli_rate: Optional[float] = Field(None, ge=0, le=100)
    edli_wage_ceiling: Optional[float] = Field(None, ge=0)
    epf_admin_rate: Optional[float] = Field(None, ge=0, le=100)
    esic_employee_rate: Optional[float] = Field(None, ge=0, le=100)
    esic_employer_rate: Optional[float] = Field(None, ge=0, le=100)
    esic_wage_ceiling: Optional[float] = Field(None, ge=0)
    notes: Optional[str] = None


class StatutoryConfigRead(StatutoryConfigBase):
    id: int
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


# ----- PT slab ------------------------------------------------------


class PTSlabBase(BaseModel):
    state: str = Field(..., min_length=1, max_length=40)
    effective_from: date
    slab_min: float = Field(..., ge=0)
    slab_max: Optional[float] = Field(None, ge=0)
    monthly_amount: float = Field(..., ge=0)
    gender: str = Field("ALL", pattern="^(ALL|M|F|O)$")
    month_index: Optional[int] = Field(None, ge=1, le=12)
    is_active: bool = True
    notes: Optional[str] = None

    @model_validator(mode="after")
    def _max_above_min(self):
        if self.slab_max is not None and self.slab_max < self.slab_min:
            raise ValueError("slab_max cannot be less than slab_min")
        return self


class PTSlabCreate(PTSlabBase):
    pass


class PTSlabUpdate(BaseModel):
    monthly_amount: Optional[float] = Field(None, ge=0)
    slab_max: Optional[float] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = None


class PTSlabRead(PTSlabBase):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


# ----- employee statutory detail ------------------------------------


class EmployeeStatutoryDetailBase(BaseModel):
    employee_id: int
    uan: Optional[str] = Field(None, max_length=20)
    pf_member_id: Optional[str] = Field(None, max_length=40)
    esic_ip_number: Optional[str] = Field(None, max_length=20)
    pt_state: Optional[str] = Field(None, max_length=40)
    gender: str = Field("ALL", pattern="^(ALL|M|F|O)$")
    esic_continuation_until: Optional[date] = None


class EmployeeStatutoryDetailUpsert(EmployeeStatutoryDetailBase):
    pass


class EmployeeStatutoryDetailRead(EmployeeStatutoryDetailBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


# ----- generation + filing ------------------------------------------


class GenerateRequest(BaseModel):
    payroll_run_id: int
    employer_identifier_id: Optional[int] = None    # default: first active
    config_id: Optional[int] = None                  # default: pick by month
    state: Optional[str] = None                      # PT only — if omitted,
                                                     # one filing per state
                                                     # is generated


class StatutoryFilingRead(BaseModel):
    id: int
    payroll_run_id: int
    stream: str
    state: Optional[str]
    status: str
    file_url: Optional[str]
    file_name: Optional[str]
    employer_identifier_id: Optional[int]
    config_id: Optional[int]
    summary: Optional[dict]
    challan_number: Optional[str]
    submitted_at: Optional[datetime]
    paid_at: Optional[datetime]
    paid_amount: Optional[float]
    generated_at: datetime
    generated_by_id: Optional[int]
    updated_at: datetime
    # enrichment
    payroll_period: Optional[str] = None
    due_date: Optional[date] = None
    days_to_due: Optional[int] = None
    model_config = ConfigDict(from_attributes=True)


class FilingStatusUpdate(BaseModel):
    status: str = Field(
        ..., pattern="^(generated|submitted|acknowledged|paid|rejected)$",
    )
    challan_number: Optional[str] = None
    paid_amount: Optional[float] = Field(None, ge=0)


class GenerateResult(BaseModel):
    filings: List[StatutoryFilingRead]
    skipped_states: List[str] = []
    notes: List[str] = []


# ----- reconciliation report ----------------------------------------


class DriftFindingRead(BaseModel):
    user_id: int
    employee_code: Optional[str]
    name: Optional[str]
    stream: str
    expected: float
    actual: float
    diff: float
    note: str = ""


class ReconciliationReport(BaseModel):
    payroll_run_id: int
    config_id: Optional[int]
    config_effective_from: Optional[date]
    employees_checked: int
    drift_count: int
    findings: List[DriftFindingRead]
    notes: List[str] = []


# ----- compliance dashboard -----------------------------------------


class ComplianceCard(BaseModel):
    stream: str               # epf | esic | pt
    state: Optional[str]
    payroll_run_id: int
    payroll_period: str       # "MM/YYYY"
    due_date: date
    days_to_due: int          # negative when overdue
    status: str
    filing_id: Optional[int]
    total_amount: Optional[float]
    employee_count: Optional[int]


class ComplianceDashboard(BaseModel):
    as_of: date
    cards: List[ComplianceCard]
    overdue: int
    due_within_7_days: int
