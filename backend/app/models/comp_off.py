from datetime import datetime, timezone, date as pydate
from typing import Optional, TYPE_CHECKING

from sqlalchemy import (
    Integer, ForeignKey, DateTime, Date, String, Float,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base

if TYPE_CHECKING:
    from .user import User
    from .attendance import Attendance


class CompOffAccrual(Base):
    __tablename__ = "comp_off_accrual"  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), index=True
    )
    holiday_date: Mapped[pydate] = mapped_column(Date, index=True, nullable=False)
    holiday_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    attendance_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("attendance.id", ondelete="SET NULL"), nullable=True
    )
    worked_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    days_credited: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="pending", index=True, nullable=False
    )
    reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    attendance: Mapped[Optional["Attendance"]] = relationship(
        "Attendance", foreign_keys=[attendance_id]
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id", "holiday_date",
            name="uq_comp_off_accrual_user_holiday",
        ),
    )
