"""Shift-aware work-date attribution.

This module is the single source of truth for deciding which logical
work-date a punch belongs to. It is intentionally pure — no DB, no I/O —
so it can be unit-tested without fixtures and reused from any endpoint.

Glossary
========
- punch_ts : timezone-aware UTC datetime when the punch happened.
- shift    : a ShiftTemplate-shaped object exposing start_time, end_time,
             is_overnight, grace_in_minutes, grace_out_minutes.
- work_date: the logical calendar date the punch is attributed to. For
             a day shift this is the date of the punch; for an overnight
             shift it is the date the shift *started*, even if the punch
             happens after midnight.

Rules
=====
1. A day shift's window is roughly
       [start - early_in_buffer, end + grace_out_minutes]
   on the calendar date of the punch.

2. An overnight shift's window is
       [start - early_in_buffer on D, end + grace_out_minutes on D+1]

3. When resolving a punch we examine:
     - the shift effective on the punch's calendar date (today_shift)
     - the shift effective on the previous calendar date (yesterday_shift)
       — but only if it is overnight; a non-overnight yesterday shift
       cannot legally pull a today-punch backwards.

4. Cases:
     0 matching windows  -> calendar date, flag OUTSIDE_WINDOW (or
                            NO_SHIFT when employee has no shift at all).
     1 matching window   -> that work_date, no flag.
     2 matching windows  -> choose the window whose start_dt is closest
                            in time to the punch_ts, flag AMBIGUOUS.

5. Backward compatibility: if the employee has no shift assignment, we
   attribute to the punch's calendar date and flag NO_SHIFT. The
   downstream code path then behaves exactly like the pre-shift world.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from enum import Enum
from typing import Optional, Protocol

# How far before a shift's nominal start we are willing to count a punch
# as "for that shift". Two hours is a generous default that handles
# people clocking in very early without bleeding into a separate day
# shift's window. The constant is deliberately exposed so callers/tests
# can override it.
DEFAULT_EARLY_IN_BUFFER = timedelta(hours=2)


class AttributionFlag(str, Enum):
    """Marker added to attendance records the resolver was not confident
    about. None on the record = high-confidence attribution; a value
    means HR should review.
    """
    NO_SHIFT = "no_shift"          # employee has no shift assignment
    OUTSIDE_WINDOW = "outside_window"  # punch falls outside any window
    AMBIGUOUS = "ambiguous"        # two windows both matched, picked nearest


class ShiftLike(Protocol):
    """Structural type accepted by the resolver. Lets tests pass simple
    dataclasses without needing a SQLAlchemy session.
    """
    start_time: time
    end_time: time
    is_overnight: bool
    grace_in_minutes: int
    grace_out_minutes: int


@dataclass
class ShiftWindow:
    """Half-open window [start_dt, end_dt) representing when a punch is
    counted as part of a given work-date for a given shift.
    """
    work_date: date
    shift: ShiftLike
    start_dt: datetime
    end_dt: datetime
    is_overnight: bool

    def contains(self, ts: datetime) -> bool:
        return self.start_dt <= ts <= self.end_dt

    def distance_to_start(self, ts: datetime) -> timedelta:
        return abs(ts - self.start_dt)


@dataclass
class WorkDateAttribution:
    """Output of `resolve_work_date`."""
    work_date: date
    shift: Optional[ShiftLike]
    is_cross_midnight: bool
    flag: Optional[AttributionFlag]


# --- date / time plumbing -----------------------------------------------


def _local_date(ts: datetime, tz: timezone = timezone.utc) -> date:
    """Local calendar date for a TZ-aware timestamp.

    Storage convention in this project is UTC; the "local" date for
    attribution is the same UTC date for now. Once a per-employee or
    org timezone setting is introduced, this is the single point that
    needs to change.
    """
    if ts.tzinfo is None:
        # Treat naive as UTC. Callers should pass aware datetimes, but
        # do not crash on legacy data.
        return ts.date()
    return ts.astimezone(tz).date()


def _combine(d: date, t: time, tz: timezone = timezone.utc) -> datetime:
    """Build a TZ-aware datetime from a date and a wall-clock time."""
    return datetime(
        d.year, d.month, d.day, t.hour, t.minute, t.second, t.microsecond,
        tzinfo=tz,
    )


def compute_window(
    shift: ShiftLike,
    work_date: date,
    early_in_buffer: timedelta = DEFAULT_EARLY_IN_BUFFER,
    tz: timezone = timezone.utc,
) -> ShiftWindow:
    """Return the punch window for `shift` evaluated as the *work_date* shift.

    For an overnight shift starting on `work_date`, the window ends on
    `work_date + 1` (because end_time is on the next calendar day).
    """
    start_dt = _combine(work_date, shift.start_time, tz) - early_in_buffer
    if shift.is_overnight:
        end_dt = _combine(
            work_date + timedelta(days=1), shift.end_time, tz
        ) + timedelta(minutes=shift.grace_out_minutes)
    else:
        end_dt = _combine(
            work_date, shift.end_time, tz
        ) + timedelta(minutes=shift.grace_out_minutes)
    return ShiftWindow(
        work_date=work_date,
        shift=shift,
        start_dt=start_dt,
        end_dt=end_dt,
        is_overnight=shift.is_overnight,
    )


# --- the resolver --------------------------------------------------------


def resolve_work_date(
    punch_ts: datetime,
    today_shift: Optional[ShiftLike],
    yesterday_shift: Optional[ShiftLike],
    early_in_buffer: timedelta = DEFAULT_EARLY_IN_BUFFER,
    tz: timezone = timezone.utc,
) -> WorkDateAttribution:
    """Pick the work-date for a punch.

    Args
    ----
    punch_ts : the actual punch timestamp (must be TZ-aware in production;
               naive accepted for tests).
    today_shift     : employee's effective shift on the punch's calendar date.
    yesterday_shift : employee's effective shift on (punch_date - 1).
                      Only considered if it is overnight.
    early_in_buffer : how early a punch may arrive and still count.
    tz              : timezone used to read the local calendar date.

    Returns
    -------
    WorkDateAttribution with the chosen work_date, the shift used
    (None if no shift available at all), is_cross_midnight (True when
    we attribute the punch to an overnight shift whose start is on a
    different calendar date than the punch), and an attribution flag
    (None for confident attributions).
    """
    punch_date = _local_date(punch_ts, tz)

    # No shift information at all -> NO_SHIFT, calendar date attribution.
    if today_shift is None and yesterday_shift is None:
        return WorkDateAttribution(
            work_date=punch_date,
            shift=None,
            is_cross_midnight=False,
            flag=AttributionFlag.NO_SHIFT,
        )

    candidates: list[ShiftWindow] = []

    if today_shift is not None:
        candidates.append(
            compute_window(today_shift, punch_date, early_in_buffer, tz)
        )

    # Yesterday's shift can only "own" today's punch if it spans midnight.
    if yesterday_shift is not None and yesterday_shift.is_overnight:
        candidates.append(
            compute_window(
                yesterday_shift, punch_date - timedelta(days=1),
                early_in_buffer, tz,
            )
        )

    matches = [w for w in candidates if w.contains(punch_ts)]

    if len(matches) == 1:
        w = matches[0]
        return WorkDateAttribution(
            work_date=w.work_date,
            shift=w.shift,
            is_cross_midnight=(w.work_date != punch_date),
            flag=None,
        )

    if len(matches) > 1:
        # Pick the window whose start is nearest the punch in time.
        chosen = min(matches, key=lambda w: w.distance_to_start(punch_ts))
        return WorkDateAttribution(
            work_date=chosen.work_date,
            shift=chosen.shift,
            is_cross_midnight=(chosen.work_date != punch_date),
            flag=AttributionFlag.AMBIGUOUS,
        )

    # No window matched. Prefer today's shift for the attribution (more
    # plausible: the employee is on shift today but punched off-window)
    # and flag OUTSIDE_WINDOW so HR can review.
    fallback_shift = today_shift or yesterday_shift
    return WorkDateAttribution(
        work_date=punch_date,
        shift=fallback_shift,
        is_cross_midnight=False,
        flag=AttributionFlag.OUTSIDE_WINDOW,
    )


# --- worked-hours / late-in / early-out ----------------------------------


def worked_hours(
    punch_in: datetime,
    punch_out: Optional[datetime],
    shift: Optional[ShiftLike],
) -> float:
    """Hours worked between punch_in and punch_out, minus the shift break.

    Naturally cross-midnight safe because we just subtract two
    timezone-aware datetimes. If there is no shift, a one-hour break
    is assumed (matches legacy behaviour).
    """
    if punch_out is None or punch_out <= punch_in:
        return 0.0
    total = (punch_out - punch_in).total_seconds()
    break_seconds = (shift.break_minutes if shift is not None else 60) * 60  # type: ignore[union-attr]
    return max(0.0, (total - break_seconds) / 3600.0)


def late_in_minutes(
    punch_in: datetime,
    work_date: date,
    shift: Optional[ShiftLike],
    tz: timezone = timezone.utc,
) -> int:
    """Minutes the employee was late, evaluated against shift.start_time +
    grace_in_minutes. 0 when on time or when no shift is provided.
    """
    if shift is None:
        return 0
    start_dt = _combine(work_date, shift.start_time, tz)
    threshold = start_dt + timedelta(minutes=shift.grace_in_minutes)
    if punch_in <= threshold:
        return 0
    return int((punch_in - threshold).total_seconds() // 60)


def early_out_minutes(
    punch_out: Optional[datetime],
    work_date: date,
    shift: Optional[ShiftLike],
    tz: timezone = timezone.utc,
) -> int:
    """Minutes the employee left early, evaluated against shift.end_time
    on work_date (or work_date+1 for overnight shifts), minus
    grace_out_minutes. 0 when on time or when no shift / no punch-out.
    """
    if shift is None or punch_out is None:
        return 0
    end_date = (
        work_date + timedelta(days=1) if shift.is_overnight else work_date
    )
    end_dt = _combine(end_date, shift.end_time, tz)
    threshold = end_dt - timedelta(minutes=shift.grace_out_minutes)
    if punch_out >= threshold:
        return 0
    return int((threshold - punch_out).total_seconds() // 60)
