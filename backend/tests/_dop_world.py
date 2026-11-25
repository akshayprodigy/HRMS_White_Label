"""Shared DOP fixture: one department, one location, seven users. Real dev DB;
teardown removes everything created here."""
import uuid
from datetime import date

import pytest
from sqlalchemy import delete, insert, or_, select

from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.models.approver_delegation import ApproverDelegation
from app.models.audit import AuditLog
from app.models.department import Department
from app.models.dop import (
    ActingAssignment, ManagerAssignment, Post, PostHolder,
)
from app.models.employee import Employee, EmployeeStatus
from app.models.notification import Notification
from app.models.user import Role, User, user_roles

NAMES = ("emp", "mgr", "mgr2", "act", "hr", "admin", "off")


async def dop_cleanup(sfx):
    async with SessionLocal() as db:
        uids = list((await db.execute(select(User.id).where(
            User.email.like(f"dop\\_%\\_{sfx}@test.com")))).scalars().all())
        pids = list((await db.execute(select(Post.id).where(
            Post.code.like(f"%{sfx}%")))).scalars().all())
        dids = list((await db.execute(select(Department.id).where(
            Department.name == f"DOP{sfx}"))).scalars().all())
        if uids or pids or dids:
            await db.execute(delete(ActingAssignment).where(or_(
                ActingAssignment.acting_user_id.in_(uids),
                ActingAssignment.covers_user_id.in_(uids),
                ActingAssignment.covers_post_id.in_(pids))))
            await db.execute(delete(ManagerAssignment).where(or_(
                ManagerAssignment.scope_user_id.in_(uids),
                ManagerAssignment.manager_user_id.in_(uids),
                ManagerAssignment.manager_post_id.in_(pids),
                ManagerAssignment.scope_department_id.in_(dids),
                ManagerAssignment.scope_location.like(f"%{sfx}%"))))
            await db.execute(delete(PostHolder).where(or_(
                PostHolder.user_id.in_(uids), PostHolder.post_id.in_(pids))))
            await db.execute(delete(Post).where(Post.id.in_(pids)))
        if uids:
            await db.execute(delete(ApproverDelegation).where(or_(
                ApproverDelegation.user_id.in_(uids),
                ApproverDelegation.delegate_id.in_(uids))))
            await db.execute(delete(AuditLog).where(AuditLog.user_id.in_(uids)))
            await db.execute(delete(Notification).where(
                Notification.user_id.in_(uids)))
            await db.execute(delete(Employee).where(Employee.user_id.in_(uids)))
            await db.execute(delete(user_roles).where(
                user_roles.c.user_id.in_(uids)))
            await db.execute(delete(User).where(User.id.in_(uids)))
        if dids:
            await db.execute(delete(Department).where(Department.id.in_(dids)))
        # audit rows written about test assignments carry the admin's id, gone
        await db.commit()


@pytest.fixture
async def dop():
    sfx = uuid.uuid4().hex[:8]
    out = {"sfx": sfx, "dept": f"DOP{sfx}", "loc": f"Mumbai{sfx}"}
    try:
        async with SessionLocal() as db:
            dept = Department(name=out["dept"], is_active=True)
            db.add(dept)
            us = {}
            for n, name in enumerate(NAMES):
                us[name] = User(
                    email=f"dop_{name}_{sfx}@test.com",
                    full_name=f"Dop {name} {sfx}",
                    hashed_password=get_password_hash("x"),
                    is_active=name != "off")
            db.add_all(us.values())
            await db.flush()
            us["admin"].is_superuser = True
            role = (await db.execute(select(Role).where(
                Role.name == "HR"))).scalars().first()
            await db.execute(insert(user_roles).values(
                user_id=us["hr"].id, role_id=role.id))
            for n, name in enumerate(NAMES):
                db.add(Employee(
                    user_id=us[name].id, employee_id=f"D{n}{sfx}",
                    department=out["dept"], designation="T",
                    location=out["loc"], date_of_joining=date(2020, 1, 1),
                    status=EmployeeStatus.ACTIVE))
            await db.commit()
            out["dept_id"] = dept.id
            out["uid"] = {n: u.id for n, u in us.items()}
        yield out
    finally:
        await dop_cleanup(sfx)
