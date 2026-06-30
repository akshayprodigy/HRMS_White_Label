"""Overtime + Night-shift allowance computation.

Pure helpers — no DB, no I/O — so the rules can be unit-tested without
fixtures and reused from both the recompute endpoint and the payroll
draft generator.

Hourly-rate basis
=================
A single documented constant.  We use the WB-payroll convention already
in use by the salary engine:

    hourly_rate = BASIC_SALARY / STANDARD_DAYS_PER_MONTH / standard_hours_per_day

with:
    STANDARD_DAYS_PER_MONTH = 26   (industry-standard working-days basis)
    standard_hours_per_day  = shift.full_day_hours when a shift is present,
                              else FALLBACK_FULL_DAY_HOURS = 8.0

Pick this basis once here, never recompute it inline.  Anyone touching
OT/night-allowance maths should import `compute_hourly_rate`.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from enum import Enum
from typing import Optional, Protocol

# ----- single documented constants ----------------------------------

STANDARD_DAYS_PER_MONTH = 26
FALLBACK_FULL_DAY_HOURS = 8.0

#: Human-readable documentation of the hourly-rate basis. Surfaced on the
#: rules-admin page so policy decisions are auditable.
HOURLY_RATE_BASIS_DOC = (
    "BASIC / 26 / full_day_hours "
    "(shift's full_day_hours, fallback 8h when no shift)"
)


# ----- string-constants mirrored from the model ---------------------


class OvertimeBasis(str, Enum):
    BEYOND_SHIFT_HOURS = "beyond_shift_hours"
    BEYOND_THRESHOLD = "beyond_threshold"


class DayType(str, Enum):
    WEEKDAY = "weekday"
    WEEKLY_OFF = "weekly_off"
    HOLIDAY = "holiday"


class NightPayoutModel(str, Enum):
    FLAT = "flat"
    HOURLY = "hourly"


# ----- structural protocols (lets tests pass plain dataclasses) ------


class ShiftLike(Protocol):
    start_time: time
    end_time: time
    is_overnight: bool
    full_day_hours: float
    weekly_offs: list  # list[int] in 0..6 (Mon=0..Sun=6)


class OTRuleLike(Protocol):
    ot_basis: str
    daily_threshold_hours: Optional[float]
    ot_rate_multiplier: float
    weekly_off_multiplier: float
    holiday_multiplier: float
    min_ot_minutes: int
    daily_ot_cap_minutes: int
    monthly_ot_cap_minutes: Optional[int]
    rounding_minutes: int


class NightRuleLike(Protocol):
    payout_model: str
    flat_amount: float
    hourly_rate: float
    night_window_start: time
    night_window_end: time
    min_night_minutes: int


# ----- DTOs ---------------------------------------------------------


@dataclass
class OvertimeComputation:
    ot_minutes: int
    ot_amount: float
    hourly_rate_used: float
    multiplier_used: float
    day_type: DayType


@dataclass
class NightAllowanceComputation:
    night_minutes: int
    amount: float
    payout_model_used: NightPayoutModel


# ----- hourly-rate (single point of truth) --------------------------


def compute_hourly_rate(
    basic_salary: float,
    shift: Optional[ShiftLike],
) -> float:
    """Return the documented hourly rate (HOURLY_RATE_BASIS_DOC).

    Always derived from BASIC salary (not gross) — matches the existing
    salary_calculator's PF-on-basic convention.
    """
    hours_per_day = (
        shift.full_day_hours if shift is not None and shift.full_day_hours > 0
        else FALLBACK_FULL_DAY_HOURS
    )
    days = STANDARD_DAYS_PER_MONTH
    if days <= 0 or hours_per_day <= 0:
        return 0.0
    return float(basic_salary) / float(days) / float(hours_per_day)


# ----- day-type classification ---------------------------------------


def classify_day_type(
    work_date: date,
    shift: Optional[ShiftLike],
    holiday_dates: set[date],
) -> DayType:
    """Decide which multiplier applies.

    Holiday wins over weekly-off (HR convention: a public holiday that
    happens to fall on a weekly-off pays at the holiday rate, not the
    weekly-off rate).
    """
    if work_date in holiday_dates:
        return DayType.HOLIDAY
    if shift is not None and shift.weekly_offs:
        if work_date.weekday() in shift.weekly_offs:
            return DayType.WEEKLY_OFF
    return DayType.WEEKDAY


# ----- rounding -----------------------------------------------------


def _round_down(minutes: int, step: int) -> int:
    """Round DOWN to nearest `step`. Always rounding-down is the safe
    direction for an employer-facing payout (never pays for unworked
    minutes due to rounding). Below `step`, the result is 0.
    """
    if step <= 0:
        return minutes
    return (minutes // step) * step


# ----- overtime ------------------------------------------------------


def _baseline_hours(
    rule: OTRuleLike, shift: Optional[ShiftLike],
) -> float:
    """Hours beyond which a worked-minute counts as OT."""
    if rule.ot_basis == OvertimeBasis.BEYOND_THRESHOLD.value:
        if rule.daily_threshold_hours is None:
            # Misconfigured rule -> behave as if no OT (fail safe).
            return float("inf")
        return float(rule.daily_threshold_hours)
    # default: beyond_shift_hours
    if shift is not None and shift.full_day_hours > 0:
        return float(shift.full_day_hours)
    return FALLBACK_FULL_DAY_HOURS


def compute_overtime(
    *,
    worked_hours: float,
    basic_salary: float,
    rule: Optional[OTRuleLike],
    shift: Optional[ShiftLike],
    day_type: DayType,
    monthly_minutes_used: int = 0,
) -> OvertimeComputation:
    """Compute OT minutes + amount for a single attendance row.

    `monthly_minutes_used` is the OT minutes ALREADY booked for this
    employee for the same month. We pass it in so the caller (which
    knows the month) can enforce the rule's monthly cap on the row
    being computed without us having to query the DB.

    Returns zeros (and no day-type) when the rule is missing — the
    no-rule no-regression contract.
    """
    if rule is None or worked_hours <= 0:
        return OvertimeComputation(
            ot_minutes=0, ot_amount=0.0,
            hourly_rate_used=0.0, multiplier_used=0.0,
            day_type=day_type,
        )

    baseline = _baseline_hours(rule, shift)
    if math.isinf(baseline):
        return OvertimeComputation(
            ot_minutes=0, ot_amount=0.0,
            hourly_rate_used=0.0, multiplier_used=0.0,
            day_type=day_type,
        )
    raw_extra_minutes = max(0, int(round((worked_hours - baseline) * 60)))

    # 1. min_ot_minutes — anything below this threshold drops to 0.
    if raw_extra_minutes < rule.min_ot_minutes:
        return OvertimeComputation(
            ot_minutes=0, ot_amount=0.0,
            hourly_rate_used=0.0, multiplier_used=0.0,
            day_type=day_type,
        )

    # 2. rounding — always round DOWN so we never overpay due to rounding.
    rounded = _round_down(raw_extra_minutes, rule.rounding_minutes)
    if rounded < rule.min_ot_minutes:
        return OvertimeComputation(
            ot_minutes=0, ot_amount=0.0,
            hourly_rate_used=0.0, multiplier_used=0.0,
            day_type=day_type,
        )

    # 3. daily cap.
    capped_daily = min(rounded, rule.daily_ot_cap_minutes)

    # 4. monthly cap (caller-provided running total).
    if rule.monthly_ot_cap_minutes is not None:
        remaining = max(0, rule.monthly_ot_cap_minutes - monthly_minutes_used)
        capped = min(capped_daily, remaining)
    else:
        capped = capped_daily

    if capped <= 0:
        return OvertimeComputation(
            ot_minutes=0, ot_amount=0.0,
            hourly_rate_used=0.0, multiplier_used=0.0,
            day_type=day_type,
        )

    # 5. pick multiplier by day-type.
    if day_type == DayType.HOLIDAY:
        mult = rule.holiday_multiplier
    elif day_type == DayType.WEEKLY_OFF:
        mult = rule.weekly_off_multiplier
    else:
        mult = rule.ot_rate_multiplier

    hourly_rate = compute_hourly_rate(basic_salary, shift)
    amount = round(hourly_rate * mult * (capped / 60.0), 2)

    return OvertimeComputation(
        ot_minutes=capped, ot_amount=amount,
        hourly_rate_used=round(hourly_rate, 4),
        multiplier_used=mult,
        day_type=day_type,
    )


# ----- night-shift allowance ----------------------------------------


def _combine(d: date, t: time, tz: timezone = timezone.utc) -> datetime:
    return datetime(d.year, d.month, d.day,
                    t.hour, t.minute, t.second, t.microsecond,
                    tzinfo=tz)


def _night_window_for_workdate(
    work_date: date,
    start_t: time,
    end_t: time,
    tz: timezone = timezone.utc,
) -> tuple[datetime, datetime]:
    """Build the (start_dt, end_dt) of the night window for a work_date.

    Cross-midnight when start_t > end_t (e.g. 22:00 -> 06:00) — end_dt
    rolls onto work_date + 1.
    """
    start_dt = _combine(work_date, start_t, tz)
    if start_t > end_t:
        end_dt = _combine(work_date + timedelta(days=1), end_t, tz)
    else:
        end_dt = _combine(work_date, end_t, tz)
    return start_dt, end_dt


def night_minutes_in_window(
    punch_in: datetime,
    punch_out: datetime,
    work_date: date,
    night_start: time,
    night_end: time,
    tz: timezone = timezone.utc,
) -> int:
    """Minutes of [punch_in, punch_out] that fall inside the night window
    for `work_date`. Cross-midnight safe.

    We consider TWO candidate windows:
      - the one anchored at `work_date`
      - the one anchored at `work_date - 1`  (catches the case where a
        day-shift employee starts work just after midnight; their
        worked period falls in YESTERDAY's night window because that
        window wraps into today)

    Returns 0 when either input is None / invalid.
    """
    if punch_in is None or punch_out is None or punch_out <= punch_in:
        return 0

    total_minutes = 0
    for anchor in (work_date - timedelta(days=1), work_date):
        win_start, win_end = _night_window_for_workdate(
            anchor, night_start, night_end, tz
        )
        ov_start = max(punch_in, win_start)
        ov_end = min(punch_out, win_end)
        if ov_end > ov_start:
            total_minutes += int((ov_end - ov_start).total_seconds() // 60)
    return total_minutes


def compute_night_allowance(
    *,
    punch_in: Optional[datetime],
    punch_out: Optional[datetime],
    work_date: date,
    rule: Optional[NightRuleLike],
    tz: timezone = timezone.utc,
) -> NightAllowanceComputation:
    """Returns zero when no rule, no punches, or below min_night_minutes."""
    if rule is None or punch_in is None or punch_out is None:
        return NightAllowanceComputation(
            night_minutes=0, amount=0.0,
            payout_model_used=NightPayoutModel(
                rule.payout_model if rule else NightPayoutModel.FLAT.value
            ),
        )

    qualifying = night_minutes_in_window(
        punch_in, punch_out, work_date,
        rule.night_window_start, rule.night_window_end, tz,
    )
    if qualifying < rule.min_night_minutes:
        return NightAllowanceComputation(
            night_minutes=0, amount=0.0,
            payout_model_used=NightPayoutModel(rule.payout_model),
        )

    model = NightPayoutModel(rule.payout_model)
    if model == NightPayoutModel.FLAT:
        amount = float(rule.flat_amount)
    else:
        amount = round(rule.hourly_rate * (qualifying / 60.0), 2)

    return NightAllowanceComputation(
        night_minutes=qualifying, amount=amount, payout_model_used=model,
    )
