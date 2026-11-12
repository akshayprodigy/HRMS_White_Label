"""Org-level attendance time rules (Section Q).

Settings live in the SystemSetting KV table. Shift-assigned employees
are evaluated against their shift's own start/end + grace; employees
with NO shift fall back to the org defaults below via a virtual
"default shift" object that satisfies the shift_resolver's ShiftLike
protocol.
"""
import logging
from dataclasses import dataclass
from datetime import time
from typing import Dict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.system import SystemSetting

logger = logging.getLogger(__name__)

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
    "attendance.absence_lop_enabled": (
        "0",
        "Count unexplained absences on scheduled working days as LOP in "
        "payroll (1/0)",
    ),
    "attendance.weekoff_comp_off_enabled": (
        "0",
        "Grant a comp-off accrual (manager -> HR approval) for working a "
        "roster or shift-assignment week-off; org default weekly offs for "
        "employees with no shift do not qualify (1/0)",
    ),
    "attendance.default_weekly_offs": (
        "6",
        "Comma-separated weekdays off for employees with no shift "
        "(Mon=0..Sun=6)",
    ),
    "schedule.min_rest_hours": (
        "11", "Minimum rest between consecutive shifts in hours (0 = off)"
    ),
    "schedule.max_consecutive_days": (
        "6", "Maximum consecutive working days (0 = off)"
    ),
    "schedule.max_consecutive_nights": (
        "4", "Maximum consecutive overnight shifts (0 = off)"
    ),
    "schedule.max_weekly_hours": (
        "48", "Maximum scheduled hours per Mon-Sun week (0 = off)"
    ),
    "schedule.no_show_minutes": (
        "30",
        "Minutes after shift start with no punch-in before an employee is "
        "flagged a no-show and alerts are sent (0 = off)",
    ),
    "schedule.lock_days": (
        "0",
        "Published schedule is locked this many days ahead (0 = off, 0-30): "
        "only roster admins / emergency-override delegates may change it, "
        "with a reason, and the employee must acknowledge",
    ),
    "schedule.callback_compensation": (
        "none",
        "Compensation when an emergency change calls an employee in on a "
        "day off: none | comp_off | allowance",
    ),
    "schedule.callback_allowance_amount": (
        "0", "Call-back allowance paid per call-back day (>= 0)"
    ),
    "leave.emergency_backdate_days": (
        "3",
        "Emergency leave may start up to this many days in the past (0-31)",
    ),
    "leave.emergency_proof_days": (
        "3",
        "Days after an emergency leave ends to submit a medical certificate "
        "the leave type requires (else it converts to LOP). 0 = the "
        "certificate must be attached upfront (0-60)",
    ),
}

# key -> inclusive upper bound
SCHEDULE_INT_CAPS: Dict[str, int] = {
    "schedule.min_rest_hours": 24,
    "schedule.max_consecutive_days": 31,
    "schedule.max_consecutive_nights": 31,
    "schedule.max_weekly_hours": 168,
    "schedule.no_show_minutes": 240,
}
SCHEDULE_INT_KEYS = tuple(SCHEDULE_INT_CAPS)
LOCK_INT_CAPS: Dict[str, int] = {"schedule.lock_days": 30}
CALLBACK_MODES = ("none", "comp_off", "allowance")
LEAVE_INT_CAPS: Dict[str, int] = {
    "leave.emergency_backdate_days": 31,
    "leave.emergency_proof_days": 60,
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
    """Upsert the given time-rule keys. Unknown keys are ignored.
    Raises ValueError (before any write) on an invalid value."""
    offs = updates.get("attendance.default_weekly_offs")
    if offs is not None:
        toks = [t.strip() for t in str(offs).split(",")]
        if not toks or not all(t.isdigit() and 0 <= int(t) <= 6 for t in toks):
            raise ValueError(
                "attendance.default_weekly_offs must be comma-separated "
                "weekday numbers 0-6 (Mon=0..Sun=6), e.g. '6' or '5,6'"
            )
    updates = dict(updates)
    wk = updates.get("attendance.weekoff_comp_off_enabled")
    if wk is not None:
        if str(wk).strip() not in ("0", "1"):
            raise ValueError(
                "attendance.weekoff_comp_off_enabled must be 0 or 1"
            )
        updates["attendance.weekoff_comp_off_enabled"] = str(wk).strip()
    for key, cap in {
        **SCHEDULE_INT_CAPS, **LEAVE_INT_CAPS, **LOCK_INT_CAPS
    }.items():
        v = updates.get(key)
        if v is not None:
            sv = str(v).strip()
            if not (sv.isascii() and sv.isdigit()) or int(sv) > cap:
                raise ValueError(
                    f"{key} must be a whole number between 0 and {cap}"
                )
            updates[key] = sv  # store the stripped value
    cm = updates.get("schedule.callback_compensation")
    if cm is not None:
        cm = str(cm).strip()
        if cm not in CALLBACK_MODES:
            raise ValueError(
                "schedule.callback_compensation must be one of: "
                + ", ".join(CALLBACK_MODES))
        updates["schedule.callback_compensation"] = cm
    amt = updates.get("schedule.callback_allowance_amount")
    if amt is not None:
        try:
            f = float(str(amt).strip())
            if not (f == f and 0 <= f < 1e9):  # NaN / negative / absurd
                raise ValueError
        except ValueError:
            raise ValueError(
                "schedule.callback_allowance_amount must be a number >= 0")
        updates["schedule.callback_allowance_amount"] = str(f)
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


async def get_schedule_rules(db: AsyncSession) -> Dict[str, int]:
    """Work rules as ints keyed without the 'schedule.' prefix. A corrupt
    stored value falls back to its default (logged)."""
    raw = await get_time_rules(db)
    out: Dict[str, int] = {}
    for key in SCHEDULE_INT_KEYS:
        short = key.split(".", 1)[1]
        try:
            val = int(str(raw[key]).strip())
            if val < 0:
                raise ValueError("negative")
            out[short] = val
        except (TypeError, ValueError):
            logger.warning(
                "Invalid stored value %r for %s; using default",
                raw.get(key), key,
            )
            out[short] = int(TIME_RULE_DEFAULTS[key][0])
    return out


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


async def get_emergency_leave_rules(db: AsyncSession) -> Dict[str, int]:
    """{'backdate_days', 'proof_days'} as ints; corrupt values fall back to
    the defaults (logged)."""
    raw = await get_time_rules(db)
    out: Dict[str, int] = {}
    for key, cap in LEAVE_INT_CAPS.items():
        short = key.split(".", 1)[1].replace("emergency_", "")
        try:
            val = int(str(raw[key]).strip())
            if not 0 <= val <= cap:
                raise ValueError("out of range")
            out[short] = val
        except (TypeError, ValueError):
            logger.warning("Invalid stored value %r for %s; using default",
                           raw.get(key), key)
            out[short] = int(TIME_RULE_DEFAULTS[key][0])
    return out


async def get_lock_rules(db: AsyncSession) -> Dict[str, object]:
    """{'lock_days': int, 'callback_compensation': str,
    'callback_allowance_amount': float}; corrupt stored values fall back to
    the defaults (logged)."""
    raw = await get_time_rules(db)
    try:
        lock_days = int(str(raw["schedule.lock_days"]).strip())
        if not 0 <= lock_days <= 30:
            raise ValueError
    except (TypeError, ValueError):
        logger.warning("Invalid stored schedule.lock_days; using 0")
        lock_days = 0
    mode = str(raw["schedule.callback_compensation"]).strip()
    if mode not in CALLBACK_MODES:
        logger.warning("Invalid stored schedule.callback_compensation")
        mode = "none"
    try:
        amount = float(str(raw["schedule.callback_allowance_amount"]).strip())
        if not (amount == amount and amount >= 0):
            raise ValueError
    except (TypeError, ValueError):
        logger.warning("Invalid stored schedule.callback_allowance_amount")
        amount = 0.0
    return {"lock_days": lock_days, "callback_compensation": mode,
            "callback_allowance_amount": amount}
