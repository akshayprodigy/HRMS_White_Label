"""Work-rule + coverage tests (Roadmap v2 Phase 1A, Task 4).
Pure rule tests + DB-backed API tests (cleaned up in teardown)."""
import uuid
from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace as NS

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.api import deps
from app.core.config import settings
from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.main import create_app
from app.models.audit import AuditLog
from app.models.coverage_requirement import CoverageRequirement
from app.models.department import Department
from app.models.employee import Employee, EmployeeStatus
from app.models.roster import RosterEntry, RosterStatus
from app.models.shift import ShiftTemplate
from app.models.user import User
from app.services.schedule_rules import (
    build_spans, check_leave_conflicts, check_rules, compute_coverage,
)
from app.services.time_rules import get_time_rules, set_time_rules

ROSTER = f"{settings.API_V1_STR}/roster"
PW = "test@12345"
D = date(2030, 1, 7)  # Monday

NIGHT = NS(start_time=time(22), end_time=time(6), is_overnight=True, break_minutes=0)
LATE = NS(start_time=time(14), end_time=time(22), is_overnight=False, break_minutes=0)
DAY = NS(start_time=time(9), end_time=time(18), is_overnight=False, break_minutes=60)
TPL = {1: NIGHT, 2: LATE, 3: DAY}
OFF = {"min_rest_hours": 0, "max_consecutive_days": 0,
       "max_consecutive_nights": 0, "max_weekly_hours": 0}


def spans(cells):
    return build_spans(cells, TPL)


# ----------------------------- pure -----------------------------

def test_build_spans_overnight_and_break():
    n, d = spans([(1, D, 1), (1, D, 3)])
    assert n.end == datetime(2030, 1, 8, 6) and n.hours == 8 and n.is_overnight
    assert d.hours == 8 and not d.is_overnight


def test_min_rest_violation():
    s = spans([(1, D, 1), (1, D + timedelta(days=1), 2)])
    v = check_rules(s, {**OFF, "min_rest_hours": 11})
    assert len(v) == 1 and v[0].rule == "min_rest"
    assert v[0].work_date == D + timedelta(days=1)
    assert "8.0h rest" in v[0].message and "11h" in v[0].message


def test_min_rest_ok_and_disabled():
    s = spans([(1, D, 3), (1, D + timedelta(days=1), 3)])  # 15h rest
    assert check_rules(s, {**OFF, "min_rest_hours": 11}) == []
    s = spans([(1, D, 1), (1, D + timedelta(days=1), 2)])
    assert check_rules(s, OFF) == []


def test_max_consecutive_days_one_violation_per_run():
    s = spans([(1, D + timedelta(days=i), 3) for i in range(7)])
    v = check_rules(s, {**OFF, "max_consecutive_days": 6})
    assert len(v) == 1 and v[0].rule == "max_consecutive_days"
    assert v[0].work_date == D + timedelta(days=6)
    # a gap resets the run
    s = spans([(1, D + timedelta(days=i), 3) for i in (0, 1, 2, 4, 5, 6)])
    assert check_rules(s, {**OFF, "max_consecutive_days": 3}) == []


def test_max_consecutive_nights():
    cells = [(1, D + timedelta(days=i), 1) for i in range(5)]
    v = check_rules(spans(cells), {**OFF, "max_consecutive_nights": 4})
    assert [x.rule for x in v] == ["max_consecutive_nights"]
    assert v[0].work_date == D + timedelta(days=4)
    # day shifts do not count as nights
    cells = [(1, D + timedelta(days=i), 3) for i in range(5)]
    assert check_rules(spans(cells), {**OFF, "max_consecutive_nights": 4}) == []


def test_max_weekly_hours_with_break():
    # 5 x 8h (9h - 1h break) = 40h; 6th day -> 48h; 7th -> 56h
    cells = [(1, D + timedelta(days=i), 3) for i in range(5)]
    assert check_rules(spans(cells), {**OFF, "max_weekly_hours": 40}) == []
    cells = [(1, D + timedelta(days=i), 3) for i in range(6)]
    v = check_rules(spans(cells), {**OFF, "max_weekly_hours": 40})
    assert len(v) == 1 and v[0].rule == "max_weekly_hours"
    assert v[0].work_date == D + timedelta(days=5)
    assert "48.0h" in v[0].message
    # Mon-Sun week boundaries: Sun + next Mon are different weeks
    cells = [(1, D + timedelta(days=6), 3), (1, D + timedelta(days=7), 3)]
    assert check_rules(spans(cells), {**OFF, "max_weekly_hours": 10}) == []


def test_leave_conflicts():
    s = spans([(1, D, 3), (1, D + timedelta(days=1), 3)])
    v = check_leave_conflicts(s, {(1, D)})
    assert len(v) == 1 and v[0].rule == "on_leave" and v[0].work_date == D
    assert check_leave_conflicts(s, set()) == []  # half-day leave excluded upstream


def _req(**kw):
    base = dict(department=None, location=None, shift_template_id=3,
                weekday=None, min_headcount=2, max_headcount=3)
    base.update(kw)
    return NS(**base)


def test_coverage_under_ok_over():
    meta = {i: ("A", "L1") for i in range(1, 6)}
    s = spans([(1, D, 3)] + [(i, D + timedelta(days=1), 3) for i in (1, 2)]
              + [(i, D + timedelta(days=2), 3) for i in range(1, 6)])
    cells = compute_coverage(s, [_req()], meta, [D + timedelta(days=i) for i in range(3)])
    assert [c.status for c in cells] == ["under", "ok", "over"]
    assert [c.scheduled for c in cells] == [1, 2, 5]


def test_coverage_weekday_and_department():
    meta = {1: ("A", None), 2: ("B", None)}
    s = spans([(1, D, 3), (2, D, 3)])
    dates = [D, D + timedelta(days=1)]
    c = compute_coverage(s, [_req(weekday=0, min_headcount=1)], meta, dates)
    assert len(c) == 1 and c[0].date == D  # Tuesday skipped
    c = compute_coverage(s, [_req(department="A", min_headcount=2)], meta, [D])
    assert c[0].scheduled == 1 and c[0].status == "under"
    c = compute_coverage(s, [_req(location="L9", min_headcount=1)], meta, [D])
    assert c[0].scheduled == 0


# ----------------------------- API -----------------------------

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
    dept = f"SR{sfx}"
    try:
        async with SessionLocal() as db:
            def mk(tag, **kw):
                return User(email=f"sr_{tag}_{sfx}@t.com", full_name=f"SR {tag}",
                            hashed_password=get_password_hash(PW),
                            is_active=True, **kw)
            e1, e2, plain = mk("e1"), mk("e2"), mk("plain")
            admin = mk("admin", is_superuser=True)
            db.add_all([e1, e2, plain, admin, Department(name=dept)])
            night = ShiftTemplate(name=f"SRN{sfx}", start_time=time(22),
                                  end_time=time(6), is_overnight=True,
                                  break_minutes=0)
            late = ShiftTemplate(name=f"SRL{sfx}", start_time=time(14),
                                 end_time=time(22), break_minutes=0)
            db.add_all([night, late])
            await db.commit()
            for tag, u in (("1", e1), ("2", e2)):
                db.add(Employee(
                    user_id=u.id, employee_id=f"SR{sfx}{tag}", department=dept,
                    designation="T", date_of_joining=date(2020, 1, 1),
                    status=EmployeeStatus.ACTIVE))
            await db.commit()
            ids = {"e1": e1.id, "e2": e2.id, "night": night.id, "late": late.id}
        yield {"ids": ids, "dept": dept, "sfx": sfx,
               "admin": f"sr_admin_{sfx}@t.com", "plain": f"sr_plain_{sfx}@t.com"}
    finally:
        async with SessionLocal() as db:
            uids = list((await db.execute(select(User.id).where(
                User.email.like(f"sr\\_%\\_{sfx}@t.com")))).scalars().all())
            tids = list((await db.execute(select(ShiftTemplate.id).where(
                ShiftTemplate.name.like(f"SR_{sfx}")))).scalars().all())
            rids = list((await db.execute(select(CoverageRequirement.id).where(
                CoverageRequirement.shift_template_id.in_(tids)))).scalars().all())
            await db.execute(delete(AuditLog).where(
                AuditLog.resource_type == "coverage_requirement",
                AuditLog.resource_id.in_([str(i) for i in rids])))
            await db.execute(delete(CoverageRequirement).where(
                CoverageRequirement.id.in_(rids)))
            await db.execute(delete(RosterEntry).where(
                RosterEntry.employee_id.in_(uids)))
            await db.execute(delete(Employee).where(Employee.user_id.in_(uids)))
            await db.execute(delete(Department).where(Department.name == dept))
            await db.execute(delete(ShiftTemplate).where(ShiftTemplate.id.in_(tids)))
            await db.execute(delete(User).where(User.id.in_(uids)))
            await db.commit()


async def _login(client, email):
    r = await client.post(f"{settings.API_V1_STR}/auth/login",
                          data={"username": email, "password": PW})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_insights_draft_entries_count(client, world):
    ids = world["ids"]
    async with SessionLocal() as db:
        before = await get_time_rules(db)
        await set_time_rules(db, {"schedule.min_rest_hours": "11"})
        db.add_all([
            RosterEntry(employee_id=ids["e1"], work_date=D,
                        shift_template_id=ids["night"], status=RosterStatus.DRAFT),
            RosterEntry(employee_id=ids["e1"], work_date=D + timedelta(days=1),
                        shift_template_id=ids["late"], status=RosterStatus.DRAFT),
        ])
        await db.commit()
    try:
        h = await _login(client, world["admin"])
        r = await client.get(f"{ROSTER}/insights", headers=h, params={
            "start": D.isoformat(), "end": (D + timedelta(days=3)).isoformat(),
            "department": world["dept"]})
        assert r.status_code == 200, r.text
        v = [x for x in r.json()["violations"] if x["user_id"] == ids["e1"]]
        assert len(v) == 1 and v[0]["rule"] == "min_rest"
        assert v[0]["work_date"] == (D + timedelta(days=1)).isoformat()
        # a window starting after the offending date excludes it
        r = await client.get(f"{ROSTER}/insights", headers=h, params={
            "start": (D + timedelta(days=2)).isoformat(),
            "end": (D + timedelta(days=3)).isoformat(),
            "department": world["dept"]})
        assert r.json()["violations"] == []
        # unscoped plain user -> 403
        hp = await _login(client, world["plain"])
        r = await client.get(f"{ROSTER}/insights", headers=hp, params={
            "start": D.isoformat(), "end": D.isoformat()})
        assert r.status_code == 403, r.text
    finally:
        async with SessionLocal() as db:
            await set_time_rules(db, {
                "schedule.min_rest_hours": before["schedule.min_rest_hours"]})


async def test_insights_coverage(client, world):
    ids = world["ids"]
    ha = await _login(client, world["admin"])
    r = await client.post(f"{ROSTER}/coverage-requirements", headers=ha, json={
        "department": world["dept"], "shift_template_id": ids["late"],
        "weekday": 0, "min_headcount": 2, "max_headcount": 3})
    assert r.status_code == 200, r.text
    async with SessionLocal() as db:
        db.add(RosterEntry(employee_id=ids["e1"], work_date=D,
                           shift_template_id=ids["late"],
                           status=RosterStatus.DRAFT))
        await db.commit()
    r = await client.get(f"{ROSTER}/insights", headers=ha, params={
        "start": D.isoformat(), "end": (D + timedelta(days=1)).isoformat(),
        "department": world["dept"]})
    cov = [c for c in r.json()["coverage"] if c["shift_template_id"] == ids["late"]]
    assert len(cov) == 1  # weekday=0 only
    assert cov[0]["scheduled"] == 1 and cov[0]["status"] == "under"


async def test_coverage_crud(client, world):
    ids = world["ids"]
    ha = await _login(client, world["admin"])
    hp = await _login(client, world["plain"])
    body = {"shift_template_id": ids["late"], "min_headcount": 2}
    assert (await client.post(f"{ROSTER}/coverage-requirements", json=body,
                              headers=hp)).status_code == 403
    for bad in ({**body, "max_headcount": 1}, {**body, "weekday": 7},
                {**body, "min_headcount": -1},
                {**body, "shift_template_id": 99999999}):
        r = await client.post(f"{ROSTER}/coverage-requirements", json=bad,
                              headers=ha)
        assert r.status_code == 422, (bad, r.text)
    r = await client.post(f"{ROSTER}/coverage-requirements", json=body, headers=ha)
    assert r.status_code == 200, r.text
    rid = r.json()["id"]
    assert (await client.patch(f"{ROSTER}/coverage-requirements/{rid}",
                               json={"max_headcount": 1}, headers=ha)
            ).status_code == 422
    r = await client.patch(f"{ROSTER}/coverage-requirements/{rid}",
                           json={"max_headcount": 5}, headers=ha)
    assert r.status_code == 200 and r.json()["max_headcount"] == 5
    assert (await client.delete(f"{ROSTER}/coverage-requirements/{rid}",
                                headers=hp)).status_code == 403
    assert (await client.delete(f"{ROSTER}/coverage-requirements/{rid}",
                                headers=ha)).status_code == 200
    r = await client.get(f"{ROSTER}/coverage-requirements", headers=ha)
    assert rid not in [x["id"] for x in r.json()]
    r = await client.get(f"{ROSTER}/coverage-requirements",
                         headers=ha, params={"include_inactive": "true"})
    assert rid in [x["id"] for x in r.json()]


async def test_time_rules_validation(client, world):
    ha = await _login(client, world["admin"])
    url = f"{settings.API_V1_STR}/hr/time-rules"
    async with SessionLocal() as db:
        before = await get_time_rules(db)
    for bad in ("abc", "-1", "1.5", ""):
        r = await client.put(url, headers=ha,
                             json={"rules": {"schedule.min_rest_hours": bad}})
        assert r.status_code == 422, (bad, r.text)
    async with SessionLocal() as db:
        assert (await get_time_rules(db))["schedule.min_rest_hours"] == \
            before["schedule.min_rest_hours"]
    r = await client.put(url, headers=ha, json={"rules": {
        "schedule.max_weekly_hours": before["schedule.max_weekly_hours"]}})
    assert r.status_code == 200, r.text
