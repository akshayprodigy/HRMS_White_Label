"""On-duty / client-visit / WFH requests (Roadmap v2 Phase 6A, Task 5)."""
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import (
    Date, DateTime, ForeignKey, Index, Integer, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class WorkLocationKind:
    ON_DUTY = "on_duty"
    CLIENT_VISIT = "client_visit"
    WFH = "wfh"
    ALL = (ON_DUTY, CLIENT_VISIT, WFH)
    NEEDS_PLACE = (ON_DUTY, CLIENT_VISIT)


class DayPortion:
    FULL = "full"
    FIRST_HALF = "first_half"
    SECOND_HALF = "second_half"
    ALL = (FULL, FIRST_HALF, SECOND_HALF)


class WorkLocationStatus:
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    ACTIVE = (PENDING, APPROVED)


class WorkLocationRequest(Base):
    __tablename__ = "work_location_request"  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    day_portion: Mapped[str] = mapped_column(
        String(16), default=DayPortion.FULL, nullable=False)
    place: Mapped[Optional[str]] = mapped_column(String(200))
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default=WorkLocationStatus.PENDING, nullable=False)
    decided_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"))
    decided_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True))
    decision_note: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_wlr_user_status", "user_id", "status"),
        Index("ix_wlr_dates", "start_date", "end_date"),
    )
