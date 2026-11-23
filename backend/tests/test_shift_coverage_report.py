"""Phase 6A Task 9: shift-coverage report. Pure-function tests need no DB;
the rest use the real dev DB with a unique suffix and full teardown."""
import uuid
from datetime import date, time, timedelta
from types import SimpleNamespace

import pytest
from _tz import org_today  # noqa: E402
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from app.api import deps
from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.main import create_app
from app.models.attendance import Attendance
from app.models.coverage_requirement import CoverageRequirement
from app.models.employee import Employee
from app.models.roster import RosterEntry
from app.models.shift import ShiftTemplate
from app.models.department import Department
from app.models.user import Role, User
from app.api.v1.endpoints import reports as EP
from app.services import report_catalog as RC
from app.services import reports as R

MON = date(2020, 1, 6)       # a Monday far in the past
TUE, WED, THU = (MON + timedelta(days=i) for i in (1, 2, 3))


# ---------------- pure (no DB) ----------------

def _req(id, wd=None, dept=None, loc=None, tid=1, mn=2, mx=3):
    return SimpleNamespace(id=id, weekday=wd, department=dept, location=loc,
                           shift_template_id=tid, min_headcount=mn,
                           max_headcount=mx)


def test_select_requirements_weekday_beats_generic():
    gen, wed = _req(1), _req(2, wd=2, mn=1)
    assert R.select_requirements([gen, wed], WED) == [wed]
    assert R.select_requirements([wed, gen], WED) == [wed]
    assert R.select_requirements([gen, wed], MON) == [gen]


def test_select_requirements_keeps_distinct_scopes():
    a, b = _req(1, dept="A"), _req(2, dept="B")
    assert {r.id for r in R.select_requirements([a, b], MON)} == {1, 2}


def test_status_and_fill():
    st = R.coverage_status
    kw = dict(required_min=2, required_max=3, future=False)
    assert st(scheduled=0, attended=1, **kw) == "understaffed"
    assert st(scheduled=0, attended=2, **kw) == "met"
    assert st(scheduled=0, attended=3, **kw) == "met"
    assert st(scheduled=0, attended=4, **kw) == "over"
    assert st(scheduled=0, attended=0, required_min=None,
              required_max=None, future=False) == "no_requirement"
    assert st(scheduled=1, attended=None, required_min=2,
              required_max=None, future=True) == "understaffed_plan"
    assert st(scheduled=2, attended=None, required_min=2,
              required_max=None, future=True) == "planned_ok"
    assert R.coverage_fill_pct(scheduled=0, attended=1, required_min=2,
                               future=False) == 50
    assert R.coverage_fill_pct(scheduled=3, attended=None, required_min=2,
                               future=True) == 150
    assert R.coverage_fill_pct(scheduled=3, attended=1, required_min=0,
                               future=False) is None


def test_catalog_entry():
    d = {x.key: x for x in RC.build_descriptors_no_fetchers()}
    sc, mr = d["shift_coverage"], d["muster_roll"]
    assert sc.permission == mr.permission
    assert {f.key for f in sc.filters} == {
        "start", "end", "department", "location"}


def _b(reqs, sched, att, start=MON, end=MON, today=date(2030, 1, 1), **kw):
    return R.build_shift_coverage(
        reqs, sched, att, {1: "S"}, start, end, today, **kw).rows


def test_builder_each_requirement_counts_its_own_scope():
    reqs = [_req(1, dept="A"), _req(2)]            # dept-A and org-wide
    att = [(MON, 1, 10, "A", "X"), (MON, 1, 11, "A", "X"),
           (MON, 1, 12, "B", "X")]
    rows = {r["department"]: r for r in _b(reqs, [], att)}
    assert rows["A"]["attended"] == 2
    assert rows[None]["attended"] == 3
    assert len(rows) == 2           # nobody left over, no extra row


def test_builder_leftover_no_requirement_row():
    reqs = [_req(1, dept="A")]
    att = [(MON, 1, 10, "A", "X"), (MON, 1, 12, "B", "X"),
           (MON, 1, 13, "B", "X")]
    rows = _b(reqs, [], att)
    nr = [r for r in rows if r["status"] == "no_requirement"]
    assert len(nr) == 1 and nr[0]["attended"] == 2
    # filter narrows leftovers; scoped viewers only see their departments
    assert not [r for r in _b(reqs, [], att, department="A")
                if r["status"] == "no_requirement"]
    assert not [r for r in _b(reqs, [], att, leftover_departments={"A"})
                if r["status"] == "no_requirement"]
    assert len([r for r in _b(reqs, [], att, leftover_departments={"B"})
                if r["status"] == "no_requirement"]) == 1


def test_builder_future_uses_plan_and_totals_not_in_totals():
    sched = [(MON, 1, 10, "A", "X")]
    res = R.build_shift_coverage([_req(1)], sched, [], {1: "S"}, MON, MON,
                                 date(2019, 1, 1))
    assert res.rows[0]["status"] == "understaffed_plan"
    assert res.rows[0]["attended"] is None
    assert res.totals == {} and res.meta["understaffed_count"] == 1


# ---------------- DB-backed ----------------

async def _cleanup(sfx):
    async with SessionLocal() as db:
        uids = list((await db.execute(select(User.id).where(
            User.email.like(f"cov\\_%\\_{sfx}@test.com")))).scalars().all())
        tids = list((await db.execute(select(ShiftTemplate.id).where(
            ShiftTemplate.name == f"COV{sfx}"))).scalars().all())
        if tids:
            await db.execute(delete(Attendance).where(
                Attendance.shift_template_id.in_(tids)))
            await db.execute(delete(RosterEntry).where(
                RosterEntry.shift_template_id.in_(tids)))
            await db.execute(delete(CoverageRequirement).where(
                CoverageRequirement.shift_template_id.in_(tids)))
        if uids:
            await db.execute(delete(Attendance).where(Attendance.user_id.in_(uids)))
            await db.execute(delete(RosterEntry).where(
                RosterEntry.employee_id.in_(uids)))
            await db.execute(delete(Employee).where(Employee.user_id.in_(uids)))
            await db.execute(delete(User).where(User.id.in_(uids)))
        if tids:
            await db.execute(delete(ShiftTemplate).where(ShiftTemplate.id.in_(tids)))
        await db.commit()


@pytest.fixture
async def world():
    sfx = uuid.uuid4().hex[:8]
    w = {"sfx": sfx, "da": f"CDA{sfx}", "db": f"CDB{sfx}", "u": []}
    try:
        async with SessionLocal() as db:
            t = ShiftTemplate(name=f"COV{sfx}", start_time=time(9),
                              end_time=time(17))
            db.add(t)
            await db.flush()
            w["tid"] = t.id
            for i in range(6):
                u = User(email=f"cov_u{i}_{sfx}@test.com", full_name=f"Cov {i}",
                         hashed_password=get_password_hash("x"), is_active=True)
                db.add(u)
                await db.flush()
                db.add(Employee(
                    user_id=u.id, employee_id=f"CV{sfx[:5]}{i}",
                    department=w["da"] if i < 4 else w["db"],
                    designation="T", date_of_joining=date(2019, 1, 1),
                    location="LX" if i < 4 else "LY"))
                w["u"].append(u.id)
            u = User(email=f"cov_su_{sfx}@test.com", full_name="Cov su",
                     hashed_password=get_password_hash("x"), is_active=True,
                     is_superuser=True)
            db.add(u)
            await db.commit()
        yield w
    finally:
        await _cleanup(sfx)


async def _add(*objs):
    async with SessionLocal() as db:
        db.add_all(objs)
        await db.commit()


def _req_row(w, **kw):
    kw.setdefault("min_headcount", 2)
    kw.setdefault("max_headcount", 3)
    return CoverageRequirement(shift_template_id=w["tid"], is_active=True, **kw)


def _att(w, i, d):
    return Attendance(user_id=w["u"][i], mode="web", work_date=d,
                      shift_template_id=w["tid"])


def _ros(w, i, d, **kw):
    return RosterEntry(employee_id=w["u"][i], work_date=d,
                       shift_template_id=w["tid"], **kw)


ADMIN = SimpleNamespace(is_superuser=True, roles=[])


async def _run(w, start, end, department=None, location=None, viewer=ADMIN):
    extras = {"location": location} if location else {}
    if viewer is not None:
        extras["_viewer"] = viewer
    f = R.ReportFilter(start=start, end=end, department=department,
                       extras=extras)
    async with SessionLocal() as db:
        res = await EP._fetch_shift_coverage(db, f)
    return [r for r in res.rows if r["shift_template_id"] == w["tid"]]


async def test_understaffed_met_over(world):
    w = world
    await _add(
        _req_row(w),
        _att(w, 0, MON),
        _att(w, 0, TUE), _att(w, 1, TUE),
        *[_att(w, i, WED) for i in range(4)],
        # D1 roster: 2 published + a week-off + a draft (both excluded)
        _ros(w, 0, MON), _ros(w, 1, MON),
        RosterEntry(employee_id=w["u"][2], work_date=MON,
                    shift_template_id=None, is_week_off=True),
        _ros(w, 3, MON, status="draft"),
    )
    rows = {r["date"]: r for r in await _run(w, MON, WED)}
    assert rows[MON]["status"] == "understaffed"
    assert rows[MON]["attended"] == 1 and rows[MON]["fill_pct"] == 50
    assert rows[MON]["scheduled"] == 2
    assert rows[MON]["required_min"] == 2 and rows[MON]["required_max"] == 3
    assert rows[TUE]["status"] == "met" and rows[TUE]["fill_pct"] == 100
    assert rows[WED]["status"] == "over" and rows[WED]["fill_pct"] == 200
    assert rows[WED]["shift_name"] == f"COV{w['sfx']}"


async def test_weekday_override(world):
    w = world
    await _add(
        _req_row(w),
        _req_row(w, weekday=2, min_headcount=1, max_headcount=5),
        *[_att(w, i, WED) for i in range(4)],
        *[_att(w, i, THU) for i in range(4)],
    )
    rows = {r["date"]: r for r in await _run(w, WED, THU)}
    assert rows[WED]["required_min"] == 1 and rows[WED]["status"] == "met"
    assert rows[THU]["required_min"] == 2 and rows[THU]["status"] == "over"
    assert len([r for r in await _run(w, WED, WED)]) == 1


async def test_department_filter_picks_requirements(world):
    w = world
    await _add(_req_row(w, department=w["da"]),
               _req_row(w, department=w["db"]),
               _att(w, 0, THU), _att(w, 1, THU), _att(w, 4, THU),
               _att(w, 5, THU))
    allr = {r["department"]: r for r in await _run(w, THU, THU)}
    assert allr[w["da"]]["attended"] == 2 and allr[w["db"]]["attended"] == 2
    only_a = await _run(w, THU, THU, department=w["da"])
    assert [r["department"] for r in only_a] == [w["da"]]
    assert only_a[0]["attended"] == 2


async def test_org_wide_requirement_counts_whole_org_under_filter(world):
    w = world
    await _add(_req_row(w), _att(w, 0, THU), _att(w, 1, THU), _att(w, 4, THU))
    rows = await _run(w, THU, THU, department=w["da"])
    assert rows[0]["department"] is None and rows[0]["attended"] == 3
    assert rows[0]["status"] == "over"


async def test_uncovered_department_gets_no_requirement_row(world):
    w = world
    await _add(_req_row(w, department=w["da"]), _att(w, 0, THU),
               _att(w, 4, THU), _att(w, 5, THU))
    rows = await _run(w, THU, THU)
    scoped = [r for r in rows if r["department"] == w["da"]][0]
    assert scoped["attended"] == 1 and scoped["status"] == "understaffed"
    nr = [r for r in rows if r["status"] == "no_requirement"]
    assert len(nr) == 1 and nr[0]["attended"] == 2


async def _viewer(uid):
    async with SessionLocal() as db:
        return (await db.execute(select(User).where(User.id == uid).options(
            selectinload(User.roles).selectinload(Role.permissions)
        ))).scalars().one()


async def test_scoped_viewer_sees_only_headed_departments(world):
    w = world
    async with SessionLocal() as db:
        db.add(Department(name=w["da"], head_user_id=w["u"][5]))
        await db.commit()
    await _add(_req_row(w, department=w["da"]),
               _req_row(w, department=w["db"]),
               _att(w, 0, THU), _att(w, 4, THU), _att(w, 5, THU))
    try:
        v = await _viewer(w["u"][5])
        rows = await _run(w, THU, THU, viewer=v)
        assert {r["department"] for r in rows
                if r["status"] != "no_requirement"} == {w["da"]}
        # dept-B attendance is outside the viewer's headed departments
        assert [r for r in rows if r["status"] == "no_requirement"] == []
        # HR (no 'roster manage') sees every requirement, like muster_roll
        hr = SimpleNamespace(is_superuser=False, roles=[
            SimpleNamespace(name="HR", permissions=[])])
        assert {r["department"] for r in await _run(w, THU, THU, viewer=hr)
                if r["status"] != "no_requirement"} == {w["da"], w["db"]}
        # no viewer at all fails closed
        assert await _run(w, THU, THU, viewer=None) == []
        # a viewer who heads nothing sees no rows at all
        v2 = await _viewer(w["u"][4])
        assert await _run(w, THU, THU, viewer=v2) == []
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(Department).where(
                Department.name == w["da"]))
            await db.commit()


async def test_future_dates_use_plan(world):
    w = world
    f1 = org_today() + timedelta(days=400)
    f2 = f1 + timedelta(days=1)
    await _add(_req_row(w), _ros(w, 0, f1), _ros(w, 1, f1), _ros(w, 2, f1),
               _ros(w, 0, f2))
    rows = {r["date"]: r for r in await _run(w, f1, f2)}
    assert rows[f1]["attended"] is None and rows[f1]["scheduled"] == 3
    assert rows[f1]["status"] == "planned_ok" and rows[f1]["fill_pct"] == 150
    assert rows[f2]["status"] == "understaffed_plan"
    assert rows[f2]["fill_pct"] == 50


async def test_no_requirement(world):
    w = world
    await _add(_att(w, 0, MON))
    rows = await _run(w, MON, MON)
    assert rows[0]["status"] == "no_requirement"
    assert rows[0]["required_min"] is None and rows[0]["fill_pct"] is None


async def test_range_limit_422(world):
    async with SessionLocal() as db:
        ok = await EP._fetch_shift_coverage(db, R.ReportFilter(
            start=MON, end=MON + timedelta(days=61)))
        assert ok is not None  # 62 days inclusive is allowed
        with pytest.raises(HTTPException) as ei:
            await EP._fetch_shift_coverage(db, R.ReportFilter(
                start=MON, end=MON + timedelta(days=62)))
        assert ei.value.status_code == 422


async def test_endpoint_422_and_export(world):
    w = world
    await _add(_req_row(w), _att(w, 0, MON))
    app = create_app()
    app.dependency_overrides[deps.verify_attendance] = lambda: None
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as c:
        r = await c.post("/api/v1/auth/login", data={
            "username": f"cov_su_{w['sfx']}@test.com", "password": "x"})
        h = {"Authorization": f"Bearer {r.json()['access_token']}"}
        url = "/api/v1/reports/run/shift_coverage"
        bad = await c.post(url, headers=h, json={
            "start": MON.isoformat(),
            "end": (MON + timedelta(days=62)).isoformat()})
        assert bad.status_code == 422
        good = {"start": MON.isoformat(), "end": MON.isoformat(),
                "department": w["da"]}
        ok = await c.post(url, headers=h, json=good)
        assert ok.status_code == 200, ok.text
        csv = await c.post(url + "?format=csv", headers=h, json=good)
        assert csv.status_code == 200 and "Fill %" in csv.text
