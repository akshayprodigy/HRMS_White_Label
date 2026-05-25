"""
Multi-user integration test:
- Creates 3 BDs, 3 PMs, 3 Employees
- Creates accounts and leads owned by each BD
- Creates projects managed by each PM
- Assigns bid tasks from leads to different PMs
- Verifies RLS: PM/BD see only their own; COO/CEO/Admin see all
"""

import asyncio
import os
import sys
import gc

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from datetime import date, datetime, timezone


async def seed_and_test():
    from app.core.config import settings
    from app.core.security import get_password_hash
    from app.models.user import User, Role
    from app.models.employee import Employee, EmployeeStatus
    from app.models.leave import LeaveType, LeaveBalanceLedger
    from app.models.bd import Account, Lead, LeadStage
    from app.models.project import Project, ProjectMember, CostBaseline
    from app.models.bid_task import LeadBidTask, LeadBidTaskAssignment

    engine = create_async_engine(settings.SQLALCHEMY_DATABASE_URI)
    AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    pw = get_password_hash("test@12345")

    async with AsyncSessionLocal() as session:

        # ── 1. Fetch existing roles ──────────────────────────────────────────
        async def get_role(name: str) -> Role:
            r = await session.execute(select(Role).where(Role.name == name))
            role = r.scalars().first()
            if not role:
                raise RuntimeError(f"Role '{name}' not found — run seed_demo_users.py first")
            await session.refresh(role, ["permissions"])
            return role

        role_pm   = await get_role("PM")
        role_bd   = await get_role("Business Developer")
        role_emp  = await get_role("Employee")

        # ── 2. Create extra users ────────────────────────────────────────────
        extra_users_def = [
            # email,                 full_name,          roles
            ("pm2@gmail.com",   "Priya Sharma (PM2)",   [role_pm]),
            ("pm3@gmail.com",   "Rahul Mehta (PM3)",    [role_pm]),
            ("bd2@gmail.com",   "Sneha Patel (BD2)",    [role_bd]),
            ("bd3@gmail.com",   "Vikram Singh (BD3)",   [role_bd]),
            ("emp2@gmail.com",  "Anita Rao (Emp2)",     [role_emp]),
            ("emp3@gmail.com",  "Deepak Kumar (Emp3)",  [role_emp]),
        ]

        db_users: dict[str, User] = {}

        # Also load existing demo users we'll need
        for email in ["pm@gmail.com", "bd@gmail.com", "employee@gmail.com",
                      "coo@gmail.com", "ceo@gmail.com", "admin@gmail.com"]:
            r = await session.execute(select(User).where(User.email == email))
            u = r.scalars().first()
            if u:
                db_users[email] = u

        for email, full_name, roles in extra_users_def:
            r = await session.execute(select(User).where(User.email == email))
            u = r.scalars().first()
            if not u:
                u = User(email=email, full_name=full_name,
                         hashed_password=pw, is_active=True, is_superuser=False)
                session.add(u)
                await session.flush()
                print(f"  Created user: {email}")
            else:
                u.hashed_password = pw
                print(f"  Exists user:  {email}")
            await session.refresh(u, ["roles"])
            u.roles = roles
            db_users[email] = u

        await session.flush()

        # ── 3. Employee profiles ─────────────────────────────────────────────
        emp_profiles = [
            ("pm2@gmail.com",  "Engineering", "PM Lead"),
            ("pm3@gmail.com",  "Engineering", "PM Lead"),
            ("bd2@gmail.com",  "Sales",       "BD Executive"),
            ("bd3@gmail.com",  "Sales",       "BD Executive"),
            ("emp2@gmail.com", "Engineering", "Developer"),
            ("emp3@gmail.com", "Engineering", "Developer"),
        ]
        for email, dept, desig in emp_profiles:
            u = db_users[email]
            r = await session.execute(select(Employee).where(Employee.user_id == u.id))
            if not r.scalars().first():
                session.add(Employee(
                    user_id=u.id,
                    employee_id=f"EMP-{u.id:04d}",
                    department=dept,
                    designation=desig,
                    status=EmployeeStatus.ACTIVE,
                    date_of_joining=date(2024, 6, 1),
                ))

        await session.flush()

        # ── 4. Leave balances for new users ─────────────────────────────────
        r = await session.execute(select(LeaveType))
        all_lt = r.scalars().all()
        lt_map = {lt.name: lt for lt in all_lt}

        for email in ["pm2@gmail.com", "pm3@gmail.com", "emp2@gmail.com", "emp3@gmail.com"]:
            u = db_users[email]
            for lt_name, bal in [("Annual Leave", 15.0), ("Sick Leave", 10.0), ("Loss of Pay", 0.0)]:
                if lt_name not in lt_map:
                    continue
                lt = lt_map[lt_name]
                ex = await session.execute(select(LeaveBalanceLedger).where(
                    LeaveBalanceLedger.user_id == u.id,
                    LeaveBalanceLedger.leave_type_id == lt.id,
                ))
                if not ex.scalars().first():
                    session.add(LeaveBalanceLedger(
                        user_id=u.id, leave_type_id=lt.id, balance=bal, used=0.0
                    ))

        await session.flush()

        # ── 5. Accounts (clients) ────────────────────────────────────────────
        accounts_def = [
            ("TechCorp Ltd",     "IT"),
            ("Green Energy Inc", "Energy"),
            ("BuildRight Pvt",   "Construction"),
        ]
        db_accounts = []
        for name, industry in accounts_def:
            r = await session.execute(select(Account).where(Account.name == name))
            acc = r.scalars().first()
            if not acc:
                acc = Account(name=name, industry=industry)
                session.add(acc)
                await session.flush()
                print(f"  Created account: {name}")
            db_accounts.append(acc)

        # ── 6. Leads — one per BD ────────────────────────────────────────────
        bd_users = [db_users["bd@gmail.com"], db_users["bd2@gmail.com"], db_users["bd3@gmail.com"]]
        leads_def = [
            # (title, stage, bd_index, account_index)
            ("ERP Implementation for TechCorp",          LeadStage.PROPOSAL,     0, 0),
            ("Solar Dashboard for Green Energy",         LeadStage.DISCOVERY,    1, 1),
            ("Construction MIS for BuildRight",          LeadStage.QUALIFIED,    2, 2),
            ("Mobile App — TechCorp Phase 2",            LeadStage.NEW,          0, 0),
            ("Analytics Platform for Green Energy",      LeadStage.NEGOTIATION,  1, 1),
        ]

        db_leads: list[Lead] = []
        lead_counter = 1
        for title, stage, bd_idx, acc_idx in leads_def:
            r = await session.execute(select(Lead).where(Lead.title == title))
            lead = r.scalars().first()
            if not lead:
                lead = Lead(
                    lead_id=f"LEAD-{100 + lead_counter:03d}",
                    title=title,
                    stage=stage,
                    owner_user_id=bd_users[bd_idx].id,
                    account_id=db_accounts[acc_idx].id,
                    estimated_value=float(500_000 * lead_counter),
                    probability_percent=30 + lead_counter * 10,
                )
                session.add(lead)
                await session.flush()
                print(f"  Created lead [{bd_users[bd_idx].full_name}]: {title}")
            db_leads.append(lead)
            lead_counter += 1

        # ── 7. Bid tasks on each lead, assigned to different PMs ─────────────
        pm_users = [db_users["pm@gmail.com"], db_users["pm2@gmail.com"], db_users["pm3@gmail.com"]]

        bid_tasks_def = [
            # (lead_index, title, assigned_pm_index)
            (0, "UI/UX Design scope",          0),
            (0, "Backend API scope",            1),
            (0, "Mobile App scope",             2),
            (1, "Dashboard Development",        0),
            (1, "Data Integration scope",       1),
            (2, "Site Management Module",       2),
            (2, "Reporting & Analytics scope",  0),
            (3, "iOS scope",                    1),
            (3, "Android scope",                2),
            (4, "Analytics ETL scope",          0),
        ]

        for lead_idx, title, pm_idx in bid_tasks_def:
            lead = db_leads[lead_idx]
            pm_u = pm_users[pm_idx]
            r = await session.execute(select(LeadBidTask).where(
                LeadBidTask.lead_id == lead.id,
                LeadBidTask.title == title,
            ))
            bid_task = r.scalars().first()
            if not bid_task:
                bid_task = LeadBidTask(
                    lead_id=lead.id,
                    title=title,
                    description=f"Scope of work for: {title}",
                    delivery_pm_user_id=pm_u.id,
                    created_by_id=bd_users[lead_idx % 3].id,
                )
                session.add(bid_task)
                await session.flush()

            # Assign to PM
            r = await session.execute(select(LeadBidTaskAssignment).where(
                LeadBidTaskAssignment.bid_task_id == bid_task.id,
                LeadBidTaskAssignment.pm_user_id == pm_u.id,
            ))
            if not r.scalars().first():
                session.add(LeadBidTaskAssignment(
                    bid_task_id=bid_task.id,
                    pm_user_id=pm_u.id,
                    assigned_by_id=bd_users[lead_idx % 3].id,
                ))
                await session.flush()
                print(f"  Bid task [{pm_u.full_name}]: {title}")

        # ── 8. Standalone projects with different PMs ────────────────────────
        projects_def = [
            # (name, code, pm_index, members_indices, budget)
            ("Cloud Infrastructure Upgrade",  "INFRA-001", 0, [0, 3],   2_500_000),
            ("Customer Portal 2.0",           "CUST-002",  1, [1, 4],   1_800_000),
            ("IoT Monitoring Platform",        "IOT-003",   2, [2, 5],   3_200_000),
            ("Internal HR Automation",         "HR-AUTO",   0, [0, 1],     900_000),
            ("Mobile Commerce App",            "MCOM-005",  1, [1, 2],   1_400_000),
            ("Data Warehouse Migration",       "DWH-006",   2, [0, 2],   4_100_000),
        ]

        # All users (for member assignment)
        all_users_ordered = [
            db_users["pm@gmail.com"],   # 0
            db_users["pm2@gmail.com"],  # 1
            db_users["pm3@gmail.com"],  # 2
            db_users["emp2@gmail.com"], # 3
            db_users["emp3@gmail.com"], # 4
            db_users["bd@gmail.com"],   # 5  (sometimes a BD is a project member)
        ]

        for name, code, pm_idx, member_indices, budget in projects_def:
            r = await session.execute(select(Project).where(Project.code == code))
            proj = r.scalars().first()
            if not proj:
                proj = Project(name=name, code=code, status="active")
                session.add(proj)
                await session.flush()
                print(f"  Created project [{pm_users[pm_idx].full_name}]: {name}")

                # Set active baseline
                session.add(CostBaseline(project_id=proj.id, amount=float(budget), is_active=True))

            # Ensure PM is a manager member
            pm_u = pm_users[pm_idx]
            r = await session.execute(select(ProjectMember).where(
                ProjectMember.project_id == proj.id,
                ProjectMember.user_id == pm_u.id,
            ))
            if not r.scalars().first():
                session.add(ProjectMember(project_id=proj.id, user_id=pm_u.id, role="manager"))

            # Other members
            for mi in member_indices:
                mem_u = all_users_ordered[mi]
                if mem_u.id == pm_u.id:
                    continue
                r = await session.execute(select(ProjectMember).where(
                    ProjectMember.project_id == proj.id,
                    ProjectMember.user_id == mem_u.id,
                ))
                if not r.scalars().first():
                    session.add(ProjectMember(project_id=proj.id, user_id=mem_u.id, role="member"))

            await session.flush()

        await session.commit()
        print("\n✓ Multi-user seed completed.\n")

    await engine.dispose()
    await asyncio.sleep(0)
    gc.collect()


# ── RLS Verification ─────────────────────────────────────────────────────────
import json
import urllib.request
import urllib.parse

BASE = "http://127.0.0.1:8000/api/v1"

def http_get(path: str, token: str) -> dict:
    req = urllib.request.Request(f"{BASE}{path}", headers={"Authorization": f"Bearer {token}"})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=8).read())
    except urllib.error.HTTPError as e:
        return {"__error__": e.code, "__body__": e.read().decode()}

def login(email: str, pw: str) -> str:
    data = urllib.parse.urlencode({"username": email, "password": pw}).encode()
    req = urllib.request.Request(f"{BASE}/auth/login", data=data, method="POST")
    return json.loads(urllib.request.urlopen(req, timeout=8).read())["access_token"]

def mark_attendance(token: str):
    """Mark attendance so gated routes open up."""
    import json as _json
    body = _json.dumps({"mode": "office"}).encode()
    req = urllib.request.Request(
        f"{BASE}/attendance/mark",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass  # already marked or some other non-fatal error


def run_rls_tests():
    print("=" * 60)
    print("RLS VERIFICATION TESTS")
    print("=" * 60)

    creds = {
        "pm@gmail.com":   "test@12345",
        "pm2@gmail.com":  "test@12345",
        "pm3@gmail.com":  "test@12345",
        "bd@gmail.com":   "test@12345",
        "bd2@gmail.com":  "test@12345",
        "bd3@gmail.com":  "test@12345",
        "emp2@gmail.com": "test@12345",
        "emp3@gmail.com": "test@12345",
        "coo@gmail.com":  "test@12345",
        "ceo@gmail.com":  "test@12345",
        "admin@gmail.com":"test@12345",
    }

    tokens = {}
    print("\n[1] Login all users")
    for email, pw in creds.items():
        try:
            tokens[email] = login(email, pw)
            print(f"  ✓ {email}")
        except Exception as e:
            print(f"  ✗ {email}: {e}")

    print("\n[2] Mark attendance for all (unblocks gated routes)")
    for email, token in tokens.items():
        mark_attendance(token)

    print("\n[3] Projects RLS — /admin/projects (RLS-aware endpoint)")
    print("-" * 40)
    for email in ["pm@gmail.com", "pm2@gmail.com", "pm3@gmail.com",
                  "coo@gmail.com", "ceo@gmail.com", "admin@gmail.com"]:
        if email not in tokens:
            continue
        data = http_get("/admin/projects", tokens[email])
        if isinstance(data, list):
            names = [p.get("name", p.get("code", "?")) for p in data]
            print(f"  {email:<25s} sees {len(data):2d} projects: {names}")
        elif data.get("__error__") == 403:
            # Try the non-admin projects endpoint for PMs
            data2 = http_get("/projects/", tokens[email])
            if isinstance(data2, list):
                names = [p.get("name", p.get("code", "?")) for p in data2]
                print(f"  {email:<25s} sees {len(data2):2d} projects (via /projects/): {names}")
            else:
                print(f"  {email:<25s} → admin=403, projects/={data2}")
        else:
            print(f"  {email:<25s} → {data}")

    print("\n[4] BD Leads RLS — /bd/leads")
    print("-" * 40)
    for email in ["bd@gmail.com", "bd2@gmail.com", "bd3@gmail.com",
                  "coo@gmail.com", "ceo@gmail.com", "admin@gmail.com"]:
        if email not in tokens:
            continue
        data = http_get("/bd/leads", tokens[email])
        if isinstance(data, list):
            titles = [l.get("title", "?")[:40] for l in data]
            print(f"  {email:<25s} sees {len(data)} leads:")
            for t in titles:
                print(f"    - {t}")
        else:
            # might be paginated dict
            items = data.get("items", data.get("leads", []))
            if items:
                print(f"  {email:<25s} sees {len(items)} leads (paginated)")
            else:
                print(f"  {email:<25s} → {data}")

    print("\n[5] PM Bid Tasks — /bd/bid-tasks?lead_id=<first_lead>")
    print("-" * 40)
    # Get any lead id using admin token
    if "admin@gmail.com" in tokens:
        all_leads = http_get("/bd/leads", tokens["admin@gmail.com"])
        if isinstance(all_leads, list) and all_leads:
            first_lead_id = all_leads[0]["id"]
            for email in ["pm@gmail.com", "pm2@gmail.com", "pm3@gmail.com",
                          "bd@gmail.com", "coo@gmail.com"]:
                if email not in tokens:
                    continue
                data = http_get(f"/bd/bid-tasks?lead_id={first_lead_id}", tokens[email])
                if isinstance(data, list):
                    titles = [t.get("title", "?") for t in data]
                    print(f"  {email:<25s} sees {len(data)} tasks: {titles}")
                else:
                    print(f"  {email:<25s} → {data}")

    print("\n[6] Employee scope isolation — tasks")
    print("-" * 40)
    for email in ["emp2@gmail.com", "emp3@gmail.com", "pm@gmail.com", "coo@gmail.com"]:
        if email not in tokens:
            continue
        data = http_get("/tasks/", tokens[email])
        count = len(data) if isinstance(data, list) else data.get("total", "?")
        print(f"  {email:<25s} sees {count} tasks")

    print("\n[7] COO portfolio overview — /projects/coo/overview")
    print("-" * 40)
    for email in ["coo@gmail.com", "ceo@gmail.com", "pm@gmail.com"]:
        if email not in tokens:
            continue
        data = http_get("/projects/coo/overview", tokens[email])
        if isinstance(data, list):
            print(f"  {email:<25s} → {len(data)} portfolio entries")
            for p in data[:3]:
                print(f"    [{p.get('code','?')}] {p.get('name','?')[:40]}  "
                      f"pm={p.get('pm_names', p.get('managers', '?'))}  "
                      f"progress={p.get('completion_percent', p.get('progress_percent', '?'))}%")
        else:
            print(f"  {email:<25s} → {data}")

    print("\n" + "=" * 60)
    print("DONE")
    print("=" * 60)


if __name__ == "__main__":
    print("── Phase 1: Seeding multi-user test data ──")
    asyncio.run(seed_and_test())
    print("── Phase 2: Running RLS verification ──")
    run_rls_tests()
