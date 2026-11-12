"""Running-late notices (Roadmap v2 Phase 2, Task 2). One row per
(user, work_date); re-posting updates it."""
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class LateNotice(Base):
    __tablename__ = "late_notice"  # type: ignore[assignment]
    __table_args__ = (
        UniqueConstraint("user_id", "work_date", name="uq_late_notice_user_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    work_date: Mapped[date] = mapped_column(Date, nullable=False)
    expected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc), nullable=False)
