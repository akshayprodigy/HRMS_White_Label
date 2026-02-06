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
    reason="Set RUN_DB_TESTS=1 to run integration HR tests.",
)
def test_hr_employees_documents_assets_and_audit() -> None:
    email = f"test-hr-{uuid.uuid4().hex[:10]}@example.com"
    password = "Password123!"

    perm_codes = [
        "hr.employees.read",
        "hr.employees.write",
        "hr.employee_documents.read",
        "hr.employee_documents.write",
        "hr.employee_assets.read",
        "hr.employee_assets.write",
        "admin.audit_logs.read",
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

        role = create_role(db, name=f"role-hr-{uuid.uuid4().hex[:8]}")
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
            "first_name": "Alex",
            "last_name": "Doe",
            "email": f"alex-{uuid.uuid4().hex[:6]}@example.com",
            "phone": "1234567890",
            "employment_type": "full_time",
            "employment_status": "active",
            "joining_date": "2026-01-01",
        },
        headers=headers,
    )
    assert employee_create.status_code == 200
    request_id = employee_create.headers.get("X-Request-Id")
    assert request_id
    employee_id = employee_create.json()["id"]

    employee_get = client.get(
        f"/api/v1/hr/employees/{employee_id}",
        headers=headers,
    )
    assert employee_get.status_code == 200

    employee_list = client.get("/api/v1/hr/employees", headers=headers)
    assert employee_list.status_code == 200
    assert any(e["id"] == employee_id for e in employee_list.json())

    employee_update = client.put(
        f"/api/v1/hr/employees/{employee_id}",
        json={"employment_status": "inactive"},
        headers=headers,
    )
    assert employee_update.status_code == 200
    assert employee_update.json()["employment_status"] == "inactive"

    audit = client.get(
        f"/api/v1/admin/audit-logs?request_id={request_id}",
        headers=headers,
    )
    assert audit.status_code == 200
    rows = audit.json()
    assert any(
        r.get("entity_type") == "employees" and r.get("action") == "create"
        for r in rows
    )

    doc_create = client.post(
        f"/api/v1/hr/employees/{employee_id}/documents",
        json={
            "document_type": "aadhaar",
            "title": "Aadhaar",
            "file_ref": "s3://bucket/aadhaar.pdf",
        },
        headers=headers,
    )
    assert doc_create.status_code == 200
    doc_id = doc_create.json()["id"]

    doc_list = client.get(
        f"/api/v1/hr/employees/{employee_id}/documents",
        headers=headers,
    )
    assert doc_list.status_code == 200
    assert any(d["id"] == doc_id for d in doc_list.json())

    asset_assign = client.post(
        f"/api/v1/hr/employees/{employee_id}/assets",
        json={
            "asset_category": "ppe",
            "asset_name": "Helmet",
            "asset_tag": "H-001",
            "issued_on": "2026-01-02",
        },
        headers=headers,
    )
    assert asset_assign.status_code == 200
    asset_id = asset_assign.json()["id"]

    asset_return = client.put(
        f"/api/v1/hr/employees/{employee_id}/assets/{asset_id}",
        json={"returned_on": "2026-01-10"},
        headers=headers,
    )
    assert asset_return.status_code == 200
    assert asset_return.json()["returned_on"] == "2026-01-10"

    asset_list = client.get(
        f"/api/v1/hr/employees/{employee_id}/assets",
        headers=headers,
    )
    assert asset_list.status_code == 200
    assert any(a["id"] == asset_id for a in asset_list.json())

    doc_delete = client.delete(
        f"/api/v1/hr/employees/{employee_id}/documents/{doc_id}",
        headers=headers,
    )
    assert doc_delete.status_code == 200

    asset_delete = client.delete(
        f"/api/v1/hr/employees/{employee_id}/assets/{asset_id}",
        headers=headers,
    )
    assert asset_delete.status_code == 200

    employee_delete = client.delete(
        f"/api/v1/hr/employees/{employee_id}",
        headers=headers,
    )
    assert employee_delete.status_code == 200
