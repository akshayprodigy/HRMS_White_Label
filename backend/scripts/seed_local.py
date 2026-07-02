"""One-command seed for the LOCAL Docker Desktop stack.

Intended run:
    docker compose -f docker-compose.local.yml exec -T backend \\
        python -m scripts.seed_local

What this does (all idempotent):

1. Existing scripts (unchanged, imported):
    - seed_admin.seed_admin()            (Super Admin role + core perms)
    - create_admin.create_admin()        (admin user + login)
    - seed_hr_permissions.seed_hr_permissions()
    - seed_departments.seed()
    - seed_leave_types.seed()

2. Notification templates via app.services.notifications_seed
   .seed_starter_templates() — same helper the /notifications/templates/seed
   HTTP endpoint uses.

3. Gaps filled locally (nothing prod-shaped):
    - One shift template  (Regular Day 09:00-18:00)
    - One geo-fence       (HQ Kolkata Test — 22.5726, 88.3639 / 500m)
    - One statutory FY config (base rates, effective from Apr 1)
    - One expense category (Travel Meals)
    - One approval chain  (Expense — HR role approval for any amount)
    - A handful of test employees (t1..t3 @ localhost) with bank/PAN/UAN
      hooked up so payroll + reports have data to chew on.

Safety:
- Refuses to run unless invoked with --yes-local OR ERP_LOCAL_SEED=1.
- Uses LOCAL_ADMIN_EMAIL / LOCAL_ADMIN_PASSWORD from env (default:
  admin@example.com / LocalAdmin!2026). Distinct from any prod path and
  distinct from the forbidden scripts/seed_demo_users.py.
- Never runs if MARIADB_SERVER is anything other than 'db' or
  'localhost' or '127.0.0.1'. Belt-and-braces against pointing at a
  real DB by mistake.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import date, time, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession, async_sessionmaker, create_async_engine,
)

from app.core.config import settings
from app.core.security import get_password_hash

# Existing seeds — imported as functions, not shelled out.
from scripts.seed_admin import seed_admin as run_seed_admin
from scripts.create_admin import create_admin as run_create_admin
from scripts.seed_hr_permissions import (
    seed_hr_permissions as run_seed_hr_permissions,
)
from scripts.seed_departments import seed as run_seed_departments
from scripts.seed_leave_types import seed as run_seed_leave_types


LOCAL_HOSTS = {"db", "localhost", "127.0.0.1"}


def _guard():
    """Refuse to run unless the caller explicitly asked for local seed."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--yes-local", action="store_true",
        help="Confirm you want local test data on THIS DB",
    )
    args = ap.parse_args()
    if not (args.yes_local or os.environ.get("ERP_LOCAL_SEED") == "1"):
        print(
            "REFUSING TO RUN.\n"
            "Pass --yes-local or set ERP_LOCAL_SEED=1 to confirm "
            "this is a local/test DB.",
            file=sys.stderr,
        )
        sys.exit(2)
    server = os.environ.get("MARIADB_SERVER", "db")
    if server not in LOCAL_HOSTS:
        print(
            f"REFUSING TO RUN against MARIADB_SERVER={server!r}. "
            "This script is local-only.",
            file=sys.stderr,
        )
        sys.exit(2)


async def _fill_gap_fixtures(session: AsyncSession) -> None:
    """Everything not already covered by an existing script."""
    from app.services.notifications_seed import seed_starter_templates
    from app.models.shift import ShiftTemplate
    from app.models.geofence import GeoFenceLocation
    from app.models.statutory import StatutoryConfig
    from app.models.expense import ExpenseCategory
    from app.models.approval_chain import (
        ApprovalChain, ApprovalChainStep,
    )
    from app.models.user import User, Role
    from app.models.employee import Employee, EmployeeStatus

    # --- Notification templates (idempotent inside the helper) ------
    n_inserted = await seed_starter_templates(session)
    print(f"  notification_templates: +{n_inserted}")

    # --- Shift template --------------------------------------------
    shift = (await session.execute(
        select(ShiftTemplate).where(ShiftTemplate.name == "Regular Day 09-18")
    )).scalar_one_or_none()
    if shift is None:
        shift = ShiftTemplate(
            name="Regular Day 09-18",
            start_time=time(9, 0),
            end_time=time(18, 0),
            is_overnight=False,
            break_minutes=60,
            grace_in_minutes=10,
            grace_out_minutes=10,
            full_day_hours=9.0,
            half_day_hours=4.5,
            weekly_offs=[5, 6],  # Sat, Sun (Mon=0)
            is_active=True,
        )
        session.add(shift)
        print("  shift_template: +Regular Day 09-18")

    # --- Geo-fence --------------------------------------------------
    fence = (await session.execute(
        select(GeoFenceLocation).where(
            GeoFenceLocation.name == "HQ Kolkata Test"
        )
    )).scalar_one_or_none()
    if fence is None:
        fence = GeoFenceLocation(
            name="HQ Kolkata Test",
            latitude=22.5726,
            longitude=88.3639,
            radius_meters=500,
            is_active=True,
        )
        session.add(fence)
        print(
            "  geofence_location: +HQ Kolkata Test "
            "(22.5726, 88.3639 / 500m)"
        )

    # --- Statutory FY config ---------------------------------------
    today = date.today()
    fy_year = today.year if today.month >= 4 else today.year - 1
    fy_name = f"FY {fy_year}-{str(fy_year + 1)[-2:]} base"
    stat = (await session.execute(
        select(StatutoryConfig).where(StatutoryConfig.name == fy_name)
    )).scalar_one_or_none()
    if stat is None:
        stat = StatutoryConfig(
            name=fy_name,
            effective_from=date(fy_year, 4, 1),
            is_active=True,
            # Defaults on the model are already the current-law numbers.
        )
        session.add(stat)
        print(f"  statutory_config: +{fy_name}")

    # --- Expense category ------------------------------------------
    cat = (await session.execute(
        select(ExpenseCategory).where(ExpenseCategory.name == "Travel Meals")
    )).scalar_one_or_none()
    if cat is None:
        cat = ExpenseCategory(
            name="Travel Meals",
            code="MEAL",
            per_diem_cap_paise=50_000,          # ₹500/day
            receipt_required_above_paise=20_000,  # ₹200
            policy_mode="warn",
            is_active=True,
        )
        session.add(cat)
        print("  expense_category: +Travel Meals")

    # --- Approval chain --------------------------------------------
    # Simple: any expense goes to HR role, single-step approval.
    chain = (await session.execute(
        select(ApprovalChain).where(
            ApprovalChain.name == "Local Test — HR Approves Expenses",
            ApprovalChain.entity_type == "expense",
        )
    )).scalar_one_or_none()
    if chain is None:
        chain = ApprovalChain(
            name="Local Test — HR Approves Expenses",
            entity_type="expense",
            department=None,
            is_active=True,
            effective_from=today,
            effective_to=None,
            skip_if_same_person=True,
            notes="Local seed — HR role signs off any amount.",
        )
        chain.steps = [
            ApprovalChainStep(
                step_order=1,
                approver_type="role",
                approver_ref="HR",
                mode="sequential",
                parallel_rule="all",
                min_amount_paise=0,
                max_amount_paise=None,   # no upper bound
                skip_if_same_person=False,
                label="HR sign-off",
            )
        ]
        session.add(chain)
        print("  approval_chain: +Local Test — HR Approves Expenses")

    await session.flush()

    # --- Test employees --------------------------------------------
    # Uses distinct emails so they can never collide with production
    # data; DoJ set to today so tenure calcs work.
    testers = [
        ("t1@example.com", "Tester One",   "T001", "Engineering"),
        ("t2@example.com", "Tester Two",   "T002", "Human Resources"),
        ("t3@example.com", "Tester Three", "T003", "Operations"),
    ]
    default_pw = "Local!2026"
    for email, name, empid, dept in testers:
        u = (await session.execute(
            select(User).where(User.email == email)
        )).scalar_one_or_none()
        if u is None:
            u = User(
                email=email,
                hashed_password=get_password_hash(default_pw),
                full_name=name,
                is_active=True,
                is_superuser=False,
            )
            session.add(u)
            await session.flush()
            print(f"  user: +{email}")
        emp = (await session.execute(
            select(Employee).where(Employee.employee_id == empid)
        )).scalar_one_or_none()
        if emp is None:
            emp = Employee(
                user_id=u.id,
                employee_id=empid,
                department=dept,
                designation="Engineer" if dept == "Engineering" else "Officer",
                date_of_joining=date.today(),
                status=EmployeeStatus.ACTIVE,
                salary=45000.0,
                hra=15000.0,
                bank_account="000000012345",
                bank_name="Local Test Bank",
                bank_ifsc_code="LOCB0000123",
                bank_account_holder_name=name,
                pan_number=f"AAAPT{empid[-4:].zfill(4)}A",
                pf_number=f"UAN{empid[-4:].zfill(4)}00000",
            )
            session.add(emp)
            print(f"  employee: +{empid} ({name})")

    await session.commit()


async def _run_all():
    # Existing seeds each open their own engine internally.
    print("[1/6] seed_admin (roles + core perms)")
    await run_seed_admin()

    print("[2/6] create_admin (admin login)")
    # create_admin honours ADMIN_EMAIL / ADMIN_PASSWORD. Bridge them
    # from our LOCAL_ADMIN_* env names so a stray ADMIN_PASSWORD in an
    # unrelated shell can't clobber the tester login.
    admin_email = os.environ.get(
        "LOCAL_ADMIN_EMAIL", "admin@example.com"
    )
    # NOSONAR — local-only default; overridden by LOCAL_ADMIN_PASSWORD
    # in .env.local. The script refuses to run against any DB other
    # than 'db'/'localhost'/'127.0.0.1' (see _guard).
    admin_password = os.environ.get(  # NOSONAR
        "LOCAL_ADMIN_PASSWORD", "LocalAdmin!2026",  # NOSONAR
    )
    os.environ["ADMIN_EMAIL"] = admin_email
    os.environ["ADMIN_PASSWORD"] = admin_password
    await run_create_admin()

    print("[3/6] seed_hr_permissions")
    await run_seed_hr_permissions()

    print("[4/6] seed_departments")
    await run_seed_departments()

    print("[5/6] seed_leave_types")
    await run_seed_leave_types()

    print("[6/6] gap fixtures (shift + geofence + statutory + "
          "expense + approval chain + notif templates + testers)")
    engine = create_async_engine(settings.SQLALCHEMY_DATABASE_URI)
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    try:
        async with session_factory() as session:
            await _fill_gap_fixtures(session)
    finally:
        await engine.dispose()

    print()
    print("Done.")
    print(f"  Admin login: {admin_email} / {admin_password}")
    print(
        "  Testers:     t1@example.com, t2@example.com, t3@example.com / "
        "Local!2026"
    )
    print(
        "  Geo-punch:   spoof browser location to 22.5726, 88.3639 "
        "(HQ Kolkata Test)"
    )


def main() -> None:
    _guard()
    asyncio.run(_run_all())


if __name__ == "__main__":
    main()
