"""Live location tracking (Roadmap v2 Phase 3, Task 3)."""
import uuid
from datetime import date, datetime, time, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, insert, select

from _cleanup import purge_shift_templates
from _tz import org_tz_utc  # noqa: F401  (pre-6A UTC expectations)
from app.core.config import settings
from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.main import create_app
from app.models.audit import AuditLog
from app.models.department import Department
from app.models.employee import Employee, EmployeeStatus
from app.models.geofence import (
    EmployeeGeoConfig, EmployeeGeoFenceLink, GeoFenceLocation,
)
from app.models.leave import LeaveRequest, LeaveStatus, LeaveType
from app.models.location import (
    LocationPing, TrackingAlert, TrackingConsent, TrackingOverride,
    TrackingPolicy,
)
from app.models.notification import Notification
from app.models.roster import RosterEntry, RosterEntryHistory, RosterStatus
from app.models.shift import ShiftTemplate
from app.models.system import SystemSetting
from app.models.user import (
    Permission, Role, User, role_permissions, user_roles,
)
from app.services import location_tracking as lt
from app.services.time_rules import set_time_rules

API = settings.API_V1_STR
T = f"{API}/tracking"
PW = "test@12345"
IN_FENCE = (22.5726, 88.3639)
OUT_FENCE = (22.6200, 88.4000)  # ~6 km away
NEAR = (22.5816, 88.3639)  # ~1 km north of the fence centre


def _now():
    return datetime.now(timezone.utc)


@pytest.fixture
async def client():
    app = create_app()  # tracking is NOT attendance-gated: no override
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as c:
        yield c


@pytest.fixture
async def world():
    sfx = uuid.uuid4().hex[:8]
    dx, dy = f"TKX{sfx}", f"TKY{sfx}"
    made_perm, fence_id = [], None
    now = _now()
    try:
        async with SessionLocal() as db:
            perms = {}
            for name in ("hr employee read", "hr employee write"):
                p = (await db.execute(select(Permission).where(
                    Permission.name == name))).scalar_one_or_none()
                if p is None:
                    p = Permission(name=name, description="t")
                    db.add(p)
                    await db.flush()
                    made_perm.append(p.id)
                perms[name] = p.id
            roles = {k: Role(name=f"TK{k}{sfx}", description="t")
                     for k in ("trk", "hrw", "hrr")}
            db.add_all(roles.values())
            await db.flush()
            await db.execute(insert(role_permissions).values([
                dict(role_id=roles["hrw"].id, permission_id=perms["hr employee read"]),
                dict(role_id=roles["hrw"].id, permission_id=perms["hr employee write"]),
                dict(role_id=roles["hrr"].id, permission_id=perms["hr employee read"]),
            ]))

            def mk(tag, **kw):
                return User(email=f"tk_{tag}_{sfx}@t.com",
                            full_name=f"TK {tag} {sfx}",
                            hashed_password=get_password_hash(PW),
                            is_active=True, **kw)
            mgr, head = mk("mgr"), mk("head")
            db.add_all([mgr, head])
            await db.flush()
            us = {n: mk(n) for n in ("e1", "e2", "eo", "hrw", "hrr", "plain")}
            us["e1"].manager_id = mgr.id
            db.add_all(us.values())
            db.add_all([Department(name=dx, head_user_id=head.id),
                        Department(name=dy)])
            # shift covering "now" (wall-clock UTC), crossing midnight if need be
            st = (now - timedelta(hours=1)).time().replace(second=0, microsecond=0)
            en = (now + timedelta(hours=1)).time().replace(second=0, microsecond=0)
            tpl = ShiftTemplate(name=f"TKS{sfx}", start_time=st, end_time=en,
                                is_overnight=en < st)
            night = ShiftTemplate(name=f"TKN{sfx}", start_time=time(22),
                                  end_time=time(6), is_overnight=True)
            fence = GeoFenceLocation(
                name=f"TKF{sfx}", latitude=IN_FENCE[0], longitude=IN_FENCE[1],
                radius_meters=200, is_active=True)
            db.add_all([tpl, night, fence])
            await db.commit()
            fence_id = fence.id
            for t, r in (("e1", "trk"), ("eo", "trk"), ("hrw", "hrw"),
                         ("hrr", "hrr")):
                await db.execute(insert(user_roles).values(
                    user_id=us[t].id, role_id=roles[r].id))
            for t in ("e1", "e2", "eo", "plain"):
                db.add(Employee(
                    user_id=us[t].id, employee_id=f"TK{sfx}{t}",
                    department=dy if t == "eo" else dx, location="LocT",
                    designation="T", date_of_joining=date(2015, 1, 1),
                    status=EmployeeStatus.ACTIVE))
                if t != "plain":
                    for dd in (-1, 0, 1):
                        db.add(RosterEntry(
                            employee_id=us[t].id,
                            work_date=now.date() + timedelta(days=dd),
                            shift_template_id=tpl.id, is_week_off=False,
                            status=RosterStatus.PUBLISHED))
            db.add(EmployeeGeoConfig(user_id=us["e1"].id, geo_enabled=True,
                                     enforcement_mode="allow_with_flag"))
            await db.commit()
            db.add(EmployeeGeoFenceLink(
                user_id=us["e1"].id, geofence_location_id=fence_id))
            await db.commit()
            ids = {t: u.id for t, u in us.items()}
            ids.update(mgr=mgr.id, head=head.id, tpl=tpl.id, night=night.id,
                       role_trk=roles["trk"].id)
        yield {"ids": ids, "sfx": sfx, "dx": dx, "dy": dy,
               "email": lambda t: f"tk_{t}_{sfx}@t.com"}
    finally:
        async with SessionLocal() as db:
            uids = list((await db.execute(select(User.id).where(
                User.email.like(f"tk\\_%\\_{sfx}@t.com")))).scalars().all())
            rids = list((await db.execute(select(Role.id).where(
                Role.name.like(f"TK%{sfx}")))).scalars().all())
            tids = list((await db.execute(select(ShiftTemplate.id).where(
                ShiftTemplate.name.in_([f"TKS{sfx}", f"TKN{sfx}"])))).scalars().all())
            for m in (LocationPing, TrackingAlert, TrackingConsent,
                      TrackingOverride):
                await db.execute(delete(m).where(m.user_id.in_(uids)))
            await db.execute(delete(TrackingPolicy).where(
                TrackingPolicy.role_id.in_(rids)))
            await db.execute(delete(AuditLog).where(AuditLog.user_id.in_(uids)))
            await db.execute(delete(Notification).where(
                Notification.user_id.in_(uids)))
            await db.execute(delete(Notification).where(
                Notification.message.like(f"%{sfx}%")))
            await db.execute(delete(LeaveRequest).where(
                LeaveRequest.employee_id.in_(uids)))
            await db.execute(delete(LeaveType).where(
                LeaveType.name == f"TKL{sfx}"))
            await db.execute(delete(EmployeeGeoFenceLink).where(
                EmployeeGeoFenceLink.user_id.in_(uids)))
            await db.execute(delete(EmployeeGeoConfig).where(
                EmployeeGeoConfig.user_id.in_(uids)))
            await db.execute(delete(GeoFenceLocation).where(
                GeoFenceLocation.name == f"TKF{sfx}"))
            await db.execute(delete(RosterEntryHistory).where(
                RosterEntryHistory.employee_id.in_(uids)))
            await db.execute(delete(RosterEntry).where(
                RosterEntry.employee_id.in_(uids)))
            await db.execute(delete(Employee).where(Employee.user_id.in_(uids)))
            await db.execute(delete(Department).where(
                Department.name.in_([dx, dy])))
            await purge_shift_templates(db, tids)
            await db.execute(delete(user_roles).where(
                user_roles.c.user_id.in_(uids)))
            await db.execute(delete(User).where(User.id.in_(uids)))
            await db.execute(delete(role_permissions).where(
                role_permissions.c.role_id.in_(rids)))
            await db.execute(delete(Role).where(Role.id.in_(rids)))
            if made_perm:
                await db.execute(delete(Permission).where(
                    Permission.id.in_(made_perm)))
            await db.commit()


async def _login(client, w, tag):
    r = await client.post(f"{API}/auth/login",
                          data={"username": w["email"](tag), "password": PW})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _ping(minutes_ago, pos=IN_FENCE, **kw):
    ts = (_now() - timedelta(minutes=minutes_ago)).replace(microsecond=0)
    return {"captured_at": ts.isoformat(), "lat": pos[0], "lng": pos[1],
            "accuracy": 10, **kw}


async def _enable(client, w, role="trk", **kw):
    h = await _login(client, w, "hrw")
    body = {"enabled": True, **kw}
    r = await client.put(f"{T}/policies/{w['ids']['role_' + role]}",
                         headers=h, json=body)
    assert r.status_code == 200, r.text
    return r


async def _backdate(uid, hours=3):
    """Move the active consent back so older test pings are not
    'before_consent'."""
    async with SessionLocal() as db:
        for c in (await db.execute(select(TrackingConsent).where(
                TrackingConsent.user_id == uid,
                TrackingConsent.revoked_at.is_(None)))).scalars().all():
            c.consented_at = _now() - timedelta(hours=hours)
        await db.commit()


async def _ready(client, w, tag="e1"):
    """Policy on + consent given; returns the employee's headers."""
    await _enable(client, w)
    h = await _login(client, w, tag)
    r = await client.post(f"{T}/consent", headers=h, json={"app_version": "1.0"})
    assert r.status_code == 200, r.text
    await _backdate(w["ids"][tag])
    return h


async def _post(client, h, pings):
    r = await client.post(f"{T}/pings", headers=h, json={"pings": pings})
    assert r.status_code == 200, r.text
    return r.json()


# --- policy / override precedence ------------------------------------------


async def test_default_off_and_policy_enables(client, world):
    h = await _login(client, world, "e1")
    st = (await client.get(f"{T}/my-status", headers=h)).json()
    assert st["required"] is False and st["consented"] is False
    assert st["window"] is None
    await _enable(client, world, interval_seconds=120, distance_filter_m=50)
    st = (await client.get(f"{T}/my-status", headers=h)).json()
    assert st["required"] is True and st["active"] is False
    assert st["interval_seconds"] == 120 and st["distance_filter_m"] == 50
    w = st["window"]
    assert w and w["in_window"] is True
    s = datetime.fromisoformat(w["start"])
    assert datetime.fromisoformat(w["shift_start"]) - s == timedelta(minutes=30)


async def test_override_beats_policy_and_smallest_params(client, world):
    i = world["ids"]
    await _enable(client, world, interval_seconds=600, distance_filter_m=500)
    h1 = await _login(client, world, "e1")
    h2 = await _login(client, world, "e2")
    hr = await _login(client, world, "hrw")
    # e2 has no role: off; override on -> required with defaults
    assert (await client.get(f"{T}/my-status", headers=h2)).json()["required"] is False
    r = await client.put(f"{T}/overrides/{i['e2']}", headers=hr,
                         json={"enabled": True})
    assert r.status_code == 200
    st = (await client.get(f"{T}/my-status", headers=h2)).json()
    assert st["required"] is True and st["interval_seconds"] == 300
    # e1 has an enabled role policy; override off wins
    await client.put(f"{T}/overrides/{i['e1']}", headers=hr, json={"enabled": False})
    assert (await client.get(f"{T}/my-status", headers=h1)).json()["required"] is False
    # removing the override falls back to the policy
    assert (await client.delete(f"{T}/overrides/{i['e1']}", headers=hr)).status_code == 200
    st = (await client.get(f"{T}/my-status", headers=h1)).json()
    assert st["required"] is True and st["interval_seconds"] == 600
    assert (await client.delete(f"{T}/overrides/{i['e1']}", headers=hr)).status_code == 404
    # smallest interval/distance among enabled policies of several roles
    async with SessionLocal() as db:
        rid = (await db.execute(select(Role.id).where(
            Role.name == f"TKhrr{world['sfx']}"))).scalar_one()
        await db.execute(insert(user_roles).values(user_id=i["e1"], role_id=rid))
        db.add(TrackingPolicy(role_id=rid, enabled=True, interval_seconds=90,
                              distance_filter_m=700))
        await db.commit()
    st = (await client.get(f"{T}/my-status", headers=h1)).json()
    assert st["interval_seconds"] == 90 and st["distance_filter_m"] == 500


async def test_policy_validation(client, world):
    hr = await _login(client, world, "hrw")
    rid = world["ids"]["role_trk"]
    for bad in ({"interval_seconds": 59}, {"interval_seconds": 3601},
                {"distance_filter_m": 9}, {"distance_filter_m": 2001}):
        r = await client.put(f"{T}/policies/{rid}", headers=hr,
                             json={"enabled": True, **bad})
        assert r.status_code == 422, bad
    assert (await client.put(f"{T}/policies/99999999", headers=hr,
                             json={"enabled": True})).status_code == 404
    assert (await client.put(f"{T}/overrides/99999999", headers=hr,
                             json={"enabled": True})).status_code == 404


# --- consent -----------------------------------------------------------------


async def test_consent_lifecycle(client, world):
    h = await _login(client, world, "e1")
    hr = await _login(client, world, "hrr")
    await _enable(client, world)
    r = await client.post(f"{T}/consent", headers=h, json={"app_version": "2.1"})
    assert r.json()["consented"] is True
    await client.post(f"{T}/consent", headers=h)  # idempotent
    async with SessionLocal() as db:
        assert len((await db.execute(select(TrackingConsent).where(
            TrackingConsent.user_id == world["ids"]["e1"]))).scalars().all()) == 1
    st = (await client.get(f"{T}/my-status", headers=h)).json()
    assert st["consented"] is True and st["active"] is True
    rows = (await client.get(f"{T}/consents?status=active", headers=hr)).json()
    mine = [x for x in rows if x["user_id"] == world["ids"]["e1"]]
    assert mine and mine[0]["status"] == "active" and mine[0]["app_version"] == "2.1"
    r = await client.delete(f"{T}/consent", headers=h)
    assert r.json() == {"consented": False, "revoked": True}
    assert (await client.delete(f"{T}/consent", headers=h)).json()["revoked"] is False
    assert (await client.get(f"{T}/my-status", headers=h)).json()["consented"] is False
    rows = (await client.get(f"{T}/consents?status=revoked", headers=hr)).json()
    assert any(x["user_id"] == world["ids"]["e1"] and x["status"] == "revoked"
               for x in rows)
    # re-consent creates a new history row; active again
    await client.post(f"{T}/consent", headers=h)
    async with SessionLocal() as db:
        assert len((await db.execute(select(TrackingConsent).where(
            TrackingConsent.user_id == world["ids"]["e1"]))).scalars().all()) == 2
    rows = (await client.get(f"{T}/consents", headers=hr)).json()
    assert [x["status"] for x in rows if x["user_id"] == world["ids"]["e1"]] == ["active"]
    async with SessionLocal() as db:
        acts = {a for (a,) in (await db.execute(select(AuditLog.action).where(
            AuditLog.user_id == world["ids"]["e1"]))).all()}
    assert {"TRACKING_CONSENT_GIVEN", "TRACKING_CONSENT_REVOKED"} <= acts


# --- window (pure helper, far-future dates) ----------------------------------


async def test_windows_overnight_weekoff_leave(world):
    i, sfx = world["ids"], world["sfx"]
    d1, d2, d3 = date(2030, 3, 4), date(2030, 3, 5), date(2030, 3, 6)
    async with SessionLocal() as db:
        lty = LeaveType(name=f"TKL{sfx}")
        db.add(lty)
        await db.flush()
        for d, off in ((d1, False), (d2, False), (d3, True)):
            db.add(RosterEntry(
                employee_id=i["e2"], work_date=d,
                shift_template_id=None if off else i["night"],
                is_week_off=off, status=RosterStatus.PUBLISHED))
        db.add(LeaveRequest(
            employee_id=i["e2"], leave_type_id=lty.id, start_date=d2,
            end_date=d2, is_half_day=False, reason="t",
            status=LeaveStatus.APPROVED, created_by_user_id=i["e2"]))
        await db.commit()
        ws = await lt.windows_for(db, i["e2"], d1, d3)
    # d1 working (overnight), d2 on leave, d3 week-off
    assert [w[0] for w in ws] == [d1]
    _, s, e, _ = ws[0]
    utc = timezone.utc
    assert s == datetime(2030, 3, 4, 21, 30, tzinfo=utc)
    assert e == datetime(2030, 3, 5, 6, 30, tzinfo=utc)
    assert lt.current_window(ws, datetime(2030, 3, 5, 6, 0, tzinfo=utc))[0] == d1
    assert lt.current_window([], datetime(2030, 3, 5, tzinfo=utc)) is None


# --- ping ingest --------------------------------------------------------------


async def test_ping_gating(client, world):
    h = await _login(client, world, "e1")
    # not required
    assert (await _post(client, h, [_ping(5)])) == {
        "accepted": 0, "dropped": {"not_required": 1}}
    await _enable(client, world)
    # required but not consented
    assert (await _post(client, h, [_ping(5)])) == {
        "accepted": 0, "dropped": {"no_consent": 1}}
    await client.post(f"{T}/consent", headers=h)
    await _backdate(world["ids"]["e1"])
    assert (await _post(client, h, [_ping(5)]))["accepted"] == 1
    # revoked -> dropped again
    await client.delete(f"{T}/consent", headers=h)
    assert (await _post(client, h, [_ping(4)])) == {
        "accepted": 0, "dropped": {"no_consent": 1}}


async def test_ping_validation_dedupe_and_reasons(client, world):
    h = await _ready(client, world)
    good = _ping(10)
    batch = [
        good, dict(good),  # in-batch duplicate
        _ping(9, accuracy=-1),
        {**_ping(8), "lat": 91},
        {**_ping(7), "lng": -181},
        _ping(-10),  # 10 min in the future
        _ping(60 * 25),  # older than 24h
        _ping(60 * 3),  # outside the shift window (shift is now +-1h)
        _ping(6, battery=101), _ping(5, speed=300), _ping(4, accuracy=6000),
    ]
    out = await _post(client, h, batch)
    assert out["accepted"] == 1
    assert out["dropped"] == {"duplicate": 1, "invalid": 6, "future": 1,
                              "too_old": 1, "outside_window": 1}
    # re-sending the same ping across batches is a duplicate
    out = await _post(client, h, [good, _ping(6)])
    assert out == {"accepted": 1, "dropped": {"duplicate": 1}}
    # batch size cap
    r = await client.post(f"{T}/pings", headers=h,
                          json={"pings": [_ping(5)] * 201})
    assert r.status_code == 422
    async with SessionLocal() as db:
        rows = (await db.execute(select(LocationPing).where(
            LocationPing.user_id == world["ids"]["e1"]))).scalars().all()
    assert len(rows) == 2 and all(r.work_date for r in rows)


async def test_no_pings_without_working_shift(client, world):
    """A week-off published for today means no window: pings dropped."""
    h = await _ready(client, world)
    i = world["ids"]
    today = _now().date()
    async with SessionLocal() as db:
        for dd in (-1, 0, 1):
            e = (await db.execute(select(RosterEntry).where(
                RosterEntry.employee_id == i["e1"],
                RosterEntry.work_date == today + timedelta(days=dd)))).scalar_one()
            e.is_week_off, e.shift_template_id = True, None
        await db.commit()
    st = (await client.get(f"{T}/my-status", headers=h)).json()
    assert st["window"] is None
    out = await _post(client, h, [_ping(5)])
    assert out == {"accepted": 0, "dropped": {"outside_window": 1}}


async def test_tracking_not_attendance_gated(client, world):
    """No punch exists for the user; the endpoints still work."""
    h = await _login(client, world, "e1")
    assert (await client.get(f"{T}/my-status", headers=h)).status_code == 200
    assert (await client.get(f"{T}/my-status")).status_code in (401, 403)


# --- scope / privacy ------------------------------------------------------------


async def test_field_now_reports_remote_status_for_full_remote_user(client, world):
    from app.models.work_location import WorkLocationRequest
    i = world["ids"]
    he1 = await _ready(client, world, "e1")
    await _post(client, he1, [_ping(8), _ping(2)])
    today = _now().date()
    async with SessionLocal() as db:
        db.add(WorkLocationRequest(
            user_id=i["e1"], kind="wfh", start_date=today, end_date=today,
            day_portion="full", purpose="t", status="approved"))
        await db.commit()
    try:
        head = await _login(client, world, "head")
        rows = (await client.get(f"{T}/field-now", headers=head)).json()["rows"]
        row = [r for r in rows if r["user_id"] == i["e1"]][0]
        assert row["status"] == "remote"
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(WorkLocationRequest).where(
                WorkLocationRequest.user_id == i["e1"]))
            await db.commit()


async def test_field_now_and_trail_scope(client, world):
    i = world["ids"]
    he1 = await _ready(client, world, "e1")
    heo = await _login(client, world, "eo")
    await client.post(f"{T}/consent", headers=heo)
    await _backdate(i["eo"])
    await _post(client, he1, [_ping(8), _ping(2)])
    he2 = await _login(client, world, "e2")
    await _post(client, heo, [_ping(3)])
    head = await _login(client, world, "head")
    now = (await client.get(f"{T}/field-now", headers=head)).json()
    uids = {r["user_id"] for r in now["rows"]}
    # in scope + tracked + consented only: e1 (dept X). eo is dept Y; e2 is
    # not required.
    assert uids == {i["e1"]}
    row = now["rows"][0]
    assert row["ping"] and row["status"] in ("on_shift", "not_arrived", "upcoming",
                                            "running_late", "no_show")
    assert row["department"] == world["dx"]
    # department filter
    assert (await client.get(f"{T}/field-now?department={world['dy']}",
                             headers=head)).json()["rows"] == []
    # employee without any scope cannot use field-now
    assert (await client.get(f"{T}/field-now", headers=he1)).status_code == 403
    today = _now().date().isoformat()
    tr = await client.get(f"{T}/trail?user_id={i['e1']}&date={today}", headers=head)
    assert tr.status_code == 200 and len(tr.json()["points"]) == 2
    # out of scope
    assert (await client.get(f"{T}/trail?user_id={i['eo']}&date={today}",
                             headers=head)).status_code == 403
    # not tracked at all (no policy): 403 even though in scope
    assert (await client.get(f"{T}/trail?user_id={i['e2']}&date={today}",
                             headers=head)).status_code == 403
    # another employee cannot read e1's trail
    assert (await client.get(f"{T}/trail?user_id={i['e1']}&date={today}",
                             headers=he2)).status_code == 403
    # employee sees their own trail (both endpoints), points in order
    mine = (await client.get(f"{T}/my-trail?date={today}", headers=he1)).json()
    assert len(mine["points"]) == 2
    assert mine["points"][0]["captured_at"] < mine["points"][1]["captured_at"]
    assert (await client.get(f"{T}/trail?user_id={i['e1']}", headers=he1)).status_code == 200
    # scheduler views are audited
    async with SessionLocal() as db:
        n = len((await db.execute(select(AuditLog).where(
            AuditLog.user_id == i["head"],
            AuditLog.action == "TRACKING_TRAIL_VIEWED"))).scalars().all())
    assert n == 1
    # revoking consent hides the employee from schedulers (own trail remains)
    await client.delete(f"{T}/consent", headers=he1)
    assert (await client.get(f"{T}/field-now", headers=head)).json()["rows"] == []
    assert (await client.get(f"{T}/trail?user_id={i['e1']}&date={today}",
                             headers=head)).status_code == 403
    assert len((await client.get(f"{T}/my-trail?date={today}",
                                 headers=he1)).json()["points"]) == 2


async def test_field_now_ignores_stale_pings(client, world):
    he1 = await _ready(client, world, "e1")
    await _post(client, he1, [_ping(30)])
    head = await _login(client, world, "head")
    rows = (await client.get(f"{T}/field-now", headers=head)).json()["rows"]
    assert len(rows) == 1 and rows[0]["ping"] is None


# --- geofence exit ----------------------------------------------------------------


async def _alerts_and_notes(w):
    async with SessionLocal() as db:
        a = (await db.execute(select(TrackingAlert).where(
            TrackingAlert.user_id == w["ids"]["e1"]))).scalars().all()
        n = (await db.execute(select(Notification).where(
            Notification.user_id == w["ids"]["mgr"],
            Notification.event_type == "tracking_geofence_exit"))).scalars().all()
        au = (await db.execute(select(AuditLog).where(
            AuditLog.user_id == w["ids"]["e1"],
            AuditLog.action == "TRACKING_GEOFENCE_EXIT"))).scalars().all()
    return a, n, au


async def test_geofence_exit_alert_exactly_once(client, world):
    h = await _ready(client, world)
    await _post(client, h, [_ping(20, IN_FENCE), _ping(15, OUT_FENCE)])
    a, n, _ = await _alerts_and_notes(world)
    assert a == [] and n == []  # a single outside ping is not enough
    await _post(client, h, [_ping(10, IN_FENCE), _ping(8, OUT_FENCE)])
    a, n, _ = await _alerts_and_notes(world)
    assert a == [] and n == []  # not consecutive
    await _post(client, h, [_ping(6, OUT_FENCE)])
    a, n, au = await _alerts_and_notes(world)
    assert len(a) == 1 and len(n) == 1 and len(au) == 1
    assert world["sfx"] in n[0].message
    await _post(client, h, [_ping(4, OUT_FENCE), _ping(2, OUT_FENCE)])
    a, n, au = await _alerts_and_notes(world)
    assert len(a) == 1 and len(n) == 1 and len(au) == 1


async def test_geofence_exit_respects_accuracy_and_no_fence(client, world):
    h = await _ready(client, world)
    # poor accuracy (10 km) makes the position uncertain: not "outside"
    await _post(client, h, [_ping(9, NEAR, accuracy=1000),
                            _ping(8, NEAR, accuracy=1000)])
    assert (await _alerts_and_notes(world))[0] == []
    # a user without fences configured never alerts
    heo = await _login(client, world, "eo")
    await client.post(f"{T}/consent", headers=heo)
    await _backdate(world["ids"]["eo"])
    await _post(client, heo, [_ping(7, OUT_FENCE), _ping(5, OUT_FENCE)])
    async with SessionLocal() as db:
        assert (await db.execute(select(TrackingAlert).where(
            TrackingAlert.user_id == world["ids"]["eo"]))).first() is None


# --- purge / retention -------------------------------------------------------------


async def test_purge_job_and_retention_rule(world):
    i = world["ids"]
    now = _now()
    async with SessionLocal() as db:
        prior = await db.get(SystemSetting, "tracking.retention_days")
        saved = prior.value if prior else None
    try:
        async with SessionLocal() as db:
            for bad in ("0", "366", "abc", "-5"):
                with pytest.raises(ValueError):
                    await set_time_rules(db, {"tracking.retention_days": bad})
            await set_time_rules(db, {"tracking.retention_days": "10"})
            for days, kind in ((11, "old"), (9, "new")):
                db.add(LocationPing(
                    user_id=i["e1"], captured_at=now - timedelta(days=days),
                    lat=1.0, lng=1.0, work_date=(now - timedelta(days=days)).date(),
                    received_at=now))
            db.add(TrackingAlert(user_id=i["e1"], kind="geofence_exit",
                                 work_date=(now - timedelta(days=20)).date()))
            db.add(TrackingAlert(user_id=i["e1"], kind="geofence_exit",
                                 work_date=(now - timedelta(days=2)).date()))
            await db.commit()
            res = await lt.purge_pings(db, now)
            assert res["retention_days"] == 10
            assert res["pings_deleted"] >= 1 and res["alerts_deleted"] >= 1
            pings = (await db.execute(select(LocationPing).where(
                LocationPing.user_id == i["e1"]))).scalars().all()
            alerts = (await db.execute(select(TrackingAlert).where(
                TrackingAlert.user_id == i["e1"]))).scalars().all()
            assert len(pings) == 1 and len(alerts) == 1
    finally:
        async with SessionLocal() as db:
            row = await db.get(SystemSetting, "tracking.retention_days")
            if saved is None and row is not None:
                await db.delete(row)
            elif saved is not None and row is not None:
                row.value = saved
            await db.commit()


async def test_purge_job_registered():
    from app.services.scheduler import REGISTRY as JOBS
    assert "location_ping_purge" in JOBS


# --- HR admin permissions --------------------------------------------------------------


async def test_admin_permissions(client, world):
    rid = world["ids"]["role_trk"]
    hrr = await _login(client, world, "hrr")
    plain = await _login(client, world, "plain")
    hrw = await _login(client, world, "hrw")
    body = {"enabled": True}
    # read-only HR: can list, cannot write
    for path in ("policies", "overrides", "consents"):
        assert (await client.get(f"{T}/{path}", headers=hrr)).status_code == 200
        assert (await client.get(f"{T}/{path}", headers=plain)).status_code == 403
    assert (await client.put(f"{T}/policies/{rid}", headers=hrr, json=body)).status_code == 403
    assert (await client.put(f"{T}/overrides/{world['ids']['e2']}", headers=hrr,
                             json=body)).status_code == 403
    assert (await client.delete(f"{T}/overrides/{world['ids']['e2']}",
                                headers=hrr)).status_code == 403
    assert (await client.put(f"{T}/policies/{rid}", headers=plain, json=body)).status_code == 403
    r = await client.put(f"{T}/policies/{rid}", headers=hrw,
                         json={"enabled": True, "interval_seconds": 120})
    assert r.status_code == 200
    pol = [p for p in (await client.get(f"{T}/policies", headers=hrr)).json()
           if p["role_id"] == rid][0]
    assert pol["enabled"] is True and pol["interval_seconds"] == 120 and pol["configured"]
    # changes are audited
    async with SessionLocal() as db:
        assert (await db.execute(select(AuditLog).where(
            AuditLog.user_id == world["ids"]["hrw"],
            AuditLog.action == "TRACKING_POLICY_UPDATED"))).first() is not None


# --- review fixes -------------------------------------------------------------------


async def test_before_consent_dropped(client, world):
    await _enable(client, world)
    h = await _login(client, world, "e1")
    await client.post(f"{T}/consent", headers=h)  # consented just now
    out = await _post(client, h, [_ping(10), _ping(0)])
    assert out == {"accepted": 1, "dropped": {"before_consent": 1}}


async def test_geofence_exit_ignores_pre_shift_margin_and_gaps(client, world):
    h = await _ready(client, world)
    # shift is now +-1h; 80 and 70 min ago are in the 30 min pre-shift margin
    out = await _post(client, h, [_ping(80, OUT_FENCE), _ping(70, OUT_FENCE)])
    assert out["accepted"] == 2
    a, n, _ = await _alerts_and_notes(world)
    assert a == [] and n == []
    # two outside pings inside the shift but 15 min apart (> 2 x 300 s)
    await _post(client, h, [_ping(30, OUT_FENCE), _ping(15, OUT_FENCE)])
    a, n, _ = await _alerts_and_notes(world)
    assert a == [] and n == []
    # ...and a pair within the gap alerts
    await _post(client, h, [_ping(8, OUT_FENCE), _ping(4, OUT_FENCE)])
    a, n, _ = await _alerts_and_notes(world)
    assert len(a) == 1 and len(n) == 1


async def test_geofence_exit_only_after_punch_in(client, world):
    from app.models.attendance import Attendance
    h = await _ready(client, world)
    i = world["ids"]
    async with SessionLocal() as db:
        db.add(Attendance(user_id=i["e1"], mode="mobile", work_date=_now().date(),
                          captured_at=_now() - timedelta(minutes=3)))
        await db.commit()
    try:
        await _post(client, h, [_ping(10, OUT_FENCE), _ping(7, OUT_FENCE)])
        assert (await _alerts_and_notes(world))[0] == []  # before punch-in
        await _post(client, h, [_ping(2, OUT_FENCE), _ping(1, OUT_FENCE)])
        assert len((await _alerts_and_notes(world))[0]) == 1
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(Attendance).where(
                Attendance.user_id == i["e1"]))
            await db.commit()


async def test_scheduler_views_hide_pings_before_reconsent(client, world):
    i = world["ids"]
    he1 = await _ready(client, world)
    head = await _login(client, world, "head")
    await _post(client, he1, [_ping(8)])
    today = _now().date().isoformat()
    assert len((await client.get(f"{T}/trail?user_id={i['e1']}&date={today}",
                                 headers=head)).json()["points"]) == 1
    await client.delete(f"{T}/consent", headers=he1)
    await client.post(f"{T}/consent", headers=he1)  # new consent, now
    rows = (await client.get(f"{T}/field-now", headers=head)).json()["rows"]
    assert rows[0]["ping"] is None
    tr = (await client.get(f"{T}/trail?user_id={i['e1']}&date={today}",
                           headers=head)).json()
    assert tr["points"] == [] and tr["truncated"] is False
    # the employee still sees the full own trail
    assert len((await client.get(f"{T}/my-trail?date={today}",
                                 headers=he1)).json()["points"]) == 1


async def test_employee_data_control(client, world):
    i = world["ids"]
    h = await _ready(client, world)
    await _post(client, h, [_ping(20, OUT_FENCE), _ping(18, OUT_FENCE)])
    assert len((await _alerts_and_notes(world))[0]) == 1
    r = await client.delete(f"{T}/my-data", headers=h)
    assert r.json() == {"deleted": {"pings": 2, "alerts": 1}}
    async with SessionLocal() as db:
        assert (await db.execute(select(LocationPing).where(
            LocationPing.user_id == i["e1"]))).first() is None
        a = (await db.execute(select(AuditLog).where(
            AuditLog.user_id == i["e1"],
            AuditLog.action == "TRACKING_DATA_DELETED"))).scalars().all()
    assert len(a) == 1 and a[0].details == {"counts": {"pings": 2, "alerts": 1}}
    # consent survives my-data; delete_data=true revokes and erases
    assert (await client.get(f"{T}/my-status", headers=h)).json()["consented"] is True
    await _post(client, h, [_ping(5)])
    r = await client.delete(f"{T}/consent?delete_data=true", headers=h)
    assert r.json()["revoked"] is True and r.json()["deleted"]["pings"] == 1
    assert (await client.get(f"{T}/my-status", headers=h)).json()["consented"] is False
    assert (await client.get(f"{T}/my-trail", headers=h)).json()["points"] == []


async def test_field_now_view_audited(client, world):
    await _ready(client, world)
    head = await _login(client, world, "head")
    await client.get(f"{T}/field-now?department={world['dx']}", headers=head)
    async with SessionLocal() as db:
        rows = (await db.execute(select(AuditLog).where(
            AuditLog.user_id == world["ids"]["head"],
            AuditLog.action == "TRACKING_FIELD_NOW_VIEWED"))).scalars().all()
    assert len(rows) == 1
    assert rows[0].details == {"department": world["dx"], "count": 1}


async def test_view_audit_throttled(client, world):
    i = world["ids"]
    he1 = await _ready(client, world, "e1")
    await _post(client, he1, [_ping(8), _ping(2)])
    head = await _login(client, world, "head")
    today = _now().date().isoformat()
    for _ in range(3):
        assert (await client.get(f"{T}/field-now", headers=head)).status_code == 200
        assert (await client.get(f"{T}/trail?user_id={i['e1']}&date={today}",
                                 headers=head)).status_code == 200

    async def count(action):
        async with SessionLocal() as db:
            return len((await db.execute(select(AuditLog).where(
                AuditLog.user_id == i["head"],
                AuditLog.action == action))).scalars().all())

    assert await count("TRACKING_FIELD_NOW_VIEWED") == 1
    assert await count("TRACKING_TRAIL_VIEWED") == 1
    # an older audit row no longer suppresses a new one
    async with SessionLocal() as db:
        for a in ("TRACKING_FIELD_NOW_VIEWED", "TRACKING_TRAIL_VIEWED"):
            for r in (await db.execute(select(AuditLog).where(
                    AuditLog.user_id == i["head"],
                    AuditLog.action == a))).scalars().all():
                r.created_at = _now() - timedelta(minutes=11)
        await db.commit()
    await client.get(f"{T}/field-now", headers=head)
    await client.get(f"{T}/trail?user_id={i['e1']}&date={today}", headers=head)
    assert await count("TRACKING_FIELD_NOW_VIEWED") == 2
    assert await count("TRACKING_TRAIL_VIEWED") == 2
