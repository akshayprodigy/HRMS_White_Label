from typing import Any
from datetime import datetime, timedelta, timezone
import random
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func

from app.api import deps
from app.models.user import User
from app.models.attendance import Attendance
from app.models.timesheet import TimeEntry
from app.models.project import Project, CostBaseline
from app.models.leave import LeaveBalanceLedger, LeaveType
from app.schemas.report import (
    ReportsSummary, AttendanceCompliance, ProjectUtilization,
    LeaveBalanceSummary, CostVariance
)

router = APIRouter()


@router.get("/summary", response_model=ReportsSummary)
async def get_reports_summary(
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user)
) -> Any:
    """
    Get summary of all reports for dashboard.
    Authorized for Admin, CEO, and HR roles.
    """
    # Authorization logic
    allowed_roles = {"admin", "ceo", "hr"}
    user_roles = {role.name.lower() for role in current_user.roles}
    
    if not current_user.is_superuser and not (user_roles & allowed_roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions to view operational reports"
        )

    # 1. Attendance Compliance (Last 7 days)
    seven_days_ago = datetime.now(timezone.utc).date() - timedelta(days=7)

    total_active_users_result = await db.execute(
        select(func.count(User.id)).where(User.is_active.is_(True))
    )
    # Avoid div by zero
    total_active_users = total_active_users_result.scalar() or 1

    attendance_query = select(
        func.date(Attendance.captured_at).label("date"),
        func.count(func.distinct(Attendance.user_id)).label("present_count")
    ).where(
        func.date(Attendance.captured_at) >= seven_days_ago
    ).group_by(
        func.date(Attendance.captured_at)
    ).order_by(
        func.date(Attendance.captured_at).desc()
    )

    attendance_results = await db.execute(attendance_query)
    attendance_compliance = []
    for res in attendance_results:
        percentage = round((res.present_count / total_active_users) * 100, 2)
        attendance_compliance.append(AttendanceCompliance(
            date=res.date,
            total_employees=total_active_users,
            present_count=res.present_count,
            compliance_percentage=percentage
        ))

    # 2. Project Utilization
    util_query = select(
        Project.id,
        Project.name,
        func.sum(TimeEntry.duration_seconds).label("total_seconds")
    ).join(
        TimeEntry, Project.id == TimeEntry.project_id
    ).group_by(
        Project.id, Project.name
    )

    util_results = await db.execute(util_query)
    project_utilization = []
    for res in util_results:
        hours = res.total_seconds / 3600
        project_utilization.append(ProjectUtilization(
            project_id=res.id,
            project_name=res.name,
            total_hours=round(hours, 2),
            # Assuming all hours are billable for now
            billable_hours=round(hours, 2),
            utilization_percentage=100.0  # Placeholder
        ))

    # 3. Leave Balances Summary
    leave_query = select(
        User.id,
        User.full_name,
        LeaveType.name.label("leave_type"),
        LeaveBalanceLedger.balance,
        LeaveBalanceLedger.used
    ).join(
        LeaveBalanceLedger, User.id == LeaveBalanceLedger.user_id
    ).join(
        LeaveType, LeaveBalanceLedger.leave_type_id == LeaveType.id
    )

    leave_results = await db.execute(leave_query)
    leave_balances = []
    for res in leave_results:
        leave_balances.append(LeaveBalanceSummary(
            employee_id=res.id,
            employee_name=res.full_name,
            leave_type=res.leave_type,
            total_allotted=res.balance + res.used,
            taken=res.used,
            remaining=res.balance
        ))

    # 4. Cost Variance Summary
    cost_baseline_query = select(
        Project.name,
        CostBaseline.amount.label("budget")
    ).join(
        CostBaseline, Project.id == CostBaseline.project_id
    ).where(
        CostBaseline.is_active.is_(True)
    )

    cost_results = await db.execute(cost_baseline_query)
    cost_variance = []
    for res in cost_results:
        # Mock actual cost as 85-115% of budget for demo
        actual = res.budget * random.uniform(0.85, 1.15)
        variance = res.budget - actual
        cost_variance.append(CostVariance(
            category=res.name,
            budgeted_cost=res.budget,
            actual_cost=round(actual, 2),
            variance=round(variance, 2),
            variance_percentage=round((variance / res.budget) * 100, 2)
        ))

    return ReportsSummary(
        attendance_compliance=attendance_compliance,
        project_utilization=project_utilization,
        leave_balances=leave_balances,
        cost_variance=cost_variance
    )


# ================================================================
# ================= REPORTS ENGINE (module 7) ====================
# ================================================================
# Extends the existing HR-dashboard endpoints above with the full
# report catalog, universal export, and saved-report CRUD. Reads
# finalized payroll + existing OT/Revision/Statutory outputs; never
# recomputes.

import io as _io
from calendar import monthrange as _monthrange
from datetime import date as _date, timedelta as _td
from typing import Any as _Any, List as _List, Optional as _Opt

from fastapi import Query as _Query, Request as _Request
from fastapi.responses import StreamingResponse as _Stream
from sqlalchemy import and_ as _and, func as _func, or_ as _or
from sqlalchemy.orm import selectinload as _selectinload

from app.api.v1.endpoints.hr import log_audit as _log_audit
from app.models.attendance import Attendance as _Attendance
from app.models.employee import Employee as _Employee
from app.models.hr import HolidayCalendar as _HolidayCalendar
from app.models.leave import (
    LeaveBalanceLedger as _LeaveBalanceLedger,
    LeaveRequest as _LeaveRequest,
    LeaveStatus as _LeaveStatus,
    LeaveType as _LeaveType,
)
from app.models.overtime import OvertimeEntry as _OvertimeEntry
from app.models.payroll import (
    PayrollLine as _PayrollLine,
    PayrollRun as _PayrollRun,
    PayrollRunStatus as _PayrollRunStatus,
)
from app.models.revision import (
    RevisionStatus as _RevisionStatus,
    SalaryRevision as _SalaryRevision,
)
from app.models.saved_report import SavedReport as _SavedReport
from app.models.shift import (
    EmployeeShiftAssignment as _EmployeeShiftAssignment,
    ShiftTemplate as _ShiftTemplate,
)
from app.models.statutory import StatutoryFiling as _StatutoryFiling
from app.models.tax import Form24QExport as _Form24QExport
from app.services import reports as _rep
from app.services import report_export as _rx
from app.services.report_catalog import (
    REGISTRY as _REGISTRY,
    ReportCategory as _RCat,
    ReportDescriptor as _RDesc,
    register_descriptors as _register_descriptors,
)


# ------------------ RBAC helper ---------------------------------


_PERM_ATT = "report attendance"
_PERM_LEAVE = "report leave"
_PERM_PAY = "report payroll"
_PERM_STAT = "report statutory"
_PERM_HC = "report headcount"


def _user_has_perm(user: User, name: str) -> bool:
    if user.is_superuser:
        return True
    for role in user.roles or []:
        for perm in role.permissions or []:
            if (perm.name or "") == name:
                return True
    return False


def _is_hr_admin(user: User) -> bool:
    if user.is_superuser:
        return True
    role_names = [(r.name or "").lower() for r in user.roles or []]
    return any(n in role_names for n in ("hr", "super admin", "admin", "ceo"))


async def _manager_team_ids(db, user: User) -> _Opt[_List[int]]:
    """Return the manager's direct-report user_ids, or None if the
    caller is HR/Super Admin (unrestricted)."""
    if _is_hr_admin(user):
        return None
    stmt = select(User.id).where(User.manager_id == user.id)
    ids = list((await db.execute(stmt)).scalars().all())
    return ids


# ------------------ Filter parsing ------------------------------


def _parse_filter(
    payload: dict, team_ids: _Opt[_List[int]] = None,
) -> _rep.ReportFilter:
    def _d(v):
        if not v:
            return None
        if isinstance(v, _date):
            return v
        return _date.fromisoformat(v)

    f = _rep.ReportFilter(
        start=_d(payload.get("start")),
        end=_d(payload.get("end")),
        department=payload.get("department"),
        employee_ids=payload.get("employee_ids"),
        shift_template_id=payload.get("shift_template_id"),
        designation_id=payload.get("designation_id"),
        grade_id=payload.get("grade_id"),
        payroll_run_id=payload.get("payroll_run_id"),
        fy=payload.get("fy"),
        manager_scope_user_ids=team_ids,
        extras={k: v for k, v in payload.items() if k in (
            "per_row", "approved_only", "reference_prefix",
        )},
    )
    return f


# ------------------ Fetchers (async wrappers over DB) -----------


async def _employees_by_user_id(db, user_ids: set[int]) -> dict:
    if not user_ids:
        return {}
    rows = (await db.execute(
        select(_Employee).where(_Employee.user_id.in_(user_ids))
        .options(_selectinload(_Employee.user))
    )).scalars().all()
    return {e.user_id: e for e in rows}


async def _fetch_muster_roll(db, f: _rep.ReportFilter) -> _rep.ReportResult:
    stmt = select(_Attendance).order_by(_Attendance.work_date)
    if f.start: stmt = stmt.where(_Attendance.work_date >= f.start)
    if f.end: stmt = stmt.where(_Attendance.work_date <= f.end)
    if f.shift_template_id:
        stmt = stmt.where(_Attendance.shift_template_id == f.shift_template_id)
    att_rows = (await db.execute(stmt)).scalars().all()

    user_ids = {a.user_id for a in att_rows}
    emps = await _employees_by_user_id(db, user_ids)
    if f.department:
        emps = {uid: e for uid, e in emps.items() if e.department == f.department}
    holidays = set((await db.execute(
        select(_HolidayCalendar.date)
    )).scalars().all())

    records: _List[_rep.AttendanceRow] = []
    for a in att_rows:
        emp = emps.get(a.user_id)
        if emp is None:
            continue
        records.append(_rep.AttendanceRow(
            user_id=a.user_id, employee_code=emp.employee_id,
            full_name=emp.user.full_name if emp.user else "",
            department=emp.department, work_date=a.work_date,
            shift_template_id=a.shift_template_id,
            punch_in=a.captured_at, punch_out=a.punch_out_time,
            attribution_flag=a.attribution_flag,
            geo_flag=a.geo_flag,
            is_holiday=(a.work_date in holidays),
        ))
    return _rep.build_muster_roll(records=records, filters=f)


async def _fetch_late_early(db, f: _rep.ReportFilter) -> _rep.ReportResult:
    stmt = (
        select(_Attendance, _ShiftTemplate)
        .join(_ShiftTemplate, _Attendance.shift_template_id == _ShiftTemplate.id)
    )
    if f.start: stmt = stmt.where(_Attendance.work_date >= f.start)
    if f.end: stmt = stmt.where(_Attendance.work_date <= f.end)
    rows = (await db.execute(stmt)).all()

    user_ids = {a.user_id for a, _t in rows}
    emps = await _employees_by_user_id(db, user_ids)
    if f.department:
        emps = {uid: e for uid, e in emps.items() if e.department == f.department}

    records = []
    for a, tpl in rows:
        emp = emps.get(a.user_id)
        if emp is None:
            continue
        records.append(_rep.AttendanceRow(
            user_id=a.user_id, employee_code=emp.employee_id,
            full_name=emp.user.full_name if emp.user else "",
            department=emp.department, work_date=a.work_date,
            shift_name=tpl.name, shift_start=tpl.start_time,
            shift_end=tpl.end_time,
            grace_in_minutes=tpl.grace_in_minutes,
            grace_out_minutes=tpl.grace_out_minutes,
            punch_in=a.captured_at, punch_out=a.punch_out_time,
        ))
    return _rep.build_late_early(records=records, filters=f)


async def _fetch_absenteeism(db, f: _rep.ReportFilter) -> _rep.ReportResult:
    stmt = select(_Attendance)
    if f.start: stmt = stmt.where(_Attendance.work_date >= f.start)
    if f.end: stmt = stmt.where(_Attendance.work_date <= f.end)
    att_rows = (await db.execute(stmt)).scalars().all()
    user_ids = {a.user_id for a in att_rows}
    emps = await _employees_by_user_id(db, user_ids)
    if f.department:
        emps = {uid: e for uid, e in emps.items() if e.department == f.department}
    holidays = set((await db.execute(
        select(_HolidayCalendar.date)
    )).scalars().all())
    records = []
    for a in att_rows:
        emp = emps.get(a.user_id)
        if emp is None: continue
        records.append(_rep.AttendanceRow(
            user_id=a.user_id, employee_code=emp.employee_id,
            full_name=emp.user.full_name if emp.user else "",
            department=emp.department, work_date=a.work_date,
            punch_in=a.captured_at,
            is_holiday=(a.work_date in holidays),
        ))
    return _rep.build_absenteeism(records=records, filters=f)


async def _fetch_ot_report(db, f: _rep.ReportFilter) -> _rep.ReportResult:
    stmt = select(_OvertimeEntry)
    if f.start: stmt = stmt.where(_OvertimeEntry.work_date >= f.start)
    if f.end: stmt = stmt.where(_OvertimeEntry.work_date <= f.end)
    ot_rows = (await db.execute(stmt)).scalars().all()

    user_ids = {o.user_id for o in ot_rows}
    emps = await _employees_by_user_id(db, user_ids)
    if f.department:
        emps = {uid: e for uid, e in emps.items() if e.department == f.department}
    entries = []
    for o in ot_rows:
        emp = emps.get(o.user_id)
        if emp is None:
            continue
        entries.append(_rep.OTEntryRow(
            user_id=o.user_id, employee_code=emp.employee_id,
            full_name=emp.user.full_name if emp.user else "",
            department=emp.department, work_date=o.work_date,
            ot_minutes=o.ot_minutes, ot_amount=o.ot_amount,
            multiplier_used=o.multiplier_used, day_type=o.day_type,
            status=o.status,
        ))
    return _rep.build_ot_report(entries=entries, filters=f)


async def _fetch_flag_summary(db, f: _rep.ReportFilter) -> _rep.ReportResult:
    stmt = select(_Attendance).where(
        _or(
            _Attendance.attribution_flag.isnot(None),
            _Attendance.geo_flag.isnot(None),
        )
    )
    if f.start: stmt = stmt.where(_Attendance.work_date >= f.start)
    if f.end: stmt = stmt.where(_Attendance.work_date <= f.end)
    att_rows = (await db.execute(stmt)).scalars().all()

    user_ids = {a.user_id for a in att_rows}
    emps = await _employees_by_user_id(db, user_ids)
    if f.department:
        emps = {uid: e for uid, e in emps.items() if e.department == f.department}
    records = []
    for a in att_rows:
        emp = emps.get(a.user_id)
        if emp is None: continue
        records.append(_rep.AttendanceRow(
            user_id=a.user_id, employee_code=emp.employee_id,
            full_name=emp.user.full_name if emp.user else "",
            department=emp.department, work_date=a.work_date,
            attribution_flag=a.attribution_flag, geo_flag=a.geo_flag,
        ))
    return _rep.build_flag_summary(records=records, filters=f)


async def _fetch_leave_balance(db, f: _rep.ReportFilter) -> _rep.ReportResult:
    stmt = (
        select(_LeaveBalanceLedger, _LeaveType)
        .join(_LeaveType, _LeaveBalanceLedger.leave_type_id == _LeaveType.id)
    )
    rows = (await db.execute(stmt)).all()
    user_ids = {b.user_id for b, _t in rows}
    emps = await _employees_by_user_id(db, user_ids)
    if f.department:
        emps = {uid: e for uid, e in emps.items() if e.department == f.department}
    balances = []
    for b, lt in rows:
        emp = emps.get(b.user_id)
        if emp is None: continue
        balances.append(_rep.LeaveBalanceRow(
            user_id=b.user_id, employee_code=emp.employee_id,
            full_name=emp.user.full_name if emp.user else "",
            department=emp.department, leave_type=lt.name,
            quota=(b.balance or 0.0) + (b.used or 0.0),
            used=b.used or 0.0, balance=b.balance or 0.0,
        ))
    return _rep.build_leave_balance(balances=balances, filters=f)


async def _fetch_leave_utilization(
    db, f: _rep.ReportFilter,
) -> _rep.ReportResult:
    # Reuse balance fetch — utilization builder aggregates.
    rows_result = await _fetch_leave_balance(db, f)
    balances = [_rep.LeaveBalanceRow(
        user_id=r["user_id"], employee_code=r["employee_code"],
        full_name=r["full_name"], department=r["department"],
        leave_type=r["leave_type"], quota=r["quota"],
        used=r["used"], balance=r["balance"],
    ) for r in rows_result.rows]
    return _rep.build_leave_utilization(balances=balances, filters=f)


async def _fetch_salary_register(
    db, f: _rep.ReportFilter,
) -> _rep.ReportResult:
    if not f.payroll_run_id:
        raise HTTPException(400, "payroll_run_id required")
    run = await db.get(_PayrollRun, f.payroll_run_id)
    if run is None:
        raise HTTPException(404, "Payroll run not found")
    if run.status not in (
        _PayrollRunStatus.FINALIZED, _PayrollRunStatus.PUBLISHED,
    ):
        raise HTTPException(
            400,
            "Salary reports run on FINALIZED / PUBLISHED payroll only.",
        )
    lines_res = (await db.execute(
        select(_PayrollLine).where(_PayrollLine.payroll_run_id == run.id)
    )).scalars().all()
    user_ids = {ln.user_id for ln in lines_res}
    emps = await _employees_by_user_id(db, user_ids)
    if f.department:
        emps = {uid: e for uid, e in emps.items() if e.department == f.department}
    lines = []
    for ln in lines_res:
        emp = emps.get(ln.user_id)
        if emp is None: continue
        lines.append(_rep.PayrollLineRow(
            user_id=ln.user_id, employee_code=emp.employee_id,
            full_name=emp.user.full_name if emp.user else "",
            department=emp.department,
            base_salary=ln.base_salary,
            payable_days=ln.payable_days, lop_days=ln.lop_days,
            gross_pay=ln.gross_pay, net_pay=ln.net_pay,
            allowances=ln.allowances or {}, deductions=ln.deductions or {},
            bank_account=emp.bank_account, bank_name=emp.bank_name,
            # Employee model doesn't carry IFSC — reuse bank_name as
            # a placeholder; production installs will add an IFSC field.
            ifsc=getattr(emp, "ifsc_code", None),
        ))
    r = _rep.build_salary_register(lines=lines, filters=f)
    r.meta["payroll_period"] = f"{run.month:02d}/{run.year}"
    r.meta["run_status"] = run.status.value if hasattr(run.status, "value") else str(run.status)
    return r


async def _fetch_bank_advice(
    db, f: _rep.ReportFilter,
) -> _rep.ReportResult:
    # Enforce finalized-only via the shared validation path.
    run = await db.get(_PayrollRun, f.payroll_run_id) if f.payroll_run_id else None
    if run is None:
        raise HTTPException(400, "payroll_run_id required")
    if run.status not in (
        _PayrollRunStatus.FINALIZED, _PayrollRunStatus.PUBLISHED,
    ):
        raise HTTPException(
            400,
            "Bank advice runs on FINALIZED / PUBLISHED payroll only.",
        )
    lines_res = (await db.execute(
        select(_PayrollLine).where(
            _PayrollLine.payroll_run_id == f.payroll_run_id
        )
    )).scalars().all()
    user_ids = {ln.user_id for ln in lines_res}
    emps = await _employees_by_user_id(db, user_ids)
    lines = []
    for ln in lines_res:
        emp = emps.get(ln.user_id)
        if emp is None: continue
        lines.append(_rep.PayrollLineRow(
            user_id=ln.user_id, employee_code=emp.employee_id,
            full_name=emp.user.full_name if emp.user else "",
            department=emp.department,
            base_salary=ln.base_salary,
            payable_days=ln.payable_days, lop_days=ln.lop_days,
            gross_pay=ln.gross_pay, net_pay=ln.net_pay,
            allowances=ln.allowances or {}, deductions=ln.deductions or {},
            bank_account=emp.bank_account, bank_name=emp.bank_name,
            ifsc=getattr(emp, "ifsc_code", None),
        ))
    return _rep.build_bank_advice(lines=lines, filters=f)


async def _fetch_increment_report(
    db, f: _rep.ReportFilter,
) -> _rep.ReportResult:
    stmt = select(_SalaryRevision).where(
        _SalaryRevision.status == _RevisionStatus.APPLIED,
    )
    if f.start: stmt = stmt.where(_SalaryRevision.effective_from >= f.start)
    if f.end: stmt = stmt.where(_SalaryRevision.effective_from <= f.end)
    revs = (await db.execute(stmt)).scalars().all()

    emp_ids = {r.employee_id for r in revs}
    emp_rows = (await db.execute(
        select(_Employee).where(_Employee.id.in_(emp_ids))
        .options(_selectinload(_Employee.user))
    )).scalars().all() if emp_ids else []
    emp_by_id = {e.id: e for e in emp_rows}
    if f.department:
        emp_by_id = {i: e for i, e in emp_by_id.items() if e.department == f.department}

    rows = []
    for rv in revs:
        emp = emp_by_id.get(rv.employee_id)
        if emp is None: continue
        rows.append(_rep.RevisionRow(
            user_id=emp.user_id, employee_code=emp.employee_id,
            full_name=emp.user.full_name if emp.user else "",
            department=emp.department,
            revision_type=rv.revision_type,
            effective_from=rv.effective_from,
            old_ctc=rv.old_ctc, new_ctc=rv.new_ctc,
            hike_amount=rv.hike_amount, hike_percent=rv.hike_percent,
            status=rv.status,
        ))
    return _rep.build_increment_report(revisions=rows, filters=f)


async def _fetch_statutory_summary(
    db, f: _rep.ReportFilter,
) -> _rep.ReportResult:
    # Pull all StatutoryFiling summaries + all Form24Q summaries in the
    # window; aggregate to per-month totals.
    stmt_f = select(_StatutoryFiling)
    stmt_q = select(_Form24QExport)
    stat_rows = (await db.execute(stmt_f)).scalars().all()
    q24_rows = (await db.execute(stmt_q)).scalars().all()

    # Bucket by (year, month) — StatutoryFiling → PayrollRun for period.
    run_map = {}
    run_ids = {s.payroll_run_id for s in stat_rows}
    if run_ids:
        runs = (await db.execute(
            select(_PayrollRun).where(_PayrollRun.id.in_(run_ids))
        )).scalars().all()
        run_map = {r.id: (r.year, r.month) for r in runs}

    period_bucket: dict[tuple, dict] = {}
    for s in stat_rows:
        key = run_map.get(s.payroll_run_id)
        if key is None:
            continue
        year, month = key
        b = period_bucket.setdefault((year, month), {
            "period": f"{month:02d}/{year}",
            "total_employees": 0,
            "total_employee_pf": 0.0, "total_employer_pf": 0.0,
            "total_eps": 0.0, "total_employee_esic": 0.0,
            "total_employer_esic": 0.0, "total_pt": 0.0, "total_tds": 0.0,
        })
        summary = s.summary or {}
        if s.stream == "epf":
            b["total_employees"] = max(
                b["total_employees"],
                int(summary.get("employee_count", 0)),
            )
            b["total_employee_pf"] += float(summary.get("total_employee_epf", 0.0))
            b["total_employer_pf"] += float(summary.get("total_employer_epf", 0.0))
            b["total_eps"] += float(summary.get("total_employer_eps", 0.0))
        elif s.stream == "esic":
            b["total_employee_esic"] += float(summary.get("total_employee_contribution", 0.0))
            b["total_employer_esic"] += float(summary.get("total_employer_contribution", 0.0))
        elif s.stream == "pt":
            b["total_pt"] += float(summary.get("total_pt_amount", 0.0))

    # TDS: use Form24Q summaries when available (per FY quarter → month
    # granularity is approximate — spread quarterly total across the
    # three months of the quarter for the summary row).
    for q in q24_rows:
        summary = q.summary or {}
        total_tds = float(summary.get("total_tds_deducted", 0.0))
        if not total_tds:
            continue
        fy_a, fy_b = q.fy.split("-")
        start_year = 2000 + int(fy_a)
        end_year = 2000 + int(fy_b)
        if q.quarter == 1:
            months = [(start_year, 4), (start_year, 5), (start_year, 6)]
        elif q.quarter == 2:
            months = [(start_year, 7), (start_year, 8), (start_year, 9)]
        elif q.quarter == 3:
            months = [(start_year, 10), (start_year, 11), (start_year, 12)]
        else:
            months = [(end_year, 1), (end_year, 2), (end_year, 3)]
        share = round(total_tds / 3.0, 2)
        for y, m in months:
            b = period_bucket.setdefault((y, m), {
                "period": f"{m:02d}/{y}",
                "total_employees": 0,
                "total_employee_pf": 0.0, "total_employer_pf": 0.0,
                "total_eps": 0.0, "total_employee_esic": 0.0,
                "total_employer_esic": 0.0, "total_pt": 0.0, "total_tds": 0.0,
            })
            b["total_tds"] += share

    keys = sorted(period_bucket.keys())
    if f.start:
        keys = [k for k in keys if _date(k[0], k[1], 1) >= _date(f.start.year, f.start.month, 1)]
    if f.end:
        keys = [k for k in keys if _date(k[0], k[1], 1) <= _date(f.end.year, f.end.month, 1)]

    months_input = [
        _rep.StatutorySummaryInput(**period_bucket[k]) for k in keys
    ]
    return _rep.build_statutory_summary(months=months_input, filters=f)


async def _fetch_headcount_trend(
    db, f: _rep.ReportFilter,
) -> _rep.ReportResult:
    # 12 months ending today.
    today = _date.today()
    months_back = int(f.extras.get("months_back", 12))
    windows = []
    for i in range(months_back - 1, -1, -1):
        y = today.year
        m = today.month - i
        while m <= 0:
            m += 12
            y -= 1
        first = _date(y, m, 1)
        last = _date(y, m, _monthrange(y, m)[1])
        windows.append((y, m, first, last))

    # Pull employees + resignations once.
    emps_q = select(_Employee).options(_selectinload(_Employee.user))
    if f.department:
        emps_q = emps_q.where(_Employee.department == f.department)
    emps = (await db.execute(emps_q)).scalars().all()

    from app.models.exit_management import Resignation as _Resignation
    resigs = (await db.execute(select(_Resignation))).scalars().all()

    rows = []
    for y, m, first, last in windows:
        joiners = sum(1 for e in emps if first <= e.date_of_joining <= last)
        leavers = sum(
            1 for r in resigs
            if r.last_working_day and first <= r.last_working_day <= last
        )
        # Closing = employees whose DOJ ≤ last and (no resignation OR
        # resignation last_working_day > last).
        exit_by_emp_id = {r.employee_id: r for r in resigs}
        closing = sum(
            1 for e in emps
            if e.date_of_joining <= last and (
                exit_by_emp_id.get(e.id) is None
                or (exit_by_emp_id[e.id].last_working_day is None
                    or exit_by_emp_id[e.id].last_working_day > last)
            )
        )
        opening = closing - joiners + leavers
        rows.append(_rep.MonthlyHeadcountRow(
            month_label=first.strftime("%b %Y"), year=y, month=m,
            opening=opening, joiners=joiners, leavers=leavers,
            closing=closing,
        ))
    return _rep.build_headcount_trend(months=rows, filters=f)


async def _fetch_attrition_report(
    db, f: _rep.ReportFilter,
) -> _rep.ReportResult:
    trend = await _fetch_headcount_trend(db, f)
    inputs = []
    for row in trend.rows:
        avg_hc = (row["opening"] + row["closing"]) / 2.0
        inputs.append(_rep.AttritionInput(
            month_label=row["month_label"], year=row["year"],
            month=row["month"],
            leavers=row["leavers"],
            voluntary=row["leavers"], involuntary=0,
            avg_headcount=avg_hc, department=f.department,
        ))
    return _rep.build_attrition_report(months=inputs, filters=f)


# ------------------ Fetcher registry ---------------------------


_FETCHERS = {
    "muster_roll": _fetch_muster_roll,
    "late_early": _fetch_late_early,
    "absenteeism": _fetch_absenteeism,
    "ot_report": _fetch_ot_report,
    "flag_summary": _fetch_flag_summary,
    "leave_balance": _fetch_leave_balance,
    "leave_utilization": _fetch_leave_utilization,
    "salary_register": _fetch_salary_register,
    "bank_advice": _fetch_bank_advice,
    "increment_report": _fetch_increment_report,
    "statutory_summary": _fetch_statutory_summary,
    "headcount_trend": _fetch_headcount_trend,
    "attrition_report": _fetch_attrition_report,
}

_register_descriptors(_FETCHERS)


# ------------------ Endpoints -----------------------------------


@router.get("/catalog")
async def report_catalog(
    current_user: User = Depends(deps.get_current_user),
) -> _Any:
    """List all reports the caller has permission to run."""
    out = []
    for d in _REGISTRY.all():
        if not _user_has_perm(current_user, d.permission):
            continue
        out.append({
            "key": d.key, "name": d.name,
            "description": d.description, "category": d.category,
            "permission": d.permission,
            "is_sensitive": d.is_sensitive,
            "manager_scoped": d.manager_scoped,
            "filters": [
                {
                    "key": fs.key, "label": fs.label, "type": fs.type,
                    "required": fs.required, "options": fs.options,
                    "hint": fs.hint,
                }
                for fs in d.filters
            ],
        })
    return {"reports": out, "categories": list({r["category"] for r in out})}


@router.post("/run/{report_key}")
async def run_report(
    report_key: str,
    payload: dict,
    db: deps.DBDep,
    request: _Request,
    format: str = _Query("json", pattern="^(json|xlsx|csv|pdf)$"),
    stream: bool = _Query(False, description="Stream large exports"),
    current_user: User = Depends(deps.get_current_user),
) -> _Any:
    """Run a report. `payload` carries the ReportFilter; `format` picks
    the renderer. Sensitive reports (payroll/statutory) audit-log every
    export."""
    desc = _REGISTRY.get(report_key)
    if desc is None:
        raise HTTPException(404, f"Unknown report: {report_key}")
    if not _user_has_perm(current_user, desc.permission):
        raise HTTPException(403, f"Missing permission: {desc.permission}")

    # Manager scope: only when the report is scoped AND caller isn't HR.
    team_ids = None
    if desc.manager_scoped:
        team_ids = await _manager_team_ids(db, current_user)
    f = _parse_filter(payload or {}, team_ids=team_ids)

    if desc.fetch_and_build is None:
        raise HTTPException(500, "Report has no fetcher registered")
    result: _rep.ReportResult = await desc.fetch_and_build(db, f)
    result.meta.setdefault("report_key", report_key)
    result.meta.setdefault(
        "generated_at", datetime.now(timezone.utc).isoformat(),
    )

    if desc.is_sensitive and format != "json":
        await _log_audit(
            db, current_user.id, "REPORT_EXPORT_SENSITIVE",
            "report", report_key,
            {
                "format": format, "filters": payload,
                "row_count": result.meta.get("row_count"),
            },
            request,
        )

    title = desc.name

    if format == "json":
        return _rx.to_json_payload(result)
    if format == "csv":
        if stream:
            return _Stream(
                _rx.iter_csv_rows(result),
                media_type="text/csv",
                headers={
                    "Content-Disposition":
                        f'attachment; filename="{report_key}.csv"',
                },
            )
        text = _rx.render_csv(result)
        return _Stream(
            _io.BytesIO(text.encode("utf-8")),
            media_type="text/csv",
            headers={
                "Content-Disposition":
                    f'attachment; filename="{report_key}.csv"',
            },
        )
    if format == "xlsx":
        blob = _rx.render_xlsx(result, stream=stream)
        return _Stream(
            _io.BytesIO(blob),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition":
                    f'attachment; filename="{report_key}.xlsx"',
            },
        )
    if format == "pdf":
        blob = _rx.render_pdf(result, title=title)
        return _Stream(
            _io.BytesIO(blob), media_type="application/pdf",
            headers={
                "Content-Disposition":
                    f'attachment; filename="{report_key}.pdf"',
            },
        )
    raise HTTPException(400, f"Unsupported format: {format}")


# ------------------ Saved reports CRUD --------------------------


@router.get("/saved")
async def list_saved(
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> _Any:
    stmt = select(_SavedReport).order_by(_SavedReport.created_at.desc())
    rows = (await db.execute(stmt)).scalars().all()
    return [
        {
            c.name: getattr(r, c.name) for c in r.__table__.columns
        } for r in rows
    ]


@router.post("/saved")
async def create_saved(
    payload: dict,
    db: deps.DBDep,
    request: _Request,
    current_user: User = Depends(deps.get_current_user),
) -> _Any:
    if not payload.get("name") or not payload.get("report_key"):
        raise HTTPException(400, "name + report_key required")
    desc = _REGISTRY.get(payload["report_key"])
    if desc is None:
        raise HTTPException(404, "Unknown report_key")
    if not _user_has_perm(current_user, desc.permission):
        raise HTTPException(403, "Missing permission for that report")
    obj = _SavedReport(
        name=payload["name"], report_key=payload["report_key"],
        description=payload.get("description"),
        filters_json=payload.get("filters_json", {}),
        default_format=payload.get("default_format", "xlsx"),
        cadence=payload.get("cadence", "none"),
        recipients_json=payload.get("recipients_json", []),
        owner_id=current_user.id,
    )
    db.add(obj)
    await db.flush()
    await _log_audit(
        db, current_user.id, "SAVED_REPORT_CREATE", "saved_report",
        str(obj.id), {"name": obj.name, "report_key": obj.report_key},
        request,
    )
    await db.commit()
    await db.refresh(obj)
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}


@router.delete("/saved/{sid}")
async def delete_saved(
    sid: int, db: deps.DBDep, request: _Request,
    current_user: User = Depends(deps.get_current_user),
) -> _Any:
    obj = await db.get(_SavedReport, sid)
    if obj is None:
        raise HTTPException(404, "Not found")
    if obj.owner_id != current_user.id and not _is_hr_admin(current_user):
        raise HTTPException(403, "Not owner")
    obj.is_active = False
    await _log_audit(
        db, current_user.id, "SAVED_REPORT_DEACTIVATE", "saved_report",
        str(sid), {}, request,
    )
    await db.commit()
    return {"message": "Deactivated"}


@router.post("/saved/{sid}/run-now")
async def saved_run_now(
    sid: int,
    db: deps.DBDep,
    request: _Request,
    format: str = _Query(None, pattern="^(json|xlsx|csv|pdf)$"),
    current_user: User = Depends(deps.get_current_user),
) -> _Any:
    obj = await db.get(_SavedReport, sid)
    if obj is None:
        raise HTTPException(404, "Not found")
    obj.last_run_at = datetime.now(timezone.utc)
    await db.commit()
    return await run_report(
        report_key=obj.report_key,
        payload=obj.filters_json or {},
        db=db, request=request,
        format=format or obj.default_format,
        stream=False,
        current_user=current_user,
    )

