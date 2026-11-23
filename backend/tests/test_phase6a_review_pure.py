"""DB-free regression tests for the Phase 6A final-review fixes."""
from datetime import date


async def test_coverage_without_viewer_is_empty(monkeypatch):
    """No viewer -> empty result, never an exception."""
    from app.api.v1.endpoints.reports import _fetch_shift_coverage
    from app.services.reports import ReportFilter

    async def fake_today(db):
        return date(2030, 6, 10)
    monkeypatch.setattr("app.api.v1.endpoints.reports.local_today", fake_today)
    d = date(2030, 6, 10)
    res = await _fetch_shift_coverage(None, ReportFilter(start=d, end=d))
    assert res.rows == []


def test_calendar_feed_uses_live_ops_bounds_for_legacy_overnight():
    from datetime import time, timezone
    from types import SimpleNamespace as NS
    from app.api.v1.endpoints import calendar_feed
    from app.services import live_ops
    assert calendar_feed.shift_bounds is live_ops.shift_bounds
    legacy = NS(start_time=time(9), end_time=time(17), is_overnight=True)
    s, e = calendar_feed.shift_bounds(legacy, date(2030, 6, 10), timezone.utc)
    assert (e - s).total_seconds() == 32 * 3600     # ends next day 17:00
