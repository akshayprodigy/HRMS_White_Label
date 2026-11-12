"""No-show alerts (Roadmap v2 Phase 1B, Task 9). One row per (user, work_date)
so the detection job is idempotent."""
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class NoShowAlert(Base):
    __tablename__ = "no_show_alert"  # type: ignore[assignment]
    __table_args__ = (
        UniqueConstraint("user_id", "work_date", name="uq_no_show_alert_user_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    work_date: Mapped[date] = mapped_column(Date, nullable=False)
    shift_template_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("shift_template.id", ondelete="CASCADE"),
        nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc), nullable=False)
