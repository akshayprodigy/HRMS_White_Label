"""Org timezone: the ONLY place shift wall-clock times and "today" are
interpreted. Storage stays UTC. org.timezone=UTC reproduces pre-6A behaviour.

Note: org_tz() reads the time rules (one query) on every call; batch callers
should resolve it once per request/job, not per row."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone, tzinfo
from typing import Optional
from zoneinfo import ZoneInfo, available_timezones

DEFAULT_TZ = "Asia/Kolkata"
RULE_KEY = "org.timezone"


def tz_from_name(name: Optional[str]) -> tzinfo:
    name = (name or "").strip() or DEFAULT_TZ
    if name.upper() == "UTC":
        return timezone.utc
    if name not in available_timezones():
        return ZoneInfo(DEFAULT_TZ)
    return ZoneInfo(name)


def tz_name(tz: tzinfo) -> str:
    return "UTC" if tz is timezone.utc else getattr(tz, "key", DEFAULT_TZ)


async def org_tz(db, user=None) -> tzinfo:
    """`user` reserved for per-location timezones (later Platform slice)."""
    from app.services.time_rules import get_time_rules
    rules = await get_time_rules(db)
    return tz_from_name(rules.get(RULE_KEY, DEFAULT_TZ))


def _aware(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def local_date(dt: datetime, tz: tzinfo) -> date:
    return _aware(dt).astimezone(tz).date()


def local_now(tz: tzinfo, now: Optional[datetime] = None) -> datetime:
    return _aware(now or datetime.now(timezone.utc)).astimezone(tz)


def local_today_for(tz: tzinfo, now: Optional[datetime] = None) -> date:
    return local_now(tz, now).date()


async def local_today(db) -> date:
    return local_today_for(await org_tz(db))


def _to_utc(d: date, t: time, tz: tzinfo) -> datetime:
    local = datetime.combine(d, t).replace(tzinfo=tz, fold=0)
    # Nonexistent local time (DST gap): round-trip check, shift forward.
    back = local.astimezone(timezone.utc).astimezone(tz)
    if back.replace(tzinfo=None) != local.replace(tzinfo=None):
        local = (local + timedelta(hours=1)).replace(minute=0, second=0)
    return local.astimezone(timezone.utc)


def shift_window(
    work_date: date, start: time, end: time, tz: tzinfo
) -> tuple[datetime, datetime]:
    s = _to_utc(work_date, start, tz)
    end_date = work_date + timedelta(days=1) if end <= start else work_date
    return s, _to_utc(end_date, end, tz)


def utc_offset_minutes(tz: tzinfo, now: Optional[datetime] = None) -> int:
    off = local_now(tz, now).utcoffset() or timedelta(0)
    return int(off.total_seconds() // 60)
