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
