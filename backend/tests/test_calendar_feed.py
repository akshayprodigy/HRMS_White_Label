"""Personal ICS calendar feed (Roadmap v2 Phase 1B, Task 5)."""
import uuid
from datetime import date, datetime, time, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from _cleanup import purge_shift_templates
from _tz import org_tz_utc  # noqa: F401  (pre-6A UTC expectations)
from app.api import deps
from app.core.config import settings
from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.main import create_app
from app.models.calendar_feed import CalendarFeedToken
from app.models.roster import RosterEntry, RosterStatus
from app.models.shift import ShiftTemplate
from app.models.user import User
from app.services.ics import IcsEvent, fold_line, escape_text, render_ics

ROSTER = f"{settings.API_V1_STR}/roster"
PW = "test@12345"
NOW = datetime(2030, 1, 1, 12, 30, 5)


# ------------------------------ pure ------------------------------

def test_escape():
    assert escape_text("a\\b;c,d\ne\r\nf") == "a\\\\b\\;c\\,d\\ne\\nf"


def test_escape_strips_control_chars():
    assert escape_text("a\x00b\x07c\x1fd\x7fe\tf") == "abcde\tf"


def test_fold_75_octets_and_multibyte():
    line = "SUMMARY:" + "x" * 200
    parts = fold_line(line).split("\r\n")
    assert all(len(p.encode()) <= 75 for p in parts)
    assert all(p.startswith(" ") for p in parts[1:])
    assert "".join([parts[0]] + [p[1:] for p in parts[1:]]) == line
    ml = "SUMMARY:" + "é" * 100 + "日本" * 40 + "😀" * 30
    parts = fold_line(ml).split("\r\n")
    assert all(len(p.encode()) <= 75 for p in parts)
    for p in parts:
        p.encode().decode("utf-8")  # no split chars
    assert "".join([parts[0]] + [p[1:] for p in parts[1:]]) == ml
    assert fold_line("short") == "short"
    exact = "y" * 75
    assert fold_line(exact) == exact


def _ev(**kw):
    base = dict(uid="roster-1@hrms", start=datetime(2030, 1, 5, 9),
                end=datetime(2030, 1, 5, 17), summary="Day; Shift, A",
                description="9:00-17:00")
    base.update(kw)
    return IcsEvent(**base)


def test_render_structure():
    out = render_ics([_ev()], cal_name="My shifts", now=NOW)
    assert out.endswith("\r\n") and "\n" not in out.replace("\r\n", "")
    lines = out.split("\r\n")
    assert lines[0] == "BEGIN:VCALENDAR" and lines[1] == "VERSION:2.0"
    assert "PRODID:-//HRMS//Roster//EN" in lines
    assert "CALSCALE:GREGORIAN" in lines
    assert "REFRESH-INTERVAL;VALUE=DURATION:PT1H" in lines
    assert "X-PUBLISHED-TTL:PT1H" in lines
    assert "X-WR-CALNAME:My shifts" in lines
    assert "UID:roster-1@hrms" in lines
    assert "DTSTAMP:20300101T123005Z" in lines
    assert "DTSTART:20300105T090000" in lines
    assert "DTEND:20300105T170000" in lines
    assert "SUMMARY:Day\\; Shift\\, A" in lines
    assert lines[-2] == "END:VCALENDAR" and lines[-1] == ""


def test_overnight_end_next_day_and_empty():
    out = render_ics([_ev(start=datetime(2030, 1, 5, 22),
                          end=datetime(2030, 1, 6, 6))],
                     cal_name="c", now=NOW)
    assert "DTSTART:20300105T220000" in out and "DTEND:20300106T060000" in out
    empty = render_ics([], cal_name="c", now=NOW)
    assert "BEGIN:VEVENT" not in empty and empty.endswith("END:VCALENDAR\r\n")


def test_render_folds_long_summary():
    out = render_ics([_ev(summary="é" * 80)], cal_name="c", now=NOW)
    assert all(len(l.encode()) <= 75 for l in out.split("\r\n"))


# ------------------------------ API ------------------------------

@pytest.fixture
async def client():
    app = create_app()
    app.dependency_overrides[deps.verify_attendance] = lambda: None
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as c:
        yield c


@pytest.fixture
async def world():
    sfx = uuid.uuid4().hex[:8]
    ids = {}
    try:
        async with SessionLocal() as db:
            u = User(email=f"cf_u_{sfx}@t.com", full_name="CF u",
                     hashed_password=get_password_hash(PW), is_active=True)
            db.add(u)
            t_day = ShiftTemplate(name=f"CFD{sfx}", start_time=time(9), end_time=time(17))
            t_night = ShiftTemplate(name=f"CFN{sfx}", start_time=time(22),
                                    end_time=time(6), is_overnight=True)
            db.add_all([t_day, t_night])
            await db.commit()
            today = datetime.now(timezone.utc).date()
            mk = lambda d, **kw: RosterEntry(employee_id=u.id, work_date=d, **kw)
            rows = {
                "pub": mk(today + timedelta(days=2), shift_template_id=t_day.id,
                          status=RosterStatus.PUBLISHED),
                "night": mk(today + timedelta(days=3), shift_template_id=t_night.id,
                            status=RosterStatus.PUBLISHED),
                "draft": mk(today + timedelta(days=4), shift_template_id=t_day.id,
                            status=RosterStatus.DRAFT),
                "off": mk(today + timedelta(days=5), is_week_off=True,
                          status=RosterStatus.PUBLISHED),
                "far": mk(today + timedelta(days=200), shift_template_id=t_day.id,
                          status=RosterStatus.PUBLISHED),
                "old": mk(today - timedelta(days=60), shift_template_id=t_day.id,
                          status=RosterStatus.PUBLISHED),
            }
            db.add_all(rows.values())
            await db.commit()
            ids = {"u": u.id, "t": [t_day.id, t_night.id],
                   **{k: v.id for k, v in rows.items()}}
        yield {"ids": ids, "email": f"cf_u_{sfx}@t.com", "today": today,
               "name_day": f"CFD{sfx}", "sfx": sfx}
    finally:
        async with SessionLocal() as db:
            uid = ids.get("u")
            if uid:
                await db.execute(delete(CalendarFeedToken).where(
                    CalendarFeedToken.user_id == uid))
                await db.execute(delete(RosterEntry).where(
                    RosterEntry.employee_id == uid))
            if ids.get("t"):
                await purge_shift_templates(db, ids["t"])
            if uid:
                await db.execute(delete(User).where(User.id == uid))
            await db.commit()


async def _login(client, email):
    r = await client.post(f"{settings.API_V1_STR}/auth/login",
                          data={"username": email, "password": PW})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _path(url):
    assert url.startswith("http://test/api/v1/calendar/") and url.endswith(".ics")
    return url[len("http://test"):]


async def test_lifecycle(client, world):
    w = world
    h = await _login(client, w["email"])
    r = await client.get(f"{ROSTER}/my/calendar-feed", headers=h)
    assert r.status_code == 200 and r.json() == {"active": False, "created_at": None}
    r = await client.post(f"{ROSTER}/my/calendar-feed", headers=h)
    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-store"
    url1 = r.json()["url"]
    r = await client.get(f"{ROSTER}/my/calendar-feed", headers=h)
    assert r.json()["active"] is True and r.json()["created_at"]
    assert "url" not in r.json()
    # hash only stored
    token1 = url1.rsplit("/", 1)[1][:-4]
    async with SessionLocal() as db:
        row = (await db.execute(select(CalendarFeedToken).where(
            CalendarFeedToken.user_id == w["ids"]["u"]))).scalar_one()
        assert row.token_hash != token1 and len(row.token_hash) == 64

    # public fetch, no auth
    r = await client.get(_path(url1))
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "text/calendar; charset=utf-8"
    assert r.headers["cache-control"] == "private, max-age=900"
    body = r.text
    assert body.count("BEGIN:VEVENT") == 2  # pub + night only
    ids = w["ids"]
    assert f"UID:roster-{ids['pub']}@hrms" in body
    assert f"UID:roster-{ids['night']}@hrms" in body
    for k in ("draft", "off", "far", "old"):
        assert f"UID:roster-{ids[k]}@hrms" not in body
    d = w["today"] + timedelta(days=2)
    assert f"DTSTART:{d:%Y%m%d}T090000" in body
    n = w["today"] + timedelta(days=3)
    assert f"DTSTART:{n:%Y%m%d}T220000" in body
    assert f"DTEND:{n + timedelta(days=1):%Y%m%d}T060000" in body
    assert f"SUMMARY:{w['name_day']}" in body
    async with SessionLocal() as db:
        row = (await db.execute(select(CalendarFeedToken).where(
            CalendarFeedToken.user_id == ids["u"]))).scalar_one()
        assert row.last_used_at is not None
        first_used = row.last_used_at
    # throttled: an immediate second fetch does not rewrite last_used_at
    assert (await client.get(_path(url1))).status_code == 200
    async with SessionLocal() as db:
        row = (await db.execute(select(CalendarFeedToken).where(
            CalendarFeedToken.user_id == ids["u"]))).scalar_one()
        assert row.last_used_at == first_used
        row.last_used_at = datetime.now(timezone.utc) - timedelta(minutes=10)
        stale = row.last_used_at
        await db.commit()
    assert (await client.get(_path(url1))).status_code == 200
    async with SessionLocal() as db:
        row = (await db.execute(select(CalendarFeedToken).where(
            CalendarFeedToken.user_id == ids["u"]))).scalar_one()
        assert row.last_used_at != stale

    # rotate invalidates old
    r = await client.post(f"{ROSTER}/my/calendar-feed", headers=h)
    url2 = r.json()["url"]
    assert url2 != url1
    assert (await client.get(_path(url1))).status_code == 404
    assert (await client.get(_path(url2))).status_code == 200

    # delete
    assert (await client.delete(f"{ROSTER}/my/calendar-feed", headers=h)).status_code == 204
    assert (await client.get(_path(url2))).status_code == 404
    r = await client.get(f"{ROSTER}/my/calendar-feed", headers=h)
    assert r.json()["active"] is False
    assert (await client.delete(f"{ROSTER}/my/calendar-feed", headers=h)).status_code == 204


async def test_unknown_and_malformed_and_inactive(client, world):
    w = world
    base = f"{settings.API_V1_STR}/calendar"
    r1 = await client.get(f"{base}/{'a' * 43}.ics")
    r2 = await client.get(f"{base}/short.ics")
    assert r1.status_code == r2.status_code == 404
    h = await _login(client, w["email"])
    url = (await client.post(f"{ROSTER}/my/calendar-feed", headers=h)).json()["url"]
    async with SessionLocal() as db:
        u = await db.get(User, w["ids"]["u"])
        u.is_active = False
        await db.commit()
    r3 = await client.get(_path(url))
    assert r3.status_code == 404 and r3.json() == r1.json() == r2.json()


async def test_requires_auth_for_management(client, world):
    assert (await client.get(f"{ROSTER}/my/calendar-feed")).status_code in (401, 403)


async def test_public_base_url_override(client, world, monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", "https://hr.example.com/")
    h = await _login(client, world["email"])
    r = await client.post(f"{ROSTER}/my/calendar-feed", headers=h)
    assert r.json()["url"].startswith("https://hr.example.com/api/v1/calendar/")
    assert "//api" not in r.json()["url"].replace("https://", "")


async def test_forwarded_host_used(client, world, monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", None)
    h = await _login(client, world["email"])
    r = await client.post(f"{ROSTER}/my/calendar-feed", headers={
        **h, "X-Forwarded-Host": "hr.corp.io:8443, internal",
        "X-Forwarded-Proto": "https, http"})
    assert r.json()["url"].startswith("https://hr.corp.io:8443/api/v1/calendar/")
    r = await client.post(f"{ROSTER}/my/calendar-feed", headers={
        **h, "X-Forwarded-Host": "localhost:5173"})
    assert r.json()["url"].startswith("http://localhost:5173/api/v1/calendar/")


@pytest.mark.parametrize("bad", ["evil.com/x", "a b", "h@ost", "x.com:99999999",
                                 "-bad.com", "ex ample.com:80", "ht\\tp.com"])
async def test_invalid_forwarded_host_ignored(client, world, monkeypatch, bad):
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", None)
    h = await _login(client, world["email"])
    r = await client.post(f"{ROSTER}/my/calendar-feed",
                          headers={**h, "X-Forwarded-Host": bad})
    assert r.json()["url"].startswith("http://test/api/v1/calendar/")


async def test_public_base_url_beats_forwarded(client, world, monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", "https://hr.example.com")
    h = await _login(client, world["email"])
    r = await client.post(f"{ROSTER}/my/calendar-feed", headers={
        **h, "X-Forwarded-Host": "other.io"})
    assert r.json()["url"].startswith("https://hr.example.com/api/v1/calendar/")
