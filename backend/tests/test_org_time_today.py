"""Phase 6A Task 3: business 'today' is the org-local date, not UTC.

Time is frozen at 20:00Z, when an Asia/Kolkata org is already on the NEXT
calendar day. Real dev DB; the org.timezone rule is restored afterwards."""
from datetime import datetime, timezone

import pytest

from app.db.session import SessionLocal
from app.models.system import SystemSetting
from app.services import org_time

from test_asset_requests import P, api, submit, world  # noqa: F401

FROZEN = datetime(2031, 3, 5, 20, 0, tzinfo=timezone.utc)   # IST: 2031-03-06 01:30


@pytest.fixture
async def ist_frozen(monkeypatch):
    async with SessionLocal() as db:
        row = await db.get(SystemSetting, "org.timezone")
        saved = (row.value, row.description) if row else None
        if row:
            row.value = "Asia/Kolkata"
        else:
            db.add(SystemSetting(key="org.timezone", value="Asia/Kolkata",
                                 description="t"))
        await db.commit()

    class _Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return FROZEN.astimezone(tz) if tz else FROZEN.replace(tzinfo=None)

    monkeypatch.setattr(org_time, "datetime", _Frozen)
    yield
    monkeypatch.undo()
    async with SessionLocal() as db:
        row = await db.get(SystemSetting, "org.timezone")
        if saved is None:
            if row:
                await db.delete(row)
        elif row:
            row.value = saved[0]
        else:
            db.add(SystemSetting(key="org.timezone", value=saved[0],
                                 description=saved[1]))
        await db.commit()


async def test_local_today_is_next_day_at_2000z(ist_frozen):
    async with SessionLocal() as db:
        assert str(await org_time.local_today(db)) == "2031-03-06"


async def test_endpoint_default_date_uses_org_day(ist_frozen, api, world):
    # 2031-03-05 is "yesterday" for the IST org at 20:00Z -> rejected.
    r = await submit(api, world, needed_by="2031-03-05")
    assert r.status_code == 422, r.text
    r = await submit(api, world, needed_by="2031-03-06")
    assert r.status_code == 200, r.text


async def test_scheduler_job_uses_org_yesterday(ist_frozen):
    from app.services.scheduler import REGISTRY
    async with SessionLocal() as db:
        res = await REGISTRY["overtime_recompute_yesterday"].fn(db)
    # org today = 03-06 -> yesterday = 03-05 (UTC would have said 03-04)
    assert res["work_date"] == "2031-03-05"


def test_org_today_helper_is_tomorrows_utc_date_at_2000z():
    from _tz import TEST_TZ, org_today
    from app.services.org_time import local_today_for, tz_from_name
    tz = tz_from_name(TEST_TZ)
    assert local_today_for(tz, now=FROZEN).isoformat() == "2031-03-06"
    assert FROZEN.date().isoformat() == "2031-03-05"
    # org_today() is exactly local_today_for(TEST_TZ) of the real clock
    assert org_today() == local_today_for(tz)
