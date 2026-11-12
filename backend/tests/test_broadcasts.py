"""Emergency broadcast & mark-me-safe (Roadmap v2 Phase 2, Task 7)."""
import uuid
from datetime import date, datetime, time, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, insert, select, func

from app.api import deps
from app.api.v1.endpoints import broadcasts as bc_ep
from app.core.config import settings
from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.main import create_app
from app.models.broadcast import Broadcast, BroadcastRecipient
from app.models.department import Department
from app.models.employee import Employee, EmployeeStatus
from app.models.notification import Notification
from app.models.notification_channel import (
    NotificationDelivery, UserQuietHours, UserNotificationPreference,
)
from app.models.user import Permission, Role, User, role_permissions, user_roles
from app.services import broadcast as svc
from app.services import notifications_delivery as nd

API = f"{settings.API_V1_STR}/broadcasts"
PW = "test@12345"


@pytest.fixture
async def client():
    app = create_app()
    app.dependency_overrides[deps.verify_attendance] = lambda: None
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as c:
        yield c


@pytest.fixture
async def world(monkeypatch):
    sfx = uuid.uuid4().hex[:8]
    dx, dy = f"BX{sfx}", f"BY{sfx}"
    locx = f"LX{sfx}"
    role_name, hr_name = f"BCS{sfx}", f"BHR{sfx}"
    monkeypatch.setattr(bc_ep, "HR_ROLE_NAME", hr_name)
    try:
        async with SessionLocal() as db:
            def mk(tag, **kw):
                return User(email=f"bc_{tag}_{sfx}@t.com", full_name=f"BC {tag}",
                            phone="9000000000",
                            hashed_password=get_password_hash(PW),
                            is_active=True, **kw)
            tags = ("sender", "hr", "e1", "e2", "e3", "e4", "inactive")
            us = {t: mk(t) for t in tags}
            db.add_all(us.values())
            db.add_all([Department(name=dx), Department(name=dy)])
            perm = (await db.execute(select(Permission).where(
                Permission.name == "broadcast send"))).scalar_one()
            r1 = Role(name=role_name, description="t")
            r2 = Role(name=hr_name, description="t")
            db.add_all([r1, r2])
            await db.commit()
            await db.execute(insert(role_permissions).values(
                role_id=r1.id, permission_id=perm.id))
            await db.execute(insert(user_roles).values(
                user_id=us["sender"].id, role_id=r1.id))
            await db.execute(insert(user_roles).values(
                user_id=us["hr"].id, role_id=r2.id))
            spec = {"sender": (dx, None, EmployeeStatus.ACTIVE),
                    "hr": (dx, None, EmployeeStatus.ACTIVE),
                    "e1": (dx, locx, EmployeeStatus.ACTIVE),
                    "e2": (dx, locx, EmployeeStatus.ACTIVE),
                    "e3": (dy, locx, EmployeeStatus.ACTIVE),
                    "e4": (dy, None, EmployeeStatus.ACTIVE),
                    "inactive": (dx, locx, EmployeeStatus.INACTIVE)}
            for tag, (dept, loc, st) in spec.items():
                db.add(Employee(user_id=us[tag].id, employee_id=f"BC{sfx}{tag}"[:20],
                                department=dept, location=loc, designation="T",
                                date_of_joining=date(2020, 1, 1), status=st))
            await db.commit()
            ids = {t: u.id for t, u in us.items()}
            rids = (r1.id, r2.id)
        yield {"ids": ids, "sfx": sfx, "dx": dx, "dy": dy, "loc": locx,
               "all": list(ids.values()),
               "email": lambda t: f"bc_{t}_{sfx}@t.com"}
    finally:
        async with SessionLocal() as db:
            uids = list((await db.execute(select(User.id).where(
                User.email.like(f"bc\\_%\\_{sfx}@t.com")))).scalars().all())
            bids = list((await db.execute(select(Broadcast.id).where(
                Broadcast.created_by_id.in_(uids)))).scalars().all())
            nids = list((await db.execute(select(Notification.id).where(
                (Notification.user_id.in_(uids)) |
                ((Notification.resource_type == "broadcast") &
                 (Notification.resource_id.in_([str(b) for b in bids]))))
            )).scalars().all())
            if nids:
                await db.execute(delete(NotificationDelivery).where(
                    NotificationDelivery.notification_id.in_(nids)))
                await db.execute(delete(Notification).where(
                    Notification.id.in_(nids)))
            await db.execute(delete(NotificationDelivery).where(
                NotificationDelivery.recipient_user_id.in_(uids)))
            await db.execute(delete(BroadcastRecipient).where(
                BroadcastRecipient.user_id.in_(uids)))
            await db.execute(delete(Broadcast).where(Broadcast.id.in_(bids)))
            await db.execute(delete(UserQuietHours).where(UserQuietHours.user_id.in_(uids)))
            await db.execute(delete(UserNotificationPreference).where(
                UserNotificationPreference.user_id.in_(uids)))
            await db.execute(delete(user_roles).where(user_roles.c.user_id.in_(uids)))
            await db.execute(delete(role_permissions).where(role_permissions.c.role_id.in_(rids)))
            await db.execute(delete(Role).where(Role.id.in_(rids)))
            await db.execute(delete(Employee).where(Employee.user_id.in_(uids)))
            await db.execute(delete(Department).where(Department.name.in_([dx, dy])))
            await db.execute(delete(User).where(User.id.in_(uids)))
            await db.commit()


async def login(client, world, tag):
    r = await client.post(f"{settings.API_V1_STR}/auth/login",
                          data={"username": world["email"](tag), "password": PW})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def payload(world, **kw):
    b = {"title": "Fire drill", "message": "Evacuate now", "severity": "critical",
         "audience": "department", "audience_value": world["dx"],
         "requires_ack": True, "safety_check": True}
    b.update(kw)
    return b


async def send(client, world, **kw):
    h = await login(client, world, "sender")
    r = await client.post(API, json=payload(world, **kw), headers=h)
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------- permissions ----------------------------

async def test_sender_endpoints_need_permission(client, world):
    h = await login(client, world, "e1")
    assert (await client.post(API, json=payload(world), headers=h)).status_code == 403
    assert (await client.get(API, headers=h)).status_code == 403
    assert (await client.get(f"{API}/1", headers=h)).status_code == 403
    assert (await client.post(f"{API}/1/close", headers=h)).status_code == 403
    # recipient endpoints open to any user
    assert (await client.get(f"{API}/my", headers=h)).status_code == 200


async def test_validation(client, world):
    h = await login(client, world, "sender")
    r = await client.post(API, json=payload(world, audience_value=None), headers=h)
    assert r.status_code == 400
    r = await client.post(API, json=payload(world, audience_value="NoSuchDept" + world["sfx"]), headers=h)
    assert r.status_code == 400 and "No recipients" in r.text
    r = await client.post(API, json=payload(world, severity="bogus"), headers=h)
    assert r.status_code == 422


# --------------------------- audience resolution ---------------------------

async def test_audience_resolution(world):
    ids = world["ids"]
    async with SessionLocal() as db:
        dept = await svc.resolve_audience(db, "department", world["dx"])
        assert set(dept) == {ids["sender"], ids["hr"], ids["e1"], ids["e2"]}  # no inactive
        loc = await svc.resolve_audience(db, "location", world["loc"])
        assert set(loc) == {ids["e1"], ids["e2"], ids["e3"]}
        # 'all' with an injectable scope (never hits real users)
        allu = await svc.resolve_audience(db, "all", user_scope=world["all"])
        assert set(allu) == set(world["all"]) - {ids["inactive"]}
        assert await svc.resolve_audience(db, "all", user_scope=[]) == []


async def test_on_shift_audience(world, monkeypatch):
    ids = world["ids"]
    from app.services import live_ops
    S = live_ops.LiveStatus
    statuses = {ids["e1"]: S.ON_SHIFT, ids["e2"]: S.NOT_ARRIVED,
                ids["e3"]: S.RUNNING_LATE, ids["e4"]: S.NO_SHOW,
                ids["sender"]: S.OFF, ids["hr"]: S.UPCOMING}
    seen = {}

    async def fake_board(db, user_ids, now, **kw):
        seen["ids"] = set(user_ids)
        return [type("R", (), {"user_id": u, "status": statuses[u]})()
                for u in user_ids if u in statuses]
    monkeypatch.setattr(live_ops, "live_board", fake_board)
    async with SessionLocal() as db:
        got = await svc.resolve_audience(db, "on_shift", user_scope=world["all"])
    assert set(got) == {ids["e1"], ids["e2"], ids["e3"]}
    assert ids["inactive"] not in seen["ids"]


# -------------------- send: recipients, notifications, deliveries --------------------

async def test_send_creates_everything_and_bypasses_quiet_hours(client, world):
    ids = world["ids"]
    now = datetime.now(timezone.utc)
    async with SessionLocal() as db:
        db.add(UserQuietHours(user_id=ids["e1"], quiet_from=(now - timedelta(hours=1)).time(),
                              quiet_to=(now + timedelta(hours=1)).time(), hard_opt_out=True))
        db.add(UserNotificationPreference(user_id=ids["e2"], category="emergency",
                                          channel="email", enabled=False))
        await db.commit()
    b = await send(client, world)
    assert b["counts"]["total"] == 4 and b["counts"]["no_response"] == 4
    async with SessionLocal() as db:
        recips = (await db.execute(select(BroadcastRecipient.user_id).where(
            BroadcastRecipient.broadcast_id == b["id"]))).scalars().all()
        assert set(recips) == {ids["sender"], ids["hr"], ids["e1"], ids["e2"]}
        notifs = (await db.execute(select(Notification).where(
            Notification.resource_type == "broadcast",
            Notification.resource_id == str(b["id"])))).scalars().all()
        assert len(notifs) == 4 and all(n.event_type == "emergency_broadcast" for n in notifs)
        rows = (await db.execute(select(NotificationDelivery).where(
            NotificationDelivery.notification_id.in_([n.id for n in notifs])))).scalars().all()
        assert len(rows) == 8
        for d in rows:
            assert d.status == "queued" and d.next_retry_at is None, (d.recipient_user_id, d.channel)
        assert {(d.recipient_user_id, d.channel) for d in rows} >= {
            (ids["e1"], "email"), (ids["e1"], "sms"), (ids["e2"], "email")}


async def test_other_categories_still_respect_quiet_hours_and_optout(world):
    ids = world["ids"]
    now = datetime.now(timezone.utc)
    async with SessionLocal() as db:
        db.add(UserQuietHours(user_id=ids["e1"], quiet_from=(now - timedelta(hours=1)).time(),
                              quiet_to=(now + timedelta(hours=1)).time()))
        db.add(UserQuietHours(user_id=ids["e2"], hard_opt_out=True))
        await db.commit()
        await nd.notify(db, user_id=ids["e1"], event_type="approval_pending",
                        title="t", message="m")
        await nd.notify(db, user_id=ids["e2"], event_type="approval_pending",
                        title="t", message="m")
        # emergency single-user path (need_help alert) also bypasses
        await nd.notify(db, user_id=ids["e1"], event_type="emergency_need_help",
                        title="t", message="m")
        await nd.notify(db, user_id=ids["e2"], event_type="emergency_need_help",
                        title="t", message="m")
        await db.commit()
        rows = (await db.execute(select(NotificationDelivery).where(
            NotificationDelivery.recipient_user_id.in_([ids["e1"], ids["e2"]])))).scalars().all()
    by = {(d.recipient_user_id, d.event_type, d.channel): d for d in rows}
    # quiet hours delay non-emergency (approvals: email only enabled by default)
    d = by[(ids["e1"], "approval_pending", "email")]
    assert d.status == "queued" and d.next_retry_at is not None
    assert by[(ids["e2"], "approval_pending", "email")].status == "skipped_pref"
    for u in (ids["e1"], ids["e2"]):
        for ch in ("email", "sms"):
            e = by[(u, "emergency_need_help", ch)]
            assert e.status == "queued" and e.next_retry_at is None


# ------------------------------ responses ------------------------------

async def test_own_only_idempotent_responses_and_dashboard(client, world):
    ids = world["ids"]
    b = await send(client, world)
    bid = b["id"]
    h1, h2 = await login(client, world, "e1"), await login(client, world, "e2")
    h4 = await login(client, world, "e4")  # not a recipient
    for path in ("read", "ack"):
        assert (await client.post(f"{API}/{bid}/{path}", headers=h4)).status_code == 404
    assert (await client.post(f"{API}/{bid}/safety", json={"status": "safe"}, headers=h4)).status_code == 404
    assert (await client.get(f"{API}/my", headers=h4)).json() == []

    my = (await client.get(f"{API}/my", headers=h1)).json()
    assert len(my) == 1 and my[0]["id"] == bid and my[0]["pending"] is True
    r = await client.post(f"{API}/{bid}/ack", headers=h1)
    assert r.json()["acked_at"] and r.json()["pending"] is True  # still needs safety
    first = r.json()["acked_at"]
    assert (await client.post(f"{API}/{bid}/ack", headers=h1)).json()["acked_at"] == first
    r = await client.post(f"{API}/{bid}/safety", json={"status": "safe"}, headers=h1)
    assert r.json()["safety_status"] == "safe" and r.json()["pending"] is False
    r2 = await client.post(f"{API}/{bid}/safety", json={"status": "safe"}, headers=h1)
    assert r2.json()["responded_at"] == r.json()["responded_at"]
    # e2 only reads, then needs help
    await client.post(f"{API}/{bid}/read", headers=h2)
    r = await client.post(f"{API}/{bid}/safety", json={"status": "need_help", "note": "trapped"}, headers=h2)
    assert r.json()["safety_status"] == "need_help" and r.json()["safety_note"] == "trapped"

    hs = await login(client, world, "sender")
    d = (await client.get(f"{API}/{bid}", headers=hs)).json()
    c = d["counts"]
    assert (c["total"], c["read"], c["acked"], c["safe"], c["need_help"], c["no_response"]) == (4, 2, 2, 1, 1, 2)  # safety responses also ack
    assert d["recipients"][0]["user_id"] == ids["e2"]          # need_help first
    assert d["recipients"][0]["safety_note"] == "trapped"
    assert d["recipients"][1]["safety_status"] is None          # then no response
    for flt, expect in (("need_help", {ids["e2"]}), ("safe", {ids["e1"]}),
                        ("no_response", {ids["sender"], ids["hr"]})):
        got = (await client.get(f"{API}/{bid}?filter={flt}", headers=hs)).json()
        assert {x["user_id"] for x in got["recipients"]} == expect
    pg = (await client.get(f"{API}/{bid}?page=2&page_size=3", headers=hs)).json()
    assert len(pg["recipients"]) == 1 and pg["recipients_total"] == 4
    lst = (await client.get(API, headers=hs)).json()
    row = [x for x in lst["items"] if x["id"] == bid][0]
    assert row["counts"]["need_help"] == 1


async def test_need_help_alerts_sender_and_hr_once(client, world):
    ids = world["ids"]
    b = await send(client, world)
    h = await login(client, world, "e1")
    for _ in range(2):
        await client.post(f"{API}/{b['id']}/safety",
                          json={"status": "need_help", "note": "hurt"}, headers=h)
    async with SessionLocal() as db:
        ns = (await db.execute(select(Notification).where(
            Notification.event_type == "emergency_need_help",
            Notification.resource_id == str(b["id"])))).scalars().all()
        assert {n.user_id for n in ns} == {ids["sender"], ids["hr"]}
        assert len(ns) == 2 and "needs help" in ns[0].title
        d = (await db.execute(select(func.count()).select_from(NotificationDelivery).where(
            NotificationDelivery.notification_id.in_([n.id for n in ns])))).scalar_one()
        assert d == 4
    # safe does not alert
    h2 = await login(client, world, "e2")
    await client.post(f"{API}/{b['id']}/safety", json={"status": "safe"}, headers=h2)
    async with SessionLocal() as db:
        n = (await db.execute(select(func.count()).select_from(Notification).where(
            Notification.event_type == "emergency_need_help",
            Notification.resource_id == str(b["id"])))).scalar_one()
        assert n == 2


async def test_safety_needs_safety_check_and_close(client, world):
    b = await send(client, world, safety_check=False)
    h = await login(client, world, "e1")
    r = await client.post(f"{API}/{b['id']}/safety", json={"status": "safe"}, headers=h)
    assert r.status_code == 400
    hs = await login(client, world, "sender")
    assert len((await client.get(f"{API}/my", headers=h)).json()) == 1
    r = await client.post(f"{API}/{b['id']}/close", headers=hs)
    assert r.status_code == 200 and r.json()["closed_at"]
    assert (await client.get(f"{API}/my", headers=h)).json() == []
    assert (await client.post(f"{API}/{b['id']}/ack", headers=h)).status_code == 400
    assert (await client.post(f"{API}/{b['id']}/close", headers=hs)).status_code == 200  # idempotent
    assert (await client.get(f"{API}/99999999", headers=hs)).status_code == 404


async def test_bulk_notifier_query_count_is_chunked(world):
    """No per-user query loops: statement count does not grow with users."""
    from sqlalchemy import event
    stmts = []
    listener = lambda conn, cur, stmt, *a: stmts.append(stmt)
    async with SessionLocal() as db:
        eng = (await db.connection()).sync_engine
        event.listen(eng, "before_cursor_execute", listener)
        try:
            await nd.notify_emergency_bulk(
                db, user_ids=world["all"], event_type="emergency_broadcast",
                title="t", message="m", resource_type="broadcast",
                resource_id="0")
        finally:
            event.remove(eng, "before_cursor_execute", listener)
        await db.rollback()
    # 7 users: 1 contacts select + notification insert(s) + delivery insert(s)
    assert len(stmts) <= 6, stmts


async def test_audience_options(client, world):
    h = await login(client, world, "sender")
    r = await client.get(f"{API}/audience-options", headers=h)
    assert r.status_code == 200
    d = {x["value"]: x["count"] for x in r.json()["departments"]}
    assert d[world["dx"]] == 4          # sender, hr, e1, e2 (inactive excluded)
    assert {x["value"]: x["count"] for x in r.json()["locations"]}[world["loc"]] == 3
