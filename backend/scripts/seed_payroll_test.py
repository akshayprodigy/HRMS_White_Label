"""Seed a self-contained PAYROLL TEST fixture into a LOCAL stack.

Creates a spread of active employees (login test@12345) that exercises
every payroll branch — including the F2 employment-type master and the F3
salary-template path — plus ~2 months of attendance and one unpaid-leave
(Loss of Pay) case so proration is visible.

Employees created (email / basic salary / profile):
  pay.staff1@test.com    45000  permanent, ratio allowances  -> PF-cap, ~0 TDS
  pay.staff2@test.com     9000  permanent, ratio allowances  -> ESIC-covered
  pay.senior@test.com   150000  permanent, ratio allowances  -> real monthly TDS
  pay.contractor@test.com 60000 contractual                   -> F2 flat 10% TDS
  pay.templated@test.com  50000  permanent + "Standard Staff" -> F3 template path
  pay.explicit@test.com   30000  permanent, EXPLICIT allowances

Existing demo employees (employee/pm/hr @gmail.com) also get salaries so the
draft has no zero-pay lines. LOP: pay.staff2 takes 3 unpaid days this month.

Idempotent — re-running updates salaries to target and skips existing rows.

Safety: refuses to run unless ERP_LOCAL_SEED=1 and --yes-local is passed.

Run:
    docker exec -e ERP_LOCAL_SEED=1 -e PYTHONPATH=/app \
        erp-united-exploration-dev-backend-1 \
        python -m scripts.seed_payroll_test --yes-local
"""
import asyncio
import os
import sys
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash
from app.db.session import SessionLocal, engine
from app.models.attendance import Attendance
from app.models.employee import Employee
from app.models.leave import LeaveRequest, LeaveStatus, LeaveType
from app.models.salary_component import SalaryComponent
from app.models.salary_template import SalaryTemplate, SalaryTemplateComponent
from app.models.user import Role, User

PASSWORD = "test@12345"
ATTENDANCE_DAYS_BACK = int(os.environ.get("PAYROLL_SEED_DAYS_BACK", "62"))  # ~2 months

# email, full_name, basic, employment_type, allowances(dict|None), template_code|None
TEST_EMPLOYEES = [
    ("pay.staff1@test.com", "Pay Staff One", 45000, "permanent", None, None),
    ("pay.staff2@test.com", "Pay Staff Two", 9000, "permanent", None, None),
    ("pay.senior@test.com", "Pay Senior", 150000, "permanent", None, None),
    ("pay.contractor@test.com", "Pay Contractor", 60000, "contractual", None, None),
    ("pay.templated@test.com", "Pay Templated", 50000, "permanent", None, "standard_staff"),
    ("pay.explicit@test.com", "Pay Explicit", 30000, "permanent",
     {"hra": 15000, "conveyance_allowance": 5000, "other_allowance": 4000}, None),
]

# Give the existing demo employees salaries too (email -> basic).
EXISTING_SALARIES = {
    "employee@gmail.com": 35000,
    "pm@gmail.com": 70000,
    "hr@gmail.com": 55000,
}


def _guard():
    if os.environ.get("ERP_LOCAL_SEED") != "1" or "--yes-local" not in sys.argv:
        print("Refusing to run: set ERP_LOCAL_SEED=1 and pass --yes-local")
        sys.exit(1)


async def _get_or_create_user(db: AsyncSession, email: str, full_name: str) -> User:
    u = (await db.execute(select(User).where(User.email == email))).scalars().first()
    if u:
        return u
    u = User(
        email=email, full_name=full_name, is_active=True, is_superuser=False,
        hashed_password=get_password_hash(PASSWORD),
    )
    # Attach a default non-privileged role if one exists (login niceness).
    role = (await db.execute(
        select(Role).where(Role.name.in_(["Employee", "Staff"]))
    )).scalars().first()
    if role:
        u.roles = [role]
    db.add(u)
    await db.flush()
    print(f"  + user {email}")
    return u


async def _upsert_employee(db, user, basic, etype, allowances, template_id):
    emp = (await db.execute(
        select(Employee).where(Employee.user_id == user.id)
    )).scalars().first()
    if emp is None:
        emp = Employee(
            user_id=user.id, employee_id=f"PAY-{user.id}",
            department="Engineering", designation="Specialist",
            date_of_joining=date(2024, 1, 1), status="active",
        )
        db.add(emp)
    emp.salary = basic
    emp.employment_type = etype
    emp.salary_template_id = template_id
    # Explicit allowances if given, else NULL (payroll applies 30/50/20 ratio).
    emp.conveyance_allowance = (allowances or {}).get("conveyance_allowance")
    emp.hra = (allowances or {}).get("hra")
    emp.other_allowance = (allowances or {}).get("other_allowance")
    await db.flush()
    return emp


async def _ensure_standard_template(db) -> int:
    """A template mirroring the legacy 30/50/20 structure (basic uses the
    employee's own salary; allowances are percent_of_basic)."""
    tmpl = (await db.execute(
        select(SalaryTemplate).where(SalaryTemplate.code == "standard_staff")
    )).scalars().first()
    if tmpl is None:
        tmpl = SalaryTemplate(code="standard_staff", name="Standard Staff (30/50/20)",
                              description="Legacy-equivalent structure", is_active=True)
        db.add(tmpl)
        await db.flush()
        comps = {c.code: c.id for c in (await db.execute(
            select(SalaryComponent).where(SalaryComponent.code.in_(
                ["conveyance", "hra", "other"]))
        )).scalars().all()}
        for code, pct, order in [("conveyance", 30.0, 1), ("hra", 50.0, 2), ("other", 20.0, 3)]:
            db.add(SalaryTemplateComponent(
                template_id=tmpl.id, component_id=comps[code],
                calc_method="percent_of_basic", percent=pct, display_order=order,
            ))
        await db.flush()
        print(f"  + salary template 'standard_staff' (id {tmpl.id})")
    return tmpl.id


async def _seed_attendance(db, user_ids: list[int]):
    today = datetime.now(timezone.utc).date()
    created = 0
    for uid in user_ids:
        existing = {
            r for (r,) in (await db.execute(
                select(Attendance.work_date).where(Attendance.user_id == uid)
            )).all()
        }
        for d in range(ATTENDANCE_DAYS_BACK):
            day = today - timedelta(days=d)
            if day.weekday() >= 5:  # skip Sat/Sun
                continue
            if day in existing:
                continue
            punch_in = datetime.combine(day, time(9, 5), tzinfo=timezone.utc)
            punch_out = datetime.combine(day, time(17, 35), tzinfo=timezone.utc)
            db.add(Attendance(
                user_id=uid, mode="web", captured_at=punch_in,
                punch_out_time=punch_out, work_date=day,
                is_cross_midnight=False, attribution_flag=None,
            ))
            created += 1
    await db.flush()
    print(f"  attendance rows created: {created} (last {ATTENDANCE_DAYS_BACK} days, weekdays)")


async def _seed_lop_leave(db, user_id: int):
    """3 approved unpaid (Loss of Pay) days this month for one employee, so a
    payroll draft shows prorated pay (payable_days < days_in_month)."""
    lop = (await db.execute(
        select(LeaveType).where(LeaveType.unpaid_allowed.is_(True))
    )).scalars().first()
    if lop is None:
        print("  ! no unpaid leave type found — skipping LOP case")
        return
    today = datetime.now(timezone.utc).date()
    start = today.replace(day=10)
    end = today.replace(day=12)
    exists = (await db.execute(
        select(LeaveRequest).where(
            LeaveRequest.employee_id == user_id,
            LeaveRequest.leave_type_id == lop.id,
            LeaveRequest.start_date == start,
        )
    )).scalars().first()
    if exists:
        return
    db.add(LeaveRequest(
        employee_id=user_id, leave_type_id=lop.id,
        start_date=start, end_date=end, is_half_day=False,
        reason="Payroll test — unpaid LOP", status=LeaveStatus.APPROVED,
        created_by_user_id=user_id,
    ))
    await db.flush()
    print(f"  + LOP leave {start}..{end} for user {user_id}")


async def main():
    _guard()
    async with SessionLocal() as db:
        template_id = await _ensure_standard_template(db)

        seeded_user_ids = []
        lop_target = None
        for email, name, basic, etype, allow, tcode in TEST_EMPLOYEES:
            user = await _get_or_create_user(db, email, name)
            tid = template_id if tcode == "standard_staff" else None
            await _upsert_employee(db, user, basic, etype, allow, tid)
            seeded_user_ids.append(user.id)
            if email == "pay.staff2@test.com":
                lop_target = user.id
            print(f"  = {email:26s} basic={basic:>7} {etype:11s} "
                  f"{'template' if tid else ('explicit' if allow else 'ratio')}")

        # Existing demo employees get salaries so no zero-pay lines.
        for email, basic in EXISTING_SALARIES.items():
            user = (await db.execute(select(User).where(User.email == email))).scalars().first()
            if not user:
                continue
            emp = (await db.execute(
                select(Employee).where(Employee.user_id == user.id)
            )).scalars().first()
            if emp:
                emp.salary = basic
                await db.flush()
                seeded_user_ids.append(user.id)

        await _seed_attendance(db, seeded_user_ids)
        if lop_target:
            await _seed_lop_leave(db, lop_target)

        await db.commit()

        n = (await db.execute(
            select(Employee).where(Employee.status == "active")
        )).scalars().all()
        print(f"\nDONE. Active employees now in payroll scope: {len(n)}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
