import pytest
from httpx import ASGITransport, AsyncClient
import os

from app.core.config import settings
from app.db.session import SessionLocal, engine
from app.main import create_app


@pytest.fixture(autouse=True)
async def auto_dispose_engine():
    # Ensures pooled aiomysql connections don't outlive the test loop.
    yield
    await engine.dispose()


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def db():
    async with SessionLocal() as session:
        yield session
        # Keep DB as clean as possible between tests.
        await session.rollback()


async def _ensure_attendance(client: AsyncClient, headers: dict) -> None:
    today_url = f"{settings.API_V1_STR}/attendance/today"
    today = await client.get(today_url, headers=headers)
    if (
        today.status_code == 200
        and (today.json() or {}).get("is_marked") is True
    ):
        return

    mark = await client.post(
        f"{settings.API_V1_STR}/attendance/mark",
        headers=headers,
        json={"mode": "office", "remarks": "pytest"},
    )
    # 200 OK or 400 ALREADY_MARKED
    if mark.status_code in (200, 400):
        return


@pytest.fixture
async def admin_token_headers(client: AsyncClient) -> dict:
    username = os.getenv("PYTEST_ADMIN_USERNAME", "admin@example.com")
    password = os.getenv("PYTEST_ADMIN_PASSWORD", "admin123")
    resp = await client.post(
        f"{settings.API_V1_STR}/auth/login",
        data={"username": username, "password": password},
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    await _ensure_attendance(client, headers)
    return headers
