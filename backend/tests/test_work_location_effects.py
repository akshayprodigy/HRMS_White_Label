"""Phase 6A Task 8: approved work-location requests relax the geofence and
count as present. Real dev DB; everything created here is removed."""
import uuid
from datetime import date, datetime, time, timedelta, timezone

import pytest
from _cleanup import purge_gap_notifications, purge_shift_templates
from _tz import org_today, org_tz_utc  # noqa: F401
from sqlalchemy import delete, select

from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.models.attendance import Attendance
from app.models.audit import AuditLog
from app.models.coverage_gap import CoverageGap
from app.models.department import Department
from app.models.employee import Employee, EmployeeStatus
from app.models.geofence import (
    EmployeeGeoConfig, EmployeeGeoFenceLink, GeoFenceLocation,
)
from app.models.no_show import NoShowAlert
from app.models.leave import HalfDaySession, LeaveRequest, LeaveStatus, LeaveType
from app.models.notification import Notification
from app.models.roster import RosterEntry, RosterEntryHistory, RosterStatus
from app.models.shift import ShiftTemplate
from app.models.system import SystemSetting
from app.models.user import User
from app.models.work_location import WorkLocationRequest
from app.services import live_ops
from app.services.absence_lop import count_absent_days
from app.services.geofence import GeoFlag
from app.services.live_ops import LiveStatus as S, no_show_job
from app.services.punch import PunchRejected, record_punch_in, record_punch_out
from app.services.reports import AttendanceRow, ReportFilter, build_muster_roll

FENCE = (12.9716, 77.5946)
FAR = (12.9716 + 0.045, 77.5946)   # ~5 km north
UTC = timezone.utc
D = date(2030, 6, 10)
NOW = datetime(2030, 6, 10, 10, 0, tzinfo=UTC)
RULE_KEY = "schedule.no_show_minutes"


@pytest.fixture
async def world():
    sfx = uuid.uuid4().hex[:8]
    dept = f"WE{sfx}"
    async with SessionLocal() as db:
        prior = await db.get(SystemSetting, RULE_KEY)
        prior_val = (prior.value, prior.description) if prior else None
    try:
        async with SessionLocal() as db:
            us = {t: User(email=f"wle_{t}_{sfx}@test.com", full_name=f"WE {t}",
                          hashed_password=get_password_hash("x"),
                          is_active=True)
                  for t in ("strict", "full", "half", "none", "mock", "flagmode")}
            db.add_all(us.values())
            db.add(Department(name=dept))
            tpl = ShiftTemplate(name=f"WET{sfx}", start_time=time(9),
                                end_time=time(17), grace_in_minutes=10)
            fence = GeoFenceLocation(
                name=f"WEF{sfx}", latitude=FENCE[0], longitude=FENCE[1],
                radius_meters=200, is_active=True)
            db.add_all([tpl, fence])
            await db.commit()
            for t, u in us.items():
                db.add(Employee(
                    user_id=u.id, employee_id=f"WE{sfx}{t}", department=dept,
                    designation="T", date_of_joining=date(2020, 1, 1),
                    status=EmployeeStatus.ACTIVE))
                if t in ("strict", "mock", "flagmode"):
                    db.add(EmployeeGeoConfig(
                        user_id=u.id, geo_enabled=True,
                        enforcement_mode=("allow_with_flag"
                                          if t == "flagmode" else "strict")))
            await db.commit()
            for t in ("strict", "mock", "flagmode"):
                db.add(EmployeeGeoFenceLink(
                    user_id=us[t].id, geofence_location_id=fence.id))
            await db.commit()
            ids = {t: u.id for t, u in us.items()}
            ids["tpl"] = tpl.id
        yield {"ids": ids, "sfx": sfx, "dept": dept}
    finally:
        async with SessionLocal() as db:
            uids = list((await db.execute(select(User.id).where(
                User.email.like(f"wle\\_%\\_{sfx}@test.com")))).scalars().all())
            tids = list((await db.execute(select(ShiftTemplate.id).where(
                ShiftTemplate.name == f"WET{sfx}"))).scalars().all())
            await purge_gap_notifications(db, tids)
            await db.execute(delete(CoverageGap).where(
                CoverageGap.shift_template_id.in_(tids)))
            aids = [str(i) for i in (await db.execute(select(Attendance.id).where(
                Attendance.user_id.in_(uids)))).scalars().all()]
            if aids:
                await db.execute(delete(Notification).where(
                    Notification.resource_type == "attendance",
                    Notification.resource_id.in_(aids)))
                await db.execute(delete(AuditLog).where(
                    AuditLog.resource_type == "attendance",
                    AuditLog.resource_id.in_(aids)))
            await db.execute(delete(NoShowAlert).where(
                NoShowAlert.user_id.in_(uids)))
            await db.execute(delete(Notification).where(
                Notification.user_id.in_(uids)))
            await db.execute(delete(Notification).where(
                Notification.message.like(f"%{sfx}%")))
            await db.execute(delete(AuditLog).where(AuditLog.user_id.in_(uids)))
            await db.execute(delete(Attendance).where(
                Attendance.user_id.in_(uids)))
            await db.execute(delete(WorkLocationRequest).where(
                WorkLocationRequest.user_id.in_(uids)))
            await db.execute(delete(LeaveRequest).where(
                LeaveRequest.employee_id.in_(uids)))
            await db.execute(delete(LeaveType).where(
                LeaveType.name == f"WEL{sfx}"))
            await db.execute(delete(EmployeeGeoFenceLink).where(
                EmployeeGeoFenceLink.user_id.in_(uids)))
            await db.execute(delete(EmployeeGeoConfig).where(
                EmployeeGeoConfig.user_id.in_(uids)))
            await db.execute(delete(GeoFenceLocation).where(
                GeoFenceLocation.name == f"WEF{sfx}"))
            await db.execute(delete(RosterEntryHistory).where(
                RosterEntryHistory.employee_id.in_(uids)))
            await db.execute(delete(RosterEntry).where(
                RosterEntry.employee_id.in_(uids)))
            await db.execute(delete(Employee).where(Employee.user_id.in_(uids)))
            await db.execute(delete(Department).where(Department.name == dept))
            await purge_shift_templates(db, tids)
            await db.execute(delete(User).where(User.id.in_(uids)))
            await db.execute(delete(SystemSetting).where(
                SystemSetting.key == RULE_KEY))
            if prior_val is not None:
                db.add(SystemSetting(key=RULE_KEY, value=prior_val[0],
                                     description=prior_val[1]))
            await db.commit()


async def _approve(uid, kind="wfh", portion="full", d=None):
    async with SessionLocal() as db:
        db.add(WorkLocationRequest(
            user_id=uid, kind=kind, start_date=d or org_today(),
            end_date=d or org_today(), day_portion=portion,
            place="X" if kind != "wfh" else None, purpose="t",
            status="approved"))
        await db.commit()


async def _punch(uid, pt, **kw):
    async with SessionLocal() as db:
        user = await db.get(User, uid)
        try:
            row, _ = await record_punch_in(
                db, user, lat=pt[0], lng=pt[1], accuracy=10.0, **kw)
            await db.commit()
            return row
        except PunchRejected:
            await db.rollback()
            raise


# ---------------- punch ----------------

async def test_strict_fence_rejects_without_approval(world):
    with pytest.raises(PunchRejected) as e:
        await _punch(world["ids"]["strict"], FAR)
    assert e.value.status_code == 422


async def test_strict_fence_relaxed_with_approval(world):
    uid = world["ids"]["strict"]
    await _approve(uid, "wfh", "full")
    row = await _punch(uid, FAR)
    assert row.geo_flag == "approved_remote"
    # punch-out also relaxed, and no geo notification is sent
    async with SessionLocal() as db:
        user = await db.get(User, uid)
        att = await record_punch_out(db, user, lat=FAR[0], lng=FAR[1],
                                     accuracy=10.0)
        assert att.punch_out_geo_flag == "approved_remote"
        await db.commit()
    async with SessionLocal() as db:
        notes = (await db.execute(select(Notification).where(
            Notification.message.like("%Geo-flagged%"),
            Notification.message.like(f"%WE strict%")))).scalars().all()
        assert notes == []


async def test_half_day_approval_counts_for_whole_day(world):
    uid = world["ids"]["strict"]
    await _approve(uid, "on_duty", "second_half")
    assert (await _punch(uid, FAR)).geo_flag == "approved_remote"


async def test_inside_fence_with_approval_stays_clean(world):
    uid = world["ids"]["strict"]
    await _approve(uid, "wfh", "full")
    assert (await _punch(uid, FENCE)).geo_flag is None


async def test_mock_location_still_strict_with_approval(world):
    uid = world["ids"]["mock"]     # strict fence
    await _approve(uid, "wfh", "full")
    with pytest.raises(PunchRejected):
        await _punch(uid, FAR, is_mock=True)


async def test_mock_location_flag_mode_keeps_mock_flag(world):
    uid = world["ids"]["flagmode"]
    await _approve(uid, "wfh", "full")
    row = await _punch(uid, FAR, is_mock=True)
    assert row.geo_flag == GeoFlag.MOCK_LOCATION.value


async def test_approved_remote_excluded_from_flagged_queue(world):
    from httpx import ASGITransport, AsyncClient
    from app.api import deps
    from app.main import create_app
    uid = world["ids"]["strict"]
    async with SessionLocal() as db:
        db.add(User(email=f"wle_su_{world['sfx']}@test.com", full_name="su",
                    hashed_password=get_password_hash("x"), is_active=True,
                    is_superuser=True))
        await db.commit()
    await _approve(uid, "wfh", "full")
    await _punch(uid, FAR)
    app = create_app()
    app.dependency_overrides[deps.verify_attendance] = lambda: None
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as c:
        r = await c.post("/api/v1/auth/login", data={
            "username": f"wle_su_{world['sfx']}@test.com", "password": "x"})
        h = {"Authorization": f"Bearer {r.json()['access_token']}"}
        t = org_today().isoformat()
        q = {"date_from": t, "date_to": t, "flag_kind": "geo"}
        r = await c.get("/api/v1/attendance/flagged", headers=h, params=q)
        assert r.status_code == 200, r.text
        assert uid not in [x["user_id"] for x in r.json()]
        r = await c.get("/api/v1/attendance/flagged", headers=h,
                        params={**q, "geo_flag": "approved_remote"})
        assert uid in [x["user_id"] for x in r.json()]


# ---------------- absence LOP ----------------

def _lop(remote, **kw):
    base = dict(user_id=1, shifts={}, default_offs={6}, punched=set(),
                full_leave=set(), half_leave=set(), holidays={},
                remote=remote)
    base.update(kw)
    return count_absent_days(first=D, last=D, **base)


def test_absence_remote_full_half_and_half_leave():
    assert _lop({}) == 1.0
    assert _lop({D: "full"}) == 0.0
    assert _lop({D: "first_half"}) == 0.5
    assert _lop({D: "second_half"}, half_leave={(1, D)}) == 0.0
    assert _lop({D: "full"}, half_leave={(1, D)}) == 0.0


async def test_absence_days_for_period_batched(world):
    from app.services.absence_lop import absence_days_for_period
    i = world["ids"]
    await _approve(i["full"], "wfh", "full", D)
    await _approve(i["half"], "wfh", "first_half", D)
    async with SessionLocal() as db:
        emps = list((await db.execute(select(Employee).where(
            Employee.user_id.in_([i["full"], i["half"], i["none"]])))).scalars())
        res = await absence_days_for_period(
            db, emps, D, D, D + timedelta(days=1), {6})
    assert res[i["full"]] == 0.0
    assert res[i["half"]] == 0.5
    assert res[i["none"]] == 1.0


# ---------------- no-show / board ----------------

async def test_no_show_skips_full_remote_flags_half(world):
    i = world["ids"]
    async with SessionLocal() as db:
        row = await db.get(SystemSetting, RULE_KEY)
        if row is None:
            db.add(SystemSetting(key=RULE_KEY, value="30", description="t"))
        else:
            row.value = "30"
        for t in ("full", "half", "none"):
            db.add(RosterEntry(employee_id=i[t], work_date=D,
                               shift_template_id=i["tpl"],
                               status=RosterStatus.PUBLISHED))
        await db.commit()
    await _approve(i["full"], "client_visit", "full", D)
    await _approve(i["half"], "wfh", "first_half", D)
    ids = [i["full"], i["half"], i["none"]]
    async with SessionLocal() as db:
        board = {r.user_id: r for r in await live_ops.live_board(db, ids, NOW)}
        assert board[i["full"]].remote_kind == "client_visit"
        assert board[i["half"]].remote_kind == "wfh"
        assert board[i["none"]].remote_kind is None
        assert board[i["half"]].status == S.NO_SHOW
        assert board[i["full"]].status == S.REMOTE
        assert board[i["full"]].remote_portion == "full"
        assert board[i["half"]].remote_portion == "first_half"
        await no_show_job(db, now=NOW, user_ids=ids)
    async with SessionLocal() as db:
        alerted = {a.user_id for a in (await db.execute(select(NoShowAlert).where(
            NoShowAlert.user_id.in_(ids)))).scalars()}
    assert alerted == {i["half"], i["none"]}


# ---------------- muster ----------------

def _row(**kw):
    base = dict(user_id=1, employee_code="E", full_name="N", department="D",
                work_date=D)
    base.update(kw)
    return AttendanceRow(**base)


def test_muster_codes():
    recs = [
        _row(remote_kind="on_duty", remote_portion="full"),
        _row(remote_kind="client_visit", remote_portion="full"),
        _row(remote_kind="wfh", remote_portion="full"),
        _row(remote_kind="on_duty", remote_portion="second_half"),
        _row(remote_kind="wfh", remote_portion="first_half"),
        _row(remote_kind="wfh", remote_portion="full",
             punch_in=datetime(2030, 6, 10, 9)),
        _row(remote_kind="client_visit", remote_portion="first_half",
             punch_in=datetime(2030, 6, 10, 9)),
        _row(),
    ]
    r = build_muster_roll(records=recs, filters=ReportFilter())
    assert [x["status"] for x in r.rows] == [
        "OD", "OD", "WFH", "OD/2", "WFH/2", "P·WFH", "P·OD", "A"]
    # suffixed rows still count as present
    assert "P=2" in r.totals["status"] and "A=1" in r.totals["status"]


def _org_today(monkeypatch, d):
    """Pin the org-local 'today' the muster/coverage fetchers see."""
    async def fake(db):
        return d
    monkeypatch.setattr("app.api.v1.endpoints.reports.local_today", fake)


async def test_muster_fetch_adds_no_punch_remote_rows(world, monkeypatch):
    from app.api.v1.endpoints.reports import _fetch_muster_roll
    _org_today(monkeypatch, D + timedelta(days=30))
    i = world["ids"]
    await _approve(i["full"], "on_duty", "full", D)
    await _approve(i["half"], "wfh", "second_half", D)
    f = ReportFilter(start=D, end=D, department=world["dept"])
    async with SessionLocal() as db:
        res = await _fetch_muster_roll(db, f)
    by = {x["user_id"]: x["status"] for x in res.rows}
    assert by == {i["full"]: "OD", i["half"]: "WFH/2"}


async def test_muster_fetch_skips_future_dates(world, monkeypatch):
    from app.api.v1.endpoints.reports import _fetch_muster_roll
    i = world["ids"]
    await _approve(i["full"], "on_duty", "full", D)
    f = ReportFilter(start=D, end=D, department=world["dept"])
    _org_today(monkeypatch, D - timedelta(days=1))     # D is still ahead
    async with SessionLocal() as db:
        assert (await _fetch_muster_roll(db, f)).rows == []
    _org_today(monkeypatch, D)                          # today counts
    async with SessionLocal() as db:
        assert len((await _fetch_muster_roll(db, f)).rows) == 1


async def test_muster_fetch_skips_off_days(world, monkeypatch):
    from app.api.v1.endpoints.reports import _fetch_muster_roll
    _org_today(monkeypatch, date(2030, 12, 31))
    i = world["ids"]
    fri = date(2030, 6, 7)          # Fri; Sat is a roster week-off, Sun default
    async with SessionLocal() as db:
        for n in (0, 1, 3):         # Sunday: no roster -> default weekly off
            d = fri + timedelta(days=n)
            db.add(RosterEntry(
                employee_id=i["full"], work_date=d,
                shift_template_id=None if n == 1 else i["tpl"],
                is_week_off=(n == 1), status=RosterStatus.PUBLISHED))
        db.add(WorkLocationRequest(
            user_id=i["full"], kind="wfh", start_date=fri,
            end_date=fri + timedelta(days=3), day_portion="full",
            purpose="t", status="approved"))
        await db.commit()
    f = ReportFilter(start=fri, end=fri + timedelta(days=3),
                     department=world["dept"])
    async with SessionLocal() as db:
        res = await _fetch_muster_roll(db, f)
    got = sorted((x["work_date"], x["status"]) for x in res.rows)
    assert got == [(fri, "WFH"), (fri + timedelta(days=3), "WFH")]


async def _att(uid, d, tpl=None):
    async with SessionLocal() as db:
        db.add(Attendance(
            user_id=uid, mode="web", work_date=d, shift_template_id=tpl,
            captured_at=datetime.combine(d, time(9, 5), UTC)))
        await db.commit()


async def test_muster_fetch_punch_and_remote_day_coexist(world):
    from app.api.v1.endpoints.reports import _fetch_muster_roll
    i = world["ids"]
    await _approve(i["full"], "wfh", "full", D)
    await _att(i["full"], D, i["tpl"])
    f = ReportFilter(start=D, end=D, department=world["dept"])
    async with SessionLocal() as db:
        res = await _fetch_muster_roll(db, f)
    assert [(x["user_id"], x["status"]) for x in res.rows] == [
        (i["full"], "P·WFH")]


async def test_muster_fetch_shift_filter_still_suffixes_punched(world):
    from app.api.v1.endpoints.reports import _fetch_muster_roll
    i = world["ids"]
    await _approve(i["full"], "on_duty", "full", D)
    await _approve(i["half"], "wfh", "full", D)       # no punch: not synthesized
    await _att(i["full"], D, i["tpl"])
    f = ReportFilter(start=D, end=D, department=world["dept"],
                     shift_template_id=i["tpl"])
    async with SessionLocal() as db:
        res = await _fetch_muster_roll(db, f)
    assert [(x["user_id"], x["status"]) for x in res.rows] == [
        (i["full"], "P·OD")]


async def test_muster_synthesis_clipped_by_leave_and_joining(
        world, monkeypatch):
    _org_today(monkeypatch, D)      # D is in the future; the muster skips those
    from app.api.v1.endpoints.reports import _fetch_muster_roll
    i = world["ids"]
    await _approve(i["full"], "wfh", "full", D)       # also on full leave
    await _approve(i["half"], "wfh", "full", D)       # joins after D
    await _approve(i["none"], "wfh", "full", D)       # control
    async with SessionLocal() as db:
        lt = LeaveType(name=f"WEL{world['sfx']}")
        db.add(lt)
        await db.flush()
        db.add(LeaveRequest(
            employee_id=i["full"], leave_type_id=lt.id, start_date=D,
            end_date=D, is_half_day=False, reason="t",
            status=LeaveStatus.APPROVED, created_by_user_id=i["full"]))
        emp = (await db.execute(select(Employee).where(
            Employee.user_id == i["half"]))).scalar_one()
        emp.date_of_joining = D + timedelta(days=1)
        await db.commit()
    f = ReportFilter(start=D, end=D, department=world["dept"])
    async with SessionLocal() as db:
        res = await _fetch_muster_roll(db, f)
    assert [(x["user_id"], x["status"]) for x in res.rows] == [
        (i["none"], "WFH")]


async def test_overnight_punch_out_next_day_stays_relaxed(world):
    uid = world["ids"]["strict"]
    await _approve(uid, "wfh", "full")
    row = await _punch(uid, FAR)
    # Punch-out is evaluated against the open row's work_date, not the
    # calendar date of the punch-out: simulate it landing a day later.
    async with SessionLocal() as db:
        user = await db.get(User, uid)
        att = await db.get(Attendance, row.id)
        out = await record_punch_out(
            db, user, at=datetime.now(UTC) + timedelta(hours=20),
            lat=FAR[0], lng=FAR[1], accuracy=10.0)
        assert att.work_date == org_today()
        assert out.punch_out_geo_flag == "approved_remote"
        await db.commit()


async def test_dashboard_and_flag_summary_exclude_approved_remote(world):
    from app.api.v1.endpoints.dashboard import _wp_hr_flagged_attendance
    from app.api.v1.endpoints.reports import _fetch_flag_summary
    uid = world["ids"]["strict"]
    today = org_today()
    async with SessionLocal() as db:
        before = (await _wp_hr_flagged_attendance(db, None, None))
    await _approve(uid, "wfh", "full")
    row = await _punch(uid, FAR)
    assert row.geo_flag == "approved_remote"
    async with SessionLocal() as db:
        # attribution flag may also be set (no shift): clear it so only the
        # geo dimension could count this row
        a = await db.get(Attendance, row.id)
        a.attribution_flag = None
        await db.commit()
    async with SessionLocal() as db:
        after = (await _wp_hr_flagged_attendance(db, None, None))
        assert after["count"] == before["count"]
        assert after["geo_in"] == before["geo_in"]
        res = await _fetch_flag_summary(
            db, ReportFilter(start=today, end=today))
    assert uid not in [r["user_id"] for r in res.rows]
