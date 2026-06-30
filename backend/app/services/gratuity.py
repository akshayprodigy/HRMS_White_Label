"""Gratuity computation.

Pure helpers — no DB, no I/O.

# Documented constants

## GRATUITY_FORMULA = "(last_basic_da / days_basis) × 15 × years"
Payment of Gratuity Act 1972 §4(2). `days_basis` is 26 by default
(working days/month) and configurable via GratuityConfig.

## ELIGIBILITY_YEARS = 5 (Payment of Gratuity Act §4(1))
Continuous service must be at least 5 years. Below that, gratuity is
NOT payable — we still compute the accruing liability for finance,
but the `is_eligible` flag stays False and `gratuity_payable` is 0.
Configurable via GratuityConfig.eligibility_years for the rare case
where company policy is more generous.

## YEARS_ROUNDING_RULE = "≥6_months_rounds_up"
For the FORMULA, fractional years are rounded:
- < 6 months   → drop
- ≥ 6 months   → round up to the next full year
So 4y 7m → 5y for the formula. ELIGIBILITY is a separate check (5
full years of continuous service); the round-up does NOT make a
sub-5-year tenure eligible.

## STATUTORY_CAP_INR = 2_000_000 (default, configurable)
Section 4(3): ₹20 lakh ceiling (raised from ₹10L in March 2018).
Configurable via GratuityConfig.statutory_cap. The cap applies to the
PAYABLE amount, not the computed amount — we surface both so HR can
explain the gap.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable, Optional, Protocol


GRATUITY_FORMULA = "(last_basic_da / days_basis) * 15 * years"
ELIGIBILITY_YEARS = 5
YEARS_ROUNDING_RULE = "≥6_months_rounds_up"
STATUTORY_CAP_INR = 2_000_000


# ----- protocols ---------------------------------------------------


class GratuityConfigLike(Protocol):
    statutory_cap: float
    eligibility_years: int
    days_basis: int


# ----- DTO ---------------------------------------------------------


@dataclass
class GratuityResult:
    last_basic_da: float
    days_basis: int
    raw_years: float                 # actual fractional years
    rounded_years: int               # rounded for formula
    is_eligible: bool
    computed_amount: float           # before cap
    capped_amount: float             # after cap (payable)
    cap_applied: bool
    eligibility_years_used: int
    note: str = ""


# ----- helpers -----------------------------------------------------


def _full_and_remainder_months(
    joining_date: date, as_of: date,
) -> tuple[int, int]:
    """Anniversary-aware decomposition of tenure.

    Returns (full_years_completed, remainder_months) where:
    - DOJ 2020-04-01 → as_of 2025-04-01 → (5, 0)   (exactly 5y)
    - DOJ 2020-01-15 → as_of 2025-08-15 → (5, 7)   (5y 7m)
    - DOJ 2020-05-01 → as_of 2025-04-30 → (4, 11)  (just under 5y)
    """
    if as_of < joining_date:
        return 0, 0

    full_years = as_of.year - joining_date.year
    anniv_passed = (
        (as_of.month, as_of.day) >= (joining_date.month, joining_date.day)
    )
    if not anniv_passed:
        full_years -= 1
    full_years = max(0, full_years)

    last_anniv_year = joining_date.year + full_years
    try:
        last_anniv = date(last_anniv_year, joining_date.month, joining_date.day)
    except ValueError:
        # Feb 29 DOJ in a non-leap target year — use Feb 28.
        last_anniv = date(last_anniv_year, joining_date.month, 28)
    months = (as_of.year - last_anniv.year) * 12 + (as_of.month - last_anniv.month)
    if as_of.day < last_anniv.day:
        months -= 1
    return full_years, max(0, months)


def years_of_service(
    *, joining_date: date, as_of: date,
) -> tuple[float, int]:
    """Return (raw_years_with_decimal, rounded_years_per_act_rule)."""
    if as_of < joining_date:
        return 0.0, 0
    full_years, months = _full_and_remainder_months(joining_date, as_of)
    rounded = full_years + (1 if months >= 6 else 0)
    raw = max(0.0, (as_of - joining_date).days / 365.25)
    return round(raw, 4), rounded


def is_eligible(
    *, joining_date: date, as_of: date,
    eligibility_years: int = ELIGIBILITY_YEARS,
) -> bool:
    """True iff ≥ `eligibility_years` FULL years of continuous service.

    Uses anniversary-aware full-year count — NOT the rounded years
    (so 4y 7m is NOT eligible just because the formula would round up).
    """
    full_years, _ = _full_and_remainder_months(joining_date, as_of)
    return full_years >= eligibility_years


def compute_gratuity(
    *,
    last_basic_da_monthly: float,
    joining_date: date,
    as_of: date,
    config: Optional[GratuityConfigLike] = None,
) -> GratuityResult:
    """Apply the Payment of Gratuity Act formula.

    `last_basic_da_monthly` is the LAST DRAWN Basic+DA per month.
    Returns the eligibility flag, the rounded years, the computed
    amount, and the capped payable amount.

    No-regression: with `config=None` we use the documented constants.
    """
    eligibility_years = (
        config.eligibility_years if config is not None
        else ELIGIBILITY_YEARS
    )
    days_basis = config.days_basis if config is not None else 26
    cap = config.statutory_cap if config is not None else STATUTORY_CAP_INR

    raw, rounded = years_of_service(joining_date=joining_date, as_of=as_of)

    eligible = is_eligible(
        joining_date=joining_date, as_of=as_of,
        eligibility_years=eligibility_years,
    )

    if last_basic_da_monthly <= 0 or days_basis <= 0:
        computed = 0.0
    else:
        computed = (last_basic_da_monthly / days_basis) * 15 * rounded
    computed = round(computed, 2)

    if not eligible:
        return GratuityResult(
            last_basic_da=last_basic_da_monthly,
            days_basis=days_basis,
            raw_years=raw, rounded_years=rounded,
            is_eligible=False,
            computed_amount=computed,
            capped_amount=0.0,
            cap_applied=False,
            eligibility_years_used=eligibility_years,
            note=(
                f"Not eligible — needs {eligibility_years} years of "
                f"continuous service "
                f"(has {_full_and_remainder_months(joining_date, as_of)[0]} years)."
            ),
        )

    capped = min(computed, cap)
    return GratuityResult(
        last_basic_da=last_basic_da_monthly,
        days_basis=days_basis,
        raw_years=raw, rounded_years=rounded,
        is_eligible=True,
        computed_amount=computed,
        capped_amount=round(capped, 2),
        cap_applied=computed > cap,
        eligibility_years_used=eligibility_years,
    )


# ----- company-wide liability --------------------------------------


@dataclass
class LiabilityRow:
    employee_id: int
    name: Optional[str]
    raw_years: float
    rounded_years: int
    last_basic_da: float
    is_eligible: bool
    accruing_liability: float       # capped if cap applied
    payable_if_exits_today: float   # 0 when not eligible


def aggregate_company_liability(rows: Iterable[LiabilityRow]) -> dict:
    """Sum accruing liability across all employees. Eligible vs
    accruing-only (under-5-year) totals exposed separately.
    """
    rows = list(rows)
    total_accruing = round(sum(r.accruing_liability for r in rows), 2)
    eligible_total = round(
        sum(r.payable_if_exits_today for r in rows if r.is_eligible), 2
    )
    accruing_under_5y = round(
        sum(r.accruing_liability for r in rows if not r.is_eligible), 2
    )
    return {
        "total_employees": len(rows),
        "eligible_employees": sum(1 for r in rows if r.is_eligible),
        "total_accruing_liability": total_accruing,
        "payable_if_all_exit_today": eligible_total,
        "accruing_under_5_years": accruing_under_5y,
    }
