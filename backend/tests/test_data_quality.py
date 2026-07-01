"""Unit tests for data-quality scanner (Section K Item 3)."""
from dataclasses import replace

import pytest

from app.services.data_quality import (
    BLOCKING_SEVERITIES, EmployeeSnapshot, Finding, Severity,
    readiness_gate, scan_all, scan_employee, summarize,
)


def _complete() -> EmployeeSnapshot:
    """A snapshot with every field valid so the scanner should
    produce ZERO findings. Any test that changes this to invalid
    checks a specific classification path."""
    return EmployeeSnapshot(
        employee_pk=1,
        employee_code="EMP001",
        full_name="Alice Kumar",
        department="Engineering",
        designation="Engineer",
        pan_number="ABCDE1234F",
        pf_number="PF/12345",
        bank_account="12345678901",
        bank_ifsc="HDFC0001234",
        bank_account_holder_name="Alice Kumar",
        bank_verified=True,
        uan="123456789012",
        pf_member_id="MH-BOM-12345/6/7",
        esic_ip_number="1234567890",
        esic_applicable=True,
        pt_state="Maharashtra",
    )


# ---------------------------------------------------------------------------
# No-false-positive
# ---------------------------------------------------------------------------


def test_complete_employee_yields_zero_findings():
    findings = scan_employee(_complete())
    assert findings == []


def test_esic_not_applicable_does_not_block_when_ip_missing():
    snap = replace(
        _complete(), esic_applicable=False, esic_ip_number=None,
    )
    findings = scan_employee(snap)
    assert not any(f.severity == Severity.BLOCKS_ESIC for f in findings)


# ---------------------------------------------------------------------------
# BLOCKS_PF
# ---------------------------------------------------------------------------


def test_missing_pf_number_blocks_pf():
    snap = replace(_complete(), pf_number=None)
    findings = scan_employee(snap)
    assert any(
        f.severity == Severity.BLOCKS_PF and f.field == "pf_number"
        for f in findings
    )


def test_missing_uan_blocks_pf():
    snap = replace(_complete(), uan=None)
    findings = scan_employee(snap)
    assert any(
        f.severity == Severity.BLOCKS_PF and f.field == "uan"
        for f in findings
    )


def test_uan_wrong_shape_blocks_pf():
    snap = replace(_complete(), uan="12345")
    findings = scan_employee(snap)
    assert any(
        f.severity == Severity.BLOCKS_PF and f.field == "uan"
        for f in findings
    )


def test_missing_pf_member_id_blocks_pf():
    snap = replace(_complete(), pf_member_id=None)
    findings = scan_employee(snap)
    assert any(
        f.severity == Severity.BLOCKS_PF and f.field == "pf_member_id"
        for f in findings
    )


# ---------------------------------------------------------------------------
# BLOCKS_ESIC
# ---------------------------------------------------------------------------


def test_esic_applicable_but_no_ip_blocks_esic():
    snap = replace(_complete(), esic_ip_number=None)
    findings = scan_employee(snap)
    assert any(
        f.severity == Severity.BLOCKS_ESIC for f in findings
    )


# ---------------------------------------------------------------------------
# BLOCKS_FORM16
# ---------------------------------------------------------------------------


def test_missing_pan_blocks_form16():
    snap = replace(_complete(), pan_number=None)
    findings = scan_employee(snap)
    assert any(
        f.severity == Severity.BLOCKS_FORM16 for f in findings
    )


def test_invalid_pan_shape_blocks_form16():
    snap = replace(_complete(), pan_number="INVALID")
    findings = scan_employee(snap)
    assert any(
        f.severity == Severity.BLOCKS_FORM16 for f in findings
    )


# ---------------------------------------------------------------------------
# BLOCKS_NEFT
# ---------------------------------------------------------------------------


def test_missing_any_bank_field_blocks_neft():
    for kwargs in [
        {"bank_account": None},
        {"bank_ifsc": None},
        {"bank_account_holder_name": None},
    ]:
        snap = replace(_complete(), **kwargs)
        findings = scan_employee(snap)
        assert any(
            f.severity == Severity.BLOCKS_NEFT for f in findings
        )


def test_bad_ifsc_blocks_neft_specifically():
    snap = replace(_complete(), bank_ifsc="BADIFSC")
    findings = scan_employee(snap)
    assert any(
        f.severity == Severity.BLOCKS_NEFT
        and f.field == "bank_ifsc_code"
        for f in findings
    )


def test_bad_account_blocks_neft():
    snap = replace(_complete(), bank_account="12ABC34")
    findings = scan_employee(snap)
    assert any(
        f.severity == Severity.BLOCKS_NEFT
        and f.field == "bank_account"
        for f in findings
    )


def test_unverified_bank_is_only_warn_not_blocker():
    snap = replace(_complete(), bank_verified=False)
    findings = scan_employee(snap)
    verify_finding = next(
        f for f in findings if f.field == "bank_verified_at"
    )
    assert verify_finding.severity == Severity.WARN
    assert not verify_finding.is_blocker


# ---------------------------------------------------------------------------
# WARN — non-blocking
# ---------------------------------------------------------------------------


def test_missing_department_is_warn():
    snap = replace(_complete(), department=None)
    findings = scan_employee(snap)
    assert any(
        f.severity == Severity.WARN and f.field == "department"
        for f in findings
    )


def test_missing_designation_is_warn():
    snap = replace(_complete(), designation=None)
    findings = scan_employee(snap)
    assert any(
        f.severity == Severity.WARN and f.field == "designation"
        for f in findings
    )


def test_missing_pt_state_is_warn_not_blocker():
    snap = replace(_complete(), pt_state=None)
    findings = scan_employee(snap)
    pt = next(f for f in findings if f.field == "pt_state")
    assert pt.severity == Severity.WARN
    assert not pt.is_blocker


# ---------------------------------------------------------------------------
# Finding shape + drill link
# ---------------------------------------------------------------------------


def test_finding_carries_drill_link():
    snap = replace(_complete(), pan_number=None)
    findings = scan_employee(snap)
    pan = next(f for f in findings if f.field == "pan_number")
    assert pan.drill["route"] == "hr-directory"
    assert pan.drill["params"]["employee_pk"] == 1


def test_finding_to_dict_includes_is_blocker():
    f = Finding(
        employee_pk=1, employee_code="X", full_name="X",
        field="pan_number", severity=Severity.BLOCKS_FORM16,
        reason="test",
    )
    assert f.to_dict()["is_blocker"] is True


# ---------------------------------------------------------------------------
# Fleet summary + readiness gate
# ---------------------------------------------------------------------------


def test_scan_all_aggregates_across_employees():
    a = replace(_complete(), employee_pk=1, pan_number=None)
    b = replace(_complete(), employee_pk=2, uan=None)
    findings = scan_all([a, b])
    emps_with_findings = {f.employee_pk for f in findings}
    assert emps_with_findings == {1, 2}


def test_summarize_counts_by_severity_and_employees_blocked():
    a = replace(_complete(), employee_pk=1, pan_number=None)  # 1 blocker
    b = replace(_complete(), employee_pk=2, department=None)  # 1 warn
    findings = scan_all([a, b])
    s = summarize(findings)
    assert s["blocker_count"] >= 1
    assert s["employees_blocked"] == 1  # only 'a'
    assert s["by_severity"].get(Severity.BLOCKS_FORM16, 0) >= 1


def test_readiness_gate_ready_when_no_blockers():
    findings = scan_all([_complete()])
    gate = readiness_gate(findings)
    assert gate["ready"] is True
    assert gate["blocker_count"] == 0


def test_readiness_gate_not_ready_when_blocker_present():
    snap = replace(_complete(), pan_number=None)
    gate = readiness_gate(scan_all([snap]))
    assert gate["ready"] is False
    assert gate["blocker_count"] >= 1
    assert gate["blockers"]


def test_blocking_severities_set_is_stable():
    assert Severity.BLOCKS_PF in BLOCKING_SEVERITIES
    assert Severity.BLOCKS_ESIC in BLOCKING_SEVERITIES
    assert Severity.BLOCKS_FORM16 in BLOCKING_SEVERITIES
    assert Severity.BLOCKS_NEFT in BLOCKING_SEVERITIES
    assert Severity.WARN not in BLOCKING_SEVERITIES
