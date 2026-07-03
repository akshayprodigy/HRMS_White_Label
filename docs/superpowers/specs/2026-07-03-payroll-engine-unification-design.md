# Payroll Engine Unification (P0) — Design

**Date:** 2026-07-03
**Status:** Approved (user picked P0 from the payroll audit fix sequence)

## Problem

Payroll has two disconnected salary engines:

- **Path A (payslip path):** `services/salary_calculator.py` — hardcoded rates.
  PF = 12% of basic **without the ₹15,000 wage ceiling**, ESIC by manual
  `Employee.esic_applicable` flag on a base that excludes OT/arrears, PT =
  West-Bengal-only slabs, TDS = 0 unless HR types a number. Used by
  `POST /payroll/{run}/generate-draft` and the line editor.
- **Path B (compliance path):** `services/statutory.py` + `services/tds.py` —
  config-driven (`StatutoryConfig`, `PTStateSlab`, `TaxSlabConfig`,
  `SectionLimitConfig`, `EmployeeTaxDeclaration`, `EmployeeStatutoryDetail`),
  effective-dated, correct ceilings/rebates/marginal relief. Only reads
  *finalized* lines for filings — never feeds the payslip.

Result: guaranteed drift (payslip PF ₹5,400 vs ECR-capped ₹1,800 for a ₹45k
basic), no auto TDS, wrong ESIC base, single-state PT. The shipped
reconciliation reports exist precisely to detect this drift.

## Goal

One engine: `generate-draft` (and the line editor) compute PF / ESIC / PT /
TDS from the same config tables the compliance filings use. Reconciliation
drift for a freshly generated run = zero rows.

## Non-goals (deferred to P1/P2)

- Absence→LOP policy, incentive input feed, half-day LOP fix, payslip PDF,
  leave encashment, gratuity payout via F&F, expense reimbursements in
  payroll, salary structure templates.
- Contractual employees keep the existing flat-10% TDS path.
- Earnings proration keeps the legacy `roundup` behaviour (no payout change
  for earnings; only statutory deductions change).

## Design

### New service: `app/services/payroll_engine.py`

Two layers — an async loader and pure math:

1. `load_statutory_context(db, year, month) -> StatutoryContext`
   - Active `StatutoryConfig` via `pick_config_for_month`; when none exists,
     a built-in `DEFAULT_STATUTORY` dataclass mirroring the model defaults
     (12/12/8.33, ₹15k PF ceiling, 0.75/3.25, ₹21k ESIC ceiling).
   - All active `PTStateSlab` rows; `EmployerIdentifier.default_pt_state`.
   - `TaxSlabConfig` for the run's FY (exact-FY → latest-active fallback,
     same rule as tax.py); `SectionLimitConfig` map. May be `None` → TDS 0
     with note `no_tax_slab_config`.
   - Per employee: `EmployeeStatutoryDetail` (pt_state, gender,
     esic_continuation_until), `EmployeeTaxDeclaration` for the FY.
   - Per user: FY-to-date aggregates (gross / basic / hra / tds) from
     FINALIZED+PUBLISHED lines of *other* runs in this FY (reuses the
     `_annual_aggregate` key shape from tax.py).

2. `compute_statutory(ctx, employee, *, basic_actual, gross_total, vpf,
   guest_house, tds_override, run_year, run_month) -> StatutoryResult`
   - **PF:** `epf_wages = min(basic_actual, ceiling)`; employee
     `round2(epf_wages × pf_employee_rate%)`; employer
     `round2(epf_wages × pf_employer_rate%)`; admin + EDLI charges as
     separate employer-cost keys. Matches `compute_ecr_row` exactly →
     `reconcile_pf` drift 0.
   - **ESIC:** coverage decided by `is_under_esic` (gross ≤ ceiling, or
     continuation date) — the manual `esic_applicable` flag no longer
     drives payroll. Base = **full gross** (earnings + OT + night +
     arrears + incentive), which is the statutorily correct ESI wage.
   - **PT:** state = detail.pt_state → employer default → `WEST BENGAL`;
     slab via `pick_pt_slab` on full gross with gender/month overrides.
     If the DB has no slabs for the resolved state, fall back to the
     legacy built-in WB table (preserves current behaviour on empty DBs).
   - **TDS (auto):** annual projection = FY-to-date actuals + current
     month's gross × `fy_remaining_months_inclusive(run.month)`; regime =
     declaration regime else `new` (statutory default); old regime applies
     HRA exemption + capped Chapter VI-A; `compute_annual_tax` →
     `compute_monthly_tds(projected, ytd_tds, months_remaining,
     previous_employer_tds)`. `tds_override` (line editor) wins when set.
   - Statutory amounts round to paise (`round2`) so the drift tolerance
     (±₹0.011) in the reconciliation reports is met by construction.

### Rewiring `endpoints/payroll.py`

- `generate_draft`: `calculate_salary` remains the earnings/proration
  engine, but its four statutory outputs are **overridden** by
  `compute_statutory`, evaluated *after* OT/night/arrears are known (so the
  ESIC/PT/TDS bases include them). Net = gross − unified deductions.
  Deductions JSON keeps all existing keys and adds provenance:
  `epf_wages`, `epf_admin_charges`, `edli_charges`, `esic_covered`,
  `esic_basis`, `pt_state`, `tds_auto`, `tds_regime`, `tds_note`,
  `engine: "unified_v1"`.
- `update_payroll_line`: same engine. Manual TDS edit sets
  `tds_manual: true` and is preserved; otherwise TDS re-derives. ESIC/PT
  re-derive from the edited gross.
- Contractual branch untouched.

### Seeds: `scripts/seed_statutory_defaults.py` (guarded, idempotent)

- `EmployerIdentifier` "Veliora (Local)" with `default_pt_state = WEST
  BENGAL`.
- `PTStateSlab` tables for WEST BENGAL, KARNATAKA, MAHARASHTRA (Feb ₹300
  via month_index), TELANGANA, GUJARAT.
- `TaxSlabConfig` FY 25-26 and 26-27 (new-regime slabs per Budget 2025:
  nil→4L, 5%→8L, 10%→12L, 15%→16L, 20%→20L, 25%→24L, 30% above; std
  deduction ₹75k new / ₹50k old; 87A ₹12L/₹60k new, ₹5L/₹12.5k old;
  surcharge bands incl. 25% new-regime cap; cess 4%).
- `SectionLimitConfig`: 80C 1.5L, 80D 25k, 80CCD_1B 50k, hra pct rows.
- Tester salary spread so every statutory branch is exercisable:
  t1 stays ₹45k basic (PF-cap + 87A-zero-TDS case), t2 → ₹9k basic/₹4.5k
  HRA (ESIC-covered case), t3 → ₹1.5L basic/₹75k HRA (real-TDS case);
  `EmployeeStatutoryDetail` rows (pt_state WEST BENGAL, gender).

## Success criteria (live, June 2026 run regenerated)

1. t1 (basic 45k): employee PF **1800** (was 5400), TDS 0 with
   `tds_note` showing 87A rebate zeroed it, PT 200.
2. t3 (basic 1.5L): PF 1800 (capped), auto TDS > 0 monthly, PT 200.
3. t2 (gross 18k): ESIC employee 0.75% / employer 3.25% of full gross,
   `esic_covered: true` without any manual flag.
4. PF/ESIC/PT reconciliation endpoints report **zero drift rows** for the
   regenerated run; ECR totals match payslip PF.
5. Line editor edit on a draft line keeps OT and recomputes statutory
   consistently (no reversion to hardcoded rates).
