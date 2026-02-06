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
    reason="Set RUN_DB_TESTS=1 to run integration core/audit tests.",
)
def test_core_crud_and_audit_logs_are_written() -> None:
    email = f"test-{uuid.uuid4().hex[:10]}@example.com"
    password = "Password123!"

    perm_codes = [
        "admin.users.read",
        "admin.users.write",
        "admin.roles.read",
        "admin.roles.write",
        "admin.permissions.read",
        "admin.permissions.write",
        "core.organizations.read",
        "core.organizations.write",
        "core.sites.read",
        "core.sites.write",
        "core.projects.read",
        "core.projects.write",
        "core.cost_centers.read",
        "core.cost_centers.write",
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

        role = create_role(db, name=f"role-{uuid.uuid4().hex[:8]}")
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

    # Admin endpoints (basic coverage)
    assert (
        client.get(
            "/api/v1/admin/users",
            headers=headers,
        ).status_code
        == 200
    )
    assert (
        client.get(
            "/api/v1/admin/roles",
            headers=headers,
        ).status_code
        == 200
    )
    assert (
        client.get(
            "/api/v1/admin/permissions",
            headers=headers,
        ).status_code
        == 200
    )

    perm_code = f"test.permission.{uuid.uuid4().hex[:10]}"
    perm_create = client.post(
        "/api/v1/admin/permissions",
        json={"code": perm_code, "description": "test"},
        headers=headers,
    )
    assert perm_create.status_code == 200
    perm_id = perm_create.json()["id"]
    perm_update = client.put(
        f"/api/v1/admin/permissions/{perm_id}",
        json={"description": "test-updated"},
        headers=headers,
    )
    assert perm_update.status_code == 200
    perm_delete = client.delete(
        f"/api/v1/admin/permissions/{perm_id}",
        headers=headers,
    )
    assert perm_delete.status_code == 200

    role_name = f"role-{uuid.uuid4().hex[:8]}"
    role_create = client.post(
        "/api/v1/admin/roles",
        json={"name": role_name},
        headers=headers,
    )
    assert role_create.status_code == 200
    role_id = role_create.json()["id"]
    role_update = client.put(
        f"/api/v1/admin/roles/{role_id}",
        json={"name": f"{role_name}-updated"},
        headers=headers,
    )
    assert role_update.status_code == 200
    role_delete = client.delete(
        f"/api/v1/admin/roles/{role_id}",
        headers=headers,
    )
    assert role_delete.status_code == 200

    created_user_email = f"created-{uuid.uuid4().hex[:10]}@example.com"
    user_create = client.post(
        "/api/v1/admin/users",
        json={
            "email": created_user_email,
            "password": "Password123!",
            "is_active": True,
        },
        headers=headers,
    )
    assert user_create.status_code == 200
    created_user_id = user_create.json()["id"]

    user_update = client.put(
        f"/api/v1/admin/users/{created_user_id}",
        json={"is_active": False},
        headers=headers,
    )
    assert user_update.status_code == 200

    roles = client.get("/api/v1/admin/roles", headers=headers).json()
    some_role_id = roles[0]["id"]
    set_roles = client.put(
        f"/api/v1/admin/users/{created_user_id}/roles",
        json={"role_ids": [some_role_id]},
        headers=headers,
    )
    assert set_roles.status_code == 200

    user_delete = client.delete(
        f"/api/v1/admin/users/{created_user_id}",
        headers=headers,
    )
    assert user_delete.status_code == 200

    # Organizations
    org_code = f"ORG-{uuid.uuid4().hex[:6]}"
    org_create = client.post(
        "/api/v1/core/organizations",
        json={"code": org_code, "name": f"Org {org_code}", "is_active": True},
        headers=headers,
    )
    assert org_create.status_code == 200
    org_request_id = org_create.headers.get("X-Request-Id")
    assert org_request_id
    org_id = org_create.json()["id"]

    org_get = client.get(
        f"/api/v1/core/organizations/{org_id}",
        headers=headers,
    )
    assert org_get.status_code == 200

    org_list = client.get("/api/v1/core/organizations", headers=headers)
    assert org_list.status_code == 200

    org_update = client.put(
        f"/api/v1/core/organizations/{org_id}",
        json={"name": f"Org {org_code} Updated"},
        headers=headers,
    )
    assert org_update.status_code == 200

    org_delete = client.delete(
        f"/api/v1/core/organizations/{org_id}",
        headers=headers,
    )
    assert org_delete.status_code == 200

    org_delete_request_id = org_delete.headers.get("X-Request-Id")
    assert org_delete_request_id
    audit_for_org_delete = client.get(
        f"/api/v1/admin/audit-logs?request_id={org_delete_request_id}",
        headers=headers,
    )
    assert audit_for_org_delete.status_code == 200
    delete_rows = audit_for_org_delete.json()
    assert any(
        r.get("entity_type") == "organizations" and r.get("action") == "delete" for r in delete_rows
    )

    # Verify audit logs (create request_id is the tightest correlation)
    audit_for_org_create = client.get(
        f"/api/v1/admin/audit-logs?request_id={org_request_id}",
        headers=headers,
    )
    assert audit_for_org_create.status_code == 200
    rows = audit_for_org_create.json()
    assert len(rows) >= 1
    assert any(
        r.get("entity_type") == "organizations" and r.get("action") == "create" for r in rows
    )

    # Cost Centers (minimal coverage)
    org2 = client.post(
        "/api/v1/core/organizations",
        json={
            "code": f"ORG-{uuid.uuid4().hex[:6]}",
            "name": f"Org {uuid.uuid4().hex[:6]}",
            "is_active": True,
        },
        headers=headers,
    )
    assert org2.status_code == 200
    org2_id = org2.json()["id"]

    cc_code = f"CC-{uuid.uuid4().hex[:6]}"
    cc_create = client.post(
        "/api/v1/core/cost-centers",
        json={
            "organization_id": org2_id,
            "code": cc_code,
            "name": f"Cost Center {cc_code}",
            "is_active": True,
        },
        headers=headers,
    )
    assert cc_create.status_code == 200
    cc_id = cc_create.json()["id"]

    assert (
        client.get(
            "/api/v1/core/cost-centers",
            headers=headers,
        ).status_code
        == 200
    )
    assert (
        client.get(
            f"/api/v1/core/cost-centers/{cc_id}",
            headers=headers,
        ).status_code
        == 200
    )

    cc_update = client.put(
        f"/api/v1/core/cost-centers/{cc_id}",
        json={"name": f"Cost Center {cc_code} Updated"},
        headers=headers,
    )
    assert cc_update.status_code == 200

    cc_delete = client.delete(
        f"/api/v1/core/cost-centers/{cc_id}",
        headers=headers,
    )
    assert cc_delete.status_code == 200

    # Sites + Projects (minimal coverage)
    site_code = f"SITE-{uuid.uuid4().hex[:6]}"
    site_create = client.post(
        "/api/v1/core/sites",
        json={
            "organization_id": org2_id,
            "code": site_code,
            "name": f"Site {site_code}",
            "is_active": True,
        },
        headers=headers,
    )
    assert site_create.status_code == 200
    site_id = site_create.json()["id"]
    assert (
        client.get(
            "/api/v1/core/sites",
            headers=headers,
        ).status_code
        == 200
    )
    assert (
        client.get(
            f"/api/v1/core/sites/{site_id}",
            headers=headers,
        ).status_code
        == 200
    )
    assert (
        client.put(
            f"/api/v1/core/sites/{site_id}",
            json={"name": f"Site {site_code} Updated"},
            headers=headers,
        ).status_code
        == 200
    )

    project_code = f"PRJ-{uuid.uuid4().hex[:6]}"
    project_create = client.post(
        "/api/v1/core/projects",
        json={
            "organization_id": org2_id,
            "site_id": site_id,
            "code": project_code,
            "name": f"Project {project_code}",
            "is_active": True,
        },
        headers=headers,
    )
    assert project_create.status_code == 200
    project_id = project_create.json()["id"]
    assert (
        client.get(
            "/api/v1/core/projects",
            headers=headers,
        ).status_code
        == 200
    )
    assert (
        client.get(
            f"/api/v1/core/projects/{project_id}",
            headers=headers,
        ).status_code
        == 200
    )
    assert (
        client.put(
            f"/api/v1/core/projects/{project_id}",
            json={"name": f"Project {project_code} Updated"},
            headers=headers,
        ).status_code
        == 200
    )
    assert (
        client.delete(
            f"/api/v1/core/projects/{project_id}",
            headers=headers,
        ).status_code
        == 200
    )

    assert (
        client.delete(
            f"/api/v1/core/sites/{site_id}",
            headers=headers,
        ).status_code
        == 200
    )
