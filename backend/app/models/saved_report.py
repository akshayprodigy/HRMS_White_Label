"""SavedReport model.

A saved-report is (report_key, filters_json, recipients, cadence).
On-demand "run now" is available immediately; the actual scheduler
job is a documented follow-up (mirrors the apply-due pattern from
salary revisions — the model is here so no schema churn later).
"""
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer, String, Text, JSON,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


if TYPE_CHECKING:
    from .user import User


class SavedReportCadence:
    NONE = "none"           # run-now only
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"


class SavedReport(Base):
    __tablename__ = "saved_report"  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    report_key: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    filters_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    default_format: Mapped[str] = mapped_column(
        String(10), default="xlsx", nullable=False,
    )

    cadence: Mapped[str] = mapped_column(
        String(20), default=SavedReportCadence.NONE, nullable=False,
    )
    recipients_json: Mapped[list] = mapped_column(
        JSON, default=list, nullable=False,
    )   # list[str] of email addresses

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    last_run_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    next_run_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    owner_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc), nullable=False,
    )
