"""Salary-revision effective-dating + arrear computation.

Pure helpers — no DB, no I/O — so the lifecycle logic can be unit-tested
without fixtures.

# Documented constants

## MID_MONTH_RULE = "apply_full_month_containing_effective_from"

When a revision's `effective_from` falls mid-month (e.g. June 15), the
NEW components apply for the ENTIRE payroll month that contains it
(June). We deliberately do NOT pro-rate within the month — too few
companies do it that way for it to be worth the complexity, and the
arrear path already handles back-dated cases cleanly.

If you ever switch to per-day proration, the only place to change is
`is_effective_for_month()` below.

## ARREAR_BASIS = "monthly_ctc_delta_x_months"

Arrears for a back-dated revision = (new monthly gross − old monthly
gross) × number of payroll months between the effective month and the
current draft month (exclusive of the current draft, which is already
paid at the new rate by `effective_components_for_month`).

We use total monthly gross (Basic + HRA + Conveyance + Other), NOT only
basic. This matches the existing salary_calculator earnings shape.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Iterable, Optional, Protocol


MID_MONTH_RULE = "apply_full_month_containing_effective_from"
ARREAR_BASIS = "monthly_ctc_delta_x_months"


class RevStatus(str, Enum):
    DRAFT = "draft"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"
    CANCELLED = "cancelled"


class RevisionLike(Protocol):
    """Structural type accepted by the helpers."""
    id: int
    employee_id: int
    status: str
    effective_from: date
    new_basic: float
    new_conveyance: float
    new_hra: float
    new_other_allowance: float
    new_ctc: float
    old_basic: float
    old_conveyance: float
    old_hra: float
    old_other_allowance: float
    old_ctc: float
    arrears_run_id: Optional[int]


# ----- DTOs ---------------------------------------------------------


@dataclass
class EffectiveComponents:
    basic: float
    conveyance: float
    hra: float
    other_allowance: float
    ctc: float
    source: str          # "revision:<id>" or "employee_master"
    revision_id: Optional[int] = None


@dataclass
class ArrearComputation:
    revision_id: int
    months_owed: int     # full months gap, exclusive of the draft month
    monthly_delta: float
    amount: float        # rounded to 2dp


# ----- effective-date plumbing --------------------------------------


def is_effective_for_month(
    effective_from: date, year: int, month: int
) -> bool:
    """True when the revision's NEW components govern this payroll month.

    The rule (MID_MONTH_RULE): the new components apply for the entire
    month that contains `effective_from`, and every later month.
    Earlier months keep the old components.
    """
    eff_month_start = date(effective_from.year, effective_from.month, 1)
    target_month_start = date(year, month, 1)
    return target_month_start >= eff_month_start


def months_between_exclusive(
    start: date, end: date
) -> int:
    """Number of FULL calendar months from `start` (inclusive) up to but
    excluding the month of `end`. Negative if end is before start.

    Used to count how many already-finalized payroll months a back-dated
    revision should be paid arrears for.
    """
    return (
        (end.year - start.year) * 12
        + (end.month - start.month)
    )


# ----- effective components -----------------------------------------


def effective_components_for_month(
    *,
    employee_basic: float,
    employee_conveyance: float,
    employee_hra: float,
    employee_other_allowance: float,
    revisions: Iterable[RevisionLike],
    year: int,
    month: int,
) -> EffectiveComponents:
    """Pick the components that should be used for this payroll month.

    Selects the most recent APPLIED revision whose effective_from is
    in/before the target month. If none, falls back to the employee
    master values — the no-regression contract for employees that have
    never had a revision.
    """
    applied = [
        r for r in revisions
        if r.status == RevStatus.APPLIED.value
        and is_effective_for_month(r.effective_from, year, month)
    ]
    if not applied:
        ctc = (
            employee_basic + employee_conveyance
            + employee_hra + employee_other_allowance
        )
        return EffectiveComponents(
            basic=employee_basic, conveyance=employee_conveyance,
            hra=employee_hra, other_allowance=employee_other_allowance,
            ctc=ctc, source="employee_master",
        )
    latest = max(applied, key=lambda r: r.effective_from)
    return EffectiveComponents(
        basic=latest.new_basic, conveyance=latest.new_conveyance,
        hra=latest.new_hra, other_allowance=latest.new_other_allowance,
        ctc=latest.new_ctc,
        source=f"revision:{latest.id}", revision_id=latest.id,
    )


# ----- arrears -------------------------------------------------------


def _monthly_gross(
    basic: float, conveyance: float, hra: float, other: float
) -> float:
    return basic + conveyance + hra + other


def _gap_months_for_arrear(
    effective_from: date, draft_year: int, draft_month: int,
) -> int:
    """How many already-finalized payroll months exist between
    effective_from and the current draft month.

    Example: effective_from = 2026-03-15, draft month = 2026-06 →
    March / April / May = 3 finalised months → 3 months of arrears.

    The CURRENT draft month is not counted — it picks up the new rate
    via `effective_components_for_month`, so paying arrears there would
    double-count.
    """
    eff_anchor = date(effective_from.year, effective_from.month, 1)
    draft_anchor = date(draft_year, draft_month, 1)
    return max(0, months_between_exclusive(eff_anchor, draft_anchor))


def compute_arrears_for_revision(
    *, revision: RevisionLike, draft_year: int, draft_month: int,
) -> Optional[ArrearComputation]:
    """Return the arrear injection for a revision in this draft month.

    Returns None when:
    - revision is not APPLIED
    - revision has already been paid arrears (`arrears_run_id` set)
    - effective_from is in / after the draft month (no past gap)
    - the gap is zero (effective month == draft month)

    Never raises. The caller stamps `arrears_run_id` after injecting.
    """
    if revision.status != RevStatus.APPLIED.value:
        return None
    if revision.arrears_run_id is not None:
        return None
    gap = _gap_months_for_arrear(
        revision.effective_from, draft_year, draft_month,
    )
    if gap == 0:
        return None

    old_g = _monthly_gross(
        revision.old_basic, revision.old_conveyance,
        revision.old_hra, revision.old_other_allowance,
    )
    new_g = _monthly_gross(
        revision.new_basic, revision.new_conveyance,
        revision.new_hra, revision.new_other_allowance,
    )
    delta = new_g - old_g
    if delta <= 0:
        # No positive delta -> nothing to back-pay. A negative delta
        # (correction/demotion) is NOT recovered via arrears; HR uses
        # an adjustment line instead.
        return None

    return ArrearComputation(
        revision_id=revision.id,
        months_owed=gap,
        monthly_delta=round(delta, 2),
        amount=round(delta * gap, 2),
    )


# ----- band check ---------------------------------------------------


def band_warning_for(
    new_ctc: float,
    grade_min_salary: Optional[float],
    grade_max_salary: Optional[float],
) -> Optional[str]:
    """Warn (don't block) when the new CTC is outside the target grade.

    Returns None when no grade band is configured or the CTC is inside.
    Otherwise a short human-readable string suitable for storage on
    SalaryRevision.band_warning and surfacing in the UI.
    """
    if grade_min_salary is None and grade_max_salary is None:
        return None
    if grade_min_salary is not None and new_ctc < grade_min_salary:
        return (
            f"CTC {new_ctc:,.0f} is below the grade's minimum "
            f"{grade_min_salary:,.0f}."
        )
    if grade_max_salary is not None and new_ctc > grade_max_salary:
        return (
            f"CTC {new_ctc:,.0f} is above the grade's maximum "
            f"{grade_max_salary:,.0f}."
        )
    return None


# ----- hike derivation ---------------------------------------------


def derive_hike(old_ctc: float, new_ctc: float) -> tuple[float, float]:
    """Return (hike_amount, hike_percent). Zero pct when old_ctc <= 0."""
    amt = round(new_ctc - old_ctc, 2)
    if old_ctc <= 0:
        return amt, 0.0
    pct = round((amt / old_ctc) * 100.0, 2)
    return amt, pct
