"""Shift swaps (Roadmap v2 Phase 1B, Task 2)."""
import asyncio
import uuid
from datetime import date, time, timedelta, datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from _cleanup import purge_shift_templates
from app.api import deps
from app.core.config import settings
from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.main import create_app
from app.models.audit import AuditLog
from app.models.department import Department
from app.models.employee import Employee, EmployeeStatus
from app.models.leave import LeaveRequest, LeaveStatus, LeaveType
from app.models.notification import Notification
from app.models.roster import RosterEntry, RosterEntryHistory, RosterStatus
from app.models.schedule_delegation import DelegationScope, ScheduleDelegation
from app.models.shift_swap import ShiftSwapRequest
from app.models.system import SystemSetting
from app.models.user import User
from app.models.shift import ShiftTemplate
from app.services.swaps import swapped_cells
from app.services.time_rules import set_time_rules

SW = f"{settings.API_V1_STR}/roster/swaps"
PW = "test@12345"
TODAY = datetime.now(timezone.utc).date()
D = TODAY + timedelta(days=10)


def dd(n):
    return (D + timedelta(days=n)).isoformat()


def dn(n):
    return D + timedelta(days=n)


# ------------------------------ pure ------------------------------

def test_swapped_cells_same_day():
    a = {date(2030, 1, 1): (1, False)}
    b = {date(2030, 1, 1): (2, False)}
    na, nb = swapped_cells(a, b, [date(2030, 1, 1)])
    assert na == {date(2030, 1, 1): (2, False)}
    assert nb == {date(2030, 1, 1): (1, False)}


def test_swapped_cells_two_days_and_week_off():
    d1, d2 = date(2030, 1, 1), date(2030, 1, 4)
    a = {d1: (1, False), d2: (None, True)}
    b = {d1: (None, True), d2: (3, False)}
    na, nb = swapped_cells(a, b, [d1, d2])
    assert na == {d1: (None, True), d2: (3, False)}
    assert nb == {d1: (1, False), d2: (None, True)}


def test_swapped_cells_only_given_dates_and_inputs_untouched():
    d1, d2 = date(2030, 1, 1), date(2030, 1, 2)
    a = {d1: (1, False), d2: (1, False)}
    b = {d1: (2, False), d2: (2, False)}
    na, nb = swapped_cells(a, b, [d1])
    assert set(na) == {d1} and set(nb) == {d1}
    assert a[d1] == (1, False)


# ------------------------------ API ------------------------------

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
    dept_x, dept_y = f"SX{sfx}", f"SY{sfx}"
    ids = {}
    try:
        async with SessionLocal() as db:
            def mk(tag, **kw):
                return User(email=f"sw_{tag}_{sfx}@t.com", full_name=f"SW {tag}",
                            hashed_password=get_password_hash(PW),
                            is_active=True, **kw)
            us = {t: mk(t) for t in (
                "e1", "e2", "e3", "e4", "e5", "deleg", "deleg1")}
            us["admin"] = mk("admin", is_superuser=True)
            db.add_all(us.values())
            db.add_all([Department(name=dept_x), Department(name=dept_y)])
            t1 = ShiftTemplate(name=f"SWT1{sfx}", start_time=time(9), end_time=time(17))
            t2 = ShiftTemplate(name=f"SWT2{sfx}", start_time=time(14), end_time=time(22))
            tn = ShiftTemplate(name=f"SWTN{sfx}", start_time=time(22), end_time=time(6),
                               is_overnight=True)
            db.add_all([t1, t2, tn])
            await db.commit()
            for tag, dept, st in (
                ("e1", dept_x, EmployeeStatus.ACTIVE),
                ("e2", dept_x, EmployeeStatus.ACTIVE),
                ("e3", dept_y, EmployeeStatus.ACTIVE),
                ("e4", dept_x, EmployeeStatus.ACTIVE),
                ("e5", dept_x, EmployeeStatus.INACTIVE),
            ):
                db.add(Employee(
                    user_id=us[tag].id, employee_id=f"SW{sfx}{tag}",
                    department=dept, designation="Tester",
                    date_of_joining=date(2020, 1, 1), status=st))
            # deleg covers e1+e2; deleg1 covers only e1
            db.add(ScheduleDelegation(
                grantee_id=us["deleg"].id, scope_type=DelegationScope.EMPLOYEES,
                employee_ids=[us["e1"].id, us["e2"].id], can_approve_changes=True,
                valid_from=TODAY - timedelta(days=1)))
            db.add(ScheduleDelegation(
                grantee_id=us["deleg1"].id, scope_type=DelegationScope.EMPLOYEES,
                employee_ids=[us["e1"].id], can_approve_changes=True,
                valid_from=TODAY - timedelta(days=1)))
            await db.commit()
            ids = {t: u.id for t, u in us.items()}
            ids.update(t1=t1.id, t2=t2.id, tn=tn.id)
        yield {"ids": ids, "sfx": sfx, "dept": dept_x,
               "email": lambda t: f"sw_{t}_{sfx}@t.com"}
    finally:
        async with SessionLocal() as db:
            uids = list((await db.execute(select(User.id).where(
                User.email.like(f"sw\\_%\\_{sfx}@t.com")))).scalars().all())
            swap_ids = list((await db.execute(select(ShiftSwapRequest.id).where(
                ShiftSwapRequest.requester_id.in_(uids)))).scalars().all())
            await db.execute(delete(AuditLog).where(
                AuditLog.user_id.in_(uids), AuditLog.action.like("roster.%")))
            await db.execute(delete(Notification).where(
                Notification.user_id.in_(uids)))
            if swap_ids:
                await db.execute(delete(Notification).where(
                    Notification.resource_type == "shift_swap",
                    Notification.resource_id.in_([str(i) for i in swap_ids])))
            await db.execute(delete(ShiftSwapRequest).where(
                ShiftSwapRequest.requester_id.in_(uids)))
            await db.execute(delete(LeaveRequest).where(
                LeaveRequest.employee_id.in_(uids)))
            await db.execute(delete(LeaveType).where(
                LeaveType.name == f"SWLV{sfx}"))
            await db.execute(delete(RosterEntryHistory).where(
                RosterEntryHistory.employee_id.in_(uids)))
            await db.execute(delete(RosterEntry).where(
                RosterEntry.employee_id.in_(uids)))
            await db.execute(delete(ScheduleDelegation).where(
                ScheduleDelegation.grantee_id.in_(uids)))
            await db.execute(delete(Employee).where(Employee.user_id.in_(uids)))
            await db.execute(delete(Department).where(
                Department.name.in_([dept_x, dept_y])))
            tids = list((await db.execute(select(ShiftTemplate.id).where(
                ShiftTemplate.name.in_(
                    [f"SWT1{sfx}", f"SWT2{sfx}", f"SWTN{sfx}"])))).scalars().all())
            await purge_shift_templates(db, tids)
            await db.execute(delete(User).where(User.id.in_(uids)))
            await db.commit()


async def _login(client, email):
    r = await client.post(f"{settings.API_V1_STR}/auth/login",
                          data={"username": email, "password": PW})
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
            RosterEntry.employee_id == uid, RosterEntry.work_date == day,
            RosterEntry.status == RosterStatus.PUBLISHED))).scalars().first()
        return None if r is None else (r.shift_template_id, r.is_week_off)


async def _create(client, w, requester="e1", cp="e2", **kw):
    h = await _login(client, w["email"](requester))
    body = {"counterparty_id": w["ids"][cp], "requester_date": dd(0),
            "reason": "family event"}
    body.update(kw)
    return await client.post(SW, headers=h, json=body)


async def _to_approval(client, w):
    r = await _create(client, w)
    assert r.status_code == 200, r.text
    sid = r.json()["id"]
    h2 = await _login(client, w["email"]("e2"))
    r = await client.post(f"{SW}/{sid}/accept", headers=h2)
    assert r.status_code == 200, r.text
    return sid


async def _setup_same_day(w):
    ids = w["ids"]
    await _pub(ids["e1"], dn(0), ids["t1"])
    await _pub(ids["e2"], dn(0), ids["t2"])


async def test_happy_path_same_day(client, world):
    w, ids = world, world["ids"]
    await _setup_same_day(w)
    r = await _create(client, w)
    assert r.status_code == 200, r.text
    j = r.json()
    sid = j["id"]
    assert j["status"] == "pending_peer"
    assert j["counterparty_date"] == dd(0)
    assert j["requester_name"] == "SW e1" and j["counterparty_name"] == "SW e2"
    h1, h2, hd = [await _login(client, w["email"](t)) for t in ("e1", "e2", "deleg")]
    # counterparty notified
    async with SessionLocal() as db:
        n = (await db.execute(select(Notification).where(
            Notification.user_id == ids["e2"],
            Notification.resource_type == "shift_swap"))).scalars().all()
        assert len(n) == 1
    # not decidable before peer accepts
    r = await client.post(f"{SW}/{sid}/decide", headers=hd, json={"action": "approve"})
    assert r.status_code == 409
    r = await client.post(f"{SW}/{sid}/accept", headers=h2)
    assert r.status_code == 200 and r.json()["status"] == "pending_approval"
    async with SessionLocal() as db:
        n = (await db.execute(select(Notification).where(
            Notification.user_id.in_([ids["e1"], ids["deleg"]]),
            Notification.resource_type == "shift_swap"))).scalars().all()
        assert {x.user_id for x in n} == {ids["e1"], ids["deleg"]}
    r = await client.get(SW, headers=hd)
    assert [x["id"] for x in r.json()] == [sid]
    r = await client.post(f"{SW}/{sid}/decide", headers=hd,
                          json={"action": "approve", "note": "ok"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved" and r.json()["decision_note"] == "ok"
    assert r.json()["decided_by_id"] == ids["deleg"]
    assert await _cell(ids["e1"], dn(0)) == (ids["t2"], False)
    assert await _cell(ids["e2"], dn(0)) == (ids["t1"], False)
    async with SessionLocal() as db:
        hist = (await db.execute(select(RosterEntryHistory).where(
            RosterEntryHistory.employee_id.in_([ids["e1"], ids["e2"]])))
        ).scalars().all()
        assert len(hist) == 2
        assert all(h.reason == f"Shift swap #{sid}" for h in hist)
        n = (await db.execute(select(Notification).where(
            Notification.user_id.in_([ids["e1"], ids["e2"]]),
            Notification.title == "Schedule changed"))).scalars().all()
        assert {x.user_id for x in n} == {ids["e1"], ids["e2"]}
    # queue now empty, decided again -> 409
    assert (await client.get(SW, headers=hd)).json() == []
    r = await client.post(f"{SW}/{sid}/decide", headers=hd, json={"action": "approve"})
    assert r.status_code == 409
    r = await client.get(f"{SW}/my", headers=h1)
    assert [x["id"] for x in r.json()] == [sid]
    assert r.json()[0]["requester_cell"]["shift_template_id"] == ids["t1"]
    assert r.json()[0]["counterparty_cell"]["shift_template_id"] == ids["t2"]


async def test_different_day_classic(client, world):
    w, ids = world, world["ids"]
    # e1 works t1 on D, off on D+3; e2 off on D, works t2 on D+3
    await _pub(ids["e1"], dn(0), ids["t1"])
    await _pub(ids["e1"], dn(3), off=True)
    await _pub(ids["e2"], dn(0), off=True)
    await _pub(ids["e2"], dn(3), ids["t2"])
    r = await _create(client, w, counterparty_date=dd(3))
    assert r.status_code == 200, r.text
    sid = r.json()["id"]
    h2 = await _login(client, w["email"]("e2"))
    hd = await _login(client, w["email"]("deleg"))
    assert (await client.post(f"{SW}/{sid}/accept", headers=h2)).status_code == 200
    r = await client.post(f"{SW}/{sid}/decide", headers=hd, json={"action": "approve"})
    assert r.status_code == 200, r.text
    assert await _cell(ids["e1"], dn(0)) == (None, True)
    assert await _cell(ids["e2"], dn(0)) == (ids["t1"], False)
    assert await _cell(ids["e1"], dn(3)) == (ids["t2"], False)
    assert await _cell(ids["e2"], dn(3)) == (None, True)


async def test_decline_and_cancel(client, world):
    w, ids = world, world["ids"]
    await _setup_same_day(w)
    h1, h2 = [await _login(client, w["email"](t)) for t in ("e1", "e2")]
    sid = (await _create(client, w)).json()["id"]
    # only counterparty can decline
    assert (await client.post(f"{SW}/{sid}/decline", headers=h1)).status_code == 403
    r = await client.post(f"{SW}/{sid}/decline", headers=h2)
    assert r.status_code == 200 and r.json()["status"] == "declined"
    assert (await client.post(f"{SW}/{sid}/decline", headers=h2)).status_code == 409
    # new one: cancel by requester
    sid2 = (await _create(client, w)).json()["id"]
    assert (await client.post(f"{SW}/{sid2}/cancel", headers=h2)).status_code == 403
    r = await client.post(f"{SW}/{sid2}/cancel", headers=h1)
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert (await client.post(f"{SW}/{sid2}/cancel", headers=h1)).status_code == 409
    # cancel after accept
    sid3 = (await _create(client, w)).json()["id"]
    await client.post(f"{SW}/{sid3}/accept", headers=h2)
    r = await client.post(f"{SW}/{sid3}/cancel", headers=h1)
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert await _cell(ids["e1"], dn(0)) == (ids["t1"], False)  # untouched


async def test_accept_counterparty_only(client, world):
    w = world
    await _setup_same_day(w)
    sid = (await _create(client, w)).json()["id"]
    for t in ("e1", "e3", "deleg", "admin"):
        h = await _login(client, w["email"](t))
        r = await client.post(f"{SW}/{sid}/accept", headers=h)
        assert r.status_code == 403, (t, r.text)
    r = await client.post(f"{SW}/99999999/accept",
                          headers=await _login(client, w["email"]("e2")))
    assert r.status_code == 404


async def test_self_approval_blocked(client, world):
    w, ids = world, world["ids"]
    await _setup_same_day(w)
    sid = await _to_approval(client, w)
    # give the counterparty a delegation covering both parties
    async with SessionLocal() as db:
        db.add(ScheduleDelegation(
            grantee_id=ids["e2"], scope_type=DelegationScope.EMPLOYEES,
            employee_ids=[ids["e1"], ids["e3"]], can_approve_changes=True,
            valid_from=TODAY - timedelta(days=1)))
        await db.commit()
    for t in ("e1", "e2"):
        h = await _login(client, w["email"](t))
        r = await client.post(f"{SW}/{sid}/decide", headers=h,
                              json={"action": "approve"})
        assert r.status_code == 403, (t, r.text)
        assert (await client.get(SW, headers=h)).json() == []
    # roster admin who is not a party may decide, even reject
    ha = await _login(client, w["email"]("admin"))
    r = await client.post(f"{SW}/{sid}/decide", headers=ha,
                          json={"action": "reject", "note": "no"})
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    assert await _cell(ids["e1"], dn(0)) == (ids["t1"], False)
    async with SessionLocal() as db:
        n = (await db.execute(select(Notification).where(
            Notification.user_id.in_([ids["e1"], ids["e2"]]),
            Notification.title == "Shift swap rejected"))).scalars().all()
        assert {x.user_id for x in n} == {ids["e1"], ids["e2"]}


async def test_approver_scope_must_cover_both(client, world):
    w, ids = world, world["ids"]
    await _setup_same_day(w)
    sid = await _to_approval(client, w)
    h1 = await _login(client, w["email"]("deleg1"))  # covers e1 only
    r = await client.post(f"{SW}/{sid}/decide", headers=h1, json={"action": "approve"})
    assert r.status_code == 403
    assert (await client.get(SW, headers=h1)).json() == []
    hp = await _login(client, w["email"]("e3"))
    r = await client.post(f"{SW}/{sid}/decide", headers=hp, json={"action": "approve"})
    assert r.status_code == 403
    assert await _cell(ids["e1"], dn(0)) == (ids["t1"], False)


async def test_create_validation(client, world):
    w, ids = world, world["ids"]
    await _setup_same_day(w)
    # self
    r = await _create(client, w, cp="e1")
    assert r.status_code == 400
    # inactive counterparty / no employee record
    r = await _create(client, w, cp="e5")
    assert r.status_code == 400
    r = await _create(client, w, counterparty_id=2**31 - 1)
    assert r.status_code == 400
    # past
    await _pub(ids["e1"], TODAY - timedelta(days=1), ids["t1"])
    r = await _create(client, w, requester_date=(TODAY - timedelta(days=1)).isoformat())
    assert r.status_code == 400
    # beyond 90 days
    r = await _create(client, w, requester_date=(TODAY + timedelta(days=91)).isoformat())
    assert r.status_code == 400
    # dates too far apart
    r = await _create(client, w, counterparty_date=dd(15))
    assert r.status_code == 400
    # requester has no published shift on that date
    r = await _create(client, w, requester_date=dd(5))
    assert r.status_code == 400
    # draft shift does not count
    await _pub(ids["e1"], dn(6), ids["t1"], status=RosterStatus.DRAFT)
    r = await _create(client, w, requester_date=dd(6))
    assert r.status_code == 400
    # identical cells -> nothing to swap
    await _pub(ids["e1"], dn(7), ids["t1"])
    await _pub(ids["e2"], dn(7), ids["t1"])
    r = await _create(client, w, requester_date=dd(7))
    assert r.status_code == 400
    # schema: bad id
    r = await _create(client, w, counterparty_id=0)
    assert r.status_code == 422


async def test_duplicate_pending_409(client, world):
    w, ids = world, world["ids"]
    await _setup_same_day(w)
    assert (await _create(client, w)).status_code == 200
    r = await _create(client, w)
    assert r.status_code == 409
    # the counterparty's side conflicts too (e2 requesting something on D)
    await _pub(ids["e3"], dn(0), ids["t1"])
    r = await _create(client, w, requester="e3", cp="e2")
    assert r.status_code == 409
    # different date is fine
    await _pub(ids["e1"], dn(1), ids["t1"])
    await _pub(ids["e2"], dn(1), ids["t2"])
    assert (await _create(client, w, requester_date=dd(1))).status_code == 200


async def test_leave_conflict_409(client, world):
    w, ids = world, world["ids"]
    await _setup_same_day(w)
    async with SessionLocal() as db:
        lt = LeaveType(name=f"SWLV{w['sfx']}")
        db.add(lt)
        await db.commit()
        db.add(LeaveRequest(
            employee_id=ids["e2"], leave_type_id=lt.id, start_date=dn(0),
            end_date=dn(0), is_half_day=False, reason="t",
            status=LeaveStatus.APPROVED, created_by_user_id=ids["e2"]))
        await db.commit()
    r = await _create(client, w)  # e2 would work t1 on a leave day
    assert r.status_code == 409
    assert dd(0) in r.text


async def test_accept_schedule_changed_409(client, world):
    w, ids = world, world["ids"]
    await _setup_same_day(w)
    sid = (await _create(client, w)).json()["id"]
    async with SessionLocal() as db:
        e = (await db.execute(select(RosterEntry).where(
            RosterEntry.employee_id == ids["e1"],
            RosterEntry.work_date == dn(0)))).scalars().one()
        e.shift_template_id = ids["tn"]
        await db.commit()
    h2 = await _login(client, w["email"]("e2"))
    r = await client.post(f"{SW}/{sid}/accept", headers=h2)
    assert r.status_code == 409 and "schedule changed" in r.text.lower()


async def test_past_on_approve_400(client, world):
    w, ids = world, world["ids"]
    await _setup_same_day(w)
    sid = await _to_approval(client, w)
    async with SessionLocal() as db:
        s = await db.get(ShiftSwapRequest, sid)
        s.requester_date = s.counterparty_date = TODAY - timedelta(days=1)
        await db.commit()
    hd = await _login(client, w["email"]("deleg"))
    r = await client.post(f"{SW}/{sid}/decide", headers=hd, json={"action": "approve"})
    assert r.status_code == 400
    assert await _cell(ids["e1"], dn(0)) == (ids["t1"], False)


async def test_double_decide_concurrent(client, world):
    w, ids = world, world["ids"]
    await _setup_same_day(w)
    sid = await _to_approval(client, w)
    hd = await _login(client, w["email"]("deleg"))
    url = f"{SW}/{sid}/decide"
    r1, r2 = await asyncio.gather(
        client.post(url, headers=hd, json={"action": "approve"}),
        client.post(url, headers=hd, json={"action": "approve"}),
    )
    assert sorted([r1.status_code, r2.status_code]) == [200, 409], (r1.text, r2.text)
    assert await _cell(ids["e1"], dn(0)) == (ids["t2"], False)
    async with SessionLocal() as db:
        hist = (await db.execute(select(RosterEntryHistory).where(
            RosterEntryHistory.employee_id == ids["e1"]))).scalars().all()
        assert len(hist) == 1  # applied exactly once


async def test_candidates(client, world):
    w, ids = world, world["ids"]
    await _pub(ids["e2"], dn(0), ids["t2"])
    await _pub(ids["e4"], dn(0), off=True)
    await _pub(ids["e3"], dn(0), ids["t1"])  # other department
    h1 = await _login(client, w["email"]("e1"))
    r = await client.get(f"{SW}/candidates", headers=h1, params={"date": dd(0)})
    assert r.status_code == 200, r.text
    by = {x["user_id"]: x for x in r.json()}
    assert set(by) == {ids["e2"], ids["e4"]}  # same dept, active, not self
    assert by[ids["e2"]]["shift_template_id"] == ids["t2"]
    assert by[ids["e2"]]["shift_name"] == f"SWT2{w['sfx']}"
    assert by[ids["e4"]]["is_week_off"] is True
    assert by[ids["e2"]]["name"] == "SW e2"


@pytest.fixture
async def rules_cfg():
    keys = ["min_rest_hours", "max_consecutive_days",
            "max_consecutive_nights", "max_weekly_hours"]
    async with SessionLocal() as db:
        snap = {}
        for k in keys:
            row = await db.get(SystemSetting, f"schedule.{k}")
            snap[k] = row.value if row else None
    try:
        async def apply(**kv):
            async with SessionLocal() as db:
                await set_time_rules(
                    db, {f"schedule.{k}": str(v) for k, v in kv.items()})
        yield apply
    finally:
        async with SessionLocal() as db:
            for k, v in snap.items():
                row = await db.get(SystemSetting, f"schedule.{k}")
                if v is None:
                    if row:
                        await db.delete(row)
                elif row:
                    row.value = v
                else:
                    db.add(SystemSetting(key=f"schedule.{k}", value=v,
                                         description="restored"))
            await db.commit()


async def test_check_rest_violation_and_decide_warnings(client, world, rules_cfg):
    w, ids = world, world["ids"]
    await rules_cfg(min_rest_hours=11, max_consecutive_days=6,
                    max_consecutive_nights=4, max_weekly_hours=168)
    # e1: night on D; e2: day on D and day on D+1. After swap e2 works the
    # night (ends D+1 06:00) then a day at 09:00 -> 3h rest.
    await _pub(ids["e1"], dn(0), ids["tn"])
    await _pub(ids["e2"], dn(0), ids["t1"])
    await _pub(ids["e2"], dn(1), ids["t1"])
    sid = (await _create(client, w)).json()["id"]
    h1 = await _login(client, w["email"]("e1"))
    hd = await _login(client, w["email"]("deleg"))
    r = await client.get(f"{SW}/{sid}/check", headers=h1)
    assert r.status_code == 200, r.text
    v = r.json()
    assert [(x["user_id"], x["rule"], x["work_date"]) for x in v] == [
        (ids["e2"], "min_rest", dd(1))]
    assert (await client.get(f"{SW}/{sid}/check",
                             headers=await _login(client, w["email"]("e3")))
            ).status_code == 403
    h2 = await _login(client, w["email"]("e2"))
    await client.post(f"{SW}/{sid}/accept", headers=h2)
    r = await client.post(f"{SW}/{sid}/decide", headers=hd, json={"action": "approve"})
    assert r.status_code == 200, r.text
    assert [x["rule"] for x in r.json()["warnings"]] == ["min_rest"]
    # warnings never block
    assert await _cell(ids["e2"], dn(0)) == (ids["tn"], False)


async def test_check_no_violation_when_swap_harmless(client, world, rules_cfg):
    w, ids = world, world["ids"]
    await rules_cfg(min_rest_hours=11, max_consecutive_days=6,
                    max_consecutive_nights=4, max_weekly_hours=168)
    await _setup_same_day(w)
    sid = (await _create(client, w)).json()["id"]
    h1 = await _login(client, w["email"]("e1"))
    r = await client.get(f"{SW}/{sid}/check", headers=h1)
    assert r.status_code == 200 and r.json() == []
