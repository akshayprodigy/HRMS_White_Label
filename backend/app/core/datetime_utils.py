from datetime import datetime, timezone
from typing import Optional


def as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """MariaDB round-trips DATETIME columns as naive; treat them as UTC.
    Aware values are converted to UTC (e.g. 09:30+05:30 -> 04:00Z)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
