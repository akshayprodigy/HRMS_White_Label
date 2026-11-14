"""Biometric HR API (Roadmap v2 Phase 4, Task 5).

DB-backed on the real dev DB, far-future dates (2031), full teardown."""
import asyncio
import time
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, insert, select

from app.api import deps
from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.main import create_app
from app.models.attendance import Attendance
from app.models.audit import AuditLog
from app.models.biometric import (
    BiometricDevice, BiometricDeviceStatus as DS, BiometricDeviceUser,
    BiometricPunch, BiometricPunchState as S, BiometricUserMap,
)
from app.models.employee import Employee, EmployeeStatus
from app.models.notification import Notification
from app.models.user import Role, User, user_roles
from app.services import biometric as bio

P = "/api/v1/biometric"


def at(d: date, hh: int, mm: int = 0) -> datetime:
    return datetime(d.year, d.month, d.day, hh, mm, tzinfo=timezone.utc)


@pytest.fixture
async def world():
    sfx = uuid.uuid4().hex[:8]
    ids: dict = {"sfx": sfx}
    try:
        async with SessionLocal() as db:
            us = {}
            for n in ("hr", "a", "b", "c", "inact", "ghost"):
                us[n] = User(email=f"bapi_{n}_{sfx}@t.com",
                             full_name=f"Bapi {n} {sfx}",
                             hashed_password=get_password_hash("x"),
                             is_active=(n != "inact"))
            db.add_all(us.values())
            await db.commit()
            role = (await db.execute(
                select(Role).where(Role.name == "HR"))).scalars().first()
            assert role is not None, "HR role missing"
            await db.execute(insert(user_roles).values(
                user_id=us["hr"].id, role_id=role.id))
            for n in ("a", "b", "c"):
                db.add(Employee(
                    user_id=us[n].id, employee_id=f"BA{sfx}{n}",
                    department="T", designation="T",
                    date_of_joining=date(2020, 1, 1),
                    status=EmployeeStatus.ACTIVE))
            devs = {}
            for n, st in (("act", DS.ACTIVE), ("pend", DS.PENDING),
                          ("other", DS.ACTIVE)):
                devs[n] = BiometricDevice(
                    serial=f"BAPI{sfx}{n}", utc_offset_minutes=330, status=st)
            db.add_all(devs.values())
            await db.commit()
            ids.update({n: u.id for n, u in us.items()})
            ids.update({f"d_{n}": d.id for n, d in devs.items()})
        yield ids
    finally:
        async with SessionLocal() as db:
            uids = list((await db.execute(select(User.id).where(
                User.email.like(f"bapi\\_%\\_{sfx}@t.com")))).scalars().all())
            dids = list((await db.execute(select(BiometricDevice.id).where(
                BiometricDevice.serial.like(f"BAPI{sfx}%")))).scalars().all())
            await db.execute(delete(BiometricPunch).where(
                BiometricPunch.pin.like(f"%{sfx}%")))
            if dids:
                await db.execute(delete(BiometricPunch).where(
                    BiometricPunch.device_id.in_(dids)))
            await db.execute(delete(BiometricUserMap).where(
                BiometricUserMap.pin.like(f"%{sfx}%")))
            await db.execute(delete(Attendance).where(
                Attendance.user_id.in_(uids)))
            await db.execute(delete(Notification).where(
                Notification.user_id.in_(uids)))
            await db.execute(delete(AuditLog).where(
                AuditLog.user_id.in_(uids)))
            if dids:
                await db.execute(delete(BiometricDevice).where(
                    BiometricDevice.id.in_(dids)))
            await db.execute(delete(Employee).where(
                Employee.user_id.in_(uids)))
            await db.execute(delete(user_roles).where(
                user_roles.c.user_id.in_(uids)))
            await db.execute(delete(User).where(User.id.in_(uids)))
            await db.commit()


async def _login(c, email, pw="x"):
    r = await c.post("/api/v1/auth/login",
                     data={"username": email, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
async def api(world):
    app = create_app()
    app.dependency_overrides[deps.verify_attendance] = lambda: None
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as c:
        c.hr = await _login(c, f"bapi_hr_{world['sfx']}@t.com")
        yield c


async def store(world, dev_key, pin, times):
    async with SessionLocal() as db:
        dev = await db.get(BiometricDevice, world[dev_key])
        await bio.store_taps(db, source="adms", device=dev,
                             taps=[(pin, t, "0", "1", "raw") for t in times])
        await db.commit()


async def states(pin):
    async with SessionLocal() as db:
        return sorted((await db.execute(select(BiometricPunch.state).where(
            BiometricPunch.pin == pin))).scalars().all())


# ---------------- permission matrix ----------------

async def test_403_matrix_and_hr_ok(api, world):
    from app.api.v1.endpoints.biometric import router as bio_router
    routes = []
    for rt in bio_router.routes:
        path = rt.path.replace("{device_id}", str(world["d_act"])).replace(
            "{map_id}", "1")
        for m in rt.methods:
            routes.append((m, path, {}))
    assert len(routes) >= 12, routes
    d = world["d_act"]
    for email in ("employee@gmail.com", "pm@gmail.com"):
        h = await _login(api, email, "test@12345")
        for m, path, body in routes:
            r = await api.request(m, P + path, headers=h, json=body)
            assert r.status_code == 403, (email, m, path, r.status_code)
    # no auth at all
    assert (await api.get(P + "/devices")).status_code in (401, 403)
    for path in ("/devices", "/mappings", "/punches",
                 f"/devices/{d}/users"):
        r = await api.get(P + path, headers=api.hr)
        assert r.status_code == 200, (path, r.text)
    r = await api.post(P + "/punches/reprocess", headers=api.hr,
                       json={"state": "error"})
    assert r.status_code == 200 and "backfill" in r.json()


# ---------------- devices ----------------

async def test_list_health_and_counts(api, world):
    sfx = world["sfx"]
    now = datetime.now(timezone.utc)
    async with SessionLocal() as db:
        for key, seen, st in (("d_act", now, DS.ACTIVE),
                              ("d_pend", now - timedelta(hours=2), DS.ACTIVE),
                              ("d_other", None, DS.ACTIVE)):
            d = await db.get(BiometricDevice, world[key])
            d.last_seen_at, d.status = seen, st
        db.add_all([BiometricDeviceUser(device_id=world["d_act"], pin=f"{sfx}1"),
                    BiometricDeviceUser(device_id=world["d_act"], pin=f"{sfx}2")])
        await db.commit()
    await store(world, "d_act", f"{sfx}u1", [at(date(2031, 5, 1), 9)])
    await store(world, "d_act", f"{sfx}u1", [at(date(2031, 5, 1), 10)])
    await store(world, "d_act", f"{sfx}u2", [at(date(2031, 5, 1), 11)])
    r = await api.get(P + "/devices", headers=api.hr)
    by = {x["id"]: x for x in r.json()}
    assert by[world["d_act"]]["health"] == "online"
    assert by[world["d_pend"]]["health"] == "offline"
    assert by[world["d_other"]]["health"] == "never"
    assert by[world["d_act"]]["enrolled_users"] == 2
    assert by[world["d_act"]]["unmapped_pins"] == 2
    assert by[world["d_act"]]["pending_punches"] == 0
    r = await api.post(f"{P}/devices/{world['d_other']}/disable", headers=api.hr)
    assert r.status_code == 200 and r.json()["health"] == "disabled"
    assert (await api.post(f"{P}/devices/{world['d_other']}/disable",
                           headers=api.hr)).status_code == 409
    async with SessionLocal() as db:
        n = (await db.execute(select(AuditLog).where(
            AuditLog.action == "BIOMETRIC_DEVICE_DISABLED",
            AuditLog.resource_id == str(world["d_other"])))).scalars().all()
        assert len(n) == 1


async def test_patch_validation(api, world):
    u = f"{P}/devices/{world['d_act']}"
    for bad in ({"utc_offset_minutes": 841}, {"utc_offset_minutes": -721},
                {"ip_allowlist": ["10.0.0.1", "nope"]},
                {"ip_allowlist": "300.1.1.1"},
                {"ip_allowlist": ["10.0.%d.0/24" % i for i in range(60)]},
                {"name": "x" * 121}, {"location_note": "x" * 201}):
        r = await api.patch(u, headers=api.hr, json=bad)
        assert r.status_code == 422, (bad, r.status_code)
    r = await api.patch(u, headers=api.hr, json={
        "name": " Gate ", "utc_offset_minutes": 0,
        "ip_allowlist": ["10.0.0.5", "192.168.1.7/24", "10.0.0.5"],
        "location_note": "main gate"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["name"] == "Gate" and j["utc_offset_minutes"] == 0
    assert j["ip_allowlist"] == "10.0.0.5/32,192.168.1.0/24"
    r = await api.patch(u, headers=api.hr, json={"ip_allowlist": ""})
    assert r.json()["ip_allowlist"] is None and r.json()["name"] == "Gate"
    assert (await api.patch(f"{P}/devices/99999999", headers=api.hr,
                            json={"name": "x"})).status_code == 404


async def test_approve_backfills_pending_taps(api, world):
    sfx, d = world["sfx"], date(2031, 5, 2)
    pin = f"{sfx}ap"
    async with SessionLocal() as db:
        db.add(BiometricUserMap(device_id=None, pin=pin, user_id=world["a"]))
        await db.commit()
    await store(world, "d_pend", pin, [at(d, 9), at(d, 18)])
    assert await states(pin) == [S.PENDING_DEVICE] * 2
    r = await api.get(P + "/devices", headers=api.hr)
    assert {x["id"]: x for x in r.json()}[world["d_pend"]]["pending_punches"] == 2
    r = await api.post(f"{P}/devices/{world['d_pend']}/approve", headers=api.hr)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["device"]["status"] == "active" and j["backfill"].get("applied", 0) >= 1
    assert S.APPLIED in await states(pin)
    async with SessionLocal() as db:
        dev = await db.get(BiometricDevice, world["d_pend"])
        assert dev.approved_by_id == world["hr"] and dev.approved_at
    assert j["remaining"] == 0 and "next_after_id" in j
    assert j["device"]["enrolled_users"] == 0 and \
        j["device"]["pending_punches"] == 0
    assert (await api.post(f"{P}/devices/{world['d_pend']}/approve",
                           headers=api.hr)).status_code == 409


async def test_delete_device(api, world):
    sfx, d = world["sfx"], date(2031, 5, 3)
    # junk pending device with held taps: deletes, taps go too
    await store(world, "d_pend", f"{sfx}junk", [at(d, 9)])
    r = await api.delete(f"{P}/devices/{world['d_pend']}", headers=api.hr)
    assert r.status_code == 200, r.text
    assert await states(f"{sfx}junk") == []
    # device with applied punches -> 409
    pin = f"{sfx}del"
    async with SessionLocal() as db:
        db.add(BiometricUserMap(device_id=None, pin=pin, user_id=world["b"]))
        await db.commit()
    await store(world, "d_act", pin, [at(d, 9)])
    await bio.apply_pending(SessionLocal, pin=pin)
    assert S.APPLIED in await states(pin)
    r = await api.delete(f"{P}/devices/{world['d_act']}", headers=api.hr)
    assert r.status_code == 409 and "Disable" in r.text  # active
    await api.post(f"{P}/devices/{world['d_act']}/disable", headers=api.hr)
    r = await api.delete(f"{P}/devices/{world['d_act']}", headers=api.hr)
    assert r.status_code == 409  # applied taps
    assert (await api.delete(f"{P}/devices/99999999",
                             headers=api.hr)).status_code == 404


# ---------------- mappings ----------------

async def test_mapping_upsert_conflict_replace(api, world):
    sfx, d = world["sfx"], date(2031, 5, 4)
    pin = f"{sfx}m1"
    await store(world, "d_act", pin, [at(d, 9), at(d, 17)])
    await store(world, "d_other", pin, [at(d, 10)])  # other device, same pin
    assert await states(pin) == [S.UNMAPPED] * 3
    body = {"device_id": None, "pin": pin, "user_id": world["a"]}
    r = await api.put(P + "/mappings", headers=api.hr, json=body)
    assert r.status_code == 200, r.text
    # global mapping back-fills taps from every device
    assert await states(pin) == [S.APPLIED, S.APPLIED, S.DUPLICATE] or \
        S.UNMAPPED not in await states(pin)
    j = r.json()["mapping"]
    assert j["user_id"] == world["a"] and j["employee_code"] == f"BA{sfx}a"
    # same user again: idempotent
    assert (await api.put(P + "/mappings", headers=api.hr,
                          json=body)).status_code == 200
    # different user: 409 unless replace
    r = await api.put(P + "/mappings", headers=api.hr,
                      json={**body, "user_id": world["b"]})
    assert r.status_code == 409
    r = await api.put(P + "/mappings", headers=api.hr,
                      json={**body, "user_id": world["b"], "replace": True})
    assert r.status_code == 200 and r.json()["mapping"]["user_id"] == world["b"]
    # device-specific mapping may differ from the global one
    r = await api.put(P + "/mappings", headers=api.hr, json={
        "device_id": world["d_act"], "pin": pin, "user_id": world["c"]})
    assert r.status_code == 200
    # unchanged: no extra audit, no back-fill
    async with SessionLocal() as db:
        n0 = len((await db.execute(select(AuditLog.id).where(
            AuditLog.action == "BIOMETRIC_MAPPING_SET",
            AuditLog.user_id == world["hr"]))).scalars().all())
    r = await api.put(P + "/mappings", headers=api.hr, json={
        "device_id": world["d_act"], "pin": pin, "user_id": world["c"]})
    assert r.status_code == 200 and r.json()["backfill"] == {}
    async with SessionLocal() as db:
        n1 = len((await db.execute(select(AuditLog.id).where(
            AuditLog.action == "BIOMETRIC_MAPPING_SET",
            AuditLog.user_id == world["hr"]))).scalars().all())
    assert n0 == n1
    # list + filter
    r = await api.get(P + "/mappings", headers=api.hr, params={"q": pin})
    assert len(r.json()) == 2
    r = await api.get(P + "/mappings", headers=api.hr,
                      params={"device_id": world["d_act"], "q": pin})
    assert len(r.json()) == 1
    # delete
    mid = r.json()[0]["id"]
    assert (await api.delete(f"{P}/mappings/{mid}",
                             headers=api.hr)).status_code == 200
    assert (await api.delete(f"{P}/mappings/{mid}",
                             headers=api.hr)).status_code == 404
    async with SessionLocal() as db:
        acts = (await db.execute(select(AuditLog.action).where(
            AuditLog.user_id == world["hr"],
            AuditLog.action.like("BIOMETRIC_MAPPING%")))).scalars().all()
    assert "BIOMETRIC_MAPPING_SET" in acts and "BIOMETRIC_MAPPING_DELETED" in acts


async def test_mapping_validation(api, world):
    sfx = world["sfx"]
    ok = {"pin": f"{sfx}v", "user_id": world["a"]}
    for bad in ({**ok, "user_id": world["inact"]}, {**ok, "user_id": 99999999},
                {**ok, "pin": "bad pin!"}, {**ok, "pin": "x" * 33},
                {**ok, "device_id": 99999999}):
        r = await api.put(P + "/mappings", headers=api.hr, json=bad)
        assert r.status_code in (400, 404, 422), (bad, r.status_code, r.text)
    r = await api.put(P + "/mappings", headers=api.hr,
                      json={**ok, "pin": "bad pin!"})
    assert r.status_code == 400


async def test_concurrent_mapping_puts(api, world):
    sfx = world["sfx"]
    for i in range(4):
        pin = f"{sfx}cc{i}"
        dev = None if i % 2 else world["d_act"]
        rs = await asyncio.gather(*[
            api.put(P + "/mappings", headers=api.hr,
                    json={"device_id": dev, "pin": pin, "user_id": world[u]})
            for u in ("a", "b")])
        codes = sorted(r.status_code for r in rs)
        assert codes == [200, 409], (codes, [r.text for r in rs])
    async with SessionLocal() as db:
        n = (await db.execute(select(BiometricUserMap).where(
            BiometricUserMap.pin.like(f"{sfx}cc%")))).scalars().all()
    assert len(n) == 4


async def test_suggestions_and_auto_map(api, world):
    sfx, d = world["sfx"], date(2031, 5, 5)
    dev = world["d_act"]
    async with SessionLocal() as db:
        # a: by employee code; b: by name; c: ambiguous name; ghost: nothing
        db.add_all([
            BiometricDeviceUser(device_id=dev, pin=f"BA{sfx}a", name="zzz"),
            BiometricDeviceUser(device_id=dev, pin=f"{sfx}n2",
                                name=f"BAPI B {sfx}"),
            BiometricDeviceUser(device_id=dev, pin=f"{sfx}n3",
                                name=f"bapi c {sfx}"),
            BiometricDeviceUser(device_id=dev, pin=f"{sfx}n4",
                                name=f"Bapi c {sfx}"),
            BiometricDeviceUser(device_id=dev, pin=f"{sfx}n5", name="Nobody"),
        ])
        await db.commit()
    r = await api.get(f"{P}/devices/{dev}/users", headers=api.hr)
    by = {x["pin"]: x for x in r.json() if sfx in x["pin"]}
    assert by[f"BA{sfx}a"]["suggested_user_id"] == world["a"]
    assert by[f"BA{sfx}a"]["suggested_employee_code"] == f"BA{sfx}a"
    assert by[f"{sfx}n2"]["suggested_user_id"] == world["b"]
    # same user suggested for two pins -> ambiguous, neither suggested
    assert by[f"{sfx}n3"]["suggested_user_id"] is None
    assert by[f"{sfx}n4"]["suggested_user_id"] is None
    assert by[f"{sfx}n5"]["suggested_user_id"] is None
    assert all(x["mapping"] is None for x in by.values())
    await store(world, "d_act", f"BA{sfx}a", [at(d, 9), at(d, 18)])
    r = await api.post(P + "/mappings/auto", headers=api.hr,
                       json={"device_id": dev})
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 2 and r.json()["backfill"].get("applied", 0) >= 1
    assert S.UNMAPPED not in await states(f"BA{sfx}a")
    r = await api.get(f"{P}/devices/{dev}/users", headers=api.hr)
    by = {x["pin"]: x for x in r.json() if sfx in x["pin"]}
    m = by[f"BA{sfx}a"]["mapping"]
    assert m["scope"] == "device" and m["user_id"] == world["a"]
    # second run creates nothing
    r = await api.post(P + "/mappings/auto", headers=api.hr,
                       json={"device_id": dev})
    assert r.json()["created"] == 0
    # a user already mapped (b) is never suggested again for another pin
    async with SessionLocal() as db:
        db.add(BiometricDeviceUser(device_id=dev, pin=f"{sfx}n6",
                                   name=f"Bapi b {sfx}"))
        await db.commit()
    r = await api.get(f"{P}/devices/{dev}/users", headers=api.hr)
    by = {x["pin"]: x for x in r.json() if sfx in x["pin"]}
    assert by[f"{sfx}n6"]["suggested_user_id"] is None


# ---------------- punch log / reprocess ----------------

async def test_punch_log_filters_and_paging(api, world):
    sfx, d = world["sfx"], date(2031, 5, 6)
    pin, pin2 = f"{sfx}pl", f"{sfx}pm"
    async with SessionLocal() as db:
        db.add(BiometricUserMap(device_id=None, pin=pin, user_id=world["c"]))
        await db.commit()
    await store(world, "d_act", pin, [at(d, h) for h in (9, 12, 18)])
    await store(world, "d_other", pin2, [at(d, 10)])
    await bio.apply_pending(SessionLocal, pin=pin)
    g = lambda **p: api.get(P + "/punches", headers=api.hr, params=p)
    r = await g(pin=pin)
    j = r.json()
    assert j["total"] == 3 and len(j["items"]) == 3
    times = [x["punch_time"] for x in j["items"]]
    assert times == sorted(times, reverse=True)
    it = j["items"][0]
    assert it["device_serial"] == f"BAPI{sfx}act" and it["user_name"]
    assert it["employee_code"] == f"BA{sfx}c"
    r = await g(pin=pin, limit=2, offset=2)
    assert r.json()["total"] == 3 and len(r.json()["items"]) == 1
    assert (await g(pin=pin2)).json()["items"][0]["user_name"] is None
    assert (await g(device_id=world["d_other"], pin=pin2)).json()["total"] == 1
    assert (await g(pin=pin2, state="applied")).json()["total"] == 0
    assert (await g(pin=pin2, state="unmapped")).json()["total"] == 1
    assert (await g(user_id=world["c"], pin=pin)).json()["total"] == 3
    r = await g(pin=pin, **{"from": at(d, 10).isoformat(),
                            "to": at(d, 18).isoformat()})
    assert r.json()["total"] == 1
    assert (await g(state="bogus")).status_code == 422
    assert (await g(limit=201)).status_code == 422
    assert (await g(limit=0)).status_code == 422


async def test_reprocess_locked(api, world, monkeypatch):
    sfx, d = world["sfx"], date(2031, 5, 7)
    pin = f"{sfx}rp"
    async with SessionLocal() as db:
        db.add(BiometricUserMap(device_id=None, pin=pin, user_id=world["a"]))
        await db.commit()

    async def locked(db, wd, fresh=False):
        raise HTTPException(status_code=409, detail="locked")
    with monkeypatch.context() as mp:
        mp.setattr(bio, "assert_attendance_editable", locked)
        await store(world, "d_act", pin, [at(d, 9), at(d, 18)])
        await bio.apply_pending(SessionLocal, pin=pin,
                                states={bio.PENDING_APPLY})
        assert await states(pin) == [S.LOCKED] * 2
        # still locked: reprocess keeps them locked
        r = await api.post(P + "/punches/reprocess", headers=api.hr,
                           json={"state": "locked", "device_id": world["d_act"]})
        assert r.status_code == 200
        assert await states(pin) == [S.LOCKED] * 2
    r = await api.post(P + "/punches/reprocess", headers=api.hr,
                       json={"state": "locked", "device_id": world["d_act"]})
    assert r.status_code == 200, r.text
    assert S.LOCKED not in await states(pin)
    assert S.APPLIED in await states(pin)
    assert (await api.post(P + "/punches/reprocess", headers=api.hr,
                           json={"state": "applied"})).status_code == 422
    async with SessionLocal() as db:
        n = (await db.execute(select(AuditLog).where(
            AuditLog.action == "BIOMETRIC_REPROCESS",
            AuditLog.user_id == world["hr"]))).scalars().all()
    assert len(n) >= 2


# ---------------- review fixes ----------------

async def test_like_wildcards_escaped(api, world):
    sfx = world["sfx"]
    async with SessionLocal() as db:
        db.add_all([BiometricUserMap(device_id=None, pin=f"{sfx}w1", user_id=world["a"]),
                    BiometricUserMap(device_id=None, pin=f"{sfx}w2", user_id=world["a"])])
        await db.commit()
    for q in ("_", "%"):
        r = await api.get(P + "/mappings", headers=api.hr, params={"q": q})
        assert r.status_code == 200
        # none of our pins / names contain a literal _ or %, so no match
        assert not [x for x in r.json() if sfx in x["pin"]], q
    r = await api.get(P + "/mappings", headers=api.hr, params={"q": f"{sfx}w_"})
    assert r.json() == []  # '_' is literal, not "any char"


async def test_global_mapping_backfills_two_devices_and_import(api, world):
    sfx, d = world["sfx"], date(2031, 6, 1)
    pin = f"{sfx}gl"
    await store(world, "d_act", pin, [at(d, 9)])
    await store(world, "d_other", pin, [at(d, 12)])
    async with SessionLocal() as db:
        await bio.store_taps(db, source="import", device=None,
                             taps=[(pin, at(d, 18), None, None, "csv")],
                             import_batch=uuid.uuid4().hex)
        await db.commit()
    assert await states(pin) == [S.UNMAPPED] * 3
    r = await api.put(P + "/mappings", headers=api.hr, json={
        "device_id": None, "pin": pin, "user_id": world["a"]})
    assert r.status_code == 200 and r.json()["remaining"] == 0
    assert S.UNMAPPED not in await states(pin)
    async with SessionLocal() as db:
        rows = (await db.execute(select(BiometricPunch).where(
            BiometricPunch.pin == pin))).scalars().all()
    assert {x.source for x in rows} == {"adms", "import"} or \
        {x.source for x in rows} >= {"import"}
    assert all(x.user_id == world["a"] for x in rows)


async def test_apply_pending_keyset_paging(world):
    sfx, d = world["sfx"], date(2031, 6, 2)
    # 3 unmappable pins first (lowest ids), then 7 mappable taps
    junk = [f"{sfx}j{i}" for i in range(3)]
    for p in junk:
        await store(world, "d_act", p, [at(d, 8)])
    pin = f"{sfx}pg"
    await store(world, "d_act", pin, [at(d, 9, m) for m in range(7)])
    async with SessionLocal() as db:
        db.add(BiometricUserMap(device_id=None, pin=pin, user_id=world["a"]))
        await db.commit()
    kw = dict(device_id=world["d_act"], limit=2)
    # deadline 0 -> stops after the first page; remaining > 0
    r1 = await bio.apply_pending(SessionLocal, deadline_s=0, **kw)
    assert sum(r1["counts"].values()) == 2 and r1["remaining"] > 0
    # continue until done; unmappable rows never block later mappable ones
    cursor, total, guard = r1["next_after_id"], dict(r1["counts"]), 0
    while True:
        r = await bio.apply_pending(SessionLocal, after_id=cursor,
                                    deadline_s=0, **kw)
        for k, v in r["counts"].items():
            total[k] = total.get(k, 0) + v
        cursor = r["next_after_id"]
        guard += 1
        if r["remaining"] == 0 or guard > 20:
            break
    assert r["remaining"] == 0 and guard <= 20
    st = await states(pin)
    assert S.UNMAPPED not in st and len(st) == 7
    for p in junk:
        assert await states(p) == [S.UNMAPPED]
    # one unbounded call from scratch: junk rows remain but are passed over
    r = await bio.apply_pending(SessionLocal, **kw)
    assert r["remaining"] == 0 and r["counts"].get(S.UNMAPPED, 0) == 3


async def test_reprocess_after_id_continues(api, world):
    sfx, d = world["sfx"], date(2031, 6, 3)
    pin = f"{sfx}ra"
    await store(world, "d_act", pin, [at(d, 9, m) for m in range(5)])
    async with SessionLocal() as db:
        db.add(BiometricUserMap(device_id=None, pin=pin, user_id=world["b"]))
        await db.commit()
    # tiny page via direct call, then finish through the endpoint
    r = await bio.apply_pending(SessionLocal, pin=pin, limit=2, deadline_s=0)
    assert r["remaining"] == 3
    r = await api.post(P + "/punches/reprocess", headers=api.hr, json={
        "state": "pending", "pin": pin, "after_id": r["next_after_id"]})
    assert r.status_code == 200, r.text
    assert r.json()["remaining"] == 0
    assert S.UNMAPPED not in await states(pin)


async def test_approve_vs_attlog_race(api, world):
    sfx = world["sfx"]
    async with SessionLocal() as db:
        db.add(BiometricUserMap(device_id=None, pin=f"{sfx}rc", user_id=world["a"]))
        await db.commit()
    for i in range(4):
        async with SessionLocal() as db:
            dev = BiometricDevice(serial=f"BAPI{sfx}r{i}", utc_offset_minutes=0,
                                  status=DS.PENDING,
                                  last_seen_at=datetime.now(timezone.utc))
            db.add(dev)
            await db.commit()
            did = dev.id
        # one pre-held tap so approve has work, then race approve vs attlog
        await store_dev(did, f"{sfx}rc", [datetime(2031, 7, 1, 1, i, tzinfo=timezone.utc)])
        t = f"2031-07-02 0{i}:30:00"
        body = f"{sfx}rc\t{t}\t0\t1\t0\t0\t0\t0\t0\t0\n"
        ra, rb = await asyncio.gather(
            api.post(f"{P}/devices/{did}/approve", headers=api.hr),
            api.post("/iclock/cdata", params={"SN": f"BAPI{sfx}r{i}",
                                              "table": "ATTLOG", "Stamp": "1"},
                     content=body))
        assert ra.status_code == 200, ra.text
        assert rb.status_code == 200, rb.text
        async with SessionLocal() as db:
            held = (await db.execute(select(BiometricPunch.id).where(
                BiometricPunch.device_id == did,
                BiometricPunch.state == S.PENDING_DEVICE))).scalars().all()
            allp = (await db.execute(select(BiometricPunch.id).where(
                BiometricPunch.device_id == did))).scalars().all()
        assert held == [] and len(allp) == 2, (i, held, allp)


async def store_dev(did, pin, times):
    async with SessionLocal() as db:
        dev = await db.get(BiometricDevice, did)
        await bio.store_taps(db, source="adms", device=dev,
                             taps=[(pin, t, "0", "1", "raw") for t in times])
        await db.commit()


async def test_mapping_pin_newline_rejected(api, world):
    r = await api.put(P + "/mappings", headers=api.hr,
                      json={"pin": f"{world['sfx']}n\nx", "user_id": world["a"]})
    assert r.status_code in (400, 422), r.text
