"""Selfie punch + offline punch sync (Roadmap v2 Phase 3, Task 2)."""
import asyncio
import uuid
from datetime import date, datetime, time, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, insert, select

from _cleanup import purge_shift_templates
from app.core.config import settings
from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.main import create_app
from app.models.payroll import PayrollRun, PayrollRunStatus
from app.models.attendance import Attendance, AttendanceSelfie
from app.models.audit import AuditLog
from app.models.comp_off import CompOffAccrual
from app.models.department import Department
from app.models.employee import Employee, EmployeeStatus
from app.models.geofence import (
    EmployeeGeoConfig, EmployeeGeoFenceLink, GeoFenceLocation,
)
from app.models.notification import Notification
from app.models.roster import RosterEntry, RosterEntryHistory, RosterStatus
from app.models.shift import ShiftTemplate
from app.models.system import SystemSetting
from app.models.user import (
    Permission, Role, User, role_permissions, user_roles,
)
from app.services.selfie_lifecycle import purge_selfies
from app.services.time_rules import get_time_rules, set_time_rules

API = settings.API_V1_STR
ATT = f"{API}/attendance"
PW = "test@12345"
TODAY = datetime.now(timezone.utc).date()
IN_FENCE = (22.5726, 88.3639)
OUT_FENCE = (22.6200, 88.4000)
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


@pytest.fixture(autouse=True)
def _selfie_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "ATTENDANCE_SELFIE_DIR", str(tmp_path / "selfies"))
    yield tmp_path / "selfies"


@pytest.fixture
async def client():
    app = create_app()  # NOTE: attendance gate deliberately NOT overridden
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as c:
        yield c


@pytest.fixture
async def world():
    sfx = uuid.uuid4().hex[:8]
    made_perm, fence_id = [], None
    try:
        async with SessionLocal() as db:
            role = Role(name=f"SOR{sfx}", description="t")
            db.add(role)
            await db.flush()
            p = (await db.execute(select(Permission).where(
                Permission.name == "hr employee read"))).scalar_one_or_none()
            if p is None:
                p = Permission(name="hr employee read", description="t")
                db.add(p)
                await db.flush()
                made_perm.append(p.id)
            await db.execute(insert(role_permissions).values(
                role_id=role.id, permission_id=p.id))
            us = {t: User(email=f"so_{t}_{sfx}@t.com", full_name=f"SO {t}",
                          hashed_password=get_password_hash(PW), is_active=True)
                  for t in ("e1", "e2", "e3", "other", "hr")}
            db.add_all(us.values())
            tpl = ShiftTemplate(name=f"SOT{sfx}", start_time=time(9),
                                end_time=time(17))
            fence = GeoFenceLocation(
                name=f"SOF{sfx}", latitude=IN_FENCE[0], longitude=IN_FENCE[1],
                radius_meters=200, is_active=True)
            db.add_all([tpl, fence])
            await db.commit()
            fence_id = fence.id
            await db.execute(insert(user_roles).values(
                user_id=us["hr"].id, role_id=role.id))
            for t in ("e1", "e2", "e3"):
                db.add(Employee(
                    user_id=us[t].id, employee_id=f"SO{sfx}{t}",
                    department=f"SOD{sfx}", designation="T",
                    date_of_joining=date(2015, 1, 1),
                    status=EmployeeStatus.ACTIVE))
                for dd in (-1, 0, 1):
                    db.add(RosterEntry(
                        employee_id=us[t].id, work_date=TODAY + timedelta(days=dd),
                        shift_template_id=tpl.id, is_week_off=False,
                        status=RosterStatus.PUBLISHED))
                # e1/e2 flag-only geofence, e3 strict (offline STRICT reject)
                db.add(EmployeeGeoConfig(
                    user_id=us[t].id, geo_enabled=True,
                    enforcement_mode="strict" if t == "e3" else "allow_with_flag"))
            await db.commit()
            for t in ("e1", "e2", "e3"):
                db.add(EmployeeGeoFenceLink(
                    user_id=us[t].id, geofence_location_id=fence_id))
            await db.commit()
            ids = {t: u.id for t, u in us.items()}
            ids["tpl"] = tpl.id
        yield {"ids": ids, "sfx": sfx, "email": lambda t: f"so_{t}_{sfx}@t.com"}
    finally:
        async with SessionLocal() as db:
            uids = list((await db.execute(select(User.id).where(
                User.email.like(f"so\\_%\\_{sfx}@t.com")))).scalars().all())
            tids = list((await db.execute(select(ShiftTemplate.id).where(
                ShiftTemplate.name == f"SOT{sfx}"))).scalars().all())
            aids = [str(i) for i in (await db.execute(select(Attendance.id).where(
                Attendance.user_id.in_(uids)))).scalars().all()]
            if aids:
                await db.execute(delete(Notification).where(
                    Notification.resource_type == "attendance",
                    Notification.resource_id.in_(aids)))
                await db.execute(delete(AuditLog).where(
                    AuditLog.resource_type == "attendance",
                    AuditLog.resource_id.in_(aids)))
                await db.execute(delete(CompOffAccrual).where(
                    CompOffAccrual.user_id.in_(uids)))
            await db.execute(delete(Notification).where(
                Notification.user_id.in_(uids)))
            await db.execute(delete(AuditLog).where(AuditLog.user_id.in_(uids)))
            await db.execute(delete(Attendance).where(
                Attendance.user_id.in_(uids)))
            await db.execute(delete(AttendanceSelfie).where(
                AttendanceSelfie.user_id.in_(uids)))
            await db.execute(delete(EmployeeGeoFenceLink).where(
                EmployeeGeoFenceLink.user_id.in_(uids)))
            await db.execute(delete(EmployeeGeoConfig).where(
                EmployeeGeoConfig.user_id.in_(uids)))
            if fence_id:
                await db.execute(delete(GeoFenceLocation).where(
                    GeoFenceLocation.id == fence_id))
            await db.execute(delete(RosterEntryHistory).where(
                RosterEntryHistory.employee_id.in_(uids)))
            await db.execute(delete(RosterEntry).where(
                RosterEntry.employee_id.in_(uids)))
            await db.execute(delete(Employee).where(Employee.user_id.in_(uids)))
            await purge_shift_templates(db, tids)
            await db.execute(delete(user_roles).where(
                user_roles.c.user_id.in_(uids)))
            await db.execute(delete(User).where(User.id.in_(uids)))
            rl = list((await db.execute(select(Role.id).where(
                Role.name == f"SOR{sfx}"))).scalars().all())
            await db.execute(delete(role_permissions).where(
                role_permissions.c.role_id.in_(rl)))
            await db.execute(delete(Role).where(Role.id.in_(rl)))
            if made_perm:
                await db.execute(delete(Permission).where(
                    Permission.id.in_(made_perm)))
            await db.commit()


@pytest.fixture
async def rules():
    """Set time rules for a test and restore the stored values afterwards."""
    keys = ("attendance.selfie_required", "attendance.offline_max_hours",
            "attendance.selfie_retention_days")
    async with SessionLocal() as db:
        before = {k: await db.get(SystemSetting, k) for k in keys}
        saved = {k: (v.value if v else None) for k, v in before.items()}

    async def setter(**kw):
        async with SessionLocal() as db:
            await set_time_rules(db, {f"attendance.{k}": v for k, v in kw.items()})
    yield setter
    async with SessionLocal() as db:
        for k, v in saved.items():
            row = await db.get(SystemSetting, k)
            if v is None and row is not None:
                await db.delete(row)
            elif v is not None and row is not None:
                row.value = v
        await db.commit()


async def _login(client, email):
    r = await client.post(f"{API}/auth/login",
                          data={"username": email, "password": PW})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _selfie(client, h, data=PNG, ctype="image/png", name="s.png"):
    return await client.post(f"{ATT}/selfie", headers=h,
                             files={"file": (name, data, ctype)})


def _msg(r):
    return str(r.json()["error"]["message"]).lower()


def iso(dt):
    return dt.isoformat()


def _off(kind, when, *, uid=None, pt=IN_FENCE, **kw):
    return {"client_uuid": uid or uuid.uuid4().hex, "kind": kind,
            "captured_at": iso(when), "latitude": pt[0], "longitude": pt[1],
            "accuracy": 10.0, **kw}


async def _rows(uid):
    async with SessionLocal() as db:
        return list((await db.execute(select(Attendance).where(
            Attendance.user_id == uid).order_by(Attendance.captured_at)))
            .scalars().all())


# --- selfie upload ------------------------------------------------------


async def test_selfie_upload_validation(client, world, _selfie_dir, monkeypatch):
    h = await _login(client, world["email"]("e1"))
    r = await _selfie(client, h, b"GIF89a....", "image/gif", "x.gif")
    assert r.status_code == 400
    r = await _selfie(client, h, b"not really a png at all", "image/png")
    assert r.status_code == 400  # magic bytes mismatch
    r = await _selfie(client, h, b"", "image/png")
    assert r.status_code == 400
    monkeypatch.setattr(settings, "ATTENDANCE_SELFIE_MAX_BYTES", 1000)
    r = await _selfie(client, h, PNG + b"\x00" * 2000)
    assert r.status_code == 413
    monkeypatch.setattr(settings, "ATTENDANCE_SELFIE_MAX_BYTES", 3 * 1024 * 1024)
    assert [p for p in _selfie_dir.iterdir()] == []  # rejects left no files
    for data, ct in ((PNG, "image/png"), (JPG, "image/jpeg"),
                     (b"RIFF\x00\x00\x00\x00WEBPVP8 ", "image/webp")):
        r = await _selfie(client, h, data, ct)
        assert r.status_code == 200, r.text
        assert r.json()["selfie_id"] > 0
    assert len(list(_selfie_dir.iterdir())) == 3
    r = await client.post(f"{ATT}/selfie",
                          files={"file": ("s.png", PNG, "image/png")})
    assert r.status_code in (401, 403)


async def test_selfie_only_uploader_can_attach_once(client, world):
    h1 = await _login(client, world["email"]("e1"))
    h2 = await _login(client, world["email"]("e2"))
    sid = (await _selfie(client, h2)).json()["selfie_id"]
    r = await client.post(f"{ATT}/mark", headers=h1, json={
        "mode": "mobile", "selfie_id": sid})
    assert r.status_code == 400 and "selfie" in _msg(r)
    assert await _rows(world["ids"]["e1"]) == []  # nothing created
    own = (await _selfie(client, h1)).json()["selfie_id"]
    r = await client.post(f"{ATT}/mark", headers=h1, json={
        "mode": "mobile", "selfie_id": own})
    assert r.status_code == 200 and r.json()["has_selfie"] is True
    assert "selfie_url" not in r.json()
    r = await client.post(f"{ATT}/punch-out", headers=h1, json={"selfie_id": own})
    assert r.status_code == 400  # single use
    assert (await client.post(f"{ATT}/mark", headers=h1, json={
        "mode": "mobile", "selfie_id": 99999999})).status_code == 200  # existing row returned


async def test_selfie_required_rule(client, world, rules):
    await rules(selfie_required="1")
    h = await _login(client, world["email"]("e1"))
    r = await client.post(f"{ATT}/mark", headers=h, json={"mode": "mobile"})
    assert r.status_code == 400 and "selfie" in _msg(r)
    s1 = (await _selfie(client, h)).json()["selfie_id"]
    r = await client.post(f"{ATT}/mark", headers=h, json={
        "mode": "mobile", "selfie_id": s1})
    assert r.status_code == 200
    r = await client.post(f"{ATT}/punch-out", headers=h, json={})
    assert r.status_code == 400 and "selfie" in _msg(r)
    s2 = (await _selfie(client, h, JPG, "image/jpeg")).json()["selfie_id"]
    r = await client.post(f"{ATT}/punch-out", headers=h, json={"selfie_id": s2})
    assert r.status_code == 200 and r.json()["has_punch_out_selfie"] is True
    await rules(selfie_required="1")
    h2 = await _login(client, world["email"]("e2"))
    # web punches are exempt from the selfie rule
    assert (await client.post(f"{ATT}/mark", headers=h2, json={
        "mode": "office"})).status_code == 200
    await rules(selfie_required="0")
    h2 = await _login(client, world["email"]("e2"))
    assert (await client.post(f"{ATT}/mark", headers=h2, json={
        "mode": "mobile"})).status_code == 200  # rule off: no selfie needed


async def test_selfie_required_applies_to_offline_items(client, world, rules):
    await rules(selfie_required="1")
    h = await _login(client, world["email"]("e1"))
    now = datetime.now(timezone.utc)
    r = await client.post(f"{ATT}/offline-sync", headers=h, json={
        "punches": [_off("in", now - timedelta(minutes=5))]})
    assert r.json()["results"][0]["status"] == "rejected"
    assert "selfie" in r.json()["results"][0]["reason"].lower()


async def test_time_rule_validation(world):
    async with SessionLocal() as db:
        for key, bad in (("attendance.selfie_required", "2"),
                         ("attendance.offline_max_hours", "0"),
                         ("attendance.offline_max_hours", "73"),
                         ("attendance.offline_max_hours", "abc"),
                         ("attendance.selfie_retention_days", "3651"),
                         ("attendance.selfie_retention_days", "-1")):
            with pytest.raises(ValueError):
                await set_time_rules(db, {key: bad})
        rules = await get_time_rules(db)
    assert "attendance.selfie_required" in rules
    assert "attendance.offline_max_hours" in rules


async def test_liveness_flag_and_review_listing(client, world):
    he1 = await _login(client, world["email"]("e1"))
    he2 = await _login(client, world["email"]("e2"))
    hhr = await _login(client, world["email"]("hr"))
    r = await client.post(f"{ATT}/mark", headers=he1, json={
        "mode": "mobile", "latitude": IN_FENCE[0], "longitude": IN_FENCE[1],
        "accuracy": 10, "liveness_passed": False, "liveness_score": 0.2})
    assert r.status_code == 200
    assert r.json()["review_flag"] == "liveness_failed"
    assert r.json()["liveness_passed"] is False
    r = await client.post(f"{ATT}/mark", headers=he2, json={
        "mode": "mobile", "latitude": IN_FENCE[0], "longitude": IN_FENCE[1],
        "accuracy": 10, "liveness_passed": True, "liveness_score": 0.9})
    assert r.json()["review_flag"] is None
    r = await client.get(f"{ATT}/flagged", headers=hhr, params={
        "date_from": str(TODAY - timedelta(days=2)), "date_to": str(TODAY + timedelta(days=2)),
        "flag_kind": "review"})
    assert r.status_code == 200
    mine = [x for x in r.json() if x["user_id"] in (world["ids"]["e1"], world["ids"]["e2"])]
    assert [x["user_id"] for x in mine] == [world["ids"]["e1"]]
    assert mine[0]["review_flag"] == "liveness_failed"
    r = await client.get(f"{ATT}/flagged", headers=hhr, params={
        "review_flag": "liveness_failed",
        "date_from": str(TODAY - timedelta(days=2)), "date_to": str(TODAY + timedelta(days=2))})
    assert world["ids"]["e1"] in [x["user_id"] for x in r.json()]
    # liveness failure on punch-out flags the row too
    r = await client.post(f"{ATT}/punch-out", headers=he2, json={
        "latitude": IN_FENCE[0], "longitude": IN_FENCE[1], "accuracy": 10,
        "liveness_passed": False})
    assert r.json()["review_flag"] == "liveness_failed"
    assert r.json()["punch_out_liveness_passed"] is False


async def test_selfie_view_permissions(client, world):
    he1 = await _login(client, world["email"]("e1"))
    hhr = await _login(client, world["email"]("hr"))
    hot = await _login(client, world["email"]("other"))
    sid = (await _selfie(client, he1)).json()["selfie_id"]
    att = (await client.post(f"{ATT}/mark", headers=he1, json={
        "mode": "mobile", "selfie_id": sid})).json()
    for h in (he1, hhr):
        r = await client.get(f"{ATT}/{att['id']}/selfie", headers=h)
        assert r.status_code == 200 and r.content == PNG
        assert r.headers["content-type"] == "image/png"
        assert r.headers["x-content-type-options"] == "nosniff"
    async with SessionLocal() as db:
        n = (await db.execute(select(AuditLog).where(
            AuditLog.action == "SELFIE_VIEW",
            AuditLog.resource_id == str(att["id"])))).scalars().all()
    assert sorted(x.user_id for x in n) == sorted(
        [world["ids"]["e1"], world["ids"]["hr"]])
    assert (await client.get(f"{ATT}/{att['id']}/selfie", headers=hot)).status_code == 404
    assert (await client.get(f"{ATT}/{att['id']}/selfie", headers=he1,
                             params={"side": "out"})).status_code == 404
    assert (await client.get(f"{ATT}/99999999/selfie", headers=he1)).status_code == 404


# --- offline sync -------------------------------------------------------


async def test_offline_in_out_one_batch_ordering(client, world):
    h = await _login(client, world["email"]("e1"))
    now = datetime.now(timezone.utc)
    i, o = _off("in", now - timedelta(hours=3)), _off("out", now - timedelta(hours=1))
    # Out listed first; the server must process by captured_at (in first).
    r = await client.post(f"{ATT}/offline-sync", headers=h, json={"punches": [o, i]})
    assert r.status_code == 200, r.text
    res = r.json()["results"]
    assert [x["client_uuid"] for x in res] == [o["client_uuid"], i["client_uuid"]]
    assert [x["status"] for x in res] == ["created", "created"]
    assert res[0]["attendance_id"] == res[1]["attendance_id"]
    (row,) = await _rows(world["ids"]["e1"])
    assert row.is_offline and row.review_flag == "offline"
    assert row.client_uuid == i["client_uuid"]
    assert row.punch_out_client_uuid == o["client_uuid"]
    assert row.punch_out_time is not None
    assert r.json()["counts"] == {"created": 2}


async def test_offline_idempotent_by_client_uuid(client, world):
    h = await _login(client, world["email"]("e1"))
    now = datetime.now(timezone.utc)
    i, o = _off("in", now - timedelta(hours=3)), _off("out", now - timedelta(hours=1))
    first = await client.post(f"{ATT}/offline-sync", headers=h, json={"punches": [i, o]})
    again = await client.post(f"{ATT}/offline-sync", headers=h, json={"punches": [i, o]})
    assert [x["status"] for x in again.json()["results"]] == ["duplicate", "duplicate"]
    assert again.json()["results"][0]["attendance_id"] == first.json()["results"][0]["attendance_id"]
    assert len(await _rows(world["ids"]["e1"])) == 1
    # same uuid twice inside one request: created once, then duplicate
    h2 = await _login(client, world["email"]("e2"))
    k = _off("in", now - timedelta(minutes=2))
    r = await client.post(f"{ATT}/offline-sync", headers=h2, json={"punches": [k, k]})
    assert [x["status"] for x in r.json()["results"]] == ["created", "duplicate"]
    assert len(await _rows(world["ids"]["e2"])) == 1


async def test_offline_client_uuid_cannot_collide_across_users(client, world):
    h1 = await _login(client, world["email"]("e1"))
    h2 = await _login(client, world["email"]("e2"))
    now = datetime.now(timezone.utc)
    i = _off("in", now - timedelta(hours=2))
    await client.post(f"{ATT}/offline-sync", headers=h1, json={"punches": [i]})
    r = await client.post(f"{ATT}/offline-sync", headers=h2, json={"punches": [i]})
    assert r.json()["results"][0]["status"] == "rejected"
    assert r.json()["results"][0]["reason"] == "invalid_client_uuid"
    assert r.json()["results"][0]["attendance_id"] is None
    assert await _rows(world["ids"]["e2"]) == []


async def test_offline_window(client, world, rules):
    h = await _login(client, world["email"]("e1"))
    now = datetime.now(timezone.utc)
    r = await client.post(f"{ATT}/offline-sync", headers=h, json={"punches": [
        _off("in", now - timedelta(hours=13)),
        _off("in", now + timedelta(minutes=10)),
    ]})
    st = [(x["status"], x["reason"]) for x in r.json()["results"]]
    assert st == [("rejected", "captured_too_old"),
                  ("rejected", "captured_in_future")]
    assert await _rows(world["ids"]["e1"]) == []
    # window honours the time rule: 13h old accepted once max is 24h
    await rules(offline_max_hours="24")
    r = await client.post(f"{ATT}/offline-sync", headers=h, json={"punches": [
        _off("in", now - timedelta(hours=13))]})
    assert r.json()["results"][0]["status"] == "created"
    # within 2-minute skew accepted
    h2 = await _login(client, world["email"]("e2"))
    r = await client.post(f"{ATT}/offline-sync", headers=h2, json={"punches": [
        _off("in", datetime.now(timezone.utc) + timedelta(seconds=60))]})
    assert r.json()["results"][0]["status"] == "created"


async def test_offline_batch_size_limit(client, world):
    h = await _login(client, world["email"]("e1"))
    now = datetime.now(timezone.utc)
    big = [_off("in", now - timedelta(minutes=1)) for _ in range(51)]
    assert (await client.post(f"{ATT}/offline-sync", headers=h,
                              json={"punches": big})).status_code == 422
    assert (await client.post(f"{ATT}/offline-sync", headers=h,
                              json={"punches": []})).status_code == 422


async def test_offline_punch_out_needs_open_punch(client, world):
    h = await _login(client, world["email"]("e1"))
    now = datetime.now(timezone.utc)
    r = await client.post(f"{ATT}/offline-sync", headers=h, json={"punches": [
        _off("out", now - timedelta(hours=1))]})
    x = r.json()["results"][0]
    assert x["status"] == "rejected" and "punched in" in x["reason"]
    # an open punch that started AFTER the out does not count
    await client.post(f"{ATT}/offline-sync", headers=h, json={"punches": [
        _off("in", now - timedelta(minutes=10))]})
    r = await client.post(f"{ATT}/offline-sync", headers=h, json={"punches": [
        _off("out", now - timedelta(minutes=30))]})
    x = r.json()["results"][0]
    assert x["status"] == "rejected" and "before" in x["reason"]
    # a LIVE punch-in is a valid open punch for an offline punch-out
    h2 = await _login(client, world["email"]("e2"))
    await client.post(f"{ATT}/mark", headers=h2, json={"mode": "web"})
    r = await client.post(f"{ATT}/offline-sync", headers=h2, json={"punches": [
        _off("out", datetime.now(timezone.utc) + timedelta(seconds=60))]})
    assert r.json()["results"][0]["status"] == "created"
    (row,) = await _rows(world["ids"]["e2"])
    assert row.is_offline and row.review_flag == "offline"
    assert row.client_uuid is None and row.punch_out_client_uuid is not None


async def test_offline_second_punch_in_same_day_rejected(client, world):
    h = await _login(client, world["email"]("e1"))
    now = datetime.now(timezone.utc)
    await client.post(f"{ATT}/mark", headers=h, json={"mode": "web"})
    r = await client.post(f"{ATT}/offline-sync", headers=h, json={"punches": [
        _off("in", datetime.now(timezone.utc) - timedelta(minutes=1))]})
    x = r.json()["results"][0]
    assert x["status"] == "rejected" and x["reason"] == "already_punched_in"
    assert len(await _rows(world["ids"]["e1"])) == 1


async def test_offline_attribution_parity_with_live(client, world):
    """Identical inputs through live mark/punch-out and offline-sync must
    yield identical attribution / geofence / flag fields."""
    h1 = await _login(client, world["email"]("e1"))
    h2 = await _login(client, world["email"]("e2"))
    now = datetime.now(timezone.utc)
    live = await client.post(f"{ATT}/mark", headers=h1, json={
        "mode": "mobile", "latitude": OUT_FENCE[0], "longitude": OUT_FENCE[1],
        "accuracy": 12.0, "is_mock_location": True})
    assert live.status_code == 200
    r = await client.post(f"{ATT}/offline-sync", headers=h2, json={"punches": [
        _off("in", datetime.now(timezone.utc) - timedelta(seconds=5),
             pt=OUT_FENCE, accuracy=12.0, is_mock_location=True)]})
    assert r.json()["results"][0]["status"] == "created"
    lo = await client.post(f"{ATT}/punch-out", headers=h1, json={
        "latitude": IN_FENCE[0], "longitude": IN_FENCE[1], "accuracy": 8.0})
    assert lo.status_code == 200
    r = await client.post(f"{ATT}/offline-sync", headers=h2, json={"punches": [
        _off("out", datetime.now(timezone.utc), pt=IN_FENCE, accuracy=8.0)]})
    assert r.json()["results"][0]["status"] == "created"
    (a,), (b,) = await _rows(world["ids"]["e1"]), await _rows(world["ids"]["e2"])
    for f in ("work_date", "shift_template_id", "is_cross_midnight",
              "attribution_flag", "is_mock_location", "geo_flag",
              "matched_fence_id", "distance_to_fence_meters", "accuracy",
              "punch_out_geo_flag", "punch_out_matched_fence_id",
              "punch_out_distance_to_fence_meters", "punch_out_is_mock"):
        assert getattr(a, f) == getattr(b, f), f
    assert a.geo_flag is not None and a.is_mock_location
    assert a.is_offline is False and b.is_offline is True
    # same notifications (geo flag) generated for both punch-ins
    async with SessionLocal() as db:
        n = {u: len((await db.execute(select(Notification).where(
            Notification.resource_type == "attendance",
            Notification.resource_id == str(r_id)))).scalars().all())
            for u, r_id in (("a", a.id), ("b", b.id))}
    assert n["a"] == n["b"]


async def test_offline_strict_geo_reject_is_reported_and_audited(client, world):
    h = await _login(client, world["email"]("e3"))
    now = datetime.now(timezone.utc)
    r = await client.post(f"{ATT}/offline-sync", headers=h, json={"punches": [
        _off("in", now - timedelta(hours=1), pt=OUT_FENCE),
        _off("in", now - timedelta(minutes=30), pt=IN_FENCE),
    ]})
    res = r.json()["results"]
    assert res[0]["status"] == "rejected" and res[0]["reason"]
    assert res[1]["status"] == "created"  # one bad item doesn't sink the batch
    async with SessionLocal() as db:
        n = (await db.execute(select(AuditLog).where(
            AuditLog.user_id == world["ids"]["e3"],
            AuditLog.action == "STRICT_GEO_REJECT_PUNCH_IN"))).scalars().all()
    assert len(n) == 1


async def test_offline_selfie_and_liveness_flag_in_review(client, world):
    he1 = await _login(client, world["email"]("e1"))
    hhr = await _login(client, world["email"]("hr"))
    sid = (await _selfie(client, he1)).json()["selfie_id"]
    now = datetime.now(timezone.utc)
    r = await client.post(f"{ATT}/offline-sync", headers=he1, json={"punches": [
        _off("in", now - timedelta(hours=2), selfie_id=sid, liveness_passed=False)]})
    assert r.json()["results"][0]["status"] == "created"
    (row,) = await _rows(world["ids"]["e1"])
    assert row.selfie_url and row.review_flag == "liveness_failed" and row.is_offline
    r = await client.get(f"{ATT}/flagged", headers=hhr, params={
        "date_from": str(TODAY - timedelta(days=2)), "date_to": str(TODAY + timedelta(days=2))})
    mine = [x for x in r.json() if x["user_id"] == world["ids"]["e1"]]
    assert len(mine) == 1
    assert mine[0]["is_offline"] is True and mine[0]["has_selfie"] is True
    assert mine[0]["review_flag"] == "liveness_failed"
    r = await client.get(f"{ATT}/flagged", headers=hhr, params={
        "review_flag": "offline",
        "date_from": str(TODAY - timedelta(days=2)), "date_to": str(TODAY + timedelta(days=2))})
    assert world["ids"]["e1"] in [x["user_id"] for x in r.json()]


async def test_offline_rows_listed_in_flagged_default(client, world):
    he2 = await _login(client, world["email"]("e2"))
    hhr = await _login(client, world["email"]("hr"))
    now = datetime.now(timezone.utc)
    await client.post(f"{ATT}/offline-sync", headers=he2, json={"punches": [
        _off("in", now - timedelta(hours=2))]})
    r = await client.get(f"{ATT}/flagged", headers=hhr, params={
        "date_from": str(TODAY - timedelta(days=2)), "date_to": str(TODAY + timedelta(days=2))})
    got = [x for x in r.json() if x["user_id"] == world["ids"]["e2"]]
    assert got and got[0]["review_flag"] == "offline"


async def test_live_mark_unchanged_idempotent(client, world):
    h = await _login(client, world["email"]("e1"))
    a = await client.post(f"{ATT}/mark", headers=h, json={"mode": "web"})
    b = await client.post(f"{ATT}/mark", headers=h, json={"mode": "web"})
    assert a.status_code == b.status_code == 200 and a.json()["id"] == b.json()["id"]
    assert a.json()["is_offline"] is False and a.json()["review_flag"] is None
    out = await client.post(f"{ATT}/punch-out", headers=h)
    assert out.status_code == 200 and out.json()["punch_out_time"]
    again = await client.post(f"{ATT}/punch-out", headers=h)
    assert again.status_code == 400


async def test_live_mark_ignores_client_captured_at(client, world):
    h = await _login(client, world["email"]("e1"))
    before = datetime.now(timezone.utc)
    r = await client.post(f"{ATT}/mark", headers=h, json={
        "mode": "web", "captured_at": iso(before - timedelta(days=3))})
    assert r.status_code == 200
    (row,) = await _rows(world["ids"]["e1"])
    cap = row.captured_at if row.captured_at.tzinfo else row.captured_at.replace(tzinfo=timezone.utc)
    assert cap >= before - timedelta(seconds=2)  # server time, not -3 days
    assert row.device_captured_at is not None  # kept for diagnostics only
    assert row.is_offline is False


async def test_offline_payroll_lock(client, world):
    h = await _login(client, world["email"]("e1"))
    now = datetime.now(timezone.utc)
    h2 = await _login(client, world["email"]("e2"))
    await client.post(f"{ATT}/mark", headers=h2, json={"mode": "web"})  # open punch
    async with SessionLocal() as db:
        run = PayrollRun(month=now.month, year=now.year,
                         status=PayrollRunStatus.LEAVES_LOCKED)
        db.add(run)
        await db.commit()
        run_id = run.id
    try:
        r = await client.post(f"{ATT}/offline-sync", headers=h, json={"punches": [
            _off("in", now - timedelta(minutes=30))]})
        assert [(x["status"], x["reason"]) for x in r.json()["results"]] == [
            ("rejected", "payroll_locked")]
        assert await _rows(world["ids"]["e1"]) == []
        r = await client.post(f"{ATT}/offline-sync", headers=h2, json={"punches": [
            _off("out", datetime.now(timezone.utc) + timedelta(seconds=30))]})
        assert [(x["status"], x["reason"]) for x in r.json()["results"]] == [
            ("rejected", "payroll_locked")]
        assert (await _rows(world["ids"]["e2"]))[0].punch_out_time is None
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(PayrollRun).where(PayrollRun.id == run_id))
            await db.commit()


async def test_concurrent_live_and_offline_make_one_row(client, world):
    h = await _login(client, world["email"]("e1"))
    for _ in range(3):  # a few rounds to shake out the race
        await asyncio.gather(
            client.post(f"{ATT}/mark", headers=h, json={"mode": "web"}),
            client.post(f"{ATT}/mark", headers=h, json={"mode": "web"}),
            client.post(f"{ATT}/offline-sync", headers=h, json={"punches": [
                _off("in", datetime.now(timezone.utc) - timedelta(seconds=3))]}),
        )
        assert len(await _rows(world["ids"]["e1"])) == 1
        async with SessionLocal() as db:
            await db.execute(delete(Attendance).where(
                Attendance.user_id == world["ids"]["e1"]))
            await db.commit()


async def test_offline_row_has_synced_at(client, world):
    h = await _login(client, world["email"]("e1"))
    now = datetime.now(timezone.utc)
    await client.post(f"{ATT}/offline-sync", headers=h, json={"punches": [
        _off("in", now - timedelta(hours=1))]})
    (row,) = await _rows(world["ids"]["e1"])
    assert row.synced_at is not None and row.device_captured_at is not None


async def test_upload_rate_limit(client, world):
    h = await _login(client, world["email"]("e1"))
    for _ in range(20):
        assert (await _selfie(client, h)).status_code == 200
    assert (await _selfie(client, h)).status_code == 429
    h2 = await _login(client, world["email"]("e2"))
    assert (await _selfie(client, h2)).status_code == 200  # per user


async def test_selfie_purge_unattached_and_retention(client, world, rules, _selfie_dir):
    h = await _login(client, world["email"]("e1"))
    h2 = await _login(client, world["email"]("e2"))
    old = (await _selfie(client, h)).json()["selfie_id"]
    fresh = (await _selfie(client, h)).json()["selfie_id"]
    att_sid = (await _selfie(client, h2)).json()["selfie_id"]
    keep_sid = (await _selfie(client, h)).json()["selfie_id"]
    a = (await client.post(f"{ATT}/mark", headers=h2, json={
        "mode": "mobile", "selfie_id": att_sid})).json()
    async with SessionLocal() as db:
        row = await db.get(AttendanceSelfie, old)
        row.created_at = datetime.now(timezone.utc) - timedelta(hours=49)
        await db.commit()
    async with SessionLocal() as db:
        res = await purge_selfies(db)
    assert res["unattached_deleted"] >= 1
    async with SessionLocal() as db:
        assert await db.get(AttendanceSelfie, old) is None
        assert await db.get(AttendanceSelfie, fresh) is not None
    assert len(list(_selfie_dir.iterdir())) == 3  # 4 uploaded - 1 purged
    # retention: punch older than N days loses its selfie file + url
    async with SessionLocal() as db:
        att = await db.get(Attendance, a["id"])
        att.captured_at = datetime.now(timezone.utc) - timedelta(days=100)
        await db.commit()
    async with SessionLocal() as db:
        await purge_selfies(db)
        att = await db.get(Attendance, a["id"])
        assert att.selfie_url is None
        assert await db.get(AttendanceSelfie, att_sid) is None
    assert len(list(_selfie_dir.iterdir())) == 2
    # retention 0 = keep forever
    s2 = (await _selfie(client, h2, JPG, "image/jpeg")).json()["selfie_id"]
    a2 = (await client.post(f"{ATT}/punch-out", headers=h2, json={"selfie_id": s2})).json()
    async with SessionLocal() as db:
        att = await db.get(Attendance, a2["id"])
        att.captured_at = datetime.now(timezone.utc) - timedelta(days=400)
        await db.commit()
    await rules(selfie_retention_days="0")
    async with SessionLocal() as db:
        await purge_selfies(db)
        assert (await db.get(Attendance, a2["id"])).punch_out_selfie_url
    del keep_sid
