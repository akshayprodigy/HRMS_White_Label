"""Unit tests for expense/travel pure helpers."""
from typing import List

import pytest

from app.services.expense import (
    LineItemInput, POLICY_DEFAULT_MODE, REIMBURSE_DEFAULT_MODE,
    decide_reimbursement, evaluate_policy,
    reconcile_travel_advance, sum_line_items,
)


# ---------------------------------------------------------------------------
# Policy evaluation
# ---------------------------------------------------------------------------


def test_no_flags_when_no_policy_configured():
    lines = [LineItemInput(amount_paise=100_000, category_name="Meals",
                           has_receipt=True)]
    assert evaluate_policy(lines).flags == []


def test_receipt_required_above_flags_missing_receipt():
    lines = [LineItemInput(
        amount_paise=150_000, category_name="Meals",
        has_receipt=False,
        receipt_required_above_paise=100_000,
    )]
    report = evaluate_policy(lines)
    assert len(report.flags) == 1
    assert "Receipt" in report.flags[0].reason
    assert report.flags[0].severity == "warn"
    assert not report.has_blocks


def test_receipt_below_threshold_no_flag_even_if_missing():
    lines = [LineItemInput(
        amount_paise=90_000, category_name="Meals",
        has_receipt=False,
        receipt_required_above_paise=100_000,
    )]
    assert evaluate_policy(lines).flags == []


def test_per_diem_cap_flags_over_amount():
    lines = [LineItemInput(
        amount_paise=250_000, category_name="Meals",
        has_receipt=True,
        per_diem_cap_paise=200_000,
    )]
    report = evaluate_policy(lines)
    assert len(report.flags) == 1
    assert "per-diem" in report.flags[0].reason


def test_block_severity_when_category_is_block_mode():
    lines = [LineItemInput(
        amount_paise=250_000, category_name="Fuel",
        has_receipt=True,
        per_diem_cap_paise=200_000,
        policy_mode="block",
    )]
    report = evaluate_policy(lines)
    assert report.flags[0].severity == "block"
    assert report.has_blocks


def test_by_line_grouping_returns_all_flags_for_a_line():
    lines = [LineItemInput(
        amount_paise=250_000, category_name="Fuel",
        has_receipt=False,
        per_diem_cap_paise=200_000,
        receipt_required_above_paise=100_000,
    )]
    report = evaluate_policy(lines)
    grouped = report.by_line()
    assert len(grouped[0]) == 2


def test_policy_default_mode_documented():
    assert POLICY_DEFAULT_MODE == "warn"


# ---------------------------------------------------------------------------
# Totals
# ---------------------------------------------------------------------------


def test_sum_lines_integer_arithmetic():
    lines = [
        LineItemInput(amount_paise=100_001, category_name="X",
                      has_receipt=False),
        LineItemInput(amount_paise=249_999, category_name="Y",
                      has_receipt=False),
    ]
    assert sum_line_items(lines) == 350_000


def test_sum_empty_returns_zero():
    assert sum_line_items([]) == 0


# ---------------------------------------------------------------------------
# Reimbursement double-pay guard
# ---------------------------------------------------------------------------


def test_can_reimburse_approved_claim_first_time():
    d = decide_reimbursement(
        claim_status="approved",
        reimbursement_mode=None, reimbursed_at=None,
        payroll_run_id=None, requested_mode="direct",
    )
    assert d.can_reimburse
    assert d.mode == "direct"


def test_cannot_reimburse_draft_claim():
    d = decide_reimbursement(
        claim_status="draft",
        reimbursement_mode=None, reimbursed_at=None,
        payroll_run_id=None,
    )
    assert not d.can_reimburse
    assert "must be approved" in (d.reason or "")


def test_cannot_double_pay_direct_then_direct():
    d = decide_reimbursement(
        claim_status="approved",
        reimbursement_mode="direct",
        reimbursed_at="2026-07-01",
        payroll_run_id=None,
        requested_mode="direct",
    )
    assert not d.can_reimburse
    assert "double-pay" in (d.reason or "")


def test_cannot_double_pay_payroll_after_direct():
    d = decide_reimbursement(
        claim_status="approved",
        reimbursement_mode="direct",
        reimbursed_at="2026-07-01",
        payroll_run_id=None,
        requested_mode="payroll",
    )
    assert not d.can_reimburse


def test_cannot_reimburse_after_payroll_push():
    d = decide_reimbursement(
        claim_status="approved",
        reimbursement_mode="payroll",
        reimbursed_at=None,
        payroll_run_id=42,
        requested_mode="direct",
    )
    assert not d.can_reimburse


def test_unknown_mode_rejected():
    d = decide_reimbursement(
        claim_status="approved",
        reimbursement_mode=None, reimbursed_at=None,
        payroll_run_id=None, requested_mode="cash-under-table",
    )
    assert not d.can_reimburse
    assert "unknown reimbursement mode" in (d.reason or "")


def test_reimburse_default_mode_documented():
    assert REIMBURSE_DEFAULT_MODE == "direct"


# ---------------------------------------------------------------------------
# Travel advance reconciliation
# ---------------------------------------------------------------------------


def test_reconcile_advance_matches_actuals_exactly():
    r = reconcile_travel_advance(
        advance_paid_paise=500_000, actual_spend_paise=500_000
    )
    assert r.balance_paise == 0
    assert r.surplus_paise == 0
    assert not r.needs_recovery
    assert not r.needs_topup


def test_reconcile_advance_underspent_recovers_from_employee():
    r = reconcile_travel_advance(
        advance_paid_paise=500_000, actual_spend_paise=300_000
    )
    assert r.balance_paise == 200_000
    assert r.surplus_paise == 0
    assert r.needs_recovery


def test_reconcile_advance_overspent_pays_top_up():
    r = reconcile_travel_advance(
        advance_paid_paise=300_000, actual_spend_paise=500_000
    )
    assert r.balance_paise == 0
    assert r.surplus_paise == 200_000
    assert r.needs_topup


def test_reconcile_zero_advance_treats_actuals_as_topup():
    r = reconcile_travel_advance(
        advance_paid_paise=0, actual_spend_paise=100_000
    )
    assert r.surplus_paise == 100_000
    assert r.balance_paise == 0
