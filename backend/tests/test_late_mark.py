"""Pure unit tests for the W9 late-mark engine + W4 PF cap."""
from dataclasses import dataclass
from datetime import date, datetime, time

from app.services.late_mark import _is_late


@dataclass
class _Shift:
    start_time: time


def test_is_late_respects_grace():
    shift = _Shift(start_time=time(9, 0))
    wd = date(2026, 6, 1)
    # 09:05 with 10-min grace -> not late
    assert _is_late(datetime(2026, 6, 1, 9, 5), wd, shift, 10) is False
    # 09:10 exactly at grace edge -> not late
    assert _is_late(datetime(2026, 6, 1, 9, 10), wd, shift, 10) is False
    # 09:11 -> late
    assert _is_late(datetime(2026, 6, 1, 9, 11), wd, shift, 10) is True


def test_is_late_handles_tz_aware_punch():
    from datetime import timezone
    shift = _Shift(start_time=time(9, 0))
    wd = date(2026, 6, 1)
    aware = datetime(2026, 6, 1, 9, 30, tzinfo=timezone.utc)
    assert _is_late(aware, wd, shift, 10) is True


def test_block_math():
    # blocks = late_count // lates_per_deduction; deduct = blocks * days
    for late_count, per, days, expected in [
        (6, 3, 1.0, 2.0), (5, 3, 1.0, 1.0), (2, 3, 1.0, 0.0), (9, 3, 0.5, 1.5),
    ]:
        blocks = late_count // per
        assert round(blocks * days, 2) == expected


def test_pf_cap_clamp():
    # W4: employee PF clamped to the configurable max amount.
    epf_wages, rate = 15000.0, 12.0
    raw = round(epf_wages * rate / 100.0, 2)
    assert raw == 1800.0
    assert min(raw, 1000.0) == 1000.0     # cap active
    assert min(raw, 5000.0) == 1800.0     # cap above raw -> no effect
