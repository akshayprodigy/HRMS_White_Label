"""Seed statutory + tax config defaults for the unified payroll engine.

Section: payroll engine unification (P0). Populates, idempotently:

- EmployerIdentifier "Veliora (Local)" with default PT state WEST BENGAL
- PTStateSlab tables for WEST BENGAL / KARNATAKA / MAHARASHTRA /
  TELANGANA / GUJARAT (Maharashtra carries the Feb Rs 300 month override)
- TaxSlabConfig for FY 25-26 and 26-27 (Budget-2025 new-regime slabs,
  87A Rs 12L / Rs 60k, std deduction 75k new / 50k old, 4% cess,
  surcharge bands with the 25% new-regime cap)
- SectionLimitConfig rows (80C / 80D / 80CCD_1B / 80TTA + HRA pcts)
- Tester salary spread so every statutory branch is live:
    T001 45k basic  -> PF-cap + zero-TDS-after-87A case
    T002  9k basic  -> ESIC-covered case (gross 18k <= 21k ceiling)
    T003 1.5L basic -> real monthly TDS case
  (T002/T003 salaries are OVERWRITTEN to these targets on each run.)
- EmployeeStatutoryDetail rows for T001-T003 (pt_state WEST BENGAL)

Safety: refuses to run unless ERP_LOCAL_SEED=1 and --yes-local is
passed — same contract as scripts/seed_local.py.

Run:
    docker compose -f docker-compose.local.yml exec -T \
        -e ERP_LOCAL_SEED=1 -e PYTHONPATH=/app \
        backend python -m scripts.seed_statutory_defaults --yes-local
"""
import asyncio
import os
import sys
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.employee import Employee
from app.models.statutory import (
    EmployerIdentifier, EmployeeStatutoryDetail, PTStateSlab,
)
from app.models.tax import SectionLimitConfig, TaxSlabConfig


EFFECTIVE = date(2024, 4, 1)

# state -> [(slab_min, slab_max, monthly_amount, month_index)]
PT_TABLES = {
    "WEST BENGAL": [
        (0.0, 10000.0, 0.0, None),
        (10000.01, 15000.0, 110.0, None),
        (15000.01, 25000.0, 130.0, None),
        (25000.01, 40000.0, 150.0, None),
        (40000.01, None, 200.0, None),
    ],
    "KARNATAKA": [
        (0.0, 24999.99, 0.0, None),
        (25000.0, None, 200.0, None),
    ],
    "MAHARASHTRA": [
        (0.0, 7500.0, 0.0, None),
        (7500.01, 10000.0, 175.0, None),
        (10000.01, None, 200.0, None),
        (10000.01, None, 300.0, 2),   # Feb catch-up month
    ],
    "TELANGANA": [
        (0.0, 15000.0, 0.0, None),
        (15000.01, 20000.0, 150.0, None),
        (20000.01, None, 200.0, None),
    ],
    "GUJARAT": [
        (0.0, 12000.0, 0.0, None),
        (12000.01, None, 200.0, None),
    ],
}

SLABS_JSON = {
    "new": [
        {"upto": 400000, "rate": 0},
        {"upto": 800000, "rate": 5},
        {"upto": 1200000, "rate": 10},
        {"upto": 1600000, "rate": 15},
        {"upto": 2000000, "rate": 20},
        {"upto": 2400000, "rate": 25},
        {"upto": None, "rate": 30},
    ],
    "old": [
        {"upto": 250000, "rate": 0},
        {"upto": 500000, "rate": 5},
        {"upto": 1000000, "rate": 20},
        {"upto": None, "rate": 30},
    ],
    "surcharge_old": [
        {"upto": 5000000, "rate": 0},
        {"upto": 10000000, "rate": 10},
        {"upto": 20000000, "rate": 15},
        {"upto": 50000000, "rate": 25},
        {"upto": None, "rate": 37},
    ],
    "surcharge_new": [
        {"upto": 5000000, "rate": 0},
        {"upto": 10000000, "rate": 10},
        {"upto": 20000000, "rate": 15},
        {"upto": None, "rate": 25},
    ],
}

FY_LABELS = ["25-26", "26-27"]

SECTION_LIMITS = [
    # (code, limit, is_percentage)
    ("80C", 150000.0, False),
    ("80D", 25000.0, False),
    ("80CCD_1B", 50000.0, False),
    ("80TTA", 10000.0, False),
    ("hra_metro_pct", 50.0, True),
    ("hra_non_metro_pct", 40.0, True),
]

# employee_id -> (salary, hra, conveyance, other)
TESTER_SALARIES = {
    "T002": (9000.0, 4500.0, 2700.0, 1800.0),
    "T003": (150000.0, 75000.0, 45000.0, 30000.0),
}
TESTER_PT_STATE = "WEST BENGAL"
TESTER_IDS = ["T001", "T002", "T003"]


def _guard() -> None:
    if os.environ.get("ERP_LOCAL_SEED") != "1" or "--yes-local" not in sys.argv:
        print(
            "REFUSING to run: set ERP_LOCAL_SEED=1 and pass --yes-local.\n"
            "This script writes config + test salaries — local stacks only."
        )
        sys.exit(1)


async def _ensure_employer(session: AsyncSession) -> None:
    row = (await session.execute(
        select(EmployerIdentifier).limit(1)
    )).scalars().first()
    if row is None:
        session.add(EmployerIdentifier(
            name="Veliora (Local)",
            default_pt_state=TESTER_PT_STATE,
            is_active=True,
        ))
        print("  employer_identifier: +Veliora (Local)")
    elif not row.default_pt_state:
        row.default_pt_state = TESTER_PT_STATE
        print("  employer_identifier: default_pt_state -> WEST BENGAL")


async def _ensure_pt_slabs(session: AsyncSession) -> None:
    added = 0
    for state, rows in PT_TABLES.items():
        for slab_min, slab_max, amount, month_index in rows:
            existing = (await session.execute(
                select(PTStateSlab).where(
                    PTStateSlab.state == state,
                    PTStateSlab.effective_from == EFFECTIVE,
                    PTStateSlab.slab_min == slab_min,
                    PTStateSlab.gender == "ALL",
                    PTStateSlab.month_index.is_(None)
                    if month_index is None
                    else PTStateSlab.month_index == month_index,
                )
            )).scalars().first()
            if existing:
                continue
            session.add(PTStateSlab(
                state=state, effective_from=EFFECTIVE,
                slab_min=slab_min, slab_max=slab_max,
                monthly_amount=amount, gender="ALL",
                month_index=month_index, is_active=True,
                notes="seed_statutory_defaults",
            ))
            added += 1
    print(f"  pt_state_slab: +{added} rows ({len(PT_TABLES)} states)")


async def _ensure_tax_slabs(session: AsyncSession) -> None:
    for fy in FY_LABELS:
        existing = (await session.execute(
            select(TaxSlabConfig).where(TaxSlabConfig.fy == fy)
        )).scalars().first()
        if existing:
            continue
        session.add(TaxSlabConfig(
            fy=fy, name=f"FY {fy} (Budget 2025 defaults)",
            slabs_json=SLABS_JSON,
            standard_deduction_old=50000.0,
            standard_deduction_new=75000.0,
            rebate_87a_old_threshold=500000.0,
            rebate_87a_old_max=12500.0,
            rebate_87a_new_threshold=1200000.0,
            rebate_87a_new_max=60000.0,
            cess_rate=4.0, is_active=True,
            notes="seed_statutory_defaults",
        ))
        print(f"  tax_slab_config: +FY {fy}")


async def _ensure_section_limits(session: AsyncSession) -> None:
    added = 0
    for fy in FY_LABELS:
        for code, limit, is_pct in SECTION_LIMITS:
            existing = (await session.execute(
                select(SectionLimitConfig).where(
                    SectionLimitConfig.fy == fy,
                    SectionLimitConfig.section_code == code,
                )
            )).scalars().first()
            if existing:
                continue
            session.add(SectionLimitConfig(
                fy=fy, section_code=code, limit_amount=limit,
                is_percentage=is_pct, applies_to="BOTH",
                notes="seed_statutory_defaults",
            ))
            added += 1
    print(f"  section_limit_config: +{added} rows")


async def _spread_tester_salaries(session: AsyncSession) -> None:
    for empid, (salary, hra, ca, other) in TESTER_SALARIES.items():
        emp = (await session.execute(
            select(Employee).where(Employee.employee_id == empid)
        )).scalars().first()
        if emp is None:
            print(f"  tester {empid}: not found, skipped")
            continue
        emp.salary = salary
        emp.hra = hra
        emp.conveyance_allowance = ca
        emp.other_allowance = other
        print(f"  tester {empid}: basic={salary:.0f} hra={hra:.0f}")


async def _ensure_statutory_details(session: AsyncSession) -> None:
    for empid in TESTER_IDS:
        emp = (await session.execute(
            select(Employee).where(Employee.employee_id == empid)
        )).scalars().first()
        if emp is None:
            continue
        detail = (await session.execute(
            select(EmployeeStatutoryDetail).where(
                EmployeeStatutoryDetail.employee_id == emp.id
            )
        )).scalars().first()
        if detail is None:
            session.add(EmployeeStatutoryDetail(
                employee_id=emp.id, pt_state=TESTER_PT_STATE,
                gender="ALL",
            ))
            print(f"  employee_statutory_detail: +{empid}")


async def main() -> None:
    _guard()
    engine = create_async_engine(settings.SQLALCHEMY_DATABASE_URI)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        print("[1/5] employer identifier")
        await _ensure_employer(session)
        print("[2/5] PT slabs")
        await _ensure_pt_slabs(session)
        print("[3/5] tax slab configs")
        await _ensure_tax_slabs(session)
        print("[4/5] section limits")
        await _ensure_section_limits(session)
        print("[5/5] tester salaries + statutory details")
        await _spread_tester_salaries(session)
        await _ensure_statutory_details(session)
        await session.commit()
    await engine.dispose()
    print("done.")


if __name__ == "__main__":
    asyncio.run(main())
