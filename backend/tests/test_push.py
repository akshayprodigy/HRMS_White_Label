"""Device tokens, PUSH channel and actionable notifications
(Roadmap v2 Phase 3, Task 1). No network: Expo is tested via a mock transport."""
import json
import uuid
from datetime import date, datetime, time, timedelta, timezone

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from _cleanup import purge_shift_templates
from app.api import deps
from app.api.v1.endpoints import broadcasts as bc_ep
from app.core.config import settings
from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.main import create_app
from app.models.approval import ApprovalItem, ApprovalStatus, ApprovalStep
from app.models.approval_chain import (
    ChainedApprovalInstance, ChainedApprovalStepInstance,
)
from app.models.audit import AuditLog
from app.models.broadcast import Broadcast, BroadcastRecipient
from app.models.department import Department
from app.models.device import DeviceToken
from app.models.employee import Employee, EmployeeStatus
from app.models.notification import Notification
from app.models.notification_channel import (
    Channel, NotificationTemplate, DeliveryStatus, NotificationDelivery, UserNotificationPreference,
    UserQuietHours,
)
from app.models.open_shift import OpenShift, OpenShiftClaim
from app.models.shift import ShiftTemplate
from app.models.user import User
from app.services import broadcast as bsvc
from app.services import notifications_delivery as nd
from app.services import open_shifts as os_svc
from app.services import push as push_svc

API = settings.API_V1_STR
ORIG_VERIFY = deps.verify_attendance  # the function the routes depend on
PW = "test@12345"
TAGS = ("adm", "e1", "e2", "apr", "req", "oth")


@pytest.fixture
async def client():
    app = create_app()
    app.dependency_overrides[ORIG_VERIFY] = lambda: None
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as c:
        yield c


@pytest.fixture(autouse=True)
def _no_gate(monkeypatch):
    async def ok(db, user):
        return user
    monkeypatch.setattr(deps, "verify_attendance", ok)


@pytest.fixture(autouse=True)
def _restore_provider():
    prev = push_svc.get_push_provider()
    yield
    push_svc.set_push_provider(prev)


@pytest.fixture
async def world(monkeypatch):
    sfx = uuid.uuid4().hex[:8]
    dx = f"PX{sfx}"
    test_ids = set()
    orig = bc_ep._alert_recipients

    async def only_test(db, b, exclude):
        return [u for u in await orig(db, b, exclude) if u in test_ids]
    monkeypatch.setattr(bc_ep, "_alert_recipients", only_test)
    tpl_id = None
    try:
        async with SessionLocal() as db:
            us = {}
            for t in TAGS:
                us[t] = User(
                    email=f"pu_{t}_{sfx}@t.com", full_name=f"PU {t}",
                    hashed_password=get_password_hash(PW), is_active=True,
                    is_superuser=(t == "adm"))
            db.add_all(us.values())
            db.add(Department(name=dx))
            tpl = ShiftTemplate(name=f"PUT{sfx}", start_time=time(9),
                                end_time=time(17))
            db.add(tpl)
            await db.commit()
            tpl_id = tpl.id
            for t in ("e1", "e2"):
                db.add(Employee(user_id=us[t].id, employee_id=f"PU{sfx}{t}"[:20],
                                department=dx, designation="T",
                                date_of_joining=date(2020, 1, 1),
                                status=EmployeeStatus.ACTIVE))
            await db.commit()
            ids = {t: u.id for t, u in us.items()}
            test_ids.update(ids.values())
        yield {"ids": ids, "sfx": sfx, "dx": dx, "tpl": tpl_id, "n": [0]}
    finally:
        async with SessionLocal() as db:
            uids = list((await db.execute(select(User.id).where(
                User.email.like(f"pu\\_%\\_{sfx}@t.com")))).scalars().all())
            bids = list((await db.execute(select(Broadcast.id).where(
                Broadcast.created_by_id.in_(uids)))).scalars().all())
            nids = list((await db.execute(select(Notification.id).where(
                (Notification.user_id.in_(uids)) |
                ((Notification.resource_type == "broadcast") &
                 (Notification.resource_id.in_([str(b) for b in bids] or ["-"])))
            ))).scalars().all())
            if nids:
                await db.execute(delete(NotificationDelivery).where(
                    NotificationDelivery.notification_id.in_(nids)))
            await db.execute(delete(NotificationDelivery).where(
                NotificationDelivery.recipient_user_id.in_(uids)))
            if nids:
                await db.execute(delete(Notification).where(
                    Notification.id.in_(nids)))
            await db.execute(delete(BroadcastRecipient).where(
                BroadcastRecipient.broadcast_id.in_(bids or [-1])))
            await db.execute(delete(Broadcast).where(Broadcast.id.in_(bids or [-1])))
            sids = list((await db.execute(select(OpenShift.id).where(
                OpenShift.shift_template_id == tpl_id))).scalars().all())
            if sids:
                await db.execute(delete(OpenShiftClaim).where(
                    OpenShiftClaim.open_shift_id.in_(sids)))
            items = list((await db.execute(select(ApprovalItem.id).where(
                ApprovalItem.resource_id.like(f"{sfx}%")))).scalars().all())
            if items:
                await db.execute(delete(ApprovalStep).where(
                    ApprovalStep.approval_item_id.in_(items)))
                await db.execute(delete(ApprovalItem).where(
                    ApprovalItem.id.in_(items)))
            insts = list((await db.execute(select(ChainedApprovalInstance.id)
                         .where(ChainedApprovalInstance.submitter_id.in_(uids))
                         )).scalars().all())
            if insts:
                await db.execute(delete(ChainedApprovalStepInstance).where(
                    ChainedApprovalStepInstance.instance_id.in_(insts)))
                await db.execute(delete(ChainedApprovalInstance).where(
                    ChainedApprovalInstance.id.in_(insts)))
            await db.execute(delete(AuditLog).where(AuditLog.user_id.in_(uids)))
            await db.execute(delete(DeviceToken).where(
                (DeviceToken.user_id.in_(uids))
                | (DeviceToken.token.like(f"%{sfx}%"))))
            await db.execute(delete(NotificationTemplate).where(
                NotificationTemplate.event_type == f"pushpriv_{sfx}"))
            await db.execute(delete(UserQuietHours).where(
                UserQuietHours.user_id.in_(uids)))
            await db.execute(delete(UserNotificationPreference).where(
                UserNotificationPreference.user_id.in_(uids)))
            await db.execute(delete(Employee).where(Employee.user_id.in_(uids)))
            await db.commit()
            await purge_shift_templates(db, [tpl_id] if tpl_id else [])
            await db.execute(delete(User).where(User.id.in_(uids)))
            await db.execute(delete(Department).where(Department.name == dx))
            await db.commit()


async def login(client, w, tag):
    r = await client.post(f"{API}/auth/login", data={
        "username": f"pu_{tag}_{w['sfx']}@t.com", "password": PW})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def tok(w, n="a"):
    return f"ExponentPushToken[{w['sfx']}{n}]"


async def add_token(w, tag, n="a", revoked=False):
    async with SessionLocal() as db:
        db.add(DeviceToken(
            user_id=w["ids"][tag], platform="android", token=tok(w, n),
            revoked_at=datetime.now(timezone.utc) if revoked else None))
        await db.commit()


async def mk_notif(w, tag, *, event_type=None, rtype=None, rid=None,
                   title="T", message="M"):
    async with SessionLocal() as db:
        n = Notification(user_id=w["ids"][tag], title=title, message=message,
                         type="info", resource_type=rtype, resource_id=rid,
                         event_type=event_type)
        db.add(n)
        await db.commit()
        return n.id


async def deliveries(nid):
    async with SessionLocal() as db:
        return list((await db.execute(select(NotificationDelivery).where(
            NotificationDelivery.notification_id == nid))).scalars().all())


async def notify_user(w, tag, event_type, **kw):
    async with SessionLocal() as db:
        nid = await nd.notify(db, user_id=w["ids"][tag], event_type=event_type,
                              title="Hello", message="World", **kw)
        await db.commit()
    return nid


# ------------------------------- device tokens -------------------------------

async def test_register_upsert_refresh(client, world):
    h = await login(client, world, "e1")
    body = {"token": tok(world), "platform": "ios", "app_version": "1.0.0",
            "tenant": "acme"}
    r = await client.post(f"{API}/devices", json=body, headers=h)
    assert r.status_code == 200, r.text
    first = r.json()
    body["app_version"] = "1.0.1"
    r = await client.post(f"{API}/devices", json=body, headers=h)
    assert r.status_code == 200
    assert r.json()["id"] == first["id"] and r.json()["app_version"] == "1.0.1"
    mine = (await client.get(f"{API}/devices/my", headers=h)).json()
    assert [d["token"] for d in mine] == [tok(world)]


async def test_register_validation_and_auth(client, world):
    h = await login(client, world, "e1")
    r = await client.post(f"{API}/devices", headers=h,
                          json={"token": tok(world), "platform": "windows"})
    assert r.status_code == 422
    r = await client.post(f"{API}/devices", headers=h,
                          json={"token": "x", "platform": "ios"})
    assert r.status_code == 422
    r = await client.post(f"{API}/devices",
                          json={"token": tok(world), "platform": "ios"})
    assert r.status_code == 401


async def test_token_moves_to_new_user_and_unrevokes(client, world):
    h1, h2 = await login(client, world, "e1"), await login(client, world, "e2")
    body = {"token": tok(world), "platform": "android"}
    await client.post(f"{API}/devices", json=body, headers=h1)
    await client.delete(f"{API}/devices/{tok(world)}", headers=h1)
    assert (await client.get(f"{API}/devices/my", headers=h1)).json() == []
    r = await client.post(f"{API}/devices", json=body, headers=h2)
    assert r.status_code == 200
    assert [d["token"] for d in
            (await client.get(f"{API}/devices/my", headers=h2)).json()] == [tok(world)]
    assert (await client.get(f"{API}/devices/my", headers=h1)).json() == []
    async with SessionLocal() as db:
        d = (await db.execute(select(DeviceToken).where(
            DeviceToken.token == tok(world)))).scalar_one()
        assert d.user_id == world["ids"]["e2"] and d.revoked_at is None


async def test_revoke_own_only(client, world):
    h1, h2 = await login(client, world, "e1"), await login(client, world, "e2")
    await client.post(f"{API}/devices", headers=h1,
                      json={"token": tok(world), "platform": "ios"})
    r = await client.delete(f"{API}/devices/{tok(world)}", headers=h2)
    assert r.status_code == 404
    assert len((await client.get(f"{API}/devices/my", headers=h1)).json()) == 1
    r = await client.delete(f"{API}/devices/{tok(world)}", headers=h1)
    assert r.status_code == 200 and r.json() == {"revoked": True}
    assert (await client.get(f"{API}/devices/my", headers=h1)).json() == []
    assert (await client.delete(f"{API}/devices/{tok(world)}", headers=h1)).status_code == 200
    assert (await client.delete(f"{API}/devices/nope-{world['sfx']}", headers=h1)).status_code == 404


# ------------------------------- dispatch -------------------------------

async def test_push_rows_only_for_users_with_active_tokens(world):
    await add_token(world, "e1")
    await add_token(world, "e2", n="b", revoked=True)
    n1 = await notify_user(world, "e1", "approval_pending")
    n2 = await notify_user(world, "e2", "approval_pending")  # revoked only
    n3 = await notify_user(world, "apr", "approval_pending")  # none
    ch1 = {d.channel for d in await deliveries(n1)}
    assert Channel.PUSH in ch1
    assert Channel.PUSH not in {d.channel for d in await deliveries(n2)}
    assert Channel.PUSH not in {d.channel for d in await deliveries(n3)}
    d = [d for d in await deliveries(n1) if d.channel == Channel.PUSH][0]
    assert d.status == DeliveryStatus.QUEUED


async def _quiet(w, tag, hard=False, around_now=True):
    now = datetime.now(timezone.utc)
    async with SessionLocal() as db:
        db.add(UserQuietHours(
            user_id=w["ids"][tag],
            quiet_from=(now - timedelta(hours=1)).time(),
            quiet_to=(now + timedelta(hours=1)).time(), hard_opt_out=hard))
        await db.commit()


async def test_quiet_hours_delay_push(world):
    await add_token(world, "e1")
    await _quiet(world, "e1")
    nid = await notify_user(world, "e1", "approval_pending")
    d = [d for d in await deliveries(nid) if d.channel == Channel.PUSH][0]
    assert d.status == DeliveryStatus.QUEUED and d.next_retry_at is not None


async def test_preference_and_hard_opt_out_skip_push(world):
    await add_token(world, "e1")
    await add_token(world, "e2", n="b")
    async with SessionLocal() as db:
        db.add(UserNotificationPreference(
            user_id=world["ids"]["e1"], category="approvals",
            channel=Channel.PUSH, enabled=False))
        await db.commit()
    await _quiet(world, "e2", hard=True)
    # hard_opt_out with no quiet window overlap is irrelevant to the check
    for tag in ("e1", "e2"):
        nid = await notify_user(world, tag, "approval_pending")
        d = [d for d in await deliveries(nid) if d.channel == Channel.PUSH][0]
        assert d.status == DeliveryStatus.SKIPPED_PREF


async def test_emergency_bypasses_quiet_hours_prefs_and_opt_out(world):
    await add_token(world, "e1")
    await _quiet(world, "e1", hard=True)
    async with SessionLocal() as db:
        db.add(UserNotificationPreference(
            user_id=world["ids"]["e1"], category="emergency",
            channel=Channel.PUSH, enabled=False))
        await db.commit()
    nid = await notify_user(world, "e1", "emergency_broadcast")
    d = [d for d in await deliveries(nid) if d.channel == Channel.PUSH][0]
    assert d.status == DeliveryStatus.QUEUED and d.next_retry_at is None


async def test_emergency_bulk_creates_push_only_for_token_holders(world):
    await add_token(world, "e1")
    async with SessionLocal() as db:
        await nd.notify_emergency_bulk(
            db, user_ids=[world["ids"]["e1"], world["ids"]["e2"]],
            event_type="emergency_broadcast", title="T", message="M",
            resource_type="broadcast", resource_id="0")
        await db.commit()
    async with SessionLocal() as db:
        rows = (await db.execute(select(NotificationDelivery).where(
            NotificationDelivery.recipient_user_id.in_(
                [world["ids"]["e1"], world["ids"]["e2"]]),
            NotificationDelivery.channel == Channel.PUSH))).scalars().all()
    assert {r.recipient_user_id for r in rows} == {world["ids"]["e1"]}


# ------------------------------- sending -------------------------------

class Recorder(push_svc.PushProvider):
    name = "rec"

    def __init__(self, result=None):
        self.calls = []
        self.result = result or push_svc.PushResult(ok=True, provider_message_id="m1")

    async def send(self, **kw):
        self.calls.append(kw)
        return self.result


async def send_push_for(nid):
    d = [d for d in await deliveries(nid) if d.channel == Channel.PUSH][0]
    async with SessionLocal() as db:
        res = await nd.send_one_delivery(db, d.id)
    return res, [d for d in await deliveries(nid) if d.channel == Channel.PUSH][0]


async def test_send_builds_payload_and_marks_sent(world):
    await add_token(world, "e1")
    rec = Recorder()
    push_svc.set_push_provider(rec)
    nid = await notify_user(world, "e1", "approval_pending",
                            resource_type="nothing", resource_id="1")
    res, d = await send_push_for(nid)
    assert res.ok and d.status == DeliveryStatus.SENT
    call = rec.calls[0]
    assert call["tokens"] == [tok(world)]
    assert call["data"] == {
        "notification_id": nid, "user_id": world["ids"]["e1"],
        "event_type": "approval_pending",
        "resource_type": "nothing", "resource_id": "1",
        "category": "none", "actions": []}
    assert call["priority"] == "default"


async def test_emergency_push_is_high_priority(world):
    await add_token(world, "e1")
    rec = Recorder()
    push_svc.set_push_provider(rec)
    nid = await notify_user(world, "e1", "emergency_broadcast")
    await send_push_for(nid)
    assert rec.calls[0]["priority"] == "high"


async def test_send_failure_retries_then_revoked_token_fails_permanently(world):
    await add_token(world, "e1")
    push_svc.set_push_provider(Recorder(push_svc.PushResult(ok=False, error="boom")))
    nid = await notify_user(world, "e1", "approval_pending")
    res, d = await send_push_for(nid)
    assert not res.ok and d.status == DeliveryStatus.QUEUED and d.attempts == 1
    # token revoked meanwhile -> permanent failure, provider not called
    async with SessionLocal() as db:
        await push_svc.revoke_tokens(db, [tok(world)])
        await db.commit()
    rec = Recorder()
    push_svc.set_push_provider(rec)
    res, d = await send_push_for(nid)
    assert d.status == DeliveryStatus.FAILED and not rec.calls


def expo_transport(handler_log, responder):
    def handler(request: httpx.Request):
        msgs = json.loads(request.content)
        handler_log.append((request, msgs))
        return httpx.Response(200, json={"data": responder(msgs)})
    return httpx.MockTransport(handler)


async def test_expo_batches_of_100_and_auth_header():
    log = []
    p = push_svc.ExpoPushProvider(
        access_token="secret",
        transport=expo_transport(
            log, lambda msgs: [{"status": "ok", "id": f"t{i}"} for i, _ in enumerate(msgs)]))
    tokens = [f"ExponentPushToken[{i}]" for i in range(250)]
    res = await p.send(tokens=tokens, title="a", body="b",
                       data={"x": 1}, category="approval")
    assert res.ok and not res.invalid_tokens
    assert [len(m) for _, m in log] == [100, 100, 50]
    assert log[0][0].headers["authorization"] == "Bearer secret"
    assert str(log[0][0].url) == push_svc.EXPO_URL
    first = log[0][1][0]
    assert first["to"] == tokens[0] and first["categoryId"] == "approval"
    assert first["data"] == {"x": 1}


async def test_expo_device_not_registered_revokes_token(world):
    await add_token(world, "e1", n="a")
    await add_token(world, "e1", n="b")
    dead = tok(world, "b")

    def responder(msgs):
        return [{"status": "error", "message": "gone",
                 "details": {"error": "DeviceNotRegistered"}}
                if m["to"] == dead else {"status": "ok", "id": "x1"}
                for m in msgs]
    push_svc.set_push_provider(push_svc.ExpoPushProvider(
        transport=expo_transport([], responder)))
    nid = await notify_user(world, "e1", "approval_pending")
    res, d = await send_push_for(nid)
    assert res.ok and d.status == DeliveryStatus.SENT
    async with SessionLocal() as db:
        assert await push_svc.active_tokens(db, world["ids"]["e1"]) == [tok(world, "a")]


async def test_expo_all_unregistered_marks_failed_and_revokes(world):
    await add_token(world, "e1")
    push_svc.set_push_provider(push_svc.ExpoPushProvider(
        transport=expo_transport([], lambda msgs: [
            {"status": "error", "details": {"error": "DeviceNotRegistered"}}
            for _ in msgs])))
    nid = await notify_user(world, "e1", "approval_pending")
    res, d = await send_push_for(nid)
    assert not res.ok and d.status == DeliveryStatus.FAILED
    async with SessionLocal() as db:
        assert await push_svc.active_tokens(db, world["ids"]["e1"]) == []


async def test_expo_http_error_is_retryable(world):
    await add_token(world, "e1")
    push_svc.set_push_provider(push_svc.ExpoPushProvider(
        transport=httpx.MockTransport(lambda r: httpx.Response(503, text="down"))))
    nid = await notify_user(world, "e1", "approval_pending")
    res, d = await send_push_for(nid)
    assert not res.ok and d.status == DeliveryStatus.QUEUED
    async with SessionLocal() as db:
        assert len(await push_svc.active_tokens(db, world["ids"]["e1"])) == 1


def test_default_provider_is_log():
    assert push_svc.provider_from_settings().name == "log"


# ------------------------------- actions -------------------------------

async def mk_item(w, approver, requester="req"):
    w["n"][0] += 1
    async with SessionLocal() as db:
        it = ApprovalItem(resource_type="push_test",
                          resource_id=f"{w['sfx']}{w['n'][0]}",
                          status=ApprovalStatus.PENDING, current_step_number=1,
                          requested_by_id=w["ids"][requester])
        db.add(it)
        await db.flush()
        db.add(ApprovalStep(approval_item_id=it.id, step_number=1,
                            approver_id=w["ids"][approver],
                            status=ApprovalStatus.PENDING))
        await db.commit()
        return it.id, it.resource_id


async def item_status(iid):
    async with SessionLocal() as db:
        return (await db.get(ApprovalItem, iid, populate_existing=True)).status


async def act(client, h, nid, action, **kw):
    return await client.post(f"{API}/notifications/actions", headers=h,
                             json={"notification_id": nid, "action": action, **kw})


async def test_action_approve_and_reject(client, world):
    ha = await login(client, world, "apr")
    iid, rid = await mk_item(world, "apr")
    nid = await mk_notif(world, "apr", event_type="approval_pending",
                         rtype="push_test", rid=rid)
    async with SessionLocal() as db:
        p = await push_svc.build_payload(db, await db.get(Notification, nid))
    assert p["category"] == "approval" and p["actions"] == ["approve", "reject"]
    assert p["user_id"] == world["ids"]["apr"]
    r = await act(client, ha, nid, "approve", comment="ok")
    assert r.status_code == 200, r.text
    assert r.json()["target"]["type"] == "approval"
    assert await item_status(iid) == ApprovalStatus.APPROVED
    async with SessionLocal() as db:
        assert (await db.get(Notification, nid)).is_read is True
    # already actioned -> clean 4xx
    r = await act(client, ha, nid, "approve")
    assert r.status_code == 400
    # reject path on a fresh item
    iid2, rid2 = await mk_item(world, "apr")
    nid2 = await mk_notif(world, "apr", rtype="push_test", rid=rid2)
    r = await act(client, ha, nid2, "reject", comment="no")
    assert r.status_code == 200, r.text
    assert await item_status(iid2) == ApprovalStatus.REJECTED


async def test_action_approve_sod_failure(client, world):
    ha = await login(client, world, "apr")
    iid, rid = await mk_item(world, "apr", requester="apr")  # own request
    nid = await mk_notif(world, "apr", rtype="push_test", rid=rid)
    r = await act(client, ha, nid, "approve")
    assert r.status_code == 403
    assert await item_status(iid) == ApprovalStatus.PENDING


async def test_action_approve_requires_authorisation(client, world):
    ho = await login(client, world, "oth")
    iid, rid = await mk_item(world, "apr")
    nid = await mk_notif(world, "oth", rtype="push_test", rid=rid)  # oth is not an approver
    r = await act(client, ho, nid, "approve")
    assert r.status_code == 403
    assert await item_status(iid) == ApprovalStatus.PENDING


async def test_action_foreign_notification_is_404(client, world):
    ho = await login(client, world, "oth")
    iid, rid = await mk_item(world, "apr")
    nid = await mk_notif(world, "apr", rtype="push_test", rid=rid)
    r = await act(client, ho, nid, "approve")
    assert r.status_code == 404
    assert (await act(client, ho, 999999999, "approve")).status_code == 404
    assert await item_status(iid) == ApprovalStatus.PENDING


async def test_action_wrong_kind_is_400(client, world):
    ha = await login(client, world, "apr")
    iid, rid = await mk_item(world, "apr")
    nid = await mk_notif(world, "apr", rtype="push_test", rid=rid)
    for a in ("claim", "safe", "acknowledge"):
        assert (await act(client, ha, nid, a)).status_code == 400
    nid2 = await mk_notif(world, "apr")  # no target
    assert (await act(client, ha, nid2, "approve")).status_code == 400
    assert (await act(client, ha, nid, "explode")).status_code == 422


async def test_action_chain_approve(client, world):
    ha = await login(client, world, "apr")
    async with SessionLocal() as db:
        inst = ChainedApprovalInstance(
            chain_id=None, entity_type="expense",
            entity_id=990000000 + int(uuid.uuid4().int % 1000000),
            submitter_id=world["ids"]["req"], amount_paise=1000,
            status="pending", current_step_order=1)
        db.add(inst)
        await db.flush()
        db.add(ChainedApprovalStepInstance(
            instance_id=inst.id, step_order=1, approver_type="specific_user",
            approver_user_id=world["ids"]["apr"], mode="sequential",
            parallel_rule="all", status="pending"))
        await db.commit()
        iid = inst.id
    nid = await mk_notif(world, "apr", rtype="chained_approval_instance",
                         rid=str(iid))
    async with SessionLocal() as db:
        p = await push_svc.build_payload(db, await db.get(Notification, nid))
    assert p["category"] == "approval"
    r = await act(client, ha, nid, "approve")
    assert r.status_code == 200, r.text
    assert r.json()["target"]["kind"] == "chain"
    async with SessionLocal() as db:
        assert (await db.get(ChainedApprovalInstance, iid,
                             populate_existing=True)).status == "approved"


async def test_action_attendance_gate_applies_to_approvals_not_broadcasts(
        client, world, monkeypatch):
    from fastapi import HTTPException

    async def deny(db, user):
        raise HTTPException(403, "punch in first")
    monkeypatch.setattr(deps, "verify_attendance", deny)
    ha = await login(client, world, "apr")
    iid, rid = await mk_item(world, "apr")
    nid = await mk_notif(world, "apr", rtype="push_test", rid=rid)
    assert (await act(client, ha, nid, "approve")).status_code == 403
    assert await item_status(iid) == ApprovalStatus.PENDING


async def mk_broadcast(w, *, safety=True, ack=True):
    async with SessionLocal() as db:
        b = await bsvc.create_and_send(
            db, sender_id=w["ids"]["adm"], title="Drill", message="Go",
            severity="critical", audience="department",
            audience_value=w["dx"], requires_ack=ack, safety_check=safety)
        await db.commit()
        return b.id


async def bc_notif(w, tag, bid):
    async with SessionLocal() as db:
        return (await db.execute(select(Notification.id).where(
            Notification.user_id == w["ids"][tag],
            Notification.resource_type == "broadcast",
            Notification.resource_id == str(bid)))).scalar_one()


async def recipient(w, tag, bid):
    async with SessionLocal() as db:
        return (await db.execute(select(BroadcastRecipient).where(
            BroadcastRecipient.broadcast_id == bid,
            BroadcastRecipient.user_id == w["ids"][tag]
        ).execution_options(populate_existing=True))).scalar_one()


async def test_action_broadcast_safe_need_help_and_ack(client, world):
    h1, h2 = await login(client, world, "e1"), await login(client, world, "e2")
    bid = await mk_broadcast(world)
    n1, n2 = await bc_notif(world, "e1", bid), await bc_notif(world, "e2", bid)
    async with SessionLocal() as db:
        p = await push_svc.build_payload(db, await db.get(Notification, n1))
    assert p["category"] == "broadcast_safety" and p["actions"] == ["safe", "need_help"]
    r = await act(client, h1, n1, "safe")
    assert r.status_code == 200, r.text
    assert (await recipient(world, "e1", bid)).safety_status == "safe"
    r = await act(client, h2, n2, "need_help", comment="trapped")
    assert r.status_code == 200, r.text
    rr = await recipient(world, "e2", bid)
    assert rr.safety_status == "need_help" and rr.safety_note == "trapped"
    # ack-only broadcast
    bid2 = await mk_broadcast(world, safety=False, ack=True)
    n3 = await bc_notif(world, "e1", bid2)
    async with SessionLocal() as db:
        p = await push_svc.build_payload(db, await db.get(Notification, n3))
    assert p["category"] == "broadcast_ack" and p["actions"] == ["acknowledge"]
    assert (await act(client, h1, n3, "safe")).status_code == 400  # no safety check
    r = await act(client, h1, n3, "acknowledge")
    assert r.status_code == 200, r.text
    assert (await recipient(world, "e1", bid2)).acked_at is not None


async def test_action_broadcast_foreign_notification_404(client, world):
    h2 = await login(client, world, "e2")
    bid = await mk_broadcast(world)
    n1 = await bc_notif(world, "e1", bid)
    assert (await act(client, h2, n1, "safe")).status_code == 404
    assert (await recipient(world, "e1", bid)).safety_status is None


async def test_action_open_shift_claim(client, world):
    h1, h2 = await login(client, world, "e1"), await login(client, world, "e2")
    async with SessionLocal() as db:
        adm = await db.get(User, world["ids"]["adm"])
        s = await os_svc.create_open_shift(
            db, adm, work_date=date.today() + timedelta(days=20),
            shift_template_id=world["tpl"], department=world["dx"], slots=1)
        await db.commit()
        sid = s.id
    async with SessionLocal() as db:
        nid = (await db.execute(select(Notification.id).where(
            Notification.user_id == world["ids"]["e1"],
            Notification.resource_type == "open_shift",
            Notification.resource_id == str(sid)))).scalar_one()
        n = await db.get(Notification, nid)
        assert n.event_type == "open_shift_available"
        p = await push_svc.build_payload(db, n)
    assert p["category"] == "open_shift" and p["actions"] == ["claim"]
    assert (await act(client, h2, nid, "claim")).status_code == 404  # e2 is not owner
    r = await act(client, h1, nid, "claim")
    assert r.status_code == 200, r.text
    async with SessionLocal() as db:
        c = (await db.execute(select(OpenShiftClaim).where(
            OpenShiftClaim.open_shift_id == sid,
            OpenShiftClaim.user_id == world["ids"]["e1"]))).scalar_one()
        assert c.status == "pending"
    # second claim: same service -> conflict
    assert (await act(client, h1, nid, "claim")).status_code == 409


# ------------------------------- review fixes -------------------------------

async def test_token_format_validated(client, world):
    h = await login(client, world, "e1")
    for bad in ("not-a-token-at-all", "ExponentPushToken[]", "ExponentPushToken[a b]"):
        r = await client.post(f"{API}/devices", headers=h,
                              json={"token": bad, "platform": "ios"})
        assert r.status_code == 422, bad
    r = await client.post(f"{API}/devices", headers=h, json={
        "token": f"ExpoPushToken[{world['sfx']}z]", "platform": "ios"})
    assert r.status_code == 200


async def test_token_move_is_audited(client, world):
    h1, h2 = await login(client, world, "e1"), await login(client, world, "e2")
    body = {"token": tok(world), "platform": "ios"}
    await client.post(f"{API}/devices", json=body, headers=h1)
    await client.post(f"{API}/devices", json=body, headers=h2)
    async with SessionLocal() as db:
        a = (await db.execute(select(AuditLog).where(
            AuditLog.action == "DEVICE_TOKEN_MOVED",
            AuditLog.user_id == world["ids"]["e2"]))).scalars().all()
    assert len(a) == 1
    assert a[0].details == {"from_user_id": world["ids"]["e1"],
                            "to_user_id": world["ids"]["e2"]}


async def test_sensitive_events_get_generic_push_text(world):
    await add_token(world, "e1")
    rec = Recorder()
    push_svc.set_push_provider(rec)
    async with SessionLocal() as db:
        nid = await nd.notify(db, user_id=world["ids"]["e1"],
                              event_type="expense_approved", title="Claim Rs 5000",
                              message="Rs 5000 approved")
        await db.commit()
    # expense default push is off -> opt in so a push row exists
    d_rows = [d for d in await deliveries(nid) if d.channel == Channel.PUSH]
    assert d_rows[0].status == DeliveryStatus.SKIPPED_PREF
    async with SessionLocal() as db:
        db.add(UserNotificationPreference(
            user_id=world["ids"]["e1"], category="expense",
            channel=Channel.PUSH, enabled=True))
        await db.commit()
    nid = await notify_user(world, "e1", "expense_approved")
    async with SessionLocal() as db:
        n = await db.get(Notification, nid)
        n.title, n.message = "Claim Rs 5000", "Rs 5000 approved"
        await db.commit()
    await send_push_for(nid)
    assert rec.calls[0]["title"] == "New update"
    assert rec.calls[0]["body"] == "Open the app to view details."
    async with SessionLocal() as db:  # in-app text untouched
        assert (await db.get(Notification, nid)).message == "Rs 5000 approved"


async def test_sensitive_template_gets_generic_push_text(world):
    await add_token(world, "e1")
    ev = f"pushpriv_{world['sfx']}"
    async with SessionLocal() as db:
        db.add(NotificationTemplate(event_type=ev, channel="email", category="other",
                                    subject="s", body_text="b", is_sensitive=True))
        db.add(UserNotificationPreference(
            user_id=world["ids"]["e1"], category="other",
            channel=Channel.PUSH, enabled=True))
        await db.commit()
    rec = Recorder()
    push_svc.set_push_provider(rec)
    nid = await notify_user(world, "e1", ev)
    await send_push_for(nid)
    assert rec.calls[0]["title"] == "New update"
    # a non-sensitive approval keeps its text
    nid2 = await notify_user(world, "e1", "approval_pending")
    await send_push_for(nid2)
    assert rec.calls[1]["title"] == "Hello" and rec.calls[1]["body"] == "World"


def test_push_defaults_limited():
    d = nd.DEFAULT_ENABLED_CHANNELS_BY_CATEGORY
    for c in ("approvals", "leave", "scheduling"):
        assert "push" in d[c]
    for c in ("overtime", "payroll", "performance", "expense", "statutory", "other"):
        assert "push" not in d[c]


async def test_push_default_off_for_other_categories_and_pref_api(client, world):
    await add_token(world, "e1")
    h = await login(client, world, "e1")
    n1 = await notify_user(world, "e1", "payslip_published")
    assert [d.status for d in await deliveries(n1) if d.channel == Channel.PUSH] \
        == [DeliveryStatus.SKIPPED_PREF]
    r = await client.put(f"{API}/me/notifications/preferences", headers=h, json=[
        {"category": "payroll", "channel": "push", "enabled": True}])
    assert r.status_code == 200
    assert any(p["category"] == "payroll" and p["channel"] == "push" and p["enabled"]
               for p in r.json())
    n2 = await notify_user(world, "e1", "payslip_published")
    assert [d.status for d in await deliveries(n2) if d.channel == Channel.PUSH] \
        == [DeliveryStatus.QUEUED]
    n3 = await notify_user(world, "e1", "open_shift_available")
    assert [d.status for d in await deliveries(n3) if d.channel == Channel.PUSH] \
        == [DeliveryStatus.QUEUED]


async def test_expo_missing_tickets_are_transient():
    p = push_svc.ExpoPushProvider(transport=expo_transport(
        [], lambda msgs: [{"status": "ok", "id": "t0"}, {"status": "ok", "id": "t1"}]))
    toks = [f"ExponentPushToken[{i}]" for i in range(3)]
    res = await p.send(tokens=toks, title="a", body="b", data={})
    assert res.transient and res.ok_tokens == toks[:2] and res.error


async def test_partial_failure_retries_only_unsent_tokens(world):
    await add_token(world, "e1", n="a")
    await add_token(world, "e1", n="b")
    bad = tok(world, "b")
    state = {"fail": True}
    seen = []

    def responder(msgs):
        seen.append([m["to"] for m in msgs])
        return [{"status": "error", "message": "slow",
                 "details": {"error": "MessageRateExceeded"}}
                if (m["to"] == bad and state["fail"]) else {"status": "ok", "id": "id-" + m["to"][-3:]}
                for m in msgs]
    push_svc.set_push_provider(push_svc.ExpoPushProvider(
        transport=expo_transport([], responder)))
    nid = await notify_user(world, "e1", "approval_pending")
    res, d = await send_push_for(nid)
    assert not res.ok and d.status == DeliveryStatus.QUEUED
    assert d.context_json["push_sent_tokens"] == [tok(world, "a")]
    state["fail"] = False
    res, d = await send_push_for(nid)
    assert res.ok and d.status == DeliveryStatus.SENT
    assert seen == [[tok(world, "a"), bad], [bad]]


async def test_receipts_poll_revokes_device_not_registered(world):
    await add_token(world, "e1", n="a")
    await add_token(world, "e1", n="b")
    a, b = tok(world, "a"), tok(world, "b")
    push_svc.set_push_provider(push_svc.ExpoPushProvider(transport=expo_transport(
        [], lambda msgs: [{"status": "ok", "id": "tk-" + m["to"][-3:]} for m in msgs])))
    nid = await notify_user(world, "e1", "approval_pending")
    _, d = await send_push_for(nid)
    assert json.loads(d.provider_ticket_ids) == [[a, "tk-" + a[-3:]], [b, "tk-" + b[-3:]]]

    calls = []

    def handler(request):
        ids = json.loads(request.content)["ids"]
        calls.append(ids)
        assert "getReceipts" in str(request.url)
        return httpx.Response(200, json={"data": {
            "tk-" + b[-3:]: {"status": "error",
                             "details": {"error": "DeviceNotRegistered"}}}})
    push_svc.set_push_provider(push_svc.ExpoPushProvider(
        transport=httpx.MockTransport(handler)))
    async with SessionLocal() as db:
        out = await push_svc.poll_receipts(db)
    assert out["revoked"] == 1 and calls
    async with SessionLocal() as db:
        assert await push_svc.active_tokens(db, world["ids"]["e1"]) == [a]
    d = [x for x in await deliveries(nid) if x.channel == Channel.PUSH][0]
    # token b's ticket handled; a's has no receipt yet -> kept for later
    assert json.loads(d.provider_ticket_ids) == [[a, "tk-" + a[-3:]]]


async def test_receipts_job_registered():
    from app.services.scheduler import REGISTRY
    assert REGISTRY["push_receipts_poll"].default_cadence_cron == "*/15 * * * *"


async def test_replay_legacy_approval_after_reassignment_or_escalation(client, world):
    ha = await login(client, world, "apr")
    iid, rid = await mk_item(world, "apr")
    nid = await mk_notif(world, "apr", event_type="approval_pending",
                         rtype="push_test", rid=rid)
    async with SessionLocal() as db:  # escalated / reassigned to someone else
        st = (await db.execute(select(ApprovalStep).where(
            ApprovalStep.approval_item_id == iid))).scalar_one()
        st.approver_id = world["ids"]["oth"]
        await db.commit()
    r = await act(client, ha, nid, "approve")
    assert r.status_code in (400, 403)
    assert await item_status(iid) == ApprovalStatus.PENDING
    async with SessionLocal() as db:  # item decided elsewhere
        it = await db.get(ApprovalItem, iid)
        it.status = ApprovalStatus.APPROVED
        await db.commit()
    assert (await act(client, ha, nid, "approve")).status_code == 400


async def test_replay_chain_after_escalation(client, world):
    ha = await login(client, world, "apr")
    async with SessionLocal() as db:
        inst = ChainedApprovalInstance(
            chain_id=None, entity_type="expense",
            entity_id=990000000 + int(uuid.uuid4().int % 1000000),
            submitter_id=world["ids"]["req"], amount_paise=1000,
            status="pending", current_step_order=1)
        db.add(inst)
        await db.flush()
        db.add(ChainedApprovalStepInstance(
            instance_id=inst.id, step_order=1, approver_type="specific_user",
            approver_user_id=world["ids"]["oth"], mode="sequential",
            parallel_rule="all", status="pending"))  # escalated away from apr
        await db.commit()
        iid = inst.id
    nid = await mk_notif(world, "apr", rtype="chained_approval_instance", rid=str(iid))
    r = await act(client, ha, nid, "approve")
    assert r.status_code in (400, 403), r.text
    async with SessionLocal() as db:
        assert (await db.get(ChainedApprovalInstance, iid,
                             populate_existing=True)).status == "pending"
