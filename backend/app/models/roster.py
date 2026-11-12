"""Weekly/monthly roster planner (W7).

A per-employee-per-day layer sitting on TOP of the range-based
EmployeeShiftAssignment. Precedence for attendance shift resolution
(services/effective_shift.py): a PUBLISHED RosterEntry overrides the
EmployeeShiftAssignment for that day (a roster week-off yields no shift,
so a punch that day is unscheduled). DRAFT entries are ignored entirely,
and blank cells (no shift, not a week-off) fall back to the assignment.
Payroll / overtime are not otherwise changed by the roster.

`employee_id` here is a User id (mirrors EmployeeShiftAssignment.employee_id),
not the Employee PK.
"""
from datetime import datetime, date as pydate, timezone
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    JSON, Boolean, Date, DateTime, ForeignKey, Integer, String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base

if TYPE_CHECKING:
    from .user import User
    from .shift import ShiftTemplate


class RosterStatus:
    DRAFT = "draft"
    PUBLISHED = "published"


class RosterChangeStatus:
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class RosterEntry(Base):
    __tablename__ = "roster_entry"  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    employee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    work_date: Mapped[pydate] = mapped_column(Date, index=True, nullable=False)
    # NULL shift + is_week_off False => unassigned/blank; NULL + is_week_off
    # True => explicit week-off.
    shift_template_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("shift_template.id", ondelete="RESTRICT"),
        nullable=True,
    )
    is_week_off: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(16), default=RosterStatus.PUBLISHED, index=True, nullable=False
    )
    # Department-name snapshot for scoped filtering (historical stamp — do
    # NOT trust for authorization; re-scope on read via live Department heads).
    department: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    assigned_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc), nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "employee_id", "work_date", name="uq_roster_entry_emp_date"
        ),
    )

    shift_template: Mapped[Optional["ShiftTemplate"]] = relationship(
        "ShiftTemplate", foreign_keys=[shift_template_id]
    )
    employee: Mapped["User"] = relationship("User", foreign_keys=[employee_id])
    assigned_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[assigned_by_id]
    )


class RosterChangeRequest(Base):
    __tablename__ = "roster_change_request"  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    employee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    roster_entry_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("roster_entry.id", ondelete="SET NULL"),
        nullable=True,
    )
    work_date: Mapped[pydate] = mapped_column(Date, nullable=False)
    current_shift_template_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("shift_template.id", ondelete="SET NULL"),
        nullable=True,
    )
    requested_shift_template_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("shift_template.id", ondelete="SET NULL"),
        nullable=True,
    )
    requested_week_off: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=RosterChangeStatus.PENDING, index=True,
        nullable=False,
    )
    decided_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    decision_note: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc), nullable=False,
    )

    user: Mapped["User"] = relationship("User", foreign_keys=[employee_id])
    requested_shift: Mapped[Optional["ShiftTemplate"]] = relationship(
        "ShiftTemplate", foreign_keys=[requested_shift_template_id]
    )
    current_shift: Mapped[Optional["ShiftTemplate"]] = relationship(
        "ShiftTemplate", foreign_keys=[current_shift_template_id]
    )
    decided_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[decided_by_id]
    )


class RosterEntryHistory(Base):
    """Audit trail of edits to PUBLISHED schedule cells (and publish events).
    Template ids carry no FK so history survives template removal."""
    __tablename__ = "roster_entry_history"  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    employee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    work_date: Mapped[pydate] = mapped_column(Date, index=True, nullable=False)
    roster_entry_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("roster_entry.id", ondelete="SET NULL"),
        nullable=True,
    )
    old_shift_template_id: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    old_is_week_off: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    new_shift_template_id: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    new_is_week_off: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    changed_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True,
        default=lambda: datetime.now(timezone.utc), nullable=False,
    )
    # True when the change landed inside the schedule lock window
    # (schedule.lock_days) -- the employee must acknowledge it.
    is_emergency: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False
    )


class ScheduleChangeAck(Base):
    """One acknowledgement owed by an employee per emergency change."""
    __tablename__ = "schedule_change_ack"  # type: ignore[assignment]
    __table_args__ = (
        UniqueConstraint("history_id", "user_id", name="uq_sched_ack_hist_user"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    history_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("roster_entry_history.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc), nullable=False,
    )


class RosterPublishRequest(Base):
    __tablename__ = "roster_publish_request"  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    requested_by_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    start: Mapped[pydate] = mapped_column(Date, nullable=False)
    end: Mapped[pydate] = mapped_column(Date, nullable=False)
    department: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    employee_ids: Mapped[List[int]] = mapped_column(
        JSON, default=list, nullable=False
    )
    note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), default="pending", index=True, nullable=False
    )
    decided_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    decision_note: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc), nullable=False,
    )

    requester: Mapped["User"] = relationship(
        "User", foreign_keys=[requested_by_id]
    )
