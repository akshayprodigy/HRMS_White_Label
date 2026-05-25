from datetime import datetime
from typing import Optional, List, Dict
from pydantic import BaseModel
from enum import Enum


class PayrollRunStatus(str, Enum):
    DRAFT = "draft"
    ATTENDANCE_LOCKED = "attendance_locked"
    LEAVES_LOCKED = "leaves_locked"
    DRAFT_GENERATED = "draft_generated"
    FINALIZED = "finalized"
    PUBLISHED = "published"


class PayrollRunBase(BaseModel):
    month: int
    year: int


class PayrollRunCreate(PayrollRunBase):
    pass


class PayrollRunRead(PayrollRunBase):
    id: int
    status: PayrollRunStatus
    total_gross: float
    total_net: float
    total_deductions: float
    attendance_locked_at: Optional[datetime] = None
    leaves_locked_at: Optional[datetime] = None
    finalized_at: Optional[datetime] = None
    published_at: Optional[datetime] = None
    finalized_by_id: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


class SalaryDisbursementCreate(BaseModel):
    amount: float
    payment_mode: str = "bank_transfer"
    reference: Optional[str] = None
    remarks: Optional[str] = None


class SalaryDisbursementRead(BaseModel):
    id: int
    payroll_line_id: int
    amount: float
    payment_mode: str
    reference: Optional[str] = None
    remarks: Optional[str] = None
    disbursed_by_id: int
    disbursed_by_name: Optional[str] = None
    disbursed_at: datetime

    class Config:
        from_attributes = True


class PayrollLineRead(BaseModel):
    id: int
    payroll_run_id: int
    user_id: int
    base_salary: float
    payable_days: float
    lop_days: float
    arrear: float = 0.0
    incentive: float = 0.0
    gross_pay: float
    net_pay: float
    advance_deduction: float = 0.0
    disbursed_amount: float = 0.0
    held_amount: float = 0.0
    held_reason: Optional[str] = None
    held_released: bool = False
    allowances: Optional[Dict] = None
    deductions: Optional[Dict] = None

    # Computed
    payable_amount: Optional[float] = None
    pending_amount: Optional[float] = None
    disbursement_count: int = 0

    # User info often needed for list
    user_full_name: Optional[str] = None

    class Config:
        from_attributes = True


class PayrollLineUpdate(BaseModel):
    arrear: Optional[float] = None
    incentive: Optional[float] = None
    guest_house: Optional[float] = None
    tds: Optional[float] = None


class PayslipRead(BaseModel):
    id: int
    payroll_line_id: int
    file_url: str
    published_at: datetime

    class Config:
        from_attributes = True


class PayrollDashboard(BaseModel):
    active_runs: List[PayrollRunRead]
    last_finalized_run: Optional[PayrollRunRead] = None
    total_processed_ytd: float


class PayrollActionResponse(BaseModel):
    message: str
    run: PayrollRunRead
