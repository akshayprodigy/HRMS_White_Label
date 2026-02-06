from __future__ import annotations

import datetime as dt
import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.database import SessionLocal
from app.db.models.iam import Permission
from app.main import app
from app.modules.iam.service import (
    create_permission,
    create_role,
    create_user,
    set_role_permissions,
    set_user_roles,
)


@pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="Set RUN_DB_TESTS=1 to run integration HR leave tests.",
)
def test_hr_leave_workflows_and_balance_rules() -> None:
    email = f"test-hr-leave-{uuid.uuid4().hex[:10]}@example.com"
    password = "Password123!"

    perm_codes = [
        "hr.employees.write",
        "hr.leave_types.read",
        "hr.leave_types.write",
        "hr.leave_policies.read",
        "hr.leave_policies.write",
        "hr.leave_balances.read",
        "hr.leave_requests.read",
        "hr.leave_requests.apply",
        "hr.leave_requests.approve",
        "hr.leave_requests.reject",
        "hr.leave_requests.cancel",
        "hr.holiday_calendars.read",
        "hr.holiday_calendars.write",
        "admin.jobs.leave_credit",
    ]

    with SessionLocal() as db:
        user = create_user(db, email=email, password=password, is_active=True)

        permissions: list[Permission] = []
        for code in perm_codes:
            perm = db.execute(
                select(Permission).where(Permission.code == code)
            ).scalar_one_or_none()
            if perm is None:
                perm = create_permission(db, code=code, description=None)
            permissions.append(perm)

        role = create_role(db, name=f"role-hr-leave-{uuid.uuid4().hex[:8]}")
        set_role_permissions(
            db,
            role_id=role.id,
            permission_ids=[p.id for p in permissions],
        )
        set_user_roles(db, user_id=user.id, role_ids=[role.id])

    client = TestClient(app)

    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200
    access_token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    employee_create = client.post(
        "/api/v1/hr/employees",
        json={
            "employee_code": f"EMP-{uuid.uuid4().hex[:6]}",
            "first_name": "Sam",
            "last_name": "Tester",
            "employment_type": "full_time",
            "employment_status": "active",
            "joining_date": "2026-01-01",
        },
        headers=headers,
    )
    assert employee_create.status_code == 200
    employee_id = employee_create.json()["id"]

    # Add a holiday to affect day count.
    # Pick a weekday triplet (leave_from, holiday, leave_to) and retry if the
    # chosen holiday_date already exists in a persistent DB.
    # Use a far-future window to avoid collisions with previously created
    # holiday dates in a persistent MariaDB volume.
    base = dt.date(2099, 1, 10)
    leave_from = ""
    leave_to = ""
    holiday_date = ""
    for i in range(0, 20):
        holiday = base + dt.timedelta(days=i)
        left = holiday - dt.timedelta(days=1)
        right = holiday + dt.timedelta(days=1)

        if (
            holiday.weekday() >= 5
            or left.weekday() >= 5
            or right.weekday() >= 5
        ):
            continue

        holiday_date = holiday.isoformat()
        leave_from = left.isoformat()
        leave_to = right.isoformat()

        existing = client.get(
            "/api/v1/hr/holidays",
            params={"date_from": leave_from, "date_to": leave_to},
            headers=headers,
        )
        assert existing.status_code == 200
        if existing.json():
            continue

        holiday_create = client.post(
            "/api/v1/hr/holidays",
            json={
                "holiday_date": holiday_date,
                "name": f"Founders Day {uuid.uuid4().hex[:6]}",
                "is_optional": False,
            },
            headers=headers,
        )
        if holiday_create.status_code == 200:
            break
    else:
        raise AssertionError("Could not create a unique weekday holiday")

    leave_type = client.post(
        "/api/v1/hr/leave-types",
        json={
            "code": f"AL{uuid.uuid4().hex[:4]}",
            "name": "Annual Leave",
            "description": None,
            "is_active": True,
        },
        headers=headers,
    )
    assert leave_type.status_code == 200
    leave_type_id = leave_type.json()["id"]

    policy = client.post(
        "/api/v1/hr/leave-policies",
        json={
            "leave_type_id": leave_type_id,
            "name": "Default policy",
            "monthly_credit_days": 2,
            "max_balance_days": 10,
            "is_active": True,
            "notes": None,
        },
        headers=headers,
    )
    assert policy.status_code == 200

    credit = client.post(
        "/api/v1/admin/jobs/leave-credit",
        json={
            "year": 2026,
            "month": 2,
            "leave_type_id": leave_type_id,
        },
        headers=headers,
    )
    assert credit.status_code == 200
    assert credit.json()["status"] == "ok"

    balances = client.get(
        f"/api/v1/hr/leave-balances/employees/{employee_id}",
        headers=headers,
    )
    assert balances.status_code == 200
    rows = balances.json()
    assert any(r["leave_type_id"] == leave_type_id for r in rows)

    # Apply leave X to X+2 with holiday on X+1 => 2 days
    apply = client.post(
        "/api/v1/hr/leave-requests/apply",
        json={
            "employee_id": employee_id,
            "leave_type_id": leave_type_id,
            "date_from": leave_from,
            "date_to": leave_to,
            "reason": "Personal work",
        },
        headers=headers,
    )
    assert apply.status_code == 200
    req = apply.json()
    assert req["status"] == "applied"
    assert float(req["days"]) == pytest.approx(2.0)
    request_id = req["id"]

    # Cancel should refund
    cancel = client.post(
        f"/api/v1/hr/leave-requests/{request_id}/cancel",
        headers=headers,
    )
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "cancelled"

    # Apply again then approve
    apply2 = client.post(
        "/api/v1/hr/leave-requests/apply",
        json={
            "employee_id": employee_id,
            "leave_type_id": leave_type_id,
            "date_from": leave_from,
            "date_to": leave_to,
            "reason": "Personal work",
        },
        headers=headers,
    )
    assert apply2.status_code == 200
    request_id2 = apply2.json()["id"]

    approve = client.post(
        f"/api/v1/hr/leave-requests/{request_id2}/approve",
        json={"comment": "ok"},
        headers=headers,
    )
    assert approve.status_code == 200
    assert approve.json()["status"] == "approved"

    # Insufficient balance check: request too many days
    too_many = client.post(
        "/api/v1/hr/leave-requests/apply",
        json={
            "employee_id": employee_id,
            "leave_type_id": leave_type_id,
            "date_from": "2026-02-02",
            "date_to": "2026-02-20",
            "reason": None,
        },
        headers=headers,
    )
    assert too_many.status_code == 400
    assert "Insufficient" in too_many.text
