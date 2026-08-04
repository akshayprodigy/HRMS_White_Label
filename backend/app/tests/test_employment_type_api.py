import pytest
from httpx import AsyncClient, ASGITransport

from app.core.config import settings
from app.api.deps import get_current_user, get_db, verify_attendance
from app.models.user import User, Role, Permission
from unittest.mock import AsyncMock

BASE = settings.API_V1_STR

role_hr = Role(id=1, name="HR")
role_hr.permissions = [Permission(name="hr employee write")]
role_none = Role(id=2, name="Staff")
role_none.permissions = [Permission(name="hr employee read")]
user_hr = User(id=1, email="hr@test.com", full_name="HR", is_active=True, is_superuser=False, roles=[role_hr])
user_none = User(id=2, email="s@test.com", full_name="S", is_active=True, is_superuser=False, roles=[role_none])


def _db_no_clash():
    """AsyncMock db where the code-clash lookup returns None and refresh
    stamps the id/timestamps so the response serializes."""
    db = AsyncMock()
    scalars = AsyncMock()
    scalars.first = lambda: None
    exec_result = AsyncMock()
    exec_result.scalars = lambda: scalars
    db.execute = AsyncMock(return_value=exec_result)

    async def _refresh(obj):
        from datetime import datetime, timezone
        obj.id = 99
        obj.created_at = datetime.now(timezone.utc)
        obj.updated_at = datetime.now(timezone.utc)

    db.commit = AsyncMock()
    db.refresh = AsyncMock(side_effect=_refresh)
    db.add = lambda obj: None
    return db


@pytest.mark.asyncio
async def test_create_employment_type_forbidden_without_hr_write(app):
    app.dependency_overrides[verify_attendance] = lambda: None
    app.dependency_overrides[get_current_user] = lambda: user_none
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(f"{BASE}/hr/employment-types", json={"code": "consultant", "name": "Consultant"})
            assert resp.status_code == 403, resp.text
    finally:
        app.dependency_overrides = {}


@pytest.mark.asyncio
async def test_create_employment_type_ok_lowercases_code(app):
    db = _db_no_clash()

    async def _get_db():
        return db

    app.dependency_overrides[verify_attendance] = lambda: None
    app.dependency_overrides[get_current_user] = lambda: user_hr
    app.dependency_overrides[get_db] = _get_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(f"{BASE}/hr/employment-types",
                                 json={"code": "Consultant", "name": "Consultant",
                                       "statutory_enabled": False, "flat_tds_rate": 0.1})
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["code"] == "consultant"  # lowercased
            assert body["statutory_enabled"] is False
    finally:
        app.dependency_overrides = {}
