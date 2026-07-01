"""Data-quality scan — payroll/statutory readiness.

Pure classifier + finding shape. Endpoints assemble the (employee,
statutory_detail, bank_details) tuples and hand them to `scan()`.

Severity glossary
-----------------
- BLOCKS_PF     : PF ECR / PF number missing / UAN missing → PF filing fails.
- BLOCKS_ESIC   : ESIC IP number missing while ESIC applicable → contribution
                  file fails.
- BLOCKS_FORM16 : PAN missing / invalid → Form 16 Part B cannot generate.
- BLOCKS_NEFT   : Bank IFSC or account or holder name missing/invalid →
                  bank advice NEFT row cannot be cut.
- WARN          : missing department / designation / other non-blocking
                  gaps.

Every finding carries a `drill` pointer so the HR dashboard widget and
the report both link into the fix screen (Employee edit, statutory
detail edit, etc.).

Nothing here writes — HR always decides whether to unblock. The
"readiness check" endpoint calls scan() and returns any findings with
`is_blocker=True` so HR can eyeball them before running payroll.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

from app.services.bank_details import (
    validate_account_number, validate_ifsc,
)


PAN_REGEX = None  # set below without importing re at module scope again
UAN_REGEX = None


def _lazy_compile():
    global PAN_REGEX, UAN_REGEX
    if PAN_REGEX is None:
        import re
        PAN_REGEX = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
        UAN_REGEX = re.compile(r"^\d{12}$")


class Severity:
    BLOCKS_PF = "BLOCKS_PF"
    BLOCKS_ESIC = "BLOCKS_ESIC"
    BLOCKS_FORM16 = "BLOCKS_FORM16"
    BLOCKS_NEFT = "BLOCKS_NEFT"
    WARN = "WARN"


BLOCKING_SEVERITIES = {
    Severity.BLOCKS_PF, Severity.BLOCKS_ESIC,
    Severity.BLOCKS_FORM16, Severity.BLOCKS_NEFT,
}


@dataclass
class EmployeeSnapshot:
    """The subset of employee data the scanner needs. Callers assemble
    from ORM rows. Keeping this DB-free lets tests cover every code
    path without spinning up SQLAlchemy."""
    employee_pk: int
    employee_code: str
    full_name: str
    department: Optional[str]
    designation: Optional[str]
    pan_number: Optional[str]
    pf_number: Optional[str]
    bank_account: Optional[str]
    bank_ifsc: Optional[str]
    bank_account_holder_name: Optional[str]
    bank_verified: bool
    # Statutory detail row (may be missing entirely — represented as None).
    uan: Optional[str] = None
    pf_member_id: Optional[str] = None
    esic_ip_number: Optional[str] = None
    esic_applicable: bool = False
    pt_state: Optional[str] = None


@dataclass
class Finding:
    employee_pk: int
    employee_code: str
    full_name: str
    field: str
    severity: str
    reason: str
    drill: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_blocker(self) -> bool:
        return self.severity in BLOCKING_SEVERITIES

    def to_dict(self) -> dict:
        return {
            "employee_pk": self.employee_pk,
            "employee_code": self.employee_code,
            "full_name": self.full_name,
            "field": self.field,
            "severity": self.severity,
            "reason": self.reason,
            "drill": self.drill,
            "is_blocker": self.is_blocker,
        }


# ------------------------------------------------------------------
# Per-employee scan
# ------------------------------------------------------------------


def _drill_employee(pk: int, tab: str = "job") -> Dict[str, Any]:
    return {"route": "hr-directory", "params": {"employee_pk": pk, "tab": tab}}


def scan_employee(snap: EmployeeSnapshot) -> List[Finding]:
    """Return every data-quality finding for a single employee.
    Complete + valid rows produce zero findings (no-false-positive)."""
    _lazy_compile()
    out: List[Finding] = []

    def _emit(field_: str, severity: str, reason: str, tab: str = "job"):
        out.append(Finding(
            employee_pk=snap.employee_pk,
            employee_code=snap.employee_code,
            full_name=snap.full_name,
            field=field_, severity=severity, reason=reason,
            drill=_drill_employee(snap.employee_pk, tab),
        ))

    # PF chain — pf_number lives on Employee, uan + pf_member_id on
    # StatutoryDetail. All three matter for a valid ECR.
    if not (snap.pf_number and snap.pf_number.strip()):
        _emit("pf_number", Severity.BLOCKS_PF,
              "PF number missing — required for PF ECR", tab="statutory")
    if not (snap.uan and snap.uan.strip()):
        _emit("uan", Severity.BLOCKS_PF,
              "UAN missing — required by EPFO for member linkage",
              tab="statutory")
    elif not UAN_REGEX.match(snap.uan.strip()):
        _emit("uan", Severity.BLOCKS_PF,
              f"UAN {snap.uan!r} is not 12 numeric digits",
              tab="statutory")
    if not (snap.pf_member_id and snap.pf_member_id.strip()):
        _emit("pf_member_id", Severity.BLOCKS_PF,
              "PF member id missing — required for PF ECR",
              tab="statutory")

    # ESIC — only blocks if the employee is under ESIC.
    if snap.esic_applicable and not (
        snap.esic_ip_number and snap.esic_ip_number.strip()
    ):
        _emit("esic_ip_number", Severity.BLOCKS_ESIC,
              "ESIC IP number missing while ESIC is applicable",
              tab="statutory")

    # PAN — mandatory for TDS / Form 16.
    if not (snap.pan_number and snap.pan_number.strip()):
        _emit("pan_number", Severity.BLOCKS_FORM16,
              "PAN missing — cannot generate Form 16",
              tab="tax")
    elif not PAN_REGEX.match(snap.pan_number.strip().upper()):
        _emit("pan_number", Severity.BLOCKS_FORM16,
              f"PAN {snap.pan_number!r} is not in the standard AAAAA9999A shape",
              tab="tax")

    # NEFT — every field matters.
    if not (
        snap.bank_account and snap.bank_ifsc
        and snap.bank_account_holder_name
    ):
        _emit("bank_details", Severity.BLOCKS_NEFT,
              "Bank details incomplete (account / IFSC / holder name)",
              tab="bank")
    else:
        if not validate_ifsc(snap.bank_ifsc).ok:
            _emit("bank_ifsc_code", Severity.BLOCKS_NEFT,
                  f"IFSC {snap.bank_ifsc!r} fails RBI shape check",
                  tab="bank")
        if not validate_account_number(snap.bank_account).ok:
            _emit("bank_account", Severity.BLOCKS_NEFT,
                  "Account number fails length/digit sanity check",
                  tab="bank")
        if not snap.bank_verified:
            _emit("bank_verified_at", Severity.WARN,
                  "Bank details present but not yet HR-verified",
                  tab="bank")

    # PT state — missing PT state means PT deduction skipped silently.
    if not (snap.pt_state and snap.pt_state.strip()):
        _emit("pt_state", Severity.WARN,
              "PT state missing — professional tax will not deduct",
              tab="statutory")

    # Data hygiene.
    if not (snap.department and snap.department.strip()):
        _emit("department", Severity.WARN,
              "Department missing", tab="job")
    if not (snap.designation and snap.designation.strip()):
        _emit("designation", Severity.WARN,
              "Designation missing", tab="job")

    return out


# ------------------------------------------------------------------
# Fleet-wide scan + summary
# ------------------------------------------------------------------


def scan_all(snapshots: Iterable[EmployeeSnapshot]) -> List[Finding]:
    out: List[Finding] = []
    for s in snapshots:
        out.extend(scan_employee(s))
    return out


def summarize(findings: Iterable[Finding]) -> Dict[str, Any]:
    """Return counts by severity + blockers total + per-field counts.
    Used as the HR dashboard exceptions widget payload."""
    by_severity: Dict[str, int] = {}
    by_field: Dict[str, int] = {}
    blocker_count = 0
    employees_blocked = set()
    for f in findings:
        by_severity[f.severity] = by_severity.get(f.severity, 0) + 1
        by_field[f.field] = by_field.get(f.field, 0) + 1
        if f.is_blocker:
            blocker_count += 1
            employees_blocked.add(f.employee_pk)
    return {
        "count": len(list(findings)) if not isinstance(findings, list) else len(findings),
        "blocker_count": blocker_count,
        "employees_blocked": len(employees_blocked),
        "by_severity": by_severity,
        "by_field": by_field,
    }


def readiness_gate(findings: Iterable[Finding]) -> Dict[str, Any]:
    """Return a compact readiness verdict. Advisory — NEVER auto-blocks
    payroll. HR sees this before hitting Run Payroll and decides.
    """
    blockers = [f for f in findings if f.is_blocker]
    return {
        "ready": not blockers,
        "blocker_count": len(blockers),
        "blockers": [f.to_dict() for f in blockers[:20]],
    }
