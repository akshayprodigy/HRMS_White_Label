"""Pure unit tests for the F3 salary-structure resolver.

The load-bearing guarantee: a template equivalent to the legacy flat-column
default (basic flat + conveyance 30% / hra 50% / other 20% of basic)
reproduces the exact values payroll computed before F3.
"""
from app.services.salary_structure import (
    ResolvedLine, resolve_earnings_from_template,
)


def _standard_lines():
    return [
        ResolvedLine(slot="conveyance", calc_method="percent_of_basic", value=None, percent=30.0),
        ResolvedLine(slot="hra", calc_method="percent_of_basic", value=None, percent=50.0),
        ResolvedLine(slot="other", calc_method="percent_of_basic", value=None, percent=20.0),
    ]


def test_standard_template_matches_legacy_ratio_path():
    # Legacy path: round(basic*0.30), round(basic*0.50), round(basic*0.20).
    for basic in [10000, 25000, 33333, 47777, 100000]:
        r = resolve_earnings_from_template(basic, _standard_lines())
        assert r.basic == basic
        assert r.conveyance == round(basic * 0.30)
        assert r.hra == round(basic * 0.50)
        assert r.other_allowance == round(basic * 0.20)


def test_ctc_is_sum_of_heads():
    r = resolve_earnings_from_template(20000, _standard_lines())
    assert r.ctc == r.basic + r.conveyance + r.hra + r.other_allowance


def test_flat_lines_are_absolute():
    lines = [
        ResolvedLine(slot="hra", calc_method="flat", value=8000.0, percent=None),
        ResolvedLine(slot="conveyance", calc_method="flat", value=1600.0, percent=None),
    ]
    r = resolve_earnings_from_template(30000, lines)
    assert r.basic == 30000
    assert r.hra == 8000
    assert r.conveyance == 1600
    assert r.other_allowance == 0


def test_basic_slot_flat_overrides_employee_basic():
    lines = [
        ResolvedLine(slot="basic", calc_method="flat", value=40000.0, percent=None),
        ResolvedLine(slot="hra", calc_method="percent_of_basic", value=None, percent=50.0),
    ]
    r = resolve_earnings_from_template(999, lines)  # employee basic ignored
    assert r.basic == 40000
    assert r.hra == 20000


def test_extra_slotless_earning_folds_into_other():
    lines = [
        ResolvedLine(slot="hra", calc_method="percent_of_basic", value=None, percent=50.0),
        ResolvedLine(slot=None, calc_method="flat", value=1500.0, percent=None),   # medical
        ResolvedLine(slot="other", calc_method="percent_of_basic", value=None, percent=10.0),
    ]
    r = resolve_earnings_from_template(20000, lines)
    assert r.hra == 10000
    # other = 10% of 20000 (2000) + 1500 flat medical folded in
    assert r.other_allowance == 3500


def test_none_or_zero_basic_is_safe():
    r = resolve_earnings_from_template(None, _standard_lines())
    assert r.basic == 0
    assert r.conveyance == 0
    assert r.hra == 0
    assert r.other_allowance == 0


def test_empty_template_keeps_basic_only():
    r = resolve_earnings_from_template(15000, [])
    assert r.basic == 15000
    assert r.conveyance == 0 and r.hra == 0 and r.other_allowance == 0
