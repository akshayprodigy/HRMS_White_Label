"""Late-mark rules engine (W9).

A configurable rule: employees late beyond a grace threshold accumulate
"late marks"; every N late marks in a month deducts a day of leave,
cascading Casual Leave (CL) -> Privilege Leave (PL) -> Loss of Pay (LOP).
The residual LOP days feed payroll (reduce payable_days), mirroring the
OvertimeRule/OvertimeEntry pattern.
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class LateMarkScope:
    ORG_DEFAULT = "org_default"
    SHIFT = "shift"


class LateMarkRule(Base):
    __tablename__ = "late_mark_rule"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)

    scope: Mapped[str] = mapped_column(
        String(20), default=LateMarkScope.ORG_DEFAULT, nullable=False, index=True
    )
    shift_template_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("shift_template.id", ondelete="CASCADE"),
        nullable=True, index=True,
    )

    # A punch-in later than shift start + grace_minutes is a "late mark".
    grace_minutes: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    # Every `lates_per_deduction` late marks in a month deducts
    # `deduction_days_per_block` days of leave.
    lates_per_deduction: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    deduction_days_per_block: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)

    # Cascade order: absorb the deduction into first_leave_type, then
    # second_leave_type, then the residual becomes LOP. Configurable so the
    # product stays white-label (no hardcoded CL/PL). NULL = straight to LOP.
    first_leave_type_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("leavetype.id", ondelete="SET NULL"), nullable=True
    )
    second_leave_type_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("leavetype.id", ondelete="SET NULL"), nullable=True
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc), nullable=False,
    )
    created_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )

    shift_template: Mapped[Optional["ShiftTemplate"]] = relationship()  # noqa: F821


class LateMarkDeduction(Base):
    """Per-employee, per-month tally of late marks and the resulting
    CL/PL/LOP deduction. `payroll_run_id` NULL = candidate not yet paid
    (mirrors OvertimeEntry); the LOP portion feeds payable_days."""
    __tablename__ = "late_mark_deduction"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)

    late_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    deducted_days: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    cl_days: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    pl_days: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    lop_days: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    payroll_run_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("payrollrun.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("user_id", "year", "month", name="uq_late_mark_user_period"),
    )
