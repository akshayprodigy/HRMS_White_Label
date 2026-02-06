from __future__ import annotations

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
    reason="Set RUN_DB_TESTS=1 to run integration Profitability tests.",
)
def test_projects_profitability_rollup() -> None:
    email = f"test-profit-{uuid.uuid4().hex[:10]}@example.com"
    password = "Password123!"

    uom_code = f"U{uuid.uuid4().hex[:6].upper()}"
    warehouse_code = f"WH-{uuid.uuid4().hex[:6].upper()}"

    perm_codes = [
        "core.organizations.read",
        "core.organizations.write",
        "core.projects.read",
        "core.projects.write",
        "core.cost_centers.read",
        "core.cost_centers.write",
        "hr.employees.read",
        "hr.employees.write",
        "hr.attendance.read",
        "hr.attendance.write",
        "inventory.uoms.read",
        "inventory.uoms.write",
        "inventory.items.read",
        "inventory.items.write",
        "inventory.warehouses.read",
        "inventory.warehouses.write",
        "inventory.grns.read",
        "inventory.grns.write",
        "inventory.issues.read",
        "inventory.issues.write",
        "projects.finance.read",
        "projects.finance.write",
        "projects.profitability.read",
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

        role = create_role(db, name=f"role-profit-{uuid.uuid4().hex[:8]}")
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

    org_create = client.post(
        "/api/v1/core/organizations",
        json={
            "code": f"ORG-{uuid.uuid4().hex[:6]}",
            "name": f"Org {uuid.uuid4().hex[:8]}",
        },
        headers=headers,
    )
    assert org_create.status_code == 200
    org_id = org_create.json()["id"]

    project_create = client.post(
        "/api/v1/core/projects",
        json={
            "organization_id": org_id,
            "site_id": None,
            "code": f"PRJ-{uuid.uuid4().hex[:6]}",
            "name": "Test Project",
        },
        headers=headers,
    )
    assert project_create.status_code == 200
    project_id = project_create.json()["id"]

    cc_create = client.post(
        "/api/v1/core/cost-centers",
        json={
            "organization_id": org_id,
            "code": f"CC-{uuid.uuid4().hex[:6]}",
            "name": "Test Cost Center",
        },
        headers=headers,
    )
    assert cc_create.status_code == 200
    cost_center_id = cc_create.json()["id"]

    employee_create = client.post(
        "/api/v1/hr/employees",
        json={
            "employee_code": f"E-{uuid.uuid4().hex[:6]}",
            "first_name": "Test",
            "last_name": "Worker",
            "employment_type": "full_time",
            "employment_status": "active",
            "joining_date": "2026-01-01",
        },
        headers=headers,
    )
    assert employee_create.status_code == 200
    employee_id = employee_create.json()["id"]

    uom_create = client.post(
        "/api/v1/inventory/uoms",
        json={"code": uom_code, "name": "Numbers", "symbol": uom_code.lower()},
        headers=headers,
    )
    assert uom_create.status_code == 200
    uom_id = uom_create.json()["id"]

    item_create = client.post(
        "/api/v1/inventory/items",
        json={
            "sku": f"IT-{uuid.uuid4().hex[:6]}",
            "name": "Test Item",
            "description": None,
            "base_uom_id": uom_id,
        },
        headers=headers,
    )
    assert item_create.status_code == 200
    item_id = item_create.json()["id"]

    wh_create = client.post(
        "/api/v1/inventory/warehouses",
        json={"code": warehouse_code, "name": "Main", "location": None},
        headers=headers,
    )
    assert wh_create.status_code == 200
    warehouse_id = wh_create.json()["id"]

    grn_create = client.post(
        "/api/v1/inventory/grns",
        json={
            "grn_number": f"GRN-{uuid.uuid4().hex[:8]}",
            "grn_date": "2026-01-05",
            "purchase_order_id": None,
            "vendor_name": "Vendor",
            "warehouse_id": warehouse_id,
            "item_id": item_id,
            "uom_id": uom_id,
            "qty_received": 10,
            "unit_cost": 12.5,
            "notes": None,
        },
        headers=headers,
    )
    assert grn_create.status_code == 200

    issue_create = client.post(
        "/api/v1/inventory/issues",
        json={
            "issue_number": f"ISS-{uuid.uuid4().hex[:8]}",
            "issue_date": "2026-01-06",
            "project_id": project_id,
            "cost_center_id": cost_center_id,
            "warehouse_id": warehouse_id,
            "item_id": item_id,
            "uom_id": uom_id,
            "qty_issued": 4,
            "unit_cost": 12.5,
            "remarks": "Issued to site",
        },
        headers=headers,
    )
    assert issue_create.status_code == 200

    att_post = client.post(
        "/api/v1/hr/attendance",
        json={
            "employee_id": employee_id,
            "project_id": project_id,
            "work_date": "2026-01-06",
            "hours": 8,
            "hourly_rate": 100,
            "notes": None,
        },
        headers=headers,
    )
    assert att_post.status_code == 200

    rev_post = client.post(
        f"/api/v1/projects/{project_id}/revenues",
        json={
            "revenue_date": "2026-01-07",
            "category": "Contract",
            "description": None,
            "amount": 10000,
            "client": None,
            "reference_no": None,
            "notes": None,
        },
        headers=headers,
    )
    assert rev_post.status_code == 200

    exp_post = client.post(
        f"/api/v1/projects/{project_id}/direct-expenses",
        json={
            "expense_date": "2026-01-06",
            "category": "Fuel",
            "description": None,
            "amount": 200,
            "vendor": None,
            "reference_no": None,
            "notes": None,
        },
        headers=headers,
    )
    assert exp_post.status_code == 200

    resp = client.get(
        f"/api/v1/projects/{project_id}/profitability",
        params={"date_from": "2026-01-01", "date_to": "2026-01-31"},
        headers=headers,
    )
    assert resp.status_code == 200
    payload = resp.json()

    assert payload["project_id"] == project_id
    assert float(payload["revenue_total"]) == pytest.approx(10000.0)
    assert float(payload["labor_hours_total"]) == pytest.approx(8.0)
    assert float(payload["labor_cost_total"]) == pytest.approx(800.0)
    assert float(payload["materials_qty_total"]) == pytest.approx(4.0)
    assert float(payload["materials_cost_total"]) == pytest.approx(50.0)
    assert float(payload["direct_expenses_total"]) == pytest.approx(200.0)

    assert float(payload["total_cost"]) == pytest.approx(1050.0)
    assert float(payload["gross_profit"]) == pytest.approx(8950.0)
    assert float(payload["gross_margin_percent"]) == pytest.approx(89.5)

    assert any(
        r["category"] == "Contract" for r in payload["revenue_by_category"]
    )
    assert any(
        r["category"] == "Fuel"
        for r in payload["direct_expenses_by_category"]
    )
    assert any(
        r["employee_id"] == employee_id for r in payload["labor_by_employee"]
    )
    assert any(r["item_id"] == item_id for r in payload["materials_by_item"])
