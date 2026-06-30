"""Statutory filing generators + pure helpers.

Three regulatory streams: EPF (PF ECR text file), ESIC (contribution
CSV), and Professional Tax (per-state monthly summary). Generators read
finalized PayrollLine data — they never recompute salary.

# Documented constants

## EPFO_ECR_DELIMITER = "#~#"
EPFO ECR v2 format separator. Eleven fields per row, one line per
member. Encoded ASCII. The file does NOT carry a header.

## ESIC_CONTRIBUTION_PERIOD_RULE
ESIC defines two six-month contribution periods: April–September and
October–March. The continuation rule (Sec 2(9) ESI Act) says: once an
employee has been covered in a period, they remain covered for the rest
of THAT period even if their wages cross the wage ceiling mid-period.
Captured here as `current_period_window()`.

## PT_PICK_RULE = "state + effective_from + slab_min<=gross<=slab_max"
Pick the slab whose effective_from is the latest ≤ payroll month for the
employee's state, then locate the tier by gross_for_pt. month_index, if
set, scopes the tier to a specific month (Maharashtra Feb).

## DRIFT_TOLERANCE_PAISE = 1
Reconciliation drift between computed-from-config and actual-from-payroll
within ±1 paise (0.01 INR) is treated as a rounding artefact, not drift.
Anything larger surfaces in the report.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Iterable, List, Optional, Protocol


EPFO_ECR_DELIMITER = "#~#"
DRIFT_TOLERANCE_PAISE = 1   # = ₹0.01 in paise — we compare in INR with
# abs(diff) <= 0.011 to be safe with float rounding.
DRIFT_TOLERANCE_INR = 0.011


# =====================================================================
# protocols (structural typing — tests pass plain dataclasses)
# =====================================================================


class ConfigLike(Protocol):
    id: int
    effective_from: date
    pf_employee_rate: float
    pf_employer_rate: float
    eps_rate: float
    pf_wage_ceiling: float
    eps_wage_ceiling: float
    edli_rate: float
    edli_wage_ceiling: float
    epf_admin_rate: float
    esic_employee_rate: float
    esic_employer_rate: float
    esic_wage_ceiling: float


class PTSlabLike(Protocol):
    state: str
    effective_from: date
    slab_min: float
    slab_max: Optional[float]
    monthly_amount: float
    gender: str
    month_index: Optional[int]


class EmployeeDetailLike(Protocol):
    uan: Optional[str]
    pf_member_id: Optional[str]
    esic_ip_number: Optional[str]
    pt_state: Optional[str]
    gender: str
    esic_continuation_until: Optional[date]


# =====================================================================
# config-resolver (effective-dated, "as-of latest <= month-end")
# =====================================================================


def pick_config_for_month(
    configs: Iterable[ConfigLike], year: int, month: int,
) -> Optional[ConfigLike]:
    """Return the latest-effective StatutoryConfig <= last day of month.

    Inactive configs are filtered by the CALLER (so tests can pass a
    pre-filtered list). Returns None when no config is in scope.
    """
    target = date(year, month, 1)
    candidates = [c for c in configs if c.effective_from <= target]
    if not candidates:
        return None
    return max(candidates, key=lambda c: c.effective_from)


# =====================================================================
# PF / ECR
# =====================================================================


@dataclass
class ECRRow:
    """One member's contribution row in the EPFO ECR file.

    Field names match the EPFO column-order so the writer can serialize
    in a single tuple without remapping.
    """
    uan: str
    member_name: str
    gross_wages: float
    epf_wages: float
    eps_wages: float
    edli_wages: float
    epf_contri_remitted: float    # employee EPF share (12% of EPF wages)
    eps_contri_remitted: float    # employer EPS share (8.33% of EPS wages)
    epf_eps_diff_remitted: float  # employer share to EPF account
    ncp_days: int
    refund_of_advances: float = 0.0


def _round2(x: float) -> float:
    return round(float(x), 2)


def compute_ecr_row(
    *,
    uan: str,
    member_name: str,
    gross_wages: float,
    basic_for_pf: float,
    config: ConfigLike,
    ncp_days: int,
    refund_of_advances: float = 0.0,
) -> ECRRow:
    """Compute one member's ECR row from the finalized payroll snapshot.

    `basic_for_pf` is the employee's basic+DA component this month
    (after LOP proration). EPF/EPS/EDLI wages are capped at the config
    ceilings — the classic PF cap. Employee EPF contribution is the
    employee rate × EPF wages.
    """
    epf_wages = min(basic_for_pf, config.pf_wage_ceiling)
    eps_wages = min(basic_for_pf, config.eps_wage_ceiling)
    edli_wages = min(basic_for_pf, config.edli_wage_ceiling)

    epf_employee = _round2(epf_wages * config.pf_employee_rate / 100.0)
    eps_employer = _round2(eps_wages * config.eps_rate / 100.0)
    # Employer's full PF rate − the EPS portion lands in EPF account.
    epf_employer_to_epf = _round2(
        (epf_wages * config.pf_employer_rate / 100.0) - eps_employer
    )

    return ECRRow(
        uan=uan or "0",
        member_name=(member_name or "").strip().upper()[:85],
        gross_wages=_round2(gross_wages),
        epf_wages=_round2(epf_wages),
        eps_wages=_round2(eps_wages),
        edli_wages=_round2(edli_wages),
        epf_contri_remitted=epf_employee,
        eps_contri_remitted=eps_employer,
        epf_eps_diff_remitted=max(0.0, epf_employer_to_epf),
        ncp_days=int(max(0, ncp_days)),
        refund_of_advances=_round2(refund_of_advances),
    )


def render_ecr_text(rows: Iterable[ECRRow]) -> str:
    """Render the ECR text file body. One line per row, delimiter `#~#`,
    integer-rupee amounts (EPFO accepts only whole rupees in the wages
    columns). Contribution columns retain paise rounded to integer too.
    """
    lines: List[str] = []
    for r in rows:
        cells = [
            r.uan,
            r.member_name,
            str(int(round(r.gross_wages))),
            str(int(round(r.epf_wages))),
            str(int(round(r.eps_wages))),
            str(int(round(r.edli_wages))),
            str(int(round(r.epf_contri_remitted))),
            str(int(round(r.eps_contri_remitted))),
            str(int(round(r.epf_eps_diff_remitted))),
            str(int(r.ncp_days)),
            str(int(round(r.refund_of_advances))),
        ]
        lines.append(EPFO_ECR_DELIMITER.join(cells))
    # EPFO accepts LF or CRLF; we use LF.
    return "\n".join(lines) + ("\n" if lines else "")


def summarize_ecr(rows: List[ECRRow]) -> dict:
    return {
        "employee_count": len(rows),
        "total_gross_wages": _round2(sum(r.gross_wages for r in rows)),
        "total_epf_wages": _round2(sum(r.epf_wages for r in rows)),
        "total_eps_wages": _round2(sum(r.eps_wages for r in rows)),
        "total_employee_epf": _round2(sum(r.epf_contri_remitted for r in rows)),
        "total_employer_eps": _round2(sum(r.eps_contri_remitted for r in rows)),
        "total_employer_epf": _round2(sum(r.epf_eps_diff_remitted for r in rows)),
    }


# =====================================================================
# ESIC
# =====================================================================


@dataclass
class ESICRow:
    ip_number: str
    name: str
    days_worked: int
    gross_wages: float
    employee_contribution: float
    employer_contribution: float
    reason_for_zero_workdays: str = ""
    last_working_day: str = ""


def current_period_window(today: date) -> tuple[date, date]:
    """The current ESIC contribution period (April-Sept / Oct-March).

    Returns (period_start, period_end) where both ends are inclusive.
    """
    if 4 <= today.month <= 9:
        return date(today.year, 4, 1), date(today.year, 9, 30)
    # Oct–Dec → period spans this year-Oct .. next-year-Mar
    if today.month >= 10:
        return date(today.year, 10, 1), date(today.year + 1, 3, 31)
    # Jan–Mar → period started last-year-Oct
    return date(today.year - 1, 10, 1), date(today.year, 3, 31)


def is_under_esic(
    *,
    gross_wages_this_month: float,
    config: ConfigLike,
    payroll_month: date,
    continuation_until: Optional[date],
) -> bool:
    """ESIC coverage decision for this month.

    Rules:
    1. If `continuation_until` is set and the payroll month is on/before
       it, the employee STAYS under ESIC regardless of wages — the
       mid-period continuation rule.
    2. Otherwise, covered iff gross <= esic_wage_ceiling.

    Wages strictly above the ceiling and no active continuation = NOT
    under ESIC.
    """
    if (
        continuation_until is not None
        and payroll_month <= continuation_until
    ):
        return True
    return gross_wages_this_month <= config.esic_wage_ceiling


def compute_esic_row(
    *,
    ip_number: str, name: str, days_worked: int,
    gross_wages: float, config: ConfigLike,
) -> ESICRow:
    """ESIC contribution row. Caller decides coverage via is_under_esic;
    this just renders the math when covered.
    """
    employee = _round2(gross_wages * config.esic_employee_rate / 100.0)
    employer = _round2(gross_wages * config.esic_employer_rate / 100.0)
    return ESICRow(
        ip_number=ip_number or "",
        name=(name or "").strip().upper()[:60],
        days_worked=int(max(0, days_worked)),
        gross_wages=_round2(gross_wages),
        employee_contribution=employee,
        employer_contribution=employer,
    )


def render_esic_csv(rows: Iterable[ESICRow]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
    # ESIC accepts CSV/XLSX with this column order.
    w.writerow([
        "IP Number", "IP Name", "No of Days for which wages paid",
        "Total Monthly Wages", "Reason Code for Zero workdays",
        "Last Working Day",
    ])
    for r in rows:
        w.writerow([
            r.ip_number, r.name, r.days_worked, r.gross_wages,
            r.reason_for_zero_workdays, r.last_working_day,
        ])
    return buf.getvalue()


def summarize_esic(rows: List[ESICRow]) -> dict:
    return {
        "employee_count": len(rows),
        "total_gross_wages": _round2(sum(r.gross_wages for r in rows)),
        "total_employee_contribution": _round2(
            sum(r.employee_contribution for r in rows)
        ),
        "total_employer_contribution": _round2(
            sum(r.employer_contribution for r in rows)
        ),
    }


# =====================================================================
# Professional Tax
# =====================================================================


def pick_pt_slab(
    slabs: Iterable[PTSlabLike],
    *,
    state: str,
    year: int, month: int,
    gross_for_pt: float,
    gender: str = "ALL",
) -> Optional[PTSlabLike]:
    """Locate the per-state slab tier for one employee in one month.

    Algorithm:
    1. Filter active slabs for the same state with effective_from <=
       month-start.
    2. From those, keep the rows whose effective_from == the LATEST date
       in that filtered set (slab version live in this month).
    3. Prefer rows with month_index == this month; fall back to NULL.
    4. Prefer rows matching gender; fall back to ALL.
    5. Among the remaining, pick the slab where
       slab_min <= gross_for_pt <= (slab_max or +∞).
    Returns None when nothing matches (= zero PT for this month).
    """
    target = date(year, month, 1)
    same_state = [
        s for s in slabs
        if (s.state or "").upper() == (state or "").upper()
        and s.effective_from <= target
    ]
    if not same_state:
        return None
    latest = max(s.effective_from for s in same_state)
    live = [s for s in same_state if s.effective_from == latest]

    # Month override has priority.
    month_specific = [s for s in live if s.month_index == month]
    pool = month_specific if month_specific else [
        s for s in live if s.month_index is None
    ]

    # Gender preference.
    gender_specific = [
        s for s in pool if (s.gender or "ALL").upper() == gender.upper()
    ]
    chosen_pool = gender_specific if gender_specific else [
        s for s in pool if (s.gender or "ALL").upper() == "ALL"
    ]

    for s in chosen_pool:
        lo = float(s.slab_min)
        hi = float("inf") if s.slab_max is None else float(s.slab_max)
        if lo <= gross_for_pt <= hi:
            return s
    return None


@dataclass
class PTSummaryRow:
    state: str
    employee_count: int
    total_gross_wages: float
    total_pt_amount: float


def render_pt_csv(rows: List[dict]) -> str:
    """Per-employee PT detail for one state. `rows` is the caller-shaped
    list of {employee_id, name, gross_wages, pt_amount, gender}.
    """
    buf = io.StringIO()
    w = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
    w.writerow([
        "Employee ID", "Name", "Gender", "Gross Wages", "Professional Tax",
    ])
    for r in rows:
        w.writerow([
            r.get("employee_id", ""), r.get("name", ""),
            r.get("gender", "ALL"),
            _round2(r.get("gross_wages", 0.0)),
            _round2(r.get("pt_amount", 0.0)),
        ])
    return buf.getvalue()


# =====================================================================
# reconciliation (config-vs-payroll drift detection)
# =====================================================================


@dataclass
class DriftFinding:
    user_id: int
    employee_code: Optional[str]
    name: Optional[str]
    stream: str               # "epf_employee" | "epf_employer_to_epf" |
                              # "eps_employer" | "esic_employee" |
                              # "esic_employer" | "pt"
    expected: float
    actual: float
    diff: float
    note: str = ""


def reconcile_pf(
    *,
    actual_employee_pf: float,
    actual_employer_pf: float,
    basic_for_pf: float,
    config: ConfigLike,
    user_id: int,
    employee_code: Optional[str] = None,
    name: Optional[str] = None,
) -> List[DriftFinding]:
    """Compare what the payroll actually deducted vs. what the active
    config says it should have been. Drift within DRIFT_TOLERANCE_INR
    is suppressed (rounding noise).
    """
    out: List[DriftFinding] = []
    epf_wages = min(basic_for_pf, config.pf_wage_ceiling)
    expected_employee = _round2(epf_wages * config.pf_employee_rate / 100.0)
    expected_employer = _round2(epf_wages * config.pf_employer_rate / 100.0)
    if abs(expected_employee - actual_employee_pf) > DRIFT_TOLERANCE_INR:
        out.append(DriftFinding(
            user_id=user_id, employee_code=employee_code, name=name,
            stream="epf_employee",
            expected=expected_employee, actual=actual_employee_pf,
            diff=_round2(actual_employee_pf - expected_employee),
        ))
    if abs(expected_employer - actual_employer_pf) > DRIFT_TOLERANCE_INR:
        out.append(DriftFinding(
            user_id=user_id, employee_code=employee_code, name=name,
            stream="epf_employer_total",
            expected=expected_employer, actual=actual_employer_pf,
            diff=_round2(actual_employer_pf - expected_employer),
        ))
    return out


def reconcile_esic(
    *,
    actual_employee_esi: float,
    actual_employer_esi: float,
    gross_wages: float,
    config: ConfigLike,
    is_covered: bool,
    user_id: int,
    employee_code: Optional[str] = None,
    name: Optional[str] = None,
) -> List[DriftFinding]:
    out: List[DriftFinding] = []
    if not is_covered:
        # Should be zero. Anything non-zero is drift.
        if actual_employee_esi > DRIFT_TOLERANCE_INR:
            out.append(DriftFinding(
                user_id=user_id, employee_code=employee_code, name=name,
                stream="esic_employee",
                expected=0.0, actual=actual_employee_esi,
                diff=_round2(actual_employee_esi),
                note="Charged ESIC but employee is not covered this month",
            ))
        if actual_employer_esi > DRIFT_TOLERANCE_INR:
            out.append(DriftFinding(
                user_id=user_id, employee_code=employee_code, name=name,
                stream="esic_employer",
                expected=0.0, actual=actual_employer_esi,
                diff=_round2(actual_employer_esi),
            ))
        return out

    expected_employee = _round2(gross_wages * config.esic_employee_rate / 100.0)
    expected_employer = _round2(gross_wages * config.esic_employer_rate / 100.0)
    if abs(expected_employee - actual_employee_esi) > DRIFT_TOLERANCE_INR:
        out.append(DriftFinding(
            user_id=user_id, employee_code=employee_code, name=name,
            stream="esic_employee",
            expected=expected_employee, actual=actual_employee_esi,
            diff=_round2(actual_employee_esi - expected_employee),
        ))
    if abs(expected_employer - actual_employer_esi) > DRIFT_TOLERANCE_INR:
        out.append(DriftFinding(
            user_id=user_id, employee_code=employee_code, name=name,
            stream="esic_employer",
            expected=expected_employer, actual=actual_employer_esi,
            diff=_round2(actual_employer_esi - expected_employer),
        ))
    return out


def reconcile_pt(
    *,
    actual_pt: float,
    expected_pt: float,
    user_id: int,
    employee_code: Optional[str] = None,
    name: Optional[str] = None,
) -> List[DriftFinding]:
    if abs(expected_pt - actual_pt) <= DRIFT_TOLERANCE_INR:
        return []
    return [DriftFinding(
        user_id=user_id, employee_code=employee_code, name=name,
        stream="pt",
        expected=expected_pt, actual=actual_pt,
        diff=_round2(actual_pt - expected_pt),
    )]


# =====================================================================
# compliance due-date helpers
# =====================================================================


def pf_due_date(payroll_year: int, payroll_month: int) -> date:
    """EPF ECR + payment due 15th of the month after payroll month."""
    y, m = (payroll_year, payroll_month + 1) if payroll_month < 12 else (payroll_year + 1, 1)
    return date(y, m, 15)


def esic_due_date(payroll_year: int, payroll_month: int) -> date:
    """ESIC contribution due 15th of the month after payroll month."""
    return pf_due_date(payroll_year, payroll_month)


def pt_due_date(payroll_year: int, payroll_month: int, state: str) -> date:
    """State-wise PT due date. Most states: 21st of next month
    (Karnataka: 20th, Maharashtra: end of next month). Returns a
    representative date — adjust by state when business teams ask.
    """
    state_u = (state or "").upper()
    y, m = (payroll_year, payroll_month + 1) if payroll_month < 12 else (payroll_year + 1, 1)
    if state_u in ("MAHARASHTRA", "MH"):
        # Last day of next month — simple 28th proxy that always exists.
        return date(y, m, 28)
    if state_u in ("KARNATAKA", "KA"):
        return date(y, m, 20)
    return date(y, m, 21)
