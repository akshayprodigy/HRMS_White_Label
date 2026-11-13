"""Live location tracking (Roadmap v2 Phase 3, Task 3).

Off by default for every role: HR enables per role (`tracking_policy`) or per
employee (`tracking_override`); the employee must consent (`tracking_consent`,
history rows, revocable). Pings are only accepted during the rostered shift
window.
"""
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean, Date, DateTime, Double, ForeignKey, Index, Integer, String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


def _now():
    return datetime.now(timezone.utc)


class TrackingPolicy(Base):
    __tablename__ = "tracking_policy"  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("role.id", ondelete="CASCADE"),
        unique=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    interval_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=300)
    distance_filter_m: Mapped[int] = mapped_column(
        Integer, nullable=False, default=100)
    updated_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)


class TrackingOverride(Base):
    __tablename__ = "tracking_override"  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"),
        unique=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    updated_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)


class TrackingConsent(Base):
    """History rows; the active consent is the latest row with
    revoked_at IS NULL."""
    __tablename__ = "tracking_consent"  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"),
        index=True, nullable=False)
    consented_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)
    app_version: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)


class LocationPing(Base):
    __tablename__ = "location_ping"  # type: ignore[assignment]
    __table_args__ = (
        UniqueConstraint("user_id", "captured_at", name="uq_location_ping_user_ts"),
        Index("ix_location_ping_captured", "captured_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False)
    lat: Mapped[float] = mapped_column(Double, nullable=False)
    lng: Mapped[float] = mapped_column(Double, nullable=False)
    accuracy: Mapped[Optional[float]] = mapped_column(Double, nullable=True)
    speed: Mapped[Optional[float]] = mapped_column(Double, nullable=True)
    battery: Mapped[Optional[float]] = mapped_column(Double, nullable=True)
    work_date: Mapped[date] = mapped_column(Date, nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False)


class TrackingAlert(Base):
    __tablename__ = "tracking_alert"  # type: ignore[assignment]
    __table_args__ = (
        UniqueConstraint("user_id", "work_date", "kind",
                         name="uq_tracking_alert"),
        Index("ix_tracking_alert_work_date", "work_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    work_date: Mapped[date] = mapped_column(Date, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False)
