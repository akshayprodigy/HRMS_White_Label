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
