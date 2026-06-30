"""Unit tests for the OT + night-allowance pure helpers.

No DB, no fixtures — every test passes plain dataclasses to the helpers
so we can iterate the maths cheaply.
"""
from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from typing import Optional

import pytest

from app.services.overtime import (
    DayType,
    HOURLY_RATE_BASIS_DOC,
    NightPayoutModel,
    OvertimeBasis,
    classify_day_type,
    compute_hourly_rate,
    compute_night_allowance,
    compute_overtime,
    night_minutes_in_window,
    STANDARD_DAYS_PER_MONTH,
)


# ---------------------------- fixtures ----------------------------


@dataclass
class FakeShift:
    start_time: time = time(9, 0)
    end_time: time = time(18, 0)
    is_overnight: bool = False
    full_day_hours: float = 8.0
    weekly_offs: list = field(default_factory=lambda: [6])  # Sun


@dataclass
class FakeOTRule:
    ot_basis: str = OvertimeBasis.BEYOND_SHIFT_HOURS.value
    daily_threshold_hours: Optional[float] = None
    ot_rate_multiplier: float = 1.5
    weekly_off_multiplier: float = 2.0
    holiday_multiplier: float = 2.0
    min_ot_minutes: int = 30
    daily_ot_cap_minutes: int = 240
    monthly_ot_cap_minutes: Optional[int] = None
    rounding_minutes: int = 30


@dataclass
class FakeNightRule:
    payout_model: str = NightPayoutModel.FLAT.value
    flat_amount: float = 200.0
    hourly_rate: float = 80.0
    night_window_start: time = time(22, 0)
    night_window_end: time = time(6, 0)
    min_night_minutes: int = 60


def overnight_shift() -> FakeShift:
    return FakeShift(
        start_time=time(20, 0), end_time=time(4, 0),
        is_overnight=True, full_day_hours=8.0, weekly_offs=[6],
    )


# ---------------------------- hourly rate ----------------------------


class TestHourlyRate:
    def test_basis_is_documented(self):
        assert "26" in HOURLY_RATE_BASIS_DOC
        assert "full_day_hours" in HOURLY_RATE_BASIS_DOC
        assert STANDARD_DAYS_PER_MONTH == 26

    def test_uses_shift_full_day_hours(self):
        # 26000 / 26 / 8 = 125
        rate = compute_hourly_rate(26000, FakeShift(full_day_hours=8.0))
        assert rate == pytest.approx(125.0)

    def test_falls_back_to_8h_when_no_shift(self):
        rate = compute_hourly_rate(26000, None)
        assert rate == pytest.approx(125.0)  # 26000/26/8

    def test_uses_shift_hours_when_not_eight(self):
        # 24000 / 26 / 9
        rate = compute_hourly_rate(24000, FakeShift(full_day_hours=9.0))
        assert rate == pytest.approx(24000 / 26 / 9)


# ---------------------------- classify_day_type ----------------------


class TestClassifyDayType:
    def test_holiday_wins_over_weekly_off(self):
        # Sunday is a weekly off, but the date is also a holiday.
        sunday = date(2026, 6, 28)
        assert sunday.weekday() == 6
        d = classify_day_type(sunday, FakeShift(weekly_offs=[6]), {sunday})
        assert d == DayType.HOLIDAY

    def test_weekly_off_when_no_holiday(self):
        sunday = date(2026, 6, 28)
        d = classify_day_type(sunday, FakeShift(weekly_offs=[6]), set())
        assert d == DayType.WEEKLY_OFF

    def test_weekday_when_neither(self):
        wed = date(2026, 7, 1)
        d = classify_day_type(wed, FakeShift(weekly_offs=[6]), set())
        assert d == DayType.WEEKDAY

    def test_no_shift_means_no_weekly_off_concept(self):
        sun = date(2026, 6, 28)
        d = classify_day_type(sun, None, set())
        assert d == DayType.WEEKDAY


# ---------------------------- overtime compute ----------------------


class TestComputeOvertime:
    def test_no_rule_no_regression(self):
        c = compute_overtime(
            worked_hours=12.0, basic_salary=26000,
            rule=None, shift=FakeShift(),
            day_type=DayType.WEEKDAY,
        )
        assert c.ot_minutes == 0
        assert c.ot_amount == 0.0

    def test_no_overtime_when_at_or_below_shift_hours(self):
        c = compute_overtime(
            worked_hours=8.0, basic_salary=26000,
            rule=FakeOTRule(), shift=FakeShift(full_day_hours=8.0),
            day_type=DayType.WEEKDAY,
        )
        assert c.ot_minutes == 0

    def test_overtime_beyond_shift_hours_weekday(self):
        # 10h worked, 8h shift -> 120 OT min
        # rounding 30, daily cap 240, mult 1.5
        # hourly = 26000/26/8 = 125; amount = 125 * 1.5 * 2 = 375
        c = compute_overtime(
            worked_hours=10.0, basic_salary=26000,
            rule=FakeOTRule(), shift=FakeShift(full_day_hours=8.0),
            day_type=DayType.WEEKDAY,
        )
        assert c.ot_minutes == 120
        assert c.multiplier_used == 1.5
        assert c.ot_amount == pytest.approx(375.0)

    def test_weekly_off_uses_weekly_off_multiplier(self):
        c = compute_overtime(
            worked_hours=10.0, basic_salary=26000,
            rule=FakeOTRule(), shift=FakeShift(full_day_hours=8.0),
            day_type=DayType.WEEKLY_OFF,
        )
        # 125 * 2.0 * 2h = 500
        assert c.multiplier_used == 2.0
        assert c.ot_amount == pytest.approx(500.0)

    def test_holiday_uses_holiday_multiplier(self):
        rule = FakeOTRule(holiday_multiplier=2.5)
        c = compute_overtime(
            worked_hours=10.0, basic_salary=26000,
            rule=rule, shift=FakeShift(full_day_hours=8.0),
            day_type=DayType.HOLIDAY,
        )
        assert c.multiplier_used == 2.5

    def test_min_ot_minutes_drops_short_overtime(self):
        # 8h + 20 min -> 20 min < min 30 -> dropped
        c = compute_overtime(
            worked_hours=8 + 20 / 60, basic_salary=26000,
            rule=FakeOTRule(min_ot_minutes=30, rounding_minutes=15),
            shift=FakeShift(full_day_hours=8.0),
            day_type=DayType.WEEKDAY,
        )
        assert c.ot_minutes == 0

    def test_rounding_rounds_down(self):
        # 8h + 70 min worked. Round down to nearest 30 -> 60.
        c = compute_overtime(
            worked_hours=8 + 70 / 60, basic_salary=26000,
            rule=FakeOTRule(min_ot_minutes=30, rounding_minutes=30),
            shift=FakeShift(full_day_hours=8.0),
            day_type=DayType.WEEKDAY,
        )
        assert c.ot_minutes == 60

    def test_daily_cap_enforced(self):
        # 8h + 6h OT, daily cap 240 -> capped to 240
        c = compute_overtime(
            worked_hours=14.0, basic_salary=26000,
            rule=FakeOTRule(daily_ot_cap_minutes=240),
            shift=FakeShift(full_day_hours=8.0),
            day_type=DayType.WEEKDAY,
        )
        assert c.ot_minutes == 240

    def test_monthly_cap_enforced_with_running_total(self):
        # Monthly cap 300 min; already used 250; today rounded would be 120.
        # Remaining = 50 -> ot_minutes 50. After cap.
        rule = FakeOTRule(monthly_ot_cap_minutes=300, min_ot_minutes=30)
        c = compute_overtime(
            worked_hours=10.0, basic_salary=26000,
            rule=rule, shift=FakeShift(full_day_hours=8.0),
            day_type=DayType.WEEKDAY,
            monthly_minutes_used=250,
        )
        assert c.ot_minutes == 50

    def test_monthly_cap_already_exhausted(self):
        rule = FakeOTRule(monthly_ot_cap_minutes=120)
        c = compute_overtime(
            worked_hours=10.0, basic_salary=26000,
            rule=rule, shift=FakeShift(full_day_hours=8.0),
            day_type=DayType.WEEKDAY,
            monthly_minutes_used=120,
        )
        assert c.ot_minutes == 0
        assert c.ot_amount == 0.0

    def test_beyond_threshold_basis(self):
        rule = FakeOTRule(
            ot_basis=OvertimeBasis.BEYOND_THRESHOLD.value,
            daily_threshold_hours=9.0,
        )
        # 10h - 9h = 60 min
        c = compute_overtime(
            worked_hours=10.0, basic_salary=26000,
            rule=rule, shift=FakeShift(full_day_hours=8.0),
            day_type=DayType.WEEKDAY,
        )
        assert c.ot_minutes == 60

    def test_misconfigured_threshold_rule_returns_zero(self):
        rule = FakeOTRule(
            ot_basis=OvertimeBasis.BEYOND_THRESHOLD.value,
            daily_threshold_hours=None,
        )
        c = compute_overtime(
            worked_hours=20.0, basic_salary=26000,
            rule=rule, shift=FakeShift(full_day_hours=8.0),
            day_type=DayType.WEEKDAY,
        )
        assert c.ot_minutes == 0


# ---------------------------- night-window math ----------------------


class TestNightWindowIntersection:
    def test_punch_inside_window_same_day(self):
        # 22:30 -> 23:30 inside 22-06 window
        pi = datetime(2026, 6, 30, 22, 30, tzinfo=timezone.utc)
        po = datetime(2026, 6, 30, 23, 30, tzinfo=timezone.utc)
        m = night_minutes_in_window(
            pi, po, work_date=date(2026, 6, 30),
            night_start=time(22, 0), night_end=time(6, 0),
        )
        assert m == 60

    def test_crossing_midnight_inside_window(self):
        # 22:00 D -> 04:00 D+1 inside 22-06
        pi = datetime(2026, 6, 30, 22, 0, tzinfo=timezone.utc)
        po = datetime(2026, 7, 1, 4, 0, tzinfo=timezone.utc)
        m = night_minutes_in_window(
            pi, po, work_date=date(2026, 6, 30),
            night_start=time(22, 0), night_end=time(6, 0),
        )
        assert m == 360  # 6 hours

    def test_partial_window_overlap(self):
        # 20:00 -> 23:30 ; only 22:00-23:30 is night
        pi = datetime(2026, 6, 30, 20, 0, tzinfo=timezone.utc)
        po = datetime(2026, 6, 30, 23, 30, tzinfo=timezone.utc)
        m = night_minutes_in_window(
            pi, po, work_date=date(2026, 6, 30),
            night_start=time(22, 0), night_end=time(6, 0),
        )
        assert m == 90

    def test_completely_outside_window(self):
        # 09:00 -> 18:00 weekday: zero
        pi = datetime(2026, 6, 30, 9, 0, tzinfo=timezone.utc)
        po = datetime(2026, 6, 30, 18, 0, tzinfo=timezone.utc)
        m = night_minutes_in_window(
            pi, po, work_date=date(2026, 6, 30),
            night_start=time(22, 0), night_end=time(6, 0),
        )
        assert m == 0

    def test_punches_in_yesterdays_tail_attributed_today(self):
        # Worker punched in 23:30 D-1 and out 02:00 D, attribution flag
        # placed work_date = D-1 by the shift resolver. We should still
        # detect the night minutes correctly (180 min).
        pi = datetime(2026, 6, 29, 23, 30, tzinfo=timezone.utc)
        po = datetime(2026, 6, 30, 2, 0, tzinfo=timezone.utc)
        m = night_minutes_in_window(
            pi, po, work_date=date(2026, 6, 29),
            night_start=time(22, 0), night_end=time(6, 0),
        )
        # 23:30->24:00 (30) + 00:00->02:00 (120) = 150
        assert m == 150

    def test_day_window_non_crossing(self):
        # 13:00-15:00 window, day shift. Worked 13:30-14:30 -> 60 night.
        pi = datetime(2026, 6, 30, 13, 30, tzinfo=timezone.utc)
        po = datetime(2026, 6, 30, 14, 30, tzinfo=timezone.utc)
        m = night_minutes_in_window(
            pi, po, work_date=date(2026, 6, 30),
            night_start=time(13, 0), night_end=time(15, 0),
        )
        assert m == 60


# ---------------------------- night allowance ----------------------


class TestComputeNightAllowance:
    def test_no_rule_no_regression(self):
        c = compute_night_allowance(
            punch_in=datetime(2026, 6, 30, 22, 0, tzinfo=timezone.utc),
            punch_out=datetime(2026, 7, 1, 4, 0, tzinfo=timezone.utc),
            work_date=date(2026, 6, 30), rule=None,
        )
        assert c.night_minutes == 0
        assert c.amount == 0.0

    def test_below_min_minutes_pays_zero(self):
        # 30 min of night work; min_night_minutes 60 -> 0
        rule = FakeNightRule(min_night_minutes=60)
        c = compute_night_allowance(
            punch_in=datetime(2026, 6, 30, 22, 0, tzinfo=timezone.utc),
            punch_out=datetime(2026, 6, 30, 22, 30, tzinfo=timezone.utc),
            work_date=date(2026, 6, 30), rule=rule,
        )
        assert c.night_minutes == 0
        assert c.amount == 0.0

    def test_flat_payout_qualifies_above_min(self):
        rule = FakeNightRule(
            payout_model=NightPayoutModel.FLAT.value, flat_amount=300.0,
            min_night_minutes=60,
        )
        c = compute_night_allowance(
            punch_in=datetime(2026, 6, 30, 22, 0, tzinfo=timezone.utc),
            punch_out=datetime(2026, 7, 1, 4, 0, tzinfo=timezone.utc),
            work_date=date(2026, 6, 30), rule=rule,
        )
        assert c.night_minutes == 360
        assert c.amount == 300.0
        assert c.payout_model_used == NightPayoutModel.FLAT

    def test_hourly_payout_pro_rated(self):
        rule = FakeNightRule(
            payout_model=NightPayoutModel.HOURLY.value,
            hourly_rate=80.0, min_night_minutes=60,
        )
        c = compute_night_allowance(
            punch_in=datetime(2026, 6, 30, 22, 0, tzinfo=timezone.utc),
            punch_out=datetime(2026, 7, 1, 4, 0, tzinfo=timezone.utc),
            work_date=date(2026, 6, 30), rule=rule,
        )
        # 6h * 80 = 480
        assert c.night_minutes == 360
        assert c.amount == pytest.approx(480.0)

    def test_missing_punch_out(self):
        rule = FakeNightRule()
        c = compute_night_allowance(
            punch_in=datetime(2026, 6, 30, 22, 0, tzinfo=timezone.utc),
            punch_out=None,
            work_date=date(2026, 6, 30), rule=rule,
        )
        assert c.night_minutes == 0


# ---------------------------- no-double-count contract ---------------


class TestRecomputeNoDoubleCount:
    """Simulates the recompute-after-payroll-finalize guard.

    The caller (recompute endpoint) is responsible for filtering on
    `payroll_run_id IS NULL` before updating an entry. These tests
    encode the SHAPE of that contract on the pure helpers: feeding the
    same inputs twice must produce the same numbers — never doubled.
    """

    def test_compute_twice_gives_same_amount(self):
        kw = dict(
            worked_hours=10.0, basic_salary=26000,
            rule=FakeOTRule(), shift=FakeShift(full_day_hours=8.0),
            day_type=DayType.WEEKDAY,
        )
        a = compute_overtime(**kw)
        b = compute_overtime(**kw)
        assert a.ot_minutes == b.ot_minutes
        assert a.ot_amount == b.ot_amount

    def test_night_compute_twice_gives_same_amount(self):
        kw = dict(
            punch_in=datetime(2026, 6, 30, 22, 0, tzinfo=timezone.utc),
            punch_out=datetime(2026, 7, 1, 4, 0, tzinfo=timezone.utc),
            work_date=date(2026, 6, 30),
            rule=FakeNightRule(
                payout_model=NightPayoutModel.HOURLY.value,
                hourly_rate=80.0,
            ),
        )
        a = compute_night_allowance(**kw)
        b = compute_night_allowance(**kw)
        assert a.night_minutes == b.night_minutes
        assert a.amount == b.amount
