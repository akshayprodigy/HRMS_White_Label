import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock

from app.core.config import settings
from app.api.deps import get_current_user, get_db, verify_attendance
from app.models.user import User, Role, Permission

BASE = settings.API_V1_STR

role_hr = Role(id=1, name="HR")
role_hr.permissions = [Permission(name="hr employee write")]
role_none = Role(id=2, name="Staff")
role_none.permissions = [Permission(name="hr employee read")]
user_hr = User(id=1, email="hr@test.com", full_name="HR", is_active=True, is_superuser=False, roles=[role_hr])
user_none = User(id=2, email="s@test.com", full_name="S", is_active=True, is_superuser=False, roles=[role_none])


def _db_no_clash():
    db = AsyncMock()
    scalars = AsyncMock()
    scalars.first = lambda: None
    exec_result = AsyncMock()
    exec_result.scalars = lambda: scalars
    db.execute = AsyncMock(return_value=exec_result)

    async def _refresh(obj):
        from datetime import datetime, timezone
        obj.id = 77
        obj.created_at = datetime.now(timezone.utc)
        obj.updated_at = datetime.now(timezone.utc)

    db.commit = AsyncMock()
    db.refresh = AsyncMock(side_effect=_refresh)
    db.add = lambda obj: None
    return db


@pytest.mark.asyncio
async def test_create_component_forbidden_without_hr_write(app):
    app.dependency_overrides[verify_attendance] = lambda: None
    app.dependency_overrides[get_current_user] = lambda: user_none
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(f"{BASE}/hr/salary-components",
                                 json={"code": "medical", "name": "Medical"})
            assert resp.status_code == 403, resp.text
    finally:
        app.dependency_overrides = {}


@pytest.mark.asyncio
async def test_create_component_ok_lowercases_code(app):
    db = _db_no_clash()

    async def _get_db():
        return db

    app.dependency_overrides[verify_attendance] = lambda: None
    app.dependency_overrides[get_current_user] = lambda: user_hr
    app.dependency_overrides[get_db] = _get_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(f"{BASE}/hr/salary-components",
                                 json={"code": "Medical", "name": "Medical Allowance",
                                       "slot": "other", "default_calc_method": "flat"})
            assert resp.status_code == 200, resp.text
            assert resp.json()["code"] == "medical"
    finally:
        app.dependency_overrides = {}


@pytest.mark.asyncio
async def test_create_component_rejects_bad_slot(app):
    db = _db_no_clash()

    async def _get_db():
        return db

    app.dependency_overrides[verify_attendance] = lambda: None
    app.dependency_overrides[get_current_user] = lambda: user_hr
    app.dependency_overrides[get_db] = _get_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(f"{BASE}/hr/salary-components",
                                 json={"code": "weird", "name": "Weird", "slot": "bonus"})
            assert resp.status_code == 400, resp.text
    finally:
        app.dependency_overrides = {}


@pytest.mark.asyncio
async def test_create_template_forbidden_without_hr_write(app):
    app.dependency_overrides[verify_attendance] = lambda: None
    app.dependency_overrides[get_current_user] = lambda: user_none
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(f"{BASE}/hr/salary-templates",
                                 json={"code": "std", "name": "Standard"})
            assert resp.status_code == 403, resp.text
    finally:
        app.dependency_overrides = {}
