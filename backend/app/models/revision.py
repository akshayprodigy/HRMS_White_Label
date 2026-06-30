"""Salary revision + bulk revision cycle.

Core lifecycle:

  DRAFT  →  PENDING (submitted)  →  APPROVED  →  APPLIED
              │                       │
              └──── REJECTED ─────────┘

A revision stays in APPROVED while waiting for `effective_from` to
arrive; the apply-due job (or a manual HR action) flips it to APPLIED.

Effective-dating is authoritative. The actual employee-master mutation
happens only on the APPLY transition — never sooner. Back-dated
revisions trigger arrears in the next draft payroll run; finalized runs
are never retro-edited.
"""
from datetime import datetime, date as pydate, timezone
from typing import TYPE_CHECKING, Optional, List

from sqlalchemy import (
    Boolean, DateTime, Date, Float, ForeignKey, Integer, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


if TYPE_CHECKING:
    from .user import User


class RevisionType:
    PROMOTION = "promotion"
    INCREMENT = "increment"
    CORRECTION = "correction"
    DEMOTION = "demotion"


class RevisionStatus:
    DRAFT = "draft"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"
    CANCELLED = "cancelled"


class CycleStatus:
    DRAFT = "draft"
    PENDING = "pending"           # bulk-submit triggered, employee items pending
    COMPLETED = "completed"       # all items moved out of PENDING
    CANCELLED = "cancelled"


class RevisionCycle(Base):
    __tablename__ = "revision_cycle"  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(
        String(160), nullable=False, unique=True, index=True,
    )
    effective_from: Mapped[pydate] = mapped_column(Date, nullable=False)

    status: Mapped[str] = mapped_column(
        String(20), default=CycleStatus.DRAFT, nullable=False, index=True
    )

    # Planning fields — set when the cycle is created, used by the
    # workspace's plan-vs-actual view.
    budget_hike_amount: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    created_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )

    revisions: Mapped[List["SalaryRevision"]] = relationship(
        back_populates="cycle",
    )


class SalaryRevision(Base):
    __tablename__ = "salary_revision"  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    employee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("employee.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    cycle_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("revision_cycle.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )

    revision_type: Mapped[str] = mapped_column(
        String(20), default=RevisionType.INCREMENT, nullable=False, index=True
    )
    effective_from: Mapped[pydate] = mapped_column(
        Date, nullable=False, index=True
    )
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # --------- snapshot: what we are changing FROM ---------
    old_designation_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("designation.id", ondelete="SET NULL"),
        nullable=True,
    )
    old_grade_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("grade.id", ondelete="SET NULL"), nullable=True,
    )
    old_basic: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    old_conveyance: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    old_hra: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    old_other_allowance: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    old_ctc: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # --------- snapshot: what we are changing TO ---------
    new_designation_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("designation.id", ondelete="SET NULL"),
        nullable=True,
    )
    new_grade_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("grade.id", ondelete="SET NULL"), nullable=True,
    )
    new_basic: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    new_conveyance: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    new_hra: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    new_other_allowance: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    new_ctc: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Derived (stored for fast queries; recomputed on every save).
    hike_amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    hike_percent: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Soft warning if the new_ctc is outside the new grade's band.
    band_warning: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # --------- lifecycle ---------
    status: Mapped[str] = mapped_column(
        String(20), default=RevisionStatus.DRAFT,
        nullable=False, index=True,
    )
    approval_item_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("approvalitem.id", ondelete="SET NULL"),
        nullable=True,
    )
    rejected_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    applied_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    applied_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True,
    )

    # Letter generated on apply (Promotion / Salary Revision).
    letter_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("employeeletter.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Set when this revision's arrear has been injected into a payroll
    # draft. Prevents double-arrear on re-generate. SET NULL on run
    # deletion so a re-draft can re-pick it up.
    arrears_run_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("payrollrun.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    # The arrear amount actually injected (≠ recomputed-on-the-fly).
    arrears_amount: Mapped[float] = mapped_column(
        Float, default=0.0, nullable=False
    )
    arrears_months: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    created_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )

    cycle: Mapped[Optional[RevisionCycle]] = relationship(
        back_populates="revisions",
    )
