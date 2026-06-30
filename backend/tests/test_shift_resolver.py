"""Unit tests for the shift-aware work-date resolver.

Pure-function tests with no DB / no fixtures required:

    pytest backend/tests/test_shift_resolver.py -v

The resolver is the single point that decides which logical date a
punch belongs to. These cases exist because the system's correctness
depends on those decisions:

1. Overnight attribution: a punch-in at 21:50 and punch-out at 06:10
   the next calendar day both belong to the SAME work-date — the day
   the shift started.
2. Month boundary: a night shift that starts Jun 30 23:00 and ends
   Jul 1 07:00 belongs to JUNE (work_date = Jun 30), not July, so
   the June payroll picks it up.
3. Day shift no-regression: a 09:00 punch on a 09-to-18 day shift
   attributes to the calendar date, with no flag — i.e. legacy
   behaviour is unchanged.
4. No-shift fallback: when the employee has no shift assignment we
   attribute to the calendar date and flag NO_SHIFT, so the rest of
   the system can treat the record exactly like before.
5. Outside-window: a 03:00 punch with only a day shift triggers
   OUTSIDE_WINDOW so HR can review.
6. Ambiguous: when both today's and yesterday's overnight shifts can
   claim a punch, the nearer-start window wins and the record is
   flagged AMBIGUOUS.
"""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

import pytest

from app.services.shift_resolver import (
    AttributionFlag,
    early_out_minutes,
    late_in_minutes,
    resolve_work_date,
    worked_hours,
)


@dataclass
class FakeShift:
    """Minimal stand-in for ShiftTemplate matching the resolver's Protocol."""
    start_time: time
    end_time: time
    is_overnight: bool
    grace_in_minutes: int = 10
    grace_out_minutes: int = 10
    break_minutes: int = 60


# Canonical fixtures used by multiple tests.
DAY_SHIFT = FakeShift(
    start_time=time(9, 0), end_time=time(18, 0), is_overnight=False
)
NIGHT_SHIFT = FakeShift(
    start_time=time(22, 0), end_time=time(6, 0), is_overnight=True
)


def utc(y, m, d, hh=0, mm=0, ss=0) -> datetime:
    return datetime(y, m, d, hh, mm, ss, tzinfo=timezone.utc)


# --- 1. Overnight attribution -------------------------------------------


class TestOvernightAttribution:
    def test_punch_in_just_before_midnight_belongs_to_start_date(self):
        # Night shift 22:00-06:00; punch-in 21:50 on Jun 10.
        result = resolve_work_date(
            punch_ts=utc(2026, 6, 10, 21, 50),
            today_shift=NIGHT_SHIFT,
            yesterday_shift=NIGHT_SHIFT,
        )
        assert result.work_date == date(2026, 6, 10)
        assert result.is_cross_midnight is False  # the punch itself is on D
        assert result.flag is None

    def test_punch_out_after_midnight_belongs_to_start_date(self):
        # The 06:10 punch-out on Jun 11 must attribute back to Jun 10.
        # Today (Jun 11) the employee is also on a night shift, but the
        # 06:10 timestamp is BEFORE Jun 11's 22:00 start window, so only
        # Jun 10's window matches.
        result = resolve_work_date(
            punch_ts=utc(2026, 6, 11, 6, 10),
            today_shift=NIGHT_SHIFT,        # Jun 11
            yesterday_shift=NIGHT_SHIFT,    # Jun 10
        )
        assert result.work_date == date(2026, 6, 10)
        assert result.is_cross_midnight is True
        assert result.flag is None

    def test_punch_out_after_midnight_within_grace(self):
        # 06:09 with a 10-min grace_out → still attribute to Jun 10.
        result = resolve_work_date(
            punch_ts=utc(2026, 6, 11, 6, 9),
            today_shift=NIGHT_SHIFT,
            yesterday_shift=NIGHT_SHIFT,
        )
        assert result.work_date == date(2026, 6, 10)
        assert result.flag is None

    def test_punch_far_after_grace_falls_outside_window(self):
        # 08:00 next day is well past the end + grace → OUTSIDE_WINDOW.
        result = resolve_work_date(
            punch_ts=utc(2026, 6, 11, 8, 0),
            today_shift=NIGHT_SHIFT,
            yesterday_shift=NIGHT_SHIFT,
        )
        assert result.work_date == date(2026, 6, 11)
        assert result.flag is AttributionFlag.OUTSIDE_WINDOW


# --- 2. Month-boundary correctness for payroll --------------------------


class TestMonthBoundary:
    def test_night_shift_started_jun_30_belongs_to_june_payroll(self):
        # Shift starts Jun 30 23:00 and ends Jul 1 07:00. Both punches
        # MUST attribute to work_date = Jun 30, so June payroll picks
        # them up.
        night = FakeShift(
            start_time=time(23, 0), end_time=time(7, 0), is_overnight=True
        )
        # Punch-in:
        r_in = resolve_work_date(
            punch_ts=utc(2026, 6, 30, 22, 55),  # 5-min early
            today_shift=night, yesterday_shift=night,
        )
        assert r_in.work_date == date(2026, 6, 30)
        assert r_in.work_date.month == 6

        # Punch-out the next calendar day:
        r_out = resolve_work_date(
            punch_ts=utc(2026, 7, 1, 7, 5),  # within 10-min grace
            today_shift=night, yesterday_shift=night,
        )
        assert r_out.work_date == date(2026, 6, 30)
        assert r_out.work_date.month == 6, "must NOT roll into July"

    def test_punch_in_after_midnight_within_grace_still_jun_30(self):
        # Slightly late punch-in: 23:30 on Jun 30. Still Jun 30.
        night = FakeShift(
            start_time=time(23, 0), end_time=time(7, 0), is_overnight=True
        )
        r = resolve_work_date(
            punch_ts=utc(2026, 6, 30, 23, 30),
            today_shift=night, yesterday_shift=night,
        )
        assert r.work_date == date(2026, 6, 30)


# --- 3. Day shift no-regression ------------------------------------------


class TestDayShiftNoRegression:
    def test_on_time_punch_is_calendar_date_with_no_flag(self):
        r = resolve_work_date(
            punch_ts=utc(2026, 6, 10, 9, 0),
            today_shift=DAY_SHIFT,
            yesterday_shift=DAY_SHIFT,
        )
        assert r.work_date == date(2026, 6, 10)
        assert r.is_cross_midnight is False
        assert r.flag is None

    def test_late_in_within_grace_is_still_unflagged(self):
        # 09:08 with a 10-min grace_in is on time.
        r = resolve_work_date(
            punch_ts=utc(2026, 6, 10, 9, 8),
            today_shift=DAY_SHIFT,
            yesterday_shift=DAY_SHIFT,
        )
        assert r.work_date == date(2026, 6, 10)
        assert r.flag is None

    def test_early_punch_within_buffer_is_unflagged(self):
        # 07:30 punch — within the 2h early buffer.
        r = resolve_work_date(
            punch_ts=utc(2026, 6, 10, 7, 30),
            today_shift=DAY_SHIFT,
            yesterday_shift=DAY_SHIFT,
        )
        assert r.work_date == date(2026, 6, 10)
        assert r.flag is None

    def test_punch_out_within_grace_unflagged(self):
        # 18:08 on a day shift ending 18:00 with 10-min grace.
        r = resolve_work_date(
            punch_ts=utc(2026, 6, 10, 18, 8),
            today_shift=DAY_SHIFT,
            yesterday_shift=DAY_SHIFT,
        )
        assert r.work_date == date(2026, 6, 10)
        assert r.flag is None


# --- 4. No-shift fallback ------------------------------------------------


class TestNoShiftFallback:
    def test_no_shift_attributes_to_calendar_date_with_flag(self):
        r = resolve_work_date(
            punch_ts=utc(2026, 6, 10, 9, 5),
            today_shift=None,
            yesterday_shift=None,
        )
        assert r.work_date == date(2026, 6, 10)
        assert r.is_cross_midnight is False
        assert r.flag is AttributionFlag.NO_SHIFT
        assert r.shift is None

    def test_day_only_yesterday_shift_is_ignored(self):
        # Yesterday shift is a day shift, today none. We attribute today
        # with NO_SHIFT because a day shift cannot "own" the next day.
        r = resolve_work_date(
            punch_ts=utc(2026, 6, 10, 9, 5),
            today_shift=None,
            yesterday_shift=DAY_SHIFT,
        )
        # No today shift; yesterday's DAY shift cannot span midnight.
        # But yesterday_shift is provided -> the early branch path uses it
        # as a fallback only if a window matched. None match, so it falls
        # back to today's calendar date with OUTSIDE_WINDOW.
        assert r.work_date == date(2026, 6, 10)
        assert r.flag in (
            AttributionFlag.OUTSIDE_WINDOW,
            AttributionFlag.NO_SHIFT,
        )


# --- 5. Outside-window flag ---------------------------------------------


class TestOutsideWindow:
    def test_punch_at_3am_with_day_shift_only_is_flagged(self):
        # 03:00 is outside the [07:00, 18:10] day window.
        r = resolve_work_date(
            punch_ts=utc(2026, 6, 10, 3, 0),
            today_shift=DAY_SHIFT,
            yesterday_shift=DAY_SHIFT,
        )
        assert r.work_date == date(2026, 6, 10)
        assert r.flag is AttributionFlag.OUTSIDE_WINDOW
        assert r.shift is DAY_SHIFT


# --- 6. Ambiguous (two windows match) -----------------------------------


class TestAmbiguous:
    def test_punch_in_overlap_between_two_overnight_windows(self):
        # Construct a scenario where today's overnight and yesterday's
        # overnight could BOTH plausibly claim a punch. Today's window
        # opens at 20:00 (22:00 - 2h buffer); yesterday's window closes
        # at 06:10 (next-day 06:00 + grace). The two windows do not
        # actually overlap in time on this configuration, so we craft
        # a shift with a 20:00 start (window opens 18:00) and a 14:00
        # end the next day — yesterday's window would still be open at
        # 18:00 and today's window also opens at 18:00 — overlap exists.
        early_long = FakeShift(
            start_time=time(20, 0), end_time=time(14, 0),
            is_overnight=True, grace_in_minutes=10, grace_out_minutes=10,
        )
        # 18:00 on Jun 10 → today's window opens 18:00 AND yesterday's
        # (Jun 9 20:00 start, Jun 10 14:10 end) has already closed at
        # 14:10. So this particular pair won't overlap.
        # Use a different overlap: an end at 19:00 next day with
        # generous grace.
        ovl = FakeShift(
            start_time=time(20, 0), end_time=time(19, 0),
            is_overnight=True, grace_in_minutes=10, grace_out_minutes=60,
        )
        # Jun 10 18:30:
        #   today's window  = [Jun10 18:00, Jun11 20:00] (start-2h..end+1h)
        #   yesterday's window = [Jun9 18:00, Jun10 20:00]
        # Both contain Jun10 18:30 -> AMBIGUOUS.
        r = resolve_work_date(
            punch_ts=utc(2026, 6, 10, 18, 30),
            today_shift=ovl, yesterday_shift=ovl,
        )
        assert r.flag is AttributionFlag.AMBIGUOUS
        # Nearer-start tiebreak: Jun 10 20:00 start is 1.5h away from
        # 18:30; Jun 9 20:00 start is 22.5h away. Today wins.
        assert r.work_date == date(2026, 6, 10)


# --- 7. worked_hours / late / early-out ---------------------------------


class TestHelpers:
    def test_worked_hours_day_shift(self):
        # 09:05 to 18:05 with 60-min break → 8h.
        h = worked_hours(
            punch_in=utc(2026, 6, 10, 9, 5),
            punch_out=utc(2026, 6, 10, 18, 5),
            shift=DAY_SHIFT,
        )
        assert h == pytest.approx(8.0, abs=1e-6)

    def test_worked_hours_crosses_midnight(self):
        # 22:00 to 06:30 (next day) with 60-min break → 7.5h.
        h = worked_hours(
            punch_in=utc(2026, 6, 10, 22, 0),
            punch_out=utc(2026, 6, 11, 6, 30),
            shift=NIGHT_SHIFT,
        )
        assert h == pytest.approx(7.5, abs=1e-6)

    def test_worked_hours_no_punch_out_is_zero(self):
        h = worked_hours(
            punch_in=utc(2026, 6, 10, 9, 0),
            punch_out=None,
            shift=DAY_SHIFT,
        )
        assert h == 0.0

    def test_worked_hours_without_shift_assumes_60min_break(self):
        # 09:00 to 18:00, no shift → 9h - 1h break = 8h (legacy).
        h = worked_hours(
            punch_in=utc(2026, 6, 10, 9, 0),
            punch_out=utc(2026, 6, 10, 18, 0),
            shift=None,
        )
        assert h == pytest.approx(8.0, abs=1e-6)

    def test_late_in_minutes_evaluates_against_shift_start_plus_grace(self):
        # Punch at 09:25 on a 09:00 start, 10-min grace → 15min late.
        m = late_in_minutes(
            punch_in=utc(2026, 6, 10, 9, 25),
            work_date=date(2026, 6, 10),
            shift=DAY_SHIFT,
        )
        assert m == 15

    def test_late_in_zero_when_within_grace(self):
        m = late_in_minutes(
            punch_in=utc(2026, 6, 10, 9, 9),
            work_date=date(2026, 6, 10),
            shift=DAY_SHIFT,
        )
        assert m == 0

    def test_early_out_minutes_for_overnight(self):
        # Night shift ends 06:00 next day. Punch out at 05:30 with
        # 10-min grace → 20 min early.
        m = early_out_minutes(
            punch_out=utc(2026, 6, 11, 5, 30),
            work_date=date(2026, 6, 10),
            shift=NIGHT_SHIFT,
        )
        assert m == 20

    def test_early_out_zero_without_punch_out(self):
        m = early_out_minutes(
            punch_out=None,
            work_date=date(2026, 6, 10),
            shift=DAY_SHIFT,
        )
        assert m == 0

    def test_helpers_noop_without_shift(self):
        assert late_in_minutes(
            punch_in=utc(2026, 6, 10, 9, 30),
            work_date=date(2026, 6, 10),
            shift=None,
        ) == 0
        assert early_out_minutes(
            punch_out=utc(2026, 6, 10, 17, 0),
            work_date=date(2026, 6, 10),
            shift=None,
        ) == 0
