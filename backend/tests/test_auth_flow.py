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
    reason="Set RUN_DB_TESTS=1 to run integration auth tests.",
)
def test_login_refresh_logout_and_permissions() -> None:
    email = f"test-{uuid.uuid4().hex[:10]}@example.com"
    password = "Password123!"

    with SessionLocal() as db:
        user = create_user(db, email=email, password=password, is_active=True)

        # Minimal admin perms to hit /admin/users
        perm_read = db.execute(
            select(Permission).where(Permission.code == "admin.users.read")
        ).scalar_one_or_none()
        if perm_read is None:
            perm_read = create_permission(
                db,
                code="admin.users.read",
                description=None,
            )

        perm_write = db.execute(
            select(Permission).where(Permission.code == "admin.users.write")
        ).scalar_one_or_none()
        if perm_write is None:
            perm_write = create_permission(
                db,
                code="admin.users.write",
                description=None,
            )

        role = create_role(db, name=f"role-{uuid.uuid4().hex[:8]}")
        set_role_permissions(
            db,
            role_id=role.id,
            permission_ids=[perm_read.id, perm_write.id],
        )
        set_user_roles(db, user_id=user.id, role_ids=[role.id])

    client = TestClient(app)

    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200
    body = login.json()
    assert "access_token" in body
    assert body["user"]["email"] == email
    assert "admin.users.read" in body["permissions"]

    # Refresh cookie should be set on the client cookie jar
    assert "refresh_token" in client.cookies

    access_token_1 = body["access_token"]

    me = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token_1}"},
    )
    assert me.status_code == 200
    assert me.json()["user"]["email"] == email

    # Permission-protected route: /admin/users
    users = client.get(
        "/api/v1/admin/users",
        headers={"Authorization": f"Bearer {access_token_1}"},
    )
    assert users.status_code == 200

    refresh = client.post("/api/v1/auth/refresh")
    assert refresh.status_code == 200
    access_token_2 = refresh.json()["access_token"]
    assert access_token_2 != access_token_1

    logout = client.post("/api/v1/auth/logout")
    assert logout.status_code == 200
