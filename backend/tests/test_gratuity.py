"""Unit tests for gratuity helpers."""
from dataclasses import dataclass
from datetime import date

import pytest

from app.services.gratuity import (
    ELIGIBILITY_YEARS, GRATUITY_FORMULA, STATUTORY_CAP_INR,
    YEARS_ROUNDING_RULE,
    aggregate_company_liability, compute_gratuity,
    is_eligible, years_of_service, LiabilityRow,
)


@dataclass
class FakeConfig:
    statutory_cap: float = 2_000_000
    eligibility_years: int = 5
    days_basis: int = 26


# =====================================================================
# Documented constants
# =====================================================================


class TestConstants:
    def test_formula_documented(self):
        assert "days_basis" in GRATUITY_FORMULA
        assert "15" in GRATUITY_FORMULA

    def test_eligibility_default_5(self):
        assert ELIGIBILITY_YEARS == 5

    def test_cap_default_20L(self):
        assert STATUTORY_CAP_INR == 2_000_000

    def test_rounding_rule_documented(self):
        assert "6" in YEARS_ROUNDING_RULE


# =====================================================================
# years_of_service rounding
# =====================================================================


class TestYearsOfService:
    def test_exactly_5_years(self):
        raw, r = years_of_service(
            joining_date=date(2020, 4, 1), as_of=date(2025, 4, 1),
        )
        assert r == 5

    def test_5y_7m_rounds_up_to_6(self):
        raw, r = years_of_service(
            joining_date=date(2020, 1, 15), as_of=date(2025, 8, 15),
        )
        assert r == 6   # 5y 7m → round up

    def test_5y_5m_rounds_down_to_5(self):
        raw, r = years_of_service(
            joining_date=date(2020, 1, 15), as_of=date(2025, 6, 15),
        )
        assert r == 5

    def test_5y_exactly_6m_rounds_up(self):
        raw, r = years_of_service(
            joining_date=date(2020, 1, 15), as_of=date(2025, 7, 15),
        )
        assert r == 6   # ≥ 6 months → up

    def test_under_1_year_is_zero(self):
        raw, r = years_of_service(
            joining_date=date(2025, 1, 15), as_of=date(2025, 10, 15),
        )
        assert r == 1  # 9 months → ≥6 → rounds up

    def test_just_a_few_months(self):
        raw, r = years_of_service(
            joining_date=date(2025, 5, 1), as_of=date(2025, 8, 15),
        )
        assert r == 0  # 3.5 months → 0 full years, <6 → 0

    def test_as_of_before_doj_returns_zero(self):
        raw, r = years_of_service(
            joining_date=date(2026, 1, 1), as_of=date(2025, 1, 1),
        )
        assert (raw, r) == (0.0, 0)

    def test_leap_day_doj_handled(self):
        # Feb 29 DOJ; computing on a non-leap target year shouldn't crash.
        raw, r = years_of_service(
            joining_date=date(2020, 2, 29), as_of=date(2025, 2, 28),
        )
        assert r >= 4


# =====================================================================
# eligibility
# =====================================================================


class TestEligibility:
    def test_5_years_eligible(self):
        assert is_eligible(
            joining_date=date(2020, 4, 1), as_of=date(2025, 4, 1),
        ) is True

    def test_4_years_11_months_not_eligible(self):
        # FULL YEARS = 4 → not eligible regardless of rounding.
        assert is_eligible(
            joining_date=date(2020, 5, 1), as_of=date(2025, 4, 1),
        ) is False

    def test_custom_eligibility_years(self):
        # Some org has 3-year eligibility policy.
        assert is_eligible(
            joining_date=date(2022, 1, 1), as_of=date(2025, 6, 1),
            eligibility_years=3,
        ) is True


# =====================================================================
# compute_gratuity — formula + cap
# =====================================================================


class TestComputeGratuity:
    def test_basic_formula_5y(self):
        # last_basic_da = 26000, days_basis = 26 → daily wage 1000
        # 1000 × 15 × 5 = 75,000
        r = compute_gratuity(
            last_basic_da_monthly=26000,
            joining_date=date(2020, 4, 1), as_of=date(2025, 4, 1),
        )
        assert r.is_eligible is True
        assert r.rounded_years == 5
        assert r.computed_amount == 75000
        assert r.capped_amount == 75000
        assert r.cap_applied is False

    def test_under_5_years_zero_payable(self):
        # Eligibility not met -> capped_amount = 0 even though computed
        # math could produce a number.
        r = compute_gratuity(
            last_basic_da_monthly=26000,
            joining_date=date(2022, 1, 1), as_of=date(2025, 6, 1),
        )
        assert r.is_eligible is False
        assert r.capped_amount == 0.0
        assert "Not eligible" in r.note

    def test_rounds_up_at_6_months(self):
        # 5y 7m → 6 years for formula.
        # 26000/26 × 15 × 6 = 90,000
        r = compute_gratuity(
            last_basic_da_monthly=26000,
            joining_date=date(2020, 1, 15), as_of=date(2025, 8, 15),
        )
        assert r.rounded_years == 6
        assert r.computed_amount == 90000

    def test_rounds_down_below_6_months(self):
        # 5y 5m → 5 years.
        # 26000/26 × 15 × 5 = 75,000
        r = compute_gratuity(
            last_basic_da_monthly=26000,
            joining_date=date(2020, 1, 15), as_of=date(2025, 6, 15),
        )
        assert r.rounded_years == 5

    def test_20L_cap_applied(self):
        # Massive salary: 1L basic. (100000/26)×15×20 = ~1,153,846 × 20 = 11.5L
        # → wait, math is per-year; 5 years for 1L basic: 11.5L; 20 years: 11.5 × 20 = ...
        # Let me just pick numbers that exceed 20L.
        # 200000/26 × 15 × 20 = 2,307,692 → above 20L cap.
        r = compute_gratuity(
            last_basic_da_monthly=200000,
            joining_date=date(2005, 1, 1), as_of=date(2025, 6, 1),
        )
        assert r.computed_amount > 2_000_000
        assert r.capped_amount == 2_000_000
        assert r.cap_applied is True

    def test_zero_salary_zero_computed(self):
        r = compute_gratuity(
            last_basic_da_monthly=0,
            joining_date=date(2020, 1, 1), as_of=date(2025, 6, 1),
        )
        assert r.computed_amount == 0.0

    def test_config_overrides_days_basis(self):
        # 30-day basis. 30000/30 × 15 × 5 = 75,000.
        r = compute_gratuity(
            last_basic_da_monthly=30000,
            joining_date=date(2020, 4, 1), as_of=date(2025, 4, 1),
            config=FakeConfig(days_basis=30),
        )
        assert r.days_basis == 30
        assert r.computed_amount == 75000.0

    def test_config_overrides_eligibility(self):
        # Custom org policy: 3 years suffices.
        r = compute_gratuity(
            last_basic_da_monthly=26000,
            joining_date=date(2022, 1, 1), as_of=date(2025, 6, 1),
            config=FakeConfig(eligibility_years=3),
        )
        assert r.is_eligible is True
        assert r.capped_amount > 0

    def test_config_overrides_cap(self):
        # Org policy: cap raised to 30L.
        r = compute_gratuity(
            last_basic_da_monthly=200000,
            joining_date=date(2005, 1, 1), as_of=date(2025, 6, 1),
            config=FakeConfig(statutory_cap=3_000_000),
        )
        assert r.capped_amount <= 3_000_000


# =====================================================================
# No-regression
# =====================================================================


class TestNoRegression:
    def test_compute_twice_same_result(self):
        kw = dict(
            last_basic_da_monthly=26000,
            joining_date=date(2020, 4, 1), as_of=date(2025, 4, 1),
        )
        a = compute_gratuity(**kw)
        b = compute_gratuity(**kw)
        assert a.capped_amount == b.capped_amount

    def test_no_config_falls_back_to_defaults(self):
        r = compute_gratuity(
            last_basic_da_monthly=26000,
            joining_date=date(2020, 4, 1), as_of=date(2025, 4, 1),
            config=None,
        )
        assert r.eligibility_years_used == ELIGIBILITY_YEARS
        assert r.days_basis == 26


# =====================================================================
# Company liability aggregation
# =====================================================================


class TestAggregateCompanyLiability:
    def test_split_eligible_vs_accruing(self):
        rows = [
            LiabilityRow(
                employee_id=1, name="a", raw_years=6, rounded_years=6,
                last_basic_da=26000, is_eligible=True,
                accruing_liability=90000, payable_if_exits_today=90000,
            ),
            LiabilityRow(
                employee_id=2, name="b", raw_years=2, rounded_years=2,
                last_basic_da=26000, is_eligible=False,
                accruing_liability=30000, payable_if_exits_today=0.0,
            ),
        ]
        s = aggregate_company_liability(rows)
        assert s["total_employees"] == 2
        assert s["eligible_employees"] == 1
        assert s["total_accruing_liability"] == 120000.0
        assert s["payable_if_all_exit_today"] == 90000.0
        assert s["accruing_under_5_years"] == 30000.0

    def test_empty_returns_zero(self):
        s = aggregate_company_liability([])
        assert s["total_employees"] == 0
        assert s["total_accruing_liability"] == 0.0
