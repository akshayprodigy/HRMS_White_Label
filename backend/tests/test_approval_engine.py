"""Unit tests for the generic approval-chain engine.

All pure — no DB. Every rule the engine promises is covered.
"""
from typing import List

import pytest

from app.services.approval_engine import (
    AUTO_APPROVE_BELOW_DEFAULT,
    AbsenceCheck, ChainSpec, RequestContext, StepSpec,
    advance_state, build_plan, filter_absent_approvers,
    is_approver_absent, pick_effective_chain, validate_bands,
)


# ---------------------------------------------------------------------------
# Band validation
# ---------------------------------------------------------------------------


def _steps(*specs):
    """Compact helper: (order, min, max) tuples → StepSpec list."""
    return [
        StepSpec(step_order=o, approver_type="reporting_manager",
                 min_amount_paise=lo, max_amount_paise=hi)
        for (o, lo, hi) in specs
    ]


def test_bands_ok_full_coverage_open_ended():
    steps = _steps((1, None, None))
    assert validate_bands(steps).ok


def test_bands_ok_two_bands_touching():
    steps = _steps((1, 0, 500_000), (2, 500_001, None))
    assert validate_bands(steps).ok


def test_bands_gap_between_two_bands():
    steps = _steps((1, 0, 500_000), (2, 600_000, None))
    result = validate_bands(steps)
    assert not result.ok
    assert result.gaps == [(500_001, 599_999)]


def test_bands_gap_at_top_end():
    steps = _steps((1, 0, 500_000))
    result = validate_bands(steps)
    assert not result.ok
    # Some gap that includes +inf sentinel exists.
    assert any(g[0] > 500_000 for g in result.gaps)


def test_bands_empty_chain_rejected():
    result = validate_bands([])
    assert not result.ok
    assert result.empty


def test_bands_duplicate_orders_rejected():
    steps = _steps((1, 0, 500_000), (1, 500_001, None))
    result = validate_bands(steps)
    assert not result.ok
    assert 1 in result.duplicate_orders


def test_bands_overlap_is_fine():
    # Overlapping ranges still cover — engine picks one per request.
    steps = _steps((1, 0, 1_000_000), (2, 500_000, None))
    assert validate_bands(steps).ok


# ---------------------------------------------------------------------------
# Plan building — threshold routing + skip + auto-approve
# ---------------------------------------------------------------------------


def _resolver_return(mapping):
    def _r(step, _ctx):
        return list(mapping.get(step.step_order, []))
    return _r


def _chain(steps, **kwargs):
    return ChainSpec(
        id=kwargs.pop("id", 1),
        name=kwargs.pop("name", "test"),
        entity_type=kwargs.pop("entity_type", "expense"),
        steps=tuple(steps),
        auto_approve_below_paise=kwargs.pop(
            "auto_approve_below_paise", None
        ),
        skip_if_same_person=kwargs.pop("skip_if_same_person", True),
        department=kwargs.pop("department", None),
    )


def test_amount_below_threshold_returns_empty_plan():
    chain = _chain(
        _steps((1, None, None)), auto_approve_below_paise=100_000
    )
    ctx = RequestContext(submitter_id=10, amount_paise=50_000)
    plan = build_plan(chain, ctx, _resolver_return({1: [11]}))
    assert plan == []


def test_amount_at_threshold_is_not_auto_approved():
    """Threshold is strict-less-than."""
    chain = _chain(
        _steps((1, None, None)), auto_approve_below_paise=100_000
    )
    ctx = RequestContext(submitter_id=10, amount_paise=100_000)
    plan = build_plan(chain, ctx, _resolver_return({1: [11]}))
    assert len(plan) == 1


def test_small_amount_routes_only_to_first_band():
    steps = _steps(
        (1, 0, 500_000),          # manager band
        (2, 500_001, None),       # finance + ceo band
    )
    chain = _chain(steps)
    ctx = RequestContext(submitter_id=10, amount_paise=200_000)
    plan = build_plan(chain, ctx, _resolver_return({1: [11], 2: [99]}))
    assert [p.step_order for p in plan] == [1]


def test_large_amount_routes_to_high_band():
    steps = _steps(
        (1, 0, 500_000),
        (2, 500_001, None),
    )
    chain = _chain(steps)
    ctx = RequestContext(submitter_id=10, amount_paise=10_000_000)
    plan = build_plan(chain, ctx, _resolver_return({1: [11], 2: [99]}))
    assert [p.step_order for p in plan] == [2]


def test_skip_if_same_person_removes_submitter_from_approvers():
    step = StepSpec(step_order=1, approver_type="reporting_manager",
                    min_amount_paise=None, max_amount_paise=None)
    chain = _chain([step])
    ctx = RequestContext(submitter_id=42, amount_paise=100_000)
    # Resolver returns the submitter themselves — must be stripped.
    plan = build_plan(chain, ctx, _resolver_return({1: [42, 43]}))
    assert plan[0].approver_user_ids == [43]


def test_skip_if_same_person_disabled_at_chain_level():
    step = StepSpec(step_order=1, approver_type="reporting_manager",
                    min_amount_paise=None, max_amount_paise=None)
    chain = _chain([step], skip_if_same_person=False)
    ctx = RequestContext(submitter_id=42, amount_paise=100_000)
    plan = build_plan(chain, ctx, _resolver_return({1: [42]}))
    assert plan[0].approver_user_ids == [42]


def test_no_eligible_approver_marks_step_with_reason():
    step = StepSpec(step_order=1, approver_type="finance",
                    min_amount_paise=None, max_amount_paise=None)
    chain = _chain([step])
    ctx = RequestContext(submitter_id=10, amount_paise=100_000)
    plan = build_plan(chain, ctx, _resolver_return({1: []}))
    assert plan[0].approver_user_ids == []
    assert plan[0].skip_reason == "no_eligible_approver"


def test_parallel_step_dedups_ids_and_preserves_order():
    step = StepSpec(
        step_order=1, approver_type="role", approver_ref="finance",
        mode="parallel", parallel_rule="all",
        min_amount_paise=None, max_amount_paise=None,
    )
    chain = _chain([step])
    ctx = RequestContext(submitter_id=10, amount_paise=100_000)
    plan = build_plan(chain, ctx, _resolver_return({1: [55, 66, 55, 77]}))
    assert plan[0].approver_user_ids == [55, 66, 77]


# ---------------------------------------------------------------------------
# advance_state — sequential + parallel + reject-stops
# ---------------------------------------------------------------------------


def _row(step_order, status="pending", mode="sequential",
         parallel_rule="all", approver_user_id=1):
    return {
        "step_order": step_order,
        "status": status,
        "mode": mode,
        "parallel_rule": parallel_rule,
        "approver_user_id": approver_user_id,
    }


def test_sequential_approve_advances_to_next_step():
    rows = [
        _row(1, status="approved"),
        _row(2),
    ]
    out = advance_state(
        all_step_instances=rows, acted_step_order=1, action="approve"
    )
    assert out.next_status == "pending"
    assert out.advance_to_step == 2
    assert out.should_notify_next


def test_sequential_reject_stops_chain():
    rows = [_row(1, status="rejected"), _row(2)]
    out = advance_state(
        all_step_instances=rows, acted_step_order=1, action="reject"
    )
    assert out.next_status == "rejected"
    assert out.finalize


def test_final_step_approve_finalizes():
    rows = [_row(1, status="approved")]
    out = advance_state(
        all_step_instances=rows, acted_step_order=1, action="approve"
    )
    assert out.next_status == "approved"
    assert out.finalize


def test_parallel_all_waits_for_every_approver():
    # Two rows at step 1; only one has approved so far.
    rows = [
        _row(1, status="approved", mode="parallel", parallel_rule="all"),
        _row(1, status="pending",  mode="parallel", parallel_rule="all"),
        _row(2),
    ]
    out = advance_state(
        all_step_instances=rows, acted_step_order=1, action="approve"
    )
    assert out.next_status == "pending"
    assert out.advance_to_step is None


def test_parallel_all_advances_when_all_approved():
    rows = [
        _row(1, status="approved", mode="parallel", parallel_rule="all"),
        _row(1, status="approved", mode="parallel", parallel_rule="all"),
        _row(2),
    ]
    out = advance_state(
        all_step_instances=rows, acted_step_order=1, action="approve"
    )
    assert out.advance_to_step == 2


def test_parallel_any_advances_on_first_approve():
    rows = [
        _row(1, status="approved", mode="parallel", parallel_rule="any"),
        _row(1, status="pending",  mode="parallel", parallel_rule="any"),
        _row(2),
    ]
    out = advance_state(
        all_step_instances=rows, acted_step_order=1, action="approve"
    )
    assert out.advance_to_step == 2


def test_parallel_any_reject_stops_chain():
    """Conservative default: a reject anywhere aborts the flow."""
    rows = [
        _row(1, status="rejected", mode="parallel", parallel_rule="any"),
        _row(1, status="pending",  mode="parallel", parallel_rule="any"),
    ]
    out = advance_state(
        all_step_instances=rows, acted_step_order=1, action="reject"
    )
    assert out.next_status == "rejected"
    assert out.finalize


def test_advance_state_unknown_action_raises():
    with pytest.raises(ValueError):
        advance_state(
            all_step_instances=[_row(1)],
            acted_step_order=1, action="frobnicate",
        )


def test_advance_state_missing_current_step_finalizes_reject():
    """If someone tries to act on a step that isn't in the plan, engine
    treats that as a rejection — protects against data drift.
    """
    out = advance_state(
        all_step_instances=[_row(2)], acted_step_order=1, action="approve"
    )
    assert out.next_status == "rejected"


# ---------------------------------------------------------------------------
# pick_effective_chain — department > org-wide
# ---------------------------------------------------------------------------


def test_pick_prefers_department_specific_chain():
    org_wide = _chain(_steps((1, None, None)), id=1, department=None)
    eng_chain = _chain(_steps((1, None, None)), id=2, department="engineering")
    picked = pick_effective_chain(
        [org_wide, eng_chain],
        entity_type="expense", department="engineering",
    )
    assert picked.id == 2


def test_pick_falls_back_to_org_wide():
    org_wide = _chain(_steps((1, None, None)), id=1, department=None)
    eng_chain = _chain(_steps((1, None, None)), id=2, department="engineering")
    picked = pick_effective_chain(
        [org_wide, eng_chain],
        entity_type="expense", department="ops",
    )
    assert picked.id == 1


def test_pick_returns_none_when_no_entity_match():
    tr = _chain(_steps((1, None, None)), id=1,
                entity_type="travel", department=None)
    picked = pick_effective_chain(
        [tr], entity_type="expense", department=None
    )
    assert picked is None


def test_pick_ties_broken_by_highest_id():
    a = _chain(_steps((1, None, None)), id=1, department=None)
    b = _chain(_steps((1, None, None)), id=5, department=None)
    picked = pick_effective_chain(
        [a, b], entity_type="expense", department=None,
    )
    assert picked.id == 5


def test_auto_approve_below_default_is_documented():
    # Documented behaviour: default off (0).
    assert AUTO_APPROVE_BELOW_DEFAULT == 0


# ---------------------------------------------------------------------------
# Section M B5: skip-if-absent — is_approver_absent + filter_absent_approvers
# ---------------------------------------------------------------------------


def _chk(user_id, days, dates):
    return AbsenceCheck(
        user_id=user_id,
        required_window_days=days,
        attended_work_dates=frozenset(dates),
    )


def test_is_approver_absent_true_when_no_attendance():
    assert is_approver_absent(_chk(1, 7, []))


def test_is_approver_absent_false_when_any_attendance():
    assert not is_approver_absent(_chk(1, 7, ["2026-07-01"]))


def test_is_approver_absent_disabled_when_window_zero():
    """window_days<=0 disables the check regardless of attendance."""
    assert not is_approver_absent(_chk(1, 0, []))
    assert not is_approver_absent(_chk(1, -1, []))


def test_filter_absent_approvers_drops_only_the_absent():
    checks = [
        _chk(1, 7, []),                # absent
        _chk(2, 7, ["2026-06-30"]),    # present
        _chk(3, 7, []),                # absent
        _chk(4, 7, ["2026-07-01", "2026-06-29"]),  # present
    ]
    assert filter_absent_approvers(checks) == [2, 4]


def test_filter_absent_approvers_preserves_order():
    checks = [
        _chk(9, 7, ["2026-06-30"]),
        _chk(3, 7, ["2026-06-30"]),
        _chk(5, 7, ["2026-06-30"]),
    ]
    assert filter_absent_approvers(checks) == [9, 3, 5]


def test_filter_absent_approvers_can_return_empty_list():
    """The endpoint layer is the one that guards against stranding —
    the pure helper faithfully returns [] when everyone is absent so
    the endpoint can consciously decide to fall back."""
    checks = [_chk(1, 7, []), _chk(2, 7, [])]
    assert filter_absent_approvers(checks) == []


def test_filter_absent_approvers_window_zero_keeps_everyone():
    """Chain step with skip_if_absent_days=None/0 → no one drops."""
    checks = [
        _chk(1, 0, []), _chk(2, 0, []), _chk(3, 0, ["2026-07-01"]),
    ]
    assert filter_absent_approvers(checks) == [1, 2, 3]
