import pytest
from httpx import AsyncClient, ASGITransport
from datetime import date, timedelta
from app.core.config import settings
from app.models.leave import LeaveType, LeaveBalanceLedger
from app.models.user import User
from sqlalchemy import select


async def _ensure_attendance(ac: AsyncClient, headers: dict) -> None:
    today = await ac.get(f"{settings.API_V1_STR}/attendance/today", headers=headers)
    if today.status_code == 200 and (today.json() or {}).get("is_marked") is True:
        return
    resp = await ac.post(
        f"{settings.API_V1_STR}/attendance/mark",
        json={"mode": "office", "remarks": "pytest"},
        headers=headers,
    )
    assert resp.status_code in (200, 400)


async def _ensure_leave_type_and_balance(
    db,
    *,
    user_email: str,
    leave_type_name: str,
    min_balance: float,
) -> None:
    user = (
        await db.execute(select(User).where(User.email == user_email))
    ).scalar_one()

    leave_type = (
        await db.execute(select(LeaveType).where(LeaveType.name == leave_type_name))
    ).scalar_one_or_none()
    if leave_type is None:
        leave_type = LeaveType(name=leave_type_name, description="pytest")
        db.add(leave_type)
        await db.flush()

    ledger = (
        await db.execute(
            select(LeaveBalanceLedger).where(
                LeaveBalanceLedger.user_id == user.id,
                LeaveBalanceLedger.leave_type_id == leave_type.id,
            )
        )
    ).scalar_one_or_none()

    if ledger is None:
        ledger = LeaveBalanceLedger(
            user_id=user.id,
            leave_type_id=leave_type.id,
            balance=min_balance,
            used=0.0,
        )
        db.add(ledger)
    else:
        used = float(ledger.used or 0.0)
        required_total_balance = used + float(min_balance)
        if float(ledger.balance or 0.0) < required_total_balance:
            ledger.balance = required_total_balance

    await db.commit()


def _parse_iso_date(value: str) -> date:
    return date.fromisoformat(value)


async def _pick_non_overlapping_start(
    ac: AsyncClient,
    headers: dict,
    *,
    min_offset_days: int,
) -> date:
    start = date.today() + timedelta(days=min_offset_days)
    mine = await ac.get(f"{settings.API_V1_STR}/leave/my", headers=headers)
    if mine.status_code != 200:
        return start

    for item in mine.json() or []:
        status = str(item.get("status") or "").lower()
        if status in {"rejected", "cancelled", "canceled"}:
            continue
        end_date = item.get("end_date")
        if not end_date:
            continue
        end_dt = _parse_iso_date(str(end_date))
        if end_dt >= start:
            start = end_dt + timedelta(days=7)
    return start

@pytest.fixture
def app():
    from app.main import create_app
    return create_app()

@pytest.mark.asyncio
async def test_leave_management_workflow(app, db):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        await _ensure_leave_type_and_balance(
            db,
            user_email="employee@gmail.com",
            leave_type_name="Annual Leave",
            min_balance=20.0,
        )
        # 1. Login as Employee
        login_data = {"username": "employee@gmail.com", "password": "test@12345"}
        login_response = await ac.post(f"{settings.API_V1_STR}/auth/login", data=login_data)
        assert login_response.status_code == 200
        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        await _ensure_attendance(ac, headers)
        
        # Get Leave Balances
        bal_resp = await ac.get(f"{settings.API_V1_STR}/leave/balances", headers=headers)
        assert bal_resp.status_code == 200
        balances = bal_resp.json()
        annual = next(
            (b for b in balances if b["leave_type"]["name"] == "Annual Leave"),
            None,
        )
        assert annual is not None
        annual_leave_id = int(annual["leave_type"]["id"])
        used_before = float(annual.get("used") or 0)

        # 2. Apply for Leave
        start_date = await _pick_non_overlapping_start(
            ac,
            headers,
            min_offset_days=30,
        )
        end_date = start_date + timedelta(days=1)
        
        apply_data = {
            "leave_type_id": annual_leave_id,
            "start_date": str(start_date),
            "end_date": str(end_date),
            "reason": "Test Vacation"
        }
        
        apply_resp = await ac.post(f"{settings.API_V1_STR}/leave/apply", json=apply_data, headers=headers)
        assert apply_resp.status_code == 200
        leave_id = apply_resp.json()["id"]
        assert apply_resp.json()["status"] == "submitted"

        # 3. Test Overlap
        overlap_resp = await ac.post(f"{settings.API_V1_STR}/leave/apply", json=apply_data, headers=headers)
        assert overlap_resp.status_code == 400
        assert "overlap" in overlap_resp.json()["error"]["message"].lower()

        # 4. Login as PM (Manager) to approve
        pm_login = {"username": "pm@gmail.com", "password": "test@12345"}
        pm_resp = await ac.post(f"{settings.API_V1_STR}/auth/login", data=pm_login)
        pm_token = pm_resp.json()["access_token"]
        pm_headers = {"Authorization": f"Bearer {pm_token}"}

        await _ensure_attendance(ac, pm_headers)
        
        # Check Inbox
        inbox_resp = await ac.get(f"{settings.API_V1_STR}/leave/approvals/inbox", headers=pm_headers)
        assert inbox_resp.status_code == 200
        items = inbox_resp.json()
        approval_item = next(item for item in items if item["resource_id"] == str(leave_id))
        
        # Approve Step 1 (Manager)
        action_data = {"status": "approved", "comment": "Enjoy!"}
        action_resp = await ac.post(f"{settings.API_V1_STR}/leave/approvals/{approval_item['id']}/action", json=action_data, headers=pm_headers)
        assert action_resp.status_code == 200

        # 5. Check as HR (Step 2)
        hr_login = {"username": "hr@gmail.com", "password": "test@12345"}
        hr_resp = await ac.post(f"{settings.API_V1_STR}/auth/login", data=hr_login)
        hr_token = hr_resp.json()["access_token"]
        hr_headers = {"Authorization": f"Bearer {hr_token}"}

        await _ensure_attendance(ac, hr_headers)
        
        inbox_resp = await ac.get(f"{settings.API_V1_STR}/leave/approvals/inbox", headers=hr_headers)
        items = inbox_resp.json()
        approval_item = next(item for item in items if item["resource_id"] == str(leave_id))
        
        # Final Approval (HR)
        action_resp = await ac.post(f"{settings.API_V1_STR}/leave/approvals/{approval_item['id']}/action", json=action_data, headers=hr_headers)
        assert action_resp.status_code == 200

        # 6. Verify Leave Status is APPROVED
        leave_resp = await ac.get(f"{settings.API_V1_STR}/leave/my", headers=headers)
        leaves = leave_resp.json()
        target_leave = next(l for l in leaves if l["id"] == leave_id)
        assert target_leave["status"] == "approved"
        
        # 7. Check Balance Deduction
        bal_resp_after = await ac.get(f"{settings.API_V1_STR}/leave/balances", headers=headers)
        balances_after = bal_resp_after.json()
        annual_bal = next(b for b in balances_after if b["leave_type"]["name"] == "Annual Leave")
        assert float(annual_bal.get("used") or 0) == used_before + 2.0

@pytest.mark.asyncio
async def test_insufficient_balance(app, db):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        await _ensure_leave_type_and_balance(
            db,
            user_email="employee@gmail.com",
            leave_type_name="Sick Leave",
            min_balance=10.0,
        )
        login_data = {"username": "employee@gmail.com", "password": "test@12345"}
        login_response = await ac.post(f"{settings.API_V1_STR}/auth/login", data=login_data)
        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        await _ensure_attendance(ac, headers)
        
        # Get Sick Leave balance (seeded as 10.0)
        bal_resp = await ac.get(f"{settings.API_V1_STR}/leave/balances", headers=headers)
        balances = bal_resp.json()
        sick_leave_id = next(b["leave_type"]["id"] for b in balances if b["leave_type"]["name"] == "Sick Leave")
        
        # Try to apply for 15 days of sick leave
        today = date.today()
        apply_data = {
            "leave_type_id": sick_leave_id,
            "start_date": str(today + timedelta(days=2000)),
            "end_date": str(today + timedelta(days=2015)),
            "reason": "Very long sickness"
        }
        
        resp = await ac.post(f"{settings.API_V1_STR}/leave/apply", json=apply_data, headers=headers)
        assert resp.status_code == 400
        assert "insufficient" in resp.json()["error"]["message"].lower()

@pytest.mark.asyncio
async def test_half_day_leave(app, db):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        await _ensure_leave_type_and_balance(
            db,
            user_email="employee@gmail.com",
            leave_type_name="Sick Leave",
            min_balance=1.0,
        )
        login_data = {"username": "employee@gmail.com", "password": "test@12345"}
        login_response = await ac.post(f"{settings.API_V1_STR}/auth/login", data=login_data)
        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        await _ensure_attendance(ac, headers)
        
        bal_resp = await ac.get(f"{settings.API_V1_STR}/leave/balances", headers=headers)
        balances = bal_resp.json()
        sick_leave_id = next(b["leave_type"]["id"] for b in balances if b["leave_type"]["name"] == "Sick Leave")
        
        start_date = await _pick_non_overlapping_start(
            ac,
            headers,
            min_offset_days=3000,
        )
        apply_data = {
            "leave_type_id": sick_leave_id,
            "start_date": str(start_date),
            "end_date": str(start_date),
            "is_half_day": True,
            "half_day_session": "morning",
            "reason": "Checkup"
        }
        
        resp = await ac.post(f"{settings.API_V1_STR}/leave/apply", json=apply_data, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["total_days"] == 0.5
