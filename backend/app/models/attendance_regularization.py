"""Employee-initiated attendance regularization (missed/wrong punch fix)."""
from datetime import datetime, timezone, date as pydate
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class RegularizationStatus:
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class AttendanceRegularization(Base):
    __tablename__ = "attendance_regularization"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    work_date: Mapped[pydate] = mapped_column(Date, nullable=False, index=True)
    attendance_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("attendance.id", ondelete="SET NULL"),
        nullable=True,
    )
    requested_punch_in: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    requested_punch_out: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default=RegularizationStatus.PENDING,
        nullable=False, index=True,
    )
    decided_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    decision_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
