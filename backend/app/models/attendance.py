from datetime import datetime, timezone, date as pydate
from typing import Optional, TYPE_CHECKING
from sqlalchemy import String, Integer, ForeignKey, Float, DateTime, Text, Date
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base_class import Base

if TYPE_CHECKING:
    from .user import User


class Attendance(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), index=True
    )
    mode: Mapped[str] = mapped_column(String(50))  # 'web', 'mobile', etc.
    remarks: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    accuracy: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    punch_out_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    user: Mapped["User"] = relationship("User", back_populates="attendances")


class CorrectionStatus:
    SUBMITTED = "submitted"
    # Backward-compatible alias used by some endpoints
    PENDING = SUBMITTED
    APPROVED = "approved"
    REJECTED = "rejected"


class AttendanceCorrectionRequest(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    attendance_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("attendance.id", ondelete="SET NULL"),
        nullable=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), index=True
    )
    date: Mapped[pydate] = mapped_column(Date, nullable=False)
    requested_mode: Mapped[str] = mapped_column(String(50))
    requested_remarks: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    reason: Mapped[str] = mapped_column(Text)
    attachment_url: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(20), default=CorrectionStatus.SUBMITTED, index=True
    )
    created_by_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    user: Mapped["User"] = relationship(
        "User", foreign_keys=[user_id]
    )
    created_by: Mapped["User"] = relationship(
        "User", foreign_keys=[created_by_id]
    )
    attendance: Mapped["Attendance"] = relationship("Attendance")
