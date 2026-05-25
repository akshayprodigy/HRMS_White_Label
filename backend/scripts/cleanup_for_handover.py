"""
Cleanup script for production handover.

Removes all demo/test data while preserving:
- 3 super admin users
- Roles & permissions (and their associations)
- Bid line items, Leave types, Departments, Holidays, Policies, System settings

Run via:
  docker compose -f docker-compose.prod.yml exec -T -w /app -e PYTHONPATH=/app backend python scripts/cleanup_for_handover.py
"""

import asyncio
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


KEEP_EMAILS = {
    "admin@gmail.com",
    "admin@unitedexploration.co.in",
    "admin@innocorelabs.com",
}


async def cleanup():
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import select, text

    from app.core.config import settings
    from app.models.user import User

    engine = create_async_engine(settings.SQLALCHEMY_DATABASE_URI)
    AsyncSessionLocal = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with AsyncSessionLocal() as session:
        # Get IDs of admin users to keep
        result = await session.execute(
            select(User.id, User.email).where(
                User.email.in_(KEEP_EMAILS)
            )
        )
        keep_users = {row.id: row.email for row in result.all()}
        keep_ids = set(keep_users.keys())

        if not keep_ids:
            print("ERROR: No admin users found. Aborting.")
            return

        print(f"Keeping {len(keep_ids)} admin users: {list(keep_users.values())}")
        placeholders = ",".join(str(uid) for uid in keep_ids)

        # Tables to DELETE FROM in FK-safe order.
        # Using actual DB table names from SHOW TABLES.
        tables_to_clear = [
            # Payroll & Salary
            "salarydisbursement",
            "advancerecovery",
            "payslip",
            "payrollline",
            "payrollrun",
            "salaryadvance",

            # Attendance & Time
            "attendancecorrectionrequest",
            "attendance",
            "timeentry",
            "timer_session",

            # Tasks & Projects
            "task_completion_document",
            "task_completion_request",
            "taskattachment",
            "taskcomment",
            "subtask",
            "task",
            "costchangerequest",
            "costbaseline",
            "milestone",
            "project_member",
            "project",

            # BD & Leads
            "lead_bid_task_review_line",
            "lead_bid_task_review",
            "bid_task_assignment_document",
            "lead_bid_task_assignment",
            "lead_bid_task",
            "quotationversion",
            "proposalsnapshot",
            "estimateresourceline",
            "estimatephase",
            "estimateversion",
            "bd_activity_log",
            "lead_document",
            "lead",
            "client_details",
            "contact",
            "account",

            # Recruitment & Onboarding
            "onboardingtask",
            "onboardingprocess",
            "interview",
            "applicant",
            "manpowerrequisition",

            # Exit Management
            "clearanceitem",
            "clearancerequest",
            "exitinterview",
            "resignation",

            # Leave
            "leaverequest",
            "leavebalanceledger",

            # HR
            "policyacknowledgement",
            "employeeletter",

            # Approvals & Audit
            "approvalstep",
            "approvalitem",
            "notification",
            "auditlog",

            # Employee records
            "employee",
        ]

        print("\nCleaning up data tables...")
        for table in tables_to_clear:
            try:
                result = await session.execute(
                    text(f"DELETE FROM `{table}`")
                )
                count = result.rowcount
                if count > 0:
                    print(f"  {table}: deleted {count} rows")
            except Exception as e:
                err_msg = str(e).split("\n")[0]
                print(f"  {table}: SKIP ({err_msg})")

        # Delete non-admin users
        await session.execute(
            text(
                f"DELETE FROM user_roles WHERE user_id NOT IN ({placeholders})"
            )
        )
        result = await session.execute(
            text(f"DELETE FROM `user` WHERE id NOT IN ({placeholders})")
        )
        print(f"  user: deleted {result.rowcount} non-admin users")

        await session.commit()

        print("\nCleanup complete! Database is ready for handover.")
        print("Preserved: 3 super admins, roles, permissions,")
        print("  bid line items, leave types, departments,")
        print("  holidays, policies, system settings.")


if __name__ == "__main__":
    asyncio.run(cleanup())
