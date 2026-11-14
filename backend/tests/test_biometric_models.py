"""Biometric models (Roadmap v2 Phase 4, Task 1). DB-backed; cleans up."""
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.models.biometric import (
    BiometricDevice, BiometricPunch, BiometricPunchState, BiometricUserMap,
)
from app.models.user import User


async def test_user_map_and_punch_uniqueness():
    sfx = uuid.uuid4().hex[:8]
    user_id = dev_id = None
    pin = f"9{sfx[:6]}"
    keys = [f"dk_{sfx}_1", f"dk_{sfx}_1"]
    try:
        async with SessionLocal() as db:
            u = User(email=f"bio_{sfx}@t.com", full_name="Bio",
                     hashed_password=get_password_hash("x"), is_active=True)
            d = BiometricDevice(serial=f"SN{sfx}", utc_offset_minutes=330)
            db.add_all([u, d])
            await db.commit()
            user_id, dev_id = u.id, d.id

            # global + device-specific map for same pin coexist
            db.add_all([
                BiometricUserMap(device_id=None, pin=pin, user_id=user_id),
                BiometricUserMap(device_id=dev_id, pin=pin, user_id=user_id),
            ])
            await db.commit()
            n = (await db.execute(select(BiometricUserMap).where(
                BiometricUserMap.pin == pin))).scalars().all()
            assert len(n) == 2

            # second global row for the same pin is rejected
            db.add(BiometricUserMap(device_id=None, pin=pin, user_id=user_id))
            with pytest.raises(IntegrityError):
                await db.commit()
            await db.rollback()

            # duplicate dedupe_key rejected
            now = datetime.now(timezone.utc)
            db.add(BiometricPunch(
                dedupe_key=keys[0], source="adms", device_id=dev_id, pin=pin,
                punch_time=now, state=BiometricPunchState.UNMAPPED))
            await db.commit()
            db.add(BiometricPunch(
                dedupe_key=keys[1], source="adms", device_id=dev_id, pin=pin,
                punch_time=now, state=BiometricPunchState.UNMAPPED))
            with pytest.raises(IntegrityError):
                await db.commit()
            await db.rollback()
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(BiometricPunch).where(
                BiometricPunch.dedupe_key.in_(keys)))
            await db.execute(delete(BiometricUserMap).where(
                BiometricUserMap.pin == pin))
            if dev_id:
                await db.execute(delete(BiometricDevice).where(
                    BiometricDevice.id == dev_id))
            if user_id:
                await db.execute(delete(User).where(User.id == user_id))
            await db.commit()
