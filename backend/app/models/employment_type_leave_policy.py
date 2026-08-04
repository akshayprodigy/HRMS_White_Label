"""Per-employment-type leave policy (W1).

Gates leave eligibility and overrides the annual quota per
(employment_type, leave_type). A MISSING row means eligible at the
LeaveType default quota — so absence of a matrix never breaks leave for
anyone (legacy-safe fallback).
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class EmploymentTypeLeavePolicy(Base):
    __tablename__ = "employment_type_leave_policy"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    employment_type_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("employment_type.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    leave_type_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("leavetype.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    is_eligible: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Override for this type's annual quota; NULL falls back to LeaveType.annual_quota.
    annual_quota: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc), nullable=False,
    )

    employment_type: Mapped["EmploymentType"] = relationship()  # noqa: F821
    leave_type: Mapped["LeaveType"] = relationship()  # noqa: F821

    __table_args__ = (
        UniqueConstraint("employment_type_id", "leave_type_id", name="uq_emptype_leavetype"),
    )
