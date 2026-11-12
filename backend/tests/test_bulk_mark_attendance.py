"""Supervisor bulk mark-present fallback (Roadmap v2 Phase 2, Task 9)."""
import uuid
from datetime import date, datetime, time, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, insert, select

from _cleanup import purge_gap_notifications, purge_shift_templates
from app.api import deps
from app.core.config import settings
from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.main import create_app
from app.models.attendance import Attendance
from app.models.audit import AuditLog
from app.models.coverage_gap import CoverageGap, GapSource, GapStatus
from app.models.department import Department
from app.models.employee import Employee, EmployeeStatus
from app.models.notification import Notification
from app.models.payroll import PayrollRun, PayrollRunStatus
from app.models.roster import RosterEntry, RosterEntryHistory, RosterStatus
from app.models.shift import ShiftTemplate
from app.models.user import (
    Permission, Role, User, role_permissions, user_roles,
)
from app.models.open_shift import OpenShift, OpenShiftStatus
from app.services import coverage_gaps as gap_svc
from app.services.manual_attendance import (
    ManualAttendanceExists, create_manual_attendance_row,
)
from fastapi import HTTPException

API = f"{settings.API_V1_STR}/attendance/bulk-mark"
MANUAL = f"{settings.API_V1_STR}/hr/attendance/manual"
PW = "test@12345"
TODAY = datetime.now(timezone.utc).date()
OLD_A, OLD_B = date(2018, 4, 10), date(2018, 4, 11)
LOCKED = date(2019, 3, 5)


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
    dept_x, dept_y = f"BX{sfx}", f"BY{sfx}"
    made_perm = []
    try:
        async with SessionLocal() as db:
            role = Role(name=f"BMR{sfx}", description="t")
            db.add(role)
            await db.flush()
            p = (await db.execute(select(Permission).where(
                Permission.name == "attendance edit"))).scalar_one_or_none()
            if p is None:
                p = Permission(name="attendance edit", description="t")
                db.add(p)
                await db.flush()
                made_perm.append(p.id)
            await db.execute(insert(role_permissions).values(
                role_id=role.id, permission_id=p.id))

            def mk(tag, **kw):
                return User(email=f"bm_{tag}_{sfx}@t.com", full_name=f"BM {tag}",
                            hashed_password=get_password_hash(PW),
                            is_active=True, **kw)
            us = {t: mk(t) for t in ("e1", "e2", "e3", "e4", "sx", "hr", "plain")}
            db.add_all(us.values())
            db.add_all([Department(name=dept_x), Department(name=dept_y)])
            tpl = ShiftTemplate(name=f"BMT{sfx}", start_time=time(9),
                                end_time=time(17))
            db.add(tpl)
            await db.commit()
            await db.execute(insert(user_roles).values(
                user_id=us["hr"].id, role_id=role.id))
            for tag, dept in (("e1", dept_x), ("e2", dept_x), ("e3", dept_x),
                              ("e4", dept_y)):
                db.add(Employee(
                    user_id=us[tag].id, employee_id=f"BM{sfx}{tag}",
                    department=dept, designation="T",
                    date_of_joining=date(2015, 1, 1),
                    status=EmployeeStatus.ACTIVE))
            await db.execute(Department.__table__.update().where(
                Department.name == dept_x).values(head_user_id=us["sx"].id))
            for d in (TODAY, OLD_A, OLD_B):
                db.add(RosterEntry(
                    employee_id=us["e1"].id, work_date=d,
                    shift_template_id=tpl.id, is_week_off=False,
                    status=RosterStatus.PUBLISHED))
            await db.commit()
            ids = {t: u.id for t, u in us.items()}
            ids["tpl"] = tpl.id
        yield {"ids": ids, "sfx": sfx,
               "email": lambda t: f"bm_{t}_{sfx}@t.com"}
    finally:
        async with SessionLocal() as db:
            uids = list((await db.execute(select(User.id).where(
                User.email.like(f"bm\\_%\\_{sfx}@t.com")))).scalars().all())
            tids = list((await db.execute(select(ShiftTemplate.id).where(
                ShiftTemplate.name == f"BMT{sfx}"))).scalars().all())
            await db.execute(delete(Notification).where(
                Notification.user_id.in_(uids)))
            await db.execute(delete(AuditLog).where(
                AuditLog.user_id.in_(uids)))
            await db.execute(delete(Attendance).where(
                Attendance.user_id.in_(uids)))
            await purge_gap_notifications(db, tids)
            await db.execute(delete(CoverageGap).where(
                CoverageGap.shift_template_id.in_(tids)))
            await db.execute(Department.__table__.update().where(
                Department.name.in_([dept_x, dept_y])).values(
                head_user_id=None, deputy_head_user_id=None))
            await db.execute(delete(RosterEntryHistory).where(
                RosterEntryHistory.employee_id.in_(uids)))
            await db.execute(delete(RosterEntry).where(
                RosterEntry.employee_id.in_(uids)))
            await db.execute(delete(Employee).where(Employee.user_id.in_(uids)))
            await db.execute(delete(Department).where(
                Department.name.in_([dept_x, dept_y])))
            await purge_shift_templates(db, tids)
            await db.execute(delete(user_roles).where(
                user_roles.c.user_id.in_(uids)))
            await db.execute(delete(User).where(User.id.in_(uids)))
            rl = list((await db.execute(select(Role.id).where(
                Role.name == f"BMR{sfx}"))).scalars().all())
            await db.execute(delete(role_permissions).where(
                role_permissions.c.role_id.in_(rl)))
            await db.execute(delete(Role).where(Role.id.in_(rl)))
            if made_perm:
                await db.execute(delete(Permission).where(
                    Permission.id.in_(made_perm)))
            await db.commit()


async def _login(client, email):
    r = await client.post(f"{settings.API_V1_STR}/auth/login",
                          data={"username": email, "password": PW})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def body(w, tags, d=TODAY, **kw):
    return {"work_date": d.isoformat(),
            "user_ids": [w["ids"][t] for t in tags],
            "punch_in_time": "00:01", "reason": "Punch system outage", **kw}


def by_user(resp, w):
    inv = {v: k for k, v in w["ids"].items()}
    return {inv[r["user_id"]]: r for r in resp.json()["results"]}


async def test_authorization_matrix(client, world):
    w = world
    plain = await _login(client, w["email"]("plain"))
    r = await client.post(API, json=body(w, ["e1"]), headers=plain)
    assert r.status_code == 403
    # unauthenticated
    assert (await client.post(API, json=body(w, ["e1"]))).status_code in (401, 403)

    sx = await _login(client, w["email"]("sx"))
    r = await client.post(API, json=body(w, ["e1", "e4"]), headers=sx)
    assert r.status_code == 200, r.text
    res = by_user(r, w)
    assert res["e1"]["status"] == "created" and res["e1"]["attendance_id"]
    assert res["e4"]["status"] == "out_of_scope"
    assert r.json()["counts"]["created"] == 1
    # date window for schedulers: today-3 refused, today-2 ok
    r = await client.post(
        API, json=body(w, ["e2"], TODAY - timedelta(days=3)), headers=sx)
    assert r.status_code == 403
    r = await client.post(
        API, json=body(w, ["e2"], TODAY - timedelta(days=2)), headers=sx)
    assert r.status_code == 200 and by_user(r, w)["e2"]["status"] == "created"
    # future date refused (403 for schedulers: outside window)
    r = await client.post(
        API, json=body(w, ["e3"], TODAY + timedelta(days=1)), headers=sx)
    assert r.status_code == 403

    hr = await _login(client, w["email"]("hr"))
    r = await client.post(
        API, json=body(w, ["e3"], TODAY + timedelta(days=1)), headers=hr)
    assert r.status_code == 422
    r = await client.post(API, json=body(w, ["e4", "e3"], OLD_A), headers=hr)
    assert r.status_code == 200
    res = by_user(r, w)
    assert res["e4"]["status"] == res["e3"]["status"] == "created"

    async with SessionLocal() as db:
        rows = (await db.execute(select(Attendance).where(
            Attendance.user_id.in_([w["ids"]["e1"], w["ids"]["e4"]])))
        ).scalars().all()
        assert all(a.mode == "manual_bulk" for a in rows)
        assert {a.edited_by_id for a in rows} == {w["ids"]["sx"], w["ids"]["hr"]}
        e1 = next(a for a in rows if a.user_id == w["ids"]["e1"])
        assert e1.captured_at.replace(tzinfo=timezone.utc) == datetime.combine(
            TODAY, time(0, 1), tzinfo=timezone.utc)
        audits = (await db.execute(select(AuditLog).where(
            AuditLog.action == "BULK_MARK_ATTENDANCE",
            AuditLog.user_id.in_([w["ids"]["sx"], w["ids"]["hr"]])))
        ).scalars().all()
        assert len(audits) == 4
        assert all(a.details["reason"] == "Punch system outage"
                   and a.details["batch_id"] for a in audits)


async def test_validation(client, world):
    w = world
    hr = await _login(client, w["email"]("hr"))
    for bad in ({"reason": "abc"}, {"user_ids": []},
                {"punch_in_time": "nope"},
                {"punch_out_time": f"{OLD_A}T00:00:00Z"}, {"user_ids": list(range(1, 202))}):
        r = await client.post(API, json={**body(w, ["e1"], OLD_A), **bad},
                              headers=hr)
        assert r.status_code == 422, (bad, r.text)
    # ISO datetime accepted; HH:MM out earlier than in rolls to next day
    r = await client.post(API, json=body(
        w, ["e2"], OLD_A, punch_in_time=f"{OLD_A}T22:00:00Z",
        punch_out_time="06:00"), headers=hr)
    assert r.status_code == 200 and by_user(r, w)["e2"]["status"] == "created"
    async with SessionLocal() as db:
        a = (await db.execute(select(Attendance).where(
            Attendance.user_id == w["ids"]["e2"]))).scalars().one()
        assert (a.punch_out_time - a.captured_at) == timedelta(hours=8)


async def test_existing_skipped_and_independent_failures(client, world):
    w = world
    hr = await _login(client, w["email"]("hr"))
    r = await client.post(API, json=body(w, ["e1"], OLD_A), headers=hr)
    assert by_user(r, w)["e1"]["status"] == "created"
    payload = body(w, ["e1", "e2"], OLD_A)
    payload["user_ids"].insert(1, 2_000_000_000)  # not an employee
    r = await client.post(API, json=payload, headers=hr)
    assert r.status_code == 200
    out = r.json()["results"]
    assert [x["status"] for x in out] == ["skipped_existing", "error", "created"]
    assert r.json()["counts"] == {
        "created": 1, "skipped_existing": 1, "out_of_scope": 0,
        "locked": 0, "error": 1}


async def test_payroll_locked_month(client, world):
    w = world
    hr = await _login(client, w["email"]("hr"))
    async with SessionLocal() as db:
        run = PayrollRun(month=LOCKED.month, year=LOCKED.year,
                         status=PayrollRunStatus.LEAVES_LOCKED)
        db.add(run)
        await db.commit()
        run_id = run.id
    try:
        r = await client.post(API, json=body(w, ["e1", "e2"], LOCKED), headers=hr)
        assert r.status_code == 200
        assert {x["status"] for x in r.json()["results"]} == {"locked"}
        async with SessionLocal() as db:
            assert (await db.execute(select(Attendance).where(
                Attendance.work_date == LOCKED,
                Attendance.user_id.in_([w["ids"]["e1"], w["ids"]["e2"]])))
            ).first() is None
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(PayrollRun).where(PayrollRun.id == run_id))
            await db.commit()


async def test_shift_attribution_parity_with_manual_endpoint(client, world):
    w = world
    hr = await _login(client, w["email"]("hr"))
    r = await client.post(MANUAL, headers=hr, json={
        "user_id": w["ids"]["e1"], "work_date": OLD_A.isoformat(),
        "punch_in_time": f"{OLD_A}T09:00:00Z", "reason": "forgot to punch"})
    assert r.status_code == 200, r.text
    r = await client.post(MANUAL, headers=hr, json={
        "user_id": w["ids"]["e2"], "work_date": OLD_A.isoformat(),
        "punch_in_time": f"{OLD_A}T09:00:00Z", "reason": "forgot to punch"})
    assert r.status_code == 200
    # dupes still 409 on the manual endpoint
    r = await client.post(MANUAL, headers=hr, json={
        "user_id": w["ids"]["e1"], "work_date": OLD_A.isoformat(),
        "punch_in_time": f"{OLD_A}T09:00:00Z", "reason": "forgot to punch"})
    assert r.status_code == 409
    # bulk: e1 on OLD_B (rostered), e2 on OLD_B (no shift)
    r = await client.post(API, json=body(w, ["e1", "e2"], OLD_B), headers=hr)
    assert r.status_code == 200
    async with SessionLocal() as db:
        rows = (await db.execute(select(Attendance).where(
            Attendance.user_id.in_([w["ids"]["e1"], w["ids"]["e2"]])))
        ).scalars().all()
    got = {(a.user_id, a.work_date): a for a in rows}
    for tag in ("e1", "e2"):
        m, b = got[(w["ids"][tag], OLD_A)], got[(w["ids"][tag], OLD_B)]
        assert m.mode == "manual" and b.mode == "manual_bulk"
        assert m.shift_template_id == b.shift_template_id
        assert m.attribution_flag == b.attribution_flag
    assert got[(w["ids"]["e1"], OLD_A)].shift_template_id == w["ids"]["tpl"]
    assert got[(w["ids"]["e2"], OLD_A)].attribution_flag == "no_shift"


async def test_marking_dismisses_open_noshow_gap(client, world):
    w = world
    async with SessionLocal() as db:
        g1 = await gap_svc.open_gap(
            db, work_date=TODAY, shift_template_id=w["ids"]["tpl"],
            absent_user_id=w["ids"]["e1"], source=GapSource.NO_SHOW,
            notify=False)
        g2 = await gap_svc.open_gap(
            db, work_date=TODAY, shift_template_id=w["ids"]["tpl"],
            absent_user_id=w["ids"]["e2"], source=GapSource.MANUAL,
            notify=False)
        await db.commit()
        g1id, g2id = g1.id, g2.id
    sx = await _login(client, w["email"]("sx"))
    r = await client.post(API, json=body(w, ["e1", "e2"]), headers=sx)
    assert r.status_code == 200
    async with SessionLocal() as db:
        g1 = await db.get(CoverageGap, g1id)
        g2 = await db.get(CoverageGap, g2id)
        assert g1.status == GapStatus.DISMISSED
        assert g1.note == "Marked present by supervisor"
        assert g1.resolved_by_id == w["ids"]["sx"]
        assert g2.status == GapStatus.OPEN  # only no_show gaps are dismissed


async def test_snapshot_staleness_existing_row_and_lock_detected(world):
    """A row/payroll lock committed by another session AFTER this session's
    snapshot must still be detected (locking, fresh reads)."""
    w = world
    uid = w["ids"]["e1"]
    actor = type("A", (), {"id": w["ids"]["hr"]})()
    pin = datetime.combine(OLD_A, time(9), tzinfo=timezone.utc)
    async with SessionLocal() as db1:
        # establish the REPEATABLE READ snapshot
        await db1.execute(select(Attendance).where(Attendance.user_id == uid))
        async with SessionLocal() as db2:
            db2.add(Attendance(user_id=uid, mode="web", captured_at=pin,
                               work_date=OLD_A))
            await db2.commit()
        with pytest.raises(ManualAttendanceExists):
            await create_manual_attendance_row(
                db1, actor, uid, OLD_A, pin, None, "reason", mode="manual_bulk")
        await db1.rollback()
    async with SessionLocal() as db1:
        await db1.execute(select(PayrollRun).where(PayrollRun.id == 0))
        async with SessionLocal() as db2:
            run = PayrollRun(month=LOCKED.month, year=LOCKED.year,
                             status=PayrollRunStatus.LEAVES_LOCKED)
            db2.add(run)
            await db2.commit()
            run_id = run.id
        try:
            with pytest.raises(HTTPException) as ei:
                await create_manual_attendance_row(
                    db1, actor, w["ids"]["e2"], LOCKED,
                    datetime.combine(LOCKED, time(9), tzinfo=timezone.utc),
                    None, "reason", mode="manual_bulk")
            assert ei.value.status_code == 409
            await db1.rollback()
        finally:
            async with SessionLocal() as db3:
                await db3.execute(delete(PayrollRun).where(
                    PayrollRun.id == run_id))
                await db3.commit()


async def test_time_bounds(client, world):
    w = world
    sx = await _login(client, w["email"]("sx"))
    hr = await _login(client, w["email"]("hr"))
    fut = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    # future punch-in: refused for HR and supervisors
    for h in (sx, hr):
        r = await client.post(API, json=body(
            w, ["e1"], TODAY, punch_in_time=fut), headers=h)
        assert r.status_code == 422, r.text
    # supervisor: punch-in far outside work date window
    r = await client.post(API, json=body(
        w, ["e1"], TODAY - timedelta(days=1),
        punch_in_time=f"{TODAY - timedelta(days=3)}T10:00:00Z"), headers=sx)
    assert r.status_code == 422
    # >24h session refused for HR
    r = await client.post(API, json=body(
        w, ["e1"], OLD_A, punch_in_time=f"{OLD_A}T01:00:00Z",
        punch_out_time=f"{OLD_B}T02:00:00Z"), headers=hr)
    assert r.status_code == 422
    # equal HH:MM in/out
    r = await client.post(API, json=body(
        w, ["e1"], OLD_A, punch_in_time="09:00", punch_out_time="09:00"),
        headers=hr)
    assert r.status_code == 422
    # night shift rollover still fine for supervisor
    d = TODAY - timedelta(days=1)
    r = await client.post(API, json=body(
        w, ["e1"], d, punch_in_time="22:00", punch_out_time="06:00"),
        headers=sx)
    assert r.status_code == 200 and by_user(r, w)["e1"]["status"] == "created"


async def test_dismiss_cancels_linked_open_shift(client, world):
    w = world
    async with SessionLocal() as db:
        sh = OpenShift(work_date=TODAY, shift_template_id=w["ids"]["tpl"],
                       status=OpenShiftStatus.OPEN)
        db.add(sh)
        await db.flush()
        g = await gap_svc.open_gap(
            db, work_date=TODAY, shift_template_id=w["ids"]["tpl"],
            absent_user_id=w["ids"]["e1"], source=GapSource.NO_SHOW,
            notify=False)
        g.open_shift_id = sh.id
        await db.commit()
        sid, gid = sh.id, g.id
    sx = await _login(client, w["email"]("sx"))
    r = await client.post(API, json=body(w, ["e1"]), headers=sx)
    assert r.status_code == 200
    async with SessionLocal() as db:
        assert (await db.get(OpenShift, sid)).status == OpenShiftStatus.CANCELLED
        assert (await db.get(CoverageGap, gid)).status == GapStatus.DISMISSED
        await db.execute(delete(CoverageGap).where(CoverageGap.id == gid))
        await db.execute(delete(OpenShift).where(OpenShift.id == sid))
        await db.commit()
