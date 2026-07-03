"""On-demand payslip PDF renderer.

Publish creates Payslip rows; this module turns one into an actual
PDF at download time (no files stored on disk — the PDF is a pure
function of the PayrollLine snapshot, so regeneration is always
consistent with what was published).

Company name resolves from the active EmployerIdentifier (the legal
employer entity) and falls back to the product name for unconfigured
installs.
"""
from __future__ import annotations

import io
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

MONTHS = [
    "", "January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December",
]

ACCENT = colors.HexColor("#0F172A")
MUTED = colors.HexColor("#64748B")
LINE = colors.HexColor("#E2E8F0")
GREEN = colors.HexColor("#15803D")


def _inr(x) -> str:
    try:
        return f"Rs {float(x or 0):,.2f}"
    except (TypeError, ValueError):
        return "Rs 0.00"


def _mask_account(acct: Optional[str]) -> str:
    if not acct:
        return "-"
    tail = acct[-4:]
    return f"XXXX{tail}"


def build_payslip_pdf(
    *,
    company_name: str,
    month: int,
    year: int,
    employee_name: str,
    employee_code: str,
    department: Optional[str],
    designation: Optional[str],
    pan_number: Optional[str],
    bank_name: Optional[str],
    bank_account: Optional[str],
    payable_days: float,
    lop_days: float,
    allowances: dict,
    deductions: dict,
    gross_pay: float,
    net_pay: float,
    advance_deduction: float,
) -> bytes:
    """Render one payslip to PDF bytes."""
    al = allowances or {}
    ded = deductions or {}
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=16 * mm, bottomMargin=16 * mm,
        title=f"Payslip {MONTHS[month]} {year} - {employee_code}",
    )
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle(
        "h1", parent=styles["Title"], fontSize=16, textColor=ACCENT,
        alignment=0, spaceAfter=1,
    )
    sub = ParagraphStyle(
        "sub", parent=styles["Normal"], fontSize=9, textColor=MUTED,
    )
    foot = ParagraphStyle(
        "foot", parent=styles["Normal"], fontSize=7.5, textColor=MUTED,
    )

    story = [
        Paragraph(company_name, h1),
        Paragraph(f"Payslip — {MONTHS[month]} {year}", sub),
        Spacer(1, 6 * mm),
    ]

    # ----- employee info -----
    info_rows = [
        ["Employee", employee_name, "Employee Code", employee_code],
        ["Department", department or "-", "Designation", designation or "-"],
        ["PAN", pan_number or "-", "Bank",
         f"{bank_name or '-'} ({_mask_account(bank_account)})"],
        ["Paid Days", f"{payable_days:g}", "LOP Days", f"{lop_days:g}"],
    ]
    info = Table(info_rows, colWidths=[28 * mm, 62 * mm, 32 * mm, 52 * mm])
    info.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("TEXTCOLOR", (0, 0), (0, -1), MUTED),
        ("TEXTCOLOR", (2, 0), (2, -1), MUTED),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
        ("FONTNAME", (3, 0), (3, -1), "Helvetica-Bold"),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, LINE),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
    ]))
    story += [info, Spacer(1, 7 * mm)]

    # ----- earnings / deductions side by side -----
    earnings = [
        ("Basic Salary", al.get("basic_salary_actual")),
        ("HRA", al.get("hra_actual")),
        ("Conveyance", al.get("conveyance_actual")),
        ("Other Allowance", al.get("other_allowance_actual")),
        ("Arrears", al.get("arrear")),
        ("Incentive", al.get("incentive")),
        ("Overtime", al.get("overtime")),
        ("Night Allowance", al.get("night_allowance")),
    ]
    dedns = [
        ("Provident Fund", ded.get("employee_pf")),
        ("Voluntary PF", ded.get("voluntary_pf")),
        ("ESI", ded.get("employee_esi")),
        ("Professional Tax", ded.get("professional_tax")),
        ("Income Tax (TDS)", ded.get("tds")),
        ("Advance Recovery", advance_deduction),
        ("Guest House", ded.get("guest_house")),
    ]
    earnings = [(k, v) for k, v in earnings if float(v or 0) != 0]
    dedns = [(k, v) for k, v in dedns if float(v or 0) != 0]
    total_ded = ded.get("total_deductions", 0.0)

    n = max(len(earnings), len(dedns), 1)
    earnings += [("", None)] * (n - len(earnings))
    dedns += [("", None)] * (n - len(dedns))

    rows = [["EARNINGS", "", "DEDUCTIONS", ""]]
    for (ek, ev), (dk, dv) in zip(earnings, dedns):
        rows.append([
            ek, _inr(ev) if ev is not None else "",
            dk, _inr(dv) if dv is not None else "",
        ])
    rows.append([
        "Gross Earnings", _inr(gross_pay),
        "Total Deductions", _inr(float(total_ded) + float(advance_deduction or 0)),
    ])

    t = Table(rows, colWidths=[48 * mm, 39 * mm, 48 * mm, 39 * mm])
    t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("ALIGN", (3, 0), (3, -1), "RIGHT"),
        ("LINEBELOW", (0, 1), (-1, -2), 0.4, LINE),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("LINEABOVE", (0, -1), (-1, -1), 0.8, ACCENT),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
    ]))
    story += [t, Spacer(1, 7 * mm)]

    # ----- net pay -----
    net = Table(
        [["NET PAY", _inr(net_pay)]],
        colWidths=[135 * mm, 39 * mm],
    )
    net.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("TEXTCOLOR", (1, 0), (1, 0), GREEN),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F0FDF4")),
        ("BOX", (0, 0), (-1, -1), 0.8, GREEN),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
    ]))
    story += [net, Spacer(1, 8 * mm)]

    story.append(Paragraph(
        "System-generated payslip — no signature required. "
        "Figures are as published in the payroll run; contact HR for "
        "any discrepancy.", foot,
    ))

    doc.build(story)
    return buf.getvalue()
