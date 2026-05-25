import calendar
from datetime import datetime, date, timezone
from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException, Request
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
from app.models.audit import AuditLog
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

    # Get distinct user_ids that have attendance in the period
    att_q = select(Attendance.user_id.distinct()).where(
        and_(
            func.date(Attendance.captured_at) >= month_start,
            func.date(Attendance.captured_at) <= month_end,
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
    
    num_days = calendar.monthrange(run.year, run.month)[1]
    
    total_gross = 0.0
    total_net = 0.0
    
    for emp in employees:
        # Calculate LOP days from unpaid leaves
        # Find approved leave requests in this month
        start_of_month = date(run.year, run.month, 1)
        end_of_month = date(run.year, run.month, num_days)
        
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
        base_salary = emp.salary or 0.0

        # Resolve salary components (auto-calculate from basic if not set)
        ca = emp.conveyance_allowance if emp.conveyance_allowance is not None else round(base_salary * 0.30)
        hra_val = emp.hra if emp.hra is not None else round(base_salary * 0.50)
        other_val = emp.other_allowance if emp.other_allowance is not None else round(base_salary * 0.20)
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

        gross = breakdown["total_actual_earnings"]
        net = breakdown["net_salary"]

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
            arrear=0.0,
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
                "arrear": 0.0,
                "incentive": 0.0,
            },
            deductions={
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
            },
        )
        db.add(line)
        total_gross += gross
        total_net += net

    run.status = PayrollRunStatus.DRAFT_GENERATED
    run.total_gross = total_gross
    run.total_net = total_net
    
    log_audit(
        db, current_user.id, "GENERATE_DRAFT", "payroll_run",
        str(run_id), {
            "period": f"{run.month}/{run.year}",
            "line_count": len(employees)
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

    line.arrear = new_arrear
    line.incentive = new_incentive
    line.gross_pay = breakdown["total_actual_earnings"]
    line.net_pay = breakdown["net_salary"]
    line.allowances = {
        **(line.allowances or {}),
        "arrear": new_arrear,
        "incentive": new_incentive,
        "basic_salary_actual": breakdown["basic_salary_actual"],
        "conveyance_actual": breakdown["conveyance_actual"],
        "hra_actual": breakdown["hra_actual"],
        "other_allowance_actual": breakdown["other_allowance_actual"],
    }
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
    }

    # Update run totals using old values
    run.total_gross = run.total_gross - old_gross + breakdown["total_actual_earnings"]
    run.total_net = run.total_net - old_net + breakdown["net_salary"]

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
