import enum
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING, List
from sqlalchemy import String, Integer, ForeignKey, DateTime, Enum, Float, JSON, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base_class import Base

if TYPE_CHECKING:
    from .user import User


class PayrollRunStatus(str, enum.Enum):
    DRAFT = "draft"
    ATTENDANCE_LOCKED = "attendance_locked"
    LEAVES_LOCKED = "leaves_locked"
    DRAFT_GENERATED = "draft_generated"
    FINALIZED = "finalized"
    PUBLISHED = "published"


class PayrollRun(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    month: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-12
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[PayrollRunStatus] = mapped_column(
        Enum(PayrollRunStatus), default=PayrollRunStatus.DRAFT, index=True
    )
    
    total_gross: Mapped[float] = mapped_column(Float, default=0.0)
    total_net: Mapped[float] = mapped_column(Float, default=0.0)
    total_deductions: Mapped[float] = mapped_column(Float, default=0.0)
    
    attendance_locked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    leaves_locked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    finalized_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    published_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    finalized_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id")
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    
    finalized_by: Mapped[Optional["User"]] = relationship()
    lines: Mapped[List["PayrollLine"]] = relationship(
        "PayrollLine",
        back_populates="payroll_run",
        cascade="all, delete-orphan",
        foreign_keys="[PayrollLine.payroll_run_id]"
    )


class PayrollLine(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    payroll_run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("payrollrun.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), index=True
    )
    
    base_salary: Mapped[float] = mapped_column(Float, nullable=False)
    payable_days: Mapped[float] = mapped_column(Float, default=0.0)
    lop_days: Mapped[float] = mapped_column(Float, default=0.0)  # Loss of Pay
    
    gross_pay: Mapped[float] = mapped_column(Float, default=0.0)
    net_pay: Mapped[float] = mapped_column(Float, default=0.0)

    # Variable / one-off earnings (set by HR before finalize)
    arrear: Mapped[float] = mapped_column(Float, default=0.0)
    incentive: Mapped[float] = mapped_column(Float, default=0.0)

    # Advance recovery deducted during this payroll
    advance_deduction: Mapped[float] = mapped_column(Float, default=0.0)

    # Tracks total disbursed so far (sum of all SalaryDisbursement records)
    disbursed_amount: Mapped[float] = mapped_column(Float, default=0.0)
    held_amount: Mapped[float] = mapped_column(Float, default=0.0)
    held_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    held_released: Mapped[bool] = mapped_column(Boolean, default=False)
    held_released_in_run_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("payrollrun.id", ondelete="SET NULL"), nullable=True
    )

    # Detailed breakdown
    allowances: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    deductions: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    payroll_run: Mapped["PayrollRun"] = relationship(
        "PayrollRun", back_populates="lines",
        foreign_keys=[payroll_run_id]
    )
    user: Mapped["User"] = relationship("User")
    payslip: Mapped[Optional["Payslip"]] = relationship(
        "Payslip", back_populates="payroll_line", uselist=False
    )
    disbursements: Mapped[List["SalaryDisbursement"]] = relationship(
        "SalaryDisbursement",
        back_populates="payroll_line",
        cascade="all, delete-orphan",
        order_by="SalaryDisbursement.disbursed_at"
    )


class Payslip(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    payroll_line_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("payrollline.id", ondelete="CASCADE"), index=True
    )
    file_url: Mapped[str] = mapped_column(String(512), nullable=False)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    
    payroll_line: Mapped["PayrollLine"] = relationship(
        "PayrollLine", back_populates="payslip"
    )


class SalaryDisbursement(Base):
    """Each record = one partial payment made to an employee for a payroll line."""
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    payroll_line_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("payrollline.id", ondelete="CASCADE"), index=True
    )
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    payment_mode: Mapped[str] = mapped_column(
        String(30), default="bank_transfer"
    )
    reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    remarks: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    disbursed_by_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id"), nullable=False
    )
    disbursed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )

    payroll_line: Mapped["PayrollLine"] = relationship(
        "PayrollLine", back_populates="disbursements"
    )
    disbursed_by: Mapped["User"] = relationship("User")
