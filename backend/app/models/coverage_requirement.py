"""Minimum/maximum headcount requirement per shift (Roadmap v2 Phase 1A).

NULL department/location = all; NULL weekday = every day (Mon=0..Sun=6).
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class CoverageRequirement(Base):
    __tablename__ = "coverage_requirement"  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    department: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    shift_template_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("shift_template.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    weekday: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    min_headcount: Mapped[int] = mapped_column(Integer, nullable=False)
    max_headcount: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc), nullable=False,
    )
