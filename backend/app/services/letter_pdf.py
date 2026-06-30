"""
PDF generation service for employee letters.
All letters use UEIPL branding per company policy documents.
"""
from __future__ import annotations

from io import BytesIO
from datetime import date
from typing import Any, Dict, Optional

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


PAGE_W, PAGE_H = A4
MARGIN_L = 20 * mm
MARGIN_R = 20 * mm
MARGIN_TOP = 25 * mm
MARGIN_BOT = 25 * mm
CONTENT_W = PAGE_W - MARGIN_L - MARGIN_R

# Company branding
COMPANY_NAME = "United Engineering & Industries Pvt. Ltd."
COMPANY_SHORT = "UEIPL"
COMPANY_ADDR_1 = "Unit 402, 4th Floor, Block-C, Axis Mall"
COMPANY_ADDR_2 = "Rajarhat, New Town, Kolkata-700156"
COMPANY_CIN = "CIN: U14220WB2014PTC204104"
COMPANY_CERTS = "ISO 9001:2015 | QCI-NABET Accredited"
HR_SIGNATORY = "Arijit Dey"
HR_DESIGNATION = "Senior Manager - HR & Admin"


def _fmt_date(d: Any) -> str:
    if isinstance(d, date):
        return d.strftime("%d %B %Y")
    if isinstance(d, str) and d:
        return d
    return "_______________"


def _ordinal_suffix(day: int) -> str:
    if 11 <= day <= 13:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")


def _fmt_date_ordinal(d: Any) -> str:
    if isinstance(d, date):
        day = d.day
        sfx = _ordinal_suffix(day)
        return f"{day}{sfx} {d.strftime('%B %Y')}"
    return _fmt_date(d)


class LetterCanvas:
    """Helper that wraps reportlab canvas with UEIPL header/footer."""

    def __init__(self):
        self.buf = BytesIO()
        self.c = canvas.Canvas(self.buf, pagesize=A4)
        self.y = PAGE_H - MARGIN_TOP
        self.page_num = 0
        self._start_page()

    def _start_page(self):
        self.page_num += 1
        self.y = PAGE_H - MARGIN_TOP
        self._draw_header()
        self.y -= 5 * mm

    def _draw_header(self):
        c = self.c
        c.setFont("Helvetica-Bold", 14)
        c.drawString(MARGIN_L, self.y, COMPANY_NAME)
        self.y -= 5 * mm
        c.setFont("Helvetica", 8)
        c.drawString(MARGIN_L, self.y, COMPANY_CERTS)
        self.y -= 4 * mm
        c.drawString(MARGIN_L, self.y, COMPANY_ADDR_1)
        self.y -= 3.5 * mm
        c.drawString(MARGIN_L, self.y, COMPANY_ADDR_2)
        self.y -= 3.5 * mm
        c.drawString(MARGIN_L, self.y, COMPANY_CIN)
        self.y -= 5 * mm
        # Separator line
        c.setStrokeColorRGB(0.2, 0.2, 0.6)
        c.setLineWidth(1.2)
        c.line(MARGIN_L, self.y, PAGE_W - MARGIN_R, self.y)
        self.y -= 8 * mm

    def _draw_footer(self):
        c = self.c
        fy = 15 * mm
        c.setStrokeColorRGB(0.2, 0.2, 0.6)
        c.setLineWidth(0.5)
        c.line(MARGIN_L, fy + 3 * mm, PAGE_W - MARGIN_R, fy + 3 * mm)
        c.setFont("Helvetica", 7)
        c.drawString(
            MARGIN_L, fy,
            f"{COMPANY_NAME} | {COMPANY_ADDR_1}, {COMPANY_ADDR_2}"
        )

    def ensure_space(self, needed: float = 15 * mm):
        if self.y < MARGIN_BOT + needed:
            self._draw_footer()
            self.c.showPage()
            self._start_page()

    def title(self, text: str):
        self.ensure_space()
        self.c.setFont("Helvetica-Bold", 14)
        self.c.drawCentredString(PAGE_W / 2, self.y, text)
        self.y -= 10 * mm

    def subtitle(self, text: str):
        self.ensure_space()
        self.c.setFont("Helvetica-Bold", 11)
        self.c.drawCentredString(PAGE_W / 2, self.y, text)
        self.y -= 8 * mm

    def heading(self, text: str):
        self.ensure_space()
        self.c.setFont("Helvetica-Bold", 11)
        self.c.drawString(MARGIN_L, self.y, text)
        self.y -= 6 * mm

    def text(self, text: str, bold: bool = False,
             indent: float = 0, font_size: float = 10):
        font = "Helvetica-Bold" if bold else "Helvetica"
        self.c.setFont(font, font_size)
        x = MARGIN_L + indent
        max_chars = int(CONTENT_W / (font_size * 0.5))
        for line in (text or "").split("\n"):
            # Simple word-wrap
            while len(line) > max_chars:
                split = line[:max_chars].rfind(" ")
                if split == -1:
                    split = max_chars
                self.ensure_space()
                self.c.drawString(x, self.y, line[:split])
                self.y -= 4.5 * mm
                line = line[split:].lstrip()
            self.ensure_space()
            self.c.drawString(x, self.y, line)
            self.y -= 4.5 * mm

    def spacer(self, h: float = 5 * mm):
        self.y -= h

    def field_row(self, label: str, value: str):
        self.ensure_space()
        self.c.setFont("Helvetica-Bold", 10)
        self.c.drawString(MARGIN_L, self.y, label)
        self.c.setFont("Helvetica", 10)
        self.c.drawString(MARGIN_L + 50 * mm, self.y, value or "")
        self.y -= 5.5 * mm

    def signature_block(self, name: str = HR_SIGNATORY,
                        designation: str = HR_DESIGNATION):
        self.spacer(15 * mm)
        self.text("For " + COMPANY_NAME, bold=True)
        self.spacer(12 * mm)
        self.text(name, bold=True)
        self.text(designation)

    def finalize(self) -> bytes:
        self._draw_footer()
        self.c.showPage()
        self.c.save()
        return self.buf.getvalue()


# ─────────────────────────────────────────────
# Letter generators
# ─────────────────────────────────────────────

def generate_offer_letter(data: Dict[str, Any]) -> bytes:
    lc = LetterCanvas()
    ref = data.get("reference_number", "")
    dt = _fmt_date(data.get("date"))

    lc.field_row("Ref:", ref)
    lc.field_row("Date:", dt)
    lc.spacer()

    name = data.get("employee_name", "_______________")
    phone = data.get("phone", "")
    email = data.get("email", "")

    lc.text(f"To,")
    lc.text(f"{name}")
    if phone:
        lc.text(f"Phone: {phone}")
    if email:
        lc.text(f"Email: {email}")
    lc.spacer()

    position = data.get("designation", "_______________")
    joining_date = _fmt_date(data.get("joining_date"))

    lc.title("OFFER LETTER")
    lc.spacer()

    lc.text(f"Dear {name},")
    lc.spacer(3 * mm)
    lc.text(
        f"With reference to your application and the subsequent interview "
        f"you had with us, we are pleased to offer you the position of "
        f"\"{position}\" at {COMPANY_NAME}."
    )
    lc.spacer(3 * mm)
    lc.text(
        f"Your date of joining will be {joining_date}. You will be on "
        f"probation for a period of 6 (Six) months from the date of your "
        f"joining. During the probation period, either party may terminate "
        f"this offer by giving one month's written notice."
    )
    lc.spacer(3 * mm)
    lc.text(
        "Your detailed terms and conditions of employment will be "
        "mentioned in the Appointment Letter which will be issued to "
        "you on the date of your joining."
    )
    lc.spacer(3 * mm)
    lc.text(
        "We look forward to a long and mutually rewarding association "
        "with you."
    )
    lc.spacer(3 * mm)
    lc.text("Congratulations and welcome to the UEIPL family!")

    lc.signature_block()
    return lc.finalize()


def generate_appointment_letter(data: Dict[str, Any]) -> bytes:
    lc = LetterCanvas()
    ref = data.get("reference_number", "")
    dt = _fmt_date(data.get("date"))
    name = data.get("employee_name", "_______________")
    position = data.get("designation", "_______________")
    department = data.get("department", "_______________")
    joining_date = _fmt_date(data.get("joining_date"))
    ctc = data.get("ctc", "_______________")

    lc.field_row("Ref:", ref)
    lc.field_row("Date:", dt)
    lc.spacer()
    lc.text(f"To, {name}")
    lc.spacer()
    lc.title("APPOINTMENT LETTER")
    lc.spacer()

    lc.text(f"Dear {name},")
    lc.spacer(3 * mm)
    lc.text(
        f"With reference to your application and the subsequent interview, "
        f"we are pleased to appoint you as \"{position}\" in the "
        f"\"{department}\" department of {COMPANY_NAME} on the following "
        f"terms and conditions:"
    )
    lc.spacer(3 * mm)

    # 1. Probation
    lc.heading("1. Probation Period")
    lc.text(
        "You will be on probation for a period of 6 (Six) months from "
        f"the date of joining i.e., {joining_date}. During the probation "
        "period your services may be terminated by giving one month's "
        "written notice from either side. The company reserves the right "
        "to extend the probation period if deemed necessary.",
        indent=5 * mm
    )
    lc.spacer(3 * mm)

    # 2. CTC
    lc.heading("2. Compensation")
    lc.text(
        f"Your Cost to Company (CTC) will be Rs. {ctc}/- per annum. "
        "The detailed salary breakup is provided in the Annexure "
        "attached herewith. Your salary is confidential and should not "
        "be discussed with other employees.",
        indent=5 * mm
    )
    lc.spacer(3 * mm)

    # 3. Leave
    lc.heading("3. Leave Policy")
    lc.text(
        "You will be entitled to leaves as per the company's Time "
        "Office Policy. The leave categories include Casual Leave (CL), "
        "Privilege Leave (PL), Sick Leave (SL), and Compensatory Off. "
        "Detailed leave rules are covered in the company's HR policy "
        "handbook.",
        indent=5 * mm
    )
    lc.spacer(3 * mm)

    # 4. Working hours
    lc.heading("4. Working Hours")
    lc.text(
        "Office hours are from 10:15 AM to 6:30 PM, Monday to Saturday "
        "(except 2nd & 4th Saturdays and Sundays). A 30-minute lunch "
        "break is provided between 1:30 PM and 2:30 PM. Maximum 3 late "
        "arrivals per month are permitted; beyond that, leave will be "
        "deducted as per the Time Office Policy.",
        indent=5 * mm
    )
    lc.spacer(3 * mm)

    # 5. Place of posting
    lc.heading("5. Place of Posting")
    posting = data.get("posting_location", "Kolkata")
    lc.text(
        f"Your initial place of posting will be {posting}. However, "
        "the company reserves the right to transfer you to any other "
        "location, branch, or associate company as per business "
        "requirements.",
        indent=5 * mm
    )
    lc.spacer(3 * mm)

    # 6. Notice period
    lc.heading("6. Notice Period & Termination")
    lc.text(
        "After confirmation, you will be required to give 2 (Two) "
        "months' written notice or salary in lieu thereof for "
        "resignation. The company reserves the right to terminate your "
        "services with 2 months' notice or salary in lieu thereof.",
        indent=5 * mm
    )
    lc.spacer(3 * mm)

    # 7. Return of property
    lc.heading("7. Return of Company Property")
    lc.text(
        "Upon separation from the company, you shall return all "
        "company property including but not limited to ID cards, "
        "laptops, documents, access cards, and any other materials "
        "belonging to the company.",
        indent=5 * mm
    )
    lc.spacer(3 * mm)

    # 8. Confidentiality
    lc.heading("8. Confidentiality & Non-Disclosure")
    lc.text(
        "You shall maintain strict confidentiality regarding all "
        "company information, trade secrets, client data, and business "
        "processes. This obligation shall survive the termination of "
        "your employment.",
        indent=5 * mm
    )
    lc.spacer(3 * mm)

    # 9. Non-compete
    lc.heading("9. Restraint of Trade")
    lc.text(
        "During your employment and for a period of 12 months after "
        "leaving the company, you shall not engage in any business or "
        "employment that directly competes with the company's business "
        "interests without prior written consent.",
        indent=5 * mm
    )
    lc.spacer(3 * mm)

    lc.text(
        "Please sign and return a copy of this letter as acceptance "
        "of the above terms and conditions."
    )

    lc.signature_block()

    # Acceptance section
    lc.spacer(15 * mm)
    lc.text("ACCEPTANCE", bold=True)
    lc.spacer(3 * mm)
    lc.text(
        "I have read, understood and accept the above terms and "
        "conditions of my appointment."
    )
    lc.spacer(12 * mm)
    lc.text(f"Name: {name}")
    lc.text("Signature: ___________________")
    lc.text("Date: ___________________")

    return lc.finalize()


def generate_confirmation_letter(data: Dict[str, Any]) -> bytes:
    lc = LetterCanvas()
    ref = data.get("reference_number", "")
    dt = _fmt_date(data.get("date"))
    name = data.get("employee_name", "_______________")
    emp_id = data.get("employee_code", "")
    position = data.get("designation", "_______________")
    department = data.get("department", "")
    joining_date = _fmt_date(data.get("joining_date"))
    confirmation_date = _fmt_date(data.get("confirmation_date"))

    lc.field_row("Ref:", ref)
    lc.field_row("Date:", dt)
    lc.spacer()
    lc.text(f"To, {name}")
    if emp_id:
        lc.text(f"Employee Code: {emp_id}")
    lc.spacer()

    lc.title("CONFIRMATION LETTER")
    lc.spacer()

    lc.text(f"Dear {name},")
    lc.spacer(3 * mm)
    lc.text(
        f"This is with reference to your appointment as \"{position}\" "
        f"in the \"{department}\" department, dated {joining_date}."
    )
    lc.spacer(3 * mm)
    lc.text(
        "We are pleased to inform you that after successful completion "
        "of your probation period of 6 (Six) months, your services are "
        f"hereby confirmed with effect from {confirmation_date}."
    )
    lc.spacer(3 * mm)
    lc.text(
        "All other terms and conditions of your employment as mentioned "
        "in your Appointment Letter shall remain unchanged."
    )
    lc.spacer(3 * mm)
    lc.text(
        "We appreciate your contribution and look forward to your "
        "continued association with the company."
    )
    lc.spacer(3 * mm)
    lc.text("Congratulations!")

    lc.signature_block()
    return lc.finalize()


def generate_release_experience_order(data: Dict[str, Any]) -> bytes:
    lc = LetterCanvas()
    ref = data.get("reference_number", "")
    dt = _fmt_date(data.get("date"))
    name = data.get("employee_name", "_______________")
    emp_id = data.get("employee_code", "")
    position = data.get("designation", "_______________")
    department = data.get("department", "")
    joining_date = _fmt_date(data.get("joining_date"))
    last_working_date = _fmt_date(data.get("last_working_date"))
    cessation_cause = data.get(
        "cessation_cause", "Resignation"
    )
    performance = data.get("performance_rating", "Satisfactory")

    lc.field_row("Ref:", ref)
    lc.field_row("Date:", dt)
    lc.spacer()

    lc.title("RELEASE & EXPERIENCE ORDER")
    lc.spacer()

    lc.text("To Whomsoever It May Concern,")
    lc.spacer(3 * mm)
    lc.text(
        f"This is to certify that Mr./Ms. {name}"
        + (f" (Employee Code: {emp_id})" if emp_id else "")
        + f" was employed with {COMPANY_NAME} as "
        f"\"{position}\""
        + (f" in the \"{department}\" department" if department else "")
        + f" from {joining_date} to {last_working_date}."
    )
    lc.spacer(3 * mm)

    lc.field_row("Date of Joining:", joining_date)
    lc.field_row("Last Working Date:", last_working_date)
    lc.field_row("Last Designation:", position)
    lc.field_row("Cause of Cessation:", cessation_cause)
    lc.field_row("Performance:", performance)
    lc.spacer(3 * mm)

    lc.text(
        f"During the tenure with the company, {name}'s conduct and "
        f"performance has been {performance.lower()}."
    )
    lc.spacer(3 * mm)
    lc.text(
        "We wish all the best in future endeavors."
    )

    lc.signature_block()
    return lc.finalize()


def _fmt_money(v: Any) -> str:
    try:
        return f"Rs. {float(v):,.2f}"
    except (TypeError, ValueError):
        return str(v) if v not in (None, "") else "_______________"


def generate_promotion_letter(data: Dict[str, Any]) -> bytes:
    lc = LetterCanvas()
    ref = data.get("reference_number", "")
    dt = _fmt_date(data.get("date"))
    name = data.get("employee_name", "_______________")
    emp_id = data.get("employee_code", "")
    old_designation = data.get("old_designation", "_______________")
    new_designation = data.get("new_designation", "_______________")
    old_grade = data.get("old_grade", "")
    new_grade = data.get("new_grade", "")
    department = data.get("department", "")
    effective_date = _fmt_date(data.get("effective_date"))
    old_ctc = _fmt_money(data.get("old_ctc"))
    new_ctc = _fmt_money(data.get("new_ctc"))

    lc.field_row("Ref:", ref)
    lc.field_row("Date:", dt)
    lc.spacer()
    lc.text(f"To, {name}")
    if emp_id:
        lc.text(f"Employee Code: {emp_id}")
    if department:
        lc.text(f"Department: {department}")
    lc.spacer()

    lc.title("LETTER OF PROMOTION")
    lc.spacer()

    lc.text(f"Dear {name},")
    lc.spacer(3 * mm)
    lc.text(
        "In recognition of your performance, contribution and continued "
        f"commitment to {COMPANY_NAME}, we are pleased to promote you "
        f"from the position of \"{old_designation}\" to "
        f"\"{new_designation}\""
        + (f" (Grade {new_grade})" if new_grade else "")
        + f" with effect from {effective_date}."
    )
    lc.spacer(3 * mm)

    lc.heading("Position Details")
    lc.field_row("Previous Designation:", old_designation)
    if old_grade:
        lc.field_row("Previous Grade:", old_grade)
    lc.field_row("New Designation:", new_designation)
    if new_grade:
        lc.field_row("New Grade:", new_grade)
    lc.field_row("Effective From:", effective_date)
    lc.spacer(3 * mm)

    lc.heading("Revised Compensation")
    lc.field_row("Previous Annual CTC:", old_ctc)
    lc.field_row("Revised Annual CTC:", new_ctc)
    hike_amt = data.get("hike_amount")
    hike_pct = data.get("hike_percent")
    if hike_amt is not None:
        lc.field_row("Hike Amount:", _fmt_money(hike_amt))
    if hike_pct is not None:
        try:
            lc.field_row("Hike Percentage:", f"{float(hike_pct):.2f}%")
        except (TypeError, ValueError):
            pass
    lc.spacer(3 * mm)
    lc.text(
        "The detailed salary structure is available with HR and will "
        "reflect in your payslip from the next applicable payroll cycle. "
        "All other terms and conditions of your employment shall remain "
        "unchanged."
    )
    lc.spacer(3 * mm)
    lc.text(
        "We trust that you will accept the additional responsibility "
        "associated with this promotion and continue contributing with "
        "the same dedication."
    )
    lc.spacer(3 * mm)
    lc.text("Congratulations and best wishes!")

    lc.signature_block()
    return lc.finalize()


def generate_salary_revision_letter(data: Dict[str, Any]) -> bytes:
    lc = LetterCanvas()
    ref = data.get("reference_number", "")
    dt = _fmt_date(data.get("date"))
    name = data.get("employee_name", "_______________")
    emp_id = data.get("employee_code", "")
    designation = data.get("designation", "")
    department = data.get("department", "")
    effective_date = _fmt_date(data.get("effective_date"))
    old_ctc = _fmt_money(data.get("old_ctc"))
    new_ctc = _fmt_money(data.get("new_ctc"))
    revision_type = (data.get("revision_type") or "increment").title()

    lc.field_row("Ref:", ref)
    lc.field_row("Date:", dt)
    lc.spacer()
    lc.text(f"To, {name}")
    if emp_id:
        lc.text(f"Employee Code: {emp_id}")
    if designation:
        lc.text(f"Designation: {designation}")
    if department:
        lc.text(f"Department: {department}")
    lc.spacer()

    lc.title("SALARY REVISION LETTER")
    lc.subtitle(f"({revision_type})")
    lc.spacer()

    lc.text(f"Dear {name},")
    lc.spacer(3 * mm)
    lc.text(
        f"In recognition of your performance and contribution to "
        f"{COMPANY_NAME}, we are pleased to inform you that your "
        f"compensation has been revised with effect from {effective_date}."
    )
    lc.spacer(3 * mm)

    lc.heading("Revised Compensation")
    lc.field_row("Previous Annual CTC:", old_ctc)
    lc.field_row("Revised Annual CTC:", new_ctc)
    hike_amt = data.get("hike_amount")
    hike_pct = data.get("hike_percent")
    if hike_amt is not None:
        lc.field_row("Increment Amount:", _fmt_money(hike_amt))
    if hike_pct is not None:
        try:
            lc.field_row("Increment Percentage:", f"{float(hike_pct):.2f}%")
        except (TypeError, ValueError):
            pass
    lc.field_row("Effective From:", effective_date)
    lc.spacer(3 * mm)

    # Component breakdown when supplied
    new_basic = data.get("new_basic")
    new_hra = data.get("new_hra")
    new_conv = data.get("new_conveyance")
    new_other = data.get("new_other_allowance")
    if any(v is not None for v in (new_basic, new_hra, new_conv, new_other)):
        lc.heading("Revised Salary Components (Monthly)")
        if new_basic is not None:
            lc.field_row("Basic:", _fmt_money(new_basic))
        if new_hra is not None:
            lc.field_row("HRA:", _fmt_money(new_hra))
        if new_conv is not None:
            lc.field_row("Conveyance:", _fmt_money(new_conv))
        if new_other is not None:
            lc.field_row("Other Allowance:", _fmt_money(new_other))
        lc.spacer(3 * mm)

    lc.text(
        "The revised salary will reflect in your payslip from the next "
        "applicable payroll cycle. Any back-dated portion will be paid "
        "as arrears in the same payslip. All other terms of your "
        "employment shall remain unchanged."
    )
    lc.spacer(3 * mm)
    lc.text(
        "We value your contribution and look forward to your continued "
        "association with the company."
    )

    lc.signature_block()
    return lc.finalize()


def generate_relieving_letter(data: Dict[str, Any]) -> bytes:
    lc = LetterCanvas()
    ref = data.get("reference_number", "")
    dt = _fmt_date(data.get("date"))
    name = data.get("employee_name", "_______________")
    emp_id = data.get("employee_code", "")
    position = data.get("designation", "_______________")
    resignation_date = _fmt_date(data.get("resignation_date"))
    relieving_date = _fmt_date(data.get("relieving_date"))

    lc.field_row("Ref:", ref)
    lc.field_row("Date:", dt)
    lc.spacer()
    lc.text(f"To, {name}")
    if emp_id:
        lc.text(f"Employee Code: {emp_id}")
    lc.spacer()

    lc.title("RELIEVING LETTER")
    lc.spacer()

    lc.text(f"Dear {name},")
    lc.spacer(3 * mm)
    lc.text(
        f"This is with reference to your resignation letter dated "
        f"{resignation_date}, requesting to be relieved from your "
        f"duties as \"{position}\" at {COMPANY_NAME}."
    )
    lc.spacer(3 * mm)
    lc.text(
        f"We hereby confirm that you have been relieved from your "
        f"duties with effect from {relieving_date}, upon completion "
        f"of all formalities and no-due clearance."
    )
    lc.spacer(3 * mm)
    lc.text(
        "Please ensure that all company property has been returned "
        "and all pending dues have been settled."
    )
    lc.spacer(3 * mm)
    lc.text(
        "We thank you for your service and wish you all the best "
        "in your future endeavors."
    )

    lc.signature_block()
    return lc.finalize()


# Registry for easy lookup
LETTER_GENERATORS = {
    "offer_letter": generate_offer_letter,
    "appointment_letter": generate_appointment_letter,
    "confirmation_letter": generate_confirmation_letter,
    "release_experience_order": generate_release_experience_order,
    "relieving_letter": generate_relieving_letter,
    "promotion_letter": generate_promotion_letter,
    "salary_revision_letter": generate_salary_revision_letter,
}


def generate_letter(letter_type: str, data: Dict[str, Any]) -> bytes:
    gen = LETTER_GENERATORS.get(letter_type)
    if not gen:
        raise ValueError(f"Unknown letter type: {letter_type}")
    return gen(data)
