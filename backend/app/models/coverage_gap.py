"""Coverage gaps (Roadmap v2 Phase 2, Task 3): a shift that needs a
replacement because someone is absent (emergency leave, no-show, give-away
with no open shift posted, sick call, manual)."""
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import (
    Date, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class GapSource:
    EMERGENCY_LEAVE = "emergency_leave"
    NO_SHOW = "no_show"
    DROP = "drop"
    SICK_CALL = "sick_call"
    MANUAL = "manual"
    ALL = (EMERGENCY_LEAVE, NO_SHOW, DROP, SICK_CALL, MANUAL)
    MANUAL_ALLOWED = (SICK_CALL, MANUAL)


class GapStatus:
    OPEN = "open"
    FILLED = "filled"
    DISMISSED = "dismissed"


class CoverageGap(Base):
    __tablename__ = "coverage_gap"  # type: ignore[assignment]
    __table_args__ = (
        # NULL absent_user_id rows never collide (SQL NULLs are distinct).
        UniqueConstraint("absent_user_id", "work_date", "source",
                         name="uq_coverage_gap_absent_date_source"),
        Index("ix_coverage_gap_status_date", "status", "work_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    work_date: Mapped[date] = mapped_column(Date, nullable=False)
    shift_template_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("shift_template.id", ondelete="CASCADE"),
        nullable=False, index=True)
    department: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    absent_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    source_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=GapStatus.OPEN)
    open_shift_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("open_shift.id", ondelete="SET NULL"), nullable=True)
    filled_by_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    resolved_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc), nullable=False)
