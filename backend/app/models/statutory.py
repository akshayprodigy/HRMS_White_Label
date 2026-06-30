"""Statutory filing masters + filing records.

Three regulatory streams in scope:
- EPF (Provident Fund) — EPFO ECR text file
- ESIC — Employee State Insurance contribution file
- Professional Tax — per-state monthly summary

Effective-dating is central. Rates change (e.g. EPF wage ceiling jumped
from ₹6,500 → ₹15,000 in 2014). Every config row carries effective_from;
the picker chooses the row with the latest effective_from that is ≤ the
payroll month. PT slabs are scoped to a state because each Indian state
sets its own slab table.

This module ONLY ADDS tables. It does not modify Employee, payroll, or
salary_calculator — generators READ finalized payroll lines.
"""
from datetime import datetime, date as pydate, timezone
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    Boolean, DateTime, Date, Float, ForeignKey, Integer, String, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base

if TYPE_CHECKING:
    from .user import User


class StatutoryStream:
    """Enum-like constants for the filing stream."""
    EPF = "epf"
    ESIC = "esic"
    PT = "pt"


class FilingStatus:
    DRAFT = "draft"
    GENERATED = "generated"
    SUBMITTED = "submitted"
    ACKNOWLEDGED = "acknowledged"
    PAID = "paid"
    REJECTED = "rejected"


# ----- masters ------------------------------------------------------


class EmployerIdentifier(Base):
    """Single-row master of the company's statutory identifiers.

    Multiple rows are allowed for multi-establishment companies (PF code
    per establishment) — most installs will have one.
    """
    __tablename__ = "employer_identifier"  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)

    pf_establishment_code: Mapped[Optional[str]] = mapped_column(
        String(40), nullable=True
    )
    pf_extension: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    esic_employer_code: Mapped[Optional[str]] = mapped_column(
        String(40), nullable=True
    )
    tan: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    pan: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    lin: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    # Default state for PT when an employee's state is missing.
    default_pt_state: Mapped[Optional[str]] = mapped_column(
        String(40), nullable=True
    )
    address_line: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc), nullable=False,
    )


class StatutoryConfig(Base):
    """Effective-dated PF + ESIC rates and ceilings.

    Resolver: for payroll month M, pick the row with the LATEST
    `effective_from <= last day of M`. This is the standard "as-of"
    pattern — same one used by the salary-revision module.
    """
    __tablename__ = "statutory_config"  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    effective_from: Mapped[pydate] = mapped_column(
        Date, nullable=False, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # ----- EPF -----
    pf_employee_rate: Mapped[float] = mapped_column(
        Float, default=12.0, nullable=False
    )
    pf_employer_rate: Mapped[float] = mapped_column(
        Float, default=12.0, nullable=False
    )
    # Of the employer's 12%, EPS_rate goes to EPS — the rest to EPF.
    eps_rate: Mapped[float] = mapped_column(
        Float, default=8.33, nullable=False
    )
    # Statutory PF wage ceiling (current law: ₹15,000/month).
    pf_wage_ceiling: Mapped[float] = mapped_column(
        Float, default=15000.0, nullable=False
    )
    eps_wage_ceiling: Mapped[float] = mapped_column(
        Float, default=15000.0, nullable=False
    )
    edli_rate: Mapped[float] = mapped_column(
        Float, default=0.5, nullable=False
    )
    edli_wage_ceiling: Mapped[float] = mapped_column(
        Float, default=15000.0, nullable=False
    )
    epf_admin_rate: Mapped[float] = mapped_column(
        Float, default=0.5, nullable=False
    )

    # ----- ESIC -----
    esic_employee_rate: Mapped[float] = mapped_column(
        Float, default=0.75, nullable=False
    )
    esic_employer_rate: Mapped[float] = mapped_column(
        Float, default=3.25, nullable=False
    )
    # Monthly wage ceiling for ESIC coverage (₹21,000 since 2017).
    esic_wage_ceiling: Mapped[float] = mapped_column(
        Float, default=21000.0, nullable=False
    )

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc), nullable=False,
    )


class PTStateSlab(Base):
    """One row per state slab tier.

    Picker:
      - filter by state + effective_from <= target month
      - for the surviving rows, pick the slab where
        slab_min <= gross_for_pt <= slab_max
      - return monthly_amount

    `gender` is "ALL" by default; some states (e.g. Karnataka pre-2024)
    differentiated. The picker falls back to ALL when no gendered row
    matches.

    `month_index` lets a state special-case a particular month
    (e.g. Maharashtra: ₹300 in Feb, ₹200 other months). NULL = applies
    every month.
    """
    __tablename__ = "pt_state_slab"  # type: ignore[assignment]
    __table_args__ = (
        UniqueConstraint(
            "state", "effective_from", "slab_min", "gender", "month_index",
            name="uq_pt_slab",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    state: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    effective_from: Mapped[pydate] = mapped_column(
        Date, nullable=False, index=True
    )

    slab_min: Mapped[float] = mapped_column(Float, nullable=False)
    # NULL = "and above"
    slab_max: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    monthly_amount: Mapped[float] = mapped_column(Float, nullable=False)

    gender: Mapped[str] = mapped_column(
        String(8), default="ALL", nullable=False
    )
    month_index: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc), nullable=False,
    )


class EmployeeStatutoryDetail(Base):
    """Statutory identifiers that the ECR/ESIC files need.

    Kept as a separate table (vs. extending Employee) so the existing
    Employee model stays untouched — the spec explicitly forbade modifying
    salary_calculator / revision files; we extend the same principle to
    Employee.
    """
    __tablename__ = "employee_statutory_detail"  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    employee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("employee.id", ondelete="CASCADE"),
        unique=True, index=True, nullable=False,
    )

    uan: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    pf_member_id: Mapped[Optional[str]] = mapped_column(
        String(40), nullable=True
    )
    esic_ip_number: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True
    )
    pt_state: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    gender: Mapped[str] = mapped_column(String(8), default="ALL", nullable=False)
    # Per ESIC continuation rule (April-Sept / Oct-March) once an employee
    # is brought under ESIC for a period they STAY under ESIC for the rest
    # of that period even if wages exceed the ceiling. This flag captures
    # the "currently in coverage for the active period" state and is
    # toggled by the generator at period boundaries.
    esic_continuation_until: Mapped[Optional[pydate]] = mapped_column(
        Date, nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc), nullable=False,
    )


# ----- filings (one row per generated export) -----------------------


class StatutoryFiling(Base):
    """One generated export — PF ECR, ESIC contribution file, or PT
    summary — for one (payroll_run, stream) pair.

    `file_url` is where the rendered file lives. `summary` is the
    aggregate (total wages, total contribution, employee count) used
    by the compliance dashboard. `state` is only set for PT (state-wise
    summaries are state-scoped). `challan_number` / `paid_at` are set
    once the actual filing is submitted to the regulator.
    """
    __tablename__ = "statutory_filing"  # type: ignore[assignment]
    __table_args__ = (
        UniqueConstraint(
            "payroll_run_id", "stream", "state",
            name="uq_statutory_filing_run_stream_state",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    payroll_run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("payrollrun.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    stream: Mapped[str] = mapped_column(
        String(10), nullable=False, index=True
    )
    state: Mapped[Optional[str]] = mapped_column(
        String(40), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(
        String(20), default=FilingStatus.GENERATED, nullable=False, index=True
    )

    file_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    file_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    employer_identifier_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("employer_identifier.id", ondelete="SET NULL"),
        nullable=True,
    )
    config_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("statutory_config.id", ondelete="SET NULL"),
        nullable=True,
    )

    # JSON-shaped totals captured at generation time. Cheap to query for
    # the dashboard without re-reading the file.
    summary: Mapped[Optional[dict]] = mapped_column(
        # SQLAlchemy JSON column - imported on the fly to avoid
        # polluting the imports above.
        # NOTE: using sa.JSON via the existing pattern in this codebase.
        # If a project uses sqlalchemy.JSON elsewhere, this is consistent.
        __import__("sqlalchemy").JSON, nullable=True,
    )

    challan_number: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )
    submitted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    paid_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    paid_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc), nullable=False,
    )
    generated_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc), nullable=False,
    )
