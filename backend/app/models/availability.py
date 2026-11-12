"""Employee availability & shift preferences (Roadmap v2 Phase 1B)."""
import enum
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class AvailabilityKind(str, enum.Enum):
    UNAVAILABLE = "unavailable"
    PREFERRED = "preferred"


class EmployeeAvailability(Base):
    __tablename__ = "employee_availability"  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    weekday: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    specific_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    shift_template_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("shift_template.id", ondelete="CASCADE"),
        nullable=True)
    valid_from: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    valid_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    note: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc), nullable=False)
