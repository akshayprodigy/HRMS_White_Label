"""Endpoint-side helpers that send manager edits through the DOP service.

Every writer runs as one retried transaction (see the contract in
services/dop/assignments.py): commit first, take the reporting lock, write,
commit. Bodies capture plain values only: a rollback expires every ORM object
the request loaded.
"""
from types import SimpleNamespace

from sqlalchemy import select

from app.api.v1.endpoints.roster_common import (
    plain_actor, reload_user, retry_on_lock,
)
from app.models.user import User
from app.services.dop import assignments as A


async def change_manager(db, *, actor_id, user_id, manager_id) -> None:
    """Own transaction: set (or clear, manager_id=None) one user's reporting
    manager. HTTP 422/409 from the service reject the caller's request."""
    async def body():
        await db.commit()
        await A.lock_reporting(db)
        await A.set_reporting_manager(
            db, actor_id=actor_id, user_id=user_id, manager_id=manager_id)
    await retry_on_lock(db, body, commit=True)


async def reload_actor(db, actor_id) -> None:
    """Re-load the request's user (+roles) after a commit/rollback. Takes the
    id captured BEFORE the change: an expired user cannot be read."""
    await reload_user(db, plain_actor(SimpleNamespace(id=actor_id)))()


async def current_manager(db, user_id):
    return (await db.execute(select(User.manager_id).where(
        User.id == user_id))).scalar_one_or_none()
