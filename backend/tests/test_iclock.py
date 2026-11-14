"""ADMS /iclock endpoints (Roadmap v2 Phase 4, Task 4).

DB-backed on the real dev DB, far-future dates (2031), full teardown."""
import asyncio
import uuid
from datetime import date, datetime, time, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, insert, select, update

from _cleanup import purge_shift_templates
from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.main import create_app
from app.models.attendance import Attendance
from app.models.audit import AuditLog
from app.models.biometric import (
    BiometricDevice, BiometricDeviceStatus, BiometricDeviceUser,
    BiometricPunch, BiometricPunchState as S, BiometricUserMap,
)
from app.models.notification import Notification
from app.models.shift import EmployeeShiftAssignment, ShiftTemplate
from app.models.user import Role, User, user_roles
from app.core.datetime_utils import as_utc
from app.services import biometric as bio

D = date(2031, 1, 6)


async def _ap(*a, **k):
    return (await bio.apply_pending(*a, **k))["counts"]


@pytest.fixture
async def client():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as c:
        yield c


@pytest.fixture
async def world():
    sfx = uuid.uuid4().hex[:8]
    w = {"sfx": sfx, "pin": f"{sfx}1", "pin2": f"{sfx}2"}
    try:
        async with SessionLocal() as db:
            tpl = ShiftTemplate(name=f"ICT{sfx}", start_time=time(9),
                                end_time=time(18))
            emp = User(email=f"ic_emp_{sfx}@t.com", full_name="IC emp",
                       hashed_password=get_password_hash("x"), is_active=True)
            hr = User(email=f"ic_hr_{sfx}@t.com", full_name="IC hr",
                      hashed_password=get_password_hash("x"), is_active=True)
            db.add_all([tpl, emp, hr])
            await db.commit()
            role = (await db.execute(
                select(Role).where(Role.name == "HR"))).scalars().first()
            if role is not None:
                await db.execute(insert(user_roles).values(
                    user_id=hr.id, role_id=role.id))
            db.add(EmployeeShiftAssignment(
                employee_id=emp.id, shift_template_id=tpl.id,
                effective_from=date(2031, 1, 1)))
            await db.commit()
            w.update(emp=emp.id, hr=hr.id, tpl=tpl.id, has_hr=role is not None)
        yield w
    finally:
        async with SessionLocal() as db:
            uids = [w.get("emp"), w.get("hr")]
            uids = [u for u in uids if u]
            devs = list((await db.execute(select(BiometricDevice.id).where(
                BiometricDevice.serial.like(f"IC{sfx}%")))).scalars().all())
            await db.execute(delete(Notification).where(
                Notification.title == bio.CAP_ALERT_TITLE,
                Notification.created_at >= datetime.now(timezone.utc)
                - timedelta(minutes=30)))
            if devs:
                await db.execute(delete(Notification).where(
                    Notification.resource_type == "biometric_device",
                    Notification.resource_id.in_([str(d) for d in devs])))
            aids = [str(i) for i in (await db.execute(select(Attendance.id).where(
                Attendance.user_id.in_(uids)))).scalars().all()]
            if aids:
                await db.execute(delete(Notification).where(
                    Notification.resource_type == "attendance",
                    Notification.resource_id.in_(aids)))
                await db.execute(delete(AuditLog).where(
                    AuditLog.resource_type == "attendance",
                    AuditLog.resource_id.in_(aids)))
            await db.execute(delete(Notification).where(
                Notification.user_id.in_(uids)))
            await db.execute(delete(AuditLog).where(AuditLog.user_id.in_(uids)))
            await db.execute(delete(BiometricPunch).where(
                BiometricPunch.pin.like(f"{sfx}%")))
            await db.execute(delete(BiometricUserMap).where(
                BiometricUserMap.pin.like(f"{sfx}%")))
            await db.execute(delete(Attendance).where(Attendance.user_id.in_(uids)))
            if devs:
                await db.execute(delete(BiometricDeviceUser).where(
                    BiometricDeviceUser.device_id.in_(devs)))
                await db.execute(delete(BiometricDevice).where(
                    BiometricDevice.id.in_(devs)))
            await db.execute(delete(EmployeeShiftAssignment).where(
                EmployeeShiftAssignment.employee_id.in_(uids)))
            await purge_shift_templates(db, [w["tpl"]] if "tpl" in w else [])
            await db.execute(delete(User).where(User.id.in_(uids)))
            await db.commit()


def sn(w, tag):
    return f"IC{w['sfx']}{tag}"


def attlog(pin, day=D):
    # device clock == UTC (offset forced to 0 once approved)
    return (f"{pin}\t{day} 09:00:00\t0\t1\t0\t0\n"
            f"{pin}\t{day} 18:00:00\t1\t1\t0\t0\n")


async def _dev(serial):
    async with SessionLocal() as db:
        return (await db.execute(select(BiometricDevice).where(
            BiometricDevice.serial == serial))).scalars().first()


async def _set(serial, **vals):
    async with SessionLocal() as db:
        await db.execute(update(BiometricDevice).where(
            BiometricDevice.serial == serial).values(**vals))
        await db.commit()


async def _punches(pin):
    async with SessionLocal() as db:
        return list((await db.execute(select(BiometricPunch).where(
            BiometricPunch.pin == pin))).scalars().all())


async def _attendance(uid):
    async with SessionLocal() as db:
        return list((await db.execute(select(Attendance).where(
            Attendance.user_id == uid))).scalars().all())


async def _notifs(uid, device_serial):
    async with SessionLocal() as db:
        d = (await db.execute(select(BiometricDevice.id).where(
            BiometricDevice.serial == device_serial))).scalar()
        return list((await db.execute(select(Notification).where(
            Notification.user_id == uid,
            Notification.resource_type == "biometric_device",
            Notification.resource_id == str(d)))).scalars().all())


# ---------------- pure helpers ----------------

def test_client_ip_rule():
    f = bio.client_ip
    assert f("127.0.0.1", "203.0.113.5, 10.0.0.1") == "203.0.113.5"
    # spoofed leftmost private entry is never believed
    assert f("127.0.0.1", "10.0.0.5, 203.0.113.9") == "203.0.113.9"
    assert f("127.0.0.1", "203.0.113.1, 10.0.0.5, 198.51.100.2") == "198.51.100.2"
    assert f("127.0.0.1", "10.0.0.5, 192.168.1.1") == "192.168.1.1"  # all private: nearest hop
    assert f("172.18.0.4", "10.2.3.4") == "10.2.3.4"  # LAN device behind nginx
    assert f("127.0.0.1", "10.0.0.5, junk") == "127.0.0.1"
    assert f("10.1.2.3", "203.0.113.5") == "203.0.113.5"
    assert f("172.18.0.4", "198.51.100.7") == "198.51.100.7"
    assert f("8.8.8.8", "203.0.113.5") == "8.8.8.8"       # untrusted peer
    assert f("127.0.0.1", None) == "127.0.0.1"
    assert f("127.0.0.1", "garbage") == "127.0.0.1"
    assert f(None, "1.2.3.4") is None


def test_ip_allowed():
    assert bio.ip_allowed(None, "1.2.3.4")
    assert bio.ip_allowed("", "1.2.3.4")
    assert bio.ip_allowed("10.0.0.0/8", "10.5.5.5")
    assert not bio.ip_allowed("10.0.0.0/8", "11.5.5.5")
    assert bio.ip_allowed("192.168.1.5, 10.0.0.0/8", "192.168.1.5")
    assert not bio.ip_allowed("10.0.0.0/8", None)
    assert not bio.ip_allowed("10.0.0.0/8", "nope")


# ---------------- endpoints ----------------

async def test_handshake_registers_pending_and_notifies(client, world):
    s = sn(world, "a")
    r = await client.get("/iclock/cdata", params={"SN": s, "options": "all"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    assert f"GET OPTION FROM: {s}" in r.text
    dev = await _dev(s)
    assert dev.status == BiometricDeviceStatus.PENDING
    assert dev.last_seen_at is not None and dev.last_ip
    assert dev.utc_offset_minutes == 330
    if world["has_hr"]:
        assert len(await _notifs(world["hr"], s)) == 1
    # a second call neither re-registers nor re-notifies
    await client.get("/iclock/cdata", params={"SN": s})
    if world["has_hr"]:
        assert len(await _notifs(world["hr"], s)) == 1


async def test_pending_then_approved_flow_and_idempotency(client, world):
    s, pin, uid = sn(world, "b"), world["pin"], world["emp"]
    body = attlog(pin)
    r = await client.post("/iclock/cdata", params={"SN": s, "table": "ATTLOG",
                                                    "Stamp": "7"}, content=body)
    assert (r.status_code, r.text) == (200, "OK: 2")
    rows = await _punches(pin)
    assert len(rows) == 2 and {x.state for x in rows} == {S.PENDING_DEVICE}
    assert await _attendance(uid) == []
    assert (await _dev(s)).attlog_stamp == "7"
    # approve, map, then new taps are applied live
    await _set(s, status=BiometricDeviceStatus.ACTIVE, utc_offset_minutes=0)
    async with SessionLocal() as db:
        db.add(BiometricUserMap(device_id=None, pin=pin, user_id=uid))
        await db.commit()
    d2 = date(2031, 1, 7)
    r = await client.post("/iclock/cdata", params={"SN": s, "table": "ATTLOG"},
                          content=attlog(pin, d2))
    assert r.text == "OK: 2"
    att = [a for a in await _attendance(uid) if a.work_date == d2]
    assert len(att) == 1 and att[0].mode == "biometric"
    assert att[0].punch_out_time is not None
    # re-post: same count, no new rows
    n = len(await _punches(pin))
    r = await client.post("/iclock/cdata", params={"SN": s, "table": "ATTLOG"},
                          content=attlog(pin, d2))
    assert r.text == "OK: 2"
    assert len(await _punches(pin)) == n


async def test_ip_allowlist_403(client, world):
    s = sn(world, "c")
    await client.get("/iclock/cdata", params={"SN": s})
    await _set(s, ip_allowlist="10.0.0.0/8")
    before = (await _dev(s)).last_seen_at
    r = await client.get("/iclock/cdata", params={"SN": s},
                         headers={"X-Forwarded-For": "203.0.113.9"})
    assert (r.status_code, r.text) == (403, "ERROR")
    assert (await _dev(s)).last_seen_at == before
    r = await client.get("/iclock/cdata", params={"SN": s},
                         headers={"X-Forwarded-For": "10.2.3.4"})
    assert r.status_code == 200


async def test_disabled_device_ok_stores_nothing(client, world):
    s, pin = sn(world, "d"), world["pin"]
    await client.get("/iclock/cdata", params={"SN": s})
    from datetime import datetime, timedelta, timezone
    before = datetime.now(timezone.utc) - timedelta(hours=1)
    await _set(s, status=BiometricDeviceStatus.DISABLED, last_seen_at=before)
    r = await client.post("/iclock/cdata", params={"SN": s, "table": "ATTLOG"},
                          content=attlog(pin))
    assert (r.status_code, r.text) == (200, "OK")
    assert await _punches(pin) == []
    assert as_utc((await _dev(s)).last_seen_at) > before
    r = await client.get("/iclock/cdata", params={"SN": s})
    assert r.text == "OK"


@pytest.mark.parametrize("bad", ["", "a b", "x" * 65, "a/b", "é"])
async def test_bad_sn_400(client, bad):
    params = {"SN": bad} if bad else {}
    r = await client.get("/iclock/cdata", params=params)
    assert (r.status_code, r.text) == (400, "ERROR")


async def test_body_over_1mb_413(client, world):
    s = sn(world, "e")
    big = "x" * (1024 * 1024 + 10)
    r = await client.post("/iclock/cdata", params={"SN": s, "table": "ATTLOG"},
                          content=big)
    assert r.status_code == 413
    # chunked (no content-length) bodies are limited too
    async def gen():
        for _ in range(3):
            yield b"y" * (512 * 1024)
    r = await client.post("/iclock/cdata", params={"SN": s, "table": "ATTLOG"},
                          content=gen())
    assert r.status_code == 413


async def test_non_utf8_body_does_not_fail(client, world):
    s = sn(world, "f")
    body = ("USER PIN=" + world["pin"] + "\tName=").encode() + b"\xff\xfe\xe9\n"
    r = await client.post("/iclock/cdata", params={"SN": s, "table": "OPERLOG"},
                          content=body)
    assert r.status_code == 200 and r.text == "OK: 1"


async def test_operlog_upserts_users_and_ignores_fp(client, world):
    s, p1, p2 = sn(world, "g"), world["pin"], world["pin2"]
    body = (f"USER PIN={p1}\tName=Alice\tPri=0\n"
            f"FP PIN={p1}\tFID=0\tTMP=AAAA\n"
            f"USER PIN={p2}\tName=Bob\n")
    r = await client.post("/iclock/cdata", params={"SN": s, "table": "OPERLOG",
                                                    "Stamp": "5"}, content=body)
    assert r.text == "OK: 3"
    dev = await _dev(s)
    assert dev.operlog_stamp == "5"
    async with SessionLocal() as db:
        us = {u.pin: u.name for u in (await db.execute(select(
            BiometricDeviceUser).where(
            BiometricDeviceUser.device_id == dev.id))).scalars().all()}
    assert us == {p1: "Alice", p2: "Bob"}
    # upsert renames, no duplicates
    await client.post("/iclock/cdata", params={"SN": s, "table": "OPERLOG"},
                      content=f"USER PIN={p1}\tName=Alicia\n")
    async with SessionLocal() as db:
        us = {u.pin: u.name for u in (await db.execute(select(
            BiometricDeviceUser).where(
            BiometricDeviceUser.device_id == dev.id))).scalars().all()}
    assert us == {p1: "Alicia", p2: "Bob"}


async def test_other_table_getrequest_devicecmd(client, world):
    s = sn(world, "h")
    r = await client.post("/iclock/cdata", params={"SN": s, "table": "ATTPHOTO"},
                          content="whatever")
    assert r.text == "OK: 0"
    assert (await client.get("/iclock/getrequest", params={"SN": s})).text == "OK"
    assert (await client.post("/iclock/devicecmd", params={"SN": s},
                              content="ID=1&Return=0")).text == "OK"


async def test_back_online_notifies_once(client, world):
    if not world["has_hr"]:
        pytest.skip("no HR role")
    s = sn(world, "i")
    await client.get("/iclock/cdata", params={"SN": s})
    from datetime import datetime, timezone
    await _set(s, offline_alerted_at=datetime.now(timezone.utc))
    await asyncio.gather(*[client.get("/iclock/getrequest", params={"SN": s})
                           for _ in range(3)])
    assert (await _dev(s)).offline_alerted_at is None
    titles = [n.title for n in await _notifs(world["hr"], s)]
    assert titles.count("Biometric device back online") == 1


async def test_concurrent_first_handshakes_one_device_one_notification(
        client, world):
    s = sn(world, "j")
    rs = await asyncio.gather(*[
        client.get("/iclock/cdata", params={"SN": s}) for _ in range(8)])
    assert all(r.status_code == 200 and "GET OPTION FROM" in r.text for r in rs)
    async with SessionLocal() as db:
        n = (await db.execute(select(BiometricDevice).where(
            BiometricDevice.serial == s))).scalars().all()
    assert len(n) == 1
    if world["has_hr"]:
        assert len(await _notifs(world["hr"], s)) == 1


async def test_apply_failure_does_not_fail_response(client, world, monkeypatch):
    s, pin, uid = sn(world, "k"), world["pin"], world["emp"]
    await client.get("/iclock/cdata", params={"SN": s})
    await _set(s, status=BiometricDeviceStatus.ACTIVE, utc_offset_minutes=0)
    async with SessionLocal() as db:
        db.add(BiometricUserMap(device_id=None, pin=pin, user_id=uid))
        await db.commit()

    async def boom(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(bio, "apply_punch_committed", boom)
    r = await client.post("/iclock/cdata", params={"SN": s, "table": "ATTLOG"},
                          content=attlog(pin))
    assert (r.status_code, r.text) == (200, "OK: 2")
    assert {x.state for x in await _punches(pin)} == {bio.PENDING_APPLY}
    monkeypatch.undo()
    counts = await _ap(SessionLocal, pin=pin)
    assert sum(counts.values()) == 2
    assert len(await _attendance(uid)) == 1


async def test_spoofed_xff_cannot_pass_allowlist(client, world):
    s = sn(world, "l")
    await client.get("/iclock/cdata", params={"SN": s})
    await _set(s, ip_allowlist="10.0.0.0/8")
    # attacker prepends a private IP; the right-most untrusted hop is public
    r = await client.get("/iclock/cdata", params={"SN": s}, headers={
        "X-Forwarded-For": "10.0.0.5, 203.0.113.9"})
    assert (r.status_code, r.text) == (403, "ERROR")


async def test_pending_device_cap(client, world, monkeypatch):
    monkeypatch.setattr(bio, "MAX_PENDING_DEVICES", 0)
    s = sn(world, "m")
    for _ in range(2):
        r = await client.get("/iclock/cdata", params={"SN": s})
        assert (r.status_code, r.text) == (200, "OK")
    assert await _dev(s) is None
    async with SessionLocal() as db:
        n = (await db.execute(select(Notification).where(
            Notification.user_id == world["hr"],
            Notification.title == bio.CAP_ALERT_TITLE))).scalars().all()
    if world["has_hr"]:
        assert len(n) == 1  # throttled to one per hour


async def test_pending_taps_cap(client, world, monkeypatch):
    monkeypatch.setattr(bio, "MAX_PENDING_TAPS_PER_DEVICE", 2)
    s, pin = sn(world, "n"), world["pin"]
    r = await client.post("/iclock/cdata", params={"SN": s, "table": "ATTLOG"},
                          content=attlog(pin))
    assert r.text == "OK: 2" and len(await _punches(pin)) == 2
    r = await client.post("/iclock/cdata", params={"SN": s, "table": "ATTLOG"},
                          content=attlog(pin, date(2031, 1, 8)))
    assert r.text == "OK: 2" and len(await _punches(pin)) == 2


async def test_notify_failure_does_not_undo_device(client, world, monkeypatch):
    from sqlalchemy.exc import OperationalError
    from app.services import roster as roster_svc

    async def boom(*a, **k):
        raise OperationalError("x", {}, Exception(1020, "Record has changed"))
    monkeypatch.setattr(roster_svc, "notify_many", boom)
    s = sn(world, "o")
    r = await client.get("/iclock/cdata", params={"SN": s})
    assert r.status_code == 200 and f"GET OPTION FROM: {s}" in r.text
    assert (await _dev(s)) is not None
