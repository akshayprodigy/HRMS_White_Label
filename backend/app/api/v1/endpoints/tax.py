"""TDS / Form 16 / Form 24Q / Gratuity endpoints.

Generators READ finalized payroll only. They never recompute salary,
never modify Employee, payroll, salary_calculator, the Part-1 statutory
module, or the revision module. The exit-time gratuity SNAPSHOT is
attached to the existing Resignation row (FK), not recreated.
"""
import io
import json
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, func, select
from sqlalchemy.orm import selectinload

from app.api import deps
from app.api.v1.endpoints.hr import log_audit
from app.models.employee import Employee
from app.models.exit_management import Resignation
from app.models.hr import EmployeeLetter, LetterType
from app.models.payroll import (
    PayrollLine, PayrollRun, PayrollRunStatus,
)
from app.models.tax import (
    DeclarationStatus, EmployeeTaxDeclaration, Form16Record, Form16Status,
    Form24QExport, Form24QStatus, GratuityComputation, GratuityConfig,
    GratuityStatus, SectionLimitConfig, TaxRegime, TaxSlabConfig,
)
from app.models.user import User
from app.schemas.tax import (
    CompanyLiabilityReport, DeclarationCreate, DeclarationRead,
    DeclarationUpdate, ExitGratuityResult, Form16GenerateRequest,
    Form16GenerateResult, Form16Read, Form16TracesUpload,
    Form24QGenerateRequest, Form24QRead, GratuityConfigCreate,
    GratuityConfigRead, GratuityConfigUpdate, GratuityResultRead,
    RegimeComparisonRead, SectionLimitCreate, SectionLimitRead,
    SectionLimitUpdate, TaxComputationRead, TaxSlabConfigCreate,
    TaxSlabConfigRead, TaxSlabConfigUpdate, TDSReconciliationReport,
    TDSReconRow, VerifyAction,
)
from app.services.form24q import (
    Form24QAnnexureIRow, Form24QAnnexureIIRow, quarter_end_date,
    render_annexure_i_csv, render_annexure_ii_csv, summarize_annexure_i,
)
from app.services.gratuity import (
    LiabilityRow, aggregate_company_liability, compute_gratuity,
)
from app.services.letter_pdf import generate_letter
from app.services.tds import (
    DEFAULT_REGIME, cap_chapter_via, compare_regimes, compute_annual_tax,
    compute_monthly_tds, fy_for_date, fy_remaining_months_inclusive,
    pick_slab_config_for_fy, quarter_for_month, reconcile_tds_for_employee,
    section_limits_map,
)


router = APIRouter()

PERM_CONFIG_WRITE = "tax config write"
PERM_VERIFY = "tax declaration verify"
PERM_GENERATE = "tax generate"            # Form 16, 24Q, recon
PERM_VIEW_ALL = "tax view all"
PERM_GRATUITY_VIEW = "gratuity view"


# =====================================================================
# shared helpers
# =====================================================================


async def _current_employee(db, user: User) -> Optional[Employee]:
    return (await db.execute(
        select(Employee).where(Employee.user_id == user.id)
    )).scalar_one_or_none()


async def _resolve_slab_config(db, fy: str) -> Optional[TaxSlabConfig]:
    rows = (await db.execute(
        select(TaxSlabConfig).where(TaxSlabConfig.is_active.is_(True))
    )).scalars().all()
    return pick_slab_config_for_fy(rows, fy)


async def _resolve_section_limits(db, fy: str) -> Dict[str, SectionLimitConfig]:
    rows = (await db.execute(
        select(SectionLimitConfig).where(SectionLimitConfig.fy == fy)
    )).scalars().all()
    return section_limits_map(rows, fy)


async def _resolve_gratuity_config(db) -> Optional[GratuityConfig]:
    return (await db.execute(
        select(GratuityConfig).where(GratuityConfig.is_active.is_(True))
        .order_by(GratuityConfig.effective_from.desc()).limit(1)
    )).scalar_one_or_none()


def _user_can_view_all(user: User) -> bool:
    if user.is_superuser:
        return True
    role_names = [(r.name or "").lower() for r in user.roles or []]
    if any(n in role_names for n in ("hr", "super admin", "admin", "ceo")):
        return True
    for role in user.roles or []:
        for perm in role.permissions or []:
            if (perm.name or "") in (
                PERM_VIEW_ALL, PERM_VERIFY, PERM_GENERATE, PERM_CONFIG_WRITE,
                PERM_GRATUITY_VIEW,
            ):
                return True
    return False


def _fy_period_window(fy: str) -> tuple[date, date]:
    """Calendar dates that bracket the FY label "24-25"."""
    a, b = fy.split("-")
    start_year = 2000 + int(a)
    end_year = 2000 + int(b)
    return date(start_year, 4, 1), date(end_year, 3, 31)


async def _payroll_lines_for_employee_fy(
    db, employee_id: int, fy: str,
) -> List[tuple[PayrollRun, PayrollLine]]:
    """All finalized PayrollLine rows for one employee inside the FY."""
    emp = await db.get(Employee, employee_id)
    if emp is None:
        return []
    period_start, period_end = _fy_period_window(fy)
    # Filter by run.year/month within FY range.
    stmt = (
        select(PayrollRun, PayrollLine)
        .join(PayrollLine, PayrollLine.payroll_run_id == PayrollRun.id)
        .where(and_(
            PayrollLine.user_id == emp.user_id,
            PayrollRun.status.in_([
                PayrollRunStatus.FINALIZED, PayrollRunStatus.PUBLISHED,
            ]),
        ))
        .order_by(PayrollRun.year, PayrollRun.month)
    )
    rows = (await db.execute(stmt)).all()
    out = []
    for run, line in rows:
        run_first = date(run.year, run.month, 1)
        if period_start <= run_first <= period_end:
            out.append((run, line))
    return out


def _annual_aggregate(lines: List[tuple[PayrollRun, PayrollLine]]) -> dict:
    """Roll FY's monthly lines into annual totals used by projection."""
    gross = 0.0
    basic = 0.0
    hra_received = 0.0
    tds = 0.0
    for _, line in lines:
        al = line.allowances or {}
        ded = line.deductions or {}
        gross += float(line.gross_pay or 0.0)
        basic += float(al.get("basic_salary_actual", line.base_salary or 0.0))
        hra_received += float(al.get("hra_actual", 0.0))
        tds += float(ded.get("tds", 0.0))
    return {
        "gross": round(gross, 2),
        "basic": round(basic, 2),
        "hra_received": round(hra_received, 2),
        "tds": round(tds, 2),
    }


# =====================================================================
# TaxSlabConfig CRUD
# =====================================================================


@router.get("/configs", response_model=List[TaxSlabConfigRead])
async def list_tax_configs(
    db: deps.DBDep,
    current_user: User = Depends(deps.check_permissions([PERM_CONFIG_WRITE])),
) -> Any:
    return list((await db.execute(
        select(TaxSlabConfig).order_by(TaxSlabConfig.fy.desc())
    )).scalars().all())


@router.post("/configs", response_model=TaxSlabConfigRead)
async def create_tax_config(
    payload: TaxSlabConfigCreate,
    db: deps.DBDep, request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_CONFIG_WRITE])),
) -> Any:
    obj = TaxSlabConfig(**payload.model_dump())
    db.add(obj)
    await db.flush()
    await log_audit(
        db, current_user.id, "TAX_CONFIG_CREATE", "tax_slab_config",
        str(obj.id), payload.model_dump(), request,
    )
    await db.commit()
    await db.refresh(obj)
    return obj


@router.patch("/configs/{cid}", response_model=TaxSlabConfigRead)
async def update_tax_config(
    cid: int, payload: TaxSlabConfigUpdate,
    db: deps.DBDep, request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_CONFIG_WRITE])),
) -> Any:
    obj = await db.get(TaxSlabConfig, cid)
    if obj is None:
        raise HTTPException(404, "Config not found")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(obj, k, v)
    await log_audit(
        db, current_user.id, "TAX_CONFIG_UPDATE", "tax_slab_config",
        str(cid), data, request,
    )
    await db.commit()
    await db.refresh(obj)
    return obj


# =====================================================================
# SectionLimitConfig CRUD
# =====================================================================


@router.get("/section-limits", response_model=List[SectionLimitRead])
async def list_section_limits(
    db: deps.DBDep,
    fy: Optional[str] = Query(None),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    stmt = select(SectionLimitConfig)
    if fy:
        stmt = stmt.where(SectionLimitConfig.fy == fy)
    return list((await db.execute(
        stmt.order_by(SectionLimitConfig.fy.desc(), SectionLimitConfig.section_code)
    )).scalars().all())


@router.post("/section-limits", response_model=SectionLimitRead)
async def create_section_limit(
    payload: SectionLimitCreate,
    db: deps.DBDep, request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_CONFIG_WRITE])),
) -> Any:
    obj = SectionLimitConfig(**payload.model_dump())
    db.add(obj)
    await db.flush()
    await log_audit(
        db, current_user.id, "SECTION_LIMIT_CREATE", "section_limit_config",
        str(obj.id), payload.model_dump(), request,
    )
    await db.commit()
    await db.refresh(obj)
    return obj


@router.patch("/section-limits/{sid}", response_model=SectionLimitRead)
async def update_section_limit(
    sid: int, payload: SectionLimitUpdate,
    db: deps.DBDep, request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_CONFIG_WRITE])),
) -> Any:
    obj = await db.get(SectionLimitConfig, sid)
    if obj is None:
        raise HTTPException(404, "Limit not found")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(obj, k, v)
    await log_audit(
        db, current_user.id, "SECTION_LIMIT_UPDATE", "section_limit_config",
        str(sid), data, request,
    )
    await db.commit()
    await db.refresh(obj)
    return obj


# =====================================================================
# GratuityConfig CRUD
# =====================================================================


@router.get("/gratuity-configs", response_model=List[GratuityConfigRead])
async def list_gratuity_configs(
    db: deps.DBDep,
    current_user: User = Depends(deps.check_permissions([PERM_CONFIG_WRITE])),
) -> Any:
    return list((await db.execute(
        select(GratuityConfig).order_by(GratuityConfig.effective_from.desc())
    )).scalars().all())


@router.post("/gratuity-configs", response_model=GratuityConfigRead)
async def create_gratuity_config(
    payload: GratuityConfigCreate,
    db: deps.DBDep, request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_CONFIG_WRITE])),
) -> Any:
    obj = GratuityConfig(**payload.model_dump())
    db.add(obj)
    await db.flush()
    await log_audit(
        db, current_user.id, "GRATUITY_CONFIG_CREATE", "gratuity_config",
        str(obj.id), payload.model_dump(mode="json"), request,
    )
    await db.commit()
    await db.refresh(obj)
    return obj


@router.patch("/gratuity-configs/{cid}", response_model=GratuityConfigRead)
async def update_gratuity_config(
    cid: int, payload: GratuityConfigUpdate,
    db: deps.DBDep, request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_CONFIG_WRITE])),
) -> Any:
    obj = await db.get(GratuityConfig, cid)
    if obj is None:
        raise HTTPException(404, "Config not found")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(obj, k, v)
    await log_audit(
        db, current_user.id, "GRATUITY_CONFIG_UPDATE", "gratuity_config",
        str(cid), data, request,
    )
    await db.commit()
    await db.refresh(obj)
    return obj


# =====================================================================
# EmployeeTaxDeclaration
# =====================================================================


async def _enrich_decl(db, d: EmployeeTaxDeclaration) -> DeclarationRead:
    emp = await db.get(Employee, d.employee_id, options=[
        selectinload(Employee.user),
    ])
    data = {c.name: getattr(d, c.name) for c in d.__table__.columns}
    data["employee_full_name"] = emp.user.full_name if emp and emp.user else None
    data["employee_code"] = emp.employee_id if emp else None
    return DeclarationRead.model_validate(data)


@router.get("/declarations", response_model=List[DeclarationRead])
async def list_declarations(
    db: deps.DBDep,
    fy: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    employee_id: Optional[int] = Query(None),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    stmt = select(EmployeeTaxDeclaration)
    if fy:
        stmt = stmt.where(EmployeeTaxDeclaration.fy == fy)
    if status:
        stmt = stmt.where(EmployeeTaxDeclaration.status == status)
    if not _user_can_view_all(current_user):
        emp = await _current_employee(db, current_user)
        if emp is None:
            return []
        stmt = stmt.where(EmployeeTaxDeclaration.employee_id == emp.id)
    elif employee_id is not None:
        stmt = stmt.where(EmployeeTaxDeclaration.employee_id == employee_id)
    stmt = stmt.order_by(EmployeeTaxDeclaration.fy.desc())
    rows = (await db.execute(stmt)).scalars().all()
    return [await _enrich_decl(db, d) for d in rows]


@router.get("/declarations/my", response_model=List[DeclarationRead])
async def my_declarations(
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    emp = await _current_employee(db, current_user)
    if emp is None:
        return []
    rows = (await db.execute(
        select(EmployeeTaxDeclaration).where(
            EmployeeTaxDeclaration.employee_id == emp.id
        ).order_by(EmployeeTaxDeclaration.fy.desc())
    )).scalars().all()
    return [await _enrich_decl(db, d) for d in rows]


@router.put("/declarations", response_model=DeclarationRead)
async def upsert_declaration(
    payload: DeclarationCreate,
    db: deps.DBDep, request: Request,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Employee submits or updates own declaration (or HR upserts on
    behalf of an employee with verify permission)."""
    emp = await db.get(Employee, payload.employee_id)
    if emp is None:
        raise HTTPException(404, "Employee not found")
    if (
        emp.user_id != current_user.id
        and not (_user_can_view_all(current_user))
    ):
        raise HTTPException(403, "Cannot edit another employee's declaration")

    existing = (await db.execute(
        select(EmployeeTaxDeclaration).where(and_(
            EmployeeTaxDeclaration.employee_id == payload.employee_id,
            EmployeeTaxDeclaration.fy == payload.fy,
        ))
    )).scalar_one_or_none()

    data = payload.model_dump()
    if existing is None:
        d = EmployeeTaxDeclaration(
            **data, status=DeclarationStatus.SUBMITTED,
            submitted_at=datetime.now(timezone.utc),
        )
        db.add(d)
    else:
        if existing.status == DeclarationStatus.VERIFIED:
            raise HTTPException(
                400,
                "Declaration already VERIFIED. Ask HR to reset before editing.",
            )
        for k, v in data.items():
            setattr(existing, k, v)
        existing.status = DeclarationStatus.SUBMITTED
        existing.submitted_at = datetime.now(timezone.utc)
        d = existing

    await db.flush()
    await log_audit(
        db, current_user.id, "DECLARATION_SUBMIT", "employee_tax_declaration",
        str(d.id), {"fy": d.fy, "regime": d.regime}, request,
    )
    await db.commit()
    await db.refresh(d)
    return await _enrich_decl(db, d)


@router.post("/declarations/{did}/action", response_model=DeclarationRead)
async def verify_declaration(
    did: int, payload: VerifyAction,
    db: deps.DBDep, request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_VERIFY])),
) -> Any:
    d = await db.get(EmployeeTaxDeclaration, did)
    if d is None:
        raise HTTPException(404, "Declaration not found")
    if d.status not in (DeclarationStatus.SUBMITTED, DeclarationStatus.REJECTED):
        raise HTTPException(400, f"Not actionable in status {d.status}")
    now = datetime.now(timezone.utc)
    if payload.action == "verify":
        d.status = DeclarationStatus.VERIFIED
        d.verified_at = now
        d.verified_by_id = current_user.id
        d.rejection_reason = None
    else:
        d.status = DeclarationStatus.REJECTED
        d.rejection_reason = payload.rejection_reason
    await log_audit(
        db, current_user.id,
        "DECLARATION_VERIFY" if payload.action == "verify" else "DECLARATION_REJECT",
        "employee_tax_declaration",
        str(did), {"reason": payload.rejection_reason}, request,
    )
    await db.commit()
    await db.refresh(d)
    return await _enrich_decl(db, d)


# =====================================================================
# TDS projection (employee comparison) + reconciliation
# =====================================================================


@router.get(
    "/projection/{employee_id}",
    response_model=RegimeComparisonRead,
)
async def project_for_employee(
    employee_id: int, db: deps.DBDep,
    fy: Optional[str] = Query(None),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Project annual tax for an employee under BOTH regimes; surface the
    cheaper one. Reads finalized payroll for the FY to build the gross.
    """
    emp = await db.get(Employee, employee_id, options=[
        selectinload(Employee.user),
    ])
    if emp is None:
        raise HTTPException(404, "Employee not found")
    if emp.user_id != current_user.id and not _user_can_view_all(current_user):
        raise HTTPException(403, "Not authorized")

    fy = fy or fy_for_date(date.today())
    slab = await _resolve_slab_config(db, fy)
    if slab is None:
        raise HTTPException(400, "No TaxSlabConfig configured")

    decl = (await db.execute(
        select(EmployeeTaxDeclaration).where(and_(
            EmployeeTaxDeclaration.employee_id == emp.id,
            EmployeeTaxDeclaration.fy == fy,
        ))
    )).scalar_one_or_none()

    limits = await _resolve_section_limits(db, fy)

    lines = await _payroll_lines_for_employee_fy(db, emp.id, fy)
    agg = _annual_aggregate(lines)
    # Project full year: if employee has 6 months of data we extrapolate
    # the rest pro-rata using the latest month's gross.
    months_with_data = len(lines)
    if months_with_data > 0 and months_with_data < 12:
        last_month_gross = (
            float(lines[-1][1].gross_pay or 0.0) if lines else 0.0
        )
        annualized_gross = agg["gross"] + last_month_gross * (12 - months_with_data)
        # similarly for basic + HRA
        last_al = lines[-1][1].allowances or {}
        last_basic = float(last_al.get(
            "basic_salary_actual", lines[-1][1].base_salary or 0.0,
        ))
        last_hra = float(last_al.get("hra_actual", 0.0))
        annualized_basic = agg["basic"] + last_basic * (12 - months_with_data)
        annualized_hra = agg["hra_received"] + last_hra * (12 - months_with_data)
    else:
        annualized_gross = agg["gross"]
        annualized_basic = agg["basic"]
        annualized_hra = agg["hra_received"]

    chap_via = (
        cap_chapter_via(decl.declarations_json, limits) if decl else 0.0
    )
    rent_annual = (decl.monthly_rent_paid * 12.0) if decl else 0.0
    metro = decl.rented_in_metro if decl else False
    other_income = decl.other_income_annual if decl else 0.0
    prev_employer = decl.previous_employer_income if decl else 0.0

    cmp_result = compare_regimes(
        gross_salary_annual=annualized_gross,
        basic_da_annual=annualized_basic,
        hra_received_annual=annualized_hra,
        rent_paid_annual=rent_annual, metro=metro,
        chapter_via_deductions=chap_via,
        other_income_annual=other_income,
        previous_employer_income=prev_employer,
        slab_config=slab,
    )

    return RegimeComparisonRead(
        fy=fy, employee_id=emp.id,
        employee_full_name=emp.user.full_name if emp.user else None,
        old=TaxComputationRead(**cmp_result.old.__dict__),
        new=TaxComputationRead(**cmp_result.new.__dict__),
        better_regime=cmp_result.better_regime,
        saving=cmp_result.saving,
        declared_regime=decl.regime if decl else None,
    )


@router.get(
    "/reconciliation/{fy}",
    response_model=TDSReconciliationReport,
)
async def reconcile_fy(
    fy: str, db: deps.DBDep,
    as_of: Optional[date] = Query(None),
    current_user: User = Depends(deps.check_permissions([PERM_GENERATE])),
) -> Any:
    """The headline Q4 catch-up report. Per-employee required-monthly
    vs last-month-deducted; flags under/over.
    """
    slab = await _resolve_slab_config(db, fy)
    if slab is None:
        raise HTTPException(400, "No TaxSlabConfig configured for this FY")
    cutoff = as_of or date.today()
    months_remaining = fy_remaining_months_inclusive(cutoff.month)

    # All active employees with finalized payroll inside the FY.
    period_start, period_end = _fy_period_window(fy)
    emp_user_ids = list((await db.execute(
        select(PayrollLine.user_id).join(
            PayrollRun, PayrollLine.payroll_run_id == PayrollRun.id,
        ).where(and_(
            PayrollRun.status.in_([
                PayrollRunStatus.FINALIZED, PayrollRunStatus.PUBLISHED,
            ]),
            PayrollRun.year >= period_start.year,
            PayrollRun.year <= period_end.year,
        )).distinct()
    )).scalars().all())
    emps = list((await db.execute(
        select(Employee).where(Employee.user_id.in_(emp_user_ids))
        .options(selectinload(Employee.user))
    )).scalars().all())

    rows: List[TDSReconRow] = []
    under = over = ok = 0

    for emp in emps:
        lines = await _payroll_lines_for_employee_fy(db, emp.id, fy)
        if not lines:
            continue
        agg = _annual_aggregate(lines)
        last_run, last_line = lines[-1]
        last_tds = float((last_line.deductions or {}).get("tds", 0.0))

        # Re-project annual tax for this employee using the declared
        # regime (or new by default).
        decl = (await db.execute(
            select(EmployeeTaxDeclaration).where(and_(
                EmployeeTaxDeclaration.employee_id == emp.id,
                EmployeeTaxDeclaration.fy == fy,
            ))
        )).scalar_one_or_none()
        regime = (decl.regime if decl else DEFAULT_REGIME)
        limits = await _resolve_section_limits(db, fy)
        chap_via = (
            cap_chapter_via(decl.declarations_json, limits) if decl else 0.0
        )
        months_with_data = len(lines)
        if 0 < months_with_data < 12:
            last_basic_full = float(
                (last_line.allowances or {}).get(
                    "basic_salary_actual", last_line.base_salary or 0.0,
                )
            )
            last_hra_full = float((last_line.allowances or {}).get("hra_actual", 0.0))
            annualized_gross = agg["gross"] + float(last_line.gross_pay or 0.0) * (12 - months_with_data)
            annualized_basic = agg["basic"] + last_basic_full * (12 - months_with_data)
            annualized_hra = agg["hra_received"] + last_hra_full * (12 - months_with_data)
        else:
            annualized_gross = agg["gross"]
            annualized_basic = agg["basic"]
            annualized_hra = agg["hra_received"]

        proj = compute_annual_tax(
            regime=regime,
            gross_salary_annual=annualized_gross,
            basic_da_annual=annualized_basic,
            hra_received_annual=annualized_hra,
            rent_paid_annual=(decl.monthly_rent_paid * 12.0) if decl else 0.0,
            metro=(decl.rented_in_metro if decl else False),
            chapter_via_deductions=chap_via,
            other_income_annual=(decl.other_income_annual if decl else 0.0),
            previous_employer_income=(decl.previous_employer_income if decl else 0.0),
            slab_config=slab,
        )

        row = reconcile_tds_for_employee(
            projected_annual_tax=proj.total_tax,
            ytd_tds=agg["tds"],
            months_remaining=months_remaining,
            last_month_tds=last_tds,
            user_id=emp.user_id,
            employee_code=emp.employee_id,
            name=emp.user.full_name if emp.user else None,
        )
        rows.append(TDSReconRow.model_validate(row.__dict__))
        if row.status == "under": under += 1
        elif row.status == "over": over += 1
        else: ok += 1

    rows.sort(key=lambda r: r.catch_up_amount, reverse=True)
    return TDSReconciliationReport(
        fy=fy, as_of=cutoff, rows=rows,
        total_under=under, total_over=over, total_ok=ok,
    )


# =====================================================================
# Form 16 — Part B generate, Part A upload, paired download
# =====================================================================


async def _enrich_form16(db, f: Form16Record) -> Form16Read:
    emp = await db.get(Employee, f.employee_id, options=[
        selectinload(Employee.user),
    ])
    data = {c.name: getattr(f, c.name) for c in f.__table__.columns}
    data["employee_full_name"] = emp.user.full_name if emp and emp.user else None
    data["employee_code"] = emp.employee_id if emp else None
    data["pan"] = emp.pan_number if emp else None
    return Form16Read.model_validate(data)


async def _generate_form16_part_b(
    db, *, emp: Employee, fy: str, slab: TaxSlabConfig,
    actor_id: int,
) -> Form16Record:
    user = (await db.execute(
        select(User).where(User.id == emp.user_id)
    )).scalar_one_or_none()
    decl = (await db.execute(
        select(EmployeeTaxDeclaration).where(and_(
            EmployeeTaxDeclaration.employee_id == emp.id,
            EmployeeTaxDeclaration.fy == fy,
        ))
    )).scalar_one_or_none()
    limits = await _resolve_section_limits(db, fy)

    lines = await _payroll_lines_for_employee_fy(db, emp.id, fy)
    agg = _annual_aggregate(lines)
    regime = decl.regime if decl else DEFAULT_REGIME
    chap_via = (
        cap_chapter_via(decl.declarations_json, limits) if decl else 0.0
    )
    proj = compute_annual_tax(
        regime=regime,
        gross_salary_annual=agg["gross"],
        basic_da_annual=agg["basic"],
        hra_received_annual=agg["hra_received"],
        rent_paid_annual=(decl.monthly_rent_paid * 12.0) if decl else 0.0,
        metro=(decl.rented_in_metro if decl else False),
        chapter_via_deductions=chap_via,
        other_income_annual=(decl.other_income_annual if decl else 0.0),
        previous_employer_income=(decl.previous_employer_income if decl else 0.0),
        slab_config=slab,
    )

    missing_pan = not (emp.pan_number and emp.pan_number.strip())
    pdf_data: Dict[str, Any] = {
        "fy": fy,
        "date": date.today().isoformat(),
        "employee_name": user.full_name if user else "",
        "employee_code": emp.employee_id,
        "pan": emp.pan_number or "",
        "designation": emp.designation or "",
        "employer_tan": "",  # would come from Part-1 EmployerIdentifier;
                             # left blank to avoid cross-module coupling.
        "regime": regime,
        "missing_pan_flag": missing_pan,
        "gross_salary_annual": agg["gross"],
        "previous_employer_income": proj.previous_employer_income,
        "other_income": proj.other_income,
        "hra_exemption": proj.hra_exemption,
        "standard_deduction": proj.standard_deduction,
        "chapter_via_deductions": proj.chapter_via_deductions,
        "taxable_income": proj.taxable_income,
        "tax_on_slabs": proj.tax_on_slabs,
        "rebate_87a": proj.rebate_87a,
        "surcharge": proj.surcharge,
        "cess": proj.cess,
        "total_tax": proj.total_tax,
        "ytd_tds": agg["tds"],
        "previous_employer_tds": (
            decl.previous_employer_tds if decl else 0.0
        ),
        "net_tax_payable": round(
            proj.total_tax - agg["tds"]
            - (decl.previous_employer_tds if decl else 0.0), 2,
        ),
    }

    # Upsert Form16Record.
    existing = (await db.execute(
        select(Form16Record).where(and_(
            Form16Record.employee_id == emp.id,
            Form16Record.fy == fy,
        ))
    )).scalar_one_or_none()
    if existing is None:
        count_q = (await db.execute(
            select(func.count(Form16Record.id))
        )).scalar() or 0
        ref_number = (
            f"UEIPL/FORM16-PART-B/{fy.replace('-', '')}/{count_q + 1:04d}"
        )
        record = Form16Record(
            employee_id=emp.id, fy=fy, reference_number=ref_number,
            generated_by_id=actor_id, missing_pan_flag=missing_pan,
        )
        db.add(record)
        await db.flush()
    else:
        record = existing
        ref_number = record.reference_number or "regen"
    pdf_data["reference_number"] = ref_number

    from app.services.letter_pdf import LETTER_GENERATORS
    pdf_bytes = LETTER_GENERATORS["form16_part_b"](pdf_data)

    file_url = f"/tax/form16/part_b/{ref_number.replace('/', '_')}.pdf"
    record.part_b_url = file_url
    record.part_b_data = {**pdf_data, "_bytes_hex": pdf_bytes.hex()}
    record.part_b_generated_at = datetime.now(timezone.utc)
    record.missing_pan_flag = missing_pan
    record.generated_by_id = actor_id
    # status transitions: keep "ready" if Part A already uploaded, else
    # pending_part_a (the default on create).
    if record.part_a_url:
        record.status = Form16Status.READY

    return record


@router.post("/form16/generate", response_model=Form16GenerateResult)
async def generate_form16(
    payload: Form16GenerateRequest,
    db: deps.DBDep, request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_GENERATE])),
) -> Any:
    slab = await _resolve_slab_config(db, payload.fy)
    if slab is None:
        raise HTTPException(400, "No TaxSlabConfig configured for this FY")

    if payload.employee_ids:
        emps = list((await db.execute(
            select(Employee).where(Employee.id.in_(payload.employee_ids))
        )).scalars().all())
    else:
        emps = list((await db.execute(
            select(Employee).where(Employee.status == "active")
        )).scalars().all())

    generated = skipped_no_pan = skipped_no_payroll = 0
    records: List[Form16Record] = []
    for emp in emps:
        lines = await _payroll_lines_for_employee_fy(db, emp.id, payload.fy)
        if not lines:
            skipped_no_payroll += 1
            continue
        rec = await _generate_form16_part_b(
            db, emp=emp, fy=payload.fy, slab=slab, actor_id=current_user.id,
        )
        if rec.missing_pan_flag:
            skipped_no_pan += 1   # still generated, but flagged
        generated += 1
        records.append(rec)

    await log_audit(
        db, current_user.id, "FORM16_GENERATE", "form16_record",
        f"fy:{payload.fy}",
        {
            "fy": payload.fy, "generated": generated,
            "skipped_no_pan": skipped_no_pan,
            "skipped_no_payroll": skipped_no_payroll,
        },
        request,
    )
    await db.commit()
    for r in records:
        await db.refresh(r)
    return Form16GenerateResult(
        fy=payload.fy, generated=generated,
        skipped_no_pan=skipped_no_pan,
        skipped_no_payroll=skipped_no_payroll,
        records=[await _enrich_form16(db, r) for r in records],
    )


@router.get("/form16", response_model=List[Form16Read])
async def list_form16(
    db: deps.DBDep,
    fy: Optional[str] = Query(None),
    employee_id: Optional[int] = Query(None),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    stmt = select(Form16Record)
    if fy: stmt = stmt.where(Form16Record.fy == fy)
    if not _user_can_view_all(current_user):
        emp = await _current_employee(db, current_user)
        if emp is None: return []
        stmt = stmt.where(Form16Record.employee_id == emp.id)
    elif employee_id is not None:
        stmt = stmt.where(Form16Record.employee_id == employee_id)
    rows = (await db.execute(stmt.order_by(Form16Record.fy.desc()))).scalars().all()
    return [await _enrich_form16(db, r) for r in rows]


@router.post("/form16/{rid}/upload-part-a", response_model=Form16Read)
async def upload_part_a(
    rid: int, payload: Form16TracesUpload,
    db: deps.DBDep, request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_GENERATE])),
) -> Any:
    """HR records the TRACES-issued Part A URL + certificate number.

    We don't host the file — we just register where it lives (e.g.
    S3 / file-share path) so the paired-download endpoint can serve
    both halves together.
    """
    rec = await db.get(Form16Record, rid)
    if rec is None:
        raise HTTPException(404, "Form16 record not found")
    rec.part_a_url = payload.part_a_url
    rec.traces_certificate_number = payload.traces_certificate_number
    rec.part_a_uploaded_at = datetime.now(timezone.utc)
    if rec.part_b_url:
        rec.status = Form16Status.READY
    await log_audit(
        db, current_user.id, "FORM16_UPLOAD_PART_A", "form16_record",
        str(rid),
        {"traces": payload.traces_certificate_number}, request,
    )
    await db.commit()
    await db.refresh(rec)
    return await _enrich_form16(db, rec)


@router.post("/form16/{rid}/issue", response_model=Form16Read)
async def issue_form16(
    rid: int,
    db: deps.DBDep, request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_GENERATE])),
) -> Any:
    rec = await db.get(Form16Record, rid)
    if rec is None:
        raise HTTPException(404, "Form16 record not found")
    if rec.status != Form16Status.READY:
        raise HTTPException(
            400,
            f"Cannot issue — status is {rec.status}. Need both Part A and Part B.",
        )
    rec.status = Form16Status.ISSUED
    rec.issued_at = datetime.now(timezone.utc)
    await log_audit(
        db, current_user.id, "FORM16_ISSUE", "form16_record",
        str(rid), {}, request,
    )
    await db.commit()
    await db.refresh(rec)
    return await _enrich_form16(db, rec)


@router.get("/form16/{rid}/download")
async def download_form16(
    rid: int, db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Return the generated Part B PDF bytes. Employee can download own;
    HR/Super Admin can download anyone's.
    """
    rec = await db.get(Form16Record, rid)
    if rec is None:
        raise HTTPException(404, "Form16 record not found")
    emp = await db.get(Employee, rec.employee_id)
    if (
        emp is not None
        and emp.user_id != current_user.id
        and not _user_can_view_all(current_user)
    ):
        raise HTTPException(403, "Not authorized")

    data = rec.part_b_data or {}
    hex_bytes = data.get("_bytes_hex")
    if not hex_bytes:
        raise HTTPException(410, "Part B bytes missing — regenerate")
    fname = (rec.reference_number or f"form16_{rid}").replace("/", "_") + ".pdf"
    return StreamingResponse(
        io.BytesIO(bytes.fromhex(hex_bytes)),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


# =====================================================================
# Form 24Q quarterly export
# =====================================================================


async def _build_24q_annexure_i(
    db, *, fy: str, quarter: int,
) -> tuple[List[Form24QAnnexureIRow], List[Employee]]:
    """One row per employee for the quarter. Sums salary + TDS across
    the three months of the quarter.
    """
    # Map quarter → calendar months
    fy_a, fy_b = fy.split("-")
    start_year = 2000 + int(fy_a)
    end_year = 2000 + int(fy_b)
    if quarter == 1:
        months = [(start_year, 4), (start_year, 5), (start_year, 6)]
    elif quarter == 2:
        months = [(start_year, 7), (start_year, 8), (start_year, 9)]
    elif quarter == 3:
        months = [(start_year, 10), (start_year, 11), (start_year, 12)]
    else:
        months = [(end_year, 1), (end_year, 2), (end_year, 3)]

    runs = list((await db.execute(
        select(PayrollRun).where(and_(
            PayrollRun.status.in_([
                PayrollRunStatus.FINALIZED, PayrollRunStatus.PUBLISHED,
            ]),
        ))
    )).scalars().all())
    runs_in_q = [r for r in runs if (r.year, r.month) in months]
    if not runs_in_q:
        return [], []

    line_rows = list((await db.execute(
        select(PayrollLine).where(
            PayrollLine.payroll_run_id.in_({r.id for r in runs_in_q})
        )
    )).scalars().all())

    # Aggregate by user_id.
    by_user: Dict[int, Dict[str, float]] = {}
    for ln in line_rows:
        d = by_user.setdefault(ln.user_id, {"paid": 0.0, "tds": 0.0})
        d["paid"] += float(ln.gross_pay or 0.0)
        d["tds"] += float((ln.deductions or {}).get("tds", 0.0))

    user_ids = list(by_user.keys())
    emps = list((await db.execute(
        select(Employee).where(Employee.user_id.in_(user_ids))
        .options(selectinload(Employee.user))
    )).scalars().all())
    emp_by_user = {e.user_id: e for e in emps}

    rows: List[Form24QAnnexureIRow] = []
    for uid, agg in by_user.items():
        emp = emp_by_user.get(uid)
        if emp is None:
            continue
        rows.append(Form24QAnnexureIRow(
            pan=(emp.pan_number or "").strip(),
            name=emp.user.full_name if emp.user else "",
            paid_amount=agg["paid"], tds_deducted=agg["tds"],
            tds_deposited=agg["tds"],
            deduction_date=quarter_end_date(fy, quarter),
        ))
    return rows, emps


@router.post("/form24q/generate", response_model=Form24QRead)
async def generate_24q(
    payload: Form24QGenerateRequest,
    db: deps.DBDep, request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_GENERATE])),
) -> Any:
    rows, _ = await _build_24q_annexure_i(
        db, fy=payload.fy, quarter=payload.quarter,
    )
    csv_text = render_annexure_i_csv(rows)
    summary = summarize_annexure_i(rows)
    fname = f"FORM24Q_{payload.fy.replace('-', '')}_Q{payload.quarter}.csv"

    existing = (await db.execute(
        select(Form24QExport).where(and_(
            Form24QExport.fy == payload.fy,
            Form24QExport.quarter == payload.quarter,
        ))
    )).scalar_one_or_none()
    if existing and existing.status in (
        Form24QStatus.SUBMITTED, Form24QStatus.ACCEPTED,
    ):
        raise HTTPException(
            400,
            f"24Q for {payload.fy} Q{payload.quarter} is already {existing.status}. "
            "Mark REJECTED before re-issuing.",
        )

    bytes_hex = csv_text.encode("utf-8").hex()
    file_url = f"/tax/24q/{fname}"
    if existing is None:
        obj = Form24QExport(
            fy=payload.fy, quarter=payload.quarter,
            file_url=file_url, file_name=fname,
            summary={**summary, "_bytes_hex": bytes_hex},
            status=Form24QStatus.GENERATED,
            generated_at=datetime.now(timezone.utc),
            generated_by_id=current_user.id,
        )
        db.add(obj)
    else:
        obj = existing
        obj.file_url = file_url
        obj.file_name = fname
        obj.summary = {**summary, "_bytes_hex": bytes_hex}
        obj.status = Form24QStatus.GENERATED
        obj.generated_at = datetime.now(timezone.utc)
        obj.generated_by_id = current_user.id

    await db.flush()
    await log_audit(
        db, current_user.id, "FORM24Q_GENERATE", "form_24q_export",
        str(obj.id),
        {"fy": payload.fy, "quarter": payload.quarter, **summary},
        request,
    )
    await db.commit()
    await db.refresh(obj)
    return obj


@router.get("/form24q", response_model=List[Form24QRead])
async def list_24q(
    db: deps.DBDep, fy: Optional[str] = Query(None),
    current_user: User = Depends(deps.check_permissions([PERM_GENERATE])),
) -> Any:
    stmt = select(Form24QExport)
    if fy:
        stmt = stmt.where(Form24QExport.fy == fy)
    return list((await db.execute(
        stmt.order_by(Form24QExport.fy.desc(), Form24QExport.quarter.desc())
    )).scalars().all())


@router.get("/form24q/{qid}/download")
async def download_24q(
    qid: int, db: deps.DBDep,
    current_user: User = Depends(deps.check_permissions([PERM_GENERATE])),
) -> Any:
    obj = await db.get(Form24QExport, qid)
    if obj is None:
        raise HTTPException(404, "24Q export not found")
    data = obj.summary or {}
    hex_bytes = data.get("_bytes_hex")
    if not hex_bytes:
        raise HTTPException(410, "Bytes missing — regenerate")
    return StreamingResponse(
        io.BytesIO(bytes.fromhex(hex_bytes)),
        media_type="text/csv",
        headers={
            "Content-Disposition":
                f'attachment; filename="{obj.file_name or "24q.csv"}"'
        },
    )


# =====================================================================
# Gratuity — single, company-wide, exit
# =====================================================================


async def _compute_for_emp(
    db, emp: Employee, *, as_of: date, config: Optional[GratuityConfig],
) -> tuple[GratuityResultRead, float]:
    """Compute gratuity for one employee. Returns (read_dto, last_drawn)."""
    user = await db.get(User, emp.user_id)
    last_basic = float(emp.salary or 0.0)
    g = compute_gratuity(
        last_basic_da_monthly=last_basic,
        joining_date=emp.date_of_joining,
        as_of=as_of, config=config,
    )
    return (
        GratuityResultRead(
            employee_id=emp.id,
            employee_full_name=user.full_name if user else None,
            employee_code=emp.employee_id,
            last_basic_da=g.last_basic_da, days_basis=g.days_basis,
            raw_years=g.raw_years, rounded_years=g.rounded_years,
            is_eligible=g.is_eligible, computed_amount=g.computed_amount,
            capped_amount=g.capped_amount, cap_applied=g.cap_applied,
            eligibility_years_used=g.eligibility_years_used,
            note=g.note, as_of=as_of,
        ),
        last_basic,
    )


@router.get(
    "/gratuity/employee/{employee_id}",
    response_model=GratuityResultRead,
)
async def gratuity_for_employee(
    employee_id: int, db: deps.DBDep,
    as_of: Optional[date] = Query(None),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    emp = await db.get(Employee, employee_id, options=[selectinload(Employee.user)])
    if emp is None:
        raise HTTPException(404, "Employee not found")
    if emp.user_id != current_user.id and not _user_can_view_all(current_user):
        raise HTTPException(403, "Not authorized")

    config = await _resolve_gratuity_config(db)
    cutoff = as_of or date.today()
    result, _ = await _compute_for_emp(db, emp, as_of=cutoff, config=config)
    return result


@router.get("/gratuity/liability", response_model=CompanyLiabilityReport)
async def gratuity_liability(
    db: deps.DBDep, as_of: Optional[date] = Query(None),
    current_user: User = Depends(deps.check_permissions([PERM_GRATUITY_VIEW])),
) -> Any:
    """Company-wide accruing liability across all active employees."""
    cutoff = as_of or date.today()
    config = await _resolve_gratuity_config(db)
    emps = list((await db.execute(
        select(Employee).where(Employee.status == "active")
        .options(selectinload(Employee.user))
    )).scalars().all())

    rows: List[GratuityResultRead] = []
    agg_rows: List[LiabilityRow] = []
    for emp in emps:
        result, _ = await _compute_for_emp(db, emp, as_of=cutoff, config=config)
        rows.append(result)
        agg_rows.append(LiabilityRow(
            employee_id=emp.id,
            name=result.employee_full_name,
            raw_years=result.raw_years, rounded_years=result.rounded_years,
            last_basic_da=result.last_basic_da,
            is_eligible=result.is_eligible,
            accruing_liability=result.capped_amount or result.computed_amount,
            payable_if_exits_today=result.capped_amount,
        ))

    agg = aggregate_company_liability(agg_rows)
    rows.sort(key=lambda r: r.capped_amount, reverse=True)
    return CompanyLiabilityReport(
        as_of=cutoff, rows=rows,
        total_employees=agg["total_employees"],
        eligible_employees=agg["eligible_employees"],
        total_accruing_liability=agg["total_accruing_liability"],
        payable_if_all_exit_today=agg["payable_if_all_exit_today"],
        accruing_under_5_years=agg["accruing_under_5_years"],
    )


@router.post(
    "/gratuity/exit/{employee_id}",
    response_model=ExitGratuityResult,
)
async def gratuity_at_exit(
    employee_id: int,
    db: deps.DBDep, request: Request,
    resignation_id: Optional[int] = Query(None),
    last_working_day: Optional[date] = Query(None),
    current_user: User = Depends(deps.check_permissions([PERM_GRATUITY_VIEW])),
) -> Any:
    """Compute exit-time gratuity and SNAPSHOT it.

    Reads the existing Resignation row (no rebuild). The figure is
    persisted in GratuityComputation so finance can audit it later
    even if employee.salary changes via a correction or revision.
    """
    emp = await db.get(Employee, employee_id, options=[
        selectinload(Employee.user),
    ])
    if emp is None:
        raise HTTPException(404, "Employee not found")

    res: Optional[Resignation] = None
    cutoff = last_working_day
    if resignation_id:
        res = await db.get(Resignation, resignation_id)
        if res is None:
            raise HTTPException(404, "Resignation not found")
        # last_working_day comes from the resignation if not overridden
        cutoff = cutoff or getattr(res, "last_working_day", None)
    if cutoff is None:
        cutoff = date.today()

    config = await _resolve_gratuity_config(db)
    result, last_basic = await _compute_for_emp(
        db, emp, as_of=cutoff, config=config,
    )

    snapshot = GratuityComputation(
        employee_id=emp.id,
        config_id=config.id if config else None,
        resignation_id=res.id if res else None,
        as_of=cutoff, last_drawn_basic_da=last_basic,
        raw_years=result.raw_years, rounded_years=result.rounded_years,
        is_eligible=result.is_eligible,
        computed_amount=result.computed_amount,
        capped_amount=result.capped_amount,
        cap_applied=result.cap_applied,
        status=GratuityStatus.COMPUTED if res else GratuityStatus.ELIGIBLE,
        notes=result.note,
        computed_by_id=current_user.id,
    )
    db.add(snapshot)
    await db.flush()
    await log_audit(
        db, current_user.id, "GRATUITY_EXIT_COMPUTE", "gratuity_computation",
        str(snapshot.id),
        {
            "employee_id": emp.id, "as_of": cutoff.isoformat(),
            "capped_amount": result.capped_amount,
        },
        request,
    )
    await db.commit()
    return ExitGratuityResult(
        employee_id=emp.id,
        resignation_id=res.id if res else None,
        last_working_day=cutoff,
        gratuity=result,
        snapshot_id=snapshot.id,
    )
