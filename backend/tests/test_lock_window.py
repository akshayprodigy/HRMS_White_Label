"""Lock window + emergency rescheduling + acknowledgement + call-back
compensation (Roadmap v2 Phase 2, Task 4)."""
import uuid
from datetime import date, time, timedelta, datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from _cleanup import purge_gap_notifications, purge_shift_templates
from app.api import deps
from app.api.v1.endpoints.roster_common import commit_or_409
from app.core.config import settings
from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.main import create_app
from app.models.approval import ApprovalItem, ApprovalStep
from app.models.audit import AuditLog
from app.models.comp_off import CompOffAccrual
from app.models.coverage_gap import CoverageGap
from app.models.department import Department
from app.models.employee import Employee, EmployeeStatus
from app.models.notification import Notification
from app.models.open_shift import OpenShift, OpenShiftClaim, ShiftDropRequest
from app.models.payroll import PayrollRun, PayrollRunStatus
from app.models.roster import (
    RosterChangeRequest, RosterEntry, RosterEntryHistory, RosterStatus,
    ScheduleChangeAck,
)
from app.models.rotation_pattern import RotationPattern
from app.models.schedule_delegation import DelegationScope, ScheduleDelegation
from app.models.shift import ShiftTemplate
from app.models.shift_allowance import ShiftAllowanceEntry, ShiftAllowanceKind
from app.models.shift_swap import ShiftSwapRequest
from app.models.system import SystemSetting
from app.models.user import User
from app.services import coverage_gaps as gap_svc
from app.services import roster as roster_svc
from app.services import time_rules

R = f"{settings.API_V1_STR}/roster"
PW = "test@12345"
TODAY = datetime.now(timezone.utc).date()
LOCK = 5
W = TODAY + timedelta(days=2)      # inside the window
W2 = TODAY + timedelta(days=3)
W3 = TODAY + timedelta(days=4)
O = TODAY + timedelta(days=20)     # outside the window
KEYS = ("schedule.lock_days", "schedule.callback_compensation",
        "schedule.callback_allowance_amount")


async def rules(**kw):
    m = {"schedule." + k: str(v) for k, v in kw.items()}
    async with SessionLocal() as db:
        await time_rules.set_time_rules(db, m)


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
    dept = f"LW{sfx}"
    async with SessionLocal() as db:   # remember + restore the time rules
        saved = {r.key: r.value for r in (await db.execute(
            select(SystemSetting).where(SystemSetting.key.in_(KEYS)))
        ).scalars().all()}
    await rules(lock_days=LOCK)
    run_ids = []
    try:
        async with SessionLocal() as db:
            def mk(tag, **kw):
                return User(email=f"lw_{tag}_{sfx}@t.com", full_name=f"LW {tag}",
                            hashed_password=get_password_hash(PW),
                            is_active=True, **kw)
            us = {t: mk(t) for t in ("e1", "e2", "e3", "sx", "dov", "dnv")}
            us["admin"] = mk("admin", is_superuser=True)
            db.add_all(us.values())
            db.add(Department(name=dept))
            t1 = ShiftTemplate(name=f"LWT1{sfx}", start_time=time(9), end_time=time(17))
            t2 = ShiftTemplate(name=f"LWT2{sfx}", start_time=time(14), end_time=time(22))
            db.add_all([t1, t2])
            await db.commit()
            for tag in ("e1", "e2", "e3"):
                db.add(Employee(
                    user_id=us[tag].id, employee_id=f"LW{sfx}{tag}",
                    department=dept, designation="Tester",
                    date_of_joining=date(2020, 1, 1),
                    status=EmployeeStatus.ACTIVE))
            await db.execute(Department.__table__.update().where(
                Department.name == dept).values(head_user_id=us["sx"].id))
            for tag, ov in (("dov", True), ("dnv", False)):
                db.add(ScheduleDelegation(
                    grantee_id=us[tag].id, scope_type=DelegationScope.EMPLOYEES,
                    employee_ids=[us["e1"].id, us["e2"].id],
                    can_publish=True, can_approve_changes=True,
                    can_emergency_override=ov,
                    valid_from=TODAY - timedelta(days=1)))
            await db.commit()
            ids = {t: u.id for t, u in us.items()}
            ids.update(t1=t1.id, t2=t2.id)
        yield {"ids": ids, "sfx": sfx, "dept": dept, "runs": run_ids,
               "email": lambda t: f"lw_{t}_{sfx}@t.com"}
    finally:
        async with SessionLocal() as db:
            uids = list((await db.execute(select(User.id).where(
                User.email.like(f"lw\\_%\\_{sfx}@t.com")))).scalars().all())
            acc_ids = [str(i) for i in (await db.execute(
                select(CompOffAccrual.id).where(
                    CompOffAccrual.user_id.in_(uids)))).scalars().all()]
            if acc_ids:
                items = list((await db.execute(select(ApprovalItem.id).where(
                    ApprovalItem.resource_type == "comp_off_accrual",
                    ApprovalItem.resource_id.in_(acc_ids)))).scalars().all())
                if items:
                    await db.execute(delete(ApprovalStep).where(
                        ApprovalStep.approval_item_id.in_(items)))
                    await db.execute(delete(ApprovalItem).where(
                        ApprovalItem.id.in_(items)))
            await db.execute(delete(ShiftAllowanceEntry).where(
                ShiftAllowanceEntry.user_id.in_(uids)))
            if run_ids:
                await db.execute(delete(PayrollRun).where(
                    PayrollRun.id.in_(run_ids)))
            await db.execute(delete(AuditLog).where(
                AuditLog.user_id.in_(uids), AuditLog.action.like("roster.%")))
            drop_ids = [str(i) for i in (await db.execute(
                select(ShiftDropRequest.id).where(
                    ShiftDropRequest.user_id.in_(uids)))).scalars().all()]
            shift_ids = [str(i) for i in (await db.execute(
                select(OpenShift.id).where(
                    OpenShift.created_by_id.in_(uids)))).scalars().all()]
            swap_ids = [str(i) for i in (await db.execute(
                select(ShiftSwapRequest.id).where(
                    ShiftSwapRequest.requester_id.in_(uids)))).scalars().all()]
            await db.execute(delete(Notification).where(
                Notification.user_id.in_(uids)))
            for rt, rids in (("shift_drop", drop_ids), ("open_shift", shift_ids),
                             ("shift_swap", swap_ids)):
                if rids:
                    await db.execute(delete(Notification).where(
                        Notification.resource_type == rt,
                        Notification.resource_id.in_(rids)))
            await db.execute(delete(ShiftSwapRequest).where(
                ShiftSwapRequest.requester_id.in_(uids)))
            await db.execute(delete(ShiftDropRequest).where(
                ShiftDropRequest.user_id.in_(uids)))
            await db.execute(delete(OpenShiftClaim).where(
                OpenShiftClaim.user_id.in_(uids)))
            await db.execute(delete(OpenShift).where(
                OpenShift.created_by_id.in_(uids)))
            await db.execute(delete(RosterChangeRequest).where(
                RosterChangeRequest.employee_id.in_(uids)))
            await db.execute(delete(RotationPattern).where(
                RotationPattern.name.like(f"LWROT{sfx}%")))
            await db.execute(Department.__table__.update().where(
                Department.name == dept).values(
                head_user_id=None, deputy_head_user_id=None))
            await db.execute(delete(RosterEntryHistory).where(
                RosterEntryHistory.employee_id.in_(uids)))
            await db.execute(delete(RosterEntry).where(
                RosterEntry.employee_id.in_(uids)))
            await db.execute(delete(ScheduleDelegation).where(
                ScheduleDelegation.grantee_id.in_(uids)))
            await db.execute(delete(Employee).where(Employee.user_id.in_(uids)))
            await db.execute(delete(Department).where(Department.name == dept))
            tids = list((await db.execute(select(ShiftTemplate.id).where(
                ShiftTemplate.name.in_([f"LWT1{sfx}", f"LWT2{sfx}"])))).scalars().all())
            await purge_gap_notifications(db, tids)
            await purge_shift_templates(db, tids)
            await db.execute(delete(User).where(User.id.in_(uids)))
            await db.execute(delete(SystemSetting).where(
                SystemSetting.key.in_(KEYS)))
            for k, v in saved.items():
                db.add(SystemSetting(key=k, value=v))
            await db.commit()


async def _h(client, w, tag):
    r = await client.post(f"{settings.API_V1_STR}/auth/login",
                          data={"username": w["email"](tag), "password": PW})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _pub(uid, day, tpl=None, off=False, status=RosterStatus.PUBLISHED):
    async with SessionLocal() as db:
        db.add(RosterEntry(employee_id=uid, work_date=day,
                           shift_template_id=None if off else tpl,
                           is_week_off=off, status=status))
        await db.commit()


async def _cell(uid, day):
    async with SessionLocal() as db:
        r = (await db.execute(select(RosterEntry).where(
            RosterEntry.employee_id == uid, RosterEntry.work_date == day
        ))).scalars().first()
        return None if r is None else (r.shift_template_id, r.is_week_off, r.status)


async def _entry_id(uid, day):
    async with SessionLocal() as db:
        return (await db.execute(select(RosterEntry.id).where(
            RosterEntry.employee_id == uid, RosterEntry.work_date == day
        ))).scalar_one()


async def _hist(uid, day=None):
    async with SessionLocal() as db:
        q = select(RosterEntryHistory).where(RosterEntryHistory.employee_id == uid)
        if day:
            q = q.where(RosterEntryHistory.work_date == day)
        return list((await db.execute(q.order_by(RosterEntryHistory.id))).scalars().all())


async def _acks(uid):
    async with SessionLocal() as db:
        return list((await db.execute(select(ScheduleChangeAck).where(
            ScheduleChangeAck.user_id == uid))).scalars().all())


async def _notes(uid, title):
    async with SessionLocal() as db:
        return list((await db.execute(select(Notification).where(
            Notification.user_id == uid, Notification.title == title))).scalars().all())


async def _assert_emergency(uid, day, n=1):
    hs = [h for h in await _hist(uid, day) if h.is_emergency]
    assert len(hs) == n, hs
    acks = await _acks(uid)
    assert any(a.history_id == hs[-1].id and a.acknowledged_at is None for a in acks)
    assert await _notes(uid, "Urgent schedule change - please acknowledge")
    return hs[-1]


def _locked_403(r, day=None):
    assert r.status_code == 403, r.text
    assert "locked" in r.text
    if day:
        assert day.isoformat() in r.text


# ------------------------------ lock_days 0 ------------------------------

async def test_lock_off_changes_nothing(client, world):
    ids = world["ids"]
    await rules(lock_days=0)
    await _pub(ids["e1"], W, ids["t1"])
    h = await _h(client, world, "sx")
    eid = await _entry_id(ids["e1"], W)
    r = await client.patch(f"{R}/entries/{eid}", headers=h, json={
        "shift_template_id": ids["t2"], "reason": "regular change"})
    assert r.status_code == 200, r.text
    hs = await _hist(ids["e1"], W)
    assert len(hs) == 1 and not hs[0].is_emergency
    assert await _acks(ids["e1"]) == []
    r = await client.post(f"{R}/bulk", headers=h, json={
        "employee_ids": [ids["e1"]], "start": W.isoformat(), "end": W.isoformat(),
        "pattern": {str(W.weekday()): ids["t1"]}})
    assert r.status_code == 200 and r.json()["updated"] == 1


# ------------------------------ entries ------------------------------

async def test_patch_blocked_for_head_allowed_for_admin(client, world):
    ids = world["ids"]
    await _pub(ids["e1"], W, ids["t1"])
    eid = await _entry_id(ids["e1"], W)
    hx = await _h(client, world, "sx")
    r = await client.patch(f"{R}/entries/{eid}", headers=hx, json={
        "shift_template_id": ids["t2"], "reason": "needs cover"})
    _locked_403(r, W)
    assert (await _cell(ids["e1"], W))[0] == ids["t1"]
    ha = await _h(client, world, "admin")
    r = await client.patch(f"{R}/entries/{eid}", headers=ha, json={
        "shift_template_id": ids["t2"]})
    assert r.status_code == 422          # reason mandatory
    r = await client.patch(f"{R}/entries/{eid}", headers=ha, json={
        "shift_template_id": ids["t2"], "reason": "client escalation"})
    assert r.status_code == 200, r.text
    h = await _assert_emergency(ids["e1"], W)
    assert h.reason == "client escalation" and h.new_shift_template_id == ids["t2"]


async def test_patch_outside_window_unaffected(client, world):
    ids = world["ids"]
    await _pub(ids["e1"], O, ids["t1"])
    eid = await _entry_id(ids["e1"], O)
    hx = await _h(client, world, "sx")
    r = await client.patch(f"{R}/entries/{eid}", headers=hx, json={
        "shift_template_id": ids["t2"], "reason": "planned change"})
    assert r.status_code == 200, r.text
    assert not any(h.is_emergency for h in await _hist(ids["e1"]))
    assert await _acks(ids["e1"]) == []


async def test_override_delegate_vs_plain_delegate(client, world):
    ids = world["ids"]
    await _pub(ids["e1"], W, ids["t1"])
    await _pub(ids["e2"], W, ids["t1"])
    e1, e2 = await _entry_id(ids["e1"], W), await _entry_id(ids["e2"], W)
    hn = await _h(client, world, "dnv")
    r = await client.patch(f"{R}/entries/{e1}", headers=hn, json={
        "shift_template_id": ids["t2"], "reason": "needs cover"})
    _locked_403(r)
    ho = await _h(client, world, "dov")
    r = await client.patch(f"{R}/entries/{e1}", headers=ho, json={
        "shift_template_id": ids["t2"], "reason": "needs cover"})
    assert r.status_code == 200, r.text
    await _assert_emergency(ids["e1"], W)
    # same override delegate cannot touch an employee outside its scope
    r = await client.patch(f"{R}/entries/{e2}", headers=ho, json={
        "shift_template_id": ids["t2"], "reason": "needs cover"})
    assert r.status_code == 200      # e2 IS in scope; sanity
    await _assert_emergency(ids["e2"], W)


async def test_upsert_single_entry(client, world):
    ids = world["ids"]
    await _pub(ids["e1"], W, ids["t1"])
    body = {"employee_id": ids["e1"], "work_date": W.isoformat(),
            "shift_template_id": ids["t2"], "reason": "emergency swap"}
    hx = await _h(client, world, "sx")
    _locked_403(await client.post(f"{R}/entries", headers=hx, json=body), W)
    ha = await _h(client, world, "admin")
    assert (await client.post(f"{R}/entries", headers=ha,
                              json={**body, "reason": None})).status_code == 422
    r = await client.post(f"{R}/entries", headers=ha, json=body)
    assert r.status_code == 200, r.text
    await _assert_emergency(ids["e1"], W)
    # a brand-new live cell inside the window is locked too
    r = await client.post(f"{R}/entries", headers=hx, json={
        "employee_id": ids["e3"], "work_date": W.isoformat(),
        "shift_template_id": ids["t1"], "reason": "extra hand"})
    _locked_403(r)
    # drafts are not live: allowed
    r = await client.post(f"{R}/entries", headers=hx, json={
        "employee_id": ids["e3"], "work_date": W.isoformat(),
        "shift_template_id": ids["t1"], "status": "draft"})
    assert r.status_code == 200 and r.json()["status"] == "draft"


async def test_delete_entry(client, world):
    ids = world["ids"]
    await _pub(ids["e1"], W, ids["t1"])
    eid = await _entry_id(ids["e1"], W)
    hx = await _h(client, world, "sx")
    _locked_403(await client.delete(
        f"{R}/entries/{eid}", headers=hx, params={"reason": "not needed"}))
    ha = await _h(client, world, "admin")
    r = await client.delete(f"{R}/entries/{eid}", headers=ha,
                            params={"reason": "not needed"})
    assert r.status_code == 200
    assert await _cell(ids["e1"], W) is None
    h = await _assert_emergency(ids["e1"], W)
    assert h.action == "delete"


async def test_bulk_and_rotation(client, world):
    ids = world["ids"]
    await _pub(ids["e1"], W, ids["t1"])
    pat = {"employee_ids": [ids["e1"]], "start": W.isoformat(),
           "end": W.isoformat(), "pattern": {str(W.weekday()): ids["t2"]}}
    hx = await _h(client, world, "sx")
    _locked_403(await client.post(f"{R}/bulk", headers=hx, json={**pat, "reason": "urgent"}), W)
    assert (await _cell(ids["e1"], W))[0] == ids["t1"]
    ha = await _h(client, world, "admin")
    assert (await client.post(f"{R}/bulk", headers=ha, json=pat)).status_code == 422
    r = await client.post(f"{R}/bulk", headers=ha, json={**pat, "reason": "urgent"})
    assert r.status_code == 200 and r.json()["updated"] == 1, r.text
    await _assert_emergency(ids["e1"], W)
    # rotation apply
    rp = await client.post(f"{R}/rotations", headers=ha, json={
        "name": f"LWROT{world['sfx']}", "cycle": [ids["t1"]]})
    assert rp.status_code == 200, rp.text
    rid = rp.json()["id"]
    body = {"employee_ids": [ids["e1"]], "start": W.isoformat(),
            "end": W.isoformat(), "anchor": W.isoformat(), "status": "published"}
    _locked_403(await client.post(f"{R}/rotations/{rid}/apply", headers=hx,
                                  json={**body, "reason": "urgent"}), W)
    r = await client.post(f"{R}/rotations/{rid}/apply", headers=ha,
                          json={**body, "reason": "urgent"})
    assert r.status_code == 200, r.text
    await _assert_emergency(ids["e1"], W, n=2)
    # outside the window: no reason needed, no flag
    r = await client.post(f"{R}/rotations/{rid}/apply", headers=hx, json={
        **body, "start": O.isoformat(), "end": O.isoformat(),
        "anchor": O.isoformat()})
    assert r.status_code == 200, r.text


async def test_copy_never_touches_published(client, world):
    """Copy writes DRAFT only and never overwrites a published target cell,
    so it can never change the live schedule (no lock needed)."""
    ids = world["ids"]
    src = TODAY - timedelta(days=10)
    await _pub(ids["e1"], src, ids["t2"])
    await _pub(ids["e1"], TODAY + timedelta(days=1), ids["t1"])
    hx = await _h(client, world, "sx")
    r = await client.post(f"{R}/copy", headers=hx, json={
        "source_start": src.isoformat(), "source_end": src.isoformat(),
        "target_start": (TODAY + timedelta(days=1)).isoformat(),
        "employee_ids": [ids["e1"]], "overwrite": True})
    assert r.status_code == 200, r.text
    assert (await _cell(ids["e1"], TODAY + timedelta(days=1)))[0] == ids["t1"]


async def test_change_request_decide(client, world):
    ids = world["ids"]
    await _pub(ids["e1"], W, ids["t1"])
    he = await _h(client, world, "e1")
    r = await client.post(f"{R}/change-requests", headers=he, json={
        "work_date": W.isoformat(), "requested_shift_template_id": ids["t2"],
        "reason": "doctor appointment"})
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    hx = await _h(client, world, "sx")
    _locked_403(await client.post(f"{R}/change-requests/{cid}/decide",
                                  headers=hx, json={"action": "approve"}), W)
    ha = await _h(client, world, "admin")
    r = await client.post(f"{R}/change-requests/{cid}/decide", headers=ha,
                          json={"action": "approve"})
    assert r.status_code == 200, r.text
    h = await _assert_emergency(ids["e1"], W)
    assert h.reason == "doctor appointment"


async def test_publish_drafts(client, world):
    ids = world["ids"]
    await _pub(ids["e1"], W, ids["t2"], status=RosterStatus.DRAFT)
    await _pub(ids["e1"], O, ids["t2"], status=RosterStatus.DRAFT)
    body = {"employee_ids": [ids["e1"]], "start": W.isoformat(),
            "end": O.isoformat()}
    hx = await _h(client, world, "sx")
    _locked_403(await client.post(f"{R}/publish", headers=hx, json=body), W)
    assert (await _cell(ids["e1"], O))[2] == RosterStatus.DRAFT
    ha = await _h(client, world, "admin")
    assert (await client.post(f"{R}/publish", headers=ha, json=body)).status_code == 422
    r = await client.post(f"{R}/publish", headers=ha,
                          json={**body, "reason": "late roster fix"})
    assert r.status_code == 200 and r.json()["published"] == 2, r.text
    await _assert_emergency(ids["e1"], W)
    # the outside-window publish is a normal (non-emergency) history row
    assert [h.is_emergency for h in await _hist(ids["e1"], O)] == [False]


async def test_publish_drafts_service_for_request_approval(world):
    """publish-requests approval runs publish_drafts as an admin."""
    ids = world["ids"]
    await _pub(ids["e2"], W2, ids["t1"], status=RosterStatus.DRAFT)
    async with SessionLocal() as db:
        admin = await db.get(User, ids["admin"])
        res = await roster_svc.publish_drafts(
            db, admin, [ids["e2"]], W2, W2, reason="approved publish request #1")
        await commit_or_409(db)
    assert res["published"] == 1
    await _assert_emergency(ids["e2"], W2)


# ------------------------------ employee-initiated flows ------------------------------

async def test_swap_follows_approver_rights(client, world):
    ids = world["ids"]
    await _pub(ids["e1"], W, ids["t1"])
    await _pub(ids["e2"], W, ids["t2"])
    h1, h2 = await _h(client, world, "e1"), await _h(client, world, "e2")
    r = await client.post(f"{R}/swaps", headers=h1, json={
        "counterparty_id": ids["e2"], "requester_date": W.isoformat(),
        "reason": "family event"})
    assert r.status_code == 200, r.text
    sid = r.json()["id"]
    assert (await client.post(f"{R}/swaps/{sid}/accept", headers=h2)).status_code == 200
    hn = await _h(client, world, "dnv")
    _locked_403(await client.post(f"{R}/swaps/{sid}/decide", headers=hn,
                                  json={"action": "approve"}))
    assert (await _cell(ids["e1"], W))[0] == ids["t1"]
    ho = await _h(client, world, "dov")
    r = await client.post(f"{R}/swaps/{sid}/decide", headers=ho,
                          json={"action": "approve"})
    assert r.status_code == 200, r.text
    assert (await _cell(ids["e1"], W))[0] == ids["t2"]
    await _assert_emergency(ids["e1"], W)
    await _assert_emergency(ids["e2"], W)


async def test_drop_decide(client, world):
    ids = world["ids"]
    await _pub(ids["e1"], W, ids["t1"])
    he = await _h(client, world, "e1")
    r = await client.post(f"{R}/drops", headers=he, json={
        "work_date": W.isoformat(), "reason": "sick child"})
    assert r.status_code == 200, r.text
    did = r.json()["id"]
    hn = await _h(client, world, "dnv")
    _locked_403(await client.post(f"{R}/drops/{did}/decide", headers=hn,
                                  json={"action": "approve", "post_open_shift": False}))
    assert (await _cell(ids["e1"], W))[0] == ids["t1"]
    ho = await _h(client, world, "dov")
    r = await client.post(f"{R}/drops/{did}/decide", headers=ho,
                          json={"action": "approve", "post_open_shift": False})
    assert r.status_code == 200, r.text
    assert (await _cell(ids["e1"], W))[1] is True
    await _assert_emergency(ids["e1"], W)


async def _post_open_shift(client, h, w, auto=False, day=W):
    r = await client.post(f"{R}/open-shifts", headers=h, json={
        "work_date": day.isoformat(), "shift_template_id": w["ids"]["t1"],
        "department": w["dept"], "slots": 1, "auto_confirm": auto})
    assert r.status_code == 200, r.text
    return r.json()["id"]


async def test_open_shift_claim_decide(client, world):
    ids = world["ids"]
    ha = await _h(client, world, "admin")
    sid = await _post_open_shift(client, ha, world)
    h3 = await _h(client, world, "e3")
    r = await client.post(f"{R}/open-shifts/{sid}/claim", headers=h3)
    assert r.status_code == 200, r.text
    async with SessionLocal() as db:
        cid = (await db.execute(select(OpenShiftClaim.id).where(
            OpenShiftClaim.user_id == ids["e3"]))).scalar_one()
    hx = await _h(client, world, "sx")
    _locked_403(await client.post(f"{R}/open-shifts/claims/{cid}/decide",
                                  headers=hx, json={"action": "approve"}))
    r = await client.post(f"{R}/open-shifts/claims/{cid}/decide", headers=ha,
                          json={"action": "approve"})
    assert r.status_code == 200, r.text
    await _assert_emergency(ids["e3"], W)


async def test_open_shift_auto_confirm_uses_creator_rights(client, world):
    ids = world["ids"]
    h3 = await _h(client, world, "e3")
    # created by a head without override: employee's claim is refused
    hx = await _h(client, world, "sx")
    r = await client.post(f"{R}/open-shifts", headers=hx, json={
        "work_date": W.isoformat(), "shift_template_id": ids["t1"],
        "department": world["dept"], "slots": 1, "auto_confirm": True})
    if r.status_code == 200:   # heads may be allowed to post
        sid = r.json()["id"]
        _locked_403(await client.post(f"{R}/open-shifts/{sid}/claim", headers=h3))
        assert await _acks(ids["e3"]) == []
    # created by an admin: confirmed instantly as an emergency change
    ha = await _h(client, world, "admin")
    sid = await _post_open_shift(client, ha, world, auto=True, day=W2)
    r = await client.post(f"{R}/open-shifts/{sid}/claim", headers=h3)
    assert r.status_code == 200, r.text
    await _assert_emergency(ids["e3"], W2)


async def test_gap_assign(client, world):
    ids = world["ids"]
    await _pub(ids["e1"], W, ids["t1"], off=False)
    async with SessionLocal() as db:
        g = await gap_svc.open_gap(
            db, work_date=W, shift_template_id=ids["t1"],
            absent_user_id=ids["e1"], source="no_show", source_id=None)
        await db.commit()
        gid = g.id
    hn = await _h(client, world, "dnv")
    _locked_403(await client.post(f"{R}/gaps/{gid}/assign", headers=hn,
                                  json={"user_id": ids["e2"]}))
    ho = await _h(client, world, "dov")
    r = await client.post(f"{R}/gaps/{gid}/assign", headers=ho,
                          json={"user_id": ids["e2"]})
    assert r.status_code == 200, r.text
    await _assert_emergency(ids["e2"], W)


# ------------------------------ acknowledgement ------------------------------

async def test_ack_endpoints(client, world):
    ids = world["ids"]
    await _pub(ids["e1"], W, ids["t1"])
    eid = await _entry_id(ids["e1"], W)
    ha = await _h(client, world, "admin")
    assert (await client.patch(f"{R}/entries/{eid}", headers=ha, json={
        "shift_template_id": ids["t2"], "reason": "urgent cover"})).status_code == 200
    he, h2 = await _h(client, world, "e1"), await _h(client, world, "e2")
    r = await client.get(f"{R}/my/acks", headers=he)
    assert r.status_code == 200 and len(r.json()) == 1, r.text
    ack = r.json()[0]
    assert ack["reason"] == "urgent cover" and ack["work_date"] == W.isoformat()
    assert (await client.get(f"{R}/my/acks", headers=h2)).json() == []
    # someone else cannot acknowledge it
    assert (await client.post(f"{R}/my/acks/{ack['id']}", headers=h2)).status_code == 403
    assert (await client.post(f"{R}/my/acks/99999999", headers=he)).status_code == 404
    # scheduler sees it as pending (scope: dept head) ; outsider has no scope
    hx = await _h(client, world, "sx")
    sc = (await client.get(f"{R}/acks", headers=hx)).json()
    assert [a["id"] for a in sc] == [ack["id"]] and sc[0]["employee_name"] == "LW e1"
    r = await client.post(f"{R}/my/acks/{ack['id']}", headers=he)
    assert r.status_code == 200 and r.json()["acknowledged_at"]
    assert (await client.post(f"{R}/my/acks/{ack['id']}", headers=he)).status_code == 200
    assert (await client.get(f"{R}/my/acks", headers=he)).json() == []
    assert (await client.get(f"{R}/acks", headers=hx)).json() == []
    done = (await client.get(f"{R}/acks", headers=hx,
                             params={"status": "acknowledged"})).json()
    assert [a["id"] for a in done] == [ack["id"]]
    # history exposes the flag
    r = await client.get(f"{R}/my/history", headers=he)
    assert any(x["is_emergency"] for x in r.json())


async def test_grid_exposes_lock_info(client, world):
    ha = await _h(client, world, "admin")
    r = await client.get(f"{R}/plan", headers=ha, params={
        "start": W.isoformat(), "end": W.isoformat(), "department": world["dept"]})
    j = r.json()
    assert j["lock_days"] == LOCK and j["can_override_lock"] is True
    hx = await _h(client, world, "sx")
    r = await client.get(f"{R}/plan", headers=hx, params={
        "start": W.isoformat(), "end": W.isoformat()})
    assert r.json()["lock_days"] == LOCK and r.json()["can_override_lock"] is False


# ------------------------------ call-back compensation ------------------------------

async def _change(client, world, uid_tag, day, tpl):
    ids = world["ids"]
    ha = await _h(client, world, "admin")
    eid = await _entry_id(ids[uid_tag], day)
    body = {"reason": "called in"}
    if tpl is None:
        body["is_week_off"] = True
    else:
        body["shift_template_id"] = tpl
    r = await client.patch(f"{R}/entries/{eid}", headers=ha, json=body)
    assert r.status_code == 200, r.text


async def _accruals(uid):
    async with SessionLocal() as db:
        return list((await db.execute(select(CompOffAccrual).where(
            CompOffAccrual.user_id == uid))).scalars().all())


async def _allow(uid):
    async with SessionLocal() as db:
        return list((await db.execute(select(ShiftAllowanceEntry).where(
            ShiftAllowanceEntry.user_id == uid))).scalars().all())


async def test_callback_comp_off_once(client, world):
    ids = world["ids"]
    await rules(callback_compensation="comp_off")
    await _pub(ids["e1"], W, off=True)
    await _change(client, world, "e1", W, ids["t1"])
    acc = await _accruals(ids["e1"])
    assert len(acc) == 1 and acc[0].holiday_name == "Call-back"
    assert acc[0].holiday_date == W and acc[0].status == "pending"
    async with SessionLocal() as db:
        item = (await db.execute(select(ApprovalItem).where(
            ApprovalItem.resource_type == "comp_off_accrual",
            ApprovalItem.resource_id == str(acc[0].id)))).scalar_one()
        steps = (await db.execute(select(ApprovalStep).where(
            ApprovalStep.approval_item_id == item.id))).scalars().all()
        assert steps
    # back to off and called in again: still one accrual, no claw-back either
    await _change(client, world, "e1", W, None)
    assert len(await _accruals(ids["e1"])) == 1
    await _change(client, world, "e1", W, ids["t2"])
    assert len(await _accruals(ids["e1"])) == 1
    # working -> another working shift is not a call-back
    await _pub(ids["e2"], W, ids["t1"])
    await _change(client, world, "e2", W, ids["t2"])
    assert await _accruals(ids["e2"]) == []


async def test_callback_allowance_once_and_stamped_untouched(client, world):
    ids = world["ids"]
    await rules(callback_compensation="allowance", callback_allowance_amount=250)
    await _pub(ids["e1"], W, off=True)
    await _change(client, world, "e1", W, ids["t1"])
    rows = await _allow(ids["e1"])
    assert len(rows) == 1 and rows[0].kind == ShiftAllowanceKind.CALLBACK
    assert rows[0].amount == 250.0 and rows[0].payroll_run_id is None
    await _change(client, world, "e1", W, None)
    await _change(client, world, "e1", W, ids["t2"])
    assert len(await _allow(ids["e1"])) == 1
    # a stamped (paid) entry is never modified or duplicated
    await _pub(ids["e3"], W2, off=True)
    async with SessionLocal() as db:
        run = PayrollRun(month=3, year=2017, status=PayrollRunStatus.DRAFT)
        db.add(run)
        await db.flush()
        world["runs"].append(run.id)
        db.add(ShiftAllowanceEntry(
            user_id=ids["e3"], work_date=W2, kind=ShiftAllowanceKind.CALLBACK,
            amount=111.0, minutes=0, payroll_run_id=run.id))
        await db.commit()
    await _change(client, world, "e3", W2, ids["t1"])
    rows = await _allow(ids["e3"])
    assert len(rows) == 1 and rows[0].amount == 111.0 and rows[0].payroll_run_id


async def test_callback_none_creates_nothing(client, world):
    ids = world["ids"]
    await _pub(ids["e1"], W, off=True)
    await _change(client, world, "e1", W, ids["t1"])
    assert await _accruals(ids["e1"]) == [] and await _allow(ids["e1"]) == []
    await _assert_emergency(ids["e1"], W)


async def test_callback_not_for_non_emergency_change(client, world):
    ids = world["ids"]
    await rules(callback_compensation="allowance", callback_allowance_amount=99)
    await _pub(ids["e1"], O, off=True)
    ha = await _h(client, world, "admin")
    eid = await _entry_id(ids["e1"], O)
    r = await client.patch(f"{R}/entries/{eid}", headers=ha, json={
        "shift_template_id": ids["t1"], "reason": "planned"})
    assert r.status_code == 200
    assert await _allow(ids["e1"]) == []


# ------------------------------ delegation flag / time rules ------------------------------

async def test_delegation_flag_crud(client, world):
    ids = world["ids"]
    ha = await _h(client, world, "admin")
    D = f"{R}/delegations"
    r = await client.post(D, headers=ha, json={
        "grantee_id": ids["e3"], "scope_type": "employees",
        "employee_ids": [ids["e1"]], "valid_from": TODAY.isoformat(),
        "can_emergency_override": True})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["can_emergency_override"] is True
    r = await client.patch(f"{D}/{j['id']}", headers=ha,
                           json={"can_emergency_override": False})
    assert r.status_code == 200 and r.json()["can_emergency_override"] is False
    assert (await client.patch(f"{D}/{j['id']}", headers=ha,
                               json={"can_emergency_override": None})).status_code == 422
    r = await client.post(D, headers=ha, json={
        "grantee_id": ids["e2"], "scope_type": "employees",
        "employee_ids": [ids["e1"]], "valid_from": TODAY.isoformat()})
    assert r.json()["can_emergency_override"] is False


async def test_time_rule_validation(world):
    async with SessionLocal() as db:
        for bad in ({"schedule.lock_days": "31"}, {"schedule.lock_days": "-1"},
                    {"schedule.lock_days": "abc"},
                    {"schedule.callback_compensation": "cash"},
                    {"schedule.callback_allowance_amount": "-5"},
                    {"schedule.callback_allowance_amount": "nan"},
                    {"schedule.callback_allowance_amount": "x"}):
            with pytest.raises(ValueError):
                await time_rules.set_time_rules(db, bad)
        out = await time_rules.set_time_rules(db, {
            "schedule.lock_days": "30", "schedule.callback_compensation": "comp_off",
            "schedule.callback_allowance_amount": "12.5"})
        assert out["schedule.lock_days"] == "30"
        got = await time_rules.get_lock_rules(db)
        assert got == {"lock_days": 30, "callback_compensation": "comp_off",
                       "callback_allowance_amount": 12.5}


async def test_lock_guard_pure_rules(world):
    ids = world["ids"]
    async with SessionLocal() as db:
        sx = await db.get(User, ids["sx"])
        admin = await db.get(User, ids["admin"])
        c = [(ids["e1"], W, (ids["t1"], False), (ids["t2"], False))]
        # no-op / outside window cells never lock
        assert await roster_svc.lock_guard(db, sx, [
            (ids["e1"], W, (ids["t1"], False), (ids["t1"], False)),
            (ids["e1"], O, (ids["t1"], False), (ids["t2"], False))],
            reason=None) == set()
        with pytest.raises(Exception) as ei:
            await roster_svc.lock_guard(db, sx, c, reason="long enough")
        assert getattr(ei.value, "status_code", None) == 403
        with pytest.raises(Exception) as ei:
            await roster_svc.lock_guard(db, admin, c, reason="ab")
        assert getattr(ei.value, "status_code", None) == 422
        assert await roster_svc.lock_guard(db, admin, c, reason="abc") == {(ids["e1"], W)}
