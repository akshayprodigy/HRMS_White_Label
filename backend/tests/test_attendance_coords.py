"""Coordinate range validation on punches (mark, punch-out, offline-sync)."""
import uuid
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.api import deps
from app.core.config import settings
from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.main import create_app
from app.models.attendance import Attendance
from app.models.user import User

ATT = f"{settings.API_V1_STR}/attendance"
PW = "test@12345"


@pytest.fixture
async def ctx():
    sfx = uuid.uuid4().hex[:8]
    email = f"ac_{sfx}@t.com"
    app = create_app()
    app.dependency_overrides[deps.verify_attendance] = lambda: None
    try:
        async with SessionLocal() as db:
            db.add(User(email=email, full_name="AC", is_active=True,
                        hashed_password=get_password_hash(PW)))
            await db.commit()
        async with AsyncClient(transport=ASGITransport(app=app),
                               base_url="http://test") as c:
            r = await c.post(f"{settings.API_V1_STR}/auth/login",
                             data={"username": email, "password": PW})
            assert r.status_code == 200, r.text
            yield c, {"Authorization": f"Bearer {r.json()['access_token']}"}
    finally:
        async with SessionLocal() as db:
            uid = (await db.execute(select(User.id).where(
                User.email == email))).scalar_one_or_none()
            if uid:
                await db.execute(delete(Attendance).where(
                    Attendance.user_id == uid))
                await db.execute(delete(User).where(User.id == uid))
            await db.commit()


BAD = [(999, 999), (91, 0), (-91, 0), (0, 181), (0, -181)]


@pytest.mark.parametrize("lat,lng", BAD)
async def test_mark_rejects_out_of_range(ctx, lat, lng):
    c, h = ctx
    r = await c.post(f"{ATT}/mark", headers=h, json={
        "mode": "office", "latitude": lat, "longitude": lng})
    assert r.status_code == 422, r.text


async def test_mark_rejects_nan_inf(ctx):
    c, h = ctx
    for raw in ('{"mode":"office","latitude":NaN,"longitude":1}',
                '{"mode":"office","latitude":1,"longitude":Infinity}'):
        r = await c.post(f"{ATT}/mark", headers={
            **h, "Content-Type": "application/json"}, content=raw)
        assert r.status_code == 422, r.text


async def test_punch_out_rejects_out_of_range(ctx):
    c, h = ctx
    r = await c.post(f"{ATT}/punch-out", headers=h, json={
        "latitude": 999, "longitude": 999})
    assert r.status_code == 422, r.text


async def test_offline_sync_rejects_items_individually(ctx):
    c, h = ctx
    now = datetime.now(timezone.utc).isoformat()
    items = [{"client_uuid": f"bad-{i}-{uuid.uuid4().hex}", "kind": "in",
              "captured_at": now, "latitude": lat, "longitude": lng}
             for i, (lat, lng) in enumerate(BAD)]
    r = await c.post(f"{ATT}/offline-sync", headers=h,
                     json={"punches": items})
    assert r.status_code == 200, r.text
    res = r.json()["results"]
    assert [x["client_uuid"] for x in res] == [i["client_uuid"] for i in items]
    assert all(x["status"] == "rejected"
               and x["reason"] == "invalid_coordinates" for x in res)
