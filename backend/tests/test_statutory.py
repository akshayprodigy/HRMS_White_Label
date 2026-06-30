"""Unit tests for the statutory generators + reconciliation helpers.

No DB, no fixtures — pure dataclasses.
"""
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import pytest

from app.services.statutory import (
    DRIFT_TOLERANCE_INR, EPFO_ECR_DELIMITER,
    compute_ecr_row, compute_esic_row,
    current_period_window, is_under_esic,
    pf_due_date, esic_due_date, pt_due_date,
    pick_config_for_month, pick_pt_slab,
    reconcile_esic, reconcile_pf, reconcile_pt,
    render_ecr_text, render_esic_csv, render_pt_csv,
    summarize_ecr, summarize_esic,
)


@dataclass
class FakeConfig:
    id: int = 1
    effective_from: date = date(2024, 1, 1)
    pf_employee_rate: float = 12.0
    pf_employer_rate: float = 12.0
    eps_rate: float = 8.33
    pf_wage_ceiling: float = 15000.0
    eps_wage_ceiling: float = 15000.0
    edli_rate: float = 0.5
    edli_wage_ceiling: float = 15000.0
    epf_admin_rate: float = 0.5
    esic_employee_rate: float = 0.75
    esic_employer_rate: float = 3.25
    esic_wage_ceiling: float = 21000.0


@dataclass
class FakeSlab:
    state: str = "WB"
    effective_from: date = date(2023, 4, 1)
    slab_min: float = 0
    slab_max: Optional[float] = 10000
    monthly_amount: float = 0
    gender: str = "ALL"
    month_index: Optional[int] = None


# =====================================================================
# documented constants surface
# =====================================================================


class TestConstants:
    def test_ecr_delimiter(self):
        assert EPFO_ECR_DELIMITER == "#~#"

    def test_drift_tolerance_is_paise_band(self):
        # 1 paise = 0.01 INR; we allow a tiny float-rounding wiggle.
        assert 0.005 <= DRIFT_TOLERANCE_INR <= 0.05


# =====================================================================
# config picker (effective-dated)
# =====================================================================


class TestPickConfig:
    def test_no_configs(self):
        assert pick_config_for_month([], 2026, 6) is None

    def test_only_future_configs_not_picked(self):
        c = FakeConfig(effective_from=date(2027, 1, 1))
        assert pick_config_for_month([c], 2026, 6) is None

    def test_latest_effective_picked(self):
        a = FakeConfig(id=1, effective_from=date(2024, 1, 1))
        b = FakeConfig(
            id=2, effective_from=date(2025, 4, 1),
            pf_wage_ceiling=21000,
        )
        c = FakeConfig(
            id=3, effective_from=date(2026, 7, 1),    # future
            pf_wage_ceiling=25000,
        )
        chosen = pick_config_for_month([a, b, c], 2026, 6)
        assert chosen is b
        assert chosen.pf_wage_ceiling == 21000


# =====================================================================
# PF / ECR
# =====================================================================


class TestPFCeilingAndECR:
    def test_basic_under_ceiling(self):
        # Basic 12000, EPF wages = 12000 (no cap), employee 12% = 1440
        row = compute_ecr_row(
            uan="100000000001", member_name="raj",
            gross_wages=18000, basic_for_pf=12000,
            config=FakeConfig(), ncp_days=0,
        )
        assert row.epf_wages == 12000
        assert row.eps_wages == 12000
        assert row.epf_contri_remitted == pytest.approx(1440.0)
        # Employer 12% = 1440; EPS 8.33% of 12000 = 999.6 -> 999.60
        assert row.eps_contri_remitted == pytest.approx(999.6)
        # diff = 1440 - 999.6 = 440.4
        assert row.epf_eps_diff_remitted == pytest.approx(440.4, abs=0.01)

    def test_basic_above_ceiling_capped(self):
        # Basic 30000 -> EPF wages cap at 15000 -> employee 12% = 1800
        row = compute_ecr_row(
            uan="100000000002", member_name="priya",
            gross_wages=50000, basic_for_pf=30000,
            config=FakeConfig(), ncp_days=0,
        )
        assert row.epf_wages == 15000
        assert row.eps_wages == 15000
        assert row.edli_wages == 15000
        assert row.epf_contri_remitted == pytest.approx(1800.0)
        # EPS 8.33% of 15000 = 1249.50
        assert row.eps_contri_remitted == pytest.approx(1249.5)

    def test_uppercased_and_truncated_name(self):
        row = compute_ecr_row(
            uan="x", member_name="  jane doe-something-very-long-name " * 4,
            gross_wages=100, basic_for_pf=100, config=FakeConfig(),
            ncp_days=0,
        )
        assert row.member_name == row.member_name.upper()
        assert len(row.member_name) <= 85

    def test_no_uan_defaults_to_zero(self):
        row = compute_ecr_row(
            uan="", member_name="x", gross_wages=10, basic_for_pf=10,
            config=FakeConfig(), ncp_days=0,
        )
        assert row.uan == "0"

    def test_ncp_days_floored_at_zero(self):
        row = compute_ecr_row(
            uan="1", member_name="x", gross_wages=10, basic_for_pf=10,
            config=FakeConfig(), ncp_days=-5,
        )
        assert row.ncp_days == 0

    def test_render_uses_pipe_tilde_pipe_delimiter(self):
        row = compute_ecr_row(
            uan="123", member_name="raj",
            gross_wages=25000, basic_for_pf=15000,
            config=FakeConfig(), ncp_days=0,
        )
        text = render_ecr_text([row])
        # 11 cells, delimiter occurs 10 times per line.
        line = text.strip().split("\n")[0]
        assert line.count(EPFO_ECR_DELIMITER) == 10
        assert line.startswith("123" + EPFO_ECR_DELIMITER + "RAJ")

    def test_render_empty_input_gives_empty_string(self):
        assert render_ecr_text([]) == ""

    def test_summary_totals(self):
        r1 = compute_ecr_row(uan="1", member_name="a", gross_wages=10000,
                             basic_for_pf=10000, config=FakeConfig(), ncp_days=0)
        r2 = compute_ecr_row(uan="2", member_name="b", gross_wages=30000,
                             basic_for_pf=20000, config=FakeConfig(), ncp_days=0)
        s = summarize_ecr([r1, r2])
        assert s["employee_count"] == 2
        # r2's EPF wages capped at 15000
        assert s["total_epf_wages"] == pytest.approx(10000 + 15000)


# =====================================================================
# ESIC mid-period continuation
# =====================================================================


class TestESICContribPeriod:
    def test_april_in_april_sep_period(self):
        s, e = current_period_window(date(2026, 4, 5))
        assert s == date(2026, 4, 1) and e == date(2026, 9, 30)

    def test_september_in_april_sep_period(self):
        s, e = current_period_window(date(2026, 9, 30))
        assert (s, e) == (date(2026, 4, 1), date(2026, 9, 30))

    def test_october_starts_new_period(self):
        s, e = current_period_window(date(2026, 10, 1))
        assert s == date(2026, 10, 1) and e == date(2027, 3, 31)

    def test_january_still_in_oct_march_period(self):
        s, e = current_period_window(date(2027, 1, 15))
        assert s == date(2026, 10, 1) and e == date(2027, 3, 31)


class TestESICCoverageDecision:
    def test_below_ceiling_covered(self):
        assert is_under_esic(
            gross_wages_this_month=18000,
            config=FakeConfig(),
            payroll_month=date(2026, 6, 1),
            continuation_until=None,
        ) is True

    def test_above_ceiling_not_covered_no_continuation(self):
        assert is_under_esic(
            gross_wages_this_month=22000,
            config=FakeConfig(),
            payroll_month=date(2026, 6, 1),
            continuation_until=None,
        ) is False

    def test_above_ceiling_but_continuation_active(self):
        # Hike pushed gross to 25k mid-period. Continuation date set to
        # period-end keeps them covered.
        assert is_under_esic(
            gross_wages_this_month=25000,
            config=FakeConfig(),
            payroll_month=date(2026, 6, 1),
            continuation_until=date(2026, 9, 30),
        ) is True

    def test_continuation_expired_then_dropped(self):
        # Past the continuation_until -> wages decide.
        assert is_under_esic(
            gross_wages_this_month=25000,
            config=FakeConfig(),
            payroll_month=date(2026, 10, 1),
            continuation_until=date(2026, 9, 30),
        ) is False

    def test_exactly_at_ceiling_is_covered(self):
        assert is_under_esic(
            gross_wages_this_month=21000,
            config=FakeConfig(),
            payroll_month=date(2026, 6, 1),
            continuation_until=None,
        ) is True


class TestESICRowAndCSV:
    def test_employee_and_employer_rates(self):
        r = compute_esic_row(
            ip_number="ESIC1", name="a", days_worked=30,
            gross_wages=20000, config=FakeConfig(),
        )
        assert r.employee_contribution == pytest.approx(150.0)   # 0.75%
        assert r.employer_contribution == pytest.approx(650.0)   # 3.25%

    def test_csv_header_present(self):
        r = compute_esic_row(
            ip_number="1", name="a", days_worked=30,
            gross_wages=10000, config=FakeConfig(),
        )
        csv_text = render_esic_csv([r])
        assert "IP Number" in csv_text.split("\n")[0]

    def test_summary_totals_match(self):
        r1 = compute_esic_row(ip_number="1", name="a", days_worked=30,
                              gross_wages=20000, config=FakeConfig())
        r2 = compute_esic_row(ip_number="2", name="b", days_worked=15,
                              gross_wages=10000, config=FakeConfig())
        s = summarize_esic([r1, r2])
        assert s["employee_count"] == 2
        assert s["total_gross_wages"] == 30000
        assert s["total_employee_contribution"] == pytest.approx(225.0)


# =====================================================================
# Professional Tax (state slab picker)
# =====================================================================


class TestPTSlabPick:
    def _wb_slabs(self):
        return [
            FakeSlab(state="WB", effective_from=date(2023, 4, 1),
                     slab_min=0, slab_max=10000, monthly_amount=0),
            FakeSlab(state="WB", effective_from=date(2023, 4, 1),
                     slab_min=10001, slab_max=15000, monthly_amount=110),
            FakeSlab(state="WB", effective_from=date(2023, 4, 1),
                     slab_min=15001, slab_max=25000, monthly_amount=130),
            FakeSlab(state="WB", effective_from=date(2023, 4, 1),
                     slab_min=25001, slab_max=40000, monthly_amount=150),
            FakeSlab(state="WB", effective_from=date(2023, 4, 1),
                     slab_min=40001, slab_max=None, monthly_amount=200),
        ]

    def test_picks_correct_slab_for_gross(self):
        s = pick_pt_slab(
            self._wb_slabs(), state="WB", year=2026, month=6,
            gross_for_pt=22000,
        )
        assert s is not None and s.monthly_amount == 130

    def test_picks_top_slab_when_above_max(self):
        s = pick_pt_slab(
            self._wb_slabs(), state="WB", year=2026, month=6,
            gross_for_pt=50000,
        )
        assert s is not None and s.monthly_amount == 200

    def test_zero_slab_when_under_threshold(self):
        s = pick_pt_slab(
            self._wb_slabs(), state="WB", year=2026, month=6,
            gross_for_pt=8000,
        )
        assert s is not None and s.monthly_amount == 0

    def test_returns_none_for_state_with_no_rows(self):
        s = pick_pt_slab(
            self._wb_slabs(), state="TN", year=2026, month=6,
            gross_for_pt=22000,
        )
        assert s is None

    def test_latest_effective_version_wins(self):
        # Two versions for WB. Newer (2025) has a different amount.
        slabs = [
            FakeSlab(state="WB", effective_from=date(2023, 4, 1),
                     slab_min=15001, slab_max=25000, monthly_amount=130),
            FakeSlab(state="WB", effective_from=date(2025, 4, 1),
                     slab_min=15001, slab_max=25000, monthly_amount=170),
        ]
        s = pick_pt_slab(slabs, state="WB", year=2026, month=6,
                         gross_for_pt=22000)
        assert s is not None and s.monthly_amount == 170

    def test_month_specific_overrides_default(self):
        # Maharashtra: ₹300 in Feb, ₹200 in other months for top slab.
        slabs = [
            FakeSlab(state="MH", effective_from=date(2023, 4, 1),
                     slab_min=10001, slab_max=None, monthly_amount=200,
                     month_index=None),
            FakeSlab(state="MH", effective_from=date(2023, 4, 1),
                     slab_min=10001, slab_max=None, monthly_amount=300,
                     month_index=2),
        ]
        feb = pick_pt_slab(slabs, state="MH", year=2026, month=2,
                           gross_for_pt=50000)
        jan = pick_pt_slab(slabs, state="MH", year=2026, month=1,
                           gross_for_pt=50000)
        assert feb is not None and feb.monthly_amount == 300
        assert jan is not None and jan.monthly_amount == 200

    def test_gender_specific_pref_over_all(self):
        slabs = [
            FakeSlab(state="KA", effective_from=date(2023, 4, 1),
                     slab_min=0, slab_max=None, monthly_amount=200,
                     gender="ALL"),
            FakeSlab(state="KA", effective_from=date(2023, 4, 1),
                     slab_min=0, slab_max=None, monthly_amount=0,
                     gender="F"),
        ]
        female = pick_pt_slab(slabs, state="KA", year=2026, month=6,
                              gross_for_pt=50000, gender="F")
        male = pick_pt_slab(slabs, state="KA", year=2026, month=6,
                            gross_for_pt=50000, gender="M")
        assert female is not None and female.monthly_amount == 0
        assert male is not None and male.monthly_amount == 200

    def test_future_effective_not_picked(self):
        slabs = [
            FakeSlab(state="WB", effective_from=date(2027, 4, 1),
                     slab_min=0, slab_max=None, monthly_amount=999),
        ]
        assert pick_pt_slab(slabs, state="WB", year=2026, month=6,
                            gross_for_pt=22000) is None


class TestRenderPTCsv:
    def test_per_employee_rows(self):
        text = render_pt_csv([
            {"employee_id": "E1", "name": "A", "gender": "M",
             "gross_wages": 22000, "pt_amount": 130},
            {"employee_id": "E2", "name": "B", "gender": "F",
             "gross_wages": 50000, "pt_amount": 0},
        ])
        lines = text.strip().split("\n")
        assert lines[0].startswith("Employee ID")
        assert "E1" in lines[1] and "130" in lines[1]


# =====================================================================
# reconciliation drift detection
# =====================================================================


class TestPFReconcile:
    def test_no_drift_when_match(self):
        # Basic 20000 -> EPF wages 15000 -> employee 1800, employer 1800
        findings = reconcile_pf(
            actual_employee_pf=1800, actual_employer_pf=1800,
            basic_for_pf=20000, config=FakeConfig(),
            user_id=1,
        )
        assert findings == []

    def test_drift_under_employee_pf(self):
        # Expected 1800, actual 1000 -> -800 drift
        findings = reconcile_pf(
            actual_employee_pf=1000, actual_employer_pf=1800,
            basic_for_pf=20000, config=FakeConfig(),
            user_id=42, employee_code="E42",
        )
        assert len(findings) == 1
        f = findings[0]
        assert f.stream == "epf_employee"
        assert f.expected == pytest.approx(1800)
        assert f.actual == 1000
        assert f.diff == pytest.approx(-800)

    def test_rounding_within_tolerance_suppressed(self):
        findings = reconcile_pf(
            actual_employee_pf=1800.005,
            actual_employer_pf=1800.0,
            basic_for_pf=20000, config=FakeConfig(),
            user_id=1,
        )
        assert findings == []


class TestESICReconcile:
    def test_no_drift_when_covered_and_matching(self):
        findings = reconcile_esic(
            actual_employee_esi=150, actual_employer_esi=650,
            gross_wages=20000, config=FakeConfig(),
            is_covered=True, user_id=1,
        )
        assert findings == []

    def test_drift_when_not_covered_but_charged(self):
        findings = reconcile_esic(
            actual_employee_esi=100, actual_employer_esi=500,
            gross_wages=30000, config=FakeConfig(),
            is_covered=False, user_id=1,
        )
        assert len(findings) == 2
        streams = sorted(f.stream for f in findings)
        assert streams == ["esic_employee", "esic_employer"]
        assert all(f.expected == 0.0 for f in findings)
        assert findings[0].note  # the note about being charged-but-uncovered

    def test_drift_when_covered_but_amount_wrong(self):
        findings = reconcile_esic(
            actual_employee_esi=300, actual_employer_esi=650,
            gross_wages=20000, config=FakeConfig(),
            is_covered=True, user_id=1,
        )
        # Only employee side drifted (150 expected, 300 actual)
        assert len(findings) == 1
        assert findings[0].stream == "esic_employee"
        assert findings[0].diff == pytest.approx(150)


class TestPTReconcile:
    def test_no_drift(self):
        assert reconcile_pt(actual_pt=130, expected_pt=130, user_id=1) == []

    def test_drift(self):
        findings = reconcile_pt(actual_pt=110, expected_pt=130, user_id=1)
        assert len(findings) == 1
        assert findings[0].stream == "pt"
        assert findings[0].diff == pytest.approx(-20)


# =====================================================================
# due-date helpers
# =====================================================================


class TestDueDates:
    def test_pf_due_15th_of_next_month(self):
        assert pf_due_date(2026, 6) == date(2026, 7, 15)

    def test_pf_due_year_boundary(self):
        assert pf_due_date(2026, 12) == date(2027, 1, 15)

    def test_esic_due_15th_of_next_month(self):
        assert esic_due_date(2026, 6) == date(2026, 7, 15)

    def test_pt_default_state_21st(self):
        assert pt_due_date(2026, 6, "WB") == date(2026, 7, 21)

    def test_pt_karnataka_20th(self):
        assert pt_due_date(2026, 6, "KA") == date(2026, 7, 20)

    def test_pt_maharashtra_end_of_next_month_proxy(self):
        # Returns the 28th as a state-end proxy that always exists.
        assert pt_due_date(2026, 6, "MH") == date(2026, 7, 28)
