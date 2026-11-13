"""Selfie retention: purge unattached uploads and expired punch selfies."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import or_, select, update

from app.core.config import settings
from app.models.attendance import Attendance, AttendanceSelfie
from app.services.time_rules import get_time_rules

UNATTACHED_TTL = timedelta(hours=48)


def _rm(name: str) -> None:
    if name and "/" not in name and not name.startswith("."):
        (Path(settings.ATTENDANCE_SELFIE_DIR) / name).unlink(missing_ok=True)


async def purge_selfies(db, now: datetime | None = None) -> dict:
    """Delete (1) selfies uploaded but never attached to a punch for 48h and
    (2) when attendance.selfie_retention_days > 0, the files of punches older
    than that (the selfie_url columns are nulled; the punch is kept)."""
    now = now or datetime.now(timezone.utc)
    unattached = 0
    for row in (await db.execute(select(AttendanceSelfie).where(
            AttendanceSelfie.used_at.is_(None),
            AttendanceSelfie.created_at < now - UNATTACHED_TTL))).scalars().all():
        _rm(row.filename)
        await db.delete(row)
        unattached += 1

    expired = 0
    rules = await get_time_rules(db)
    try:
        days = int(str(rules.get("attendance.selfie_retention_days", "90")).strip())
    except ValueError:
        days = 90
    if days > 0:
        cutoff = now - timedelta(days=days)
        rows = (await db.execute(select(Attendance).where(
            Attendance.captured_at < cutoff,
            or_(Attendance.selfie_url.is_not(None),
                Attendance.punch_out_selfie_url.is_not(None))))).scalars().all()
        names = set()
        for a in rows:
            for n in (a.selfie_url, a.punch_out_selfie_url):
                if n:
                    names.add(n)
                    _rm(n)
                    expired += 1
            a.selfie_url = None
            a.punch_out_selfie_url = None
        if names:
            for r in (await db.execute(select(AttendanceSelfie).where(
                    AttendanceSelfie.filename.in_(names)))).scalars().all():
                await db.delete(r)
    await db.commit()
    return {"unattached_deleted": unattached, "expired_deleted": expired}
