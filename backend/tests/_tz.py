"""Shared fixture: pin org.timezone=UTC for tests written against the pre-6A
"shift times are UTC" behaviour (Phase 6A Task 2). Restores the stored row.

Usage in a test module:  from _tz import org_tz_utc  # noqa: F401
(autouse, so no per-test change is needed)."""
import pytest

from app.db.session import SessionLocal
from app.models.system import SystemSetting

KEY = "org.timezone"
TEST_TZ = "Asia/Kolkata"   # the org timezone the suite runs under (conftest.py)


def org_today():
    """The org's business 'today' (TEST_TZ) -- use instead of date.today() /
    datetime.now(UTC).date() for dates that mean the org's calendar day."""
    from app.services.org_time import local_today_for, tz_from_name
    return local_today_for(tz_from_name(TEST_TZ))


@pytest.fixture(autouse=True)
async def org_tz_utc():
    async with SessionLocal() as db:
        row = await db.get(SystemSetting, KEY)
        saved = (row.value, row.description) if row else None
        if row:
            row.value = "UTC"
        else:
            db.add(SystemSetting(key=KEY, value="UTC", description="t"))
        await db.commit()
    yield
    async with SessionLocal() as db:
        row = await db.get(SystemSetting, KEY)
        if saved is None:
            if row:
                await db.delete(row)
        elif row:
            row.value = saved[0]
        else:
            db.add(SystemSetting(key=KEY, value=saved[0], description=saved[1]))
        await db.commit()
