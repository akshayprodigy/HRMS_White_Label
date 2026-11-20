"""Session-wide test setup: run the suite under one org timezone (TEST_TZ) so
business-date helpers are deterministic. Modules that need UTC import the
function-scoped `org_tz_utc` pin from _tz.py, which overrides this per test
and restores the value set here."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _tz import KEY, TEST_TZ  # noqa: E402

_saved = {}


async def _with_session(fn):
    # Own NullPool engine: no connections leak into the per-test event loops.
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.pool import NullPool
    from app.core.config import settings
    eng = create_async_engine(str(settings.SQLALCHEMY_DATABASE_URI),
                              poolclass=NullPool)
    try:
        async with AsyncSession(eng) as db:
            out = await fn(db)
            await db.commit()
            return out
    finally:
        await eng.dispose()


def pytest_sessionstart(session):
    from app.models.system import SystemSetting

    async def go(db):
        row = await db.get(SystemSetting, KEY)
        _saved["row"] = (row.value, row.description) if row else None
        if row:
            row.value = TEST_TZ
        else:
            db.add(SystemSetting(key=KEY, value=TEST_TZ, description="test"))
    asyncio.run(_with_session(go))


def pytest_sessionfinish(session, exitstatus):
    if "row" not in _saved:
        return
    from app.models.system import SystemSetting

    async def go(db):
        row = await db.get(SystemSetting, KEY)
        saved = _saved["row"]
        if saved is None:
            if row:
                await db.delete(row)
        elif row:
            row.value = saved[0]
        else:
            db.add(SystemSetting(key=KEY, value=saved[0], description=saved[1]))
    asyncio.run(_with_session(go))
