from datetime import datetime, date, time, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean, Date, DateTime, Float, ForeignKey, Integer, JSON, String, Time,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base

if TYPE_CHECKING:
    from .user import User


class ShiftTemplate(Base):
    __tablename__ = "shift_template"  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(
        String(80), unique=True, index=True, nullable=False
    )
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)

    # Derived from (start_time, end_time) at write time. Stored as a column
    # so it can be filtered/indexed without a Python round-trip.
    is_overnight: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )

    break_minutes: Mapped[int] = mapped_column(
        Integer, default=60, nullable=False
    )
    grace_in_minutes: Mapped[int] = mapped_column(
        Integer, default=10, nullable=False
    )
    grace_out_minutes: Mapped[int] = mapped_column(
        Integer, default=10, nullable=False
    )

    full_day_hours: Mapped[float] = mapped_column(
        Float, default=9.0, nullable=False
    )
    half_day_hours: Mapped[float] = mapped_column(
        Float, default=4.5, nullable=False
    )

    # JSON array of weekday integers, Python convention: Mon=0..Sun=6.
    weekly_offs: Mapped[list] = mapped_column(
        JSON, default=list, nullable=False
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
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

    created_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[created_by_id]
    )
    assignments: Mapped[list["EmployeeShiftAssignment"]] = relationship(
        back_populates="shift_template",
    )


class EmployeeShiftAssignment(Base):
    __tablename__ = "employee_shift_assignment"  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    employee_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("user.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    shift_template_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("shift_template.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )

    effective_from: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    # NULL means the assignment is ongoing (open-ended).
    effective_to: Mapped[Optional[date]] = mapped_column(
        Date, nullable=True, index=True
    )

    assigned_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    note: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    shift_template: Mapped["ShiftTemplate"] = relationship(
        back_populates="assignments",
    )
    employee: Mapped["User"] = relationship(
        "User", foreign_keys=[employee_id]
    )
    assigned_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[assigned_by_id]
    )


class ShiftChangeStatus:
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class ShiftChangeRequest(Base):
    """Section R: employee-initiated shift change, approved via the
    generic chain engine (Reporting Manager -> HR). On final approval
    the chain endpoint creates the EmployeeShiftAssignment."""

    __tablename__ = "shift_change_request"  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), index=True
    )
    # Snapshot of the shift the employee was on when they asked (may be
    # NULL when they had no shift).
    current_shift_template_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("shift_template.id", ondelete="SET NULL"),
        nullable=True,
    )
    requested_shift_template_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("shift_template.id", ondelete="CASCADE"),
    )
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=ShiftChangeStatus.PENDING, index=True
    )
    approval_instance_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("chained_approval_instance.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    decided_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    requested_shift: Mapped["ShiftTemplate"] = relationship(
        "ShiftTemplate", foreign_keys=[requested_shift_template_id]
    )
    current_shift: Mapped[Optional["ShiftTemplate"]] = relationship(
        "ShiftTemplate", foreign_keys=[current_shift_template_id]
    )
