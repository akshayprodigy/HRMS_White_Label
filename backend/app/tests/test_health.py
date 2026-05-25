import pytest
from httpx import AsyncClient
from app.main import create_app
from app.core.config import settings

@pytest.fixture
def app():
    return create_app()

@pytest.mark.asyncio
async def test_health_check(app):
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get(f"{settings.API_V1_STR}/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

@pytest.mark.asyncio
async def test_request_id_middleware(app):
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get(f"{settings.API_V1_STR}/health")
    assert "X-Request-ID" in response.headers
