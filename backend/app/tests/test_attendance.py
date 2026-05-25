import pytest
import os
from httpx import ASGITransport, AsyncClient
from app.core.config import settings
from app.db.session import engine


@pytest.fixture(autouse=True)
async def auto_dispose_engine():
    yield
    await engine.dispose()


@pytest.fixture
def app():
    from app.main import create_app
    return create_app()


@pytest.mark.asyncio
async def test_attendance_mark_and_today(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. Login
        username = os.getenv("PYTEST_ADMIN_USERNAME", "admin@example.com")
        password = os.getenv("PYTEST_ADMIN_PASSWORD", "admin123")
        login_data = {
            "username": username,
            "password": password,
        }
        login_response = await ac.post(
            f"{settings.API_V1_STR}/auth/login",
            data=login_data
        )
        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Check today (may already be marked if DB persists across runs)
        today_response = await ac.get(
            f"{settings.API_V1_STR}/attendance/today",
            headers=headers
        )
        assert today_response.status_code == 200
        already_marked = today_response.json().get("is_marked") is True

        # 3. Mark attendance
        mark_data = {
            "mode": "office",
            "remarks": "test marking",
            "latitude": 12.34,
            "longitude": 56.78,
            "accuracy": 10.0,
        }
        mark_response = await ac.post(
            f"{settings.API_V1_STR}/attendance/mark",
            json=mark_data,
            headers=headers
        )
        assert mark_response.status_code == 200
        marked = mark_response.json()
        assert isinstance(marked.get("id"), int)
        marked_id = marked["id"]
        if not already_marked:
            assert marked.get("mode") == "office"
        
        # 4. Check today (should be true)
        today_response = await ac.get(
            f"{settings.API_V1_STR}/attendance/today",
            headers=headers
        )
        assert today_response.status_code == 200
        assert today_response.json()["is_marked"] is True
        assert today_response.json()["attendance"] is not None
        assert today_response.json()["attendance"]["id"] == marked_id

        # 5. Try marking again (should fail)
        mark_response = await ac.post(
            f"{settings.API_V1_STR}/attendance/mark",
            json=mark_data,
            headers=headers
        )
        assert mark_response.status_code == 200
        assert mark_response.json()["id"] == marked_id
