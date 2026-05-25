from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING, List
from sqlalchemy import (
    String, Integer, ForeignKey, DateTime, Float, Text, Boolean
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base_class import Base

if TYPE_CHECKING:
    from .user import User
    from .employee import Employee


class AdvanceStatus:
    ACTIVE = "active"
    FULLY_RECOVERED = "fully_recovered"
    WRITTEN_OFF = "written_off"
    CANCELLED = "cancelled"


class RecoveryMode:
    ONE_TIME = "one_time"
    INSTALLMENT = "installment"


class SalaryAdvance(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    employee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("employee.id", ondelete="CASCADE"), index=True
    )
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    disbursed_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    recovery_mode: Mapped[str] = mapped_column(
        String(20), default=RecoveryMode.ONE_TIME
    )
    installment_months: Mapped[int] = mapped_column(Integer, default=1)
    recovered_amount: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(
        String(20), default=AdvanceStatus.ACTIVE, index=True
    )
    approved_by_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id"), nullable=False
    )
    remarks: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    employee: Mapped["Employee"] = relationship("Employee")
    approved_by: Mapped["User"] = relationship("User", foreign_keys=[approved_by_id])
    recoveries: Mapped[List["AdvanceRecovery"]] = relationship(
        "AdvanceRecovery",
        back_populates="advance",
        cascade="all, delete-orphan"
    )

    @property
    def outstanding(self) -> float:
        return max(0.0, self.amount - self.recovered_amount)

    @property
    def monthly_emi(self) -> float:
        if self.installment_months <= 0:
            return self.outstanding
        return round(self.amount / self.installment_months, 2)


class AdvanceRecovery(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    advance_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("salaryadvance.id", ondelete="CASCADE"),
        index=True
    )
    payroll_run_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("payrollrun.id"), nullable=True
    )
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    recovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )
    remarks: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    advance: Mapped["SalaryAdvance"] = relationship(
        "SalaryAdvance", back_populates="recoveries"
    )
