"""On-call / standby roster (Roadmap v2 Phase 2, Task 5).

on_call_rule        how a standby day is paid (flat per day or hourly)
on_call_assignment  who is on standby on which date (one per user/date)
"""
from datetime import date, datetime, time, timezone
from typing import Optional

from sqlalchemy import (
    Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class OnCallPayout:
    FLAT_PER_DAY = "flat_per_day"
    HOURLY = "hourly"
    ALL = (FLAT_PER_DAY, HOURLY)


class OnCallRule(Base):
    __tablename__ = "on_call_rule"  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    payout_model: Mapped[str] = mapped_column(
        String(20), default=OnCallPayout.FLAT_PER_DAY, nullable=False)
    flat_amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    hourly_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc), nullable=False)


class OnCallAssignment(Base):
    __tablename__ = "on_call_assignment"  # type: ignore[assignment]
    __table_args__ = (
        UniqueConstraint("user_id", "work_date", name="uq_on_call_user_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), index=True,
        nullable=False)
    work_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    is_overnight: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False)
    rule_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("on_call_rule.id", ondelete="RESTRICT"),
        nullable=False)
    note: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc), nullable=False)
