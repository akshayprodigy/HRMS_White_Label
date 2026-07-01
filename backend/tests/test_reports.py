"""Unit tests for the report engine + builders.

Pure — no DB, no xlsx/pdf renderers exercised (those need openpyxl/
reportlab and are runtime concerns). Covers:
- Indian currency formatting boundaries
- muster roll status classification + totals
- late/early minute math against shift + grace
- OT aggregate + per-row
- absenteeism % with WO/H excluded from denominator
- flag summary aggregation
- salary register totals
- bank advice missing-details skip
- statutory summary aggregation
- increment report totals
- headcount + attrition computation
- manager-scope filter drops rows outside the team
- catalog registration shape
"""
from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from typing import Any, List, Optional

import pytest

from app.services.reports import (
    AttendanceRow, ColumnType, LeaveBalanceRow, MonthlyHeadcountRow,
    AttritionInput, OTEntryRow, PayrollLineRow, ReportFilter, RevisionRow,
    StatutorySummaryInput,
    apply_manager_scope, build_absenteeism, build_attrition_report,
    build_bank_advice, build_flag_summary, build_headcount_trend,
    build_increment_report, build_late_early, build_leave_balance,
    build_leave_utilization, build_muster_roll, build_ot_report,
    build_salary_register, build_statutory_summary,
    compute_attrition_pct,
    fmt_cell, fmt_date, fmt_hours, fmt_inr, fmt_percent,
)
from app.services.report_catalog import (
    build_descriptors_no_fetchers, ReportCategory,
)


# ============================================================
# Indian formatting
# ============================================================


class TestIndianCurrency:
    def test_lakh(self):
        assert fmt_inr(100000) == "₹1,00,000.00"

    def test_crore(self):
        assert fmt_inr(10000000) == "₹1,00,00,000.00"

    def test_ten_lakh(self):
        assert fmt_inr(1234567) == "₹12,34,567.00"

    def test_small(self):
        assert fmt_inr(500) == "₹500.00"

    def test_decimals_kept(self):
        assert fmt_inr(1234567.89) == "₹12,34,567.89"

    def test_negative(self):
        assert fmt_inr(-1000) == "-₹1,000.00"

    def test_zero(self):
        assert fmt_inr(0) == "₹0.00"

    def test_none(self):
        assert fmt_inr(None) == ""

    def test_no_symbol(self):
        assert fmt_inr(100000, symbol=False) == "1,00,000.00"


class TestHoursFormat:
    def test_zero(self):
        assert fmt_hours(0) == "0h"

    def test_whole(self):
        assert fmt_hours(120) == "2h"

    def test_partial(self):
        assert fmt_hours(145) == "2h 25m"

    def test_negative(self):
        assert fmt_hours(-30) == "-0h 30m"

    def test_none(self):
        assert fmt_hours(None) == ""


class TestPercentFormat:
    def test_two_dp(self):
        assert fmt_percent(12.3456) == "12.35%"

    def test_zero(self):
        assert fmt_percent(0) == "0.00%"

    def test_none(self):
        assert fmt_percent(None) == ""


class TestFmtCellDispatch:
    def test_currency(self):
        assert fmt_cell(1000, ColumnType.CURRENCY) == "₹1,000.00"

    def test_hours(self):
        assert fmt_cell(90, ColumnType.HOURS) == "1h 30m"

    def test_percent(self):
        assert fmt_cell(25.5, ColumnType.PERCENT) == "25.50%"

    def test_text_passthrough(self):
        assert fmt_cell("abc", ColumnType.TEXT) == "abc"


# ============================================================
# manager-scope filter
# ============================================================


class TestManagerScope:
    def test_none_scope_passthrough(self):
        rows = [{"user_id": 1}, {"user_id": 2}]
        assert apply_manager_scope(rows, scope=None) == rows

    def test_scope_filters(self):
        rows = [{"user_id": 1}, {"user_id": 2}, {"user_id": 3}]
        out = apply_manager_scope(rows, scope=[1, 3])
        assert [r["user_id"] for r in out] == [1, 3]

    def test_empty_scope_empties_output(self):
        rows = [{"user_id": 1}]
        assert apply_manager_scope(rows, scope=[]) == []


# ============================================================
# Attendance: muster roll
# ============================================================


def _att(**kw) -> AttendanceRow:
    base = dict(
        user_id=1, employee_code="E001", full_name="Rita",
        department="Eng", work_date=date(2026, 7, 1),
        shift_name="Day",
    )
    base.update(kw)
    return AttendanceRow(**base)


class TestMusterRoll:
    def test_present_absent_leave_wo_holiday(self):
        recs = [
            _att(user_id=1, punch_in=datetime(2026, 7, 1, 9, 0)),
            _att(user_id=2, punch_in=None),
            _att(user_id=3, is_leave=True),
            _att(user_id=4, is_weekly_off=True),
            _att(user_id=5, is_holiday=True),
        ]
        r = build_muster_roll(records=recs, filters=ReportFilter())
        statuses = [row["status"] for row in r.rows]
        assert statuses == ["P", "A", "L", "WO", "H"]

    def test_totals_row_summary(self):
        recs = [_att(user_id=1, punch_in=datetime(2026, 7, 1, 9, 0))]
        r = build_muster_roll(records=recs, filters=ReportFilter())
        assert r.totals["employee_code"] == "TOTAL"
        assert "P=1" in r.totals["status"]

    def test_manager_scope_filters(self):
        recs = [
            _att(user_id=1, punch_in=datetime(2026, 7, 1, 9, 0)),
            _att(user_id=99, punch_in=datetime(2026, 7, 1, 9, 0)),
        ]
        f = ReportFilter(manager_scope_user_ids=[1])
        r = build_muster_roll(records=recs, filters=f)
        assert len(r.rows) == 1
        assert r.rows[0]["user_id"] == 1

    def test_columns_shape(self):
        r = build_muster_roll(records=[], filters=ReportFilter())
        keys = [c.key for c in r.columns]
        assert "status" in keys and "punch_in" in keys


# ============================================================
# late / early
# ============================================================


class TestLateEarly:
    def test_late_by_20_min_with_10_grace(self):
        # Shift 09:00; grace 10 min → threshold 09:10; punch 09:30 → 20 min late
        rec = _att(
            shift_start=time(9, 0), shift_end=time(18, 0),
            grace_in_minutes=10, grace_out_minutes=10,
            punch_in=datetime(2026, 7, 1, 9, 30, tzinfo=timezone.utc),
            punch_out=datetime(2026, 7, 1, 18, 0, tzinfo=timezone.utc),
        )
        r = build_late_early(records=[rec], filters=ReportFilter())
        assert len(r.rows) == 1
        assert r.rows[0]["late_minutes"] == 20
        assert r.rows[0]["early_minutes"] == 0

    def test_early_out(self):
        rec = _att(
            shift_start=time(9, 0), shift_end=time(18, 0),
            grace_in_minutes=10, grace_out_minutes=10,
            punch_in=datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc),
            punch_out=datetime(2026, 7, 1, 17, 30, tzinfo=timezone.utc),
        )
        r = build_late_early(records=[rec], filters=ReportFilter())
        assert r.rows[0]["early_minutes"] == 20   # threshold 17:50, out 17:30

    def test_on_time_excluded(self):
        rec = _att(
            shift_start=time(9, 0), shift_end=time(18, 0),
            grace_in_minutes=10, grace_out_minutes=10,
            punch_in=datetime(2026, 7, 1, 9, 5, tzinfo=timezone.utc),
            punch_out=datetime(2026, 7, 1, 18, 0, tzinfo=timezone.utc),
        )
        r = build_late_early(records=[rec], filters=ReportFilter())
        assert r.rows == []

    def test_totals_sum(self):
        rec1 = _att(
            user_id=1, shift_start=time(9, 0), shift_end=time(18, 0),
            grace_in_minutes=0, grace_out_minutes=0,
            punch_in=datetime(2026, 7, 1, 9, 15, tzinfo=timezone.utc),
        )
        rec2 = _att(
            user_id=2, shift_start=time(9, 0), shift_end=time(18, 0),
            grace_in_minutes=0, grace_out_minutes=0,
            punch_in=datetime(2026, 7, 1, 9, 30, tzinfo=timezone.utc),
        )
        r = build_late_early(records=[rec1, rec2], filters=ReportFilter())
        assert r.totals["late_minutes"] == 45


# ============================================================
# OT report
# ============================================================


def _ot(**kw) -> OTEntryRow:
    base = dict(
        user_id=1, employee_code="E001", full_name="Rita",
        department="Eng", work_date=date(2026, 7, 1),
        ot_minutes=60, ot_amount=1000.0,
        multiplier_used=1.5, day_type="weekday", status="approved",
    )
    base.update(kw)
    return OTEntryRow(**base)


class TestOTReport:
    def test_aggregate_default(self):
        rows = [_ot(user_id=1, ot_minutes=60), _ot(user_id=1, ot_minutes=45)]
        r = build_ot_report(entries=rows, filters=ReportFilter())
        assert len(r.rows) == 1
        assert r.rows[0]["total_minutes"] == 105
        assert r.rows[0]["entry_count"] == 2

    def test_per_row_extra(self):
        rows = [_ot(ot_minutes=60), _ot(ot_minutes=90)]
        f = ReportFilter(extras={"per_row": True})
        r = build_ot_report(entries=rows, filters=f)
        assert len(r.rows) == 2
        assert r.totals["ot_minutes"] == 150

    def test_approved_only_filter(self):
        rows = [
            _ot(status="approved", ot_minutes=60),
            _ot(status="pending", ot_minutes=120),
            _ot(status="auto_approved", ot_minutes=30),
        ]
        r = build_ot_report(entries=rows, filters=ReportFilter())
        assert r.rows[0]["total_minutes"] == 90


# ============================================================
# absenteeism
# ============================================================


class TestAbsenteeism:
    def test_percentages_excludes_wo_h(self):
        # 3 work-days, 1 present, 2 absent → 66.67%
        recs = [
            _att(user_id=1, punch_in=datetime(2026, 7, 1, 9, 0)),
            _att(user_id=1, work_date=date(2026, 7, 2), punch_in=None),
            _att(user_id=1, work_date=date(2026, 7, 3), punch_in=None),
            _att(user_id=1, work_date=date(2026, 7, 4), is_weekly_off=True),
            _att(user_id=1, work_date=date(2026, 7, 5), is_holiday=True),
        ]
        r = build_absenteeism(records=recs, filters=ReportFilter())
        row = r.rows[0]
        assert row["work_days"] == 3
        assert row["absent_days"] == 2
        assert row["absent_pct"] == 66.67

    def test_leave_not_absent(self):
        recs = [_att(user_id=1, is_leave=True)]
        r = build_absenteeism(records=recs, filters=ReportFilter())
        assert r.rows[0]["absent_days"] == 0


# ============================================================
# flag summary
# ============================================================


class TestFlagSummary:
    def test_counts_and_drop_zero(self):
        recs = [
            _att(user_id=1, attribution_flag="outside_window"),
            _att(user_id=1, geo_flag="mock_location"),
            _att(user_id=2),  # no flags → dropped
        ]
        r = build_flag_summary(records=recs, filters=ReportFilter())
        assert len(r.rows) == 1
        row = r.rows[0]
        assert row["outside_window"] == 1
        assert row["mock_location"] == 1


# ============================================================
# Leave
# ============================================================


class TestLeaveBalance:
    def test_totals(self):
        rows = [
            LeaveBalanceRow(1, "E001", "A", "Eng", "PL", 10, 4, 6),
            LeaveBalanceRow(2, "E002", "B", "Eng", "PL", 10, 8, 2),
        ]
        r = build_leave_balance(balances=rows, filters=ReportFilter())
        assert r.totals["balance"] == 8


class TestLeaveUtilization:
    def test_per_type_utilization(self):
        rows = [
            LeaveBalanceRow(1, "E001", "A", "Eng", "PL", 10, 4, 6),
            LeaveBalanceRow(2, "E002", "B", "Eng", "PL", 10, 8, 2),
            LeaveBalanceRow(3, "E003", "C", "HR", "CL", 5, 5, 0),
        ]
        r = build_leave_utilization(balances=rows, filters=ReportFilter())
        by_type = {r["leave_type"]: r for r in r.rows}
        assert by_type["PL"]["utilization_pct"] == 60.0
        assert by_type["CL"]["utilization_pct"] == 100.0
        assert by_type["CL"]["employees_with_zero_balance"] == 1


# ============================================================
# Payroll
# ============================================================


def _line(**kw) -> PayrollLineRow:
    base = dict(
        user_id=1, employee_code="E001", full_name="Rita",
        department="Eng",
        base_salary=25000, payable_days=30, lop_days=0,
        gross_pay=50000, net_pay=42000,
        allowances={
            "basic_salary_actual": 25000, "hra_actual": 12000,
            "conveyance_actual": 7500, "other_allowance_actual": 5000,
            "overtime": 500, "night_allowance": 0, "arrear": 0,
        },
        deductions={
            "employee_pf": 3000, "employee_esi": 0,
            "professional_tax": 200, "tds": 4800,
            "total_deductions": 8000,
        },
        bank_account="12345", bank_name="SBI", ifsc="SBIN0000123",
    )
    base.update(kw)
    return PayrollLineRow(**base)


class TestSalaryRegister:
    def test_component_split_and_totals(self):
        r = build_salary_register(
            lines=[_line(), _line(user_id=2, employee_code="E002")],
            filters=ReportFilter(),
        )
        assert len(r.rows) == 2
        assert r.totals["gross_pay"] == 100000
        assert r.totals["net_pay"] == 84000

    def test_currency_column_type(self):
        r = build_salary_register(lines=[_line()], filters=ReportFilter())
        gross_col = next(c for c in r.columns if c.key == "gross_pay")
        assert gross_col.type == ColumnType.CURRENCY


class TestBankAdvice:
    def test_generates_neft_layout(self):
        r = build_bank_advice(lines=[_line()], filters=ReportFilter())
        assert r.rows[0]["mode"] == "N"
        assert r.rows[0]["amount"] == 42000
        assert "SBIN" in r.rows[0]["ifsc"]

    def test_missing_bank_details_skipped_and_noted(self):
        good = _line(user_id=1)
        bad = _line(user_id=2, employee_code="E002",
                    bank_account=None, ifsc=None)
        r = build_bank_advice(lines=[good, bad], filters=ReportFilter())
        assert len(r.rows) == 1
        assert r.meta["missing_bank_details"] == 1


# ============================================================
# Statutory summary + increment report
# ============================================================


class TestStatutorySummary:
    def test_monthly_totals(self):
        months = [
            StatutorySummaryInput(
                period="04/2026", total_employees=100,
                total_employee_pf=180000, total_employer_pf=180000,
                total_eps=125000, total_employee_esic=15000,
                total_employer_esic=65000, total_pt=13000,
                total_tds=250000,
            ),
            StatutorySummaryInput(
                period="05/2026", total_employees=102,
                total_employee_pf=185000, total_employer_pf=185000,
                total_eps=128000, total_employee_esic=15500,
                total_employer_esic=66500, total_pt=13500,
                total_tds=260000,
            ),
        ]
        r = build_statutory_summary(months=months, filters=ReportFilter())
        assert r.totals["total_tds"] == 510000
        assert r.totals["total_employee_pf"] == 365000


def _rev(**kw) -> RevisionRow:
    base = dict(
        user_id=1, employee_code="E001", full_name="Rita",
        department="Eng", revision_type="increment",
        effective_from=date(2026, 4, 1),
        old_ctc=800000, new_ctc=960000,
        hike_amount=160000, hike_percent=20.0,
        status="applied",
    )
    base.update(kw)
    return RevisionRow(**base)


class TestIncrementReport:
    def test_totals_sum_hike_and_average_pct(self):
        rows = [_rev(user_id=1, hike_amount=160000, hike_percent=20),
                _rev(user_id=2, hike_amount=80000, hike_percent=10)]
        r = build_increment_report(revisions=rows, filters=ReportFilter())
        assert r.totals["hike_amount"] == 240000
        assert r.totals["hike_percent"] == 15.0  # average


# ============================================================
# Headcount / attrition
# ============================================================


class TestHeadcountTrend:
    def test_net_column(self):
        months = [
            MonthlyHeadcountRow("Jan 2026", 2026, 1,
                                opening=100, joiners=8, leavers=3, closing=105),
        ]
        r = build_headcount_trend(months=months, filters=ReportFilter())
        assert r.rows[0]["net"] == 5


class TestAttritionMath:
    def test_percentage_formula(self):
        # 2 leavers on avg headcount 100 → 2%
        assert compute_attrition_pct(leavers=2, avg_headcount=100) == 2.0

    def test_zero_headcount(self):
        assert compute_attrition_pct(leavers=1, avg_headcount=0) == 0.0

    def test_department_split(self):
        rows = [
            AttritionInput("Q1", 2026, 1, leavers=5, voluntary=4,
                           involuntary=1, avg_headcount=100, department="Eng"),
            AttritionInput("Q1", 2026, 1, leavers=1, voluntary=0,
                           involuntary=1, avg_headcount=50, department="HR"),
        ]
        r = build_attrition_report(months=rows, filters=ReportFilter())
        by_dept = {row["department"]: row for row in r.rows}
        assert by_dept["Eng"]["attrition_pct"] == 5.0
        assert by_dept["HR"]["attrition_pct"] == 2.0


# ============================================================
# Catalog registration shape
# ============================================================


class TestCatalog:
    def test_all_descriptors_registered(self):
        descs = build_descriptors_no_fetchers()
        keys = {d.key for d in descs}
        for expected in (
            "muster_roll", "late_early", "absenteeism", "ot_report",
            "flag_summary", "leave_balance", "leave_utilization",
            "salary_register", "bank_advice", "increment_report",
            "statutory_summary", "headcount_trend", "attrition_report",
        ):
            assert expected in keys

    def test_sensitive_reports_flagged(self):
        descs = {d.key: d for d in build_descriptors_no_fetchers()}
        assert descs["salary_register"].is_sensitive is True
        assert descs["bank_advice"].is_sensitive is True
        assert descs["muster_roll"].is_sensitive is False

    def test_categories_all_present(self):
        cats = {d.category for d in build_descriptors_no_fetchers()}
        assert cats == {
            ReportCategory.ATTENDANCE, ReportCategory.LEAVE,
            ReportCategory.PAYROLL, ReportCategory.STATUTORY,
            ReportCategory.HEADCOUNT,
            ReportCategory.PERFORMANCE, ReportCategory.EXPENSE,
        }
