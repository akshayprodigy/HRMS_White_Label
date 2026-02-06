from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.database import SessionLocal
from app.db.models.iam import Permission
from app.db.models.inventory import StockLedger
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
    reason="Set RUN_DB_TESTS=1 to run integration Inventory tests.",
)
def test_inventory_grn_issue_ledger_and_report() -> None:
    email = f"test-inv-{uuid.uuid4().hex[:10]}@example.com"
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
        "inventory.reports.project_consumption.read",
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

        role = create_role(db, name=f"role-inv-{uuid.uuid4().hex[:8]}")
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

    grn_number = f"GRN-{uuid.uuid4().hex[:8]}"
    grn_create = client.post(
        "/api/v1/inventory/grns",
        json={
            "grn_number": grn_number,
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
    grn_id = grn_create.json()["id"]

    issue_number = f"ISS-{uuid.uuid4().hex[:8]}"
    issue_create = client.post(
        "/api/v1/inventory/issues",
        json={
            "issue_number": issue_number,
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
    issue_id = issue_create.json()["id"]

    issue_too_much = client.post(
        "/api/v1/inventory/issues",
        json={
            "issue_number": f"ISS-{uuid.uuid4().hex[:8]}",
            "issue_date": "2026-01-06",
            "project_id": project_id,
            "cost_center_id": cost_center_id,
            "warehouse_id": warehouse_id,
            "item_id": item_id,
            "uom_id": uom_id,
            "qty_issued": 1000,
            "unit_cost": 12.5,
            "remarks": None,
        },
        headers=headers,
    )
    assert issue_too_much.status_code == 400
    assert issue_too_much.json().get("detail") == "Insufficient stock"

    report = client.get(
        "/api/v1/inventory/reports/project-consumption",
        params={
            "date_from": "2026-01-01",
            "date_to": "2026-01-31",
            "project_id": project_id,
        },
        headers=headers,
    )
    assert report.status_code == 200
    rows = report.json()
    assert any(
        r["project_id"] == project_id
        and r["item_id"] == item_id
        and float(r["qty_issued"]) == pytest.approx(4.0)
        for r in rows
    )

    with SessionLocal() as db:
        grn_ledger = db.execute(
            select(StockLedger).where(
                StockLedger.source_type == "grn",
                StockLedger.source_id == grn_id,
            )
        ).scalar_one()
        assert float(grn_ledger.qty_in) == pytest.approx(10.0)
        assert float(grn_ledger.qty_out) == pytest.approx(0.0)
        assert grn_ledger.project_id is None
        assert grn_ledger.cost_center_id is None

        issue_ledger = db.execute(
            select(StockLedger).where(
                StockLedger.source_type == "issue",
                StockLedger.source_id == issue_id,
            )
        ).scalar_one()
        assert float(issue_ledger.qty_in) == pytest.approx(0.0)
        assert float(issue_ledger.qty_out) == pytest.approx(4.0)
        assert issue_ledger.project_id == project_id
        assert issue_ledger.cost_center_id == cost_center_id
