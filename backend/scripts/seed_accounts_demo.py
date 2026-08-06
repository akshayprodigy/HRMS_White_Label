"""Seed / RESET demo data for the Accounts section demo (F6 + W13).

Idempotent AND resetting — re-running never duplicates, and it puts any
already-created demo items BACK into their demo-ready (awaiting-Accounts)
state. So after you click Approve/Verify during a demo, just run this again
to reset for the next run. Populates the four things Accounts screens show:
  1. Accounts — Payroll Approval : a payroll run in FINALIZED status
  2. Payout Verification / Expenses : an APPROVED expense claim
  3. Payout Verification / Travel : an APPROVED travel request w/ advance
  4. Payout Verification / Salary Advances : a PENDING_ACCOUNTS advance

Run:  docker exec erp-united-exploration-dev-backend-1 python -m scripts.seed_accounts_demo
"""
import asyncio
from datetime import datetime, date, timezone, timedelta

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.session import SessionLocal
from app.models.employee import Employee, EmployeeStatus
from app.models.user import User
from app.models.payroll import PayrollRun, PayrollRunStatus
from app.models.expense import (
    ExpenseClaim, ExpenseClaimStatus, ExpenseLineItem,
    TravelRequest, TravelRequestStatus,
)
from app.models.salary_advance import SalaryAdvance, AdvanceStatus

EXPENSE_TITLE = "DEMO: Client visit reimbursement"
TRAVEL_PURPOSE = "DEMO: Vendor site audit"
ADVANCE_REMARK = "DEMO: medical advance"


async def main():
    async with SessionLocal() as db:
        now = datetime.now(timezone.utc)
        today = date.today()
        report = []

        # An approver user (HR/admin) for approved_by fields.
        approver = (await db.execute(
            select(User).where(User.is_superuser.is_(True))
        )).scalars().first()
        approver_id = approver.id if approver else 1

        # A few active employees.
        emps = (await db.execute(
            select(Employee).options(selectinload(Employee.user))
            .where(Employee.status == EmployeeStatus.ACTIVE).limit(5)
        )).scalars().all()
        if not emps:
            print("No active employees — cannot seed."); return

        # 1) Ensure a payroll run is FINALIZED (awaiting Accounts). Reset the
        #    demo run back to FINALIZED if a previous demo already approved it.
        run = (await db.execute(
            select(PayrollRun).where(
                PayrollRun.status.in_([
                    PayrollRunStatus.FINALIZED,
                    PayrollRunStatus.ACCOUNTS_APPROVED,
                    PayrollRunStatus.DRAFT_GENERATED,
                ])
            ).order_by(PayrollRun.year.desc(), PayrollRun.month.desc())
        )).scalars().first()
        if run:
            was = run.status
            run.status = PayrollRunStatus.FINALIZED
            run.finalized_at = run.finalized_at or now
            run.accounts_approved_at = None
            run.accounts_approved_by_id = None
            report.append(
                f"payroll: run {run.month}/{run.year} (id {run.id}) set FINALIZED "
                f"(was {was}) → awaiting Accounts approval"
            )
        else:
            report.append("payroll: no eligible run to finalize (skip)")

        # 2) Approved expense claim awaiting Accounts.
        exists = (await db.execute(
            select(ExpenseClaim).where(ExpenseClaim.title == EXPENSE_TITLE)
        )).scalars().first()
        if exists:
            exists.status = ExpenseClaimStatus.APPROVED
            exists.accounts_verified_at = None
            exists.accounts_verified_by_id = None
            report.append(f"expense: reset id {exists.id} → APPROVED (awaiting Accounts)")
        else:
            emp = emps[0]
            claim = ExpenseClaim(
                employee_id=emp.id,
                submitter_id=emp.user_id,
                title=EXPENSE_TITLE,
                description="Cab + meals during client visit",
                claim_date=today - timedelta(days=3),
                total_amount_paise=485000,  # ₹4,850
                status=ExpenseClaimStatus.APPROVED,
                submitted_at=now - timedelta(days=2),
            )
            claim.line_items = [
                ExpenseLineItem(
                    amount_paise=320000, line_date=today - timedelta(days=3),
                    description="Intercity cab",
                ),
                ExpenseLineItem(
                    amount_paise=165000, line_date=today - timedelta(days=3),
                    description="Client lunch",
                ),
            ]
            db.add(claim)
            report.append(
                f"expense: created APPROVED claim for "
                f"{emp.user.full_name if emp.user else emp.id} (₹4,850)"
            )

        # 3) Approved travel request with an unpaid advance.
        exists_t = (await db.execute(
            select(TravelRequest).where(TravelRequest.purpose == TRAVEL_PURPOSE)
        )).scalars().first()
        if exists_t:
            exists_t.status = TravelRequestStatus.APPROVED
            exists_t.advance_paid_at = None
            exists_t.advance_paid_paise = 0
            exists_t.accounts_verified_by_id = None
            report.append(f"travel: reset id {exists_t.id} → APPROVED (advance unpaid)")
        else:
            emp = emps[1 % len(emps)]
            tr = TravelRequest(
                employee_id=emp.id,
                submitter_id=emp.user_id,
                purpose=TRAVEL_PURPOSE,
                from_city="Kolkata",
                to_city="Pune",
                start_date=today + timedelta(days=5),
                end_date=today + timedelta(days=8),
                estimated_cost_paise=2500000,   # ₹25,000
                advance_requested_paise=1500000,  # ₹15,000
                advance_paid_paise=0,
                advance_paid_at=None,
                status=TravelRequestStatus.APPROVED,
                submitted_at=now - timedelta(days=1),
            )
            db.add(tr)
            report.append(
                f"travel: created APPROVED request for "
                f"{emp.user.full_name if emp.user else emp.id} "
                f"(advance ₹15,000, Kolkata→Pune)"
            )

        # 4) Salary advance pending Accounts verification.
        exists_a = (await db.execute(
            select(SalaryAdvance).where(SalaryAdvance.remarks == ADVANCE_REMARK)
        )).scalars().first()
        if exists_a:
            exists_a.status = AdvanceStatus.PENDING_ACCOUNTS
            exists_a.accounts_verified_at = None
            exists_a.accounts_verified_by_id = None
            report.append(f"advance: reset id {exists_a.id} → PENDING_ACCOUNTS")
        else:
            emp = emps[2 % len(emps)]
            adv = SalaryAdvance(
                employee_id=emp.id,
                amount=20000.0,
                reason="Medical emergency — family",
                disbursed_date=now,
                recovery_mode="installment",
                installment_months=4,
                recovered_amount=0.0,
                status=AdvanceStatus.PENDING_ACCOUNTS,
                approved_by_id=approver_id,
                remarks=ADVANCE_REMARK,
            )
            db.add(adv)
            report.append(
                f"advance: created PENDING_ACCOUNTS advance for "
                f"{emp.user.full_name if emp.user else emp.id} (₹20,000)"
            )

        await db.commit()
        print("\n=== Accounts demo seed ===")
        for line in report:
            print("  •", line)
        print("Done.\n")


if __name__ == "__main__":
    asyncio.run(main())
