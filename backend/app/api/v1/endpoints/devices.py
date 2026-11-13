"""Mobile push device tokens (Roadmap v2 Phase 3, Task 1).

Mounted WITHOUT the attendance gate (the app registers its token at login,
before the employee can punch in). Auth is still required; every route only
touches the caller's own tokens.
"""
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from app.api import deps
from app.api.v1.endpoints.roster_common import lock_row, retry_on_lock
from app.models.device import DeviceToken
from app.models.user import User

router = APIRouter()


class DeviceIn(BaseModel):
    token: str = Field(min_length=8, max_length=255)
    platform: Literal["ios", "android"]
    app_version: Optional[str] = Field(default=None, max_length=32)
    tenant: Optional[str] = Field(default=None, max_length=64)

    @field_validator("token")
    @classmethod
    def _strip(cls, v):
        v = v.strip()
        if len(v) < 8:
            raise ValueError("token too short")
        return v


def _row(d: DeviceToken) -> dict:
    def iso(x):
        if x is not None and x.tzinfo is None:
            x = x.replace(tzinfo=timezone.utc)
        return x.isoformat() if x else None
    return {"id": d.id, "platform": d.platform, "token": d.token,
            "app_version": d.app_version, "tenant": d.tenant,
            "created_at": iso(d.created_at), "last_seen_at": iso(d.last_seen_at)}


@router.post("")
async def register_device(body: DeviceIn, db: deps.DBDep,
                          me: deps.CurrentUser):
    """Register / refresh a token. Upsert by token: a token that was bound to
    another user (shared device, re-login) moves to the caller and is
    un-revoked."""
    me_id = me.id

    async def go():
        now = datetime.now(timezone.utc)
        d = await lock_row(
            db, select(DeviceToken).where(DeviceToken.token == body.token))
        if d is None:
            d = DeviceToken(token=body.token, user_id=me_id,
                            platform=body.platform, created_at=now)
            db.add(d)
        d.user_id = me_id
        d.platform = body.platform
        d.app_version = body.app_version
        d.tenant = body.tenant
        d.last_seen_at = now
        d.revoked_at = None
        await db.flush()
        return _row(d)
    return await retry_on_lock(db, go, commit=True)


@router.get("/my")
async def my_devices(db: deps.DBDep, me: deps.CurrentUser):
    rows = (await db.execute(
        select(DeviceToken).where(DeviceToken.user_id == me.id,
                                  DeviceToken.revoked_at.is_(None))
        .order_by(DeviceToken.id))).scalars().all()
    return [_row(d) for d in rows]


@router.delete("/{token}")
async def revoke_device(token: str, db: deps.DBDep, me: deps.CurrentUser):
    me_id = me.id

    async def go():
        d = await lock_row(
            db, select(DeviceToken).where(DeviceToken.token == token,
                                          DeviceToken.user_id == me_id))
        if d is None:
            raise HTTPException(404, "Device not found")
        if d.revoked_at is None:
            d.revoked_at = datetime.now(timezone.utc)
        return {"revoked": True}
    return await retry_on_lock(db, go, commit=True)
