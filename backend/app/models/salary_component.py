"""Salary component master (F3).

A configurable catalogue of earning heads. The four canonical heads
(basic / conveyance / hra / other) are seeded to reproduce today's flat
payroll structure; HR can add extra earning components and bundle them
into templates (see salary_template.py). Deduction/statutory heads stay
owned by the unified payroll engine — this master is earnings-only.

`slot` maps a component onto one of the four canonical payroll heads the
salary calculator expects. Components with slot=None (extra earnings)
are summed into `other` at resolve time, so the four-slot contract that
`calculate_salary` depends on is always preserved.
"""
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base

# The four canonical earning heads the salary calculator consumes.
CANONICAL_SLOTS = ("basic", "conveyance", "hra", "other")

# Calculation methods a component value can use.
CALC_FLAT = "flat"
CALC_PERCENT_OF_BASIC = "percent_of_basic"
CALC_METHODS = (CALC_FLAT, CALC_PERCENT_OF_BASIC)


class SalaryComponent(Base):
    __tablename__ = "salary_component"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    # earning | deduction — resolver only sums earnings today.
    component_type: Mapped[str] = mapped_column(String(20), default="earning", nullable=False)
    # Which canonical head this maps to; None = extra earning (folded into `other`).
    slot: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Default calc method / percent — a template component may override these.
    default_calc_method: Mapped[str] = mapped_column(String(20), default=CALC_FLAT, nullable=False)
    default_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Config guardrails (F3+): the allowed range for this component's
    # percent-of-basic. When set, a template line's percent must fall within
    # [min_percent, max_percent] — so Accounts/HR can bound HRA, etc.
    min_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_taxable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc), nullable=False,
    )
