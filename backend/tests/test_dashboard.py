"""Unit tests for the dashboard service.

The critical property under test is **no data leak** — a manager's
dashboard cannot return data from another team; an employee's cannot
return anyone else's; HR sees the whole org; Finance sees the money
surface without HR employee-directory access.

Every rule the service promises is covered.
"""
from __future__ import annotations

from typing import List

import pytest

from app.services.dashboard import (
    RoleName, RolePosture, WIDGET_CATALOG,
    actionable_widget_keys, build_role_posture, descriptor_for,
    merge_widget_sets, sum_pending_counts, visible_user_ids,
    widgets_for_dashboards,
)


# ---------------------------------------------------------------------------
# Posture factory helpers
# ---------------------------------------------------------------------------


def _employee(user_id: int = 100) -> RolePosture:
    return build_role_posture(
        user_id=user_id, is_superuser=False,
        role_names=[RoleName.EMPLOYEE],
        permission_names=["employee leave read"],
        team_user_ids=[],
    )


def _manager(user_id: int = 200, team=(201, 202, 203)) -> RolePosture:
    return build_role_posture(
        user_id=user_id, is_superuser=False,
        role_names=[RoleName.PM],
        permission_names=[
            "employee leave read", "report attendance",
            "performance one_on_one",
        ],
        team_user_ids=list(team),
    )


def _hr(user_id: int = 300) -> RolePosture:
    return build_role_posture(
        user_id=user_id, is_superuser=False,
        role_names=[RoleName.HR],
        permission_names=[
            "hr employee read", "hr employee write",
            "tax declaration verify", "report attendance",
            "employee leave read", "performance cycle admin",
            "report headcount", "statutory view",
            "hr payroll view", "finance reimburse",
        ],
        team_user_ids=[],
    )


def _finance(user_id: int = 400) -> RolePosture:
    return build_role_posture(
        user_id=user_id, is_superuser=False,
        role_names=[RoleName.FINANCE],
        permission_names=[
            "finance approve", "finance reimburse",
            "hr payroll view", "statutory view",
            "report payroll",
        ],
        team_user_ids=[],
    )


def _ceo(user_id: int = 500) -> RolePosture:
    return build_role_posture(
        user_id=user_id, is_superuser=False,
        role_names=[RoleName.CEO],
        permission_names=[
            "executive report view", "report headcount",
            "performance view all",
        ],
        team_user_ids=[],
    )


def _multi_role(
    user_id: int = 600, team=(601, 602),
) -> RolePosture:
    """A Dept Head who is also an Employee (has manager role + own data)."""
    return build_role_posture(
        user_id=user_id, is_superuser=False,
        role_names=[RoleName.EMPLOYEE, RoleName.DEPT_HEAD, RoleName.FINANCE],
        permission_names=[
            "employee leave read", "report attendance",
            "performance one_on_one",
            "finance reimburse", "hr payroll view",
        ],
        team_user_ids=list(team),
    )


# ---------------------------------------------------------------------------
# RolePosture + landing mapping
# ---------------------------------------------------------------------------


def test_employee_lands_on_employee_dashboard():
    assert _employee().landing_dashboard() == "employee-dashboard"


def test_manager_lands_on_manager_dashboard():
    assert _manager().landing_dashboard() == "manager-dashboard"


def test_hr_lands_on_hr_dashboard():
    assert _hr().landing_dashboard() == "hr-dashboard"


def test_finance_lands_on_finance_dashboard():
    assert _finance().landing_dashboard() == "finance-dashboard"


def test_ceo_lands_on_executive_dashboard():
    assert _ceo().landing_dashboard() == "executive-dashboard"


def test_super_admin_lands_on_hr_dashboard():
    p = build_role_posture(
        user_id=1, is_superuser=True,
        role_names=[RoleName.SUPER_ADMIN],
        permission_names=[],
        team_user_ids=[],
    )
    assert p.landing_dashboard() == "hr-dashboard"


def test_user_without_manager_role_but_with_reports_is_manager():
    """Someone the hierarchy calls 'manager of X' still gets the manager
    cockpit even without an explicit manager-oriented role."""
    p = build_role_posture(
        user_id=1, is_superuser=False,
        role_names=[RoleName.EMPLOYEE],
        permission_names=[],
        team_user_ids=[42, 43],
    )
    assert p.is_manager
    assert p.landing_dashboard() == "manager-dashboard"


def test_multi_role_landing_uses_priority_order():
    """HR beats Finance beats Manager beats Employee."""
    p = _multi_role()
    # Employee + Dept Head + Finance → finance beats manager beats employee
    assert p.landing_dashboard() == "finance-dashboard"

    p_hr_plus_finance = build_role_posture(
        user_id=1, is_superuser=False,
        role_names=[RoleName.HR, RoleName.FINANCE],
        permission_names=[], team_user_ids=[],
    )
    assert p_hr_plus_finance.landing_dashboard() == "hr-dashboard"


def test_dashboards_available_multi_role():
    p = _multi_role()
    got = p.dashboards_available()
    # Employee always included; manager because of team; finance role.
    assert "employee-dashboard" in got
    assert "manager-dashboard" in got
    assert "finance-dashboard" in got
    assert "hr-dashboard" not in got   # user isn't HR


# ---------------------------------------------------------------------------
# Widget selection + merge
# ---------------------------------------------------------------------------


def test_employee_widgets_dont_include_hr_widgets():
    got = widgets_for_dashboards(["employee-dashboard"])
    keys = {w.key for w in got}
    assert "my_attendance_today" in keys
    assert "hr_pending_verifications" not in keys
    assert "finance_reimbursement_queue" not in keys
    assert "executive_headline_kpis" not in keys


def test_manager_widgets_include_unified_queue():
    got = widgets_for_dashboards(["manager-dashboard"])
    keys = {w.key for w in got}
    assert "unified_approval_queue" in keys
    assert "team_attendance_today" in keys
    assert "team_reviews_owed" in keys


def test_merge_dedupes_widgets_across_dashboards():
    # unified_approval_queue is on manager, hr AND finance dashboards.
    # A user on all three should only get it once.
    posture = build_role_posture(
        user_id=1, is_superuser=True,
        role_names=[RoleName.HR, RoleName.FINANCE],
        permission_names=[], team_user_ids=[],
    )
    got = merge_widget_sets(
        ["manager-dashboard", "hr-dashboard", "finance-dashboard"],
        posture,
    )
    keys = [w.key for w in got]
    assert keys.count("unified_approval_queue") == 1


def test_merge_filters_widgets_by_permission():
    # Employee posture with only 'employee leave read'.
    posture = _employee()
    # An HR widget requires 'hr employee write' — should be filtered.
    got = merge_widget_sets(["hr-dashboard"], posture)
    keys = {w.key for w in got}
    assert "hr_pending_verifications" not in keys


def test_widget_permission_none_always_passes():
    posture = _employee()
    got = merge_widget_sets(["employee-dashboard"], posture)
    keys = {w.key for w in got}
    # my_attendance_today has permission=None
    assert "my_attendance_today" in keys


# ---------------------------------------------------------------------------
# THE no-leak tests: visible_user_ids scoping
# ---------------------------------------------------------------------------


def test_no_leak_employee_self_scope_is_only_own_user_id():
    p = _employee(user_id=42)
    got = visible_user_ids(p, widget_scope="self")
    assert got == [42]


def test_no_leak_employee_team_scope_returns_only_self():
    """An employee has no reports — a team-scope widget must return
    only their own id, never a fallback list."""
    p = _employee(user_id=42)
    got = visible_user_ids(p, widget_scope="team")
    assert got == [42]


def test_no_leak_employee_org_scope_does_not_return_none():
    """An org-scope widget MUST NOT return None for a plain employee.
    Returning None means 'all users' — the widget query would then
    happily fetch other employees' data."""
    p = _employee(user_id=42)
    got = visible_user_ids(p, widget_scope="org")
    assert got is not None
    assert got == [42]


def test_no_leak_manager_team_scope_is_own_and_reports_only():
    p = _manager(user_id=200, team=(201, 202, 203))
    got = visible_user_ids(p, widget_scope="team")
    assert set(got) == {200, 201, 202, 203}


def test_no_leak_manager_team_scope_never_includes_others():
    """Critical: another team's users must NEVER appear."""
    p = _manager(user_id=200, team=(201, 202))
    got = visible_user_ids(p, widget_scope="team")
    assert 999 not in got
    assert 500 not in got
    assert 300 not in got


def test_no_leak_manager_org_scope_falls_back_to_team():
    """A plain manager asking for an org widget cannot see the whole
    org — must fall back to team scope. NEVER None."""
    p = _manager(user_id=200, team=(201, 202))
    got = visible_user_ids(p, widget_scope="org")
    assert got is not None
    assert set(got) == {200, 201, 202}


def test_no_leak_hr_org_scope_returns_none_meaning_all():
    p = _hr()
    assert visible_user_ids(p, widget_scope="org") is None


def test_no_leak_hr_team_scope_upgrades_to_org():
    """HR is org-scope; a widget marked team-scope for the caller
    should still cover the full org, not just HR's reports."""
    p = _hr()
    assert visible_user_ids(p, widget_scope="team") is None


def test_no_leak_finance_org_scope_returns_none():
    """Finance is org-scoped for MONEY widgets only, but the
    visible_user_ids helper is deliberately generous — endpoints
    still gate each widget's permission separately."""
    p = _finance()
    assert visible_user_ids(p, widget_scope="org") is None


def test_no_leak_ceo_org_scope_returns_none():
    p = _ceo()
    assert visible_user_ids(p, widget_scope="org") is None


def test_no_leak_multi_role_uses_broadest_scope():
    """A user with EMPLOYEE + DEPT_HEAD + FINANCE roles should get
    finance-level org scope — the ORG-widest wins."""
    p = _multi_role()
    assert visible_user_ids(p, widget_scope="org") is None
    # team scope: NOT upgraded to org because finance ≠ has_org_scope
    # BUT — Finance is org-scoped only for money widgets. Team-scope
    # widget still routes to caller's own team + self.
    got = visible_user_ids(p, widget_scope="team")
    assert got is not None
    assert set(got) == {600, 601, 602}


def test_no_leak_unknown_scope_raises():
    p = _employee()
    with pytest.raises(ValueError):
        visible_user_ids(p, widget_scope="mystery")


# ---------------------------------------------------------------------------
# No-leak: widget-permission MUST match underlying-report-permission
# ---------------------------------------------------------------------------


# The Section D report catalog uses these permission names. If a
# widget claims scope="org" but its permission is weaker than what the
# corresponding report requires, we'd have a data leak. This test locks
# down the mapping.
WIDGET_PERM_ALIGNMENT = {
    "team_attendance_today": "report attendance",
    "hr_headcount_trend": "report headcount",
    "hr_attrition_rate": "report headcount",
    "hr_flagged_attendance": "report attendance",
    "hr_tax_declarations_pending": "tax declaration verify",
    "finance_reimbursement_queue": "finance reimburse",
    "finance_cost_analytics": "report payroll",
    "finance_statutory_due": "statutory view",
    "finance_payroll_status": "hr payroll view",
    "hr_out_of_policy_expenses": "finance reimburse",
    "executive_rating_distribution": "performance view all",
    "hr_review_cycles_progress": "performance cycle admin",
}


@pytest.mark.parametrize(
    "widget_key,expected_perm", WIDGET_PERM_ALIGNMENT.items()
)
def test_widget_permission_matches_underlying_report_permission(
    widget_key, expected_perm,
):
    """No-leak-via-dashboard: every widget must gate on at least the
    same permission the underlying report/endpoint requires."""
    d = descriptor_for(widget_key)
    assert d is not None, f"widget {widget_key} missing from catalog"
    assert d.permission == expected_perm, (
        f"widget {widget_key} gates on {d.permission!r} but should "
        f"gate on {expected_perm!r} to match the underlying report"
    )


# ---------------------------------------------------------------------------
# CEO/COO cockpit has no action queue
# ---------------------------------------------------------------------------


def test_executive_dashboard_has_no_action_widgets():
    """Read-only strategic view. No task queue."""
    widgets = widgets_for_dashboards(["executive-dashboard"])
    action_widgets = [w for w in widgets if w.category == "action"]
    assert action_widgets == [], (
        f"executive dashboard leaked action widgets: "
        f"{[w.key for w in action_widgets]}"
    )


# ---------------------------------------------------------------------------
# Pending-count aggregation
# ---------------------------------------------------------------------------


def test_pending_count_sums_action_widgets():
    payloads = {
        "unified_approval_queue": {"count": 3},
        "my_pending_actions": {"count": 2},
        "my_leave_balance": {"count": 15, "days": 15},  # data widget
        "my_attendance_today": {"punched_in": True},
    }
    assert sum_pending_counts(payloads) == 5


def test_pending_count_ignores_data_and_analytic_widgets():
    payloads = {
        "hr_headcount_trend": {"count": 999},  # analytic, ignored
        "my_leave_balance": {"count": 20},     # data, ignored
    }
    assert sum_pending_counts(payloads) == 0


def test_pending_count_ignores_non_int_counts():
    payloads = {
        "unified_approval_queue": {"count": "3"},  # str, not int
    }
    assert sum_pending_counts(payloads) == 0


def test_pending_count_ignores_missing_payloads():
    payloads = {
        "unified_approval_queue": None,
        "my_pending_actions": {"count": 1},
    }
    assert sum_pending_counts(payloads) == 1


def test_actionable_widget_keys_contains_unified_queue():
    keys = actionable_widget_keys()
    assert "unified_approval_queue" in keys
    assert "my_pending_actions" in keys
    assert "my_leave_balance" not in keys


# ---------------------------------------------------------------------------
# Catalog integrity
# ---------------------------------------------------------------------------


def test_every_widget_belongs_to_at_least_one_dashboard():
    for key, w in WIDGET_CATALOG.items():
        assert w.dashboards, f"widget {key} has no dashboards"


def test_every_widget_category_is_valid():
    valid = {"action", "data", "analytic"}
    for key, w in WIDGET_CATALOG.items():
        assert w.category in valid, (
            f"widget {key} has invalid category {w.category!r}"
        )


def test_every_widget_scope_is_valid():
    valid = {"self", "team", "org"}
    for key, w in WIDGET_CATALOG.items():
        assert w.scope in valid, (
            f"widget {key} has invalid scope {w.scope!r}"
        )


def test_catalog_has_no_duplicate_keys():
    # dict guarantees uniqueness; this is a sanity check.
    keys = list(WIDGET_CATALOG.keys())
    assert len(keys) == len(set(keys))
