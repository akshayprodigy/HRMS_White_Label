from datetime import date, datetime
from typing import TYPE_CHECKING, Optional
from sqlalchemy import (
    Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base_class import Base

if TYPE_CHECKING:
    from .user import User


class EmployeeStatus:
    ACTIVE = "active"
    INACTIVE = "inactive"
    ON_LEAVE = "on_leave"
    NOTICE_PERIOD = "notice_period"


class Employee(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("user.id", ondelete="CASCADE"),
        unique=True,
        index=True
    )
    employee_id: Mapped[str] = mapped_column(
        String(20), unique=True, index=True, nullable=False
    )
    
    department: Mapped[str] = mapped_column(String(100), index=True)
    # Legacy free-text columns. Kept during the designation/grade master
    # transition so existing payslips, letters and reports keep working
    # while HR cleans up unmatched rows. The canonical truth is
    # designation_id / grade_id below.
    designation: Mapped[str] = mapped_column(String(100), index=True)
    designation_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("designation.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    grade_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("grade.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    date_of_joining: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=EmployeeStatus.ACTIVE, index=True
    )
    
    # Permission protected fields
    salary: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    conveyance_allowance: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    hra: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    other_allowance: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    esic_applicable: Mapped[bool] = mapped_column(Boolean, default=False)
    bank_account: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )
    bank_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # Additive plumbing columns (Section K). NEFT/bank-advice reads these.
    bank_ifsc_code: Mapped[Optional[str]] = mapped_column(
        String(11), nullable=True
    )
    bank_account_holder_name: Mapped[Optional[str]] = mapped_column(
        String(120), nullable=True
    )
    # Mirrors document-verification pattern: employee edits their own,
    # HR flips verified_at once they've confirmed the details against a
    # cancelled cheque. bank_advice fetcher can optionally filter on
    # verified rows only (default: emit all, but flag unverified).
    bank_verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    bank_verified_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    grade: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    level: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    voluntary_pf: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pf_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    pan_number: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True
    )

    # Employment type
    employment_type: Mapped[str] = mapped_column(String(20), default="permanent", nullable=False)

    # Confirmation / probation
    probation_end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    confirmation_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Self-editable contact fields
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Notice period (set by HR during creation/update)
    notice_period_days: Mapped[int] = mapped_column(Integer, default=30)

    # Key Result Areas - editable by employee, viewable by HR
    kra: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship("User", backref="employee")
