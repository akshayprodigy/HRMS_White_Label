from datetime import datetime, timezone, date as pydate
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import (
    String, Integer, ForeignKey, DateTime, Text, Date, Boolean, Float
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, backref
from app.db.base_class import Base

if TYPE_CHECKING:
    from .user import User
    from .employee import Employee


# ─── Status Constants ─────────────────────────────────────────

class ResignationStatus:
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"          # HR/Manager accepted
    NOTICE_PERIOD = "notice_period" # Serving notice
    EXIT_INTERVIEW = "exit_interview"
    CLEARANCE = "clearance"
    RELEASED = "released"
    WITHDRAWN = "withdrawn"
    REJECTED = "rejected"


class TerminationType:
    """Section M B4: split for the attrition report — voluntary vs
    involuntary. Value is stored as a string on Resignation so future
    types (contract_end, retirement, ...) can be added without a
    migration.
    """
    VOLUNTARY = "voluntary"
    INVOLUNTARY = "involuntary"


class ClearanceStatus:
    PENDING = "pending"
    CLEARED = "cleared"
    FLAGGED = "flagged"  # Issues found


# ─── Resignation ──────────────────────────────────────────────

class Resignation(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    employee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("employee.id", ondelete="CASCADE"),
        unique=True, index=True
    )
    reason: Mapped[str] = mapped_column(String(50), nullable=False)
    reason_details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Section M B4: additive — nullable so all existing rows keep working.
    # Fetcher treats NULL as VOLUNTARY (documented in attrition_report).
    termination_type: Mapped[Optional[str]] = mapped_column(
        String(16), nullable=True, index=True,
    )
    status: Mapped[str] = mapped_column(
        String(30), default=ResignationStatus.SUBMITTED, index=True
    )

    resignation_date: Mapped[pydate] = mapped_column(Date, nullable=False)
    last_working_day: Mapped[pydate] = mapped_column(Date, nullable=False)
    notice_period_days: Mapped[int] = mapped_column(Integer, nullable=False)

    # Who acted on it
    accepted_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    accepted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    released_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    released_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    withdrawn_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    hr_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    employee: Mapped["Employee"] = relationship(
        "Employee",
        backref=backref("resignation", passive_deletes=True),
    )
    accepted_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[accepted_by_id]
    )
    released_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[released_by_id]
    )
    exit_interview: Mapped[Optional["ExitInterview"]] = relationship(
        "ExitInterview", back_populates="resignation", uselist=False
    )
    clearance_requests: Mapped[List["ClearanceRequest"]] = relationship(
        "ClearanceRequest", back_populates="resignation",
        cascade="all, delete-orphan"
    )


# ─── Exit Interview ───────────────────────────────────────────

class ExitInterview(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    resignation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("resignation.id", ondelete="CASCADE"),
        unique=True, index=True
    )
    employee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("employee.id", ondelete="CASCADE"), index=True
    )

    # Reason checkboxes (from Exit Interview Form)
    reason_career: Mapped[bool] = mapped_column(Boolean, default=False)
    reason_studies: Mapped[bool] = mapped_column(Boolean, default=False)
    reason_personal: Mapped[bool] = mapped_column(Boolean, default=False)
    reason_relocation: Mapped[bool] = mapped_column(Boolean, default=False)
    reason_health: Mapped[bool] = mapped_column(Boolean, default=False)
    reason_work_environment: Mapped[bool] = mapped_column(Boolean, default=False)
    reason_compensation: Mapped[bool] = mapped_column(Boolean, default=False)
    reason_relationship: Mapped[bool] = mapped_column(Boolean, default=False)
    reason_role_mismatch: Mapped[bool] = mapped_column(Boolean, default=False)
    reason_other: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    reason_explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Ratings (1-5 scale)
    rating_job_satisfaction: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rating_work_life_balance: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rating_team_cooperation: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rating_management_communication: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rating_training_development: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rating_career_growth: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rating_compensation: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rating_company_culture: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Open feedback
    feedback_liked_most: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    feedback_liked_least: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    feedback_suggestions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # HR remarks
    hr_remarks: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    hr_reviewed_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )

    submitted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    resignation: Mapped["Resignation"] = relationship(
        "Resignation", back_populates="exit_interview"
    )
    employee: Mapped["Employee"] = relationship("Employee")
    hr_reviewed_by: Mapped[Optional["User"]] = relationship("User")


# ─── Clearance ────────────────────────────────────────────────

class ClearanceRequest(Base):
    """One clearance request per department for a resignation."""
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    resignation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("resignation.id", ondelete="CASCADE"), index=True
    )
    department: Mapped[str] = mapped_column(String(100), nullable=False)
    assigned_to_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(
        String(20), default=ClearanceStatus.PENDING, index=True
    )
    remarks: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cleared_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    resignation: Mapped["Resignation"] = relationship(
        "Resignation", back_populates="clearance_requests"
    )
    assigned_to: Mapped["User"] = relationship("User")
    items: Mapped[List["ClearanceItem"]] = relationship(
        "ClearanceItem", back_populates="clearance_request",
        cascade="all, delete-orphan"
    )


class ClearanceItem(Base):
    """Individual checklist items within a clearance request."""
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    clearance_request_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("clearancerequest.id", ondelete="CASCADE"), index=True
    )
    item_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_cleared: Mapped[bool] = mapped_column(Boolean, default=False)
    remarks: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    clearance_request: Mapped["ClearanceRequest"] = relationship(
        "ClearanceRequest", back_populates="items"
    )
