"""Work-rule + coverage tests (Roadmap v2 Phase 1A, Task 4).
Pure rule tests + DB-backed API tests (cleaned up in teardown)."""
import uuid
from datetime import date, datetime, time, timedelta, timezone
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
from app.models.audit import AuditLog
from app.models.coverage_requirement import CoverageRequirement
from app.models.department import Department
from app.models.employee import Employee, EmployeeStatus
from app.models.roster import RosterEntry, RosterStatus
from app.models.leave import LeaveRequest, LeaveStatus, LeaveType
from app.models.schedule_delegation import DelegationScope, ScheduleDelegation
from app.models.shift import EmployeeShiftAssignment, ShiftTemplate
from app.models.system import SystemSetting
from app.models.user import User
from app.services.schedule_rules import (
    build_spans, check_leave_conflicts, check_rules, compute_coverage,
)
from app.services.roster import resolve_working_template
from app.services.time_rules import (
    get_schedule_rules, get_time_rules, set_time_rules,
)

ROSTER = f"{settings.API_V1_STR}/roster"
PW = "test@12345"
D = date(2030, 1, 7)  # Monday
TODAY = datetime.now(timezone.utc).date()

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


def test_min_rest_uses_running_max_end():
    # long overnight, short nested day shift, then a shift soon after the
    # overnight ends: rest must be measured from the LATEST end.
    t = {1: NS(start_time=time(8), end_time=time(8), is_overnight=True, break_minutes=0),
         2: NS(start_time=time(10), end_time=time(11), is_overnight=False, break_minutes=0),
         3: NS(start_time=time(12), end_time=time(20), is_overnight=False, break_minutes=0)}
    d1 = D + timedelta(days=1)
    s = build_spans([(1, D, 1), (1, D, 2), (1, d1, 3)], t)  # 1 ends d1 08:00
    v = check_rules(s, {**OFF, "min_rest_hours": 11})
    assert any(x.rule == "min_rest" and x.work_date == d1 for x in v)


def test_run_reported_on_first_in_window_day():
    s = spans([(1, D + timedelta(days=i), 3) for i in range(8)])
    r = {**OFF, "max_consecutive_days": 3}
    assert check_rules(s, r)[0].work_date == D + timedelta(days=3)
    v = check_rules(s, r, window_start=D + timedelta(days=5))
    assert len(v) == 1 and v[0].work_date == D + timedelta(days=5)


def test_resolve_working_template():
    tpl = {1: NS(weekly_offs=[2]), 2: NS(weekly_offs=[])}
    asg = [NS(shift_template_id=1, effective_from=D, effective_to=None)]
    ent = lambda t, off: NS(shift_template_id=t, is_week_off=off)  # noqa: E731
    assert resolve_working_template(ent(2, True), asg, tpl, D) is None
    assert resolve_working_template(ent(2, False), asg, tpl, D) == 2
    assert resolve_working_template(ent(None, False), asg, tpl, D) == 1
    assert resolve_working_template(None, asg, tpl, D) == 1
    # Wednesday is the template's weekly off
    assert resolve_working_template(None, asg, tpl, D + timedelta(days=2)) is None
    assert resolve_working_template(None, [], tpl, D) is None


# ----------------------------- API -----------------------------

SCHED_KEYS = ["min_rest_hours", "max_consecutive_days",
              "max_consecutive_nights", "max_weekly_hours"]
BASE_RULES = {"min_rest_hours": 11, "max_consecutive_days": 6,
              "max_consecutive_nights": 4, "max_weekly_hours": 48}


@pytest.fixture
async def rules_cfg():
    """Snapshot the four schedule.* settings (incl. row existence); the
    yielded `apply(**kv)` sets values; originals restored in finally."""
    async with SessionLocal() as db:
        snap = {}
        for k in SCHED_KEYS:
            row = await db.get(SystemSetting, f"schedule.{k}")
            snap[k] = row.value if row else None
    try:
        async def apply(**kv):
            async with SessionLocal() as db:
                await set_time_rules(
                    db, {f"schedule.{k}": str(v) for k, v in kv.items()})
        yield apply
    finally:
        async with SessionLocal() as db:
            for k, v in snap.items():
                row = await db.get(SystemSetting, f"schedule.{k}")
                if v is None:
                    if row:
                        await db.delete(row)
                elif row:
                    row.value = v
                else:
                    db.add(SystemSetting(key=f"schedule.{k}", value=v,
                                         description="restored"))
            await db.commit()


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
    dept, dept2 = f"SR{sfx}", f"SY{sfx}"
    try:
        async with SessionLocal() as db:
            def mk(tag, **kw):
                return User(email=f"sr_{tag}_{sfx}@t.com", full_name=f"SR {tag}",
                            hashed_password=get_password_hash(PW),
                            is_active=True, **kw)
            e1, e2, e3, plain, deleg = (mk("e1"), mk("e2"), mk("e3"),
                                        mk("plain"), mk("deleg"))
            admin = mk("admin", is_superuser=True)
            db.add_all([e1, e2, e3, plain, deleg, admin,
                        Department(name=dept), Department(name=dept2)])
            night = ShiftTemplate(name=f"SRN{sfx}", start_time=time(22),
                                  end_time=time(6), is_overnight=True,
                                  break_minutes=0)
            late = ShiftTemplate(name=f"SRL{sfx}", start_time=time(14),
                                 end_time=time(22), break_minutes=0,
                                 weekly_offs=[2])
            db.add_all([night, late])
            await db.commit()
            for tag, u, d in (("1", e1, dept), ("2", e2, dept), ("3", e3, dept2)):
                db.add(Employee(
                    user_id=u.id, employee_id=f"SR{sfx}{tag}", department=d,
                    designation="T", date_of_joining=date(2020, 1, 1),
                    status=EmployeeStatus.ACTIVE))
            await db.commit()
            ids = {"e1": e1.id, "e2": e2.id, "e3": e3.id, "deleg": deleg.id,
                   "night": night.id, "late": late.id}
        yield {"ids": ids, "dept": dept, "dept2": dept2, "sfx": sfx,
               "admin": f"sr_admin_{sfx}@t.com", "plain": f"sr_plain_{sfx}@t.com",
               "deleg": f"sr_deleg_{sfx}@t.com"}
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
            await db.execute(delete(AuditLog).where(
                AuditLog.action == "UPDATE_TIME_RULES",
                AuditLog.user_id.in_(uids)))
            await db.execute(delete(CoverageRequirement).where(
                CoverageRequirement.id.in_(rids)))
            await db.execute(delete(RosterEntry).where(
                RosterEntry.employee_id.in_(uids)))
            await db.execute(delete(EmployeeShiftAssignment).where(
                EmployeeShiftAssignment.employee_id.in_(uids)))
            await db.execute(delete(LeaveRequest).where(
                LeaveRequest.employee_id.in_(uids)))
            await db.execute(delete(LeaveType).where(
                LeaveType.name == f"SRLV{sfx}"))
            await db.execute(delete(ScheduleDelegation).where(
                ScheduleDelegation.grantee_id.in_(uids)))
            await db.execute(delete(Employee).where(Employee.user_id.in_(uids)))
            await db.execute(delete(Department).where(
                Department.name.in_([dept, dept2])))
            await purge_shift_templates(db, tids)
            await db.execute(delete(User).where(User.id.in_(uids)))
            await db.commit()


async def _login(client, email):
    r = await client.post(f"{settings.API_V1_STR}/auth/login",
                          data={"username": email, "password": PW})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _entries(*rows):
    """rows: (uid, date, tpl_id|None, is_week_off)"""
    async with SessionLocal() as db:
        for uid, d, t, off in rows:
            db.add(RosterEntry(employee_id=uid, work_date=d, shift_template_id=t,
                               is_week_off=off, status=RosterStatus.DRAFT))
        await db.commit()


def _q(start, end, **kw):
    return {"start": start.isoformat(), "end": end.isoformat(), **kw}


async def _insights(client, h, start, end, **kw):
    r = await client.get(f"{ROSTER}/insights", headers=h, params=_q(start, end, **kw))
    assert r.status_code == 200, r.text
    return r.json()


async def test_insights_draft_entries_count(client, world, rules_cfg):
    ids = world["ids"]
    await rules_cfg(**BASE_RULES)
    await _entries((ids["e1"], D, ids["night"], False),
                   (ids["e1"], D + timedelta(days=1), ids["late"], False))
    h = await _login(client, world["admin"])
    j = await _insights(client, h, D, D + timedelta(days=3), department=world["dept"])
    v = [x for x in j["violations"] if x["user_id"] == ids["e1"]]
    assert len(v) == 1 and v[0]["rule"] == "min_rest"
    assert v[0]["work_date"] == (D + timedelta(days=1)).isoformat()
    j = await _insights(client, h, D + timedelta(days=2), D + timedelta(days=3),
                        department=world["dept"])
    assert j["violations"] == []
    hp = await _login(client, world["plain"])
    r = await client.get(f"{ROSTER}/insights", headers=hp, params=_q(D, D))
    assert r.status_code == 403, r.text


async def test_insights_range_errors(client, world):
    h = await _login(client, world["admin"])
    r = await client.get(f"{ROSTER}/insights", headers=h,
                         params=_q(D + timedelta(days=1), D))
    assert r.status_code == 400
    r = await client.get(f"{ROSTER}/insights", headers=h,
                         params=_q(D, D + timedelta(days=63)))
    assert r.status_code == 400


async def test_insights_leave_conflict(client, world, rules_cfg):
    ids = world["ids"]
    await rules_cfg(**BASE_RULES)
    async with SessionLocal() as db:
        lt = LeaveType(name=f"SRLV{world['sfx']}")
        db.add(lt)
        await db.commit()
        for day, half in ((D, False), (D + timedelta(days=1), True)):
            db.add(LeaveRequest(
                employee_id=ids["e1"], leave_type_id=lt.id, start_date=day,
                end_date=day, is_half_day=half, reason="t",
                status=LeaveStatus.APPROVED, created_by_user_id=ids["e1"]))
        await db.commit()
    await _entries((ids["e1"], D, ids["late"], False),
                   (ids["e1"], D + timedelta(days=1), ids["late"], False))
    h = await _login(client, world["admin"])
    j = await _insights(client, h, D, D + timedelta(days=2), department=world["dept"])
    v = [x for x in j["violations"] if x["rule"] == "on_leave"]
    assert [x["work_date"] for x in v] == [D.isoformat()]  # half-day excluded


async def test_assignment_fallback_and_week_off_not_counted(client, world, rules_cfg):
    ids = world["ids"]
    await rules_cfg(**BASE_RULES)
    async with SessionLocal() as db:
        db.add(EmployeeShiftAssignment(
            employee_id=ids["e2"], shift_template_id=ids["late"],
            effective_from=D - timedelta(days=30)))
        await db.commit()
    # Tue: week-off entry that still carries a template -> not working
    await _entries((ids["e2"], D + timedelta(days=1), ids["late"], True))
    h = await _login(client, world["admin"])
    r = await client.post(f"{ROSTER}/coverage-requirements", headers=h, json={
        "department": world["dept"], "shift_template_id": ids["late"],
        "min_headcount": 1})
    assert r.status_code == 200, r.text
    j = await _insights(client, h, D, D + timedelta(days=2), department=world["dept"])
    cov = sorted((c for c in j["coverage"] if c["shift_template_id"] == ids["late"]),
                 key=lambda c: c["date"])
    # Mon: assignment; Tue: week-off entry; Wed: template weekly off
    assert [c["scheduled"] for c in cov] == [1, 0, 0]


async def test_run_started_before_window_reported_in_window(client, world, rules_cfg):
    ids = world["ids"]
    await rules_cfg(**{**BASE_RULES, "max_consecutive_days": 3})
    await _entries(*[(ids["e1"], D + timedelta(days=i), ids["late"], False)
                     for i in range(5)])
    h = await _login(client, world["admin"])
    j = await _insights(client, h, D + timedelta(days=4), D + timedelta(days=6),
                        department=world["dept"])
    v = [x for x in j["violations"]
         if x["rule"] == "max_consecutive_days" and x["user_id"] == ids["e1"]]
    assert [x["work_date"] for x in v] == [(D + timedelta(days=4)).isoformat()]


async def test_coverage_counts_out_of_scope(client, world, rules_cfg):
    ids = world["ids"]
    await rules_cfg(**BASE_RULES)
    async with SessionLocal() as db:
        db.add(ScheduleDelegation(
            grantee_id=ids["deleg"], scope_type=DelegationScope.EMPLOYEES,
            employee_ids=[ids["e1"]], can_publish=False,
            valid_from=TODAY - timedelta(days=1)))
        await db.commit()
    await _entries((ids["e1"], D, ids["late"], False),
                   (ids["e2"], D, ids["late"], False))
    ha = await _login(client, world["admin"])
    for dept in (world["dept"], world["dept2"]):
        r = await client.post(f"{ROSTER}/coverage-requirements", headers=ha, json={
            "department": dept, "shift_template_id": ids["late"],
            "weekday": 0, "min_headcount": 1})
        assert r.status_code == 200, r.text
    hd = await _login(client, world["deleg"])
    # delegate scopes only e1, but e2 (same dept, out of scope) is counted
    j = await _insights(client, hd, D, D)
    mine = [c for c in j["coverage"] if c["shift_template_id"] == ids["late"]]
    assert [(c["department"], c["scheduled"]) for c in mine] == [(world["dept"], 2)]
    # requirement list is scoped too
    r = await client.get(f"{ROSTER}/coverage-requirements", headers=hd)
    depts = {x["department"] for x in r.json()
             if x["shift_template_id"] == ids["late"]}
    assert depts == {world["dept"]}
    r = await client.get(f"{ROSTER}/coverage-requirements", headers=ha)
    assert {world["dept"], world["dept2"]} <= {x["department"] for x in r.json()}
    # admin with department filter still counts everyone in that dept
    j = await _insights(client, ha, D, D, department=world["dept"])
    mine = [c for c in j["coverage"] if c["shift_template_id"] == ids["late"]]
    assert [(c["department"], c["scheduled"]) for c in mine] == [(world["dept"], 2)]


async def test_coverage_crud(client, world):
    ids = world["ids"]
    ha = await _login(client, world["admin"])
    hp = await _login(client, world["plain"])
    body = {"shift_template_id": ids["late"], "min_headcount": 2,
            "department": world["dept"]}
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
    # duplicate active requirement -> 409 (create and via PATCH)
    assert (await client.post(f"{ROSTER}/coverage-requirements", json=body,
                              headers=ha)).status_code == 409
    r2 = await client.post(f"{ROSTER}/coverage-requirements", headers=ha,
                           json={**body, "weekday": 1})
    assert r2.status_code == 200
    assert (await client.patch(f"{ROSTER}/coverage-requirements/{r2.json()['id']}",
                               json={"weekday": None}, headers=ha)
            ).status_code == 409
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
    # after soft-delete the same combination may be re-created
    assert (await client.post(f"{ROSTER}/coverage-requirements", json=body,
                              headers=ha)).status_code == 200


async def test_time_rules_validation_and_caps(client, world, rules_cfg):
    ha = await _login(client, world["admin"])
    url = f"{settings.API_V1_STR}/hr/time-rules"
    await rules_cfg(**BASE_RULES)
    for key, bad in (("min_rest_hours", "abc"), ("min_rest_hours", "-1"),
                     ("min_rest_hours", "1.5"), ("min_rest_hours", ""),
                     ("min_rest_hours", "25"), ("max_consecutive_days", "32"),
                     ("max_consecutive_nights", "32"),
                     ("max_weekly_hours", "169")):
        r = await client.put(url, headers=ha,
                             json={"rules": {f"schedule.{key}": bad}})
        assert r.status_code == 422, (key, bad, r.text)
    async with SessionLocal() as db:
        current = await get_schedule_rules(db)
        assert {k: current[k] for k in BASE_RULES} == BASE_RULES
    r = await client.put(url, headers=ha, json={"rules": {
        "schedule.min_rest_hours": " 24 ", "schedule.max_weekly_hours": "168"}})
    assert r.status_code == 200, r.text
    async with SessionLocal() as db:
        assert (await get_time_rules(db))["schedule.min_rest_hours"] == "24"


async def test_corrupt_stored_value_falls_back(world, rules_cfg):
    await rules_cfg(**BASE_RULES)
    async with SessionLocal() as db:
        row = await db.get(SystemSetting, "schedule.min_rest_hours")
        row.value = "junk"
        await db.commit()
        assert (await get_schedule_rules(db))["min_rest_hours"] == 11
