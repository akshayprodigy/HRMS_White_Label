"""Employee optional-holiday picks (Roadmap v2 Phase 6A, Task 5)."""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class PickStatus:
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    ACTIVE = (PENDING, APPROVED)


class OptionalHolidayPick(Base):
    __tablename__ = "optional_holiday_pick"  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    holiday_id: Mapped[int] = mapped_column(
        ForeignKey("holidaycalendar.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"))
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default=PickStatus.PENDING, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text)
    decided_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"))
    decided_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True))
    decision_note: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_ohp_user_year_status", "user_id", "year", "status"),
    )
