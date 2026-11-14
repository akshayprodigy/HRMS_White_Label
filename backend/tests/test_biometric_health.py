"""Biometric device health jobs + time rules (Roadmap v2 Phase 4, Task 7).

DB-backed on the real dev DB, far-future dates (2031), full teardown."""
import random
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
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
from app.models.notification import Notification
from app.models.system import SystemSetting
from app.models.user import Role, User, user_roles
from app.services import biometric as bio
from app.services.time_rules import get_time_rules, set_time_rules

RULE_KEYS = ("biometric.offline_minutes", "biometric.default_utc_offset_minutes",
             "biometric.dedupe_seconds")
EXPIRED_ACTION = "BIOMETRIC_PENDING_DEVICES_EXPIRED"


def now():
    return datetime.now(timezone.utc)


def at(d: date, hh: int, mm: int = 0) -> datetime:
    return datetime(d.year, d.month, d.day, hh, mm, tzinfo=timezone.utc)


@pytest.fixture
async def world():
    sfx = uuid.uuid4().hex[:8]
    ids: dict = {"sfx": sfx}
    saved = {}
    try:
        async with SessionLocal() as db:
            for k in RULE_KEYS:
                row = await db.get(SystemSetting, k)
                saved[k] = row.value if row else None
            us = {n: User(email=f"bhl_{n}_{sfx}@t.com", full_name=f"Bhl {n}",
                          hashed_password=get_password_hash("x"), is_active=True)
                  for n in ("hr", "u1", "u2")}
            db.add_all(us.values())
            await db.commit()
            role = (await db.execute(
                select(Role).where(Role.name == "HR"))).scalars().first()
            assert role is not None, "HR role missing"
            await db.execute(insert(user_roles).values(
                user_id=us["hr"].id, role_id=role.id))
            await db.commit()
            ids.update({n: u.id for n, u in us.items()})
        yield ids
    finally:
        async with SessionLocal() as db:
            devs = list((await db.execute(select(BiometricDevice.id).where(
                BiometricDevice.serial.like(f"BHL{sfx}%")))).scalars().all())
            uids = list((await db.execute(select(User.id).where(
                User.email.like(f"bhl\\_%\\_{sfx}@t.com")))).scalars().all())
            aids = [str(i) for i in (await db.execute(select(Attendance.id).where(
                Attendance.user_id.in_(uids)))).scalars().all()]
            if aids:
                await db.execute(delete(Notification).where(
                    Notification.resource_type == "attendance",
                    Notification.resource_id.in_(aids)))
                await db.execute(delete(AuditLog).where(
                    AuditLog.resource_type == "attendance",
                    AuditLog.resource_id.in_(aids)))
            if devs:  # notifications to REAL HR users, by device id
                await db.execute(delete(Notification).where(
                    Notification.resource_type == "biometric_device",
                    Notification.resource_id.in_([str(i) for i in devs])))
                await db.execute(delete(AuditLog).where(
                    AuditLog.resource_type == "biometric_device",
                    AuditLog.resource_id.in_([str(i) for i in devs])))
            for a in (await db.execute(select(AuditLog).where(
                    AuditLog.action == EXPIRED_ACTION))).scalars().all():
                if sfx in str(a.details):
                    await db.delete(a)
            await db.execute(delete(Notification).where(
                Notification.user_id.in_(uids)))
            await db.execute(delete(AuditLog).where(AuditLog.user_id.in_(uids)))
            await db.execute(delete(BiometricPunch).where(
                BiometricPunch.pin.like(f"{sfx}%")))
            await db.execute(delete(BiometricUserMap).where(
                BiometricUserMap.pin.like(f"{sfx}%")))
            await db.execute(delete(Attendance).where(
                Attendance.user_id.in_(uids)))
            if devs:
                await db.execute(delete(BiometricDeviceUser).where(
                    BiometricDeviceUser.device_id.in_(devs)))
                await db.execute(delete(BiometricPunch).where(
                    BiometricPunch.device_id.in_(devs)))
                await db.execute(delete(BiometricDevice).where(
                    BiometricDevice.id.in_(devs)))
            for k, v in saved.items():
                row = await db.get(SystemSetting, k)
                if v is None and row is not None:
                    await db.delete(row)
                elif v is not None and row is not None:
                    row.value = v
                elif v is not None:
                    db.add(SystemSetting(key=k, value=v))
            await db.execute(delete(user_roles).where(
                user_roles.c.user_id.in_(uids)))
            await db.execute(delete(User).where(User.id.in_(uids)))
            await db.commit()


async def mkdev(world, tag, *, status=DS.ACTIVE, seen=None, created=None,
                approved=None, ip=None):
    async with SessionLocal() as db:
        d = BiometricDevice(
            serial=f"BHL{world['sfx']}{tag}", status=status,
            utc_offset_minutes=330, last_seen_at=seen, last_ip=ip,
            approved_at=approved)
        if created is not None:
            d.created_at = created
        db.add(d)
        await db.commit()
        return d.id


async def dev_row(dev_id):
    async with SessionLocal() as db:
        d = await db.get(BiometricDevice, dev_id)
        await db.refresh(d)
        return d


async def run_alerts(world):
    async with SessionLocal() as db:
        return await bio.offline_alerts_job(
            db, serial_prefix=f"BHL{world['sfx']}")


async def offline_notifs(dev_id, title="Biometric device offline"):
    async with SessionLocal() as db:
        return list((await db.execute(select(Notification).where(
            Notification.resource_type == "biometric_device",
            Notification.resource_id == str(dev_id),
            Notification.title == title))).scalars().all())


# ---------------- offline alerts ----------------

async def test_offline_alert_once_then_rearms_after_handshake(world):
    stale = await mkdev(world, "stale", seen=now() - timedelta(hours=2))
    fresh = await mkdev(world, "fresh", seen=now() - timedelta(minutes=2))
    await run_alerts(world)
    d = await dev_row(stale)
    assert d.offline_alerted_at is not None
    first = await offline_notifs(stale)
    assert first and world["hr"] in {n.user_id for n in first}
    assert "offline since" in first[0].message
    assert (await dev_row(fresh)).offline_alerted_at is None
    assert await offline_notifs(fresh) == []

    await run_alerts(world)  # not again
    assert len(await offline_notifs(stale)) == len(first)

    # device calls in: back online, alert cleared
    async with SessionLocal() as db:
        await bio.get_or_register_device(db, f"BHL{world['sfx']}stale", None)
    assert (await dev_row(stale)).offline_alerted_at is None
    assert await offline_notifs(stale, "Biometric device back online")
    # goes stale again -> alerts again
    async with SessionLocal() as db:
        dev = await db.get(BiometricDevice, stale)
        dev.last_seen_at = now() - timedelta(hours=3)
        await db.commit()
    await run_alerts(world)
    assert len(await offline_notifs(stale)) == 2 * len(first)


async def test_pending_and_disabled_never_alerted_never_seen_rules(world):
    old = now() - timedelta(hours=5)
    pend = await mkdev(world, "pend", status=DS.PENDING, seen=old, created=old)
    dis = await mkdev(world, "dis", status=DS.DISABLED, seen=old, created=old)
    never_old = await mkdev(world, "nold", seen=None, approved=old, created=old)
    never_new = await mkdev(world, "nnew", seen=None, approved=now(),
                            created=old)  # approved just now: grace
    never_new2 = await mkdev(world, "nnew2", seen=None,
                             created=now() - timedelta(minutes=3))
    await run_alerts(world)
    for k in (pend, dis, never_new, never_new2):
        assert (await dev_row(k)).offline_alerted_at is None
        assert await offline_notifs(k) == []
    assert (await dev_row(never_old)).offline_alerted_at is not None
    assert await offline_notifs(never_old)


async def test_offline_threshold_follows_rule(world):
    d = await mkdev(world, "thr", seen=now() - timedelta(minutes=45))
    async with SessionLocal() as db:
        await set_time_rules(db, {"biometric.offline_minutes": "120"})
    await run_alerts(world)
    assert (await dev_row(d)).offline_alerted_at is None
    async with SessionLocal() as db:
        await set_time_rules(db, {"biometric.offline_minutes": "30"})
    await run_alerts(world)
    assert (await dev_row(d)).offline_alerted_at is not None


async def test_jobs_registered_and_run_now(world, monkeypatch):
    import dataclasses
    from app.models.scheduled_job import ScheduledJob
    from app.services import scheduler
    from app.services.scheduler import REGISTRY
    names = ("biometric_device_offline_alerts", "biometric_pending_device_expiry")
    assert REGISTRY[names[0]].default_cadence_cron == "*/10 * * * *"
    assert REGISTRY[names[1]].default_cadence_cron == "30 3 * * *"
    real_fns = {n: REGISTRY[n].fn for n in names}  # real wiring is the job fns
    assert real_fns[names[0]].__name__ == "_job_biometric_device_offline_alerts"

    async def stub(session):
        return {"stub": True}

    for n in names:
        monkeypatch.setitem(REGISTRY, n, dataclasses.replace(REGISTRY[n], fn=stub))
    saved = {}
    async with SessionLocal() as db:
        await scheduler.ensure_jobs(db)
        for n in names:
            r = (await db.execute(select(ScheduledJob).where(
                ScheduledJob.name == n))).scalar_one()
            saved[n] = (r.last_run_at, r.last_status, r.last_summary,
                        r.last_duration_ms, r.last_error)
    app = create_app()
    app.dependency_overrides[deps.verify_attendance] = lambda: None
    try:
        async with AsyncClient(transport=ASGITransport(app=app),
                               base_url="http://test") as c:
            r = await c.post("/api/v1/auth/login", data={
                "username": f"bhl_hr_{world['sfx']}@t.com", "password": "x"})
            h = {"Authorization": f"Bearer {r.json()['access_token']}"}
            for name in names:
                r = await c.post(f"/api/v1/admin/jobs/{name}/run-now", headers=h)
                assert r.status_code == 200, r.text
                assert r.json()["ok"] is True, r.text
    finally:
        async with SessionLocal() as db:
            for n, (a, st, sm, du, er) in saved.items():
                row = (await db.execute(select(ScheduledJob).where(
                    ScheduledJob.name == n))).scalar_one()
                row.last_run_at, row.last_status, row.last_summary = a, st, sm
                row.last_duration_ms, row.last_error = du, er
            await db.commit()


# ---------------- registration limits ----------------

async def test_per_ip_pending_cap(world):
    ip = f"198.51.{random.randint(1, 250)}.{random.randint(1, 250)}"
    for i in range(bio.MAX_PENDING_PER_IP):
        await mkdev(world, f"ip{i}", status=DS.PENDING, ip=ip)
    sn = f"BHL{world['sfx']}ipx"
    async with SessionLocal() as db:
        assert await bio.get_or_register_device(db, sn, ip) is None
    async with SessionLocal() as db:
        assert (await db.execute(select(BiometricDevice).where(
            BiometricDevice.serial == sn))).scalars().first() is None
        # another IP is unaffected; an already-known serial from this IP too
        other = await bio.get_or_register_device(
            db, f"BHL{world['sfx']}ipo", "198.51.0.1")
        assert other is not None and other.status == DS.PENDING
        known = await bio.get_or_register_device(
            db, f"BHL{world['sfx']}ip0", ip)
        assert known is not None


async def run_expiry(world):
    async with SessionLocal() as db:
        return await bio.pending_expiry_job(
            db, serial_prefix=f"BHL{world['sfx']}")


async def put_tap(world, did, state_tag="x"):
    pin = f"{world['sfx']}{state_tag}{did}"
    async with SessionLocal() as db:
        dev = await db.get(BiometricDevice, did)
        await bio.store_taps(db, source="adms", device=dev, taps=[
            (pin, at(date(2031, 3, 3), 9), "0", "1", "r")])
        await db.commit()
    return pin


async def tap_count(pin):
    async with SessionLocal() as db:
        return len((await db.execute(select(BiometricPunch.id).where(
            BiometricPunch.pin == pin))).scalars().all())


async def test_pending_expiry_idle_based(world):
    d = lambda n: now() - timedelta(days=n)
    idle8 = await mkdev(world, "i8", status=DS.PENDING, created=d(9), seen=d(8))
    seen_recent = await mkdev(world, "sr", status=DS.PENDING, created=d(10),
                              seen=d(1))
    young = await mkdev(world, "yg", status=DS.PENDING, created=d(1))
    never_old = await mkdev(world, "no", status=DS.PENDING, created=d(8))
    ancient = await mkdev(world, "an", status=DS.PENDING, created=d(61),
                          seen=now())
    active_old = await mkdev(world, "ac", created=d(70), seen=d(30))
    pins = {k: await put_tap(world, k) for k in
            (idle8, seen_recent, young, never_old, ancient, active_old)}
    async with SessionLocal() as db:
        db.add(BiometricDeviceUser(device_id=idle8, pin=f"{world['sfx']}e",
                                   name="E", updated_at=now()))
        await db.commit()
    res = await run_expiry(world)
    assert res["expired"] == 3 and res["taps_deleted"] == 3
    async with SessionLocal() as db:
        for k in (idle8, never_old, ancient):
            assert await db.get(BiometricDevice, k) is None
            assert await tap_count(pins[k]) == 0  # no orphan taps
        for k in (seen_recent, young, active_old):
            assert await db.get(BiometricDevice, k) is not None
            assert await tap_count(pins[k]) == 1
        assert (await db.execute(select(BiometricDeviceUser).where(
            BiometricDeviceUser.device_id == idle8))).first() is None
        audits = [a for a in (await db.execute(select(AuditLog).where(
            AuditLog.action == EXPIRED_ACTION))).scalars().all()
            if world["sfx"] in str(a.details)]
        assert len(audits) == 1 and audits[0].details["devices"] == 3


async def test_expiry_skips_device_approved_meanwhile_and_kept_taps(world):
    old = now() - timedelta(days=9)
    approved = await mkdev(world, "ap", status=DS.PENDING, created=old, seen=old)
    held = await mkdev(world, "hd", status=DS.PENDING, created=old, seen=old)
    p_ap = await put_tap(world, approved)
    # a device that (defensively) holds an applied-type tap is skipped
    async with SessionLocal() as db:
        dev = await db.get(BiometricDevice, held)
        _n, rows = await bio.store_taps(db, source="adms", device=dev, taps=[
            (f"{world['sfx']}kept", at(date(2031, 3, 3), 9), "0", "1", "r")])
        rows[0].state = S.APPLIED
        await db.commit()
    # approve wins the race: the candidate list is stale, the locked re-check
    # sees status=active, so nothing is deleted
    async with SessionLocal() as db:
        d = await db.get(BiometricDevice, approved)
        d.status = DS.ACTIVE
        await db.commit()
    res = await run_expiry(world)
    assert res["expired"] == 0
    async with SessionLocal() as db:
        assert await db.get(BiometricDevice, approved) is not None
        assert await db.get(BiometricDevice, held) is not None
    assert await tap_count(p_ap) == 1


async def test_notify_failure_rolls_back_and_retries(world, monkeypatch):
    old = now() - timedelta(hours=3)
    first = await mkdev(world, "n1", seen=old)
    second = await mkdev(world, "n2", seen=old + timedelta(minutes=1))
    real = bio._notify_managers

    async def boom(db, title, message, device_id):
        if device_id == first:
            raise RuntimeError("notify down")
        return await real(db, title, message, device_id)

    monkeypatch.setattr(bio, "_notify_managers", boom)
    res = await run_alerts(world)
    assert res["alerted"] == 1 and res["failed"] == 1
    assert (await dev_row(first)).offline_alerted_at is None  # stamp undone
    assert (await dev_row(second)).offline_alerted_at is not None
    assert await offline_notifs(second) and not await offline_notifs(first)
    monkeypatch.setattr(bio, "_notify_managers", real)
    await run_alerts(world)  # retried
    assert (await dev_row(first)).offline_alerted_at is not None
    assert await offline_notifs(first)


async def test_stamp_rechecks_staleness(world):
    """A device that called in after the job's SELECT must not be stamped:
    the job's UPDATE carries the staleness predicate. Simulated by running the
    job's exact stamp against a device that just handshook."""
    from sqlalchemy import func, update
    dev_id = await mkdev(world, "rc", seen=now() - timedelta(hours=2))
    async with SessionLocal() as db:  # handshake lands
        await bio.get_or_register_device(db, f"BHL{world['sfx']}rc", None)
    async with SessionLocal() as db:
        res = await db.execute(update(BiometricDevice).where(
            BiometricDevice.id == dev_id,
            BiometricDevice.status == DS.ACTIVE,
            BiometricDevice.offline_alerted_at.is_(None),
            func.coalesce(BiometricDevice.last_seen_at,
                          BiometricDevice.approved_at,
                          BiometricDevice.created_at)
            < now() - timedelta(minutes=30)).values(offline_alerted_at=now()))
        assert res.rowcount == 0
        await db.rollback()
    await run_alerts(world)
    assert (await dev_row(dev_id)).offline_alerted_at is None


async def test_handshake_clear_is_unconditional(world):
    dev_id = await mkdev(world, "hc", seen=now() - timedelta(hours=2))
    await run_alerts(world)
    assert (await dev_row(dev_id)).offline_alerted_at is not None
    async with SessionLocal() as db:
        await bio.get_or_register_device(db, f"BHL{world['sfx']}hc", None)
    assert (await dev_row(dev_id)).offline_alerted_at is None
    assert len(await offline_notifs(dev_id, "Biometric device back online")) >= 1


# ---------------- ipv4-mapped IPv6 ----------------

def test_ipv4_mapped_is_unwrapped():
    assert bio._is_trusted_hop("::ffff:10.0.0.1")
    assert bio._is_trusted_hop("::ffff:127.0.0.1")
    assert not bio._is_trusted_hop("::ffff:8.8.8.8")
    # mapped private peer: the XFF is honoured
    assert bio.client_ip("::ffff:10.0.0.1", "203.0.113.9") == "203.0.113.9"
    # a mapped hop in XFF is skipped as trusted, mapped public is returned plain
    assert bio.client_ip("10.0.0.2", "198.51.100.7, ::ffff:10.0.0.1") \
        == "198.51.100.7"
    assert bio.client_ip("10.0.0.2", "::ffff:198.51.100.7") == "198.51.100.7"
    # all-private chain returns the right-most entry unwrapped
    assert bio.client_ip("10.0.0.2", "::ffff:192.168.1.5") == "192.168.1.5"
    # a mapped PUBLIC peer is not a trusted proxy: header ignored
    assert bio.client_ip("::ffff:8.8.8.8", "1.2.3.4") == "8.8.8.8"


# ---------------- rule validation / defaults ----------------

async def test_rule_defaults_and_validation(world):
    async with SessionLocal() as db:
        for k, v in (("biometric.offline_minutes", "30"),
                     ("biometric.default_utc_offset_minutes", "330"),
                     ("biometric.dedupe_seconds", "120")):
            assert k in (await get_time_rules(db))
        for key, bad in (
                ("biometric.offline_minutes", "4"),
                ("biometric.offline_minutes", "1441"),
                ("biometric.offline_minutes", "abc"),
                ("biometric.default_utc_offset_minutes", "-721"),
                ("biometric.default_utc_offset_minutes", "841"),
                ("biometric.default_utc_offset_minutes", "5.5"),
                ("biometric.dedupe_seconds", "-1"),
                ("biometric.dedupe_seconds", "3601"),
                ("biometric.dedupe_seconds", ""),
        ):
            with pytest.raises(ValueError):
                await set_time_rules(db, {key: bad})
        out = await set_time_rules(db, {
            "biometric.offline_minutes": " 5 ",
            "biometric.default_utc_offset_minutes": "-720",
            "biometric.dedupe_seconds": "3600"})
        assert out["biometric.offline_minutes"] == "5"
        assert out["biometric.default_utc_offset_minutes"] == "-720"
        out = await set_time_rules(db, {
            "biometric.offline_minutes": "1440",
            "biometric.default_utc_offset_minutes": "840",
            "biometric.dedupe_seconds": "0"})
        assert out["biometric.dedupe_seconds"] == "0"
        # a new device takes the offset rule
        await set_time_rules(db, {"biometric.default_utc_offset_minutes": "-300"})
        dev = await bio.get_or_register_device(
            db, f"BHL{world['sfx']}off", f"198.51.{random.randint(1, 250)}.9")
        assert dev.utc_offset_minutes == -300


# ---------------- dedupe rule drives apply ----------------

async def _active_with_user(world, tag, user_key):
    dev_id = await mkdev(world, tag, seen=now())
    pin = f"{world['sfx']}{tag}"
    async with SessionLocal() as db:
        db.add(BiometricUserMap(pin=pin, user_id=world[user_key],
                                device_id=None))
        await db.commit()
    return dev_id, pin


async def test_dedupe_rule_changes_apply_behaviour(world):
    d = date(2031, 6, 9)
    async with SessionLocal() as db:
        await set_time_rules(db, {"biometric.dedupe_seconds": "600"})
    # live path (apply_punch_committed, no explicit dedupe)
    dev_id, pin = await _active_with_user(world, "d1", "u1")
    async with SessionLocal() as db:
        dev = await db.get(BiometricDevice, dev_id)
        _n, rows = await bio.store_taps(db, source="adms", device=dev, taps=[
            (pin, at(d, 9, 0), "0", "1", "r"), (pin, at(d, 9, 5), "0", "1", "r")])
        await db.commit()
        ids = [r.id for r in sorted(rows, key=lambda r: r.punch_time)]
    got = [await bio.apply_punch_committed(SessionLocal, i, quiet=True)
           for i in ids]
    assert got == [S.APPLIED, S.DUPLICATE]
    # back-fill path (apply_pending, no explicit dedupe)
    dev_id2, pin2 = await _active_with_user(world, "d2", "u2")
    async with SessionLocal() as db:
        dev = await db.get(BiometricDevice, dev_id2)
        await bio.store_taps(db, source="adms", device=dev, taps=[
            (pin2, at(d, 9, 0), "0", "1", "r"), (pin2, at(d, 9, 5), "0", "1", "r")])
        await db.commit()
    res = await bio.apply_pending(SessionLocal, pin=pin2,
                                  states={bio.PENDING_APPLY})
    assert res["counts"] == {S.APPLIED: 1, S.DUPLICATE: 1}
    # rule 120: the same 5-minute gap is a real punch-out
    async with SessionLocal() as db:
        await set_time_rules(db, {"biometric.dedupe_seconds": "120"})
    d2 = date(2031, 6, 10)
    async with SessionLocal() as db:
        dev = await db.get(BiometricDevice, dev_id)
        _n, rows = await bio.store_taps(db, source="adms", device=dev, taps=[
            (pin, at(d2, 9, 0), "0", "1", "r"), (pin, at(d2, 9, 5), "0", "1", "r")])
        await db.commit()
        ids = [r.id for r in sorted(rows, key=lambda r: r.punch_time)]
    got = [await bio.apply_punch_committed(SessionLocal, i, quiet=True)
           for i in ids]
    assert got == [S.APPLIED, S.APPLIED]
