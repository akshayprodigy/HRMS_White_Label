from datetime import datetime, timezone
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select, and_, func
from sqlalchemy.orm import selectinload
from app.api import deps
from app.models.user import User
from app.models.employee import Employee
from app.models.salary_advance import (
    SalaryAdvance, AdvanceRecovery, AdvanceStatus, RecoveryMode
)
from app.models.payroll import (
    PayrollLine, PayrollRun, PayrollRunStatus, SalaryDisbursement
)
from app.models.audit import AuditLog
from app.schemas.salary_advance import (
    SalaryAdvanceCreate,
    SalaryAdvanceUpdate,
    SalaryAdvanceRead,
    SalaryAdvanceWriteOff,
    ManualRecovery,
    AdvanceRecoveryRead,
    PartialPaymentSet,
    HeldSalaryRelease,
)
from app.schemas.payroll import (
    SalaryDisbursementCreate,
    SalaryDisbursementRead,
)

router = APIRouter()

HR_WRITE = "hr employee write"
HR_READ = "hr employee read"
HR_PAYROLL_RUN = "hr payroll run"


def _log_audit(db, user_id, action, resource_type, resource_id, details, request):
    audit_details = dict(details or {})
    audit_details["user_agent"] = request.headers.get("user-agent")
    db.add(AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=audit_details,
        ip_address=request.client.host if request.client else None,
    ))


# ─── Salary Advance CRUD ───────────────────────────────────────────

@router.get("/advances", response_model=List[SalaryAdvanceRead])
async def list_advances(
    db: deps.DBDep,
    status: Optional[str] = Query(None),
    employee_id: Optional[int] = Query(None),
    current_user: User = Depends(deps.check_permissions([HR_READ])),
) -> Any:
    """List all salary advances. Optionally filter by status or employee."""
    q = (
        select(
            SalaryAdvance,
            User.full_name.label("approved_by_name"),
            Employee.employee_id.label("employee_code"),
        )
        .join(User, SalaryAdvance.approved_by_id == User.id)
        .join(Employee, SalaryAdvance.employee_id == Employee.id)
    )
    if status:
        q = q.where(SalaryAdvance.status == status)
    if employee_id:
        q = q.where(SalaryAdvance.employee_id == employee_id)
    q = q.order_by(SalaryAdvance.created_at.desc())

    res = await db.execute(q)
    rows = res.all()

    result = []
    for adv, approver_name, emp_code in rows:
        # Get employee user name
        emp = await db.get(Employee, adv.employee_id)
        emp_user = await db.get(User, emp.user_id) if emp else None
        item = SalaryAdvanceRead.model_validate(adv)
        item.employee_name = emp_user.full_name if emp_user else None
        item.employee_code = emp_code
        item.department = emp.department if emp else None
        item.approved_by_name = approver_name
        item.outstanding = max(0.0, adv.amount - adv.recovered_amount)
        item.monthly_emi = (
            round(adv.amount / adv.installment_months, 2)
            if adv.installment_months > 0
            else adv.amount - adv.recovered_amount
        )
        result.append(item)
    return result


@router.post("/advances", response_model=SalaryAdvanceRead)
async def create_advance(
    *,
    db: deps.DBDep,
    obj_in: SalaryAdvanceCreate,
    request: Request,
    current_user: User = Depends(deps.check_permissions([HR_WRITE])),
) -> Any:
    """HR disburses a salary advance to an employee."""
    emp = await db.get(Employee, obj_in.employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    advance = SalaryAdvance(
        employee_id=obj_in.employee_id,
        amount=obj_in.amount,
        reason=obj_in.reason,
        disbursed_date=obj_in.disbursed_date,
        recovery_mode=obj_in.recovery_mode,
        installment_months=obj_in.installment_months,
        remarks=obj_in.remarks,
        approved_by_id=current_user.id,
        status=AdvanceStatus.ACTIVE,
    )
    db.add(advance)
    await db.flush()

    _log_audit(
        db, current_user.id, "CREATE_ADVANCE", "salary_advance",
        str(advance.id),
        {"employee_id": obj_in.employee_id, "amount": obj_in.amount},
        request,
    )
    await db.commit()
    await db.refresh(advance)

    emp_user = await db.get(User, emp.user_id)
    item = SalaryAdvanceRead.model_validate(advance)
    item.employee_name = emp_user.full_name if emp_user else None
    item.employee_code = emp.employee_id
    item.department = emp.department
    item.approved_by_name = current_user.full_name
    item.outstanding = advance.amount
    item.monthly_emi = (
        round(advance.amount / advance.installment_months, 2)
        if advance.installment_months > 0
        else advance.amount
    )
    return item


@router.get("/advances/my", response_model=List[SalaryAdvanceRead])
async def my_advances(
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Employee views their own salary advances."""
    emp_res = await db.execute(
        select(Employee).where(Employee.user_id == current_user.id).limit(1)
    )
    emp = emp_res.scalar_one_or_none()
    if not emp:
        return []

    res = await db.execute(
        select(SalaryAdvance)
        .where(SalaryAdvance.employee_id == emp.id)
        .order_by(SalaryAdvance.created_at.desc())
    )
    advances = res.scalars().all()
    result = []
    for adv in advances:
        approver = await db.get(User, adv.approved_by_id)
        item = SalaryAdvanceRead.model_validate(adv)
        item.employee_name = current_user.full_name
        item.employee_code = emp.employee_id
        item.department = emp.department
        item.approved_by_name = approver.full_name if approver else None
        item.outstanding = max(0.0, adv.amount - adv.recovered_amount)
        item.monthly_emi = (
            round(adv.amount / adv.installment_months, 2)
            if adv.installment_months > 0
            else item.outstanding
        )
        result.append(item)
    return result


@router.get("/advances/{advance_id}", response_model=SalaryAdvanceRead)
async def get_advance(
    advance_id: int,
    db: deps.DBDep,
    current_user: User = Depends(deps.check_permissions([HR_READ])),
) -> Any:
    """Get salary advance detail."""
    adv = await db.get(SalaryAdvance, advance_id)
    if not adv:
        raise HTTPException(status_code=404, detail="Advance not found")

    emp = await db.get(Employee, adv.employee_id)
    emp_user = await db.get(User, emp.user_id) if emp else None
    approver = await db.get(User, adv.approved_by_id)

    item = SalaryAdvanceRead.model_validate(adv)
    item.employee_name = emp_user.full_name if emp_user else None
    item.employee_code = emp.employee_id if emp else None
    item.department = emp.department if emp else None
    item.approved_by_name = approver.full_name if approver else None
    item.outstanding = max(0.0, adv.amount - adv.recovered_amount)
    item.monthly_emi = (
        round(adv.amount / adv.installment_months, 2)
        if adv.installment_months > 0
        else item.outstanding
    )
    return item


@router.put("/advances/{advance_id}", response_model=SalaryAdvanceRead)
async def update_advance(
    advance_id: int,
    *,
    db: deps.DBDep,
    obj_in: SalaryAdvanceUpdate,
    request: Request,
    current_user: User = Depends(deps.check_permissions([HR_WRITE])),
) -> Any:
    """Update recovery mode / remarks on an active advance."""
    adv = await db.get(SalaryAdvance, advance_id)
    if not adv:
        raise HTTPException(status_code=404, detail="Advance not found")
    if adv.status != AdvanceStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Can only edit active advances")

    if obj_in.recovery_mode is not None:
        adv.recovery_mode = obj_in.recovery_mode
    if obj_in.installment_months is not None:
        adv.installment_months = obj_in.installment_months
    if obj_in.reason is not None:
        adv.reason = obj_in.reason
    if obj_in.remarks is not None:
        adv.remarks = obj_in.remarks
    adv.updated_at = datetime.now(timezone.utc)

    _log_audit(
        db, current_user.id, "UPDATE_ADVANCE", "salary_advance",
        str(advance_id), {"changes": obj_in.model_dump(exclude_none=True)}, request,
    )
    await db.commit()
    await db.refresh(adv)

    emp = await db.get(Employee, adv.employee_id)
    emp_user = await db.get(User, emp.user_id) if emp else None
    approver = await db.get(User, adv.approved_by_id)
    item = SalaryAdvanceRead.model_validate(adv)
    item.employee_name = emp_user.full_name if emp_user else None
    item.employee_code = emp.employee_id if emp else None
    item.department = emp.department if emp else None
    item.approved_by_name = approver.full_name if approver else None
    item.outstanding = max(0.0, adv.amount - adv.recovered_amount)
    item.monthly_emi = (
        round(adv.amount / adv.installment_months, 2)
        if adv.installment_months > 0
        else item.outstanding
    )
    return item


@router.post("/advances/{advance_id}/write-off")
async def write_off_advance(
    advance_id: int,
    *,
    db: deps.DBDep,
    obj_in: SalaryAdvanceWriteOff,
    request: Request,
    current_user: User = Depends(deps.check_permissions([HR_WRITE])),
) -> Any:
    """Write off remaining balance of an advance (e.g. waiver)."""
    adv = await db.get(SalaryAdvance, advance_id)
    if not adv:
        raise HTTPException(status_code=404, detail="Advance not found")
    if adv.status != AdvanceStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Advance is not active")

    adv.status = AdvanceStatus.WRITTEN_OFF
    adv.remarks = obj_in.remarks or adv.remarks
    adv.updated_at = datetime.now(timezone.utc)

    _log_audit(
        db, current_user.id, "WRITE_OFF_ADVANCE", "salary_advance",
        str(advance_id),
        {"outstanding": adv.amount - adv.recovered_amount},
        request,
    )
    await db.commit()
    return {"message": "Advance written off", "advance_id": advance_id}


@router.post("/advances/{advance_id}/cancel")
async def cancel_advance(
    advance_id: int,
    *,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.check_permissions([HR_WRITE])),
) -> Any:
    """Cancel an advance (only if no recoveries yet)."""
    adv = await db.get(SalaryAdvance, advance_id)
    if not adv:
        raise HTTPException(status_code=404, detail="Advance not found")
    if adv.status != AdvanceStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Advance is not active")
    if adv.recovered_amount > 0:
        raise HTTPException(
            status_code=400,
            detail="Cannot cancel — recoveries already recorded"
        )

    adv.status = AdvanceStatus.CANCELLED
    adv.updated_at = datetime.now(timezone.utc)

    _log_audit(
        db, current_user.id, "CANCEL_ADVANCE", "salary_advance",
        str(advance_id), {}, request,
    )
    await db.commit()
    return {"message": "Advance cancelled", "advance_id": advance_id}


@router.post("/advances/{advance_id}/recover", response_model=AdvanceRecoveryRead)
async def manual_recovery(
    advance_id: int,
    *,
    db: deps.DBDep,
    obj_in: ManualRecovery,
    request: Request,
    current_user: User = Depends(deps.check_permissions([HR_WRITE])),
) -> Any:
    """Record a manual (off-payroll) recovery against an advance."""
    adv = await db.get(SalaryAdvance, advance_id)
    if not adv:
        raise HTTPException(status_code=404, detail="Advance not found")
    if adv.status != AdvanceStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Advance is not active")

    outstanding = adv.amount - adv.recovered_amount
    if obj_in.amount > outstanding + 0.01:
        raise HTTPException(
            status_code=400,
            detail=f"Recovery amount exceeds outstanding balance of {outstanding:.2f}"
        )

    recovery = AdvanceRecovery(
        advance_id=advance_id,
        amount=obj_in.amount,
        remarks=obj_in.remarks or "Manual recovery",
    )
    db.add(recovery)

    adv.recovered_amount += obj_in.amount
    if adv.recovered_amount >= adv.amount - 0.01:
        adv.status = AdvanceStatus.FULLY_RECOVERED
    adv.updated_at = datetime.now(timezone.utc)

    _log_audit(
        db, current_user.id, "MANUAL_RECOVERY", "salary_advance",
        str(advance_id), {"amount": obj_in.amount}, request,
    )
    await db.commit()
    await db.refresh(recovery)
    return recovery


@router.get(
    "/advances/{advance_id}/recoveries",
    response_model=List[AdvanceRecoveryRead],
)
async def list_recoveries(
    advance_id: int,
    db: deps.DBDep,
    current_user: User = Depends(deps.check_permissions([HR_READ])),
) -> Any:
    """List all recovery records for a given advance."""
    res = await db.execute(
        select(AdvanceRecovery)
        .where(AdvanceRecovery.advance_id == advance_id)
        .order_by(AdvanceRecovery.recovered_at.desc())
    )
    return res.scalars().all()


# ─── Partial Payment ──────────────────────────────────────────────

@router.post("/payroll/{run_id}/lines/{line_id}/partial-payment")
async def set_partial_payment(
    run_id: int,
    line_id: int,
    *,
    db: deps.DBDep,
    obj_in: PartialPaymentSet,
    request: Request,
    current_user: User = Depends(deps.check_permissions([HR_PAYROLL_RUN])),
) -> Any:
    """
    HR sets a partial payment on a payroll line (before finalization).
    The held_amount = net_pay - disbursed_amount.
    """
    run = await db.get(PayrollRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status not in (
        PayrollRunStatus.DRAFT_GENERATED,
    ):
        raise HTTPException(
            status_code=400,
            detail="Partial payment can only be set on draft-generated runs"
        )

    line = await db.get(PayrollLine, line_id)
    if not line or line.payroll_run_id != run_id:
        raise HTTPException(status_code=404, detail="Payroll line not found")

    effective_net = line.net_pay - line.advance_deduction
    if obj_in.disbursed_amount > effective_net + 0.01:
        raise HTTPException(
            status_code=400,
            detail=f"Disbursed amount cannot exceed net pay of {effective_net:.2f}"
        )

    line.disbursed_amount = obj_in.disbursed_amount
    line.held_amount = round(effective_net - obj_in.disbursed_amount, 2)
    line.held_reason = obj_in.held_reason

    _log_audit(
        db, current_user.id, "SET_PARTIAL_PAYMENT", "payroll_line",
        str(line_id),
        {
            "net_pay": line.net_pay,
            "disbursed": obj_in.disbursed_amount,
            "held": line.held_amount,
        },
        request,
    )
    await db.commit()
    return {
        "message": "Partial payment set",
        "line_id": line_id,
        "disbursed_amount": line.disbursed_amount,
        "held_amount": line.held_amount,
    }


@router.post("/payroll/{run_id}/release-held")
async def release_held_salaries(
    run_id: int,
    *,
    db: deps.DBDep,
    obj_in: HeldSalaryRelease,
    request: Request,
    current_user: User = Depends(deps.check_permissions([HR_PAYROLL_RUN])),
) -> Any:
    """
    Release previously held amounts. This marks them as released
    and associates them with the current payroll run for record-keeping.
    """
    run = await db.get(PayrollRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    released_count = 0
    for lid in obj_in.payroll_line_ids:
        line = await db.get(PayrollLine, lid)
        if not line or line.held_amount <= 0 or line.held_released:
            continue
        line.held_released = True
        line.held_released_in_run_id = run_id
        released_count += 1

    _log_audit(
        db, current_user.id, "RELEASE_HELD_SALARIES", "payroll_run",
        str(run_id), {"released_count": released_count}, request,
    )
    await db.commit()
    return {
        "message": f"{released_count} held salary(ies) released",
        "run_id": run_id,
    }


@router.get("/payroll/held-salaries")
async def list_held_salaries(
    db: deps.DBDep,
    current_user: User = Depends(deps.check_permissions([HR_READ])),
) -> Any:
    """List all unreleased held salaries across payroll runs."""
    res = await db.execute(
        select(PayrollLine, User.full_name, PayrollRun.month, PayrollRun.year)
        .join(User, PayrollLine.user_id == User.id)
        .join(PayrollRun, PayrollLine.payroll_run_id == PayrollRun.id)
        .where(
            and_(
                PayrollLine.held_amount > 0,
                PayrollLine.held_released.is_(False),
            )
        )
        .order_by(PayrollRun.year.desc(), PayrollRun.month.desc())
    )
    rows = res.all()
    return [
        {
            "line_id": line.id,
            "user_id": line.user_id,
            "user_full_name": full_name,
            "month": month,
            "year": year,
            "net_pay": line.net_pay,
            "disbursed_amount": line.disbursed_amount,
            "held_amount": line.held_amount,
            "held_reason": line.held_reason,
        }
        for line, full_name, month, year in rows
    ]


# ─── Salary Disbursements (multi-part payments) ──────────────────

@router.post(
    "/payroll/lines/{line_id}/disburse",
    response_model=SalaryDisbursementRead,
)
async def record_disbursement(
    line_id: int,
    *,
    db: deps.DBDep,
    obj_in: SalaryDisbursementCreate,
    request: Request,
    current_user: User = Depends(deps.check_permissions([HR_PAYROLL_RUN])),
) -> Any:
    """
    Record a salary disbursement against a payroll line.
    HR can pay in multiple parts — each call records one payment.
    """
    line = await db.get(PayrollLine, line_id)
    if not line:
        raise HTTPException(status_code=404, detail="Payroll line not found")

    payable = line.net_pay - line.advance_deduction
    remaining = payable - line.disbursed_amount
    if obj_in.amount > remaining + 0.01:
        raise HTTPException(
            status_code=400,
            detail=f"Amount {obj_in.amount:.2f} exceeds remaining "
                   f"payable of {remaining:.2f}"
        )

    disbursement = SalaryDisbursement(
        payroll_line_id=line_id,
        amount=obj_in.amount,
        payment_mode=obj_in.payment_mode,
        reference=obj_in.reference,
        remarks=obj_in.remarks,
        disbursed_by_id=current_user.id,
    )
    db.add(disbursement)

    line.disbursed_amount = round(line.disbursed_amount + obj_in.amount, 2)
    line.held_amount = round(payable - line.disbursed_amount, 2)

    _log_audit(
        db, current_user.id, "RECORD_DISBURSEMENT", "payroll_line",
        str(line_id),
        {"amount": obj_in.amount, "total_disbursed": line.disbursed_amount},
        request,
    )
    await db.commit()
    await db.refresh(disbursement)

    result = SalaryDisbursementRead.model_validate(disbursement)
    result.disbursed_by_name = current_user.full_name
    return result


@router.get(
    "/payroll/lines/{line_id}/disbursements",
    response_model=List[SalaryDisbursementRead],
)
async def list_disbursements(
    line_id: int,
    db: deps.DBDep,
    current_user: User = Depends(deps.check_permissions([HR_PAYROLL_RUN])),
) -> Any:
    """List all disbursement records for a payroll line."""
    res = await db.execute(
        select(SalaryDisbursement, User.full_name)
        .join(User, SalaryDisbursement.disbursed_by_id == User.id)
        .where(SalaryDisbursement.payroll_line_id == line_id)
        .order_by(SalaryDisbursement.disbursed_at.asc())
    )
    result = []
    for d, name in res.all():
        item = SalaryDisbursementRead.model_validate(d)
        item.disbursed_by_name = name
        result.append(item)
    return result
