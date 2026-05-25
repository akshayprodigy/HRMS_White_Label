import enum
from datetime import datetime, date, timezone
from typing import Optional, TYPE_CHECKING
from sqlalchemy import String, Integer, ForeignKey, DateTime, Boolean, Date, Enum, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base_class import Base

if TYPE_CHECKING:
    from .user import User


class LeaveStatus(str, enum.Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class HalfDaySession(str, enum.Enum):
    MORNING = "morning"
    AFTERNOON = "afternoon"


class LeaveType(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    code: Mapped[Optional[str]] = mapped_column(String(10), unique=True, index=True, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(String(200))
    unpaid_allowed: Mapped[bool] = mapped_column(Boolean, default=False)

    # Policy configuration fields
    annual_quota: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_carry_forward: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_accumulation: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_consecutive_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    allow_half_day: Mapped[bool] = mapped_column(Boolean, default=True)
    requires_medical_cert_after: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_cumulative: Mapped[bool] = mapped_column(Boolean, default=True)
    use_within_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_per_month: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_per_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    balances: Mapped[list["LeaveBalanceLedger"]] = relationship(
        back_populates="leave_type", cascade="all, delete-orphan"
    )
    requests: Mapped[list["LeaveRequest"]] = relationship(
        back_populates="leave_type"
    )


class LeaveBalanceLedger(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), index=True
    )
    leave_type_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("leavetype.id", ondelete="CASCADE"), index=True
    )
    balance: Mapped[float] = mapped_column(Float, default=0.0)
    used: Mapped[float] = mapped_column(Float, default=0.0)

    user: Mapped["User"] = relationship("User")
    leave_type: Mapped[LeaveType] = relationship(back_populates="balances")


class LeaveRequest(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    employee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), index=True
    )
    leave_type_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("leavetype.id", ondelete="CASCADE"), index=True
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_half_day: Mapped[bool] = mapped_column(Boolean, default=False)
    half_day_session: Mapped[Optional[HalfDaySession]] = mapped_column(
        Enum(HalfDaySession), nullable=True
    )
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    emergency_contact: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    attachment_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[LeaveStatus] = mapped_column(
        Enum(LeaveStatus), default=LeaveStatus.DRAFT, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    created_by_user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE")
    )

    employee: Mapped["User"] = relationship("User", foreign_keys=[employee_id])
    created_by: Mapped["User"] = relationship("User", foreign_keys=[created_by_user_id])
    leave_type: Mapped[LeaveType] = relationship(back_populates="requests")
