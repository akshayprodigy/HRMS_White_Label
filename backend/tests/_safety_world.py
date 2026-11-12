"""Shared fixtures for test_safety_profile / test_night_consent (Task 8)."""
import uuid
from datetime import date, time

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, insert, select

from _cleanup import purge_shift_templates
from app.api import deps
from app.core.config import settings
from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.main import create_app
from app.models.audit import AuditLog
from app.models.department import Department
from app.models.employee import Employee, EmployeeStatus
from app.models.roster import (
    RosterEntry, RosterEntryHistory, RosterStatus, ScheduleChangeAck,
)
from app.models.safety import EmployeeEmergencyContact, NightShiftConsent
from app.models.shift import ShiftTemplate
from app.models.user import Permission, Role, User, role_permissions, user_roles

PW = "test@12345"
API = settings.API_V1_STR


@pytest.fixture
async def client():
    app = create_app()
    app.dependency_overrides[deps.verify_attendance] = lambda: None
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as c:
        yield c


@pytest.fixture
async def world():
    sfx = uuid.uuid4().hex[:8]
    dept, other = f"SF{sfx}", f"SO{sfx}"
    rids = []
    try:
        async with SessionLocal() as db:
            def mk(tag):
                return User(email=f"sf_{tag}_{sfx}@t.com", full_name=f"SF {tag}",
                            phone="9000000001",
                            hashed_password=get_password_hash(PW), is_active=True)
            tags = ("head", "f", "m", "x", "hrr", "hrw", "plain")
            us = {t: mk(t) for t in tags}
            db.add_all(us.values())
            db.add_all([Department(name=dept), Department(name=other)])
            night = ShiftTemplate(name=f"SFN{sfx}", start_time=time(22),
                                  end_time=time(6), is_overnight=True)
            day = ShiftTemplate(name=f"SFD{sfx}", start_time=time(9), end_time=time(17))
            late = ShiftTemplate(name=f"SFL{sfx}", start_time=time(20), end_time=time(23))
            db.add_all([night, day, late])
            perms = {p.name: p for p in (await db.execute(select(Permission).where(
                Permission.name.in_(["hr employee read", "hr employee write"])
            ))).scalars().all()}
            rr = Role(name=f"SFR{sfx}", description="t")
            rw = Role(name=f"SFW{sfx}", description="t")
            db.add_all([rr, rw])
            await db.commit()
            rids = [rr.id, rw.id]
            await db.execute(insert(role_permissions).values(
                role_id=rr.id, permission_id=perms["hr employee read"].id))
            await db.execute(insert(role_permissions).values(
                role_id=rw.id, permission_id=perms["hr employee write"].id))
            await db.execute(insert(user_roles).values(
                user_id=us["hrr"].id, role_id=rr.id))
            await db.execute(insert(user_roles).values(
                user_id=us["hrw"].id, role_id=rw.id))
            for t in ("head", "f", "m", "plain"):
                db.add(Employee(user_id=us[t].id, employee_id=f"SF{sfx}{t}",
                                department=dept, designation="T",
                                date_of_joining=date(2020, 1, 1),
                                status=EmployeeStatus.ACTIVE,
                                gender={"f": "female", "m": "male"}.get(t)))
            for t in ("x", "hrr", "hrw"):
                db.add(Employee(user_id=us[t].id, employee_id=f"SF{sfx}{t}",
                                department=other, designation="T",
                                date_of_joining=date(2020, 1, 1),
                                status=EmployeeStatus.ACTIVE))
            await db.execute(Department.__table__.update().where(
                Department.name == dept).values(head_user_id=us["head"].id))
            await db.commit()
            ids = {t: u.id for t, u in us.items()}
            ids.update(night=night.id, day=day.id, late=late.id)
        yield {"ids": ids, "sfx": sfx, "dept": dept, "other": other,
               "email": lambda t: f"sf_{t}_{sfx}@t.com"}
    finally:
        async with SessionLocal() as db:
            uids = list((await db.execute(select(User.id).where(
                User.email.like(f"sf\\_%\\_{sfx}@t.com")))).scalars().all())
            await db.execute(delete(AuditLog).where(AuditLog.user_id.in_(uids)))
            await db.execute(delete(ScheduleChangeAck).where(
                ScheduleChangeAck.user_id.in_(uids)))
            await db.execute(delete(RosterEntryHistory).where(
                RosterEntryHistory.employee_id.in_(uids)))
            await db.execute(delete(RosterEntry).where(
                RosterEntry.employee_id.in_(uids)))
            await db.execute(delete(EmployeeEmergencyContact).where(
                EmployeeEmergencyContact.user_id.in_(uids)))
            await db.execute(delete(NightShiftConsent).where(
                NightShiftConsent.user_id.in_(uids)))
            await db.execute(Department.__table__.update().where(
                Department.name.in_([dept, other])).values(head_user_id=None))
            await db.execute(delete(user_roles).where(user_roles.c.user_id.in_(uids)))
            if rids:
                await db.execute(delete(role_permissions).where(
                    role_permissions.c.role_id.in_(rids)))
                await db.execute(delete(Role).where(Role.id.in_(rids)))
            await db.execute(delete(Employee).where(Employee.user_id.in_(uids)))
            await db.execute(delete(Department).where(Department.name.in_([dept, other])))
            tids = list((await db.execute(select(ShiftTemplate.id).where(
                ShiftTemplate.name.in_([f"SFN{sfx}", f"SFD{sfx}", f"SFL{sfx}"])))
            ).scalars().all())
            await purge_shift_templates(db, tids)
            await db.execute(delete(User).where(User.id.in_(uids)))
            await db.commit()


async def login(client, world, tag):
    r = await client.post(f"{API}/auth/login",
                          data={"username": world["email"](tag), "password": PW})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def add_entry(uid, d, tpl, status=RosterStatus.PUBLISHED, off=False):
    async with SessionLocal() as db:
        e = RosterEntry(employee_id=uid, work_date=d,
                        shift_template_id=None if off else tpl,
                        is_week_off=off, status=status)
        db.add(e)
        await db.commit()
        return e.id
