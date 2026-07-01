"""Scheduled-job registry — persistent metadata + last-run state.

The APScheduler triggers themselves live in-process; this table is the
observability + admin surface (list, run-now, enable/disable) and the
place last-run status persists across worker restarts.

Multi-worker safety: `is_running` is checked with SELECT ... FOR UPDATE
inside the job wrapper so only one worker actually runs a given tick.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, Integer, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class JobRunStatus:
    IDLE = "idle"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class ScheduledJob(Base):
    __tablename__ = "scheduled_job"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    # Stable job code — matches the callable registered in the runner.
    name: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Cron-ish cadence stored as a string; interpreter is APScheduler's
    # CronTrigger.from_crontab(...). Examples: "0 2 * * *" (daily 02:00),
    # "0 3 1 * *" (first of month 03:00), "*/15 * * * *" (every 15 min).
    cadence_cron: Mapped[str] = mapped_column(String(80), nullable=False)

    enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=True,
    )
    is_running: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
    )

    last_run_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_status: Mapped[str] = mapped_column(
        String(16), default=JobRunStatus.IDLE, nullable=False,
    )
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_duration_ms: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
