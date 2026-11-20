"""Custom letter-template rendering (W10a).

Shared by the preview + generate endpoints so the token-fill logic lives
in one place instead of the router. A template body carries {{token}}
placeholders; `build_employee_context` produces the fill dict from the
Employee record (+ its User) and company constants, and `render` does the
substitution, reporting any tokens the context could not satisfy.
"""
from __future__ import annotations

import re
from datetime import date as date_cls
from typing import Any, Dict, List, Optional, Tuple

from app.services.letter_pdf import (
    COMPANY_NAME, HR_SIGNATORY, HR_DESIGNATION, _fmt_date,
)

# Catalog surfaced to the UI as a clickable placeholder palette. `source`
# is informational (where the value comes from) — purely for the editor.
PLACEHOLDER_CATALOG: List[Dict[str, str]] = [
    {"token": "employee_name", "label": "Employee Name", "source": "employee"},
    {"token": "employee_code", "label": "Employee Code", "source": "employee"},
    {"token": "designation", "label": "Designation", "source": "employee"},
    {"token": "department", "label": "Department", "source": "employee"},
    {"token": "date_of_joining", "label": "Date of Joining", "source": "employee"},
    {"token": "email", "label": "Email", "source": "employee"},
    {"token": "phone", "label": "Phone", "source": "employee"},
    {"token": "location", "label": "Location", "source": "employee"},
    {"token": "grade", "label": "Grade", "source": "employee"},
    {"token": "salary", "label": "Annual Salary", "source": "employee"},
    {"token": "ctc", "label": "CTC", "source": "employee"},
    {"token": "manager_name", "label": "Manager Name", "source": "override"},
    {"token": "company_name", "label": "Company Name", "source": "company"},
    {"token": "hr_signatory", "label": "HR Signatory", "source": "company"},
    {"token": "hr_designation", "label": "HR Designation", "source": "company"},
    {"token": "reference_number", "label": "Reference Number", "source": "system"},
    {"token": "today", "label": "Today's Date", "source": "system"},
    {"token": "date", "label": "Letter Date", "source": "system"},
]

_TOKEN_RE = re.compile(r"{{\s*(\w+)\s*}}")


def _money(v: Any) -> str:
    try:
        return f"{float(v):,.2f}"
    except (TypeError, ValueError):
        return "" if v in (None, "") else str(v)


def build_employee_context(
    emp: Any,
    user: Any,
    *,
    reference_number: Optional[str] = None,
    letter_date: Optional[date_cls] = None,
    today: date_cls,
    overrides: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """Assemble the {{token}} -> value map from the employee record,
    its user, and company constants. `overrides` (HR-supplied extra
    context) is applied last so it wins over the derived values."""
    ld = letter_date or today
    salary = getattr(emp, "salary", None)
    ctx: Dict[str, str] = {
        "employee_name": (getattr(user, "full_name", None) or "") if user else "",
        "employee_code": getattr(emp, "employee_id", "") or "",
        "designation": getattr(emp, "designation", "") or "",
        "department": getattr(emp, "department", "") or "",
        "date_of_joining": _fmt_date(getattr(emp, "date_of_joining", None)),
        "email": (getattr(user, "email", None) or "") if user else "",
        "phone": (getattr(user, "phone", None) or "") if user else "",
        "location": getattr(emp, "location", "") or "",
        "grade": getattr(emp, "grade", "") or "",
        "salary": _money(salary),
        "ctc": _money(salary),
        "manager_name": "",
        "company_name": COMPANY_NAME,
        "hr_signatory": HR_SIGNATORY,
        "hr_designation": HR_DESIGNATION,
        "reference_number": reference_number or "",
        "today": _fmt_date(today),
        "date": _fmt_date(ld),
    }
    if overrides:
        for k, v in overrides.items():
            if v is not None:
                ctx[k] = str(v)
    return ctx


def render(body: str, context: Dict[str, str]) -> Tuple[str, List[str]]:
    """Substitute {{token}} occurrences. Returns (rendered_text, missing)
    where `missing` is the sorted unique list of tokens the context could
    not satisfy (left in place as {{token}} so the gap is visible)."""
    missing: set[str] = set()

    def _sub(m: "re.Match[str]") -> str:
        key = m.group(1)
        if key in context and context[key] != "":
            return context[key]
        if key in context:
            # present but empty — still a fill, render as blank
            return ""
        missing.add(key)
        return m.group(0)

    rendered = _TOKEN_RE.sub(_sub, body or "")
    return rendered, sorted(missing)
