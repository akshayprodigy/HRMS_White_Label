"""Seed leave / expense / travel showcase data into a LOCAL stack.

Populates, idempotently:
- LeaveBalanceLedger rows (CL / PL / SL) for the demo users
- a spread of leave requests across the last months + upcoming
  (approved / submitted / rejected)
- expense categories, expense claims with line items in every
  lifecycle status (draft / submitted / approved / reimbursed)
- travel requests (submitted / approved / completed)

Safety: refuses to run unless ERP_LOCAL_SEED=1 and --yes-local is
passed — same contract as scripts/seed_local.py. Deterministic and
re-runnable (existence checks by natural keys).

Run:
    docker compose -f docker-compose.local.yml exec -T \
        -e ERP_LOCAL_SEED=1 -e PYTHONPATH=/app \
        backend python -m scripts.seed_showcase_data --yes-local
"""
import asyncio
import os
import sys
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.employee import Employee
from app.models.expense import (
    ExpenseCategory, ExpenseClaim, ExpenseClaimStatus, ExpenseLineItem,
    TravelRequest, TravelRequestStatus,
)
from app.models.leave import (
    LeaveBalanceLedger, LeaveRequest, LeaveStatus, LeaveType,
)
from app.models.user import User

USERS = [
    "t1@example.com", "t2@example.com", "t3@example.com",
    "employee@gmail.com", "pm@gmail.com", "hr@gmail.com", "ceo@gmail.com",
]

# code -> (quota, used)
BALANCES = {"CL": (10.0, 3.0), "PL": (14.0, 4.0), "SL": (7.0, 1.0)}

# (email, type_code, start_days_from_today, length_days, status, reason)
LEAVE_PLAN = [
    ("t1@example.com", "CL", -55, 1, LeaveStatus.APPROVED, "Family function"),
    ("t1@example.com", "SL", -20, 2, LeaveStatus.APPROVED, "Fever and rest advised"),
    ("t2@example.com", "PL", -40, 3, LeaveStatus.APPROVED, "Trip to hometown"),
    ("t2@example.com", "CL", -8, 1, LeaveStatus.REJECTED, "Personal errand"),
    ("t3@example.com", "PL", -30, 2, LeaveStatus.APPROVED, "Cousin's wedding"),
    ("t3@example.com", "CL", 9, 1, LeaveStatus.SUBMITTED, "Bank and passport work"),
    ("employee@gmail.com", "SL", -12, 1, LeaveStatus.APPROVED, "Migraine"),
    ("employee@gmail.com", "PL", 14, 4, LeaveStatus.SUBMITTED, "Family vacation - Kerala"),
    ("pm@gmail.com", "CL", -25, 1, LeaveStatus.APPROVED, "School admission for kid"),
    ("hr@gmail.com", "PL", 21, 2, LeaveStatus.SUBMITTED, "Long weekend break"),
]

CATEGORIES = [
    ("Local Transport", "TRANS"),
    ("Lodging", "LODGE"),
    ("Client Entertainment", "ENT"),
    ("Office Supplies", "SUPPLY"),
]

# (email, title, days_ago, status, [(category, rupees, desc)])
CLAIM_PLAN = [
    ("t1@example.com", "Client visit - Salt Lake office", 28,
     ExpenseClaimStatus.REIMBURSED,
     [("Local Transport", 850, "Cab to client office and back"),
      ("Travel Meals", 620, "Working lunch with client team")]),
    ("t2@example.com", "Recruitment drive - college campus", 14,
     ExpenseClaimStatus.APPROVED,
     [("Local Transport", 1200, "Round trip to campus"),
      ("Office Supplies", 450, "Printed brochures and forms")]),
    ("pm@gmail.com", "Mumbai client workshop", 10,
     ExpenseClaimStatus.APPROVED,
     [("Lodging", 9800, "2 nights hotel near BKC"),
      ("Travel Meals", 2400, "Team dinners"),
      ("Local Transport", 1750, "Airport transfers and cabs")]),
    ("t3@example.com", "Night shift cab reimbursement - June", 6,
     ExpenseClaimStatus.SUBMITTED,
     [("Local Transport", 3900, "Late-night cabs, 12 days")]),
    ("employee@gmail.com", "Team outing supplies", 2,
     ExpenseClaimStatus.DRAFT,
     [("Client Entertainment", 2100, "Snacks and games for team event")]),
]

# (email, purpose, from, to, start_days, end_days, cost_rs, advance_rs, status)
TRAVEL_PLAN = [
    ("pm@gmail.com", "Client kickoff - Veliora rollout", "Kolkata", "Mumbai",
     7, 10, 42000, 15000, TravelRequestStatus.APPROVED),
    ("t2@example.com", "Campus hiring - NIT Durgapur", "Kolkata", "Durgapur",
     12, 13, 6500, 2000, TravelRequestStatus.SUBMITTED),
    ("ceo@gmail.com", "Investor meet", "Kolkata", "Bengaluru",
     -21, -19, 38000, 0, TravelRequestStatus.COMPLETED),
]


def _guard() -> None:
    if os.environ.get("ERP_LOCAL_SEED") != "1" or "--yes-local" not in sys.argv:
        print(
            "REFUSING to run: set ERP_LOCAL_SEED=1 and pass --yes-local.\n"
            "This script writes demo leave/expense data — local stacks only."
        )
        sys.exit(1)


async def _users(session) -> dict:
    rows = (await session.execute(
        select(User).where(User.email.in_(USERS))
    )).scalars().all()
    return {u.email: u for u in rows}


async def _employees_by_user(session, user_ids) -> dict:
    rows = (await session.execute(
        select(Employee).where(Employee.user_id.in_(user_ids))
    )).scalars().all()
    return {e.user_id: e for e in rows}


async def _leave_types(session) -> dict:
    rows = (await session.execute(select(LeaveType))).scalars().all()
    return {lt.code: lt for lt in rows if lt.code}


async def seed_balances(session, users, types) -> None:
    added = 0
    for email, u in users.items():
        for code, (quota, used) in BALANCES.items():
            lt = types.get(code)
            if lt is None:
                continue
            existing = (await session.execute(
                select(LeaveBalanceLedger).where(
                    LeaveBalanceLedger.user_id == u.id,
                    LeaveBalanceLedger.leave_type_id == lt.id,
                )
            )).scalars().first()
            if existing:
                continue
            # small per-user variation so numbers don't look cloned
            jitter = (u.id % 3)
            session.add(LeaveBalanceLedger(
                user_id=u.id, leave_type_id=lt.id,
                balance=quota, used=max(0.0, used - jitter),
            ))
            added += 1
    print(f"  leave balances: +{added} rows")


async def seed_leaves(session, users, types) -> None:
    today = date.today()
    added = 0
    for email, code, off, length, status, reason in LEAVE_PLAN:
        u = users.get(email)
        lt = types.get(code)
        if u is None or lt is None:
            continue
        start = today + timedelta(days=off)
        end = start + timedelta(days=length - 1)
        existing = (await session.execute(
            select(LeaveRequest).where(
                LeaveRequest.employee_id == u.id,
                LeaveRequest.start_date == start,
            )
        )).scalars().first()
        if existing:
            continue
        session.add(LeaveRequest(
            employee_id=u.id, leave_type_id=lt.id,
            start_date=start, end_date=end,
            reason=reason, status=status,
            created_by_user_id=u.id,
            created_at=datetime.now(timezone.utc) + timedelta(days=min(off, -1)),
        ))
        added += 1
    print(f"  leave requests: +{added} rows")


async def seed_categories(session) -> dict:
    out = {}
    existing = (await session.execute(select(ExpenseCategory))).scalars().all()
    for c in existing:
        out[c.name] = c
    added = 0
    for name, code in CATEGORIES:
        if name in out:
            continue
        c = ExpenseCategory(name=name, code=code, is_active=True)
        session.add(c)
        await session.flush()
        out[name] = c
        added += 1
    print(f"  expense categories: +{added} (total {len(out)})")
    return out


async def seed_claims(session, users, emps, cats) -> None:
    added = 0
    for email, title, days_ago, status, lines in CLAIM_PLAN:
        u = users.get(email)
        emp = emps.get(u.id) if u else None
        if u is None or emp is None:
            continue
        existing = (await session.execute(
            select(ExpenseClaim).where(ExpenseClaim.title == title)
        )).scalars().first()
        if existing:
            continue
        when = date.today() - timedelta(days=days_ago)
        total = sum(r for _, r, _ in lines) * 100
        claim = ExpenseClaim(
            employee_id=emp.id, submitter_id=u.id,
            title=title, claim_date=when,
            total_amount_paise=total, status=status,
        )
        if status == ExpenseClaimStatus.REIMBURSED:
            claim.reimbursement_mode = "bank"
            claim.reimbursed_at = datetime.now(timezone.utc) - timedelta(
                days=max(0, days_ago - 7)
            )
            claim.reimbursed_reference = f"NEFT-DEMO-{emp.id}{days_ago}"
        session.add(claim)
        await session.flush()
        for cat_name, rupees, desc in lines:
            cat = cats.get(cat_name)
            session.add(ExpenseLineItem(
                claim_id=claim.id,
                category_id=cat.id if cat else None,
                amount_paise=rupees * 100,
                line_date=when, description=desc,
            ))
        added += 1
    print(f"  expense claims: +{added}")


async def seed_travel(session, users, emps) -> None:
    today = date.today()
    added = 0
    for email, purpose, frm, to, s_off, e_off, cost, adv, status in TRAVEL_PLAN:
        u = users.get(email)
        emp = emps.get(u.id) if u else None
        if u is None or emp is None:
            continue
        existing = (await session.execute(
            select(TravelRequest).where(TravelRequest.purpose == purpose)
        )).scalars().first()
        if existing:
            continue
        tr = TravelRequest(
            employee_id=emp.id, submitter_id=u.id,
            purpose=purpose, from_city=frm, to_city=to,
            start_date=today + timedelta(days=s_off),
            end_date=today + timedelta(days=e_off),
            estimated_cost_paise=cost * 100,
            advance_requested_paise=adv * 100,
            advance_paid_paise=adv * 100
            if status in (TravelRequestStatus.APPROVED,
                          TravelRequestStatus.COMPLETED) else 0,
            status=status,
        )
        if status != TravelRequestStatus.DRAFT:
            tr.submitted_at = datetime.now(timezone.utc) - timedelta(days=3)
        session.add(tr)
        added += 1
    print(f"  travel requests: +{added}")


async def main() -> None:
    _guard()
    engine = create_async_engine(settings.SQLALCHEMY_DATABASE_URI)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        users = await _users(session)
        emps = await _employees_by_user(session, [u.id for u in users.values()])
        types = await _leave_types(session)
        print(f"[1/5] users found: {sorted(users)}")
        print("[2/5] leave balances")
        await seed_balances(session, users, types)
        print("[3/5] leave requests")
        await seed_leaves(session, users, types)
        print("[4/5] expense categories + claims")
        cats = await seed_categories(session)
        await seed_claims(session, users, emps, cats)
        print("[5/5] travel requests")
        await seed_travel(session, users, emps)
        await session.commit()
    await engine.dispose()
    print("done.")


if __name__ == "__main__":
    asyncio.run(main())
