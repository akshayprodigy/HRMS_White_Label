"""TDS / income-tax computation.

Pure helpers — no DB, no I/O. All decisions exposed as documented
constants so policy moves don't require code changes.

# Documented constants

## DEFAULT_REGIME = "new"
From FY 2023-24 onwards the new regime is the DEFAULT when an
employee has not made an explicit declaration. We mirror that — the
projection picks NEW when no declaration row exists for the FY, and
the UI surfaces a banner explaining the default.

## ANNUAL_PROJECTION_ROUND_TO_RUPEE = True
Section 288A of the IT Act says tax is rounded to the nearest rupee.
We do this once, at the end of `compute_annual_tax`, so intermediate
arithmetic doesn't drift.

## MARGINAL_RELIEF_ENABLED = True
Surcharge is reduced so that post-tax income immediately after
crossing a band never falls below the pre-band post-tax income —
implemented in `_apply_surcharge_with_marginal_relief`.

## SLAB_PICK_RULE  = "exact FY match → fall back to latest active"
Forces a clean per-FY mapping but tolerates HR not creating a row for
the upcoming FY immediately.

The HRA exemption follows Section 10(13A):
   exemption = min(
       actual HRA received,
       rent paid - 10% of (Basic + DA),
       50% of (Basic + DA)  if metro else 40%,
   )
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Protocol


DEFAULT_REGIME = "new"
ANNUAL_PROJECTION_ROUND_TO_RUPEE = True
MARGINAL_RELIEF_ENABLED = True


class Regime(str, Enum):
    OLD = "old"
    NEW = "new"


# ----- protocols (tests pass plain dataclasses) ----------------------


class SlabConfigLike(Protocol):
    fy: str
    slabs_json: dict
    standard_deduction_old: float
    standard_deduction_new: float
    rebate_87a_old_threshold: float
    rebate_87a_old_max: float
    rebate_87a_new_threshold: float
    rebate_87a_new_max: float
    cess_rate: float


class SectionLimitLike(Protocol):
    fy: str
    section_code: str
    limit_amount: float
    is_percentage: bool
    applies_to: str


# ----- DTOs ----------------------------------------------------------


@dataclass
class TaxComputation:
    regime: str
    gross_income: float
    standard_deduction: float
    hra_exemption: float
    chapter_via_deductions: float
    other_income: float
    previous_employer_income: float

    taxable_income: float
    tax_on_slabs: float
    rebate_87a: float
    surcharge: float
    cess: float
    total_tax: float           # rounded to rupee (288A)

    monthly_tds: float = 0.0
    notes: List[str] = field(default_factory=list)


@dataclass
class RegimeComparison:
    old: TaxComputation
    new: TaxComputation

    @property
    def better_regime(self) -> str:
        return Regime.OLD.value if self.old.total_tax < self.new.total_tax else Regime.NEW.value

    @property
    def saving(self) -> float:
        return round(abs(self.old.total_tax - self.new.total_tax), 2)


@dataclass
class TDSReconciliationRow:
    user_id: int
    employee_code: Optional[str]
    name: Optional[str]
    projected_annual_tax: float
    ytd_tds: float
    months_remaining: int
    required_monthly: float
    last_month_tds: float
    catch_up_amount: float
    status: str


# ----- FY config picker ---------------------------------------------


def pick_slab_config_for_fy(
    configs: Iterable[SlabConfigLike], fy: str,
) -> Optional[SlabConfigLike]:
    """Exact FY match → fall back to the latest active config.

    The fallback prevents a 'no slabs for FY26-27 yet' crash on the
    1st April of a new FY before HR has created the row.
    """
    exact = [c for c in configs if c.fy == fy]
    if exact:
        return exact[0]
    sorted_active = sorted(configs, key=lambda c: c.fy)
    return sorted_active[-1] if sorted_active else None


def section_limits_map(
    limits: Iterable[SectionLimitLike], fy: str,
) -> Dict[str, SectionLimitLike]:
    """Return {section_code: row} for the given FY."""
    return {row.section_code: row for row in limits if row.fy == fy}


# ----- HRA exemption -------------------------------------------------


def compute_hra_exemption(
    *,
    basic_da_annual: float,
    hra_received_annual: float,
    rent_paid_annual: float,
    metro: bool,
    metro_pct: float = 50.0,
    non_metro_pct: float = 40.0,
) -> float:
    """Section 10(13A) HRA exemption. Returns the LEAST of the three
    legs. Zero when basic_da is zero or rent paid is below 10% of basic.
    """
    if basic_da_annual <= 0 or hra_received_annual <= 0:
        return 0.0
    leg_rent = max(0.0, rent_paid_annual - 0.10 * basic_da_annual)
    pct = metro_pct if metro else non_metro_pct
    leg_pct = (pct / 100.0) * basic_da_annual
    return round(min(hra_received_annual, leg_rent, leg_pct), 2)


# ----- slab tax math ------------------------------------------------


def _tax_on_slabs(taxable_income: float, slabs: List[dict]) -> float:
    """Walk progressive slabs.

    Each slab is {"upto": int|None, "rate": float}. `upto` is inclusive.
    A `null` upto means "and above". Returns the unrounded tax amount.
    """
    if taxable_income <= 0 or not slabs:
        return 0.0
    tax = 0.0
    prev_cap = 0.0
    for slab in slabs:
        cap = slab["upto"]
        rate = float(slab["rate"]) / 100.0
        if cap is None or taxable_income <= cap:
            tax += (taxable_income - prev_cap) * rate
            return tax
        tax += (cap - prev_cap) * rate
        prev_cap = cap
    return tax


def _apply_surcharge_with_marginal_relief(
    *, tax_before_surcharge: float, taxable_income: float,
    surcharge_slabs: List[dict],
) -> float:
    """Compute surcharge with marginal relief (Sec 113 of IT Act).

    If gross income just crosses a band, the increase in total tax can
    exceed the increase in income. Marginal relief caps the surcharge so
    that doesn't happen.

    Returns surcharge amount. Slab shape mirrors `_tax_on_slabs`.
    """
    if taxable_income <= 0 or not surcharge_slabs:
        return 0.0
    rate = 0.0
    band_start = 0.0
    for slab in surcharge_slabs:
        cap = slab["upto"]
        if cap is None or taxable_income <= cap:
            rate = float(slab["rate"]) / 100.0
            break
        band_start = cap
    surcharge = tax_before_surcharge * rate

    # Compare with a tiny epsilon — rate and band_start come from JSON
    # config so they're effectively integers, but float-eq lint is right.
    epsilon = 1e-9
    if not MARGINAL_RELIEF_ENABLED or rate < epsilon or band_start < epsilon:
        return surcharge

    # Marginal relief: the additional surcharge cannot exceed the
    # excess income over the band's lower threshold.
    excess_income = taxable_income - band_start
    if surcharge > excess_income:
        return max(0.0, excess_income)
    return surcharge


# ----- annual tax computation ---------------------------------------


def _apply_rebate_87a(
    *, tax_before_rebate: float, taxable_income: float,
    threshold: float, max_rebate: float,
) -> float:
    """Returns the rebate amount (>=0). The taxable_income is checked
    against the threshold; the rebate is capped at the lower of tax
    and max_rebate.
    """
    if taxable_income > threshold:
        return 0.0
    return min(tax_before_rebate, max_rebate)


def compute_annual_tax(
    *,
    regime: str,
    gross_salary_annual: float,
    basic_da_annual: float,
    hra_received_annual: float,
    rent_paid_annual: float,
    metro: bool,
    chapter_via_deductions: float,    # 80C/80D/80CCD(1B)/etc. — already
                                       # capped to section limits by caller
    other_income_annual: float,
    previous_employer_income: float,
    slab_config: SlabConfigLike,
    metro_pct: float = 50.0,
    non_metro_pct: float = 40.0,
) -> TaxComputation:
    """Project annual tax under the chosen regime.

    - OLD regime: HRA exemption + Chapter VI-A deductions apply.
    - NEW regime: HRA exemption + chapter VI-A do NOT apply (except
      standard deduction + 80CCD(2) which we treat as outside this
      function — caller passes 0 for `chapter_via_deductions` when
      regime is NEW).
    """
    notes: List[str] = []

    standard_deduction = (
        slab_config.standard_deduction_new if regime == Regime.NEW.value
        else slab_config.standard_deduction_old
    )

    if regime == Regime.OLD.value:
        hra_exemption = compute_hra_exemption(
            basic_da_annual=basic_da_annual,
            hra_received_annual=hra_received_annual,
            rent_paid_annual=rent_paid_annual,
            metro=metro, metro_pct=metro_pct, non_metro_pct=non_metro_pct,
        )
        chapter_via = chapter_via_deductions
    else:
        hra_exemption = 0.0
        chapter_via = 0.0
        if chapter_via_deductions > 0:
            notes.append(
                "Chapter VI-A deductions ignored under new regime."
            )

    taxable_income = max(
        0.0,
        gross_salary_annual + previous_employer_income + other_income_annual
        - hra_exemption - standard_deduction - chapter_via,
    )

    slabs_key = "old" if regime == Regime.OLD.value else "new"
    slabs = slab_config.slabs_json.get(slabs_key) or []
    surcharge_key = (
        "surcharge_old" if regime == Regime.OLD.value else "surcharge_new"
    )
    surcharge_slabs = slab_config.slabs_json.get(surcharge_key) or []

    tax_on_slabs = _tax_on_slabs(taxable_income, slabs)
    rebate = _apply_rebate_87a(
        tax_before_rebate=tax_on_slabs,
        taxable_income=taxable_income,
        threshold=(
            slab_config.rebate_87a_new_threshold if regime == Regime.NEW.value
            else slab_config.rebate_87a_old_threshold
        ),
        max_rebate=(
            slab_config.rebate_87a_new_max if regime == Regime.NEW.value
            else slab_config.rebate_87a_old_max
        ),
    )
    tax_after_rebate = max(0.0, tax_on_slabs - rebate)

    surcharge = _apply_surcharge_with_marginal_relief(
        tax_before_surcharge=tax_after_rebate,
        taxable_income=taxable_income,
        surcharge_slabs=surcharge_slabs,
    )

    cess_base = tax_after_rebate + surcharge
    cess = cess_base * (slab_config.cess_rate / 100.0)

    total_tax = tax_after_rebate + surcharge + cess
    if ANNUAL_PROJECTION_ROUND_TO_RUPEE:
        total_tax = round(total_tax)

    return TaxComputation(
        regime=regime,
        gross_income=gross_salary_annual,
        standard_deduction=standard_deduction,
        hra_exemption=hra_exemption,
        chapter_via_deductions=chapter_via,
        other_income=other_income_annual,
        previous_employer_income=previous_employer_income,
        taxable_income=round(taxable_income, 2),
        tax_on_slabs=round(tax_on_slabs, 2),
        rebate_87a=round(rebate, 2),
        surcharge=round(surcharge, 2),
        cess=round(cess, 2),
        total_tax=float(total_tax),
        notes=notes,
    )


def compare_regimes(
    *,
    gross_salary_annual: float,
    basic_da_annual: float,
    hra_received_annual: float,
    rent_paid_annual: float,
    metro: bool,
    chapter_via_deductions: float,
    other_income_annual: float,
    previous_employer_income: float,
    slab_config: SlabConfigLike,
) -> RegimeComparison:
    """Compute both regimes for the same inputs. The chapter VI-A
    figure is passed AS-IS; the OLD path uses it, the NEW path zeroes
    it out internally.
    """
    old = compute_annual_tax(
        regime=Regime.OLD.value,
        gross_salary_annual=gross_salary_annual,
        basic_da_annual=basic_da_annual,
        hra_received_annual=hra_received_annual,
        rent_paid_annual=rent_paid_annual,
        metro=metro,
        chapter_via_deductions=chapter_via_deductions,
        other_income_annual=other_income_annual,
        previous_employer_income=previous_employer_income,
        slab_config=slab_config,
    )
    new = compute_annual_tax(
        regime=Regime.NEW.value,
        gross_salary_annual=gross_salary_annual,
        basic_da_annual=basic_da_annual,
        hra_received_annual=hra_received_annual,
        rent_paid_annual=rent_paid_annual,
        metro=metro,
        chapter_via_deductions=chapter_via_deductions,
        other_income_annual=other_income_annual,
        previous_employer_income=previous_employer_income,
        slab_config=slab_config,
    )
    return RegimeComparison(old=old, new=new)


# ----- chapter VI-A capping ----------------------------------------


def cap_chapter_via(
    declarations: Dict[str, float],
    limits: Dict[str, SectionLimitLike],
) -> float:
    """Sum declared investments after capping each to its section
    limit. Sections without a configured limit are passed through.

    HRA-related entries (section codes like 'hra_metro_pct') are
    excluded — they go through compute_hra_exemption instead.
    Percentage limits (is_percentage=True) are skipped here.
    """
    if not declarations:
        return 0.0
    total = 0.0
    for code, amount in declarations.items():
        if not amount or amount <= 0:
            continue
        if code.lower().startswith("hra"):
            continue
        limit = limits.get(code)
        if limit and not limit.is_percentage:
            total += min(float(amount), float(limit.limit_amount))
        else:
            total += float(amount)
    return round(total, 2)


# ----- monthly TDS / YTD catch-up -----------------------------------


def compute_monthly_tds(
    *,
    projected_annual_tax: float,
    ytd_tds_deducted: float,
    months_remaining: int,
    previous_employer_tds: float = 0.0,
) -> float:
    """Monthly TDS = (projected_annual_tax − ytd − prev_emp) / months_remaining.

    `months_remaining` includes the CURRENT payroll month. When zero
    (last month already processed) the function returns 0.
    `previous_employer_tds` is subtracted ONCE — the caller should
    pass 0 after the first month it's been honoured.

    Negative or zero remaining tax produces zero (we don't refund via
    payroll — that's a return-time refund).
    """
    if months_remaining <= 0:
        return 0.0
    remaining = (
        projected_annual_tax - ytd_tds_deducted - previous_employer_tds
    )
    if remaining <= 0:
        return 0.0
    return round(remaining / months_remaining, 2)


def reconcile_tds_for_employee(
    *,
    projected_annual_tax: float, ytd_tds: float,
    months_remaining: int, last_month_tds: float,
    user_id: int, employee_code: Optional[str] = None,
    name: Optional[str] = None,
    tolerance_rupee: float = 100.0,
) -> TDSReconciliationRow:
    """Single-employee TDS reconciliation snapshot.

    `catch_up_amount` is the per-employee gap divided by remaining
    months. Positive → under-deducted (the classic Q4 catch-up case).
    Negative → over-deducted (TDS will be refunded via return).
    """
    required_monthly = compute_monthly_tds(
        projected_annual_tax=projected_annual_tax,
        ytd_tds_deducted=ytd_tds, months_remaining=months_remaining,
    )
    gap = required_monthly - last_month_tds
    if abs(gap) <= tolerance_rupee:
        status = "ok"
    elif gap > 0:
        status = "under"
    else:
        status = "over"

    return TDSReconciliationRow(
        user_id=user_id, employee_code=employee_code, name=name,
        projected_annual_tax=round(projected_annual_tax, 2),
        ytd_tds=round(ytd_tds, 2),
        months_remaining=months_remaining,
        required_monthly=required_monthly,
        last_month_tds=round(last_month_tds, 2),
        catch_up_amount=round(gap, 2),
        status=status,
    )


# ----- FY plumbing --------------------------------------------------


def fy_for_date(d) -> str:
    """Return the Indian FY label for a date. FY24-25 covers
    1-Apr-2024 → 31-Mar-2025."""
    year = d.year
    if d.month >= 4:
        return f"{str(year)[-2:]}-{str(year + 1)[-2:]}"
    return f"{str(year - 1)[-2:]}-{str(year)[-2:]}"


def quarter_for_month(month: int) -> int:
    """Return Indian FY quarter for a calendar month (Apr=Q1)."""
    return ((month - 4) % 12) // 3 + 1


def fy_month_index(calendar_month: int) -> int:
    """Map a calendar month to its 1..12 position WITHIN the FY.
    Apr=1, May=2, ..., Mar=12. Calendar month must be 1..12.
    """
    return ((calendar_month - 4) % 12) + 1


def fy_remaining_months_inclusive(calendar_month: int) -> int:
    """Months remaining in the FY, INCLUSIVE of `calendar_month`.

    April → 12, May → 11, ..., March → 1.
    """
    return 12 - fy_month_index(calendar_month) + 1
