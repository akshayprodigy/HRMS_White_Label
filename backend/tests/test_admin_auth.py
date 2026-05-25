import pytest
from httpx import AsyncClient
from app.main import app
from app.core.config import settings

@pytest.mark.asyncio
async def test_admin_access_unauthorized(client: AsyncClient):
    # Test that a normal user without 'admin access' cannot access admin endpoints
    # We'll use the login endpoint to get a token for user2 (standard user usually)
    # But since we're in a test env, we might need to mock or use the DB
    response = await client.get(f"{settings.API_V1_STR}/admin/users")
    assert response.status_code == 401 # No token

@pytest.mark.asyncio
async def test_admin_access_forbidden(client: AsyncClient, normal_user_token_headers):
    # Test that a logged in user without the permission gets 403
    response = await client.get(
        f"{settings.API_V1_STR}/admin/users", 
        headers=normal_user_token_headers
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"

@pytest.mark.asyncio
async def test_admin_access_granted(client: AsyncClient, superuser_token_headers):
    # Test that a super admin can access
    response = await client.get(
        f"{settings.API_V1_STR}/admin/users", 
        headers=superuser_token_headers
    )
    assert response.status_code == 200
    assert isinstance(response.json(), list)
