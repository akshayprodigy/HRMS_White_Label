"""DB-free: retry_on_lock retries LockRetry like any lock conflict."""
import pytest

from app.api.v1.endpoints.roster_common import retry_on_lock
from app.services.attendance_lock import LockRetry


class FakeDB:
    def __init__(self):
        self.rollbacks = 0

    async def rollback(self):
        self.rollbacks += 1


async def test_lockretry_is_retried_then_succeeds():
    db, calls = FakeDB(), []

    async def fn():
        calls.append(1)
        if len(calls) < 3:
            raise LockRetry()
        return "ok"

    assert await retry_on_lock(db, fn) == "ok"
    assert len(calls) == 3 and db.rollbacks == 2


async def test_lockretry_exhausted_surfaces_409():
    db, calls = FakeDB(), []

    async def fn():
        calls.append(1)
        raise LockRetry()

    with pytest.raises(LockRetry) as ei:
        await retry_on_lock(db, fn, tries=3)
    assert ei.value.status_code == 409 and len(calls) == 3
