"""Per-day shift allowances injected into payroll (Roadmap v2 Phase 2, T5).

kind 'on_call'  written from on_call_assignment
kind 'callback' written by call-back compensation (Task 4)
While payroll_run_id IS NULL the row is a candidate for the next draft;
generate_draft stamps it. FK is SET NULL like overtime/night entries.
"""
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import (
    Date, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class ShiftAllowanceKind:
    ON_CALL = "on_call"
    CALLBACK = "callback"
    ALL = (ON_CALL, CALLBACK)


class ShiftAllowanceEntry(Base):
    __tablename__ = "shift_allowance_entry"  # type: ignore[assignment]
    __table_args__ = (
        UniqueConstraint("user_id", "work_date", "kind",
                         name="uq_shift_allow_user_date_kind"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), index=True,
        nullable=False)
    work_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rule_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("on_call_rule.id", ondelete="SET NULL"),
        nullable=True)
    source_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    payroll_run_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("payrollrun.id", ondelete="SET NULL"),
        nullable=True, index=True)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc), nullable=False)
