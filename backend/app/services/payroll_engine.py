"""Unified statutory computation for the payslip path.

Bridges the two engines documented in
docs/superpowers/specs/2026-07-03-payroll-engine-unification-design.md:
`generate-draft` (and the line editor) call into this module so PF /
ESIC / PT / TDS on the payslip come from the SAME config tables the
compliance filings read (`StatutoryConfig`, `PTStateSlab`,
`TaxSlabConfig`, `SectionLimitConfig`, `EmployeeTaxDeclaration`,
`EmployeeStatutoryDetail`). Reconciliation drift for a freshly
generated run is zero by construction.

Layering:
- `load_statutory_context()` — async, all DB reads, bulk (no N+1).
- `compute_statutory()` — pure math per employee, unit-testable.

# Documented decisions

## ESIC_COVERAGE = auto
Coverage is decided by `is_under_esic` (gross <= ceiling, or the
mid-period continuation date) — the manual `Employee.esic_applicable`
flag no longer drives payroll. The ESI wage base is the FULL monthly
gross (earnings + OT + night + arrears + incentive), per the ESI Act.

## PF_BASE = prorated basic, capped
EPF wages = min(basic_actual, pf_wage_ceiling). Voluntary PF rides on
top, uncapped. Employer admin (0.5%) + EDLI (0.5%) are employer-cost
line items, not employee deductions.

## PT_STATE_RESOLUTION = detail -> employer default -> WEST BENGAL
When the DB carries no slabs for the resolved state, a built-in West
Bengal table (the legacy hardcoded slabs) applies, so an unconfigured
install keeps its previous behaviour.

## TDS_PROJECTION = ytd actuals + current month x months_remaining
Regime from the employee's FY declaration, else the statutory default
(new). Old regime applies HRA exemption + capped Chapter VI-A. The
monthly figure is the catch-up formula in `tds.compute_monthly_tds`.
A manual TDS entered in the line editor always wins (tds_manual).

## ROUNDING = paise (round2) for statutory amounts
Matches the reconciliation tolerance (+-Rs 0.011). Earnings keep the
legacy Excel-style roundup — unchanged payouts on the earnings side.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional

from sqlalchemy import and_, select

from app.models.employee import Employee
from app.models.payroll import PayrollLine, PayrollRun, PayrollRunStatus
from app.models.statutory import (
    EmployerIdentifier, EmployeeStatutoryDetail, PTStateSlab,
    StatutoryConfig,
)
from app.models.tax import (
    EmployeeTaxDeclaration, SectionLimitConfig, TaxSlabConfig,
)
from app.services.statutory import (
    is_under_esic, pick_config_for_month, pick_pt_slab,
)
from app.services.tds import (
    DEFAULT_REGIME, Regime, cap_chapter_via, compute_annual_tax,
    compute_monthly_tds, fy_for_date, fy_remaining_months_inclusive,
)


def _round2(x: float) -> float:
    return round(float(x), 2)


# --- built-in fallbacks (unconfigured installs) ----------------------


@dataclass
class DefaultStatutoryConfig:
    """Mirror of the StatutoryConfig model defaults — current law."""
    id: int = 0
    effective_from: date = date(2000, 1, 1)
    pf_employee_rate: float = 12.0
    pf_employer_rate: float = 12.0
    eps_rate: float = 8.33
    pf_wage_ceiling: float = 15000.0
    eps_wage_ceiling: float = 15000.0
    edli_rate: float = 0.5
    edli_wage_ceiling: float = 15000.0
    epf_admin_rate: float = 0.5
    esic_employee_rate: float = 0.75
    esic_employer_rate: float = 3.25
    esic_wage_ceiling: float = 21000.0


@dataclass
class _FallbackPTSlab:
    state: str
    effective_from: date
    slab_min: float
    slab_max: Optional[float]
    monthly_amount: float
    gender: str = "ALL"
    month_index: Optional[int] = None


FALLBACK_PT_STATE = "WEST BENGAL"
# The legacy hardcoded WB table from salary_calculator — kept as the
# zero-config fallback so behaviour is unchanged on empty databases.
FALLBACK_PT_SLABS: List[_FallbackPTSlab] = [
    _FallbackPTSlab(FALLBACK_PT_STATE, date(2000, 1, 1), 0.0, 10000.0, 0.0),
    _FallbackPTSlab(FALLBACK_PT_STATE, date(2000, 1, 1), 10000.01, 15000.0, 110.0),
    _FallbackPTSlab(FALLBACK_PT_STATE, date(2000, 1, 1), 15000.01, 25000.0, 130.0),
    _FallbackPTSlab(FALLBACK_PT_STATE, date(2000, 1, 1), 25000.01, 40000.0, 150.0),
    _FallbackPTSlab(FALLBACK_PT_STATE, date(2000, 1, 1), 40000.01, None, 200.0),
]


# --- context ---------------------------------------------------------


@dataclass
class StatutoryContext:
    year: int
    month: int
    fy: str
    months_remaining: int
    config: object                       # ConfigLike
    pt_slabs: List[object]
    default_pt_state: str
    tax_slab: Optional[TaxSlabConfig]
    section_limits: Dict[str, SectionLimitConfig]
    details_by_emp: Dict[int, EmployeeStatutoryDetail] = field(
        default_factory=dict
    )
    decls_by_emp: Dict[int, EmployeeTaxDeclaration] = field(
        default_factory=dict
    )
    ytd_by_user: Dict[int, dict] = field(default_factory=dict)


def _fy_window(fy: str) -> tuple[date, date]:
    a, b = fy.split("-")
    return date(2000 + int(a), 4, 1), date(2000 + int(b), 3, 31)


async def load_statutory_context(
    db, year: int, month: int, employees: List[Employee],
) -> StatutoryContext:
    """Bulk-load every config + per-employee input the engine needs."""
    fy = fy_for_date(date(year, month, 1))

    configs = (await db.execute(
        select(StatutoryConfig).where(StatutoryConfig.is_active.is_(True))
    )).scalars().all()
    config = pick_config_for_month(configs, year, month) or DefaultStatutoryConfig()

    pt_slabs = list((await db.execute(
        select(PTStateSlab).where(PTStateSlab.is_active.is_(True))
    )).scalars().all())

    employer = (await db.execute(
        select(EmployerIdentifier)
        .where(EmployerIdentifier.is_active.is_(True))
        .limit(1)
    )).scalar_one_or_none()
    default_pt_state = (
        (employer.default_pt_state if employer else None) or FALLBACK_PT_STATE
    )

    tax_slabs = (await db.execute(
        select(TaxSlabConfig).where(TaxSlabConfig.is_active.is_(True))
    )).scalars().all()
    exact = [c for c in tax_slabs if c.fy == fy]
    tax_slab = exact[0] if exact else (
        sorted(tax_slabs, key=lambda c: c.fy)[-1] if tax_slabs else None
    )

    limits = {
        row.section_code: row
        for row in (await db.execute(
            select(SectionLimitConfig).where(SectionLimitConfig.fy == fy)
        )).scalars().all()
    }

    emp_ids = [e.id for e in employees]
    user_ids = [e.user_id for e in employees]

    details_by_emp: Dict[int, EmployeeStatutoryDetail] = {}
    decls_by_emp: Dict[int, EmployeeTaxDeclaration] = {}
    if emp_ids:
        for d in (await db.execute(
            select(EmployeeStatutoryDetail).where(
                EmployeeStatutoryDetail.employee_id.in_(emp_ids)
            )
        )).scalars().all():
            details_by_emp[d.employee_id] = d
        for d in (await db.execute(
            select(EmployeeTaxDeclaration).where(and_(
                EmployeeTaxDeclaration.employee_id.in_(emp_ids),
                EmployeeTaxDeclaration.fy == fy,
            ))
        )).scalars().all():
            decls_by_emp[d.employee_id] = d

    # FY-to-date actuals from other (finalized/published) runs. The run
    # being drafted is LEAVES_LOCKED / DRAFT_GENERATED so it never
    # matches this filter — no self-counting.
    ytd_by_user: Dict[int, dict] = {}
    if user_ids:
        window_start, window_end = _fy_window(fy)
        rows = (await db.execute(
            select(PayrollRun, PayrollLine)
            .join(PayrollLine, PayrollLine.payroll_run_id == PayrollRun.id)
            .where(and_(
                PayrollLine.user_id.in_(user_ids),
                PayrollRun.status.in_([
                    PayrollRunStatus.FINALIZED, PayrollRunStatus.PUBLISHED,
                ]),
            ))
        )).all()
        for run, line in rows:
            run_first = date(run.year, run.month, 1)
            if not (window_start <= run_first <= window_end):
                continue
            al = line.allowances or {}
            ded = line.deductions or {}
            agg = ytd_by_user.setdefault(line.user_id, {
                "gross": 0.0, "basic": 0.0, "hra": 0.0, "tds": 0.0,
            })
            agg["gross"] += float(line.gross_pay or 0.0)
            agg["basic"] += float(
                al.get("basic_salary_actual", line.base_salary or 0.0)
            )
            agg["hra"] += float(al.get("hra_actual", 0.0))
            agg["tds"] += float(ded.get("tds", 0.0))

    return StatutoryContext(
        year=year, month=month, fy=fy,
        months_remaining=fy_remaining_months_inclusive(month),
        config=config, pt_slabs=pt_slabs,
        default_pt_state=default_pt_state,
        tax_slab=tax_slab, section_limits=limits,
        details_by_emp=details_by_emp, decls_by_emp=decls_by_emp,
        ytd_by_user=ytd_by_user,
    )


# --- per-employee computation ---------------------------------------


@dataclass
class StatutoryResult:
    employee_pf: float
    employer_pf: float
    epf_wages: float
    epf_admin_charges: float
    edli_charges: float
    esic_employee: float
    esic_employer: float
    esic_covered: bool
    esic_basis: str          # "wage_ceiling" | "continuation" | "not_covered"
    pt_amount: float
    pt_state: str
    tds: float
    tds_auto: float
    tds_regime: str
    tds_note: Optional[str]


def compute_statutory(
    ctx: StatutoryContext,
    emp: Employee,
    *,
    basic_actual: float,
    hra_actual: float,
    gross_total: float,
    tds_override: Optional[float] = None,
) -> StatutoryResult:
    """Config-driven PF / ESIC / PT / TDS for one payslip line.

    `gross_total` must already include OT, night allowance, arrears and
    incentive — ESIC, PT and the TDS projection are computed on it.
    """
    cfg = ctx.config
    detail = ctx.details_by_emp.get(emp.id)
    decl = ctx.decls_by_emp.get(emp.id)

    # ----- PF (capped, same math as compute_ecr_row) -----
    epf_wages = min(float(basic_actual), float(cfg.pf_wage_ceiling))
    employee_pf = _round2(epf_wages * cfg.pf_employee_rate / 100.0)
    employer_pf = _round2(epf_wages * cfg.pf_employer_rate / 100.0)
    epf_admin = _round2(epf_wages * cfg.epf_admin_rate / 100.0)
    edli = _round2(
        min(float(basic_actual), float(cfg.edli_wage_ceiling))
        * cfg.edli_rate / 100.0
    )

    # ----- ESIC (auto coverage, full-gross base) -----
    continuation = detail.esic_continuation_until if detail else None
    payroll_month = date(ctx.year, ctx.month, 1)
    covered = is_under_esic(
        gross_wages_this_month=gross_total, config=cfg,
        payroll_month=payroll_month, continuation_until=continuation,
    )
    if covered and continuation and payroll_month <= continuation:
        basis = "continuation"
    elif covered:
        basis = "wage_ceiling"
    else:
        basis = "not_covered"
    esic_employee = (
        _round2(gross_total * cfg.esic_employee_rate / 100.0) if covered else 0.0
    )
    esic_employer = (
        _round2(gross_total * cfg.esic_employer_rate / 100.0) if covered else 0.0
    )

    # ----- PT (state slabs, gender/month aware) -----
    pt_state = (
        (detail.pt_state if detail else None) or ctx.default_pt_state
    ).upper()
    gender = (detail.gender if detail else "ALL") or "ALL"
    slab_pool = ctx.pt_slabs
    if not any((s.state or "").upper() == pt_state for s in slab_pool):
        slab_pool = FALLBACK_PT_SLABS if pt_state == FALLBACK_PT_STATE else []
    slab = pick_pt_slab(
        slab_pool, state=pt_state, year=ctx.year, month=ctx.month,
        gross_for_pt=gross_total, gender=gender,
    )
    pt_amount = _round2(slab.monthly_amount) if slab else 0.0

    # ----- TDS (auto monthly, declaration-aware) -----
    tds_auto = 0.0
    tds_note: Optional[str] = None
    regime = (decl.regime if decl else DEFAULT_REGIME) or DEFAULT_REGIME
    if ctx.tax_slab is None:
        tds_note = "no_tax_slab_config"
    else:
        ytd = ctx.ytd_by_user.get(emp.user_id) or {
            "gross": 0.0, "basic": 0.0, "hra": 0.0, "tds": 0.0,
        }
        m = ctx.months_remaining
        annual_gross = ytd["gross"] + gross_total * m
        annual_basic = ytd["basic"] + float(basic_actual) * m
        annual_hra = ytd["hra"] + float(hra_actual) * m
        chap_via = (
            cap_chapter_via(decl.declarations_json, ctx.section_limits)
            if decl and regime == Regime.OLD.value else 0.0
        )
        proj = compute_annual_tax(
            regime=regime,
            gross_salary_annual=annual_gross,
            basic_da_annual=annual_basic,
            hra_received_annual=annual_hra,
            rent_paid_annual=(decl.monthly_rent_paid * 12.0) if decl else 0.0,
            metro=(decl.rented_in_metro if decl else False),
            chapter_via_deductions=chap_via,
            other_income_annual=(decl.other_income_annual if decl else 0.0),
            previous_employer_income=(
                decl.previous_employer_income if decl else 0.0
            ),
            slab_config=ctx.tax_slab,
        )
        tds_auto = compute_monthly_tds(
            projected_annual_tax=proj.total_tax,
            ytd_tds_deducted=ytd["tds"],
            months_remaining=m,
            previous_employer_tds=(
                decl.previous_employer_tds if decl else 0.0
            ),
        )
        if proj.total_tax <= 0 and proj.rebate_87a > 0:
            tds_note = "zero_after_87a_rebate"

    tds = _round2(tds_override) if tds_override is not None else tds_auto

    return StatutoryResult(
        employee_pf=employee_pf, employer_pf=employer_pf,
        epf_wages=_round2(epf_wages),
        epf_admin_charges=epf_admin, edli_charges=edli,
        esic_employee=esic_employee, esic_employer=esic_employer,
        esic_covered=covered, esic_basis=basis,
        pt_amount=pt_amount, pt_state=pt_state,
        tds=tds, tds_auto=tds_auto, tds_regime=regime, tds_note=tds_note,
    )
