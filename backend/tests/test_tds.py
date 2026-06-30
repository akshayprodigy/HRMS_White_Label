"""Unit tests for TDS computation helpers.

No DB, no fixtures — plain dataclasses passed in.

Slab values used in tests reflect FY24-25 budget; precise rates aren't
the test target, the LOGIC is.
"""
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional

import pytest

from app.services.tds import (
    ANNUAL_PROJECTION_ROUND_TO_RUPEE, DEFAULT_REGIME,
    MARGINAL_RELIEF_ENABLED, Regime,
    cap_chapter_via, compare_regimes, compute_annual_tax,
    compute_hra_exemption, compute_monthly_tds,
    fy_for_date, fy_month_index, fy_remaining_months_inclusive,
    pick_slab_config_for_fy, quarter_for_month,
    reconcile_tds_for_employee, section_limits_map,
)


@dataclass
class FakeSlabConfig:
    fy: str = "24-25"
    name: str = "FY24-25"
    standard_deduction_old: float = 50000
    standard_deduction_new: float = 75000
    rebate_87a_old_threshold: float = 500000
    rebate_87a_old_max: float = 12500
    rebate_87a_new_threshold: float = 700000
    rebate_87a_new_max: float = 25000
    cess_rate: float = 4.0
    # Approximate FY24-25 slabs (the test cares about LOGIC, not exact rates).
    slabs_json: dict = field(default_factory=lambda: {
        "old": [
            {"upto": 250000, "rate": 0},
            {"upto": 500000, "rate": 5},
            {"upto": 1000000, "rate": 20},
            {"upto": None, "rate": 30},
        ],
        "new": [
            {"upto": 300000, "rate": 0},
            {"upto": 700000, "rate": 5},
            {"upto": 1000000, "rate": 10},
            {"upto": 1200000, "rate": 15},
            {"upto": 1500000, "rate": 20},
            {"upto": None, "rate": 30},
        ],
        "surcharge_old": [
            {"upto": 5000000, "rate": 0},
            {"upto": 10000000, "rate": 10},
            {"upto": 20000000, "rate": 15},
            {"upto": 50000000, "rate": 25},
            {"upto": None, "rate": 37},
        ],
        "surcharge_new": [
            {"upto": 5000000, "rate": 0},
            {"upto": 10000000, "rate": 10},
            {"upto": 20000000, "rate": 15},
            {"upto": None, "rate": 25},   # new regime caps at 25%
        ],
    })


@dataclass
class FakeSectionLimit:
    fy: str = "24-25"
    section_code: str = "80C"
    limit_amount: float = 150000
    is_percentage: bool = False
    applies_to: str = "BOTH"


# =====================================================================
# Documented constants surface
# =====================================================================


class TestConstants:
    def test_default_regime(self):
        assert DEFAULT_REGIME == "new"

    def test_round_to_rupee_flag(self):
        assert ANNUAL_PROJECTION_ROUND_TO_RUPEE is True

    def test_marginal_relief_on(self):
        assert MARGINAL_RELIEF_ENABLED is True


# =====================================================================
# FY plumbing
# =====================================================================


class TestFYPlumbing:
    def test_fy_for_april(self):
        assert fy_for_date(date(2024, 4, 5)) == "24-25"

    def test_fy_for_march(self):
        assert fy_for_date(date(2025, 3, 31)) == "24-25"

    def test_fy_for_april_next(self):
        assert fy_for_date(date(2025, 4, 1)) == "25-26"

    def test_quarter_apr_q1(self):
        assert quarter_for_month(4) == 1
        assert quarter_for_month(6) == 1

    def test_quarter_jul_q2(self):
        assert quarter_for_month(7) == 2
        assert quarter_for_month(9) == 2

    def test_quarter_oct_q3(self):
        assert quarter_for_month(10) == 3

    def test_quarter_jan_q4(self):
        assert quarter_for_month(1) == 4
        assert quarter_for_month(3) == 4

    def test_fy_month_index(self):
        assert fy_month_index(4) == 1
        assert fy_month_index(3) == 12

    def test_remaining_months_inclusive(self):
        assert fy_remaining_months_inclusive(4) == 12
        assert fy_remaining_months_inclusive(3) == 1
        assert fy_remaining_months_inclusive(1) == 3   # Jan,Feb,Mar


# =====================================================================
# Config picker
# =====================================================================


class TestSlabConfigPicker:
    def test_exact_fy_picked(self):
        a = FakeSlabConfig(fy="23-24")
        b = FakeSlabConfig(fy="24-25")
        c = FakeSlabConfig(fy="25-26")
        chosen = pick_slab_config_for_fy([a, b, c], "24-25")
        assert chosen is b

    def test_fallback_to_latest_when_no_exact(self):
        a = FakeSlabConfig(fy="23-24")
        b = FakeSlabConfig(fy="24-25")
        chosen = pick_slab_config_for_fy([a, b], "26-27")
        assert chosen is b

    def test_empty_returns_none(self):
        assert pick_slab_config_for_fy([], "24-25") is None


# =====================================================================
# HRA exemption
# =====================================================================


class TestHRAExemption:
    def test_metro_least_of_three(self):
        # basic_da=600k, hra_received=300k, rent=240k, metro
        # leg1 = 300k
        # leg2 = 240k - 60k = 180k
        # leg3 = 50% * 600k = 300k
        # min = 180k
        assert compute_hra_exemption(
            basic_da_annual=600000, hra_received_annual=300000,
            rent_paid_annual=240000, metro=True,
        ) == 180000.0

    def test_non_metro_40_pct(self):
        # basic_da=600k, hra=300k, rent=600k, non-metro
        # leg1 = 300k; leg2 = 600k-60k = 540k; leg3 = 40%*600k = 240k
        # min = 240k
        assert compute_hra_exemption(
            basic_da_annual=600000, hra_received_annual=300000,
            rent_paid_annual=600000, metro=False,
        ) == 240000.0

    def test_rent_below_10pct_zero(self):
        # rent 50k, 10% of basic = 60k; leg2 = max(0, 50k-60k) = 0
        # so min = 0
        e = compute_hra_exemption(
            basic_da_annual=600000, hra_received_annual=300000,
            rent_paid_annual=50000, metro=True,
        )
        assert e == 0.0

    def test_zero_basic_returns_zero(self):
        assert compute_hra_exemption(
            basic_da_annual=0, hra_received_annual=300000,
            rent_paid_annual=240000, metro=True,
        ) == 0.0

    def test_zero_hra_received_returns_zero(self):
        assert compute_hra_exemption(
            basic_da_annual=600000, hra_received_annual=0,
            rent_paid_annual=240000, metro=True,
        ) == 0.0


# =====================================================================
# Chapter VI-A capping
# =====================================================================


class TestChapterViA:
    def test_caps_at_limit(self):
        limits = {"80C": FakeSectionLimit(section_code="80C", limit_amount=150000)}
        v = cap_chapter_via({"80C": 200000}, limits)
        assert v == 150000.0

    def test_uncapped_when_no_limit_row(self):
        v = cap_chapter_via({"80E": 100000}, {})
        assert v == 100000.0

    def test_ignores_hra_keys(self):
        v = cap_chapter_via({"hra_metro_pct": 50, "80C": 100000},
                            {"80C": FakeSectionLimit(section_code="80C", limit_amount=150000)})
        assert v == 100000.0

    def test_skips_percentage_limits(self):
        # Pretend 80CCD(2) has is_percentage=True (shouldn't be summed as amount)
        limits = {"80CCD_2": FakeSectionLimit(section_code="80CCD_2", limit_amount=10, is_percentage=True)}
        # Caller passed an explicit amount — uncapped pass-through.
        v = cap_chapter_via({"80CCD_2": 50000}, limits)
        assert v == 50000.0


# =====================================================================
# 87A rebate boundary
# =====================================================================


class TestRebate87A:
    def test_old_regime_under_5L_rebated(self):
        # Old regime: taxable = 500_000 - 50_000 std - some = ~400_000
        # Tax on slabs: 250k @0 + 150k @5% = 7,500. < 12,500 cap → all
        # rebated → final tax = 0
        c = compute_annual_tax(
            regime=Regime.OLD.value,
            gross_salary_annual=500000, basic_da_annual=250000,
            hra_received_annual=0, rent_paid_annual=0, metro=False,
            chapter_via_deductions=0, other_income_annual=0,
            previous_employer_income=0, slab_config=FakeSlabConfig(),
        )
        assert c.total_tax == 0

    def test_old_regime_above_5L_no_rebate(self):
        # Gross = 800k → taxable ~ 750k. Above threshold (500k) → no rebate.
        c = compute_annual_tax(
            regime=Regime.OLD.value,
            gross_salary_annual=800000, basic_da_annual=400000,
            hra_received_annual=0, rent_paid_annual=0, metro=False,
            chapter_via_deductions=0, other_income_annual=0,
            previous_employer_income=0, slab_config=FakeSlabConfig(),
        )
        assert c.rebate_87a == 0
        assert c.total_tax > 0

    def test_new_regime_under_7L_rebated(self):
        # taxable_income = 700_000 - 75_000 std = 625_000.
        # Slabs new: 300k@0 + 325k@5% = 16,250.
        # 87A new threshold = 700k → applies, max 25_000 → all rebated.
        c = compute_annual_tax(
            regime=Regime.NEW.value,
            gross_salary_annual=700000, basic_da_annual=0,
            hra_received_annual=0, rent_paid_annual=0, metro=False,
            chapter_via_deductions=0, other_income_annual=0,
            previous_employer_income=0, slab_config=FakeSlabConfig(),
        )
        assert c.total_tax == 0

    def test_new_regime_above_threshold_no_rebate(self):
        # Gross 800k → taxable 725k; above 700k threshold → no rebate.
        c = compute_annual_tax(
            regime=Regime.NEW.value,
            gross_salary_annual=800000, basic_da_annual=0,
            hra_received_annual=0, rent_paid_annual=0, metro=False,
            chapter_via_deductions=0, other_income_annual=0,
            previous_employer_income=0, slab_config=FakeSlabConfig(),
        )
        assert c.rebate_87a == 0
        assert c.total_tax > 0


# =====================================================================
# Old vs new regime comparison
# =====================================================================


class TestRegimeComparison:
    def test_old_better_when_lots_of_deductions(self):
        # Gross 15L, lots of 80C+80D+HRA → old should win.
        cmp = compare_regimes(
            gross_salary_annual=1500000, basic_da_annual=750000,
            hra_received_annual=300000, rent_paid_annual=360000, metro=True,
            chapter_via_deductions=200000,
            other_income_annual=0, previous_employer_income=0,
            slab_config=FakeSlabConfig(),
        )
        assert cmp.better_regime == "old"
        assert cmp.saving > 0

    def test_new_better_when_no_deductions(self):
        cmp = compare_regimes(
            gross_salary_annual=1500000, basic_da_annual=750000,
            hra_received_annual=0, rent_paid_annual=0, metro=False,
            chapter_via_deductions=0,
            other_income_annual=0, previous_employer_income=0,
            slab_config=FakeSlabConfig(),
        )
        # New caps at 25% surcharge in our fixture but main driver is
        # the friendlier slabs at this income level.
        assert cmp.better_regime == "new"

    def test_new_ignores_chapter_via(self):
        c = compute_annual_tax(
            regime=Regime.NEW.value,
            gross_salary_annual=1200000, basic_da_annual=600000,
            hra_received_annual=0, rent_paid_annual=0, metro=False,
            chapter_via_deductions=200000,
            other_income_annual=0, previous_employer_income=0,
            slab_config=FakeSlabConfig(),
        )
        assert c.chapter_via_deductions == 0
        assert any("new regime" in n for n in c.notes)


# =====================================================================
# Surcharge + marginal relief
# =====================================================================


class TestSurcharge:
    def test_no_surcharge_below_50L(self):
        c = compute_annual_tax(
            regime=Regime.OLD.value,
            gross_salary_annual=4000000, basic_da_annual=2000000,
            hra_received_annual=0, rent_paid_annual=0, metro=False,
            chapter_via_deductions=0, other_income_annual=0,
            previous_employer_income=0, slab_config=FakeSlabConfig(),
        )
        assert c.surcharge == 0

    def test_surcharge_above_50L(self):
        c = compute_annual_tax(
            regime=Regime.OLD.value,
            gross_salary_annual=6000000, basic_da_annual=3000000,
            hra_received_annual=0, rent_paid_annual=0, metro=False,
            chapter_via_deductions=0, other_income_annual=0,
            previous_employer_income=0, slab_config=FakeSlabConfig(),
        )
        assert c.surcharge > 0

    def test_marginal_relief_when_just_over_50L(self):
        # Income just 1 lakh over 50L should not be hit with a multi-lakh
        # surcharge that exceeds the income excess.
        c = compute_annual_tax(
            regime=Regime.OLD.value,
            gross_salary_annual=5100000, basic_da_annual=2500000,
            hra_received_annual=0, rent_paid_annual=0, metro=False,
            chapter_via_deductions=0, other_income_annual=0,
            previous_employer_income=0, slab_config=FakeSlabConfig(),
        )
        # taxable ~5,050,000. Surcharge capped at excess over 50L.
        assert c.surcharge <= 50000 + 1   # 1 paise wiggle


# =====================================================================
# Monthly TDS + YTD catch-up
# =====================================================================


class TestMonthlyTDS:
    def test_first_month_no_ytd(self):
        # 1.2 lakh annual tax / 12 months = 10,000/mo
        m = compute_monthly_tds(
            projected_annual_tax=120000, ytd_tds_deducted=0,
            months_remaining=12,
        )
        assert m == 10000.0

    def test_q4_catchup_when_under_deducted(self):
        # 1.2L annual, only 40k deducted in first 9 months → owe 80k in
        # 3 months = 26,666.67/mo (the headline Q4 catch-up case).
        m = compute_monthly_tds(
            projected_annual_tax=120000, ytd_tds_deducted=40000,
            months_remaining=3,
        )
        assert m == pytest.approx(26666.67, abs=0.01)

    def test_zero_when_already_overpaid(self):
        # 1L annual, 1.2L already deducted -> over -> 0 this month
        m = compute_monthly_tds(
            projected_annual_tax=100000, ytd_tds_deducted=120000,
            months_remaining=3,
        )
        assert m == 0.0

    def test_previous_employer_tds_subtracted(self):
        # 1L annual, 20k YTD, 30k prev employer → owe 50k in 5 mo = 10k
        m = compute_monthly_tds(
            projected_annual_tax=100000, ytd_tds_deducted=20000,
            months_remaining=5, previous_employer_tds=30000,
        )
        assert m == 10000.0

    def test_zero_when_months_remaining_is_zero(self):
        m = compute_monthly_tds(
            projected_annual_tax=100000, ytd_tds_deducted=0,
            months_remaining=0,
        )
        assert m == 0.0


# =====================================================================
# Per-employee reconciliation
# =====================================================================


class TestReconciliation:
    def test_ok_when_within_tolerance(self):
        r = reconcile_tds_for_employee(
            projected_annual_tax=120000, ytd_tds=10000,
            months_remaining=11, last_month_tds=10000,
            user_id=1, tolerance_rupee=100,
        )
        assert r.status == "ok"

    def test_under_deducted(self):
        # required = (120k - 10k) / 11 = 10000; actual 5000 → under 5000
        r = reconcile_tds_for_employee(
            projected_annual_tax=120000, ytd_tds=10000,
            months_remaining=11, last_month_tds=5000,
            user_id=1, tolerance_rupee=100,
        )
        assert r.status == "under"
        assert r.catch_up_amount == 5000

    def test_over_deducted(self):
        r = reconcile_tds_for_employee(
            projected_annual_tax=120000, ytd_tds=10000,
            months_remaining=11, last_month_tds=15000,
            user_id=1, tolerance_rupee=100,
        )
        assert r.status == "over"
        assert r.catch_up_amount == -5000


# =====================================================================
# No-regression contracts
# =====================================================================


class TestNoRegression:
    def test_idempotent_compute(self):
        kw = dict(
            regime=Regime.NEW.value,
            gross_salary_annual=1500000, basic_da_annual=750000,
            hra_received_annual=300000, rent_paid_annual=240000, metro=True,
            chapter_via_deductions=200000, other_income_annual=0,
            previous_employer_income=0, slab_config=FakeSlabConfig(),
        )
        a = compute_annual_tax(**kw)
        b = compute_annual_tax(**kw)
        assert a.total_tax == b.total_tax
        assert a.taxable_income == b.taxable_income

    def test_zero_income_zero_tax(self):
        c = compute_annual_tax(
            regime=Regime.OLD.value,
            gross_salary_annual=0, basic_da_annual=0,
            hra_received_annual=0, rent_paid_annual=0, metro=False,
            chapter_via_deductions=0, other_income_annual=0,
            previous_employer_income=0, slab_config=FakeSlabConfig(),
        )
        assert c.total_tax == 0
        assert c.taxable_income == 0
