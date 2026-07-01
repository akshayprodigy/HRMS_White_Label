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
    ]


def register_descriptors(fetchers: Dict[str, Any]) -> None:
    """Register the catalog with fetchers injected from the endpoint
    layer. Idempotent — safe to call at every endpoint import."""
    REGISTRY._by_key.clear()
    for d in build_descriptors_no_fetchers():
        d.fetch_and_build = fetchers.get(d.key)
        REGISTRY.register(d)
