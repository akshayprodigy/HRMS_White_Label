import pytest
from httpx import AsyncClient, ASGITransport

from app.core.config import settings
from app.api.deps import get_current_user, get_db, verify_attendance
from app.models.user import User, Role, Permission
from app.models.department import Department
from unittest.mock import AsyncMock

BASE = settings.API_V1_STR

role_with_perm = Role(id=1, name="HR")
role_with_perm.permissions = [Permission(name="department head write")]

role_no_perm = Role(id=2, name="Staff")
role_no_perm.permissions = [Permission(name="hr employee read")]

user_with_perm = User(id=1, email="hr@test.com", full_name="HR", is_active=True, is_superuser=False, roles=[role_with_perm])
user_no_perm = User(id=2, email="staff@test.com", full_name="Staff", is_active=True, is_superuser=False, roles=[role_no_perm])


@pytest.mark.asyncio
async def test_assign_head_forbidden_without_permission(app):
    app.dependency_overrides[verify_attendance] = lambda: None
    app.dependency_overrides[get_current_user] = lambda: user_no_perm
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.patch(f"{BASE}/functional-head/departments/1", json={"head_user_id": 5})
            assert resp.status_code == 403, resp.text
    finally:
        app.dependency_overrides = {}


@pytest.mark.asyncio
async def test_assign_head_sets_head_user_id(app):
    dept = Department(id=1, name="Engineering", description=None, is_active=True)

    async def override_db():
        db = AsyncMock()
        db.get = AsyncMock(return_value=dept)  # Department lookup AND user-exists check
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        return db

    app.dependency_overrides[verify_attendance] = lambda: None
    app.dependency_overrides[get_current_user] = lambda: user_with_perm
    app.dependency_overrides[get_db] = override_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.patch(f"{BASE}/functional-head/departments/1", json={"head_user_id": 5})
            assert resp.status_code == 200, resp.text
            assert resp.json()["head_user_id"] == 5
    finally:
        app.dependency_overrides = {}


@pytest.mark.asyncio
async def test_assign_head_404_when_department_missing(app):
    async def override_db():
        db = AsyncMock()
        db.get = AsyncMock(return_value=None)
        return db

    app.dependency_overrides[verify_attendance] = lambda: None
    app.dependency_overrides[get_current_user] = lambda: user_with_perm
    app.dependency_overrides[get_db] = override_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.patch(f"{BASE}/functional-head/departments/999", json={"head_user_id": 5})
            assert resp.status_code == 404, resp.text
    finally:
        app.dependency_overrides = {}
