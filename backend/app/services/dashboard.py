"""Dashboard service — role-based landing widgets.

Read-only aggregation layer over existing services. NEVER writes to any
compute module. Every widget is scoped server-side so a manager's payload
can never leak another team's data, an employee's payload can never leak
another employee's data, and HR sees the full org set. A "no-leak" test
enforces this in tests/test_dashboard.py.

## Design

### Widget shape

Each widget is a compact dict:
    {
      "key": str,            # stable id, drives the frontend renderer
      "title": str,          # human label
      "category": str,       # "action" | "data" | "analytic"
      "permission": str|None,# RBAC name (None = universally available)
      "scope": str,          # "self" | "team" | "org"
      "drill": {             # where clicking a row/CTA takes the user
        "route": str,
        "params": dict,
      },
      "payload": Any,        # role-scoped summary (counts, top-N)
    }

### Widget catalog

Each entry in `WIDGET_CATALOG` maps a widget key to:
    (title, category, permission, scope, drill, per_role_membership)

`per_role_membership` is the set of role names that get this widget.
When a user has multiple roles, the union of their memberships is the
final widget list. Deduped by key — same widget only appears once even
if two roles both want it. When a widget's payload builder returns
None (permission failed or no data), it's dropped.

### Multi-role merge rule

Union of widget keys across all of the user's roles. Widgets are
scoped by the CALLER's overall role posture:
- If the user has any org-wide role (HR / Super Admin / CEO / COO),
  team-scoped widgets are upgraded to org-scope where legitimate.
- Otherwise team widgets stay team-scoped (a Dept Head sees only own
  team). Employee-scope widgets always show the caller's own data.

### Role → default landing

Priority order (highest wins):
  hr / super_admin        → hr-dashboard
  ceo / coo               → executive-dashboard
  finance                 → finance-dashboard
  pm / dept_head / bd_manager / has-direct-reports → manager-dashboard
  else                    → employee-dashboard

Multi-role users get a role-switcher on the frontend so they can flip
between cockpits without a reload.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import (
    Any, Awaitable, Callable, Dict, List, Optional, Set, Tuple,
)


# ============================================================
# Role constants (lowercased)
# ============================================================


class RoleName:
    HR = "hr"
    SUPER_ADMIN = "super admin"
    CEO = "ceo"
    COO = "coo"
    FINANCE = "finance"
    PM = "pm"
    DEPT_HEAD = "dept_head"
    BD_MANAGER = "bd manager"
    EMPLOYEE = "employee"


ORG_SCOPE_ROLES = {
    RoleName.HR, RoleName.SUPER_ADMIN, RoleName.CEO, RoleName.COO,
}

FINANCE_ROLES = {RoleName.FINANCE}

MANAGER_ROLES = {
    RoleName.PM, RoleName.DEPT_HEAD, RoleName.BD_MANAGER,
}


# ============================================================
# Role posture
# ============================================================


@dataclass
class RolePosture:
    """A normalized view of a user's authorization posture.

    Computed once per request so widget builders can consult it without
    re-walking role/permission lists.
    """
    user_id: int
    is_superuser: bool
    role_names: Set[str]         # lowercased
    permissions: Set[str]        # lowercased permission names
    team_user_ids: List[int]     # direct reports (by User.manager_id)

    @property
    def has_org_scope(self) -> bool:
        if self.is_superuser:
            return True
        return bool(self.role_names & ORG_SCOPE_ROLES)

    @property
    def is_finance(self) -> bool:
        if self.is_superuser:
            return True
        return bool(self.role_names & FINANCE_ROLES)

    @property
    def is_ceo_or_coo(self) -> bool:
        return bool(self.role_names & {RoleName.CEO, RoleName.COO})

    @property
    def is_hr(self) -> bool:
        return self.is_superuser or bool(
            self.role_names & {RoleName.HR, RoleName.SUPER_ADMIN}
        )

    @property
    def is_manager(self) -> bool:
        """A user is a manager if they have direct reports OR carry a
        manager-oriented role. Managers get the manager cockpit; the
        two conditions are independent."""
        if bool(self.role_names & MANAGER_ROLES):
            return True
        return len(self.team_user_ids) > 0

    def has_permission(self, name: str) -> bool:
        if self.is_superuser:
            return True
        return name in self.permissions

    def landing_dashboard(self) -> str:
        if self.is_hr:
            return "hr-dashboard"
        if self.is_ceo_or_coo:
            return "executive-dashboard"
        if self.is_finance:
            return "finance-dashboard"
        if self.is_manager:
            return "manager-dashboard"
        return "employee-dashboard"

    def dashboards_available(self) -> List[str]:
        """Which cockpits this user may switch to (multi-role)."""
        out = ["employee-dashboard"]  # always
        if self.is_manager:
            out.append("manager-dashboard")
        if self.is_finance:
            out.append("finance-dashboard")
        if self.is_hr:
            out.append("hr-dashboard")
        if self.is_ceo_or_coo:
            out.append("executive-dashboard")
        return list(dict.fromkeys(out))


def build_role_posture(
    *,
    user_id: int,
    is_superuser: bool,
    role_names: List[str],
    permission_names: List[str],
    team_user_ids: List[int],
) -> RolePosture:
    """Pure factory — endpoints prepare the inputs and hand them in.
    Tests can construct RolePosture directly without a DB."""
    return RolePosture(
        user_id=user_id,
        is_superuser=is_superuser,
        role_names={(r or "").strip().lower() for r in role_names},
        permissions={(p or "").strip().lower() for p in permission_names},
        team_user_ids=list(team_user_ids),
    )


# ============================================================
# Widget descriptor + registry
# ============================================================


@dataclass(frozen=True)
class WidgetDescriptor:
    """Metadata for a single widget. Payload is built at call time."""
    key: str
    title: str
    category: str            # "action" | "data" | "analytic"
    permission: Optional[str]
    scope: str               # "self" | "team" | "org"
    drill_route: str
    drill_params: Dict[str, Any] = field(default_factory=dict)
    # Which dashboards this widget appears on. If a user's assembled
    # dashboard set intersects this, the widget is included.
    dashboards: Tuple[str, ...] = ()


# The canonical widget catalog. This IS the contract between backend
# scoping and the frontend renderer.
WIDGET_CATALOG: Dict[str, WidgetDescriptor] = {

    # ---------------- Employee cockpit ----------------
    "my_attendance_today": WidgetDescriptor(
        key="my_attendance_today",
        title="My Attendance Today",
        category="data",
        permission=None,
        scope="self",
        drill_route="attendance-module",
        dashboards=("employee-dashboard",),
    ),
    "my_leave_balance": WidgetDescriptor(
        key="my_leave_balance",
        title="My Leave Balance",
        category="data",
        permission="employee leave read",
        scope="self",
        drill_route="leave",
        dashboards=("employee-dashboard",),
    ),
    "my_pending_actions": WidgetDescriptor(
        key="my_pending_actions",
        title="Pending on Me",
        category="action",
        permission=None,
        scope="self",
        drill_route="dashboard",
        dashboards=("employee-dashboard",),
    ),
    "my_active_goals": WidgetDescriptor(
        key="my_active_goals",
        title="My Active Goals",
        category="data",
        permission=None,
        scope="self",
        drill_route="performance-workspace",
        drill_params={"tab": "my-goals"},
        dashboards=("employee-dashboard",),
    ),
    "my_1on1_actions": WidgetDescriptor(
        key="my_1on1_actions",
        title="My 1:1 Action Items",
        category="action",
        permission=None,
        scope="self",
        drill_route="performance-workspace",
        drill_params={"tab": "one-on-ones"},
        dashboards=("employee-dashboard",),
    ),
    "my_next_payslip": WidgetDescriptor(
        key="my_next_payslip",
        title="My Latest Payslip",
        category="data",
        permission=None,
        scope="self",
        drill_route="my-payslips",
        dashboards=("employee-dashboard",),
    ),

    # ---------------- Manager cockpit ----------------
    "unified_approval_queue": WidgetDescriptor(
        key="unified_approval_queue",
        title="Approvals Awaiting You",
        category="action",
        permission=None,
        scope="team",  # inbox is inherently caller-scoped
        drill_route="approvals-view",
        dashboards=(
            "manager-dashboard", "hr-dashboard", "finance-dashboard",
        ),
    ),
    "team_attendance_today": WidgetDescriptor(
        key="team_attendance_today",
        title="Team Attendance Today",
        category="data",
        permission="report attendance",
        scope="team",
        drill_route="attendance-hr",
        dashboards=("manager-dashboard",),
    ),
    "team_on_leave_this_week": WidgetDescriptor(
        key="team_on_leave_this_week",
        title="Team On Leave This Week",
        category="data",
        permission="employee leave read",
        scope="team",
        drill_route="hr-leave",
        dashboards=("manager-dashboard", "hr-dashboard"),
    ),
    "team_reviews_owed": WidgetDescriptor(
        key="team_reviews_owed",
        title="Reviews You Owe",
        category="action",
        permission="performance one_on_one",
        scope="team",
        drill_route="performance-workspace",
        drill_params={"tab": "team-reviews"},
        dashboards=("manager-dashboard",),
    ),
    "team_1on1_coverage": WidgetDescriptor(
        key="team_1on1_coverage",
        title="1:1 Coverage",
        category="data",
        permission="performance one_on_one",
        scope="team",
        drill_route="performance-workspace",
        drill_params={"tab": "one-on-ones"},
        dashboards=("manager-dashboard",),
    ),

    # ---------------- HR cockpit ----------------
    "hr_pending_verifications": WidgetDescriptor(
        key="hr_pending_verifications",
        title="Documents Awaiting Verification",
        category="action",
        permission="hr employee write",
        scope="org",
        drill_route="hr-directory",
        dashboards=("hr-dashboard",),
    ),
    "hr_tax_declarations_pending": WidgetDescriptor(
        key="hr_tax_declarations_pending",
        title="Tax Declarations Awaiting Verify",
        category="action",
        permission="tax declaration verify",
        scope="org",
        drill_route="tax-declaration-queue",
        dashboards=("hr-dashboard",),
    ),
    "hr_flagged_attendance": WidgetDescriptor(
        key="hr_flagged_attendance",
        title="Flagged Attendance",
        category="action",
        permission="report attendance",
        scope="org",
        drill_route="hr-attendance-review",
        dashboards=("hr-dashboard",),
    ),
    "hr_out_of_policy_expenses": WidgetDescriptor(
        key="hr_out_of_policy_expenses",
        title="Out-of-Policy Expenses",
        category="action",
        permission="finance reimburse",
        scope="org",
        drill_route="expenses-workspace",
        drill_params={"tab": "approvals"},
        dashboards=("hr-dashboard", "finance-dashboard"),
    ),
    "hr_review_cycles_progress": WidgetDescriptor(
        key="hr_review_cycles_progress",
        title="Review Cycles In Flight",
        category="data",
        permission="performance cycle admin",
        scope="org",
        drill_route="performance-workspace",
        drill_params={"tab": "cycles-admin"},
        dashboards=("hr-dashboard",),
    ),
    "hr_headcount_trend": WidgetDescriptor(
        key="hr_headcount_trend",
        title="Headcount (12-mo trend)",
        category="analytic",
        permission="report headcount",
        scope="org",
        drill_route="reports-workspace",
        drill_params={"key": "headcount_trend"},
        dashboards=("hr-dashboard", "executive-dashboard"),
    ),
    "hr_attrition_rate": WidgetDescriptor(
        key="hr_attrition_rate",
        title="Attrition Rate",
        category="analytic",
        permission="report headcount",
        scope="org",
        drill_route="reports-workspace",
        drill_params={"key": "attrition_report"},
        dashboards=("hr-dashboard", "executive-dashboard"),
    ),
    "hr_exceptions": WidgetDescriptor(
        key="hr_exceptions",
        title="HR Exceptions",
        category="action",
        permission="hr employee read",
        scope="org",
        drill_route="hr-directory",
        dashboards=("hr-dashboard",),
    ),

    # ---------------- Finance cockpit ----------------
    "finance_reimbursement_queue": WidgetDescriptor(
        key="finance_reimbursement_queue",
        title="Reimbursements Ready",
        category="action",
        permission="finance reimburse",
        scope="org",
        drill_route="expenses-workspace",
        drill_params={"tab": "finance"},
        dashboards=("finance-dashboard",),
    ),
    "finance_travel_advance_outstanding": WidgetDescriptor(
        key="finance_travel_advance_outstanding",
        title="Travel Advances Outstanding",
        category="data",
        permission="finance reimburse",
        scope="org",
        drill_route="expenses-workspace",
        drill_params={"tab": "my-travel"},
        dashboards=("finance-dashboard",),
    ),
    "finance_payroll_status": WidgetDescriptor(
        key="finance_payroll_status",
        title="Payroll Run Status",
        category="data",
        permission="hr payroll view",
        scope="org",
        drill_route="hr-payroll",
        dashboards=("finance-dashboard", "hr-dashboard"),
    ),
    "finance_statutory_due": WidgetDescriptor(
        key="finance_statutory_due",
        title="Statutory Payments Due",
        category="data",
        permission="statutory view",
        scope="org",
        drill_route="statutory-filings",
        dashboards=("finance-dashboard", "hr-dashboard"),
    ),
    "finance_cost_analytics": WidgetDescriptor(
        key="finance_cost_analytics",
        title="Cost Analytics",
        category="analytic",
        permission="report payroll",
        scope="org",
        drill_route="reports-workspace",
        drill_params={"key": "salary_register"},
        dashboards=("finance-dashboard",),
    ),

    # ---------------- Executive cockpit ----------------
    "executive_rating_distribution": WidgetDescriptor(
        key="executive_rating_distribution",
        title="Rating Distribution",
        category="analytic",
        permission="performance view all",
        scope="org",
        drill_route="reports-workspace",
        drill_params={"key": "rating_distribution"},
        dashboards=("executive-dashboard", "hr-dashboard"),
    ),
    "executive_headline_kpis": WidgetDescriptor(
        key="executive_headline_kpis",
        title="Headline KPIs",
        category="analytic",
        permission="executive report view",
        scope="org",
        drill_route="enriched-dashboard",
        dashboards=("executive-dashboard",),
    ),
}


# ============================================================
# Widget selection (pure)
# ============================================================


def widgets_for_dashboards(dashboards: List[str]) -> List[WidgetDescriptor]:
    """Return every catalog widget that belongs to at least one of the
    named dashboards. Order preserved from catalog insertion for
    deterministic layout."""
    dset = set(dashboards)
    return [
        w for w in WIDGET_CATALOG.values()
        if any(d in dset for d in w.dashboards)
    ]


def merge_widget_sets(
    dashboards: List[str], posture: RolePosture,
) -> List[WidgetDescriptor]:
    """Multi-role dedup + permission gate.

    Rules:
    - Union widgets across all named dashboards.
    - Drop any widget whose permission fails the caller.
    - Keep insertion order (catalog order).
    - Skip widgets already added — first appearance wins so the order
      matches the caller's PRIMARY landing.
    """
    seen: Set[str] = set()
    out: List[WidgetDescriptor] = []
    for w in widgets_for_dashboards(dashboards):
        if w.key in seen:
            continue
        if w.permission and not posture.has_permission(w.permission):
            continue
        seen.add(w.key)
        out.append(w)
    return out


# ============================================================
# No-leak scope helpers (pure)
# ============================================================


def visible_user_ids(
    posture: RolePosture, *, widget_scope: str,
) -> Optional[List[int]]:
    """Return the set of user ids a widget is allowed to look at, or
    None to mean 'all users' (org-wide).

    Contract:
    - scope="self"  → [posture.user_id]
    - scope="team"  → posture.team_user_ids + [posture.user_id]
                      OR None if the caller has org scope (upgrade)
    - scope="org"   → None if the caller has org or finance scope, else
                      falls back to team-scope. If neither, returns
                      just [posture.user_id] — the widget will show
                      nothing meaningful, but no data leaks.

    This is THE test surface. Every widget builder MUST pass its
    query through this function; the "no-leak" test drives every
    (role, widget) combination through it.
    """
    if widget_scope == "self":
        return [posture.user_id]
    if widget_scope == "team":
        if posture.has_org_scope:
            return None
        base = list(dict.fromkeys([posture.user_id, *posture.team_user_ids]))
        return base
    if widget_scope == "org":
        if posture.has_org_scope or posture.is_finance:
            return None
        # non-org caller asking for an org widget: fall back to team
        # scope so at least SOME meaningful (safe) data can render.
        if posture.team_user_ids:
            return list(dict.fromkeys(
                [posture.user_id, *posture.team_user_ids]
            ))
        return [posture.user_id]
    raise ValueError(f"unknown widget_scope {widget_scope!r}")


# ============================================================
# Widget descriptor accessors
# ============================================================


def descriptor_for(key: str) -> Optional[WidgetDescriptor]:
    return WIDGET_CATALOG.get(key)


def actionable_widget_keys() -> Set[str]:
    """Widgets whose count contributes to the pending-actions badge."""
    return {
        w.key for w in WIDGET_CATALOG.values() if w.category == "action"
    }


# ============================================================
# Pending-count aggregation (pure)
# ============================================================


def sum_pending_counts(payloads: Dict[str, Any]) -> int:
    """Sum every payload['count'] over action-category widgets present
    in the render set. Payload builders emit `count` (int) at the top
    level; anything else is ignored so a widget can carry richer data
    without breaking the badge.
    """
    keys = actionable_widget_keys()
    total = 0
    for key, payload in payloads.items():
        if key not in keys:
            continue
        if not isinstance(payload, dict):
            continue
        v = payload.get("count")
        if isinstance(v, int):
            total += v
    return total
