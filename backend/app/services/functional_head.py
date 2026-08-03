"""Functional-head resolution (F1).

A 'functional head' is the user set as head_user_id (or deputy_head_user_id)
on a Department. Employees are grouped by the free-text `Employee.department`
string, which matches `Department.name` — the established team key.
"""
from typing import Optional

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.department import Department
from app.models.employee import Employee
from app.models.user import User


async def resolve_head(db: AsyncSession, employee: Employee) -> Optional[User]:
    """Return the functional head governing an employee: the department's
    head if set, else its deputy, else None."""
    if not employee.department:
        return None
    dept = (
        await db.execute(select(Department).where(Department.name == employee.department))
    ).scalars().first()
    if dept is None:
        return None
    if dept.head_user_id:
        return await db.get(User, dept.head_user_id)
    if dept.deputy_head_user_id:
        return await db.get(User, dept.deputy_head_user_id)
    return None


async def resolve_team(db: AsyncSession, head_user: User) -> list[Employee]:
    """Return active employees across every department this user heads (as
    head or deputy). Empty list if the user heads nothing. The `user`
    relationship is eager-loaded for display."""
    dept_names = (
        await db.execute(
            select(Department.name).where(
                or_(
                    Department.head_user_id == head_user.id,
                    Department.deputy_head_user_id == head_user.id,
                )
            )
        )
    ).scalars().all()
    if not dept_names:
        return []
    rows = (
        await db.execute(
            select(Employee)
            .options(selectinload(Employee.user))
            .where(
                Employee.department.in_(dept_names),
                Employee.status == "active",
            )
        )
    ).scalars().all()
    return list(rows)


async def is_head_of(db: AsyncSession, head_user: User, employee: Employee) -> bool:
    """True if head_user is the head OR deputy of the employee's department."""
    if not employee.department:
        return False
    dept = (
        await db.execute(select(Department).where(Department.name == employee.department))
    ).scalars().first()
    if dept is None:
        return False
    return head_user.id in (dept.head_user_id, dept.deputy_head_user_id)
