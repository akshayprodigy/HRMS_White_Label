"""Overtime + Night-shift allowance.

Step 4 of the 24x7 shift engine. Two configurable masters
(OvertimeRule, NightShiftAllowanceRule) plus per-attendance computed
entries (OvertimeEntry, NightAllowanceEntry) that feed the payroll
draft as injected line items.

Backward compatibility
----------------------
An employee/shift with no matching rule produces zero entries and is
invisible to payroll injection -> exactly today's behaviour.
"""
from datetime import datetime, time, date as pydate, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean, DateTime, Date, Float, ForeignKey, Integer, String, Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base

if TYPE_CHECKING:
    from .user import User
    from .shift import ShiftTemplate
    from .attendance import Attendance
    from .approval import ApprovalItem
    from .payroll import PayrollRun


# ----- string-constant enums (kept as plain strings on the row so the
#       front-end can show them without an Enum import). ------------


class OvertimeScope:
    ORG_DEFAULT = "org_default"
    SHIFT = "shift"


class OvertimeBasis:
    BEYOND_SHIFT_HOURS = "beyond_shift_hours"      # extra past shift's full_day_hours
    BEYOND_THRESHOLD = "beyond_threshold"          # extra past `daily_threshold_hours`


class OvertimeStatus:
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    AUTO_APPROVED = "auto_approved"     # rule.requires_approval=False


class DayType:
    WEEKDAY = "weekday"
    WEEKLY_OFF = "weekly_off"
    HOLIDAY = "holiday"


class NightPayoutModel:
    FLAT = "flat"          # flat amount per qualifying night
    HOURLY = "hourly"      # per-hour amount for night-window minutes


# ----- masters -------------------------------------------------------


class OvertimeRule(Base):
    __tablename__ = "overtime_rule"  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)

    # Either org_default (shift_template_id NULL) or per-shift.
    scope: Mapped[str] = mapped_column(
        String(20), default=OvertimeScope.ORG_DEFAULT, nullable=False, index=True
    )
    shift_template_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("shift_template.id", ondelete="CASCADE"),
        nullable=True, index=True,
    )

    ot_basis: Mapped[str] = mapped_column(
        String(30), default=OvertimeBasis.BEYOND_SHIFT_HOURS, nullable=False
    )
    daily_threshold_hours: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )

    ot_rate_multiplier: Mapped[float] = mapped_column(Float, default=1.5, nullable=False)
    weekly_off_multiplier: Mapped[float] = mapped_column(Float, default=2.0, nullable=False)
    holiday_multiplier: Mapped[float] = mapped_column(Float, default=2.0, nullable=False)

    min_ot_minutes: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    daily_ot_cap_minutes: Mapped[int] = mapped_column(Integer, default=240, nullable=False)
    monthly_ot_cap_minutes: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )

    rounding_minutes: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    created_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )

    shift_template: Mapped[Optional["ShiftTemplate"]] = relationship()


class NightShiftAllowanceRule(Base):
    __tablename__ = "night_shift_allowance_rule"  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)

    scope: Mapped[str] = mapped_column(
        String(20), default=OvertimeScope.ORG_DEFAULT, nullable=False, index=True
    )
    shift_template_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("shift_template.id", ondelete="CASCADE"),
        nullable=True, index=True,
    )

    payout_model: Mapped[str] = mapped_column(
        String(20), default=NightPayoutModel.FLAT, nullable=False
    )
    # Used when payout_model == FLAT (currency units, e.g. INR).
    flat_amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    # Used when payout_model == HOURLY (per-hour amount for qualifying night minutes).
    hourly_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Cross-midnight aware window. e.g. 22:00 -> 06:00.
    night_window_start: Mapped[time] = mapped_column(Time, nullable=False)
    night_window_end: Mapped[time] = mapped_column(Time, nullable=False)

    min_night_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    created_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )

    shift_template: Mapped[Optional["ShiftTemplate"]] = relationship()


# ----- per-attendance computed entries ------------------------------


class OvertimeEntry(Base):
    __tablename__ = "overtime_entry"  # type: ignore[assignment]
    __table_args__ = (
        # One OT entry per employee per work-date. Prevents double-count
        # on recompute; rule changes UPDATE the existing row.
        UniqueConstraint("user_id", "work_date", name="uq_ot_user_workdate"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), index=True, nullable=False
    )
    work_date: Mapped[pydate] = mapped_column(Date, index=True, nullable=False)
    attendance_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("attendance.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    shift_template_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("shift_template.id", ondelete="SET NULL"),
        nullable=True,
    )
    rule_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("overtime_rule.id", ondelete="SET NULL"),
        nullable=True,
    )

    ot_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ot_amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    hourly_rate_used: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    multiplier_used: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    day_type: Mapped[str] = mapped_column(
        String(20), default=DayType.WEEKDAY, nullable=False
    )

    status: Mapped[str] = mapped_column(
        String(20), default=OvertimeStatus.PENDING, nullable=False, index=True
    )
    approver_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    approval_item_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("approvalitem.id", ondelete="SET NULL"),
        nullable=True,
    )
    rejection_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # When this entry is injected into a payroll run, this is set. While
    # NULL the entry is a candidate for the next draft generation.
    payroll_run_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("payrollrun.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )

    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    approver: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[approver_id]
    )


class NightAllowanceEntry(Base):
    __tablename__ = "night_allowance_entry"  # type: ignore[assignment]
    __table_args__ = (
        UniqueConstraint(
            "user_id", "work_date", name="uq_night_user_workdate"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), index=True, nullable=False
    )
    work_date: Mapped[pydate] = mapped_column(Date, index=True, nullable=False)
    attendance_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("attendance.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    rule_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("night_shift_allowance_rule.id", ondelete="SET NULL"),
        nullable=True,
    )

    night_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    payout_model_used: Mapped[str] = mapped_column(
        String(20), default=NightPayoutModel.FLAT, nullable=False
    )

    payroll_run_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("payrollrun.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )

    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
