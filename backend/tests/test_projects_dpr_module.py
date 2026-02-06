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
    reason="Set RUN_DB_TESTS=1 to run integration DPR tests.",
)
def test_projects_dpr_create_list_and_metrics() -> None:
    email = f"test-dpr-{uuid.uuid4().hex[:10]}@example.com"
    password = "Password123!"

    perm_codes = [
        "core.organizations.read",
        "core.organizations.write",
        "core.projects.read",
        "core.projects.write",
        "projects.dprs.read",
        "projects.dprs.write",
        "projects.dprs.metrics.read",
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

        role = create_role(db, name=f"role-dpr-{uuid.uuid4().hex[:8]}")
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

    dpr_create = client.post(
        "/api/v1/projects/dprs",
        json={
            "project_id": project_id,
            "dpr_date": "2026-01-07",
            "shift": "Day",
            "remarks": "Initial DPR",
            "drilling_lines": [
                {
                    "line_no": 1,
                    "location": "BH-1",
                    "meters_drilled": 100,
                    "recovered_meters": 95,
                },
                {
                    "line_no": 2,
                    "location": "BH-2",
                    "meters_drilled": 50,
                    "recovered_meters": 40,
                },
            ],
            "activity_lines": [
                {
                    "line_no": 1,
                    "activity": "Rig setup",
                    "hours": 2,
                    "remarks": None,
                }
            ],
            "consumption_lines": [],
        },
        headers=headers,
    )
    assert dpr_create.status_code == 200
    dpr_id = dpr_create.json()["id"]

    dpr_list = client.get(
        "/api/v1/projects/dprs",
        params={"project_id": project_id, "include_lines": True},
        headers=headers,
    )
    assert dpr_list.status_code == 200
    rows = dpr_list.json()
    assert any(r["id"] == dpr_id for r in rows)

    metrics = client.get(
        f"/api/v1/projects/dprs/{dpr_id}/metrics",
        headers=headers,
    )
    assert metrics.status_code == 200
    payload = metrics.json()
    assert payload["dpr_id"] == dpr_id
    assert float(payload["meters_drilled_total"]) == pytest.approx(150.0)
    assert float(payload["recovered_meters_total"]) == pytest.approx(135.0)
    assert float(payload["recovery_percent"]) == pytest.approx(90.0)
