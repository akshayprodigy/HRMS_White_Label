"""End-to-end generate_draft: absence LOP toggle off vs on.

Isolation: a throwaway MONTHLY run in March 2018 whose scope_user_ids is
set to just the test employee, so generate-draft touches no other
employee. Every row created is removed in finally; the two time-rule
settings are restored to their original state."""
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core.config import settings
from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.main import create_app
from app.models.attendance import Attendance
from app.models.audit import AuditLog
from app.models.employee import Employee
from app.models.leave import LeaveRequest, LeaveStatus, LeaveType
from app.models.payroll import PayrollLine, PayrollRun, PayrollRunStatus
from app.models.system import SystemSetting
from app.models.user import User
from app.services.time_rules import set_time_rules

BASE = f"{settings.API_V1_STR}/hr/payroll"
YEAR, MONTH = 2018, 3          # 31 days; Sundays: 4, 11, 18, 25
K_ON = "attendance.absence_lop_enabled"
K_OFF = "attendance.default_weekly_offs"


@pytest.fixture
async def client():
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _admin(client):
    r = await client.post(f"{settings.API_V1_STR}/auth/login",
                         data={"username": "admin@gmail.com", "password": "test@12345"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _line_for(client, h, run_id, uid):
    r = await client.get(f"{BASE}/{run_id}/lines", headers=h)
    assert r.status_code == 200, r.text
    lines = [x for x in r.json() if x["user_id"] == uid]
    assert len(lines) == 1
    return lines[0]


async def test_generate_draft_absence_lop_toggle(client):
    tag = uuid.uuid4().hex[:8]
    uid = eid = lt_id = run_id = None
    original: dict[str, str | None] = {}
    try:
        async with SessionLocal() as db:
            for k in (K_ON, K_OFF):
                row = await db.get(SystemSetting, k)
                original[k] = row.value if row else None

            u = User(email=f"e2e_{tag}@test.com", full_name="E2E Abs",
                     hashed_password=get_password_hash("x"), is_active=True)
            db.add(u)
            await db.flush()
            uid = u.id
            e = Employee(user_id=uid, employee_id=f"E2{tag}", department="T",
                         designation="T", date_of_joining=date(2017, 1, 1),
                         status="active", salary=31000.0, location="HQ")
            db.add(e)
            lt = LeaveType(name=f"E2E_{tag}", code=f"E{tag[:6]}", unpaid_allowed=True)
            db.add(lt)
            await db.flush()
            eid, lt_id = e.id, lt.id

            # Unpaid 2-day half-day leave Mar 12-13 (punched -> no absence
            # side), expected unpaid LOP = 2 * 0.5 = 1.0.
            db.add(LeaveRequest(
                employee_id=uid, leave_type_id=lt_id,
                start_date=date(2018, 3, 12), end_date=date(2018, 3, 13),
                is_half_day=True, reason="r",
                status=LeaveStatus.APPROVED, created_by_user_id=uid))
            # Punch every non-Sunday except Mar 5 and 6 (2 unexplained absences).
            skip = {date(2018, 3, 5), date(2018, 3, 6)}
            for day in range(1, 32):
                d = date(2018, 3, day)
                if d.weekday() == 6 or d in skip:
                    continue
                db.add(Attendance(
                    user_id=uid, mode="web", work_date=d,
                    captured_at=datetime(2018, 3, day, 9, 0, tzinfo=timezone.utc)))
            await db.commit()

        h = await _admin(client)
        async with SessionLocal() as db:
            await set_time_rules(db, {K_ON: "0", K_OFF: "6"})

        r = await client.post(f"{BASE}/run", json={"month": MONTH, "year": YEAR}, headers=h)
        assert r.status_code == 200, r.text
        run_id = r.json()["id"]
        async with SessionLocal() as db:   # scope the run to our employee only
            run = await db.get(PayrollRun, run_id)
            run.scope_user_ids = [uid]
            await db.commit()
        for step in ("lock-attendance", "lock-leaves"):
            r = await client.post(f"{BASE}/{run_id}/{step}", headers=h)
            assert r.status_code == 200, r.text

        # (a) toggle off: unpaid leave only
        r = await client.post(f"{BASE}/{run_id}/generate-draft", headers=h)
        assert r.status_code == 200, r.text
        line = await _line_for(client, h, run_id, uid)
        assert line["lop_days"] == pytest.approx(1.0)
        assert line["payable_days"] == pytest.approx(30.0)
        net_off = line["net_pay"]

        # (b) toggle on: + 2 unexplained absences
        async with SessionLocal() as db:
            await set_time_rules(db, {K_ON: "1"})
            run = await db.get(PayrollRun, run_id)   # regenerate from LEAVES_LOCKED
            run.status = PayrollRunStatus.LEAVES_LOCKED
            await db.commit()
        r = await client.post(f"{BASE}/{run_id}/generate-draft", headers=h)
        assert r.status_code == 200, r.text
        line = await _line_for(client, h, run_id, uid)
        assert line["lop_days"] == pytest.approx(3.0)
        assert line["payable_days"] == pytest.approx(28.0)
        assert line["net_pay"] < net_off
    finally:
        async with SessionLocal() as db:
            await db.rollback()
            if run_id:
                await db.execute(delete(PayrollLine).where(PayrollLine.payroll_run_id == run_id))
                await db.execute(delete(AuditLog).where(
                    AuditLog.resource_type == "payroll_run",
                    AuditLog.resource_id == str(run_id)))
                await db.execute(delete(PayrollRun).where(PayrollRun.id == run_id))
            if uid:
                await db.execute(delete(PayrollLine).where(PayrollLine.user_id == uid))
                await db.execute(delete(Attendance).where(Attendance.user_id == uid))
                await db.execute(delete(LeaveRequest).where(LeaveRequest.employee_id == uid))
            if eid:
                await db.execute(delete(Employee).where(Employee.id == eid))
            if lt_id:
                await db.execute(delete(LeaveType).where(LeaveType.id == lt_id))
            if uid:
                await db.execute(delete(User).where(User.id == uid))
            for k, v in original.items():
                row = await db.get(SystemSetting, k)
                if v is None:
                    if row:
                        await db.delete(row)
                elif row:
                    row.value = v
                else:
                    db.add(SystemSetting(key=k, value=v))
            await db.commit()
