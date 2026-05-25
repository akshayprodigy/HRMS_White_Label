import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from app.models.user import User, Role, Permission
from app.models.attendance import Attendance
from app.models.timesheet import TimeEntry
from app.models.employee import Employee
from app.models.leave import LeaveType, LeaveBalanceLedger, LeaveRequest
from app.models.approval import ApprovalItem, ApprovalStep
from app.models.project import Project, ProjectMember
from app.models.task import Task, Subtask, TaskComment, TaskAttachment
from app.models.audit import AuditLog
from app.core.config import settings

async def seed_hr_permissions():
    engine = create_async_engine(settings.SQLALCHEMY_DATABASE_URI)
    AsyncSessionLocal = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with AsyncSessionLocal() as session:
        # 1. New Permissions
        perms_to_create = [
            {
                "name": "hr employee read",
                "description": "View employee directory"
            },
            {
                "name": "hr employee write",
                "description": "Manage employee master data"
            },
            {
                "name": "hr role assign",
                "description": "Assign roles to employees",
            },
            {
                "name": "hr payroll run",
                "description": "Create and operate payroll runs"
            },
            {
                "name": "hr payroll approve",
                "description": "Approve payroll runs"
            },
            {
                "name": "hr payroll view",
                "description": "View salary and bank details"
            },
            {
                "name": "hr payroll write",
                "description": "Manage salary and bank details"
            }
        ]
        
        db_perms = {}
        for p_data in perms_to_create:
            result = await session.execute(
                select(Permission).where(Permission.name == p_data["name"])
            )
            perm = result.scalars().first()
            if not perm:
                perm = Permission(**p_data)
                session.add(perm)
            db_perms[p_data["name"]] = perm
        
        await session.flush()

        # 2. Assign to HR Role
        result = await session.execute(
            select(Role).where(Role.name == "HR")
        )
        hr_role = result.scalars().first()
        
        if hr_role:
            # Add new permissions without removing existing ones
            existing_perm_names = {p.name for p in hr_role.permissions}
            for p_name, perm in db_perms.items():
                if p_name not in existing_perm_names:
                    hr_role.permissions.append(perm)
        
        await session.commit()
    print("HR permissions seeded successfully")

if __name__ == "__main__":
    asyncio.run(seed_hr_permissions())
