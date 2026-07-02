"""Org-level attendance time rules (Section Q).

Settings live in the SystemSetting KV table. Shift-assigned employees
are evaluated against their shift's own start/end + grace; employees
with NO shift fall back to the org defaults below via a virtual
"default shift" object that satisfies the shift_resolver's ShiftLike
protocol.
"""
from dataclasses import dataclass
from datetime import time
from typing import Dict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.system import SystemSetting

# key -> (default value, description)
TIME_RULE_DEFAULTS: Dict[str, tuple[str, str]] = {
    "attendance.enable_late_flags": (
        "1", "Master toggle for late / early-exit flagging (1/0)"
    ),
    "attendance.default_start_time": (
        "09:30", "Workday start for employees with no shift (HH:MM)"
    ),
    "attendance.default_end_time": (
        "18:00", "Workday end for employees with no shift (HH:MM)"
    ),
    "attendance.late_grace_minutes": (
        "10", "Grace minutes after start before a punch-in counts as late"
    ),
    "attendance.early_exit_grace_minutes": (
        "10", "Grace minutes before end after which a punch-out is early"
    ),
}


async def get_time_rules(db: AsyncSession) -> Dict[str, str]:
    """Return the effective time rules (stored values over defaults)."""
    rows = (await db.execute(
        select(SystemSetting).where(
            SystemSetting.key.in_(TIME_RULE_DEFAULTS.keys())
        )
    )).scalars().all()
    stored = {r.key: r.value for r in rows}
    return {
        k: stored.get(k, default)
        for k, (default, _desc) in TIME_RULE_DEFAULTS.items()
    }


async def set_time_rules(
    db: AsyncSession, updates: Dict[str, str]
) -> Dict[str, str]:
    """Upsert the given time-rule keys. Unknown keys are ignored."""
    for key, value in updates.items():
        if key not in TIME_RULE_DEFAULTS:
            continue
        existing = await db.get(SystemSetting, key)
        if existing:
            existing.value = value
        else:
            db.add(SystemSetting(
                key=key,
                value=value,
                description=TIME_RULE_DEFAULTS[key][1],
            ))
    await db.commit()
    return await get_time_rules(db)


@dataclass(frozen=True)
class DefaultShift:
    """Virtual shift built from org defaults — satisfies ShiftLike."""
    start_time: time
    end_time: time
    is_overnight: bool
    break_minutes: int
    grace_in_minutes: int
    grace_out_minutes: int


def _parse_hhmm(value: str, fallback: time) -> time:
    try:
        h, m = value.strip().split(":")
        return time(int(h), int(m))
    except Exception:
        return fallback


def build_default_shift(rules: Dict[str, str]) -> DefaultShift:
    """Build the fallback ShiftLike from org-level settings."""
    start = _parse_hhmm(
        rules["attendance.default_start_time"], time(9, 30)
    )
    end = _parse_hhmm(rules["attendance.default_end_time"], time(18, 0))

    def _int(key: str, fallback: int) -> int:
        try:
            return int(rules[key])
        except Exception:
            return fallback

    return DefaultShift(
        start_time=start,
        end_time=end,
        is_overnight=end <= start,
        break_minutes=60,
        grace_in_minutes=_int("attendance.late_grace_minutes", 10),
        grace_out_minutes=_int("attendance.early_exit_grace_minutes", 10),
    )


def flags_enabled(rules: Dict[str, str]) -> bool:
    return rules.get("attendance.enable_late_flags", "1").strip() in (
        "1", "true", "yes", "on"
    )
