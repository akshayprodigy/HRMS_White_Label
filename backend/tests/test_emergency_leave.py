"""Emergency leave (Roadmap v2 Phase 2, Task 1)."""
import uuid
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, insert, select

from _cleanup import purge_gap_notifications, purge_shift_templates
from app.api import deps
from app.core.config import settings
from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.main import create_app
from app.models.approval import ApprovalItem, ApprovalStep
from app.models.audit import AuditLog
from app.models.coverage_gap import CoverageGap
from app.models.department import Department
from app.models.employee import Employee, EmployeeStatus
from app.models.leave import (
    LeaveBalanceLedger, LeaveRequest, LeaveStatus, LeaveType,
)
from app.models.notification import Notification
from app.models.notification_channel import NotificationDelivery
from app.models.roster import RosterEntry, RosterEntryHistory, RosterStatus
from app.models.shift import ShiftTemplate
from app.models.system import SystemSetting
from app.models.user import Permission, Role, User, role_permissions, user_roles
from app.services import absence_lop
from app.services import emergency_leave as el
from app.services import time_rules as tr

API = settings.API_V1_STR
PW = "test@12345"
PERMS = ("leave approve", "employee leave write", "employee leave read")
RULE_KEYS = ("leave.emergency_backdate_days", "leave.emergency_proof_days")
TODAY = datetime.now(timezone.utc).date()


def dn(n):
    return TODAY + timedelta(days=n)


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
    dept = f"EL{sfx}"
    made_perms, files = [], []
    async with SessionLocal() as db:
        saved = {r.key: r.value for r in (await db.execute(
            select(SystemSetting).where(SystemSetting.key.in_(RULE_KEYS)))
        ).scalars().all()}
    try:
        async with SessionLocal() as db:
            role = Role(name=f"ELR{sfx}", description="t")
            hrrole = Role(name=f"ELH{sfx}", description="t")
            db.add_all([role, hrrole])
            await db.flush()
            for pn, rl in [(p, role) for p in PERMS] + [
                    ("hr employee write", hrrole), ("leave approve", hrrole),
                    ("employee leave write", hrrole),
                    ("employee leave read", hrrole)]:
                p = (await db.execute(select(Permission).where(
                    Permission.name == pn))).scalar_one_or_none()
                if p is None:
                    p = Permission(name=pn, description="t")
                    db.add(p)
                    await db.flush()
                    made_perms.append(p.id)
                await db.execute(insert(role_permissions).values(
                    role_id=rl.id, permission_id=p.id))

            def mk(tag, **kw):
                return User(email=f"el_{tag}_{sfx}@t.com", full_name=f"EL {tag}",
                            hashed_password=get_password_hash(PW),
                            is_active=True, **kw)
            mgr, hr, head = mk("mgr"), mk("hr"), mk("head")
            db.add_all([mgr, hr, head])
            await db.flush()
            emp, other = mk("emp", manager_id=mgr.id), mk("other")
            db.add_all([emp, other])
            await db.flush()
            for u in (mgr, emp, other):
                await db.execute(insert(user_roles).values(
                    user_id=u.id, role_id=role.id))
            await db.execute(insert(user_roles).values(
                user_id=hr.id, role_id=hrrole.id))
            db.add(Department(name=dept))
            tpl = ShiftTemplate(name=f"ELT{sfx}", start_time=time(9),
                                end_time=time(17))
            paid = LeaveType(name=f"ELP{sfx}", unpaid_allowed=False)
            cert = LeaveType(name=f"ELC{sfx}", unpaid_allowed=False,
                             requires_medical_cert_after=1)
            unpaid = LeaveType(name=f"ELU{sfx}", unpaid_allowed=True)
            db.add_all([tpl, paid, cert, unpaid])
            await db.flush()
            for u in (emp, other):
                db.add(Employee(
                    user_id=u.id, employee_id=f"EL{sfx}{u.id}",
                    department=dept, designation="T",
                    date_of_joining=date(2020, 1, 1),
                    status=EmployeeStatus.ACTIVE))
            for lt in (paid, cert):
                for u in (emp, other):
                    db.add(LeaveBalanceLedger(
                        user_id=u.id, leave_type_id=lt.id, balance=10.0, used=0.0))
            await db.execute(Department.__table__.update().where(
                Department.name == dept).values(head_user_id=head.id))
            await db.commit()
            ids = dict(mgr=mgr.id, hr=hr.id, head=head.id, emp=emp.id,
                       other=other.id, tpl=tpl.id, paid=paid.id,
                       cert=cert.id, unpaid=unpaid.id)
        yield {"ids": ids, "sfx": sfx, "files": files,
               "email": lambda t: f"el_{t}_{sfx}@t.com"}
    finally:
        async with SessionLocal() as db:
            uids = list((await db.execute(select(User.id).where(
                User.email.like(f"el\\_%\\_{sfx}@t.com")))).scalars().all())
            tids = list((await db.execute(select(ShiftTemplate.id).where(
                ShiftTemplate.name == f"ELT{sfx}"))).scalars().all())
            lids = list((await db.execute(select(LeaveRequest.id).where(
                LeaveRequest.employee_id.in_(uids)))).scalars().all())
            rids = [str(i) for i in lids]
            if rids:  # job notified (patched) HR; stay safe for real users
                nids = list((await db.execute(select(Notification.id).where(
                    Notification.resource_type == "leave_request",
                    Notification.resource_id.in_(rids)))).scalars().all())
                if nids:
                    await db.execute(delete(NotificationDelivery).where(
                        NotificationDelivery.notification_id.in_(nids)))
                    await db.execute(delete(Notification).where(
                        Notification.id.in_(nids)))
            nids = list((await db.execute(select(Notification.id).where(
                Notification.user_id.in_(uids)))).scalars().all())
            if nids:
                await db.execute(delete(NotificationDelivery).where(
                    NotificationDelivery.notification_id.in_(nids)))
            await db.execute(delete(Notification).where(
                Notification.user_id.in_(uids)))
            await purge_gap_notifications(db, tids)
            await db.execute(delete(CoverageGap).where(
                CoverageGap.shift_template_id.in_(tids)))
            if rids:
                items = list((await db.execute(select(ApprovalItem.id).where(
                    ApprovalItem.resource_id.in_(rids),
                    ApprovalItem.resource_type == "leave_request"
                ))).scalars().all())
                if items:
                    await db.execute(delete(ApprovalStep).where(
                        ApprovalStep.approval_item_id.in_(items)))
                    await db.execute(delete(ApprovalItem).where(
                        ApprovalItem.id.in_(items)))
            await db.execute(delete(AuditLog).where(AuditLog.user_id.in_(uids)))
            await db.execute(delete(LeaveRequest).where(
                LeaveRequest.employee_id.in_(uids)))
            await db.execute(delete(LeaveBalanceLedger).where(
                LeaveBalanceLedger.user_id.in_(uids)))
            await db.execute(delete(RosterEntryHistory).where(
                RosterEntryHistory.employee_id.in_(uids)))
            await db.execute(delete(RosterEntry).where(
                RosterEntry.employee_id.in_(uids)))
            await db.execute(delete(Employee).where(Employee.user_id.in_(uids)))
            await db.execute(Department.__table__.update().where(
                Department.name == dept).values(head_user_id=None))
            await db.execute(delete(Department).where(Department.name == dept))
            await purge_shift_templates(db, tids)
            await db.execute(delete(user_roles).where(
                user_roles.c.user_id.in_(uids)))
            await db.execute(delete(User).where(User.id.in_(uids)))
            await db.execute(delete(LeaveType).where(
                LeaveType.name.like(f"EL_{sfx}")))
            rl = list((await db.execute(select(Role.id).where(
                Role.name.in_([f"ELR{sfx}", f"ELH{sfx}"])))).scalars().all())
            await db.execute(delete(role_permissions).where(
                role_permissions.c.role_id.in_(rl)))
            await db.execute(delete(Role).where(Role.id.in_(rl)))
            if made_perms:
                await db.execute(delete(Permission).where(
                    Permission.id.in_(made_perms)))
            for k in RULE_KEYS:
                row = await db.get(SystemSetting, k)
                if k in saved:
                    if row:
                        row.value = saved[k]
                elif row:
                    await db.delete(row)
            await db.commit()
        for f in files:
            Path(settings.LEAVE_ATTACHMENTS_DIR, f).unlink(missing_ok=True)


async def _login(client, w, tag):
    r = await client.post(f"{API}/auth/login",
                          data={"username": w["email"](tag), "password": PW})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _rules(**kw):
    async with SessionLocal() as db:
        await tr.set_time_rules(db, {f"leave.emergency_{k}": str(v)
                                     for k, v in kw.items()})


async def _roster(w, day, *, off=False, status=RosterStatus.PUBLISHED, uid=None):
    async with SessionLocal() as db:
        db.add(RosterEntry(
            employee_id=uid or w["ids"]["emp"], work_date=day,
            shift_template_id=None if off else w["ids"]["tpl"],
            is_week_off=off, status=status))
        await db.commit()


def _body(w, start, end=None, **kw):
    d = {"leave_type_id": w["ids"]["paid"], "start_date": start.isoformat(),
         "end_date": (end or start).isoformat(), "reason": "family emergency",
         "is_emergency": True}
    d.update(kw)
    return d


async def _apply(client, w, who="emp", **kw):
    h = await _login(client, w, who)
    return await client.post(f"{API}/leave/apply", json=_body(w, **kw), headers=h)


async def _leave(lid):
    async with SessionLocal() as db:
        return (await db.execute(select(LeaveRequest).where(
            LeaveRequest.id == lid).execution_options(
                populate_existing=True))).scalar_one()


async def _used(w, uid=None, lt="paid"):
    async with SessionLocal() as db:
        return (await db.execute(select(LeaveBalanceLedger.used).where(
            LeaveBalanceLedger.user_id == (uid or w["ids"]["emp"]),
            LeaveBalanceLedger.leave_type_id == w["ids"][lt]))).scalar_one()


async def _gaps(w):
    async with SessionLocal() as db:
        return list((await db.execute(select(CoverageGap).where(
            CoverageGap.shift_template_id == w["ids"]["tpl"]
        ).order_by(CoverageGap.work_date))).scalars().all())


async def _approve_db(lid, days_used=None, lt="paid", w=None):
    """Approve like the approval path would: status + ledger debit."""
    async with SessionLocal() as db:
        lv = (await db.execute(select(LeaveRequest).where(
            LeaveRequest.id == lid))).scalar_one()
        lv.status = LeaveStatus.APPROVED
        if days_used:
            led = (await db.execute(select(LeaveBalanceLedger).where(
                LeaveBalanceLedger.user_id == lv.employee_id,
                LeaveBalanceLedger.leave_type_id == lv.leave_type_id))
            ).scalar_one()
            led.used += days_used
        await db.commit()


@pytest.fixture(autouse=True)
def _hr_notify(monkeypatch, request):
    """Job HR fan-out goes to the fixture's HR user, never real HR."""
    if "world" not in request.fixturenames:
        return
    w = request.getfixturevalue("world")

    async def fake(db):
        return [w["ids"]["hr"]]
    monkeypatch.setattr(el, "hr_user_ids", fake)


# ------------------------------- apply rules -------------------------------

async def test_non_emergency_unchanged(client, world):
    w = world
    h = await _login(client, w, "emp")
    # cert threshold still enforced for ordinary leave
    r = await client.post(f"{API}/leave/apply", headers=h, json=_body(
        w, dn(5), leave_type_id=w["ids"]["cert"], is_emergency=False))
    assert r.status_code == 400 and "medical certificate" in r.text
    r = await client.post(f"{API}/leave/apply", headers=h, json=_body(
        w, dn(5), is_emergency=False))
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["is_emergency"] is False and j["proof_due_date"] is None
    assert await _gaps(w) == []


async def test_backdate_window(client, world):
    w = world
    await _rules(backdate_days=3, proof_days=3)
    ok = await _apply(client, w, start=dn(-3))
    assert ok.status_code == 200, ok.text
    bad = await _apply(client, w, start=dn(-10), end=dn(-4))
    assert bad.status_code == 400 and "back-dated" in bad.text
    await _rules(backdate_days=0)
    same = await _apply(client, w, start=dn(10))
    assert same.status_code == 200
    r = await _apply(client, w, who="other", start=dn(-1))
    assert r.status_code == 400


async def test_proof_deferral(client, world):
    w = world
    await _rules(backdate_days=3, proof_days=3)
    # cert-required type: ordinary leave needs the file now; emergency defers
    r = await _apply(client, w, start=dn(0), end=dn(1),
                     leave_type_id=w["ids"]["cert"])
    assert r.status_code == 200, r.text
    assert r.json()["proof_due_date"] == dn(1 + 3).isoformat()
    # attachment supplied at apply -> no proof pending
    f = Path(settings.LEAVE_ATTACHMENTS_DIR) / f"{uuid.uuid4().hex}.pdf"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(b"%PDF-1.4")
    w["files"].append(f.name)
    r2 = await _apply(client, w, who="other", start=dn(0),
                      attachment_url=f.name)
    assert r2.status_code == 200
    lv = await _leave(r2.json()["id"])
    assert lv.proof_due_date is None and lv.proof_submitted_at is not None


async def test_rule_zero_means_no_proof_required(client, world):
    w = world
    await _rules(backdate_days=3, proof_days=0)
    r = await _apply(client, w, start=dn(0), leave_type_id=w["ids"]["cert"])
    assert r.status_code == 200, r.text
    assert r.json()["proof_due_date"] is None
    async with SessionLocal() as db:
        out = await el.proof_check_job(
            db, now=datetime.now(timezone.utc) + timedelta(days=30),
            user_ids=[w["ids"]["emp"]])
    assert out == {"skipped": "disabled"}
    assert (await _leave(r.json()["id"])).converted_to_lop_at is None


async def test_rule_validation(client, world):
    async with SessionLocal() as db:
        with pytest.raises(ValueError):
            await tr.set_time_rules(db, {"leave.emergency_backdate_days": "32"})
        with pytest.raises(ValueError):
            await tr.set_time_rules(db, {"leave.emergency_proof_days": "61"})
        with pytest.raises(ValueError):
            await tr.set_time_rules(db, {"leave.emergency_proof_days": "x"})


# ------------------------------- coverage gaps -------------------------------

async def test_gaps_only_published_working_cells(client, world):
    w = world
    await _rules(backdate_days=3, proof_days=3)
    await _roster(w, dn(-1))                                   # past: skip
    await _roster(w, dn(0))
    await _roster(w, dn(1))
    await _roster(w, dn(2), off=True)                          # week-off: skip
    await _roster(w, dn(3), status=RosterStatus.DRAFT)         # draft: skip
    r = await _apply(client, w, start=dn(-1), end=dn(3))
    assert r.status_code == 200, r.text
    gaps = await _gaps(w)
    assert [g.work_date for g in gaps] == [dn(0), dn(1)]
    for g in gaps:
        assert (g.source, g.status, g.source_id, g.absent_user_id) == (
            "emergency_leave", "open", r.json()["id"], w["ids"]["emp"])
    # ONE alert to the scheduler (dept head) listing both dates
    async with SessionLocal() as db:
        ns = list((await db.execute(select(Notification).where(
            Notification.user_id == w["ids"]["head"],
            Notification.resource_type == "coverage_gap"))).scalars().all())
    assert len(ns) == 1
    assert dn(0).isoformat() in ns[0].message and dn(1).isoformat() in ns[0].message
    assert dn(3).isoformat() not in ns[0].message


async def test_half_day_still_opens_gap_and_no_roster_no_gap(client, world):
    w = world
    await _rules(backdate_days=3, proof_days=3)
    await _roster(w, dn(0))
    r = await _apply(client, w, start=dn(0), is_half_day=True,
                     half_day_session="morning")
    assert r.status_code == 200, r.text
    assert len(await _gaps(w)) == 1
    r2 = await _apply(client, w, who="other", start=dn(0))   # no roster cells
    assert r2.status_code == 200
    assert len(await _gaps(w)) == 1


async def test_reject_and_cancel_dismiss_gaps(client, world):
    w = world
    await _rules(backdate_days=3, proof_days=3)
    await _roster(w, dn(0))
    await _roster(w, dn(0), uid=w["ids"]["other"])
    r = await _apply(client, w, start=dn(0))
    r2 = await _apply(client, w, who="other", start=dn(0))
    assert len(await _gaps(w)) == 2
    # reject via the manager's approval action
    async with SessionLocal() as db:
        item = (await db.execute(select(ApprovalItem).where(
            ApprovalItem.resource_id == str(r.json()["id"]),
            ApprovalItem.resource_type == "leave_request"))).scalar_one()
    hm = await _login(client, w, "mgr")
    a = await client.post(f"{API}/leave/approvals/{item.id}/action", headers=hm,
                          json={"status": "rejected", "comment": "no"})
    assert a.status_code == 200, a.text
    # employee 'other' cancels
    ho = await _login(client, w, "other")
    c = await client.post(f"{API}/leave/{r2.json()['id']}/cancel", headers=ho)
    assert c.status_code == 200, c.text
    gaps = await _gaps(w)
    assert len(gaps) == 2
    assert all(g.status == "dismissed" and g.note == "Leave rejected/cancelled"
               for g in gaps)


async def test_on_behalf_emergency_opens_gaps(client, world):
    w = world
    await _rules(backdate_days=3, proof_days=3)
    await _roster(w, dn(0))
    h = await _login(client, w, "hr")
    r = await client.post(f"{API}/leave/apply-on-behalf", headers=h, json={
        **_body(w, dn(0)), "employee_id": w["ids"]["emp"],
        "auto_approve": True})
    assert r.status_code == 200, r.text
    assert r.json()["proof_due_date"] == dn(3).isoformat()
    assert len(await _gaps(w)) == 1
    bad = await client.post(f"{API}/leave/apply-on-behalf", headers=h, json={
        **_body(w, dn(-9)), "employee_id": w["ids"]["emp"]})
    assert bad.status_code == 400


# ------------------------------- proof upload -------------------------------

async def _upload(client, w, h):
    r = await client.post(f"{API}/leave/attachments", headers=h, files={
        "file": ("p.pdf", b"%PDF-1.4 x", "application/pdf")})
    assert r.status_code == 200, r.text
    w["files"].append(r.json()["attachment_url"])
    return r.json()["attachment_url"]


async def test_proof_upload_permissions(client, world):
    w = world
    await _rules(backdate_days=3, proof_days=3)
    r = await _apply(client, w, start=dn(0))
    lid = r.json()["id"]
    ho = await _login(client, w, "emp")
    hother = await _login(client, w, "other")
    hhr = await _login(client, w, "hr")
    name = await _upload(client, w, ho)
    # someone else: 403
    bad = await client.post(f"{API}/leave/{lid}/proof", headers=hother,
                            json={"attachment_url": name})
    assert bad.status_code == 403
    # unknown file: 400
    nf = await client.post(f"{API}/leave/{lid}/proof", headers=ho,
                           json={"attachment_url": "nope.pdf"})
    assert nf.status_code == 400
    ok = await client.post(f"{API}/leave/{lid}/proof", headers=ho,
                           json={"attachment_url": name})
    assert ok.status_code == 200, ok.text
    lv = await _leave(lid)
    assert lv.attachment_url == name and lv.proof_submitted_at is not None
    # HR may too
    r2 = await _apply(client, w, who="other", start=dn(0))
    n2 = await _upload(client, w, hother)
    ok2 = await client.post(f"{API}/leave/{r2.json()['id']}/proof",
                            headers=hhr, json={"attachment_url": n2})
    assert ok2.status_code == 200, ok2.text
    # non-emergency leave: 400
    r3 = await client.post(f"{API}/leave/apply", headers=ho, json=_body(
        w, dn(20), is_emergency=False))
    no = await client.post(f"{API}/leave/{r3.json()['id']}/proof", headers=ho,
                           json={"attachment_url": name})
    assert no.status_code == 400


# ------------------------------- the job -------------------------------

async def _emergency(client, w, who="emp", start=None, **kw):
    r = await _apply(client, w, who=who, start=start or dn(-2), **kw)
    assert r.status_code == 200, r.text
    return r.json()["id"]


async def _run_job(w, now, uid=None):
    async with SessionLocal() as db:
        return await el.proof_check_job(
            db, now=now, user_ids=[uid or w["ids"]["emp"]])


def _after_due(lv, days=1):
    return datetime.combine(lv.proof_due_date + timedelta(days=days),
                            time(6), tzinfo=timezone.utc)


async def test_job_converts_overdue_paid_refunds_once(client, world):
    w = world
    await _rules(backdate_days=3, proof_days=3)
    lid = await _emergency(client, w)
    await _approve_db(lid, days_used=1.0)
    assert await _used(w) == 1.0
    lv = await _leave(lid)
    # not yet overdue (due day itself): nothing happens
    assert (await _run_job(w, _after_due(lv, 0)))["converted"] == 0
    assert await _used(w) == 1.0
    out = await _run_job(w, _after_due(lv))
    assert out["converted"] == 1
    lv = await _leave(lid)
    assert lv.converted_to_lop_at is not None
    assert await _used(w) == 0.0
    # rerun is idempotent: no second refund
    assert (await _run_job(w, _after_due(lv, 5)))["converted"] == 0
    assert await _used(w) == 0.0
    # notified employee + (patched) HR
    async with SessionLocal() as db:
        ns = list((await db.execute(select(Notification).where(
            Notification.resource_type == "leave_request",
            Notification.resource_id == str(lid),
            Notification.event_type == "leave_converted_lop"))).scalars().all())
    assert sorted(n.user_id for n in ns) == sorted([w["ids"]["emp"], w["ids"]["hr"]])
    # payroll LOP now includes the converted day exactly once
    m0 = lv.start_date.replace(day=1)
    m1 = (m0 + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    async with SessionLocal() as db:
        assert await absence_lop.leave_lop_days(db, w["ids"]["emp"], m0, m1) == 1.0
    # proof after conversion is refused
    h = await _login(client, w, "emp")
    name = await _upload(client, w, h)
    late = await client.post(f"{API}/leave/{lid}/proof", headers=h,
                             json={"attachment_url": name})
    assert late.status_code == 400


async def test_payroll_lop_not_counted_before_conversion_and_unpaid_once(client, world):
    w = world
    await _rules(backdate_days=3, proof_days=3)
    lid = await _emergency(client, w)
    await _approve_db(lid, days_used=1.0)
    lv = await _leave(lid)
    m0 = lv.start_date.replace(day=1)
    m1 = (m0 + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    async with SessionLocal() as db:   # approved paid, not converted: no LOP
        assert await absence_lop.leave_lop_days(db, w["ids"]["emp"], m0, m1) == 0.0
    # unpaid type converted: still ONE row => counted once, no ledger change
    uid = await _emergency(client, w, who="other", leave_type_id=w["ids"]["unpaid"])
    await _approve_db(uid)
    ul = await _leave(uid)
    out = await _run_job(w, _after_due(ul), uid=w["ids"]["other"])
    assert out["converted"] == 1
    assert await _used(w, uid=w["ids"]["other"]) == 0.0
    async with SessionLocal() as db:
        assert await absence_lop.leave_lop_days(
            db, w["ids"]["other"], m0, m1) == 1.0


async def test_job_skips_when_proof_submitted_or_not_approved(client, world):
    w = world
    await _rules(backdate_days=3, proof_days=3)
    a = await _emergency(client, w)                     # proof before due
    await _approve_db(a, days_used=1.0)
    h = await _login(client, w, "emp")
    name = await _upload(client, w, h)
    ok = await client.post(f"{API}/leave/{a}/proof", headers=h,
                           json={"attachment_url": name})
    assert ok.status_code == 200
    b = await _emergency(client, w, who="other")        # still pending
    lv = await _leave(a)
    now = _after_due(lv, 10)
    assert (await _run_job(w, now))["converted"] == 0
    assert (await _run_job(w, now, uid=w["ids"]["other"]))["converted"] == 0
    assert (await _leave(a)).converted_to_lop_at is None
    assert (await _leave(b)).converted_to_lop_at is None
    assert await _used(w) == 1.0


async def test_reminder_day_before_due_once(client, world):
    w = world
    await _rules(backdate_days=3, proof_days=3)
    lid = await _emergency(client, w)
    lv = await _leave(lid)
    eve = datetime.combine(lv.proof_due_date - timedelta(days=1), time(6),
                           tzinfo=timezone.utc)
    assert (await _run_job(w, eve))["reminded"] == 1
    assert (await _run_job(w, eve))["reminded"] == 0
    async with SessionLocal() as db:
        n = list((await db.execute(select(Notification).where(
            Notification.user_id == w["ids"]["emp"],
            Notification.event_type == "leave_proof_reminder"))).scalars().all())
    assert len(n) == 1
