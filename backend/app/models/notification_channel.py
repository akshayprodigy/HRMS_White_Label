"""Notification-delivery models (Section L).

Fan-out layer on top of the existing in-app Notification model — that
model is untouched apart from a nullable `event_type` column added in
the same migration.

Design
------
- `NotificationTemplate` — HR-editable per (event_type, channel).
- `UserNotificationPreference` — per user + per event-category + per
  channel opt-in/out + optional digest cadence.
- `NotificationDelivery` — one row per channel-send attempt. The
  scheduler-driven sweeper creates QUEUED rows for any in-app
  Notification that hasn't been fanned out yet; the sender job
  consumes them.

Sensitive-content rule (documented as `is_sensitive` on template):
templates flagged sensitive strip money/amount keys from the render
context before interpolation, so payslip / salary emails NEVER carry
figures — they carry a link into the app.
"""
from __future__ import annotations

from datetime import datetime, time, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class Channel:
    IN_APP = "in_app"
    EMAIL = "email"
    SMS = "sms"


class DeliveryStatus:
    QUEUED = "queued"
    SENT = "sent"
    FAILED = "failed"
    SKIPPED_PREF = "skipped_pref"       # opted out by preference
    SKIPPED_QUIET = "skipped_quiet"     # dropped in quiet-hours window
    DEAD_LETTER = "dead_letter"


class DigestCadence:
    IMMEDIATE = "immediate"
    HOURLY = "hourly"
    DAILY = "daily"


class EventCategory:
    """Top-level buckets — user preferences are set per category, not
    per event type, so a new event doesn't require a preference
    migration.
    """
    APPROVALS = "approvals"
    LEAVE = "leave"
    OVERTIME = "overtime"
    PAYROLL = "payroll"
    PERFORMANCE = "performance"
    EXPENSE = "expense"
    STATUTORY = "statutory"
    OTHER = "other"


# Map event_type -> category. Templates carry their own category too.
EVENT_CATEGORY_MAP = {
    "leave_submitted": EventCategory.LEAVE,
    "leave_approved": EventCategory.LEAVE,
    "leave_rejected": EventCategory.LEAVE,
    "approval_pending": EventCategory.APPROVALS,
    "approval_approved": EventCategory.APPROVALS,
    "approval_rejected": EventCategory.APPROVALS,
    "overtime_submitted": EventCategory.OVERTIME,
    "overtime_approved": EventCategory.OVERTIME,
    "payslip_published": EventCategory.PAYROLL,
    "salary_revised": EventCategory.PAYROLL,
    "expense_submitted": EventCategory.EXPENSE,
    "expense_approved": EventCategory.EXPENSE,
    "expense_rejected": EventCategory.EXPENSE,
    "expense_reimbursed": EventCategory.EXPENSE,
    "review_released": EventCategory.PERFORMANCE,
    "review_submit_reminder": EventCategory.PERFORMANCE,
    "statutory_due": EventCategory.STATUTORY,
    "report_scheduled": EventCategory.OTHER,
}


class NotificationTemplate(Base):
    __tablename__ = "notification_template"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    channel: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    category: Mapped[str] = mapped_column(String(24), default="other")
    subject: Mapped[Optional[str]] = mapped_column(String(240), nullable=True)
    body_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    body_text: Mapped[str] = mapped_column(Text, nullable=False)
    # DLT template id (India SMS regulatory requirement). Provider
    # attaches this on outbound sends where the channel is SMS.
    dlt_template_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    # True → dispatcher STRIPS money/amount keys from the render
    # context; body must direct the reader to open the app instead of
    # exposing figures. See Section L "sensitive-content rule".
    is_sensitive: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint(
            "event_type", "channel",
            name="uq_notification_template_event_channel",
        ),
    )


class UserNotificationPreference(Base):
    __tablename__ = "user_notification_preference"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), index=True,
    )
    category: Mapped[str] = mapped_column(String(24), index=True)
    channel: Mapped[str] = mapped_column(String(16))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    digest_cadence: Mapped[str] = mapped_column(
        String(16), default=DigestCadence.IMMEDIATE
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id", "category", "channel",
            name="uq_user_pref_user_cat_channel",
        ),
    )


class UserQuietHours(Base):
    """Per-user daily window in which non-critical channels are
    suppressed. Sending is delayed until the window ends (retry job)."""
    __tablename__ = "user_quiet_hours"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"),
        unique=True, index=True,
    )
    quiet_from: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    quiet_to: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    # Hard opt-out — nothing goes out on email/SMS even if a specific
    # category preference says enabled. In-app notifications still fire.
    hard_opt_out: Mapped[bool] = mapped_column(Boolean, default=False)


class NotificationDelivery(Base):
    __tablename__ = "notification_delivery"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    notification_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("notification.id", ondelete="CASCADE"),
        nullable=True, index=True,
    )
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    recipient_user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), index=True,
    )
    channel: Mapped[str] = mapped_column(String(16), index=True)
    status: Mapped[str] = mapped_column(
        String(16), default=DeliveryStatus.QUEUED, index=True,
    )
    provider_message_id: Mapped[Optional[str]] = mapped_column(
        String(120), nullable=True
    )
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_digest: Mapped[bool] = mapped_column(Boolean, default=False)
    digest_batch_key: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True
    )
    # Frozen context at enqueue-time; the sender renders the template
    # from this so subsequent template edits don't change past sends.
    context_json: Mapped[dict] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
