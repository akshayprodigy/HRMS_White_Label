from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, field_validator


class SalaryAdvanceCreate(BaseModel):
    employee_id: int
    amount: float
    reason: Optional[str] = None
    disbursed_date: datetime
    recovery_mode: str = "one_time"  # one_time | installment
    installment_months: int = 1
    remarks: Optional[str] = None

    @field_validator("amount")
    @classmethod
    def amount_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Amount must be greater than zero")
        return v

    @field_validator("installment_months")
    @classmethod
    def installment_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("Installment months must be at least 1")
        return v

    @field_validator("recovery_mode")
    @classmethod
    def valid_mode(cls, v: str) -> str:
        if v not in ("one_time", "installment"):
            raise ValueError("recovery_mode must be one_time or installment")
        return v


class SalaryAdvanceUpdate(BaseModel):
    reason: Optional[str] = None
    recovery_mode: Optional[str] = None
    installment_months: Optional[int] = None
    remarks: Optional[str] = None


class SalaryAdvanceWriteOff(BaseModel):
    remarks: Optional[str] = None


class ManualRecovery(BaseModel):
    amount: float
    remarks: Optional[str] = None

    @field_validator("amount")
    @classmethod
    def amount_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Amount must be greater than zero")
        return v


class AdvanceRecoveryRead(BaseModel):
    id: int
    advance_id: int
    payroll_run_id: Optional[int] = None
    amount: float
    recovered_at: datetime
    remarks: Optional[str] = None

    class Config:
        from_attributes = True


class SalaryAdvanceRead(BaseModel):
    id: int
    employee_id: int
    amount: float
    reason: Optional[str] = None
    disbursed_date: datetime
    recovery_mode: str
    installment_months: int
    recovered_amount: float
    status: str
    approved_by_id: int
    remarks: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    # Joined fields
    employee_name: Optional[str] = None
    employee_code: Optional[str] = None
    department: Optional[str] = None
    approved_by_name: Optional[str] = None
    outstanding: Optional[float] = None
    monthly_emi: Optional[float] = None

    class Config:
        from_attributes = True


class SalaryAdvanceListResponse(BaseModel):
    items: List[SalaryAdvanceRead]
    total: int


# Partial payment schemas
class PartialPaymentSet(BaseModel):
    disbursed_amount: float
    held_reason: Optional[str] = None

    @field_validator("disbursed_amount")
    @classmethod
    def amount_non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError("Disbursed amount cannot be negative")
        return v


class HeldSalaryRelease(BaseModel):
    payroll_line_ids: List[int]
