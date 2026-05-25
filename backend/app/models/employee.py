from datetime import date
from typing import TYPE_CHECKING, Optional
from sqlalchemy import String, Integer, ForeignKey, Date, Float, Text, Boolean
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
    designation: Mapped[str] = mapped_column(String(100), index=True)
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
