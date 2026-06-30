"""Unit tests for revision effective-dating + arrear computation.

Pure helpers — no DB, plain dataclasses passed in.
"""
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import pytest

from app.services.revisions import (
    ARREAR_BASIS,
    MID_MONTH_RULE,
    RevStatus,
    band_warning_for,
    compute_arrears_for_revision,
    derive_hike,
    effective_components_for_month,
    is_effective_for_month,
    months_between_exclusive,
)


@dataclass
class FakeRevision:
    id: int = 1
    employee_id: int = 100
    status: str = RevStatus.APPLIED.value
    effective_from: date = date(2026, 6, 1)
    old_basic: float = 20000
    old_conveyance: float = 6000
    old_hra: float = 10000
    old_other_allowance: float = 4000
    old_ctc: float = 40000
    new_basic: float = 24000
    new_conveyance: float = 7200
    new_hra: float = 12000
    new_other_allowance: float = 4800
    new_ctc: float = 48000
    arrears_run_id: Optional[int] = None


# --------------------------- documented constants ---------------------


class TestConstants:
    def test_mid_month_rule_documented(self):
        assert "full_month" in MID_MONTH_RULE
        assert "effective_from" in MID_MONTH_RULE

    def test_arrear_basis_documented(self):
        assert "monthly" in ARREAR_BASIS
        assert "delta" in ARREAR_BASIS


# --------------------------- is_effective_for_month -------------------


class TestIsEffectiveForMonth:
    def test_same_month_mid_month_effective(self):
        # eff = 2026-06-15, target = 2026-06 -> True (whole month new)
        assert is_effective_for_month(date(2026, 6, 15), 2026, 6) is True

    def test_first_of_month_effective(self):
        # eff = 2026-06-01, target = 2026-06 -> True
        assert is_effective_for_month(date(2026, 6, 1), 2026, 6) is True

    def test_month_before_effective(self):
        assert is_effective_for_month(date(2026, 6, 15), 2026, 5) is False

    def test_year_boundary(self):
        # eff = 2026-01-15, target Dec 2025 -> False
        assert is_effective_for_month(date(2026, 1, 15), 2025, 12) is False
        # target Jan 2026 -> True
        assert is_effective_for_month(date(2026, 1, 15), 2026, 1) is True


# --------------------------- months_between_exclusive -----------------


class TestMonthsBetween:
    def test_zero_when_same_month(self):
        assert months_between_exclusive(date(2026, 6, 1), date(2026, 6, 30)) == 0

    def test_single_month(self):
        assert months_between_exclusive(date(2026, 5, 1), date(2026, 6, 1)) == 1

    def test_year_crossing(self):
        assert months_between_exclusive(date(2025, 11, 1), date(2026, 2, 1)) == 3

    def test_negative_when_end_before_start(self):
        assert months_between_exclusive(date(2026, 6, 1), date(2026, 5, 1)) == -1


# --------------------------- effective_components_for_month -----------


class TestEffectiveComponents:
    def test_no_regression_when_no_revisions(self):
        c = effective_components_for_month(
            employee_basic=10000, employee_conveyance=3000,
            employee_hra=5000, employee_other_allowance=2000,
            revisions=[], year=2026, month=6,
        )
        assert c.source == "employee_master"
        assert c.revision_id is None
        assert c.basic == 10000
        assert c.ctc == 20000

    def test_applied_revision_picked_when_effective(self):
        r = FakeRevision(id=7, effective_from=date(2026, 6, 1))
        c = effective_components_for_month(
            employee_basic=10000, employee_conveyance=3000,
            employee_hra=5000, employee_other_allowance=2000,
            revisions=[r], year=2026, month=6,
        )
        assert c.source == "revision:7"
        assert c.revision_id == 7
        assert c.basic == 24000

    def test_approved_but_not_applied_is_ignored(self):
        r = FakeRevision(
            id=7, status=RevStatus.APPROVED.value,
            effective_from=date(2026, 6, 1),
        )
        c = effective_components_for_month(
            employee_basic=10000, employee_conveyance=3000,
            employee_hra=5000, employee_other_allowance=2000,
            revisions=[r], year=2026, month=6,
        )
        assert c.source == "employee_master"

    def test_future_revision_ignored(self):
        r = FakeRevision(id=7, effective_from=date(2026, 7, 1))
        c = effective_components_for_month(
            employee_basic=10000, employee_conveyance=3000,
            employee_hra=5000, employee_other_allowance=2000,
            revisions=[r], year=2026, month=6,
        )
        assert c.source == "employee_master"

    def test_latest_of_multiple_picked(self):
        r1 = FakeRevision(
            id=1, effective_from=date(2026, 3, 1),
            new_basic=22000, new_conveyance=6600, new_hra=11000,
            new_other_allowance=4400, new_ctc=44000,
        )
        r2 = FakeRevision(
            id=2, effective_from=date(2026, 6, 1),
            new_basic=24000, new_conveyance=7200, new_hra=12000,
            new_other_allowance=4800, new_ctc=48000,
        )
        c = effective_components_for_month(
            employee_basic=10000, employee_conveyance=3000,
            employee_hra=5000, employee_other_allowance=2000,
            revisions=[r1, r2], year=2026, month=6,
        )
        assert c.revision_id == 2
        assert c.basic == 24000

    def test_mid_month_effective_applies_full_month(self):
        # eff = 2026-06-15, target = 2026-06 → new components apply
        # to the WHOLE June payroll.
        r = FakeRevision(id=9, effective_from=date(2026, 6, 15))
        c = effective_components_for_month(
            employee_basic=10000, employee_conveyance=3000,
            employee_hra=5000, employee_other_allowance=2000,
            revisions=[r], year=2026, month=6,
        )
        assert c.revision_id == 9


# --------------------------- arrears ---------------------------------


class TestArrears:
    def test_no_arrears_for_future_revision(self):
        # Effective Jul 2026, draft Jun 2026 — no past gap.
        r = FakeRevision(effective_from=date(2026, 7, 1))
        a = compute_arrears_for_revision(
            revision=r, draft_year=2026, draft_month=6,
        )
        assert a is None

    def test_no_arrears_for_same_month_effective(self):
        # Effective Jun 15, draft Jun — current month picks up new
        # via effective_components_for_month; arrears would double.
        r = FakeRevision(effective_from=date(2026, 6, 15))
        a = compute_arrears_for_revision(
            revision=r, draft_year=2026, draft_month=6,
        )
        assert a is None

    def test_back_dated_one_month(self):
        # Effective May, draft Jun → 1 month of arrears.
        r = FakeRevision(effective_from=date(2026, 5, 10))
        a = compute_arrears_for_revision(
            revision=r, draft_year=2026, draft_month=6,
        )
        assert a is not None
        assert a.months_owed == 1
        # Old monthly gross = 40000, new = 48000 → delta 8000 × 1 = 8000.
        assert a.monthly_delta == 8000.0
        assert a.amount == 8000.0

    def test_back_dated_across_year(self):
        # Effective Nov 2025, draft Feb 2026 → 3 months (Nov/Dec/Jan).
        r = FakeRevision(effective_from=date(2025, 11, 1))
        a = compute_arrears_for_revision(
            revision=r, draft_year=2026, draft_month=2,
        )
        assert a is not None
        assert a.months_owed == 3
        assert a.amount == 24000.0  # 8000 × 3

    def test_no_double_count_when_already_paid(self):
        # arrears_run_id set means a prior generate_draft already
        # injected. This is the no-retro-edit-finalized guard.
        r = FakeRevision(
            effective_from=date(2026, 3, 1), arrears_run_id=99,
        )
        a = compute_arrears_for_revision(
            revision=r, draft_year=2026, draft_month=6,
        )
        assert a is None

    def test_approved_but_not_applied_is_skipped(self):
        r = FakeRevision(
            status=RevStatus.APPROVED.value,
            effective_from=date(2026, 3, 1),
        )
        a = compute_arrears_for_revision(
            revision=r, draft_year=2026, draft_month=6,
        )
        assert a is None

    def test_negative_delta_not_arreared(self):
        # Demotion / correction down — arrears would be negative, but
        # we don't auto-recover; HR uses an adjustment line.
        r = FakeRevision(
            effective_from=date(2026, 3, 1),
            new_basic=15000, new_conveyance=4500,
            new_hra=7500, new_other_allowance=3000, new_ctc=30000,
        )
        a = compute_arrears_for_revision(
            revision=r, draft_year=2026, draft_month=6,
        )
        assert a is None


# --------------------------- band warning ----------------------------


class TestBandWarning:
    def test_no_warning_inside_band(self):
        assert band_warning_for(50000, 40000, 60000) is None

    def test_no_warning_when_no_band(self):
        assert band_warning_for(50000, None, None) is None

    def test_below_min_warns(self):
        msg = band_warning_for(30000, 40000, 60000)
        assert msg is not None and "below" in msg

    def test_above_max_warns(self):
        msg = band_warning_for(70000, 40000, 60000)
        assert msg is not None and "above" in msg

    def test_only_min_set(self):
        assert band_warning_for(40000, 50000, None) is not None
        assert band_warning_for(60000, 50000, None) is None

    def test_only_max_set(self):
        assert band_warning_for(70000, None, 60000) is not None
        assert band_warning_for(50000, None, 60000) is None


# --------------------------- derive_hike -----------------------------


class TestHike:
    def test_normal(self):
        amt, pct = derive_hike(40000, 48000)
        assert amt == 8000.0
        assert pct == 20.0

    def test_zero_old_ctc(self):
        amt, pct = derive_hike(0, 30000)
        assert amt == 30000.0
        assert pct == 0.0

    def test_demotion_negative(self):
        amt, pct = derive_hike(50000, 40000)
        assert amt == -10000.0
        assert pct == -20.0


# --------------------------- idempotency (no double count) -----------


class TestIdempotency:
    def test_arrears_compute_twice_same(self):
        r = FakeRevision(effective_from=date(2026, 5, 1))
        a = compute_arrears_for_revision(
            revision=r, draft_year=2026, draft_month=6,
        )
        b = compute_arrears_for_revision(
            revision=r, draft_year=2026, draft_month=6,
        )
        assert a == b

    def test_effective_components_compute_twice_same(self):
        r = FakeRevision(effective_from=date(2026, 6, 1))
        kw = dict(
            employee_basic=10000, employee_conveyance=3000,
            employee_hra=5000, employee_other_allowance=2000,
            revisions=[r], year=2026, month=6,
        )
        a = effective_components_for_month(**kw)
        b = effective_components_for_month(**kw)
        assert a == b
