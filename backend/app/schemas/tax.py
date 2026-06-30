"""Pydantic schemas for tax / Form 16 / Form 24Q / gratuity APIs."""
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ----- TaxSlabConfig -------------------------------------------------


class TaxSlabConfigBase(BaseModel):
    fy: str = Field(..., pattern=r"^\d{2}-\d{2}$",
                    description='FY label, e.g. "24-25"')
    name: str = Field(..., min_length=1, max_length=120)
    slabs_json: Dict[str, Any] = Field(
        default_factory=dict,
        description="{old:[...], new:[...], surcharge_old:[...], surcharge_new:[...]}",
    )
    standard_deduction_old: float = Field(50000, ge=0)
    standard_deduction_new: float = Field(75000, ge=0)
    rebate_87a_old_threshold: float = Field(500000, ge=0)
    rebate_87a_old_max: float = Field(12500, ge=0)
    rebate_87a_new_threshold: float = Field(700000, ge=0)
    rebate_87a_new_max: float = Field(25000, ge=0)
    cess_rate: float = Field(4.0, ge=0, le=100)
    is_active: bool = True
    notes: Optional[str] = None


class TaxSlabConfigCreate(TaxSlabConfigBase):
    pass


class TaxSlabConfigUpdate(BaseModel):
    name: Optional[str] = None
    slabs_json: Optional[Dict[str, Any]] = None
    standard_deduction_old: Optional[float] = Field(None, ge=0)
    standard_deduction_new: Optional[float] = Field(None, ge=0)
    rebate_87a_old_threshold: Optional[float] = Field(None, ge=0)
    rebate_87a_old_max: Optional[float] = Field(None, ge=0)
    rebate_87a_new_threshold: Optional[float] = Field(None, ge=0)
    rebate_87a_new_max: Optional[float] = Field(None, ge=0)
    cess_rate: Optional[float] = Field(None, ge=0, le=100)
    is_active: Optional[bool] = None
    notes: Optional[str] = None


class TaxSlabConfigRead(TaxSlabConfigBase):
    id: int
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


# ----- SectionLimitConfig --------------------------------------------


class SectionLimitBase(BaseModel):
    fy: str = Field(..., pattern=r"^\d{2}-\d{2}$")
    section_code: str = Field(..., min_length=1, max_length=40)
    limit_amount: float = Field(..., ge=0)
    is_percentage: bool = False
    applies_to: str = Field("BOTH", pattern="^(BOTH|OLD|NEW)$")
    notes: Optional[str] = None


class SectionLimitCreate(SectionLimitBase):
    pass


class SectionLimitUpdate(BaseModel):
    limit_amount: Optional[float] = Field(None, ge=0)
    is_percentage: Optional[bool] = None
    applies_to: Optional[str] = Field(None, pattern="^(BOTH|OLD|NEW)$")
    notes: Optional[str] = None


class SectionLimitRead(SectionLimitBase):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


# ----- GratuityConfig ------------------------------------------------


class GratuityConfigBase(BaseModel):
    effective_from: date
    statutory_cap: float = Field(2000000, ge=0)
    eligibility_years: int = Field(5, ge=0, le=20)
    days_basis: int = Field(26, ge=1, le=31)
    is_active: bool = True
    notes: Optional[str] = None


class GratuityConfigCreate(GratuityConfigBase):
    pass


class GratuityConfigUpdate(BaseModel):
    statutory_cap: Optional[float] = Field(None, ge=0)
    eligibility_years: Optional[int] = Field(None, ge=0, le=20)
    days_basis: Optional[int] = Field(None, ge=1, le=31)
    is_active: Optional[bool] = None
    notes: Optional[str] = None


class GratuityConfigRead(GratuityConfigBase):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


# ----- EmployeeTaxDeclaration ---------------------------------------


class DeclarationBase(BaseModel):
    fy: str = Field(..., pattern=r"^\d{2}-\d{2}$")
    regime: str = Field("new", pattern="^(old|new)$")
    declarations_json: Dict[str, float] = Field(default_factory=dict)
    monthly_rent_paid: float = Field(0.0, ge=0)
    rented_in_metro: bool = False
    landlord_pan: Optional[str] = Field(None, max_length=20)
    other_income_annual: float = Field(0.0, ge=0)
    previous_employer_income: float = Field(0.0, ge=0)
    previous_employer_tds: float = Field(0.0, ge=0)


class DeclarationCreate(DeclarationBase):
    employee_id: int


class DeclarationUpdate(BaseModel):
    regime: Optional[str] = Field(None, pattern="^(old|new)$")
    declarations_json: Optional[Dict[str, float]] = None
    monthly_rent_paid: Optional[float] = Field(None, ge=0)
    rented_in_metro: Optional[bool] = None
    landlord_pan: Optional[str] = None
    other_income_annual: Optional[float] = Field(None, ge=0)
    previous_employer_income: Optional[float] = Field(None, ge=0)
    previous_employer_tds: Optional[float] = Field(None, ge=0)


class DeclarationRead(DeclarationBase):
    id: int
    employee_id: int
    status: str
    submitted_at: Optional[datetime]
    verified_at: Optional[datetime]
    verified_by_id: Optional[int]
    rejection_reason: Optional[str]
    created_at: datetime
    updated_at: datetime
    # enrichment
    employee_full_name: Optional[str] = None
    employee_code: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class VerifyAction(BaseModel):
    action: str = Field(..., pattern="^(verify|reject)$")
    rejection_reason: Optional[str] = Field(None, max_length=500)


# ----- TDS projection / reconciliation ------------------------------


class TaxComputationRead(BaseModel):
    regime: str
    gross_income: float
    standard_deduction: float
    hra_exemption: float
    chapter_via_deductions: float
    other_income: float
    previous_employer_income: float
    taxable_income: float
    tax_on_slabs: float
    rebate_87a: float
    surcharge: float
    cess: float
    total_tax: float
    monthly_tds: float = 0.0
    notes: List[str] = Field(default_factory=list)


class RegimeComparisonRead(BaseModel):
    fy: str
    employee_id: int
    employee_full_name: Optional[str] = None
    old: TaxComputationRead
    new: TaxComputationRead
    better_regime: str
    saving: float
    declared_regime: Optional[str] = None


class TDSReconRow(BaseModel):
    user_id: int
    employee_code: Optional[str]
    name: Optional[str]
    projected_annual_tax: float
    ytd_tds: float
    months_remaining: int
    required_monthly: float
    last_month_tds: float
    catch_up_amount: float
    status: str


class TDSReconciliationReport(BaseModel):
    fy: str
    as_of: date
    rows: List[TDSReconRow]
    total_under: int
    total_over: int
    total_ok: int


# ----- Form 16 ------------------------------------------------------


class Form16Read(BaseModel):
    id: int
    employee_id: int
    fy: str
    reference_number: Optional[str]
    part_b_url: Optional[str]
    part_b_generated_at: Optional[datetime]
    part_a_url: Optional[str]
    part_a_uploaded_at: Optional[datetime]
    traces_certificate_number: Optional[str]
    status: str
    issued_at: Optional[datetime]
    missing_pan_flag: bool
    created_at: datetime
    updated_at: datetime
    employee_full_name: Optional[str] = None
    employee_code: Optional[str] = None
    pan: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class Form16GenerateRequest(BaseModel):
    fy: str = Field(..., pattern=r"^\d{2}-\d{2}$")
    employee_ids: Optional[List[int]] = None    # None = all employees
                                                # with finalized FY payroll


class Form16GenerateResult(BaseModel):
    fy: str
    generated: int
    skipped_no_pan: int
    skipped_no_payroll: int
    records: List[Form16Read]


class Form16TracesUpload(BaseModel):
    traces_certificate_number: Optional[str] = None
    part_a_url: str = Field(..., min_length=1)


# ----- Form 24Q -----------------------------------------------------


class Form24QGenerateRequest(BaseModel):
    fy: str = Field(..., pattern=r"^\d{2}-\d{2}$")
    quarter: int = Field(..., ge=1, le=4)


class Form24QRead(BaseModel):
    id: int
    fy: str
    quarter: int
    file_url: Optional[str]
    file_name: Optional[str]
    summary: Optional[dict]
    status: str
    challan_number: Optional[str]
    submitted_at: Optional[datetime]
    accepted_at: Optional[datetime]
    generated_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


# ----- Gratuity -----------------------------------------------------


class GratuityResultRead(BaseModel):
    employee_id: int
    employee_full_name: Optional[str] = None
    employee_code: Optional[str] = None
    last_basic_da: float
    days_basis: int
    raw_years: float
    rounded_years: int
    is_eligible: bool
    computed_amount: float
    capped_amount: float
    cap_applied: bool
    eligibility_years_used: int
    note: str = ""
    as_of: date


class CompanyLiabilityReport(BaseModel):
    as_of: date
    total_employees: int
    eligible_employees: int
    total_accruing_liability: float
    payable_if_all_exit_today: float
    accruing_under_5_years: float
    rows: List[GratuityResultRead]


class ExitGratuityResult(BaseModel):
    employee_id: int
    resignation_id: Optional[int]
    last_working_day: date
    gratuity: GratuityResultRead
    snapshot_id: int
