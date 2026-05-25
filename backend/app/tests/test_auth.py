import pytest
from httpx import ASGITransport, AsyncClient
import os
from app.main import create_app
from app.core.config import settings
from app.db.session import engine


@pytest.fixture(autouse=True)
async def auto_dispose_engine():
    yield
    await engine.dispose()


@pytest.fixture
def app():
    return create_app()


@pytest.mark.asyncio
async def test_auth_flow(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. Login
        username = os.getenv("PYTEST_ADMIN_USERNAME", "admin@example.com")
        password = os.getenv("PYTEST_ADMIN_PASSWORD", "admin123")
        login_data = {
            "username": username,
            "password": password,
        }
        response = await ac.post(
            f"{settings.API_V1_STR}/auth/login",
            data=login_data
        )
        assert response.status_code == 200
        tokens = response.json()
        assert "access_token" in tokens
        assert "refresh_token" in tokens
        access_token = tokens["access_token"]
        refresh_token = tokens["refresh_token"]

        # 2. Get Me (Success)
        headers = {"Authorization": f"Bearer {access_token}"}
        response = await ac.get(
            f"{settings.API_V1_STR}/auth/me",
            headers=headers
        )
        assert response.status_code == 200
        user_data = response.json()
        assert user_data["email"] == "admin@example.com"

        # 3. Refresh Token
        response = await ac.post(
            f"{settings.API_V1_STR}/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert response.status_code == 200
        new_tokens = response.json()
        assert "access_token" in new_tokens
        # Tokens may match if refreshed in the same second.

        # 4. Get Me (with new token)
        headers = {"Authorization": f"Bearer {new_tokens['access_token']}"}
        response = await ac.get(
            f"{settings.API_V1_STR}/auth/me",
            headers=headers
        )
        assert response.status_code == 200
        
        # 5. Logout
        response = await ac.post(f"{settings.API_V1_STR}/auth/logout")
        assert response.status_code == 200
        assert response.json() == {"message": "Successfully logged out"}


@pytest.mark.asyncio
async def test_login_failure(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        username = os.getenv("PYTEST_ADMIN_USERNAME", "admin@example.com")
        login_data = {
            "username": username,
            "password": "wrongpassword"
        }
        response = await ac.post(
            f"{settings.API_V1_STR}/auth/login",
            data=login_data
        )
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "401"
