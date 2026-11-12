"""Emergency broadcast & "mark me safe" (Roadmap v2 Phase 2, Task 7)."""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Index, Integer, String, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class BroadcastSeverity:
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    ALL = (INFO, WARNING, CRITICAL)


class BroadcastAudience:
    ALL_EMPLOYEES = "all"
    LOCATION = "location"
    DEPARTMENT = "department"
    ON_SHIFT = "on_shift"
    ALL = (ALL_EMPLOYEES, LOCATION, DEPARTMENT, ON_SHIFT)


class SafetyStatus:
    SAFE = "safe"
    NEED_HELP = "need_help"
    ALL = (SAFE, NEED_HELP)


def _now():
    return datetime.now(timezone.utc)


class Broadcast(Base):
    __tablename__ = "broadcast"  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(
        String(16), default=BroadcastSeverity.INFO, nullable=False)
    audience: Mapped[str] = mapped_column(String(16), nullable=False)
    audience_value: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    requires_ack: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    safety_check: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False)
    closed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)


class BroadcastRecipient(Base):
    __tablename__ = "broadcast_recipient"  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    broadcast_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("broadcast.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), index=True, nullable=False)
    read_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)
    acked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)
    safety_status: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    safety_note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    responded_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("broadcast_id", "user_id", name="uq_broadcast_recipient"),
        Index("ix_broadcast_recipient_status", "broadcast_id", "safety_status"),
    )
