import asyncio
import sys
import os
from datetime import date
from sqlalchemy import select, and_

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from app.db.session import SessionLocal
from app.models.user import User
from app.models.payroll import PayrollRun, PayrollLine, PayrollRunStatus
from app.models.leave import LeaveRequest, LeaveType
from app.models.approval import ApprovalStatus

async def test_payroll_for_employee():
    async with SessionLocal() as db:
        print("--- STARTING PAYROLL TEST SCENARIO ---")
        
        # 1. Get Demo Employee
        employee_email = "employee@gmail.com"
        result = await db.execute(select(User).where(User.email == employee_email))
        employee = result.scalar_one_or_none()
        
        if not employee:
            print(f"Employee {employee_email} not found. Consider running seed_demo_users.py first.")
            return
        
        # Ensure employee has some salary set if model supports it, 
        # but let's just use 50000.0 as a constant for calculation
        base_salary = 50000.0
        print(f"Target Employee: {employee.full_name} (Email: {employee.email})")

        # 2. Setup Unpaid Leave (LOP) for the month
        lt_result = await db.execute(select(LeaveType).where(LeaveType.unpaid_allowed == True))
        unpaid_type = lt_result.scalar_one_or_none()
        if not unpaid_type:
            unpaid_type = LeaveType(name="Unpaid Leave", unpaid_allowed=True)
            db.add(unpaid_type)
            await db.flush()

        # Add 2 LOP days: March 10 to March 11, 2026
        target_month = 3
        target_year = 2026
        
        lop_leave = LeaveRequest(
            employee_id=employee.id,
            leave_type_id=unpaid_type.id,
            start_date=date(target_year, target_month, 10),
            end_date=date(target_year, target_month, 11),
            status=ApprovalStatus.APPROVED.value if hasattr(ApprovalStatus.APPROVED, "value") else ApprovalStatus.APPROVED,
            reason="LOP Test",
            created_by_user_id=employee.id
        )
        db.add(lop_leave)
        await db.flush()
        print(f"Added 2 days of APPROVED Unpaid Leave for {target_month}/{target_year}.")

        # 3. Create Payroll Run
        # Delete existing for same period to be idempotent
        pr_result = await db.execute(
            select(PayrollRun).where(
                and_(PayrollRun.month == target_month, PayrollRun.year == target_year)
            )
        )
        existing_runs = pr_result.scalars().all()
        for r in existing_runs:
            await db.delete(r)
        await db.flush()

        payroll_run = PayrollRun(
            month=target_month,
            year=target_year,
            status=PayrollRunStatus.DRAFT
        )
        db.add(payroll_run)
        await db.flush()

        # 4. Calculation
        days_in_month = 31 # March
        lop_days = 2.0
        payable_days = days_in_month - lop_days
        gross_pay = (base_salary / days_in_month) * payable_days
        
        line = PayrollLine(
            payroll_run_id=payroll_run.id,
            user_id=employee.id,
            base_salary=base_salary,
            lop_days=lop_days,
            payable_days=payable_days,
            gross_pay=round(gross_pay, 2),
            net_pay=round(gross_pay, 2)
        )
        db.add(line)
        await db.commit()
        
        print("\n--- TEST RESULTS ---")
        print(f"Employee: {employee.full_name}")
        print(f"Month/Year: {target_month}/{target_year}")
        print(f"LOP Days: {line.lop_days}")
        print(f"Payable Days: {line.payable_days}/{days_in_month}")
        print(f"Base Salary: {line.base_salary}")
        print(f"Calculated Gross: {line.gross_pay}")
        print("-------------------------------")
        print("SCENARIO COMPLETED")

if __name__ == "__main__":
    asyncio.run(test_payroll_for_employee())
