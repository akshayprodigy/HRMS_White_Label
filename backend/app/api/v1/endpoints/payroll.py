import calendar
from datetime import datetime, date, timezone
from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import select, and_, func, delete
from app.api import deps
from app.models.payroll import (
    PayrollRun, PayrollLine, Payslip, PayrollRunStatus, SalaryDisbursement
)
from app.models.user import User
from app.models.employee import Employee
from app.models.leave import LeaveRequest, LeaveStatus, LeaveType
from app.models.attendance import Attendance
from app.models.salary_advance import (
    SalaryAdvance, AdvanceRecovery, AdvanceStatus
)
from app.services.salary_calculator import calculate_salary, calculate_salary_contractual
from app.services.payroll_engine import (
    compute_statutory, load_statutory_context,
)
from app.models.audit import AuditLog
from app.models.overtime import (
    OvertimeEntry, NightAllowanceEntry, OvertimeStatus,
)
from app.models.revision import SalaryRevision, RevisionStatus
from app.services.revisions import (
    effective_components_for_month, compute_arrears_for_revision,
)
from app.schemas.payroll import (
    PayrollRunCreate, PayrollRunRead, PayrollLineRead, PayrollLineUpdate,
    PayrollDashboard, PayrollActionResponse
)

router = APIRouter()

# Permissions
HR_PAYROLL_RUN = "hr payroll run"
HR_PAYROLL_APPROVE = "hr payroll approve"
HR_PAYROLL_VIEW = "hr payroll view"

ERR_RUN_NOT_FOUND = "Run not found"


def log_audit(
    db: deps.DBDep,
    user_id: int,
    action: str,
    resource_type: str,
    resource_id: str,
    details: dict,
    request: Request
):
    audit_details = dict(details or {})
    audit_details["user_agent"] = request.headers.get("user-agent")
    audit = AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=audit_details,
        ip_address=request.client.host if request.client else None,
    )
    db.add(audit)


@router.get("/dashboard", response_model=PayrollDashboard)
async def get_payroll_dashboard(
    db: deps.DBDep,
    current_user: User = Depends(deps.check_permissions([HR_PAYROLL_VIEW]))
) -> Any:
    # Get active runs (not published)
    active_runs_res = await db.execute(
        select(PayrollRun).where(
            PayrollRun.status != PayrollRunStatus.PUBLISHED
        ).order_by(PayrollRun.year.desc(), PayrollRun.month.desc())
    )
    active_runs = active_runs_res.scalars().all()

    # Last finalized run
    last_finalized_res = await db.execute(
        select(PayrollRun).where(
            PayrollRun.status == PayrollRunStatus.FINALIZED
        ).order_by(PayrollRun.finalized_at.desc()).limit(1)
    )
    last_finalized = last_finalized_res.scalar_one_or_none()

    # Total processed YTD (gross)
    curr_year = date.today().year
    ytd_res = await db.execute(
        select(func.sum(PayrollRun.total_gross)).where(
            and_(
                PayrollRun.year == curr_year,
                PayrollRun.status.in_([
                    PayrollRunStatus.FINALIZED, PayrollRunStatus.PUBLISHED
                ])
            )
        )
    )
    total_ytd = ytd_res.scalar() or 0.0

    return {
        "active_runs": active_runs,
        "last_finalized_run": last_finalized,
        "total_processed_ytd": total_ytd
    }


@router.post("/run", response_model=PayrollRunRead)
async def create_payroll_run(
    *,
    db: deps.DBDep,
    obj_in: PayrollRunCreate,
    current_user: User = Depends(deps.check_permissions([HR_PAYROLL_RUN]))
) -> Any:
    # Check if an active (non-published) run already exists for this period
    existing = await db.execute(
        select(PayrollRun).where(
            and_(
                PayrollRun.month == obj_in.month,
                PayrollRun.year == obj_in.year,
                PayrollRun.status != PayrollRunStatus.PUBLISHED,
            )
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail="An active payroll run for this period already exists"
        )

    db_obj = PayrollRun(
        month=obj_in.month,
        year=obj_in.year,
        status=PayrollRunStatus.DRAFT
    )
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj


@router.get("/{run_id}/attendance-check")
async def check_attendance_before_lock(
    run_id: int,
    db: deps.DBDep,
    current_user: User = Depends(deps.check_permissions([HR_PAYROLL_RUN]))
) -> Any:
    """Check which active employees have no attendance records for the payroll period."""
    run = await db.get(PayrollRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail=ERR_RUN_NOT_FOUND)

    # Get all active employees
    emp_q = select(Employee, User).join(User, Employee.user_id == User.id).where(
        Employee.status == "active", User.is_active == True
    )
    emp_rows = (await db.execute(emp_q)).all()

    import calendar as cal
    month_start = date(run.year, run.month, 1)
    month_end = date(run.year, run.month, cal.monthrange(run.year, run.month)[1])

    # Get distinct user_ids that have attendance in the period. Filter by
    # LOGICAL work_date (set by the shift-aware resolver) so a night shift
    # starting on Jun 30 23:00 and ending Jul 1 07:00 is counted in JUNE
    # payroll, not July. captured_at would mis-route that record to July.
    att_q = select(Attendance.user_id.distinct()).where(
        and_(
            Attendance.work_date >= month_start,
            Attendance.work_date <= month_end,
        )
    )
    users_with_att = set((await db.execute(att_q)).scalars().all())

    present = []
    missing = []
    for emp, user in emp_rows:
        entry = {"employee_id": emp.employee_id, "name": user.full_name, "email": user.email}
        if user.id in users_with_att:
            present.append(entry)
        else:
            missing.append(entry)

    return {
        "period": f"{run.month}/{run.year}",
        "total_active_employees": len(emp_rows),
        "with_attendance": len(present),
        "missing_attendance": len(missing),
        "missing": missing,
    }


@router.post("/{run_id}/lock-attendance", response_model=PayrollActionResponse)
async def lock_attendance(
    run_id: int,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.check_permissions([HR_PAYROLL_RUN]))
) -> Any:
    run = await db.get(PayrollRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail=ERR_RUN_NOT_FOUND)
    
    if run.status != PayrollRunStatus.DRAFT:
        raise HTTPException(
            status_code=400,
            detail="Can only lock attendance for draft runs"
        )
    
    # In a real system, we'd snapshotted attendance data here
    # For this implementation, we just mark it as locked
    run.status = PayrollRunStatus.ATTENDANCE_LOCKED
    run.attendance_locked_at = datetime.now(timezone.utc)
    
    log_audit(
        db, current_user.id, "LOCK_ATTENDANCE", "payroll_run",
        str(run_id), {"period": f"{run.month}/{run.year}"}, request
    )
    
    await db.commit()
    await db.refresh(run)
    return {"message": "Attendance successfully locked", "run": run}


@router.post("/{run_id}/lock-leaves", response_model=PayrollActionResponse)
async def lock_leaves(
    run_id: int,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.check_permissions([HR_PAYROLL_RUN]))
) -> Any:
    run = await db.get(PayrollRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail=ERR_RUN_NOT_FOUND)
    
    if run.status != PayrollRunStatus.ATTENDANCE_LOCKED:
        raise HTTPException(
            status_code=400,
            detail="Must lock attendance before locking leaves"
        )
    
    run.status = PayrollRunStatus.LEAVES_LOCKED
    run.leaves_locked_at = datetime.now(timezone.utc)
    
    log_audit(
        db, current_user.id, "LOCK_LEAVES", "payroll_run",
        str(run_id), {"period": f"{run.month}/{run.year}"}, request
    )
    
    await db.commit()
    await db.refresh(run)
    return {"message": "Leaves successfully locked", "run": run}


@router.post("/{run_id}/generate-draft", response_model=PayrollActionResponse)
async def generate_draft(
    run_id: int,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.check_permissions([HR_PAYROLL_RUN]))
) -> Any:
    run = await db.get(PayrollRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail=ERR_RUN_NOT_FOUND)
    
    if run.status != PayrollRunStatus.LEAVES_LOCKED:
        raise HTTPException(
            status_code=400,
            detail="Must lock leaves before generating draft"
        )
    
    # 1. Clear existing lines
    await db.execute(
        delete(PayrollLine).where(
            PayrollLine.payroll_run_id == run_id
        )
    )
    
    # 2. Get all active employees
    employees_res = await db.execute(
        select(Employee).where(Employee.status == "active")
    )
    employees = employees_res.scalars().all()

    # Unified statutory engine — one bulk load of StatutoryConfig,
    # PT slabs, tax slabs, declarations and FY-to-date actuals; the
    # per-line math below reads from this context (no N+1).
    stat_ctx = await load_statutory_context(
        db, run.year, run.month, employees
    )

    num_days = calendar.monthrange(run.year, run.month)[1]
    
    total_gross = 0.0
    total_net = 0.0
    
    start_of_month = date(run.year, run.month, 1)
    end_of_month = date(run.year, run.month, num_days)

    # Pull OT + night-allowance for the period in ONE SHOT and group by user.
    # We filter on payroll_run_id IS NULL so already-finalized entries are
    # never double-counted. The `work_date` boundary respects the shift
    # engine's overnight-spanning rule (Jun 30 night shift → June payroll).
    ot_rows = (await db.execute(
        select(OvertimeEntry).where(
            and_(
                OvertimeEntry.work_date >= start_of_month,
                OvertimeEntry.work_date <= end_of_month,
                OvertimeEntry.payroll_run_id.is_(None),
                OvertimeEntry.status.in_([
                    OvertimeStatus.APPROVED,
                    OvertimeStatus.AUTO_APPROVED,
                ]),
            )
        )
    )).scalars().all()
    ot_by_user: dict[int, list[OvertimeEntry]] = {}
    for r in ot_rows:
        ot_by_user.setdefault(r.user_id, []).append(r)

    night_rows = (await db.execute(
        select(NightAllowanceEntry).where(
            and_(
                NightAllowanceEntry.work_date >= start_of_month,
                NightAllowanceEntry.work_date <= end_of_month,
                NightAllowanceEntry.payroll_run_id.is_(None),
            )
        )
    )).scalars().all()
    night_by_user: dict[int, list[NightAllowanceEntry]] = {}
    for r in night_rows:
        night_by_user.setdefault(r.user_id, []).append(r)

    injected_ot_users = 0
    injected_night_users = 0
    injected_arrear_users = 0

    # Pull every APPLIED revision in one shot so we can do
    # effective-component selection + arrear computation without N+1.
    rev_q = (await db.execute(
        select(SalaryRevision).where(
            SalaryRevision.status == RevisionStatus.APPLIED
        )
    )).scalars().all()
    revs_by_emp: dict[int, list[SalaryRevision]] = {}
    for r in rev_q:
        revs_by_emp.setdefault(r.employee_id, []).append(r)

    for emp in employees:
        # Calculate LOP days from unpaid leaves
        # Find approved leave requests in this month
        
        leaves_res = await db.execute(
            select(LeaveRequest).join(LeaveType).where(
                and_(
                    LeaveRequest.employee_id == emp.user_id,
                    LeaveRequest.status == LeaveStatus.APPROVED,
                    LeaveType.unpaid_allowed.is_(True),
                    LeaveRequest.start_date <= end_of_month,
                    LeaveRequest.end_date >= start_of_month
                )
            )
        )
        unpaid_leaves = leaves_res.scalars().all()
        
        lop_days = 0.0
        for lv in unpaid_leaves:
            # Simple overlap calculation
            overlap_start = max(lv.start_date, start_of_month)
            overlap_end = min(lv.end_date, end_of_month)
            days = float((overlap_end - overlap_start).days + 1)
            if lv.is_half_day:
                days = 0.5
            lop_days += days
        
        payable_days = max(0.0, float(num_days) - lop_days)

        # Effective components for THIS payroll month. If an APPLIED
        # revision is in effect (effective_from inside the month or
        # earlier), its NEW components govern; otherwise we fall back
        # to the employee master. This is the no-regression contract:
        # employees with zero revisions are unaffected.
        emp_master_basic = float(emp.salary or 0.0)
        emp_master_ca = float(
            emp.conveyance_allowance if emp.conveyance_allowance is not None
            else round(emp_master_basic * 0.30)
        )
        emp_master_hra = float(
            emp.hra if emp.hra is not None
            else round(emp_master_basic * 0.50)
        )
        emp_master_other = float(
            emp.other_allowance if emp.other_allowance is not None
            else round(emp_master_basic * 0.20)
        )
        eff = effective_components_for_month(
            employee_basic=emp_master_basic,
            employee_conveyance=emp_master_ca,
            employee_hra=emp_master_hra,
            employee_other_allowance=emp_master_other,
            revisions=revs_by_emp.get(emp.id, []),
            year=run.year, month=run.month,
        )
        base_salary = eff.basic
        ca = eff.conveyance
        hra_val = eff.hra
        other_val = eff.other_allowance
        esic = emp.esic_applicable or False
        vpf = emp.voluntary_pf or 0.0
        is_contractual = (emp.employment_type or "permanent") in ("contractual", "advisor")

        # Full salary calculation
        if is_contractual:
            breakdown = calculate_salary_contractual(
                basic_salary=base_salary,
                paid_days=int(payable_days),
                days_in_month=num_days,
            )
            breakdown["employment_type"] = emp.employment_type or "contractual"
        else:
            breakdown = calculate_salary(
                basic_salary=base_salary,
                conveyance_allowance=ca,
                hra=hra_val,
                other_allowance=other_val,
                esic_applicable=esic,
                paid_days=int(payable_days),
                days_in_month=num_days,
                voluntary_pf=vpf,
            )

        # OT + night-allowance injection — aggregated from the pre-computed
        # entries for this employee for this work-month. Each entry has
        # work_date inside [start_of_month, end_of_month] (already filtered),
        # so the month-boundary rule (overnight shift starting Jun 30 →
        # June payroll) is respected automatically. Entries with a
        # payroll_run_id were filtered out, so double-counting on
        # re-generate is impossible.
        emp_ot_entries = ot_by_user.get(emp.user_id, [])
        emp_night_entries = night_by_user.get(emp.user_id, [])

        ot_amount = round(sum(e.ot_amount for e in emp_ot_entries), 2)
        ot_minutes = sum(e.ot_minutes for e in emp_ot_entries)
        night_amount = round(
            sum(e.amount for e in emp_night_entries), 2
        )
        night_minutes = sum(e.night_minutes for e in emp_night_entries)

        if ot_amount > 0:
            injected_ot_users += 1
        if night_amount > 0:
            injected_night_users += 1

        # Arrears for back-dated APPLIED revisions whose effective_from
        # falls in a past payroll month and that have not been paid yet
        # (arrears_run_id IS NULL). Per ARREAR_BASIS, amount =
        # (new_monthly_gross - old_monthly_gross) * months_owed. Once
        # injected, the revision's arrears_run_id is stamped so a
        # re-generate (after run delete) is the only way to re-fire,
        # and finalized runs are never retro-edited.
        arrears_amount = 0.0
        arrears_meta: list[dict] = []
        for r in revs_by_emp.get(emp.id, []):
            a = compute_arrears_for_revision(
                revision=r, draft_year=run.year, draft_month=run.month,
            )
            if a is None:
                continue
            arrears_amount += a.amount
            r.arrears_run_id = run_id
            r.arrears_amount = a.amount
            r.arrears_months = a.months_owed
            arrears_meta.append({
                "revision_id": a.revision_id,
                "months": a.months_owed,
                "monthly_delta": a.monthly_delta,
                "amount": a.amount,
            })
        arrears_amount = round(arrears_amount, 2)
        if arrears_amount > 0:
            injected_arrear_users += 1

        gross = (
            breakdown["total_actual_earnings"]
            + ot_amount + night_amount + arrears_amount
        )
        if is_contractual:
            # Legacy flat-10% contractual path — out of P0 scope.
            net = (
                breakdown["net_salary"]
                + ot_amount + night_amount + arrears_amount
            )
            stat = None
            total_ded = breakdown["total_deductions"]
        else:
            # Unified engine: ESIC / PT / TDS on the FULL gross
            # (incl. OT + night + arrears), PF on capped basic.
            stat = compute_statutory(
                stat_ctx, emp,
                basic_actual=breakdown["basic_salary_actual"],
                hra_actual=breakdown["hra_actual"],
                gross_total=gross,
            )
            total_ded = round(
                stat.employee_pf + vpf + stat.esic_employee
                + stat.pt_amount + stat.tds, 2,
            )
            net = round(gross - total_ded, 2)

        # Auto-recover active salary advances
        advance_deduction = 0.0
        active_advances_res = await db.execute(
            select(SalaryAdvance).where(
                and_(
                    SalaryAdvance.employee_id == emp.id,
                    SalaryAdvance.status == AdvanceStatus.ACTIVE,
                )
            )
        )
        for adv in active_advances_res.scalars().all():
            outstanding = adv.amount - adv.recovered_amount
            if outstanding <= 0:
                continue
            emi = (
                round(adv.amount / adv.installment_months, 2)
                if adv.installment_months > 0
                else outstanding
            )
            deduct = min(emi, outstanding, net - advance_deduction)
            if deduct <= 0:
                continue
            recovery = AdvanceRecovery(
                advance_id=adv.id,
                payroll_run_id=run_id,
                amount=deduct,
                remarks=f"Auto payroll {run.month}/{run.year}",
            )
            db.add(recovery)
            adv.recovered_amount += deduct
            if adv.recovered_amount >= adv.amount - 0.01:
                adv.status = AdvanceStatus.FULLY_RECOVERED
            advance_deduction += deduct

        line = PayrollLine(
            payroll_run_id=run_id,
            user_id=emp.user_id,
            base_salary=base_salary,
            payable_days=payable_days,
            lop_days=lop_days,
            # Pre-fill arrear with the auto-computed back-dated revision
            # delta; HR can still bump it in the line editor (any extra
            # one-off arrear). The revision-derived portion is reflected
            # separately in `allowances.revision_arrears` for audit.
            arrear=arrears_amount,
            incentive=0.0,
            gross_pay=gross,
            net_pay=net,
            advance_deduction=advance_deduction,
            disbursed_amount=0.0,
            allowances={
                "conveyance_fixed": breakdown["conveyance_fixed"],
                "hra_fixed": breakdown["hra_fixed"],
                "other_allowance_fixed": breakdown["other_allowance_fixed"],
                "conveyance_actual": breakdown["conveyance_actual"],
                "hra_actual": breakdown["hra_actual"],
                "other_allowance_actual": breakdown["other_allowance_actual"],
                "basic_salary_actual": breakdown["basic_salary_actual"],
                "total_fixed_earnings": breakdown["total_fixed_earnings"],
                "arrear": arrears_amount,
                "incentive": 0.0,
                "overtime": ot_amount,
                "overtime_minutes": ot_minutes,
                "night_allowance": night_amount,
                "night_minutes": night_minutes,
                # Provenance of the auto-populated arrear so HR can
                # tell revision-arrears apart from any manual top-up.
                "revision_arrears": arrears_amount,
                "revision_arrears_detail": arrears_meta,
                "effective_components_source": eff.source,
            },
            deductions=(
                {
                    "employee_esi": stat.esic_employee,
                    "employee_pf": stat.employee_pf,
                    "voluntary_pf": vpf,
                    "professional_tax": stat.pt_amount,
                    "guest_house": 0.0,
                    "tds": stat.tds,
                    "total_deductions": total_ded,
                    "advance_recovery": advance_deduction,
                    "employer_esic": stat.esic_employer,
                    "employer_pf": stat.employer_pf,
                    "total_employer_cost": round(
                        net + stat.esic_employer + stat.employer_pf
                        + stat.epf_admin_charges + stat.edli_charges, 2,
                    ),
                    "esic_applicable": stat.esic_covered,
                    "engine": "unified_v1",
                    "epf_wages": stat.epf_wages,
                    "epf_admin_charges": stat.epf_admin_charges,
                    "edli_charges": stat.edli_charges,
                    "esic_covered": stat.esic_covered,
                    "esic_basis": stat.esic_basis,
                    "pt_state": stat.pt_state,
                    "tds_auto": stat.tds_auto,
                    "tds_regime": stat.tds_regime,
                    "tds_note": stat.tds_note,
                } if stat is not None else {
                    "employee_esi": breakdown["employee_esi"],
                    "employee_pf": breakdown["employee_pf"],
                    "voluntary_pf": breakdown["voluntary_pf"],
                    "professional_tax": breakdown["professional_tax"],
                    "guest_house": breakdown["guest_house"],
                    "tds": breakdown["tds"],
                    "total_deductions": breakdown["total_deductions"],
                    "advance_recovery": advance_deduction,
                    "employer_esic": breakdown["employer_esic"],
                    "employer_pf": breakdown["employer_pf"],
                    "total_employer_cost": breakdown["total_employer_cost"],
                    "esic_applicable": breakdown["esic_applicable"],
                    "engine": "legacy_contractual",
                }
            ),
        )
        db.add(line)
        total_gross += gross
        total_net += net

        # Stamp injected OT + night entries so they can never be picked
        # up by a future generate_draft. This is the no-double-count
        # guarantee. If the run is later DELETED (re-draft scenario), the
        # FK is ondelete=SET NULL, so the entries become candidates
        # again.
        for e in emp_ot_entries:
            e.payroll_run_id = run_id
        for e in emp_night_entries:
            e.payroll_run_id = run_id

    run.status = PayrollRunStatus.DRAFT_GENERATED
    run.total_gross = total_gross
    run.total_net = total_net
    
    log_audit(
        db, current_user.id, "GENERATE_DRAFT", "payroll_run",
        str(run_id), {
            "period": f"{run.month}/{run.year}",
            "line_count": len(employees),
            "ot_users_injected": injected_ot_users,
            "ot_entries_injected": len(ot_rows),
            "ot_total_amount": round(
                sum(e.ot_amount for e in ot_rows), 2
            ),
            "night_users_injected": injected_night_users,
            "night_entries_injected": len(night_rows),
            "night_total_amount": round(
                sum(e.amount for e in night_rows), 2
            ),
            "arrear_users_injected": injected_arrear_users,
        },
        request
    )
    
    await db.commit()
    await db.refresh(run)
    return {"message": "Draft payroll lines generated", "run": run}


@router.post("/{run_id}/finalize", response_model=PayrollActionResponse)
async def finalize_run(
    run_id: int,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.check_permissions([HR_PAYROLL_APPROVE]))
) -> Any:
    run = await db.get(PayrollRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail=ERR_RUN_NOT_FOUND)
    
    if run.status != PayrollRunStatus.DRAFT_GENERATED:
        raise HTTPException(
            status_code=400,
            detail="Run must be in DRAFT_GENERATED status to finalize"
        )
    
    run.status = PayrollRunStatus.FINALIZED
    run.finalized_at = datetime.now(timezone.utc)
    run.finalized_by_id = current_user.id
    
    log_audit(
        db, current_user.id, "FINALIZE_RUN", "payroll_run",
        str(run_id), {"period": f"{run.month}/{run.year}"}, request
    )
    
    await db.commit()
    await db.refresh(run)
    return {"message": "Payroll run finalized", "run": run}


@router.post("/{run_id}/publish", response_model=PayrollActionResponse)
async def publish_run(
    run_id: int,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.check_permissions([HR_PAYROLL_APPROVE]))
) -> Any:
    run = await db.get(PayrollRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail=ERR_RUN_NOT_FOUND)
    
    if run.status != PayrollRunStatus.FINALIZED:
        raise HTTPException(
            status_code=400,
            detail="Run must be in FINALIZED status to publish"
        )
    
    # Generate payslips
    lines_res = await db.execute(
        select(PayrollLine).where(PayrollLine.payroll_run_id == run_id)
    )
    lines = lines_res.scalars().all()
    
    for line in lines:
        payslip_number = f"PAY-{run.year}{run.month:02d}-{line.user_id}"
        payslip = Payslip(
            payroll_line_id=line.id,
            file_url=f"/payslips/{payslip_number}.pdf",
            published_at=datetime.now(timezone.utc),
        )
        db.add(payslip)
    
    run.status = PayrollRunStatus.PUBLISHED
    run.published_at = datetime.now(timezone.utc)
    
    log_audit(
        db, current_user.id, "PUBLISH_RUN", "payroll_run",
        str(run_id), {"period": f"{run.month}/{run.year}"}, request
    )
    
    await db.commit()
    await db.refresh(run)
    return {
        "message": "Payroll run published and payslips generated",
        "run": run
    }


@router.get("/{run_id}/lines", response_model=List[PayrollLineRead])
async def get_run_lines(
    run_id: int,
    db: deps.DBDep,
    current_user: User = Depends(deps.check_permissions([HR_PAYROLL_VIEW]))
) -> Any:
    res = await db.execute(
        select(PayrollLine, User.full_name.label("user_full_name"))
        .join(User, PayrollLine.user_id == User.id)
        .where(PayrollLine.payroll_run_id == run_id)
    )
    result = []
    for row in res.all():
        line, full_name = row
        payable = line.net_pay - line.advance_deduction
        # Count disbursements
        cnt_res = await db.execute(
            select(func.count(SalaryDisbursement.id)).where(
                SalaryDisbursement.payroll_line_id == line.id
            )
        )
        line.user_full_name = full_name
        line.payable_amount = round(payable, 2)
        line.pending_amount = round(payable - line.disbursed_amount, 2)
        line.disbursement_count = cnt_res.scalar() or 0
        result.append(line)
    return result


@router.patch("/{run_id}/lines/{line_id}", response_model=PayrollLineRead)
async def update_payroll_line(
    run_id: int,
    line_id: int,
    payload: PayrollLineUpdate,
    db: deps.DBDep,
    current_user: User = Depends(deps.check_permissions([HR_PAYROLL_RUN]))
) -> Any:
    """Update arrear/incentive/guest_house/tds on a draft payroll line and recalculate."""
    run = await db.get(PayrollRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail=ERR_RUN_NOT_FOUND)
    if run.status != PayrollRunStatus.DRAFT_GENERATED:
        raise HTTPException(status_code=400, detail="Can only edit lines in DRAFT_GENERATED status")

    line_res = await db.execute(
        select(PayrollLine).where(
            PayrollLine.id == line_id,
            PayrollLine.payroll_run_id == run_id
        )
    )
    line = line_res.scalar_one_or_none()
    if not line:
        raise HTTPException(status_code=404, detail="Payroll line not found")

    emp_res = await db.execute(
        select(Employee).where(Employee.user_id == line.user_id)
    )
    emp = emp_res.scalar_one_or_none()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    num_days = calendar.monthrange(run.year, run.month)[1]
    base_salary = line.base_salary
    vpf = emp.voluntary_pf or 0.0
    is_contractual = (emp.employment_type or "permanent") in ("contractual", "advisor")

    # Use new values if provided, else keep existing from line/deductions JSON
    existing_ded = line.deductions or {}
    new_arrear = payload.arrear if payload.arrear is not None else (line.arrear or 0.0)
    new_incentive = payload.incentive if payload.incentive is not None else (line.incentive or 0.0)
    new_guest_house = payload.guest_house if payload.guest_house is not None else existing_ded.get("guest_house", 0.0)
    new_tds = payload.tds if payload.tds is not None else existing_ded.get("tds", 0.0)

    if is_contractual:
        breakdown = calculate_salary_contractual(
            basic_salary=base_salary,
            paid_days=int(line.payable_days),
            days_in_month=num_days,
            arrear=new_arrear,
            incentive=new_incentive,
        )
        breakdown["employment_type"] = emp.employment_type or "contractual"
    else:
        ca = emp.conveyance_allowance if emp.conveyance_allowance is not None else round(base_salary * 0.30)
        hra_val = emp.hra if emp.hra is not None else round(base_salary * 0.50)
        other_val = emp.other_allowance if emp.other_allowance is not None else round(base_salary * 0.20)
        breakdown = calculate_salary(
            basic_salary=base_salary,
            conveyance_allowance=ca,
            hra=hra_val,
            other_allowance=other_val,
            esic_applicable=emp.esic_applicable or False,
            paid_days=int(line.payable_days),
            days_in_month=num_days,
            voluntary_pf=vpf,
            arrear=new_arrear,
            incentive=new_incentive,
            guest_house=new_guest_house,
            tds=new_tds,
        )

    # Capture old values before mutating line
    old_gross = line.gross_pay
    old_net = line.net_pay

    # Preserve OT + night allowance already injected at generate_draft.
    # The line editor only touches arrear/incentive/guest_house/tds.
    existing_allow = line.allowances or {}
    prev_ot = float(existing_allow.get("overtime", 0.0))
    prev_night = float(existing_allow.get("night_allowance", 0.0))

    line.arrear = new_arrear
    line.incentive = new_incentive
    line.gross_pay = (
        breakdown["total_actual_earnings"] + prev_ot + prev_night
    )
    if is_contractual:
        line.net_pay = breakdown["net_salary"] + prev_ot + prev_night
        line.deductions = {
            **(line.deductions or {}),
            "employee_esi": breakdown["employee_esi"],
            "employee_pf": breakdown["employee_pf"],
            "voluntary_pf": breakdown["voluntary_pf"],
            "guest_house": new_guest_house,
            "tds": new_tds,
            "professional_tax": breakdown["professional_tax"],
            "total_deductions": breakdown["total_deductions"],
            "employer_esic": breakdown["employer_esic"],
            "employer_pf": breakdown["employer_pf"],
            "total_employer_cost": breakdown["total_employer_cost"],
            "esic_applicable": breakdown["esic_applicable"],
            "engine": "legacy_contractual",
        }
    else:
        # Unified engine on the edited gross. A TDS typed by HR is a
        # manual override and sticks across later edits (tds_manual);
        # otherwise TDS re-derives from the tax config.
        stat_ctx = await load_statutory_context(
            db, run.year, run.month, [emp]
        )
        was_manual = bool(existing_ded.get("tds_manual"))
        if payload.tds is not None:
            tds_override, tds_manual = float(payload.tds), True
        elif was_manual:
            tds_override, tds_manual = float(existing_ded.get("tds", 0.0)), True
        else:
            tds_override, tds_manual = None, False
        stat = compute_statutory(
            stat_ctx, emp,
            basic_actual=breakdown["basic_salary_actual"],
            hra_actual=breakdown["hra_actual"],
            gross_total=line.gross_pay,
            tds_override=tds_override,
        )
        total_ded = round(
            stat.employee_pf + vpf + stat.esic_employee
            + stat.pt_amount + stat.tds + new_guest_house, 2,
        )
        line.net_pay = round(line.gross_pay - total_ded, 2)
        line.deductions = {
            **(line.deductions or {}),
            "employee_esi": stat.esic_employee,
            "employee_pf": stat.employee_pf,
            "voluntary_pf": vpf,
            "guest_house": new_guest_house,
            "tds": stat.tds,
            "tds_manual": tds_manual,
            "professional_tax": stat.pt_amount,
            "total_deductions": total_ded,
            "employer_esic": stat.esic_employer,
            "employer_pf": stat.employer_pf,
            "total_employer_cost": round(
                line.net_pay + stat.esic_employer + stat.employer_pf
                + stat.epf_admin_charges + stat.edli_charges, 2,
            ),
            "esic_applicable": stat.esic_covered,
            "engine": "unified_v1",
            "epf_wages": stat.epf_wages,
            "epf_admin_charges": stat.epf_admin_charges,
            "edli_charges": stat.edli_charges,
            "esic_covered": stat.esic_covered,
            "esic_basis": stat.esic_basis,
            "pt_state": stat.pt_state,
            "tds_auto": stat.tds_auto,
            "tds_regime": stat.tds_regime,
            "tds_note": stat.tds_note,
        }
    line.allowances = {
        **existing_allow,
        "arrear": new_arrear,
        "incentive": new_incentive,
        "basic_salary_actual": breakdown["basic_salary_actual"],
        "conveyance_actual": breakdown["conveyance_actual"],
        "hra_actual": breakdown["hra_actual"],
        "other_allowance_actual": breakdown["other_allowance_actual"],
        # overtime/night already in existing_allow — carried via spread.
    }

    # Update run totals using old values (line totals already include OT/night).
    run.total_gross = run.total_gross - old_gross + line.gross_pay
    run.total_net = run.total_net - old_net + line.net_pay

    user_res = await db.execute(select(User).where(User.id == line.user_id))
    user = user_res.scalar_one_or_none()

    await db.commit()
    await db.refresh(line)

    payable = line.net_pay - line.advance_deduction
    line.user_full_name = user.full_name if user else None
    line.payable_amount = round(payable, 2)
    line.pending_amount = round(payable - line.disbursed_amount, 2)
    line.disbursement_count = 0
    return line


def _has_payroll_view(user: User) -> bool:
    if user.is_superuser:
        return True
    for role in user.roles or []:
        if (role.name or "").lower() in ("hr", "admin", "super admin"):
            return True
        for perm in role.permissions or []:
            if (perm.name or "") in (HR_PAYROLL_VIEW, HR_PAYROLL_RUN):
                return True
    return False


@router.get("/payslips/{payslip_id}/download")
async def download_payslip(
    payslip_id: int,
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user)
) -> Any:
    """Render a published payslip as PDF. Accessible to the payslip's
    owner and to payroll-view roles (HR/admin)."""
    row = (await db.execute(
        select(Payslip, PayrollLine, PayrollRun)
        .join(PayrollLine, Payslip.payroll_line_id == PayrollLine.id)
        .join(PayrollRun, PayrollLine.payroll_run_id == PayrollRun.id)
        .where(Payslip.id == payslip_id)
    )).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Payslip not found")
    _, line, run = row
    if line.user_id != current_user.id and not _has_payroll_view(current_user):
        raise HTTPException(status_code=403, detail="Not authorized")

    emp = (await db.execute(
        select(Employee).where(Employee.user_id == line.user_id)
    )).scalar_one_or_none()
    emp_user = await db.get(User, line.user_id)

    from app.models.statutory import EmployerIdentifier
    from app.core.config import settings
    employer = (await db.execute(
        select(EmployerIdentifier)
        .where(EmployerIdentifier.is_active.is_(True)).limit(1)
    )).scalar_one_or_none()

    from app.services.payslip_pdf import build_payslip_pdf
    pdf = build_payslip_pdf(
        company_name=(employer.name if employer else settings.PROJECT_NAME),
        month=run.month, year=run.year,
        employee_name=(emp_user.full_name if emp_user else "-"),
        employee_code=(emp.employee_id if emp else str(line.user_id)),
        department=(emp.department if emp else None),
        designation=(emp.designation if emp else None),
        pan_number=(emp.pan_number if emp else None),
        bank_name=(emp.bank_name if emp else None),
        bank_account=(emp.bank_account if emp else None),
        payable_days=float(line.payable_days or 0),
        lop_days=float(line.lop_days or 0),
        allowances=line.allowances or {},
        deductions=line.deductions or {},
        gross_pay=float(line.gross_pay or 0),
        net_pay=float(line.net_pay or 0),
        advance_deduction=float(line.advance_deduction or 0),
    )
    fname = (
        f"Payslip_{emp.employee_id if emp else line.user_id}"
        f"_{run.year}{run.month:02d}.pdf"
    )
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/my-payslips")
async def get_my_payslips(
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user)
) -> Any:
    """Return published payslips with salary breakdown for current user."""
    res = await db.execute(
        select(
            Payslip,
            PayrollLine.gross_pay,
            PayrollLine.net_pay,
            PayrollLine.advance_deduction,
            PayrollLine.disbursed_amount,
            PayrollLine.payable_days,
            PayrollLine.lop_days,
            PayrollRun.month,
            PayrollRun.year,
        )
        .join(PayrollLine, Payslip.payroll_line_id == PayrollLine.id)
        .join(PayrollRun, PayrollLine.payroll_run_id == PayrollRun.id)
        .where(
            and_(
                PayrollLine.user_id == current_user.id,
                PayrollRun.status == PayrollRunStatus.PUBLISHED,
            )
        )
        .order_by(PayrollRun.year.desc(), PayrollRun.month.desc())
    )
    result = []
    for slip, gross, net, adv_ded, disbursed, days, lop, month, year in res.all():
        result.append({
            "id": slip.id,
            "file_url": slip.file_url,
            "published_at": slip.published_at.isoformat() if slip.published_at else None,
            "month": month,
            "year": year,
            "gross_pay": gross,
            "net_pay": net,
            "advance_deduction": adv_ded,
            "disbursed_amount": disbursed,
            "payable_days": days,
            "lop_days": lop,
        })
    return result
