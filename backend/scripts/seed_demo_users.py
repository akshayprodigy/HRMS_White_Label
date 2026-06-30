import asyncio
import os
import sys
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, selectinload
from sqlalchemy import select
from datetime import date
import gc


async def seed_demo_roles():
    # Allow running this script directly (e.g. `python scripts/seed_demo_users.py`)
    # without requiring a pre-set PYTHONPATH.
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

    from app.core.config import settings
    from app.core.security import get_password_hash
    from app.models.employee import Employee, EmployeeStatus
    from app.models.leave import LeaveType, LeaveBalanceLedger
    from app.models.user import Permission, Role, User

    engine = create_async_engine(settings.SQLALCHEMY_DATABASE_URI)
    AsyncSessionLocal = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with AsyncSessionLocal() as session:
        # 1. Ensure Permissions exist
        perms_to_create = [
            {
                "name": "client read",
                "description": "List/search clients for selection",
            },
            {
                "name": "client create",
                "description": "Create new client records",
            },
            {
                "name": "client write",
                "description": "Update client records",
            },
            {"name": "employee leave read", "description": "View own leaves"},
            {"name": "employee leave write", "description": "Apply/Cancel own leaves"},
            {"name": "leave approve", "description": "Approve/Reject leaves"},
            {"name": "employee time read", "description": "Read own time logs"},
            {"name": "employee time write", "description": "Write own time logs"},
            {
                "name": "project write",
                "description": "Manage projects and milestones",
            },
            {"name": "hr employee read", "description": "Read all employees"},
            {"name": "hr employee write", "description": "Create/Update employees"},
            {
                "name": "hr role assign",
                "description": "Assign roles to employees",
            },
            {
                "name": "hr payroll run",
                "description": "Create and operate payroll runs",
            },
            {
                "name": "hr payroll approve",
                "description": "Approve payroll runs",
            },
            {
                "name": "hr payroll view",
                "description": "View payroll sensitive info",
            },
            {
                "name": "hr payroll write",
                "description": "Edit payroll sensitive info",
            },
            {"name": "admin access", "description": "Access admin console"},
            {"name": "bd lead read", "description": "Read business leads"},
            {"name": "bd lead write", "description": "Create/Update leads"},
            {"name": "bd estimate read", "description": "Read estimates"},
            {"name": "bd estimate write", "description": "Create/Update estimates"},
            {
                "name": "lead estimate approve",
                "description": "Approve lead estimate values",
            },
            {
                "name": "bd bid task read",
                "description": "Read lead bid tasks and assignments",
            },
            {
                "name": "bd bid task write",
                "description": "Create and assign lead bid tasks",
            },
            {
                "name": "bd bid review read",
                "description": "Read PM bid reviews for a lead",
            },
            {
                "name": "bd bid review write",
                "description": "Create/update/submit PM bid reviews",
            },
            {"name": "bd convert to project", "description": "Convert lead to project"},
            {"name": "bd report view", "description": "View BD reports"},
            {"name": "executive report view", "description": "View executive reports"},
            {"name": "recruitment read", "description": "Read recruitment requisitions"},
            {"name": "recruitment write", "description": "Submit recruitment requisitions"},
            {"name": "recruitment approve", "description": "Approve recruitment requisitions"},
            {"name": "project coo view", "description": "View all projects across portfolio (COO)"},
            {"name": "coo dashboard view", "description": "Access COO operations hub dashboard"},
            {"name": "shift template write", "description": "Create/Update/Delete shift templates"},
            {"name": "shift assign", "description": "Assign shifts to employees (single + bulk)"},
            {"name": "geo fence write", "description": "Manage geo-fence locations and per-employee allowlist/mode"},
            {"name": "overtime rule write", "description": "Manage OT + night-shift allowance rules, run recompute"},
            {"name": "overtime approve", "description": "Approve/reject employee OT entries"},
            {"name": "overtime view all", "description": "View OT/night entries across all employees"},
            {"name": "designation master write", "description": "Manage Designation + Grade master"},
            {"name": "revision write", "description": "Create / edit / submit salary revisions"},
            {"name": "revision approve", "description": "Approve non-promotion revisions (mgr/dept-head/HR)"},
            {"name": "revision approve hr", "description": "Approve PROMOTION revisions (HR / CEO authority)"},
            {"name": "revision apply", "description": "Manually apply an approved revision (HR)"},
            {"name": "revision view all", "description": "View all employees' compensation history"},
            {"name": "statutory config write", "description": "Manage PF/ESIC config + employer + PT slabs"},
            {"name": "statutory generate", "description": "Generate PF ECR / ESIC / PT exports + update filing status"},
            {"name": "statutory view", "description": "View statutory filings, reconciliation + compliance dashboard"},
        ]
        
        db_perms = {}
        for p_data in perms_to_create:
            result = await session.execute(select(Permission).where(Permission.name == p_data["name"]))
            perm = result.scalars().first()
            if not perm:
                perm = Permission(**p_data)
                session.add(perm)
            db_perms[p_data["name"]] = perm
        
        await session.flush()

        # 2. Ensure Roles exist
        roles_to_create = [
            {"name": "HR", "description": "Human Resources Management"},
            {"name": "PM", "description": "Project Management"},
            {"name": "Employee", "description": "Standard Employee Access"},
            {"name": "Super Admin", "description": "Unrestricted Access"},
            {"name": "Business Developer", "description": "Sales and Lead Management"},
            {"name": "CEO", "description": "Executive Overview Access"},
            {"name": "COO", "description": "Chief Operating Officer — cross-project oversight"},
            {"name": "BD MANAGER", "description": "Business Development Approval Authority"},
            {"name": "DEPT_HEAD", "description": "Departmental Management & Requisition Authority"},
            {"name": "RECRUITER", "description": "Talent Acquisition & Pipeline Management"}
        ]

        db_roles = {}
        for r_name, r_desc in [
            ("HR", "Human Resources Management"),
            ("PM", "Project Management"),
            ("Employee", "Standard Employee Access"),
            ("Super Admin", "Unrestricted Access"),
            ("Business Developer", "Sales and Lead Management"),
            ("CEO", "Executive Overview Access"),
            ("COO", "Chief Operating Officer — cross-project oversight"),
            ("BD MANAGER", "Business Development Approval Authority"),
            ("DEPT_HEAD", "Departmental Management & Requisition Authority"),
            ("RECRUITER", "Talent Acquisition & Pipeline Management")
        ]:
            result = await session.execute(
                select(Role).where(Role.name == r_name)
            )
            role = result.scalars().first()
            if not role:
                role = Role(name=r_name, description=r_desc)
                session.add(role)
                await session.flush()
            
            # Explicitly load permissions to avoid MissingGreenlet
            await session.refresh(role, ["permissions"])
            db_roles[r_name] = role

        # Assign permissions to roles
        db_roles["Employee"].permissions = [
            db_perms["employee leave read"],
            db_perms["employee leave write"],
            db_perms["employee time read"],
            db_perms["employee time write"]
        ]
        db_roles["HR"].permissions = [
            db_perms["employee leave read"],
            db_perms["employee leave write"],
            db_perms["leave approve"],
            db_perms["employee time read"],
            db_perms["hr employee read"],
            db_perms["hr employee write"],
            db_perms["hr role assign"],
            db_perms["hr payroll run"],
            db_perms["hr payroll approve"],
            db_perms["hr payroll view"],
            db_perms["hr payroll write"],
            db_perms["recruitment read"],
            db_perms["recruitment write"],
            db_perms["recruitment approve"],
            db_perms["shift template write"],
            db_perms["shift assign"],
            db_perms["geo fence write"],
            db_perms["overtime rule write"],
            db_perms["overtime approve"],
            db_perms["overtime view all"],
            db_perms["designation master write"],
            db_perms["revision write"],
            db_perms["revision approve"],
            db_perms["revision approve hr"],
            db_perms["revision apply"],
            db_perms["revision view all"],
            db_perms["statutory config write"],
            db_perms["statutory generate"],
            db_perms["statutory view"],
        ]
        db_roles["PM"].permissions = [
            db_perms["employee leave read"],
            db_perms["employee leave write"],
            db_perms["leave approve"],
            db_perms["employee time read"],
            db_perms["project write"],
            db_perms["bd lead read"],
            db_perms["bd bid task read"],
            db_perms["bd bid review read"],
            db_perms["bd bid review write"],
            db_perms["bd estimate read"],
            db_perms["bd estimate write"],
            db_perms["shift assign"],
            # PM approves OT for their team via the centralised inbox.
            db_perms["overtime approve"],
            # PM is step-1 approver on non-promotion revisions.
            db_perms["revision approve"],
            db_perms["revision view all"],
        ]
        db_roles["Super Admin"].permissions = [
            db_perms["admin access"],
            db_perms["employee leave write"],
            db_perms["lead estimate approve"],
            db_perms["shift template write"],
            db_perms["shift assign"],
            db_perms["geo fence write"],
            db_perms["overtime rule write"],
            db_perms["overtime approve"],
            db_perms["overtime view all"],
            db_perms["designation master write"],
            db_perms["revision write"],
            db_perms["revision approve"],
            db_perms["revision approve hr"],
            db_perms["revision apply"],
            db_perms["revision view all"],
            db_perms["statutory config write"],
            db_perms["statutory generate"],
            db_perms["statutory view"],
        ]
        db_roles["Business Developer"].permissions = [
            db_perms["client read"],
            db_perms["client create"],
            db_perms["bd lead read"],
            db_perms["bd lead write"],
            db_perms["bd bid task read"],
            db_perms["bd bid task write"],
            db_perms["bd bid review read"],
            db_perms["bd estimate read"],
            db_perms["bd estimate write"],
            db_perms["bd convert to project"],
            db_perms["bd report view"],
            db_perms["employee leave read"],
            db_perms["employee leave write"],
            db_perms["employee time read"],
            db_perms["employee time write"]
        ]
        db_roles["CEO"].permissions = [
            db_perms["employee leave read"],
            db_perms["employee leave write"],
            db_perms["employee time read"],
            db_perms["hr employee read"],
            db_perms["hr payroll view"],
            db_perms["bd report view"],
            db_perms["executive report view"],
            db_perms["lead estimate approve"],
            db_perms["recruitment read"],
            db_perms["recruitment approve"],
            # CEO authorises promotions.
            db_perms["revision approve hr"],
            db_perms["revision view all"],
            # CEO oversees compliance posture.
            db_perms["statutory view"],
        ]
        db_roles["DEPT_HEAD"].permissions = [
            db_perms["employee leave read"],
            db_perms["employee leave write"],
            db_perms["employee time read"],
            db_perms["recruitment read"],
            db_perms["recruitment write"],
            db_perms["shift assign"],
            db_perms["overtime approve"],
            db_perms["revision approve"],
        ]
        db_roles["RECRUITER"].permissions = [
            db_perms["employee leave read"],
            db_perms["employee leave write"],
            db_perms["hr employee read"],
            db_perms["recruitment read"],
            db_perms["recruitment write"],
            db_perms["recruitment approve"]
        ]
        db_roles["COO"].permissions = [
            db_perms["project coo view"],
            db_perms["coo dashboard view"],
            db_perms["project write"],
            db_perms["bd lead read"],
            db_perms["bd bid task read"],
            db_perms["bd bid review read"],
            db_perms["executive report view"],
            db_perms["employee leave read"],
            db_perms["employee leave write"],
            db_perms["employee time read"],
            db_perms["hr employee read"],
        ]
        db_roles["BD MANAGER"].permissions = [
            db_perms["bd lead read"],
            db_perms["bd lead write"],
            db_perms["bd bid task read"],
            db_perms["bd bid task write"],
            db_perms["bd bid review read"],
            db_perms["bd estimate read"],
            db_perms["bd estimate write"],
            db_perms["lead estimate approve"],
            db_perms["bd report view"],
            db_perms["bd convert to project"],
            db_perms["employee leave read"],
            db_perms["employee leave write"],
        ]

        # 3. Define Demo Users
        demo_users = [
            {"email": "hr@gmail.com", "full_name": "Demo HR", "role": "HR"},
            {"email": "pm@gmail.com", "full_name": "Demo PM", "role": "PM"},
            {"email": "employee@gmail.com", "full_name": "Demo Employee", "role": "Employee"},
            {"email": "admin@gmail.com", "full_name": "Demo Admin", "role": "Super Admin", "is_superuser": True},
            {"email": "admin@unitedexploration.co.in", "full_name": "UE Admin", "role": "Super Admin", "is_superuser": True},
            {"email": "admin@innocorelabs.com", "full_name": "ICL Admin", "role": "Super Admin", "is_superuser": True},
            {"email": "bd@gmail.com", "full_name": "Demo BD", "role": "Business Developer"},
            {"email": "ceo@gmail.com", "full_name": "United CEO", "role": ["CEO", "BD MANAGER"]},
            {"email": "coo@gmail.com", "full_name": "Demo COO", "role": "COO"},
        ]
        
        password = "test@12345"
        hashed_pw = get_password_hash(password)

        users = {}
        for u_data in demo_users:
            role_name = u_data.pop("role")
            is_super = u_data.pop("is_superuser", False)
            
            result = await session.execute(select(User).where(User.email == u_data["email"]))
            user = result.scalars().first()
            
            if not user:
                user = User(
                    **u_data,
                    hashed_password=hashed_pw,
                    is_active=True,
                    is_superuser=is_super
                )
                session.add(user)
                print(f"Created user: {u_data['email']}")
            else:
                user.hashed_password = hashed_pw
                user.is_superuser = is_super
                print(f"Updated user password: {u_data['email']}")
            
            # Explicitly set roles
            if isinstance(role_name, list):
                user.roles = [db_roles[rn] for rn in role_name]
            else:
                user.roles = [db_roles[role_name]]
            users[u_data["email"]] = user

        await session.flush()

        # Set manager for employee
        users["employee@gmail.com"].manager_id = users["pm@gmail.com"].id

        # 4. Seed Leave Types
        leave_types_data = [
            {"name": "Annual Leave", "description": "Paid annual vacation", "unpaid_allowed": False},
            {"name": "Sick Leave", "description": "Medical leave", "unpaid_allowed": False},
            {"name": "Loss of Pay", "description": "Unpaid leave", "unpaid_allowed": True}
        ]
        
        db_lts = {}
        for lt_data in leave_types_data:
            result = await session.execute(select(LeaveType).where(LeaveType.name == lt_data["name"]))
            lt = result.scalars().first()
            if not lt:
                lt = LeaveType(**lt_data)
                session.add(lt)
            db_lts[lt_data["name"]] = lt
        
        await session.flush()

        # 5. Seed Balances
        for u_email in ["employee@gmail.com", "pm@gmail.com", "hr@gmail.com"]:
            user = users[u_email]
            
            # Create Employee profile if missing
            res_emp = await session.execute(select(Employee).where(Employee.user_id == user.id))
            if not res_emp.scalars().first():
                session.add(Employee(
                    user_id=user.id,
                    employee_id=f"EMP-{user.id:03d}",
                    department="Engineering" if u_email != "hr@gmail.com" else "Human Resources",
                    designation="Designer" if u_email == "pm@gmail.com" else "Specialist",
                    status=EmployeeStatus.ACTIVE,
                    date_of_joining=date(2024, 1, 1)
                ))

            for lt_name, bal in [("Annual Leave", 15.0), ("Sick Leave", 10.0), ("Loss of Pay", 0.0)]:
                lt = db_lts[lt_name]
                res = await session.execute(select(LeaveBalanceLedger).where(
                    LeaveBalanceLedger.user_id == user.id,
                    LeaveBalanceLedger.leave_type_id == lt.id
                ))
                if not res.scalars().first():
                    session.add(LeaveBalanceLedger(
                        user_id=user.id,
                        leave_type_id=lt.id,
                        balance=bal,
                        used=0.0
                    ))

        await session.commit()
        print("\nDemo seeding completed successfully.")

    # Ensure underlying connections are closed cleanly.
    await engine.dispose()
    # Encourage aiomysql objects to finalize before asyncio.run closes the loop.
    await asyncio.sleep(0)
    gc.collect()

if __name__ == "__main__":
    asyncio.run(seed_demo_roles())
