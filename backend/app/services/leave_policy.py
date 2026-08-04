"""Per-employment-type leave policy resolution + allocation (W1).

Fallback contract (load-bearing): a MISSING policy row = eligible at the
LeaveType default quota. So an unseeded matrix never blocks leave. Mirrors
the F2 employment_type service fallback style. Join key is the free-string
Employee.employment_type == EmploymentType.code (lowercase).
"""
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employment_type import EmploymentType
from app.models.employment_type_leave_policy import EmploymentTypeLeavePolicy
from app.models.leave import LeaveBalanceLedger, LeaveType


def effective_quota(policy_quota: Optional[float], leave_type: LeaveType) -> float:
    """Policy override wins; else the LeaveType default; coalesce None -> 0.0
    so allocation never does arithmetic on None."""
    if policy_quota is not None:
        return float(policy_quota)
    return float(leave_type.annual_quota or 0.0)


async def _employment_type_id(db: AsyncSession, code: Optional[str]) -> Optional[int]:
    if not code:
        return None
    row = (await db.execute(
        select(EmploymentType).where(EmploymentType.code == code)
    )).scalars().first()
    return row.id if row else None


async def resolve_policies(db: AsyncSession, code: Optional[str]) -> dict:
    """{leave_type_id: EmploymentTypeLeavePolicy} for the given employment
    code. Empty when the code has no EmploymentType — everything falls back
    to eligible."""
    et_id = await _employment_type_id(db, code)
    if et_id is None:
        return {}
    rows = (await db.execute(
        select(EmploymentTypeLeavePolicy).where(
            EmploymentTypeLeavePolicy.employment_type_id == et_id
        )
    )).scalars().all()
    return {r.leave_type_id: r for r in rows}


async def is_eligible(db: AsyncSession, code: Optional[str], leave_type_id: int) -> bool:
    """True unless an explicit policy row marks this (type, leave_type)
    ineligible. Missing row -> eligible (legacy fallback)."""
    policies = await resolve_policies(db, code)
    row = policies.get(leave_type_id)
    return True if row is None else bool(row.is_eligible)


async def allocate_for_user(db: AsyncSession, user_id: int, *, overwrite: bool = False) -> list[dict]:
    """Seed/refresh LeaveBalanceLedger for a user from their employment-type
    policy. Never lowers balance below already-used; skips existing ledgers
    unless overwrite. Ineligible types are skipped."""
    from app.models.employee import Employee
    emp = (await db.execute(
        select(Employee).where(Employee.user_id == user_id)
    )).scalars().first()
    code = emp.employment_type if emp else None
    policies = await resolve_policies(db, code)
    leave_types = (await db.execute(select(LeaveType))).scalars().all()

    out = []
    for lt in leave_types:
        pol = policies.get(lt.id)
        if pol is not None and not pol.is_eligible:
            continue
        quota = effective_quota(pol.annual_quota if pol else None, lt)
        ledger = (await db.execute(select(LeaveBalanceLedger).where(and_(
            LeaveBalanceLedger.user_id == user_id,
            LeaveBalanceLedger.leave_type_id == lt.id,
        )))).scalars().first()
        if ledger is None:
            db.add(LeaveBalanceLedger(user_id=user_id, leave_type_id=lt.id, balance=quota, used=0.0))
            out.append({"leave_type_id": lt.id, "balance": quota, "created": True})
        elif overwrite:
            ledger.balance = max(quota, ledger.used or 0.0)  # never below used
            out.append({"leave_type_id": lt.id, "balance": ledger.balance, "created": False})
    return out
