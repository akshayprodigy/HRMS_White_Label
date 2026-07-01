"""Report catalog — the metadata registry the frontend reads to build
the reports catalog page and the run-report endpoints dispatch through.

Each ReportDescriptor pairs:
- a stable key       (URL/API-facing, don't rename)
- a human name / description
- category           (used to group in the catalog UI)
- filter schema      (which filter fields matter for THIS report)
- permission         (which RBAC perm gates this report)
- is_sensitive       (comp/statutory → audit-log on export)
- fetch_and_build    (async callable: session, ReportFilter → ReportResult)

The fetch_and_build callable is injected at endpoint-registration time
(circular-import avoidance — reports.py can't import endpoints).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

from app.services.reports import ReportFilter, ReportResult


class ReportCategory:
    ATTENDANCE = "attendance"
    LEAVE = "leave"
    PAYROLL = "payroll"
    STATUTORY = "statutory"
    HEADCOUNT = "headcount"
    PERFORMANCE = "performance"
    EXPENSE = "expense"


@dataclass
class ReportFilterSchema:
    """Describe the filter fields the frontend should surface for a
    given report. Types match the UI form widget: 'date' → date picker,
    'text' → free-form, 'select' → dropdown with `options`.
    """
    key: str
    label: str
    type: str = "text"          # date | text | int | select | employee
                                # | payroll_run | shift | fy
    required: bool = False
    options: Optional[List[Dict[str, Any]]] = None
    hint: Optional[str] = None


@dataclass
class ReportDescriptor:
    key: str
    name: str
    description: str
    category: str
    permission: str
    filters: List[ReportFilterSchema] = field(default_factory=list)
    is_sensitive: bool = False
    # fetch_and_build is Callable[[session, ReportFilter], Awaitable[ReportResult]]
    # Optional[Any] instead of a concrete type so the dataclass stays
    # importable from tests without importing DB machinery.
    fetch_and_build: Optional[Any] = None
    # Managers see only their team when this is True; HR bypasses.
    manager_scoped: bool = False


class ReportRegistry:
    """Simple keyed registry with iteration + category grouping."""
    def __init__(self):
        self._by_key: Dict[str, ReportDescriptor] = {}

    def register(self, r: ReportDescriptor) -> None:
        self._by_key[r.key] = r

    def get(self, key: str) -> Optional[ReportDescriptor]:
        return self._by_key.get(key)

    def all(self) -> List[ReportDescriptor]:
        return list(self._by_key.values())

    def by_category(self) -> Dict[str, List[ReportDescriptor]]:
        out: Dict[str, List[ReportDescriptor]] = {}
        for r in self._by_key.values():
            out.setdefault(r.category, []).append(r)
        return out


REGISTRY = ReportRegistry()


# ============================================================
# Descriptors (populated with fetch_and_build in endpoints/reports.py)
# ============================================================


def build_descriptors_no_fetchers() -> List[ReportDescriptor]:
    """Descriptor list without the fetch_and_build injected.

    The endpoint file injects the async fetchers at import time. This
    function exists so unit tests can verify the catalog shape without
    pulling FastAPI / SQLAlchemy in.
    """
    date_range = [
        ReportFilterSchema("start", "Start date", type="date"),
        ReportFilterSchema("end", "End date", type="date"),
    ]
    dept = ReportFilterSchema("department", "Department", type="text")

    return [
        # ----- Attendance -----
        ReportDescriptor(
            key="muster_roll",
            name="Daily Muster Roll",
            description=(
                "Per-employee per-date presence (P / A / L / WO / H) with "
                "punch times and any flags. The 24×7 baseline report."
            ),
            category=ReportCategory.ATTENDANCE,
            permission="report attendance",
            filters=date_range + [
                dept,
                ReportFilterSchema(
                    "shift_template_id", "Shift", type="shift",
                ),
            ],
            manager_scoped=True,
        ),
        ReportDescriptor(
            key="late_early",
            name="Late-comers & Early-leavers",
            description=(
                "Rows where punch violates shift start/end after grace. "
                "Uses the same resolver formula as attendance."
            ),
            category=ReportCategory.ATTENDANCE,
            permission="report attendance",
            filters=date_range + [dept],
            manager_scoped=True,
        ),
        ReportDescriptor(
            key="absenteeism",
            name="Absenteeism %",
            description=(
                "Absent / work-days percentage over the period. Denominator "
                "excludes weekly-offs + holidays."
            ),
            category=ReportCategory.ATTENDANCE,
            permission="report attendance",
            filters=date_range + [dept],
            manager_scoped=True,
        ),
        ReportDescriptor(
            key="ot_report",
            name="Overtime Report",
            description=(
                "Approved OT minutes + amount per employee. Toggle "
                "per-row detail vs. aggregate with the per_row extra."
            ),
            category=ReportCategory.ATTENDANCE,
            permission="report attendance",
            filters=date_range + [dept],
            manager_scoped=True,
        ),
        ReportDescriptor(
            key="flag_summary",
            name="Attendance Flag Summary",
            description=(
                "Attribution + geo flag counts per employee. Signals "
                "attendance discipline gaps and geo-policy hits."
            ),
            category=ReportCategory.ATTENDANCE,
            permission="report attendance",
            filters=date_range + [dept],
            manager_scoped=True,
        ),

        # ----- Leave -----
        ReportDescriptor(
            key="leave_balance",
            name="Leave Balance Register",
            description=(
                "Current quota / used / balance per employee per leave "
                "type. Point-in-time snapshot."
            ),
            category=ReportCategory.LEAVE,
            permission="report leave",
            filters=[dept],
            manager_scoped=True,
        ),
        ReportDescriptor(
            key="leave_utilization",
            name="Leave Utilization",
            description=(
                "Utilization percentage by leave type across the org "
                "(or a department slice). Highlights type imbalance."
            ),
            category=ReportCategory.LEAVE,
            permission="report leave",
            filters=[dept],
        ),

        # ----- Payroll -----
        ReportDescriptor(
            key="salary_register",
            name="Salary Register",
            description=(
                "Full salary line-item register for a finalized run. "
                "Sensitive — every export is audit-logged."
            ),
            category=ReportCategory.PAYROLL,
            permission="report payroll",
            filters=[
                ReportFilterSchema(
                    "payroll_run_id", "Payroll run",
                    type="payroll_run", required=True,
                ),
                dept,
            ],
            is_sensitive=True,
        ),
        ReportDescriptor(
            key="bank_advice",
            name="Bank Advice / NEFT File",
            description=(
                "Bank-uploadable NEFT layout. Assumes the common "
                "SBI/HDFC/ICICI bulk CSV format — flag another target "
                "bank in extras if needed."
            ),
            category=ReportCategory.PAYROLL,
            permission="report payroll",
            filters=[
                ReportFilterSchema(
                    "payroll_run_id", "Payroll run",
                    type="payroll_run", required=True,
                ),
            ],
            is_sensitive=True,
        ),
        ReportDescriptor(
            key="increment_report",
            name="Increments & Promotions",
            description=(
                "Salary revisions applied in the period with hike % + "
                "amount. Reads SalaryRevision (does NOT recompute)."
            ),
            category=ReportCategory.PAYROLL,
            permission="report payroll",
            filters=date_range + [dept],
            is_sensitive=True,
        ),

        # ----- Statutory -----
        ReportDescriptor(
            key="statutory_summary",
            name="Statutory Monthly Summary",
            description=(
                "PF / ESIC / PT / TDS totals per month. Aggregates the "
                "Part 1 / Part 2 filing outputs — does NOT recompute."
            ),
            category=ReportCategory.STATUTORY,
            permission="report statutory",
            filters=date_range,
            is_sensitive=True,
        ),

        # ----- Headcount -----
        ReportDescriptor(
            key="headcount_trend",
            name="Headcount Trend (12-month)",
            description=(
                "Rolling monthly opening + joiners + leavers + closing. "
                "Feeds the enriched dashboard time-series chart."
            ),
            category=ReportCategory.HEADCOUNT,
            permission="report headcount",
            filters=[dept],
        ),
        ReportDescriptor(
            key="attrition_report",
            name="Attrition Rate",
            description=(
                "Monthly attrition percentage split by voluntary / "
                "involuntary. Optional department slice."
            ),
            category=ReportCategory.HEADCOUNT,
            permission="report headcount",
            filters=[dept],
        ),

        # ----- Performance -----
        ReportDescriptor(
            key="goal_completion",
            name="Goal Completion by Employee",
            description=(
                "Per-employee latest_progress + status (achieved / "
                "at-risk / cancelled) across a cycle. Reuses the goals "
                "engine — never recomputes ratings."
            ),
            category=ReportCategory.PERFORMANCE,
            permission="performance view all",
            filters=[dept],
            manager_scoped=True,
        ),
        ReportDescriptor(
            key="review_cycle_progress",
            name="Review Cycle Progress",
            description=(
                "For a launched cycle: who is pending self / manager / "
                "calibration / release. Managers see only their team."
            ),
            category=ReportCategory.PERFORMANCE,
            permission="performance view all",
            filters=[
                ReportFilterSchema(
                    "cycle_id", "Review cycle", type="int", required=True,
                ),
                dept,
            ],
            manager_scoped=True,
        ),
        ReportDescriptor(
            key="rating_distribution",
            name="Rating Distribution (Calibration)",
            description=(
                "Percentage distribution across the rating scale for a "
                "cycle — the same numbers driving the calibration board."
            ),
            category=ReportCategory.PERFORMANCE,
            permission="performance calibration",
            filters=[
                ReportFilterSchema(
                    "cycle_id", "Review cycle", type="int", required=True,
                ),
                dept,
            ],
        ),
        ReportDescriptor(
            key="one_on_one_coverage",
            name="1:1 Coverage",
            description=(
                "Manager × reportee 1:1 frequency over the period. Flags "
                "reportees who haven't met with their manager in >30 days."
            ),
            category=ReportCategory.PERFORMANCE,
            permission="performance one_on_one",
            filters=date_range + [dept],
            manager_scoped=True,
        ),

        # ----- Expense / Finance -----
        ReportDescriptor(
            key="expense_by_employee",
            name="Expenses by Employee / Department / Category",
            description=(
                "Approved-or-later expense claim totals grouped as "
                "requested. Rupees at read time; paise on the wire."
            ),
            category=ReportCategory.EXPENSE,
            permission="finance reimburse",
            filters=date_range + [
                dept,
                ReportFilterSchema(
                    "group_by", "Group by",
                    type="select",
                    options=[
                        {"value": "employee", "label": "Employee"},
                        {"value": "department", "label": "Department"},
                        {"value": "category", "label": "Category"},
                    ],
                ),
            ],
            is_sensitive=True,
        ),
        ReportDescriptor(
            key="pending_reimbursements",
            name="Pending Reimbursements (Finance Queue)",
            description=(
                "Approved claims awaiting direct-reimbursement or "
                "payroll injection. Ordered by claim age."
            ),
            category=ReportCategory.EXPENSE,
            permission="finance reimburse",
            filters=[dept],
        ),
        ReportDescriptor(
            key="out_of_policy_claims",
            name="Out-of-policy Expense Claims",
            description=(
                "Claims with warn or block-severity policy flags. Feeds "
                "the finance quality-control review."
            ),
            category=ReportCategory.EXPENSE,
            permission="finance reimburse",
            filters=date_range + [dept],
        ),
        ReportDescriptor(
            key="travel_advance_outstanding",
            name="Travel Advance Outstanding",
            description=(
                "Advances paid but not yet reconciled against actuals. "
                "Mirrors the salary-advance outstanding surface."
            ),
            category=ReportCategory.EXPENSE,
            permission="finance reimburse",
            filters=[dept],
        ),
    ]


def register_descriptors(fetchers: Dict[str, Any]) -> None:
    """Register the catalog with fetchers injected from the endpoint
    layer. Idempotent — safe to call at every endpoint import."""
    REGISTRY._by_key.clear()
    for d in build_descriptors_no_fetchers():
        d.fetch_and_build = fetchers.get(d.key)
        REGISTRY.register(d)
