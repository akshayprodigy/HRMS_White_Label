"""Org timezone service (Roadmap v2 Phase 6A, Task 1)."""
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.db.session import SessionLocal
from app.main import create_app
from app.models.system import SystemSetting
from app.services.org_time import (
    local_date, local_today_for, org_tz, shift_window,
)
from app.services.time_rules import set_time_rules

IST = ZoneInfo("Asia/Kolkata")
LON = ZoneInfo("Europe/London")
KEY = "org.timezone"


def test_day_shift_ist():
    s, e = shift_window(date(2026, 11, 20), time(9, 0), time(18, 0), IST)
    assert s == datetime(2026, 11, 20, 3, 30, tzinfo=timezone.utc)
    assert e == datetime(2026, 11, 20, 12, 30, tzinfo=timezone.utc)


def test_cross_midnight_ist():
    s, e = shift_window(date(2026, 11, 20), time(22, 0), time(6, 0), IST)
    assert s == datetime(2026, 11, 20, 16, 30, tzinfo=timezone.utc)
    assert e == datetime(2026, 11, 21, 0, 30, tzinfo=timezone.utc)


def test_utc_parity():
    s, e = shift_window(date(2026, 11, 20), time(9, 0), time(18, 0), timezone.utc)
    assert (s, e) == (datetime(2026, 11, 20, 9, tzinfo=timezone.utc),
                      datetime(2026, 11, 20, 18, tzinfo=timezone.utc))


def test_dst_gap_moves_forward():
    # 2026-03-29 01:30 does not exist in London (clocks jump 01:00 -> 02:00)
    s, _ = shift_window(date(2026, 3, 29), time(1, 30), time(9, 0), LON)
    assert s == datetime(2026, 3, 29, 1, 0, tzinfo=timezone.utc)  # == 02:00 BST


def test_local_date_boundary():
    assert local_date(datetime(2026, 11, 20, 19, 0, tzinfo=timezone.utc), IST) == date(2026, 11, 21)
    assert local_date(datetime(2026, 11, 20, 19, 0), IST) == date(2026, 11, 21)


def test_local_today_for_now():
    now = datetime(2026, 11, 20, 20, 0, tzinfo=timezone.utc)
    assert local_today_for(IST, now=now) == date(2026, 11, 21)


@pytest.fixture
async def tz_rule():
    """Set org.timezone for a test; restore the stored row afterwards."""
    async with SessionLocal() as db:
        row = await db.get(SystemSetting, KEY)
        saved = row.value if row else None

    async def setter(value):
        async with SessionLocal() as db:
            await set_time_rules(db, {KEY: value})
    yield setter
    async with SessionLocal() as db:
        row = await db.get(SystemSetting, KEY)
        if saved is None:
            if row:
                await db.delete(row)
        elif row:
            row.value = saved
        await db.commit()


async def test_org_tz_default_and_utc(tz_rule):
    async with SessionLocal() as db:
        row = await db.get(SystemSetting, KEY)
        if row is None:
            assert await org_tz(db) == IST
    await tz_rule("Asia/Kolkata")
    async with SessionLocal() as db:
        assert await org_tz(db) == IST
    await tz_rule("UTC")
    async with SessionLocal() as db:
        assert await org_tz(db) is timezone.utc


async def test_invalid_timezone_rejected(tz_rule):
    async with SessionLocal() as db:
        with pytest.raises(ValueError):
            await set_time_rules(db, {KEY: "Mars/Base"})


async def test_meta_org_time_public():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as c:
        r = await c.get(f"{settings.API_V1_STR}/meta/org-time")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"timezone", "utc_offset_minutes", "today"}
    assert isinstance(body["utc_offset_minutes"], int)
    date.fromisoformat(body["today"])
