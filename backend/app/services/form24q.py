"""Form 24Q quarterly TDS return rendering.

Form 24Q has two annexures:
- Annexure I (deductee details): per-employee per-quarter row of salary
  paid + TDS deducted. Required every quarter (Q1..Q4).
- Annexure II (full-year salary breakdown): required ONLY in Q4 — full
  FY salary + exemptions + deductions per employee.

We render CSV (the FUV / RPU TDS-return prep utilities accept CSV
input). The actual NSDL upload happens off-system.

Pure helpers — no DB, no I/O.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from typing import Iterable, List, Optional


@dataclass
class Form24QAnnexureIRow:
    """One employee, one quarter."""
    pan: str
    name: str
    section: str = "192"            # salary TDS always under §192
    paid_amount: float = 0.0        # quarter's gross salary paid
    tds_deducted: float = 0.0
    tds_deposited: float = 0.0
    deduction_date: Optional[str] = None    # last day of quarter, ISO


@dataclass
class Form24QAnnexureIIRow:
    """One employee, full FY (Q4 only)."""
    pan: str
    name: str
    gross_salary_annual: float
    hra_exemption: float
    standard_deduction: float
    chapter_via_deductions: float
    taxable_income: float
    total_tax: float
    tds_deducted_total: float
    regime: str = "new"


def render_annexure_i_csv(rows: Iterable[Form24QAnnexureIRow]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
    w.writerow([
        "PAN", "Deductee Name", "Section",
        "Amount Paid", "TDS Deducted", "TDS Deposited",
        "Date of Deduction",
    ])
    for r in rows:
        w.writerow([
            r.pan or "PANNOTAVBL",
            (r.name or "").strip().upper()[:75],
            r.section,
            round(r.paid_amount, 2),
            round(r.tds_deducted, 2),
            round(r.tds_deposited, 2),
            r.deduction_date or "",
        ])
    return buf.getvalue()


def render_annexure_ii_csv(rows: Iterable[Form24QAnnexureIIRow]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
    w.writerow([
        "PAN", "Deductee Name", "Regime",
        "Gross Salary (Annual)", "HRA Exemption u/s 10(13A)",
        "Standard Deduction u/s 16", "Chapter VI-A Deductions",
        "Taxable Income", "Total Tax Liability", "TDS Deducted (Total)",
    ])
    for r in rows:
        w.writerow([
            r.pan or "PANNOTAVBL",
            (r.name or "").strip().upper()[:75],
            r.regime.upper(),
            round(r.gross_salary_annual, 2),
            round(r.hra_exemption, 2),
            round(r.standard_deduction, 2),
            round(r.chapter_via_deductions, 2),
            round(r.taxable_income, 2),
            round(r.total_tax, 2),
            round(r.tds_deducted_total, 2),
        ])
    return buf.getvalue()


def summarize_annexure_i(rows: List[Form24QAnnexureIRow]) -> dict:
    return {
        "employee_count": len(rows),
        "total_paid": round(sum(r.paid_amount for r in rows), 2),
        "total_tds_deducted": round(sum(r.tds_deducted for r in rows), 2),
        "total_tds_deposited": round(sum(r.tds_deposited for r in rows), 2),
        "missing_pan_count": sum(1 for r in rows if not r.pan),
    }


def quarter_end_date(fy: str, quarter: int) -> str:
    """ISO date string for the end of an FY quarter. fy = "24-25"."""
    fy_start_yr_short, fy_end_yr_short = fy.split("-")
    fy_start_yr = 2000 + int(fy_start_yr_short)
    fy_end_yr = 2000 + int(fy_end_yr_short)
    if quarter == 1:
        return f"{fy_start_yr}-06-30"
    if quarter == 2:
        return f"{fy_start_yr}-09-30"
    if quarter == 3:
        return f"{fy_start_yr}-12-31"
    return f"{fy_end_yr}-03-31"
