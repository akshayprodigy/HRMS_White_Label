"""Shared fixture: pin org.timezone=UTC for tests written against the pre-6A
"shift times are UTC" behaviour (Phase 6A Task 2). Restores the stored row.

Usage in a test module:  from _tz import org_tz_utc  # noqa: F401
(autouse, so no per-test change is needed)."""
import pytest

from app.db.session import SessionLocal
from app.models.system import SystemSetting

KEY = "org.timezone"


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
