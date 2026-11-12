"""Open shifts and claims (Roadmap v2 Phase 1B).

`ShiftDropRequest` (give-away) is added to this module in Task 4.
"""
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class OpenShiftStatus:
    OPEN = "open"
    FILLED = "filled"
    CANCELLED = "cancelled"


class ClaimStatus:
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class OpenShift(Base):
    __tablename__ = "open_shift"  # type: ignore[assignment]
    __table_args__ = (
        Index("ix_open_shift_status_date", "status", "work_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    work_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    shift_template_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("shift_template.id", ondelete="CASCADE"),
        nullable=False)
    department: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    slots: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    filled: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    note: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=OpenShiftStatus.OPEN)
    auto_confirm: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False)
    created_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    # Set by Task 4 when the shift was posted from a give-away request.
    # The employee who gave this shift away; may not claim it back.
    excluded_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    source_drop_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc), nullable=False)


class OpenShiftClaim(Base):
    __tablename__ = "open_shift_claim"  # type: ignore[assignment]
    __table_args__ = (
        UniqueConstraint("open_shift_id", "user_id", name="uq_open_shift_claim_user"),
        Index("ix_open_shift_claim_user_status", "user_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    open_shift_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("open_shift.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ClaimStatus.PENDING)
    decided_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    decided_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc), nullable=False)
