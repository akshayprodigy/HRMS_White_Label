"""Biometric (ADMS / iClock) devices, PIN mappings and raw punches
(Roadmap v2 Phase 4, Task 1)."""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Computed, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


def _now():
    return datetime.now(timezone.utc)


class BiometricDeviceStatus:
    PENDING = "pending"
    ACTIVE = "active"
    DISABLED = "disabled"


class BiometricPunchState:
    PENDING_DEVICE = "pending_device"
    UNMAPPED = "unmapped"
    APPLIED = "applied"
    DUPLICATE = "duplicate"
    LOCKED = "locked"
    EDITED = "edited"
    ERROR = "error"
    IGNORED = "ignored"


class BiometricDevice(Base):
    __tablename__ = "biometric_device"  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    serial: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=BiometricDeviceStatus.PENDING,
        server_default=BiometricDeviceStatus.PENDING, index=True)
    utc_offset_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    ip_allowlist: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    location_note: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True)
    last_ip: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    firmware: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    attlog_stamp: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    operlog_stamp: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    offline_alerted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)
    approved_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)


class BiometricDeviceUser(Base):
    """Users enrolled on a device (from OPERLOG "USER" lines)."""
    __tablename__ = "biometric_device_user"  # type: ignore[assignment]
    __table_args__ = (UniqueConstraint("device_id", "pin"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("biometric_device.id", ondelete="CASCADE"),
        nullable=False)
    pin: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)


class BiometricUserMap(Base):
    """Device PIN -> employee user. device_id NULL = applies to every device.
    MariaDB treats NULLs as distinct in unique keys, so uniqueness is enforced
    through the generated `device_key = COALESCE(device_id, 0)`."""
    __tablename__ = "biometric_user_map"  # type: ignore[assignment]
    __table_args__ = (UniqueConstraint("device_key", "pin"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("biometric_device.id", ondelete="CASCADE"),
        nullable=True)
    device_key: Mapped[int] = mapped_column(
        Integer, Computed("COALESCE(device_id, 0)", persisted=True))
    pin: Mapped[str] = mapped_column(String(32), nullable=False)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False, index=True)
    created_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False)


class BiometricPunch(Base):
    __tablename__ = "biometric_punch"  # type: ignore[assignment]
    __table_args__ = (
        Index("ix_biometric_punch_user_time", "user_id", "punch_time"),
        Index("ix_biometric_punch_state_time", "state", "punch_time"),
        Index("ix_biometric_punch_device_time", "device_id", "punch_time"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dedupe_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    device_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("biometric_device.id", ondelete="SET NULL"),
        nullable=True, index=True)
    import_batch: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True, index=True)
    pin: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    punch_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True)
    device_status: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    verify_type: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    raw: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True, index=True)
    state: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    attendance_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("attendance.id", ondelete="SET NULL"), nullable=True)
    error: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False)
    applied_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)
