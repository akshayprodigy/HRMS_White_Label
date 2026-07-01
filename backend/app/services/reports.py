"""Report engine — pure builders, one per report.

Contract
========
A report is a pure function of already-fetched inputs → `ReportResult`.
The endpoint layer does the DB query; this module contains no I/O.
That split makes every report unit-testable with plain dicts.

Every report returns:
- rows       : list of dicts, one per row
- columns    : list of ColumnDef with type + display width
- totals     : dict keyed by column key (optional per report)
- meta       : dict (period label, generated_at, filter echo)

The `type` on ColumnDef drives the export layer (Excel number formats,
PDF alignment, CSV formatting) so we get consistent rendering across
xlsx/csv/pdf/json without repeating format logic per report.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional


# ============================================================
# Shared types
# ============================================================


@dataclass
class ReportFilter:
    """Universal filter model. Each report reads only the fields it
    understands and ignores the rest — callers can pass one payload
    across reports without munging."""
    start: Optional[date] = None
    end: Optional[date] = None
    department: Optional[str] = None
    employee_ids: Optional[List[int]] = None
    shift_template_id: Optional[int] = None
    designation_id: Optional[int] = None
    grade_id: Optional[int] = None
    payroll_run_id: Optional[int] = None
    fy: Optional[str] = None
    # Manager scope. When set, reports MUST restrict the visible
    # employee set to the manager's direct reports (list of user_ids
    # provided by the caller). None → no restriction (HR view).
    manager_scope_user_ids: Optional[List[int]] = None
    # Free-form extras (kept as dict so we don't need to churn this
    # dataclass for a one-off report). Reports docstring what keys
    # they read.
    extras: Dict[str, Any] = field(default_factory=dict)


class ColumnType:
    """Every export renderer understands these seven types. Adding a
    new one is a two-place change (this constant + the renderer
    switch)."""
    TEXT = "text"
    INT = "int"
    CURRENCY = "currency"     # ₹ in Indian grouping
    HOURS = "hours"           # e.g. "8h 30m"
    PERCENT = "percent"
    DATE = "date"
    DATETIME = "datetime"


@dataclass
class ColumnDef:
    key: str
    label: str
    type: str = ColumnType.TEXT
    width: Optional[int] = None      # for Excel column width (in Excel units)
    align: Optional[str] = None      # "left" | "right" | "center"


@dataclass
class ReportResult:
    rows: List[dict]
    columns: List[ColumnDef]
    totals: Dict[str, Any] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)


# ============================================================
# Indian currency formatting
# ============================================================


def fmt_inr(v: Any, symbol: bool = True) -> str:
    """Format a number as Indian currency: ₹12,34,567.89.

    The standard Python 'n' locale-aware formatter varies by system;
    we implement grouping manually to guarantee lakhs/crores style
    everywhere.
    """
    if v is None:
        return ""
    try:
        n = float(v)
    except (TypeError, ValueError):
        return str(v)
    neg = n < 0
    n = abs(n)
    int_part = int(n)
    dec_part = round(n - int_part, 2)
    s = str(int_part)
    if len(s) <= 3:
        grouped = s
    else:
        last3 = s[-3:]
        rest = s[:-3]
        # Group `rest` in 2s from the right (Indian numbering).
        chunks = []
        while len(rest) > 2:
            chunks.append(rest[-2:])
            rest = rest[:-2]
        if rest:
            chunks.append(rest)
        chunks.reverse()
        grouped = ",".join(chunks) + "," + last3
    dec = f"{dec_part:.2f}".split(".")[1]
    formatted = f"{grouped}.{dec}"
    if symbol:
        formatted = "₹" + formatted
    if neg:
        formatted = "-" + formatted
    return formatted


def fmt_hours(minutes: Any) -> str:
    """e.g. 145 minutes → '2h 25m'."""
    if minutes is None:
        return ""
    try:
        m = int(minutes)
    except (TypeError, ValueError):
        return str(minutes)
    if m == 0:
        return "0h"
    sign = "-" if m < 0 else ""
    m = abs(m)
    h, rem = divmod(m, 60)
    if rem == 0:
        return f"{sign}{h}h"
    return f"{sign}{h}h {rem:02d}m"


def fmt_percent(v: Any, decimals: int = 2) -> str:
    if v is None:
        return ""
    try:
        return f"{float(v):.{decimals}f}%"
    except (TypeError, ValueError):
        return str(v)


def fmt_date(v: Any) -> str:
    if isinstance(v, (date, datetime)):
        return v.strftime("%d-%b-%Y")
    return "" if v is None else str(v)


def fmt_cell(value: Any, col_type: str) -> str:
    """Central dispatch used by CSV + PDF renderers so formatting is
    identical across output types."""
    if col_type == ColumnType.CURRENCY:
        return fmt_inr(value)
    if col_type == ColumnType.HOURS:
        return fmt_hours(value)
    if col_type == ColumnType.PERCENT:
        return fmt_percent(value)
    if col_type in (ColumnType.DATE, ColumnType.DATETIME):
        return fmt_date(value)
    return "" if value is None else str(value)


# ============================================================
# manager-scope helper
# ============================================================


def apply_manager_scope(
    rows: List[dict], *, user_id_key: str = "user_id",
    scope: Optional[List[int]],
) -> List[dict]:
    """Restrict the row set to the manager's team.

    Applied AFTER build_* so tests can pass unscoped rows in and
    verify scoping separately.
    """
    if scope is None:
        return rows
    scope_set = set(scope)
    return [r for r in rows if r.get(user_id_key) in scope_set]


# ============================================================
# Attendance reports
# ============================================================


@dataclass
class AttendanceRow:
    """Structural input for muster-roll and late/early builders. The
    endpoint layer builds these from Attendance rows joined to Employee.
    """
    user_id: int
    employee_code: str
    full_name: str
    department: str
    work_date: date
    shift_template_id: Optional[int] = None
    shift_name: Optional[str] = None
    shift_start: Optional[Any] = None      # datetime.time
    shift_end: Optional[Any] = None
    grace_in_minutes: int = 0
    grace_out_minutes: int = 0
    punch_in: Optional[datetime] = None
    punch_out: Optional[datetime] = None
    attribution_flag: Optional[str] = None
    geo_flag: Optional[str] = None
    is_leave: bool = False
    is_holiday: bool = False
    is_weekly_off: bool = False


def build_muster_roll(
    *, records: List[AttendanceRow], filters: ReportFilter,
) -> ReportResult:
    """Per-employee per-date presence: P / A / L / WO / H.

    - P  Present  — has punch_in
    - A  Absent   — no punch_in and not leave / WO / holiday
    - L  Leave    — is_leave
    - WO Weekly-off — is_weekly_off
    - H  Holiday  — is_holiday
    """
    columns = [
        ColumnDef("employee_code", "Emp Code", ColumnType.TEXT, width=14),
        ColumnDef("full_name", "Name", ColumnType.TEXT, width=32),
        ColumnDef("department", "Department", ColumnType.TEXT, width=20),
        ColumnDef("shift_name", "Shift", ColumnType.TEXT, width=18),
        ColumnDef("work_date", "Date", ColumnType.DATE, width=14),
        ColumnDef("status", "Status", ColumnType.TEXT, width=10),
        ColumnDef("punch_in", "IN", ColumnType.DATETIME, width=18),
        ColumnDef("punch_out", "OUT", ColumnType.DATETIME, width=18),
        ColumnDef("attribution_flag", "Attr Flag", ColumnType.TEXT, width=14),
        ColumnDef("geo_flag", "Geo Flag", ColumnType.TEXT, width=14),
    ]
    rows: List[dict] = []
    counters = {"P": 0, "A": 0, "L": 0, "WO": 0, "H": 0}
    for r in records:
        if r.is_holiday:
            status = "H"
        elif r.is_weekly_off:
            status = "WO"
        elif r.is_leave:
            status = "L"
        elif r.punch_in is not None:
            status = "P"
        else:
            status = "A"
        counters[status] += 1
        rows.append({
            "user_id": r.user_id,
            "employee_code": r.employee_code,
            "full_name": r.full_name,
            "department": r.department,
            "shift_name": r.shift_name or "",
            "work_date": r.work_date,
            "status": status,
            "punch_in": r.punch_in,
            "punch_out": r.punch_out,
            "attribution_flag": r.attribution_flag or "",
            "geo_flag": r.geo_flag or "",
        })
    rows = apply_manager_scope(
        rows, scope=filters.manager_scope_user_ids,
    )
    total_rows = len(rows)
    total_p = sum(1 for r in rows if r["status"] == "P")
    total_a = sum(1 for r in rows if r["status"] == "A")
    totals = {
        "employee_code": "TOTAL",
        "status": (
            f"P={total_p}  A={total_a}  L={counters['L']}  "
            f"WO={counters['WO']}  H={counters['H']}"
        ),
        "punch_in": total_rows,
    }
    return ReportResult(
        rows=rows, columns=columns, totals=totals,
        meta={
            "period": _period_label(filters.start, filters.end),
            "row_count": total_rows,
        },
    )


def build_late_early(
    *, records: List[AttendanceRow], filters: ReportFilter,
) -> ReportResult:
    """Late-comers + early-leavers against shift start/end + grace.

    Only rows with (late_minutes>0 or early_minutes>0) are kept. Zero
    on time is excluded from the output.
    """
    columns = [
        ColumnDef("work_date", "Date", ColumnType.DATE, width=14),
        ColumnDef("employee_code", "Emp Code", ColumnType.TEXT, width=14),
        ColumnDef("full_name", "Name", ColumnType.TEXT, width=32),
        ColumnDef("department", "Department", ColumnType.TEXT, width=20),
        ColumnDef("shift_name", "Shift", ColumnType.TEXT, width=18),
        ColumnDef("late_minutes", "Late (min)", ColumnType.INT, width=12),
        ColumnDef("early_minutes", "Early (min)", ColumnType.INT, width=12),
    ]
    rows: List[dict] = []
    total_late = 0
    total_early = 0
    for r in records:
        if r.punch_in is None or r.shift_start is None:
            continue
        # Naive minutes-late — the resolver's exact math already lives
        # in the attendance module; we recompute the SAME formula here
        # from the timestamp so this stays pure (no attendance-module
        # import).
        shift_start_dt = datetime.combine(
            r.work_date, r.shift_start, tzinfo=r.punch_in.tzinfo,
        )
        # Grace: on-time if punch_in ≤ start + grace_in.
        threshold_late = shift_start_dt + timedelta(minutes=r.grace_in_minutes)
        late = max(0, int((r.punch_in - threshold_late).total_seconds() // 60))
        early = 0
        if r.punch_out is not None and r.shift_end is not None:
            shift_end_dt = datetime.combine(
                r.work_date, r.shift_end, tzinfo=r.punch_out.tzinfo,
            )
            threshold_early = shift_end_dt - timedelta(minutes=r.grace_out_minutes)
            if r.punch_out < threshold_early:
                early = int(
                    (threshold_early - r.punch_out).total_seconds() // 60
                )
        if late == 0 and early == 0:
            continue
        rows.append({
            "user_id": r.user_id,
            "work_date": r.work_date,
            "employee_code": r.employee_code,
            "full_name": r.full_name,
            "department": r.department,
            "shift_name": r.shift_name or "",
            "late_minutes": late,
            "early_minutes": early,
        })
        total_late += late
        total_early += early
    rows = apply_manager_scope(rows, scope=filters.manager_scope_user_ids)
    return ReportResult(
        rows=rows, columns=columns,
        totals={
            "employee_code": "TOTAL",
            "late_minutes": total_late,
            "early_minutes": total_early,
        },
        meta={
            "period": _period_label(filters.start, filters.end),
            "row_count": len(rows),
        },
    )


@dataclass
class OTEntryRow:
    user_id: int
    employee_code: str
    full_name: str
    department: str
    work_date: date
    ot_minutes: int
    ot_amount: float
    multiplier_used: float
    day_type: str
    status: str


def build_ot_report(
    *, entries: List[OTEntryRow], filters: ReportFilter,
) -> ReportResult:
    """Approved OT by employee. Aggregates rows to one line per
    employee OR passes-through per-row if `extras['per_row'] is True`."""
    per_row = bool(filters.extras.get("per_row"))
    approved_only = filters.extras.get("approved_only", True)
    src = [
        e for e in entries
        if not approved_only or e.status in ("approved", "auto_approved")
    ]
    if per_row:
        columns = [
            ColumnDef("work_date", "Date", ColumnType.DATE, width=14),
            ColumnDef("employee_code", "Emp Code", ColumnType.TEXT, width=14),
            ColumnDef("full_name", "Name", ColumnType.TEXT, width=32),
            ColumnDef("department", "Department", ColumnType.TEXT, width=20),
            ColumnDef("day_type", "Day type", ColumnType.TEXT, width=12),
            ColumnDef("ot_minutes", "OT minutes", ColumnType.HOURS, width=12),
            ColumnDef("multiplier_used", "Multiplier", ColumnType.TEXT, width=10),
            ColumnDef("ot_amount", "OT amount", ColumnType.CURRENCY, width=14),
            ColumnDef("status", "Status", ColumnType.TEXT, width=12),
        ]
        rows = [
            {
                "user_id": e.user_id,
                "work_date": e.work_date,
                "employee_code": e.employee_code,
                "full_name": e.full_name,
                "department": e.department,
                "day_type": e.day_type,
                "ot_minutes": e.ot_minutes,
                "multiplier_used": f"{e.multiplier_used}×",
                "ot_amount": e.ot_amount,
                "status": e.status,
            }
            for e in src
        ]
    else:
        columns = [
            ColumnDef("employee_code", "Emp Code", ColumnType.TEXT, width=14),
            ColumnDef("full_name", "Name", ColumnType.TEXT, width=32),
            ColumnDef("department", "Department", ColumnType.TEXT, width=20),
            ColumnDef("entry_count", "Entries", ColumnType.INT, width=10),
            ColumnDef("total_minutes", "OT total", ColumnType.HOURS, width=14),
            ColumnDef("total_amount", "OT amount", ColumnType.CURRENCY, width=14),
        ]
        agg: Dict[int, dict] = {}
        for e in src:
            row = agg.setdefault(e.user_id, {
                "user_id": e.user_id,
                "employee_code": e.employee_code,
                "full_name": e.full_name,
                "department": e.department,
                "entry_count": 0, "total_minutes": 0, "total_amount": 0.0,
            })
            row["entry_count"] += 1
            row["total_minutes"] += e.ot_minutes
            row["total_amount"] += e.ot_amount
        rows = list(agg.values())

    rows = apply_manager_scope(rows, scope=filters.manager_scope_user_ids)
    if per_row:
        totals = {
            "employee_code": "TOTAL",
            "ot_minutes": sum(r["ot_minutes"] for r in rows),
            "ot_amount": round(sum(r["ot_amount"] for r in rows), 2),
        }
    else:
        totals = {
            "employee_code": "TOTAL",
            "total_minutes": sum(r["total_minutes"] for r in rows),
            "total_amount": round(sum(r["total_amount"] for r in rows), 2),
        }
    return ReportResult(
        rows=rows, columns=columns, totals=totals,
        meta={
            "period": _period_label(filters.start, filters.end),
            "row_count": len(rows),
        },
    )


def build_absenteeism(
    *, records: List[AttendanceRow], filters: ReportFilter,
) -> ReportResult:
    """% absent per employee over the period. Denominator = work-days
    (excludes WO + H)."""
    columns = [
        ColumnDef("employee_code", "Emp Code", ColumnType.TEXT, width=14),
        ColumnDef("full_name", "Name", ColumnType.TEXT, width=32),
        ColumnDef("department", "Department", ColumnType.TEXT, width=20),
        ColumnDef("work_days", "Work days", ColumnType.INT, width=10),
        ColumnDef("present_days", "Present", ColumnType.INT, width=10),
        ColumnDef("absent_days", "Absent", ColumnType.INT, width=10),
        ColumnDef("absent_pct", "Absent %", ColumnType.PERCENT, width=12),
    ]
    per_user: Dict[int, dict] = {}
    for r in records:
        row = per_user.setdefault(r.user_id, {
            "user_id": r.user_id,
            "employee_code": r.employee_code,
            "full_name": r.full_name,
            "department": r.department,
            "work_days": 0, "present_days": 0, "absent_days": 0,
        })
        if r.is_holiday or r.is_weekly_off:
            continue
        row["work_days"] += 1
        if r.punch_in is not None:
            row["present_days"] += 1
        elif not r.is_leave:
            row["absent_days"] += 1
    rows = []
    for row in per_user.values():
        wd = row["work_days"] or 1
        row["absent_pct"] = round((row["absent_days"] / wd) * 100.0, 2)
        rows.append(row)
    rows = apply_manager_scope(rows, scope=filters.manager_scope_user_ids)
    rows.sort(key=lambda r: r["absent_pct"], reverse=True)
    return ReportResult(
        rows=rows, columns=columns,
        totals={
            "employee_code": "TOTAL",
            "work_days": sum(r["work_days"] for r in rows),
            "present_days": sum(r["present_days"] for r in rows),
            "absent_days": sum(r["absent_days"] for r in rows),
        },
        meta={
            "period": _period_label(filters.start, filters.end),
            "row_count": len(rows),
        },
    )


def build_flag_summary(
    *, records: List[AttendanceRow], filters: ReportFilter,
) -> ReportResult:
    """Attribution + geo flag counts per employee."""
    columns = [
        ColumnDef("employee_code", "Emp Code", ColumnType.TEXT, width=14),
        ColumnDef("full_name", "Name", ColumnType.TEXT, width=32),
        ColumnDef("department", "Department", ColumnType.TEXT, width=20),
        ColumnDef("outside_window", "Outside window", ColumnType.INT, width=14),
        ColumnDef("ambiguous", "Ambiguous", ColumnType.INT, width=12),
        ColumnDef("no_shift", "No shift", ColumnType.INT, width=10),
        ColumnDef("outside_geofence", "Outside geo", ColumnType.INT, width=12),
        ColumnDef("mock_location", "Mock loc", ColumnType.INT, width=10),
        ColumnDef("low_accuracy", "Low accuracy", ColumnType.INT, width=12),
    ]
    per_user: Dict[int, dict] = {}
    for r in records:
        row = per_user.setdefault(r.user_id, {
            "user_id": r.user_id,
            "employee_code": r.employee_code, "full_name": r.full_name,
            "department": r.department,
            "outside_window": 0, "ambiguous": 0, "no_shift": 0,
            "outside_geofence": 0, "mock_location": 0, "low_accuracy": 0,
        })
        af = (r.attribution_flag or "").lower()
        if af in row: row[af] += 1
        gf = (r.geo_flag or "").lower()
        if gf in row: row[gf] += 1
    rows = list(per_user.values())
    # Drop employees with all-zero counts.
    rows = [
        r for r in rows if any(r[k] for k in (
            "outside_window", "ambiguous", "no_shift",
            "outside_geofence", "mock_location", "low_accuracy",
        ))
    ]
    rows = apply_manager_scope(rows, scope=filters.manager_scope_user_ids)
    return ReportResult(
        rows=rows, columns=columns,
        totals={
            "employee_code": "TOTAL",
            **{k: sum(r[k] for r in rows) for k in (
                "outside_window", "ambiguous", "no_shift",
                "outside_geofence", "mock_location", "low_accuracy",
            )},
        },
        meta={
            "period": _period_label(filters.start, filters.end),
            "row_count": len(rows),
        },
    )


# ============================================================
# Leave reports
# ============================================================


@dataclass
class LeaveBalanceRow:
    user_id: int
    employee_code: str
    full_name: str
    department: str
    leave_type: str
    quota: float
    used: float
    balance: float


def build_leave_balance(
    *, balances: List[LeaveBalanceRow], filters: ReportFilter,
) -> ReportResult:
    columns = [
        ColumnDef("employee_code", "Emp Code", ColumnType.TEXT, width=14),
        ColumnDef("full_name", "Name", ColumnType.TEXT, width=32),
        ColumnDef("department", "Department", ColumnType.TEXT, width=20),
        ColumnDef("leave_type", "Leave type", ColumnType.TEXT, width=18),
        ColumnDef("quota", "Quota", ColumnType.INT, width=10),
        ColumnDef("used", "Used", ColumnType.INT, width=10),
        ColumnDef("balance", "Balance", ColumnType.INT, width=10),
    ]
    rows = [
        {
            "user_id": b.user_id, "employee_code": b.employee_code,
            "full_name": b.full_name, "department": b.department,
            "leave_type": b.leave_type, "quota": b.quota,
            "used": b.used, "balance": b.balance,
        }
        for b in balances
    ]
    rows = apply_manager_scope(rows, scope=filters.manager_scope_user_ids)
    return ReportResult(
        rows=rows, columns=columns,
        totals={
            "employee_code": "TOTAL",
            "quota": sum(r["quota"] for r in rows),
            "used": sum(r["used"] for r in rows),
            "balance": sum(r["balance"] for r in rows),
        },
        meta={"row_count": len(rows)},
    )


def build_leave_utilization(
    *, balances: List[LeaveBalanceRow], filters: ReportFilter,
) -> ReportResult:
    columns = [
        ColumnDef("leave_type", "Leave type", ColumnType.TEXT, width=18),
        ColumnDef("total_quota", "Total quota", ColumnType.INT, width=12),
        ColumnDef("total_used", "Total used", ColumnType.INT, width=12),
        ColumnDef("utilization_pct", "Utilization %", ColumnType.PERCENT, width=14),
        ColumnDef("employees_with_zero_balance", "Zero balance emps", ColumnType.INT, width=18),
    ]
    per_type: Dict[str, dict] = {}
    for b in balances:
        row = per_type.setdefault(b.leave_type, {
            "leave_type": b.leave_type,
            "total_quota": 0, "total_used": 0,
            "employees_with_zero_balance": 0,
        })
        row["total_quota"] += b.quota
        row["total_used"] += b.used
        if b.balance <= 0:
            row["employees_with_zero_balance"] += 1
    rows = []
    for row in per_type.values():
        q = row["total_quota"] or 1
        row["utilization_pct"] = round((row["total_used"] / q) * 100.0, 2)
        rows.append(row)
    return ReportResult(
        rows=rows, columns=columns,
        totals={
            "leave_type": "TOTAL",
            "total_quota": sum(r["total_quota"] for r in rows),
            "total_used": sum(r["total_used"] for r in rows),
        },
        meta={"row_count": len(rows)},
    )


# ============================================================
# Payroll / compensation reports
# ============================================================


@dataclass
class PayrollLineRow:
    user_id: int
    employee_code: str
    full_name: str
    department: str
    base_salary: float
    payable_days: float
    lop_days: float
    gross_pay: float
    net_pay: float
    allowances: dict
    deductions: dict
    bank_account: Optional[str] = None
    bank_name: Optional[str] = None
    ifsc: Optional[str] = None


def build_salary_register(
    *, lines: List[PayrollLineRow], filters: ReportFilter,
) -> ReportResult:
    """Full salary register for a finalized payroll run. Endpoint layer
    is responsible for calling this only on FINALIZED/PUBLISHED runs.
    """
    columns = [
        ColumnDef("employee_code", "Emp Code", ColumnType.TEXT, width=14),
        ColumnDef("full_name", "Name", ColumnType.TEXT, width=32),
        ColumnDef("department", "Department", ColumnType.TEXT, width=20),
        ColumnDef("payable_days", "Days", ColumnType.INT, width=8),
        ColumnDef("lop_days", "LOP", ColumnType.INT, width=8),
        ColumnDef("basic", "Basic", ColumnType.CURRENCY, width=14),
        ColumnDef("hra", "HRA", ColumnType.CURRENCY, width=14),
        ColumnDef("conveyance", "Conveyance", ColumnType.CURRENCY, width=14),
        ColumnDef("other", "Other", ColumnType.CURRENCY, width=14),
        ColumnDef("overtime", "OT", ColumnType.CURRENCY, width=12),
        ColumnDef("night_allowance", "Night", ColumnType.CURRENCY, width=12),
        ColumnDef("arrear", "Arrear", ColumnType.CURRENCY, width=12),
        ColumnDef("gross_pay", "Gross", ColumnType.CURRENCY, width=14),
        ColumnDef("employee_pf", "PF", ColumnType.CURRENCY, width=12),
        ColumnDef("employee_esi", "ESI", ColumnType.CURRENCY, width=12),
        ColumnDef("professional_tax", "PT", ColumnType.CURRENCY, width=10),
        ColumnDef("tds", "TDS", ColumnType.CURRENCY, width=12),
        ColumnDef("total_deductions", "Deductions", ColumnType.CURRENCY, width=14),
        ColumnDef("net_pay", "Net Pay", ColumnType.CURRENCY, width=14),
    ]
    rows = []
    for ln in lines:
        al = ln.allowances or {}
        ded = ln.deductions or {}
        rows.append({
            "user_id": ln.user_id,
            "employee_code": ln.employee_code,
            "full_name": ln.full_name,
            "department": ln.department,
            "payable_days": ln.payable_days,
            "lop_days": ln.lop_days,
            "basic": al.get("basic_salary_actual", ln.base_salary),
            "hra": al.get("hra_actual", 0.0),
            "conveyance": al.get("conveyance_actual", 0.0),
            "other": al.get("other_allowance_actual", 0.0),
            "overtime": al.get("overtime", 0.0),
            "night_allowance": al.get("night_allowance", 0.0),
            "arrear": al.get("arrear", 0.0),
            "gross_pay": ln.gross_pay,
            "employee_pf": ded.get("employee_pf", 0.0),
            "employee_esi": ded.get("employee_esi", 0.0),
            "professional_tax": ded.get("professional_tax", 0.0),
            "tds": ded.get("tds", 0.0),
            "total_deductions": ded.get("total_deductions", 0.0),
            "net_pay": ln.net_pay,
        })
    numeric_cols = [
        "basic", "hra", "conveyance", "other", "overtime", "night_allowance",
        "arrear", "gross_pay", "employee_pf", "employee_esi",
        "professional_tax", "tds", "total_deductions", "net_pay",
    ]
    totals = {
        "employee_code": "TOTAL",
        **{k: round(sum(r.get(k, 0.0) for r in rows), 2) for k in numeric_cols},
    }
    return ReportResult(
        rows=rows, columns=columns, totals=totals,
        meta={"row_count": len(rows)},
    )


def build_bank_advice(
    *, lines: List[PayrollLineRow], filters: ReportFilter,
) -> ReportResult:
    """NEFT bulk upload layout.

    Assumption: SBI/HDFC/ICICI common corporate bulk NEFT CSV layout —
    Beneficiary Account Number, Beneficiary Name, Beneficiary IFSC,
    Amount, Payment Mode (N=NEFT), Reference, Payment Details.

    Bank-specific templates (e.g. YES Bank fixed-width, AXIS pipe-
    delimited) are drop-in variants — swap the columns + fmt_cell
    call.
    """
    columns = [
        ColumnDef("bank_account", "Beneficiary Account", ColumnType.TEXT, width=22),
        ColumnDef("full_name", "Beneficiary Name", ColumnType.TEXT, width=32),
        ColumnDef("ifsc", "IFSC", ColumnType.TEXT, width=14),
        ColumnDef("amount", "Amount", ColumnType.CURRENCY, width=14),
        ColumnDef("mode", "Mode", ColumnType.TEXT, width=8),
        ColumnDef("reference", "Reference", ColumnType.TEXT, width=20),
        ColumnDef("purpose", "Payment Purpose", ColumnType.TEXT, width=32),
    ]
    rows = []
    missing = 0
    ref_prefix = filters.extras.get("reference_prefix", "SALARY")
    for ln in lines:
        if not ln.bank_account or not ln.ifsc:
            missing += 1
            continue
        rows.append({
            "user_id": ln.user_id,
            "bank_account": ln.bank_account,
            "full_name": ln.full_name,
            "ifsc": ln.ifsc,
            "amount": round(ln.net_pay, 2),
            "mode": "N",
            "reference": f"{ref_prefix}-{ln.employee_code}",
            "purpose": f"Salary payment {ln.employee_code}",
        })
    return ReportResult(
        rows=rows, columns=columns,
        totals={
            "bank_account": "TOTAL",
            "amount": round(sum(r["amount"] for r in rows), 2),
        },
        meta={
            "row_count": len(rows),
            "missing_bank_details": missing,
            "note": (
                "Assumption: common NEFT CSV. State the target bank if "
                "another template (fixed-width, tab-delimited) is needed."
            ),
        },
    )


@dataclass
class StatutorySummaryInput:
    period: str                    # "MM/YYYY"
    total_employees: int
    total_employee_pf: float
    total_employer_pf: float
    total_eps: float
    total_employee_esic: float
    total_employer_esic: float
    total_pt: float
    total_tds: float


def build_statutory_summary(
    *, months: List[StatutorySummaryInput], filters: ReportFilter,
) -> ReportResult:
    """PF/ESIC/PT/TDS totals per month. Reads from the Part 1/2 filings
    output — does NOT recompute."""
    columns = [
        ColumnDef("period", "Period", ColumnType.TEXT, width=12),
        ColumnDef("total_employees", "Employees", ColumnType.INT, width=12),
        ColumnDef("total_employee_pf", "EE PF", ColumnType.CURRENCY, width=14),
        ColumnDef("total_employer_pf", "ER PF", ColumnType.CURRENCY, width=14),
        ColumnDef("total_eps", "EPS", ColumnType.CURRENCY, width=12),
        ColumnDef("total_employee_esic", "EE ESIC", ColumnType.CURRENCY, width=12),
        ColumnDef("total_employer_esic", "ER ESIC", ColumnType.CURRENCY, width=12),
        ColumnDef("total_pt", "PT", ColumnType.CURRENCY, width=12),
        ColumnDef("total_tds", "TDS", ColumnType.CURRENCY, width=14),
    ]
    rows = [
        {
            "period": m.period,
            "total_employees": m.total_employees,
            "total_employee_pf": m.total_employee_pf,
            "total_employer_pf": m.total_employer_pf,
            "total_eps": m.total_eps,
            "total_employee_esic": m.total_employee_esic,
            "total_employer_esic": m.total_employer_esic,
            "total_pt": m.total_pt,
            "total_tds": m.total_tds,
        }
        for m in months
    ]
    numeric = [
        "total_employee_pf", "total_employer_pf", "total_eps",
        "total_employee_esic", "total_employer_esic", "total_pt", "total_tds",
    ]
    return ReportResult(
        rows=rows, columns=columns,
        totals={
            "period": "TOTAL",
            **{k: round(sum(r[k] for r in rows), 2) for k in numeric},
        },
        meta={"row_count": len(rows)},
    )


@dataclass
class RevisionRow:
    user_id: int
    employee_code: str
    full_name: str
    department: str
    revision_type: str
    effective_from: date
    old_ctc: float
    new_ctc: float
    hike_amount: float
    hike_percent: float
    status: str


def build_increment_report(
    *, revisions: List[RevisionRow], filters: ReportFilter,
) -> ReportResult:
    columns = [
        ColumnDef("employee_code", "Emp Code", ColumnType.TEXT, width=14),
        ColumnDef("full_name", "Name", ColumnType.TEXT, width=32),
        ColumnDef("department", "Department", ColumnType.TEXT, width=20),
        ColumnDef("revision_type", "Type", ColumnType.TEXT, width=14),
        ColumnDef("effective_from", "Effective", ColumnType.DATE, width=14),
        ColumnDef("old_ctc", "Old CTC", ColumnType.CURRENCY, width=14),
        ColumnDef("new_ctc", "New CTC", ColumnType.CURRENCY, width=14),
        ColumnDef("hike_amount", "Hike ₹", ColumnType.CURRENCY, width=14),
        ColumnDef("hike_percent", "Hike %", ColumnType.PERCENT, width=10),
        ColumnDef("status", "Status", ColumnType.TEXT, width=12),
    ]
    rows = [
        {
            "user_id": r.user_id,
            "employee_code": r.employee_code, "full_name": r.full_name,
            "department": r.department,
            "revision_type": r.revision_type,
            "effective_from": r.effective_from,
            "old_ctc": r.old_ctc, "new_ctc": r.new_ctc,
            "hike_amount": r.hike_amount, "hike_percent": r.hike_percent,
            "status": r.status,
        }
        for r in revisions
    ]
    rows = apply_manager_scope(rows, scope=filters.manager_scope_user_ids)
    total_hike = round(sum(r["hike_amount"] for r in rows), 2)
    avg_pct = round(
        (sum(r["hike_percent"] for r in rows) / len(rows)) if rows else 0.0, 2,
    )
    return ReportResult(
        rows=rows, columns=columns,
        totals={
            "employee_code": "TOTAL",
            "hike_amount": total_hike,
            "hike_percent": avg_pct,
        },
        meta={
            "period": _period_label(filters.start, filters.end),
            "row_count": len(rows),
        },
    )


# ============================================================
# Headcount / attrition reports
# ============================================================


@dataclass
class MonthlyHeadcountRow:
    month_label: str        # "Jan 2026"
    year: int
    month: int
    opening: int
    joiners: int
    leavers: int
    closing: int


def build_headcount_trend(
    *, months: List[MonthlyHeadcountRow], filters: ReportFilter,
) -> ReportResult:
    columns = [
        ColumnDef("month_label", "Month", ColumnType.TEXT, width=14),
        ColumnDef("opening", "Opening", ColumnType.INT, width=10),
        ColumnDef("joiners", "Joiners", ColumnType.INT, width=10),
        ColumnDef("leavers", "Leavers", ColumnType.INT, width=10),
        ColumnDef("net", "Net", ColumnType.INT, width=10),
        ColumnDef("closing", "Closing", ColumnType.INT, width=10),
    ]
    rows = []
    for m in months:
        rows.append({
            "month_label": m.month_label,
            "year": m.year, "month": m.month,
            "opening": m.opening, "joiners": m.joiners,
            "leavers": m.leavers, "net": m.joiners - m.leavers,
            "closing": m.closing,
        })
    return ReportResult(
        rows=rows, columns=columns,
        totals={
            "month_label": "TOTAL",
            "joiners": sum(r["joiners"] for r in rows),
            "leavers": sum(r["leavers"] for r in rows),
            "net": sum(r["net"] for r in rows),
        },
        meta={"row_count": len(rows)},
    )


def compute_attrition_pct(
    *, leavers: int, avg_headcount: float,
) -> float:
    """Annualized attrition percentage.

    formula: attrition = leavers / avg_headcount * 100 (period-scaled
    by the caller — for annual we just pass yearly totals; for
    monthly we pass one month's numbers).
    """
    if avg_headcount <= 0:
        return 0.0
    return round((leavers / avg_headcount) * 100.0, 2)


@dataclass
class AttritionInput:
    month_label: str
    year: int
    month: int
    leavers: int
    voluntary: int
    involuntary: int
    avg_headcount: float
    department: Optional[str] = None


def build_attrition_report(
    *, months: List[AttritionInput], filters: ReportFilter,
) -> ReportResult:
    columns = [
        ColumnDef("month_label", "Month", ColumnType.TEXT, width=14),
        ColumnDef("department", "Department", ColumnType.TEXT, width=20),
        ColumnDef("leavers", "Leavers", ColumnType.INT, width=10),
        ColumnDef("voluntary", "Voluntary", ColumnType.INT, width=10),
        ColumnDef("involuntary", "Involuntary", ColumnType.INT, width=10),
        ColumnDef("avg_headcount", "Avg HC", ColumnType.INT, width=10),
        ColumnDef("attrition_pct", "Attrition %", ColumnType.PERCENT, width=12),
    ]
    rows = []
    for m in months:
        rows.append({
            "month_label": m.month_label,
            "department": m.department or "All",
            "leavers": m.leavers, "voluntary": m.voluntary,
            "involuntary": m.involuntary,
            "avg_headcount": round(m.avg_headcount, 1),
            "attrition_pct": compute_attrition_pct(
                leavers=m.leavers, avg_headcount=m.avg_headcount,
            ),
        })
    totals_avg = (
        round(sum(r["attrition_pct"] for r in rows) / len(rows), 2)
        if rows else 0.0
    )
    return ReportResult(
        rows=rows, columns=columns,
        totals={
            "month_label": "AVG",
            "leavers": sum(r["leavers"] for r in rows),
            "voluntary": sum(r["voluntary"] for r in rows),
            "involuntary": sum(r["involuntary"] for r in rows),
            "attrition_pct": totals_avg,
        },
        meta={"row_count": len(rows)},
    )


# ============================================================
# small utilities
# ============================================================


def _period_label(start: Optional[date], end: Optional[date]) -> str:
    if start and end:
        return f"{fmt_date(start)} → {fmt_date(end)}"
    if start:
        return f"from {fmt_date(start)}"
    if end:
        return f"to {fmt_date(end)}"
    return "all-time"
