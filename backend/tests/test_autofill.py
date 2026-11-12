"""Auto-fill suggestions (Roadmap v2 Phase 1B, Task 8): pure algorithm +
preview API. DB-backed API tests clean up everything they create."""
import uuid
from datetime import date, time, timedelta, datetime, timezone
from types import SimpleNamespace as NS

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from _cleanup import purge_shift_templates
from app.api import deps
from app.core.config import settings
from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.main import create_app
from app.models.coverage_requirement import CoverageRequirement
from app.models.department import Department
from app.models.employee import Employee, EmployeeStatus
from app.models.schedule_delegation import DelegationScope, ScheduleDelegation
from app.models.shift import ShiftTemplate
from app.models.user import User
from app.services.autofill import Slot, suggest
from app.services.availability import AvailabilityDay
from app.services.schedule_rules import build_spans

D = date(2030, 3, 4)  # Monday
DAY = NS(id=1, start_time=time(9), end_time=time(17), is_overnight=False,
         break_minutes=0)
EARLY = NS(id=2, start_time=time(6), end_time=time(14), is_overnight=False,
           break_minutes=0)
NIGHT = NS(id=3, start_time=time(22), end_time=time(6), is_overnight=True,
           break_minutes=0)
TPL = {1: DAY, 2: EARLY, 3: NIGHT}


def emp(uid, dept="A", loc=None):
    return NS(user_id=uid, department=dept, location=loc)


def run(emps, slots, days=None, **kw):
    kw.setdefault("existing_cells", {})
    kw.setdefault("leave_days", set())
    kw.setdefault("availability", {})
    kw.setdefault("rules", {})
    return suggest(
        employees=emps, days=days or [D], templates=TPL, slots=slots,
        window_start=D, **kw)


def test_fills_need_exactly_and_reports_residual():
    s, u = run([emp(1), emp(2), emp(3)], [Slot(D, 1, "A", None, 2)])
    assert [x.user_id for x in s] == [1, 2]
    assert u == []
    s, u = run([emp(1)], [Slot(D, 1, "A", None, 3)])
    assert len(s) == 1 and u == [Slot(D, 1, "A", None, 2)]


def test_department_filter():
    s, u = run([emp(1, "B"), emp(2, "A")], [Slot(D, 1, "A", None, 1)])
    assert [x.user_id for x in s] == [2]


def test_skips_leave_unavailable_existing_and_weekly_off():
    av = {(2, D): AvailabilityDay(unavailable_all_day=True),
          (3, D): AvailabilityDay(unavailable_templates={1})}
    s, u = run(
        [emp(i) for i in range(1, 8)], [Slot(D, 1, "A", None, 7)],
        leave_days={(1, D)},
        existing_cells={(4, D): (None, True), (5, D): (2, False)},
        availability=av, weekly_off_days={(6, D)},
    )
    assert [x.user_id for x in s] == [7]
    assert u[0].need == 6


def test_unavailable_other_template_does_not_block():
    av = {(1, D): AvailabilityDay(unavailable_templates={2})}
    s, _ = run([emp(1)], [Slot(D, 1, "A", None, 1)], availability=av)
    assert len(s) == 1


def test_respects_min_rest():
    d1 = D + timedelta(days=1)
    base = build_spans([(1, D, 3)], TPL)  # night ends 06:00 on d1
    s, u = run(
        [emp(1), emp(2)], [Slot(d1, 2, "A", None, 1)], days=[D, d1],
        base_spans=base, rules={"min_rest_hours": 11},
        existing_cells={(1, D): (3, False)})
    assert [x.user_id for x in s] == [2]
    s, u = run(
        [emp(1)], [Slot(d1, 2, "A", None, 1)], days=[D, d1],
        base_spans=base, rules={"min_rest_hours": 11},
        existing_cells={(1, D): (3, False)})
    assert s == [] and u[0].need == 1


def test_suggested_spans_feed_rule_checks():
    d1 = D + timedelta(days=1)
    s, u = run(
        [emp(1)], [Slot(D, 3, "A", None, 1), Slot(d1, 2, "A", None, 1)],
        days=[D, d1], rules={"min_rest_hours": 11})
    assert [(x.user_id, x.day) for x in s] == [(1, D)]
    assert u == [Slot(d1, 2, "A", None, 1)]


def test_fairness_spreads_nights():
    days = [D + timedelta(days=i) for i in range(4)]
    slots = [Slot(d, 3, "A", None, 1) for d in days]
    s, _ = run([emp(1), emp(2)], slots, days=days)
    counts = {1: 0, 2: 0}
    for x in s:
        counts[x.user_id] += 1
    assert counts == {1: 2, 2: 2}


def test_existing_load_counts_toward_fairness():
    d1 = D + timedelta(days=1)
    base = build_spans([(1, D, 1)], TPL)
    s, _ = run([emp(1), emp(2)], [Slot(d1, 1, "A", None, 1)], days=[D, d1],
               base_spans=base, existing_cells={(1, D): (1, False)})
    assert [x.user_id for x in s] == [2]


def test_preferred_wins_ties():
    av = {(2, D): AvailabilityDay(preferred_templates={1})}
    s, _ = run([emp(1), emp(2)], [Slot(D, 1, "A", None, 1)], availability=av)
    assert s[0].user_id == 2 and "preferred shift" in s[0].reasons


def test_tie_breaks_by_user_id_and_is_deterministic():
    emps = [emp(i) for i in (5, 3, 9, 1)]
    slots = [Slot(D, 1, "A", None, 2)]
    a = run(emps, slots)
    b = run(list(reversed(emps)), slots)
    assert a == b
    assert [x.user_id for x in a[0]] == [1, 3]


def test_one_cell_per_user_per_day():
    s, u = run([emp(1)], [Slot(D, 1, "A", None, 1), Slot(D, 2, "A", None, 1)])
    assert len(s) == 1 and len(u) == 1


# ------------------------------- API -------------------------------

ROSTER = f"{settings.API_V1_STR}/roster"
PW = "test@12345"
TODAY = datetime.now(timezone.utc).date()


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
    dx, dy = f"AFX{sfx}", f"AFY{sfx}"
    try:
        async with SessionLocal() as db:
            def mk(tag, **kw):
                return User(email=f"af_{tag}_{sfx}@t.com", full_name=f"AF {tag}",
                            hashed_password=get_password_hash(PW),
                            is_active=True, **kw)
            deleg, e1, e2, e3 = mk("deleg"), mk("e1"), mk("e2"), mk("e3")
            admin = mk("admin", is_superuser=True)
            db.add_all([deleg, e1, e2, e3, admin,
                        Department(name=dx), Department(name=dy)])
            t1 = ShiftTemplate(name=f"AFT{sfx}", start_time=time(9),
                               end_time=time(17))
            db.add(t1)
            await db.commit()
            for tag, u, d in (("1", e1, dx), ("2", e2, dx), ("3", e3, dy)):
                db.add(Employee(
                    user_id=u.id, employee_id=f"AF{sfx}{tag}", department=d,
                    designation="T", date_of_joining=date(2020, 1, 1),
                    status=EmployeeStatus.ACTIVE))
            db.add(CoverageRequirement(
                department=dx, shift_template_id=t1.id, min_headcount=2,
                is_active=True))
            db.add(CoverageRequirement(
                department=dy, shift_template_id=t1.id, min_headcount=1,
                is_active=True))
            await db.commit()
            db.add(ScheduleDelegation(
                grantee_id=deleg.id, scope_type=DelegationScope.EMPLOYEES,
                employee_ids=[e1.id], valid_from=TODAY - timedelta(days=1)))
            await db.commit()
            ids = {"e1": e1.id, "e2": e2.id, "e3": e3.id, "t1": t1.id}
        yield {"ids": ids, "sfx": sfx, "dx": dx, "dy": dy,
               "deleg": f"af_deleg_{sfx}@t.com",
               "admin": f"af_admin_{sfx}@t.com"}
    finally:
        async with SessionLocal() as db:
            uids = list((await db.execute(select(User.id).where(
                User.email.like(f"af\\_%\\_{sfx}@t.com")))).scalars().all())
            await db.execute(delete(CoverageRequirement).where(
                CoverageRequirement.department.in_([dx, dy])))
            await db.execute(delete(ScheduleDelegation).where(
                ScheduleDelegation.grantee_id.in_(uids)))
            await db.execute(delete(Employee).where(Employee.user_id.in_(uids)))
            await db.execute(delete(Department).where(
                Department.name.in_([dx, dy])))
            tids = (await db.execute(select(ShiftTemplate.id).where(
                ShiftTemplate.name == f"AFT{sfx}"))).scalars().all()
            await purge_shift_templates(db, tids)
            await db.execute(delete(User).where(User.id.in_(uids)))
            await db.commit()


async def _login(client, email):
    r = await client.post(f"{settings.API_V1_STR}/auth/login",
                          data={"username": email, "password": PW})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_api_admin_scope_and_unfilled(client, world):
    h = await _login(client, world["admin"])
    r = await client.post(f"{ROSTER}/autofill/preview", headers=h, json={
        "start": D.isoformat(), "end": D.isoformat(), "department": world["dx"]})
    assert r.status_code == 200, r.text
    j = r.json()
    ids = world["ids"]
    assert sorted(s["employee_id"] for s in j["suggestions"]) == sorted(
        [ids["e1"], ids["e2"]])
    assert j["unfilled"] == []
    assert all(s["shift_template_id"] == ids["t1"] for s in j["suggestions"])
    # other department's requirement is not leaked into this view
    r = await client.post(f"{ROSTER}/autofill/preview", headers=h, json={
        "start": D.isoformat(), "end": D.isoformat(), "department": world["dy"]})
    assert [s["employee_id"] for s in r.json()["suggestions"]] == [ids["e3"]]


async def test_api_delegate_only_own_scope(client, world):
    h = await _login(client, world["deleg"])
    r = await client.post(f"{ROSTER}/autofill/preview", headers=h, json={
        "start": D.isoformat(), "end": D.isoformat()})
    assert r.status_code == 200, r.text
    j = r.json()
    ids = world["ids"]
    assert [s["employee_id"] for s in j["suggestions"]] == [ids["e1"]]
    # e2 is out of scope so the dept-X slot stays 1 short
    assert [(u["missing"]) for u in j["unfilled"]] == [1]


async def test_api_window_cap_and_no_scope(client, world):
    h = await _login(client, world["admin"])
    r = await client.post(f"{ROSTER}/autofill/preview", headers=h, json={
        "start": D.isoformat(), "end": (D + timedelta(days=31)).isoformat()})
    assert r.status_code == 400
    r = await client.post(f"{ROSTER}/autofill/preview", headers=h, json={
        "start": D.isoformat(), "end": (D + timedelta(days=30)).isoformat()})
    assert r.status_code == 200
    # a user with no roster scope
    async with SessionLocal() as db:
        u = User(email=f"af_none_{world['sfx']}@t.com", full_name="n",
                 hashed_password=get_password_hash(PW), is_active=True)
        db.add(u)
        await db.commit()
    h2 = await _login(client, f"af_none_{world['sfx']}@t.com")
    r = await client.post(f"{ROSTER}/autofill/preview", headers=h2, json={
        "start": D.isoformat(), "end": D.isoformat()})
    assert r.status_code == 403
