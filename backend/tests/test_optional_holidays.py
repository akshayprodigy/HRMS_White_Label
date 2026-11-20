"""Phase 6A Task 6: optional holiday picks, quota, approvals, CSV import.
Real dev DB; everything created here is removed in teardown."""
import asyncio
import uuid
from datetime import date, timedelta

import pytest
from _tz import org_today  # noqa: E402
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, insert, select

from app.api import deps
from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.main import create_app
from app.models.approval_chain import (
    ApprovalChain, ApprovalChainStep, ChainedApprovalInstance,
    ChainedApprovalStepInstance,
)
from app.models.audit import AuditLog
from app.models.employee import Employee, EmployeeStatus
from app.models.hr import HolidayCalendar
from app.models.notification import Notification
from app.models.optional_holiday import OptionalHolidayPick
from app.models.payroll import PayrollRun, PayrollRunStatus
from app.models.system import SystemSetting
from app.models.user import Role, User, user_roles
from app.services import holidays as H
from app.services import optional_holidays as OH
from app.services.absence_lop import count_absent_days, is_non_working_day

P = "/api/v1/holidays"
D1, D2, D3 = date(2032, 3, 10), date(2032, 3, 11), date(2032, 3, 12)
D_ALL, D_PUNE, D_MAND = date(2032, 4, 5), date(2032, 4, 6), date(2032, 4, 7)
LOCKED = date(2032, 6, 15)
QKEY = OH.QUOTA_KEY


async def _cleanup(sfx):
    async with SessionLocal() as db:
        uids = list((await db.execute(select(User.id).where(
            User.email.like(f"oh\\_%\\_{sfx}@test.com")))).scalars().all())
        hids = list((await db.execute(select(HolidayCalendar.id).where(
            HolidayCalendar.name.like(f"%{sfx}%")))).scalars().all())
        pids = list((await db.execute(select(OptionalHolidayPick.id).where(
            (OptionalHolidayPick.user_id.in_(uids)) |
            (OptionalHolidayPick.holiday_id.in_(hids))))).scalars().all()) \
            if (uids or hids) else []
        chain_ids = list((await db.execute(select(ApprovalChain.id).where(
            ApprovalChain.name.like(f"%{sfx}%")))).scalars().all())
        inst_ids = list((await db.execute(select(ChainedApprovalInstance.id).where(
            ChainedApprovalInstance.submitter_id.in_(uids)))).scalars().all()) if uids else []
        if inst_ids:
            await db.execute(delete(ChainedApprovalStepInstance).where(
                ChainedApprovalStepInstance.instance_id.in_(inst_ids)))
            await db.execute(delete(Notification).where(
                Notification.resource_type == "chained_approval_instance",
                Notification.resource_id.in_([str(i) for i in inst_ids])))
            await db.execute(delete(ChainedApprovalInstance).where(
                ChainedApprovalInstance.id.in_(inst_ids)))
        if chain_ids:
            await db.execute(delete(ApprovalChainStep).where(
                ApprovalChainStep.chain_id.in_(chain_ids)))
            await db.execute(delete(ApprovalChain).where(
                ApprovalChain.id.in_(chain_ids)))
        if pids:
            await db.execute(delete(Notification).where(
                Notification.resource_type == "optional_holiday",
                Notification.resource_id.in_([str(p) for p in pids])))
            await db.execute(delete(AuditLog).where(
                AuditLog.resource_type == "optional_holiday",
                AuditLog.resource_id.in_([str(p) for p in pids])))
            await db.execute(delete(OptionalHolidayPick).where(
                OptionalHolidayPick.id.in_(pids)))
        # CSV-import rows
        await db.execute(delete(HolidayCalendar).where(
            HolidayCalendar.name.like(f"%{sfx}%")))
        await db.execute(delete(PayrollRun).where(
            PayrollRun.month == LOCKED.month, PayrollRun.year == LOCKED.year))
        if uids:
            await db.execute(delete(Notification).where(Notification.user_id.in_(uids)))
            await db.execute(delete(AuditLog).where(AuditLog.user_id.in_(uids)))
            await db.execute(delete(Employee).where(Employee.user_id.in_(uids)))
            await db.execute(delete(user_roles).where(user_roles.c.user_id.in_(uids)))
            await db.execute(delete(User).where(User.id.in_(uids)))
        await db.commit()


@pytest.fixture
async def world():
    sfx = uuid.uuid4().hex[:8]
    w: dict = {"sfx": sfx}
    async with SessionLocal() as db:
        row = await db.get(SystemSetting, QKEY)
        w["saved_quota"] = (row.value, row.description) if row else None
        if row:
            row.value = "2"
        else:
            db.add(SystemSetting(key=QKEY, value="2", description="t"))
        await db.commit()
    try:
        async with SessionLocal() as db:
            us = {}
            for n in ("hr", "mgr", "emp", "emp2", "pune", "plain"):
                us[n] = User(email=f"oh_{n}_{sfx}@test.com",
                             full_name=f"Oh {n} {sfx}",
                             hashed_password=get_password_hash("x"),
                             is_active=True)
            db.add_all(us.values())
            await db.flush()
            us["emp"].manager_id = us["mgr"].id
            us["emp2"].manager_id = us["mgr"].id
            role = (await db.execute(
                select(Role).where(Role.name == "HR"))).scalars().first()
            await db.execute(insert(user_roles).values(
                user_id=us["hr"].id, role_id=role.id))
            for n, loc in (("emp", "Mumbai"), ("emp2", "Mumbai"),
                           ("pune", "Pune"), ("plain", "Mumbai")):
                db.add(Employee(
                    user_id=us[n].id, employee_id=f"OH{n}{sfx}",
                    department="T", designation="T", location=loc,
                    date_of_joining=date(2020, 1, 1),
                    status=EmployeeStatus.ACTIVE))
            hs = {}
            for k, d, loc, opt in [
                ("m1", D1, "Mumbai", True), ("m2", D2, "Mumbai", True),
                ("m3", D3, "Mumbai", True), ("all", D_ALL, "All", True),
                ("pune", D_PUNE, "Pune", True),
                ("mand", D_MAND, "Mumbai", False),
                ("past", date(2020, 5, 5), "Mumbai", True),
                ("lock", LOCKED, "Mumbai", True),
            ]:
                hs[k] = HolidayCalendar(
                    name=f"OHol {k} {sfx}", date=d, location=loc, is_optional=opt)
            db.add_all(hs.values())
            await db.commit()
            w["uid"] = {n: u.id for n, u in us.items()}
            w["h"] = {k: h.id for k, h in hs.items()}
        yield w
    finally:
        await _cleanup(sfx)
        async with SessionLocal() as db:
            row = await db.get(SystemSetting, QKEY)
            sv = w["saved_quota"]
            if sv is None:
                if row:
                    await db.delete(row)
            elif row:
                row.value = sv[0]
            await db.commit()


async def _login(c, email):
    r = await c.post("/api/v1/auth/login",
                     data={"username": email, "password": "x"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
async def api(world):
    app = create_app()
    app.dependency_overrides[deps.verify_attendance] = lambda: None
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as c:
        s = world["sfx"]
        for n in ("hr", "mgr", "emp", "emp2", "pune", "plain"):
            setattr(c, n, await _login(c, f"oh_{n}_{s}@test.com"))
        yield c


async def pick(api, world, key, who="emp", reason=None):
    return await api.post(f"{P}/picks", headers=getattr(api, who), json={
        "holiday_id": world["h"][key], "reason": reason})


async def test_quota_and_cancel_frees(api, world):
    r1 = await pick(api, world, "m1")
    assert r1.status_code == 201, r1.text
    assert r1.json()["status"] == "pending"
    assert (await pick(api, world, "m2")).status_code == 201
    r = await pick(api, world, "m3")
    assert r.status_code == 409 and "quota (2)" in r.text
    r = await api.post(f"{P}/picks/{r1.json()['id']}/cancel", headers=api.emp)
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert (await pick(api, world, "m3")).status_code == 201
    # cancelled can be re-picked once quota allows
    r = await api.post(f"{P}/picks/{r1.json()['id']}/cancel", headers=api.emp)
    assert r.status_code == 409


async def test_create_validation(api, world):
    assert (await pick(api, world, "pune")).status_code == 422   # wrong location
    assert (await pick(api, world, "past")).status_code == 422   # date passed
    r = await pick(api, world, "mand")
    assert r.status_code == 422 and "optional" in r.text
    assert (await api.post(f"{P}/picks", headers=api.emp, json={
        "holiday_id": 99999999})).status_code == 404
    assert (await pick(api, world, "m1")).status_code == 201
    assert (await pick(api, world, "m1")).status_code == 409     # duplicate
    assert (await pick(api, world, "all")).status_code == 201    # 'All' ok


async def test_direct_approve_counts_only_for_that_user(api, world):
    pid = (await pick(api, world, "m1")).json()["id"]
    pid2 = (await pick(api, world, "m1", who="emp2")).json()["id"]
    r = await api.post(f"{P}/picks/{pid}/decide", headers=api.mgr,
                       json={"approve": True, "note": "ok"})
    assert r.status_code == 200 and r.json()["status"] == "approved"
    e, e2 = world["uid"]["emp"], world["uid"]["emp2"]
    async with SessionLocal() as db:
        res = await H.holidays_for(db, [e, e2], D1, D1)
        assert D1 in res[e] and res[e][D1].is_optional
        assert D1 not in res[e2]          # pending pick: not a holiday
        assert is_non_working_day(None, D1, res[e], {6})
        assert not is_non_working_day(None, D1, res[e2], {6})
        kw = dict(first=D1, last=D1, shifts={}, default_offs={6},
                  punched=set(), full_leave=set(), half_leave=set())
        assert count_absent_days(user_id=e, holidays=res[e], **kw) == 0.0
        assert count_absent_days(user_id=e2, holidays=res[e2], **kw) == 1.0
        n = (await db.execute(select(Notification).where(
            Notification.user_id == e, Notification.resource_type == "optional_holiday",
            Notification.resource_id == str(pid)))).scalars().all()
        assert any(x.event_type == "optional_holiday_decided" for x in n)
        # manager was notified of the submission (direct path)
        n = (await db.execute(select(Notification).where(
            Notification.user_id == world["uid"]["mgr"],
            Notification.resource_id == str(pid)))).scalars().all()
        assert any(x.event_type == "optional_holiday_submitted" for x in n)
    # already decided
    r = await api.post(f"{P}/picks/{pid}/decide", headers=api.mgr,
                       json={"approve": False})
    assert r.status_code == 409
    # not the employee's own manager / no perm -> 403; self -> 403
    assert (await api.post(f"{P}/picks/{pid2}/decide", headers=api.plain,
                           json={"approve": True})).status_code == 403
    assert (await api.post(f"{P}/picks/{pid2}/decide", headers=api.emp2,
                           json={"approve": True})).status_code == 403
    # HR can decide
    assert (await api.post(f"{P}/picks/{pid2}/decide", headers=api.hr,
                           json={"approve": True})).status_code == 200


async def test_reject(api, world):
    pid = (await pick(api, world, "m1")).json()["id"]
    r = await api.post(f"{P}/picks/{pid}/decide", headers=api.mgr,
                       json={"approve": False, "note": "busy"})
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    assert r.json()["decision_note"] == "busy"
    async with SessionLocal() as db:
        res = await H.holidays_for(db, [world["uid"]["emp"]], D1, D1)
        assert D1 not in res[world["uid"]["emp"]]
    # rejected frees quota and allows re-pick
    assert (await pick(api, world, "m1")).status_code == 201


async def _insert_pick(world, key, who, status):
    async with SessionLocal() as db:
        h = await db.get(HolidayCalendar, world["h"][key])
        p = OptionalHolidayPick(holiday_id=h.id, user_id=world["uid"][who],
                                year=h.date.year, status=status)
        db.add(p)
        await db.commit()
        return p.id


async def test_cancel_rules(api, world):
    # employee cancel after the date -> 409
    old = await _insert_pick(world, "past", "emp", "approved")
    r = await api.post(f"{P}/picks/{old}/cancel", headers=api.emp)
    assert r.status_code == 409 and "date has passed" in r.text
    # other employee cannot see it; HR can cancel
    assert (await api.post(f"{P}/picks/{old}/cancel", headers=api.plain)
            ).status_code == 404
    r = await api.post(f"{P}/picks/{old}/cancel", headers=api.hr)
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    # HR cancels a future approved pick
    pid = (await pick(api, world, "m1")).json()["id"]
    await api.post(f"{P}/picks/{pid}/decide", headers=api.mgr,
                   json={"approve": True})
    r = await api.post(f"{P}/picks/{pid}/cancel", headers=api.hr)
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    async with SessionLocal() as db:
        res = await H.holidays_for(db, [world["uid"]["emp"]], D1, D1)
        assert D1 not in res[world["uid"]["emp"]]


async def test_locked_period(api, world):
    pid = (await pick(api, world, "lock")).json()["id"]
    async with SessionLocal() as db:
        db.add(PayrollRun(month=LOCKED.month, year=LOCKED.year,
                          status=PayrollRunStatus.FINALIZED))
        await db.commit()
    r = await api.post(f"{P}/picks/{pid}/decide", headers=api.mgr,
                       json={"approve": True})
    assert r.status_code == 409 and "payroll period locked" in r.text
    # rejecting is still allowed
    r = await api.post(f"{P}/picks/{pid}/decide", headers=api.mgr,
                       json={"approve": False})
    assert r.status_code == 200
    async with SessionLocal() as db:
        await db.execute(delete(PayrollRun).where(
            PayrollRun.month == LOCKED.month, PayrollRun.year == LOCKED.year))
        await db.commit()
    pid2 = (await pick(api, world, "lock")).json()["id"]
    await api.post(f"{P}/picks/{pid2}/decide", headers=api.mgr,
                   json={"approve": True})
    async with SessionLocal() as db:
        db.add(PayrollRun(month=LOCKED.month, year=LOCKED.year,
                          status=PayrollRunStatus.FINALIZED))
        await db.commit()
    r = await api.post(f"{P}/picks/{pid2}/cancel", headers=api.hr)
    assert r.status_code == 409 and "payroll period locked" in r.text


@pytest.fixture
async def chain(api, world):
    async with SessionLocal() as db:
        c = ApprovalChain(
            name=f"OhChain {world['sfx']}", entity_type="optional_holiday",
            is_active=True, effective_from=date(2020, 1, 1),
            skip_if_same_person=False)
        db.add(c)
        await db.flush()
        db.add(ApprovalChainStep(
            chain_id=c.id, step_order=1, approver_type="specific_user",
            approver_ref=str(world["uid"]["hr"]), label="HR"))
        await db.commit()
    yield c


async def test_chain_path(api, world, chain):
    r = await pick(api, world, "m1")
    assert r.status_code == 201, r.text
    q = r.json()
    assert q["routed_via"] == "chain"
    r = await api.post(f"{P}/picks/{q['id']}/decide", headers=api.hr,
                       json={"approve": True})
    assert r.status_code == 409 and "approvals" in r.text
    r = await api.get("/api/v1/approval-chains/my-queue", headers=api.hr)
    row = next(x for x in r.json() if x["entity"]["id"] == q["id"]
               and x["entity"]["kind"] == "optional_holiday")
    assert row["entity"]["title"].startswith("Optional holiday: OHol m1")
    iid = row["instance"]["id"]
    r = await api.post(f"/api/v1/approval-chains/instances/{iid}/act",
                       headers=api.hr, json={"action": "approve"})
    assert r.status_code == 200, r.text
    async with SessionLocal() as db:
        assert (await db.get(OptionalHolidayPick, q["id"])).status == "approved"
        res = await H.holidays_for(db, [world["uid"]["emp"]], D1, D1)
        assert D1 in res[world["uid"]["emp"]]

    # reject via chain
    q2 = (await pick(api, world, "m2")).json()
    r = await api.get("/api/v1/approval-chains/my-queue", headers=api.hr)
    iid2 = next(x["instance"]["id"] for x in r.json()
                if x["entity"]["id"] == q2["id"]
                and x["entity"]["kind"] == "optional_holiday")
    r = await api.post(f"/api/v1/approval-chains/instances/{iid2}/act",
                       headers=api.hr, json={"action": "reject"})
    assert r.status_code == 200, r.text
    async with SessionLocal() as db:
        assert (await db.get(OptionalHolidayPick, q2["id"])).status == "rejected"

    # cancel a chain-pending pick closes its instance
    q3 = (await pick(api, world, "m3")).json()
    r = await api.post(f"{P}/picks/{q3['id']}/cancel", headers=api.emp)
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    async with SessionLocal() as db:
        inst = (await db.execute(select(ChainedApprovalInstance).where(
            ChainedApprovalInstance.entity_type == "optional_holiday",
            ChainedApprovalInstance.entity_id == q3["id"]))).scalars().one()
        assert inst.status == "cancelled"


async def test_concurrent_last_slot(api, world):
    assert (await pick(api, world, "m1")).status_code == 201
    app = create_app()
    app.dependency_overrides[deps.verify_attendance] = lambda: None
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as c2:
        h2 = await _login(c2, f"oh_emp_{world['sfx']}@test.com")
        r1, r2 = await asyncio.gather(
            api.post(f"{P}/picks", headers=api.emp,
                     json={"holiday_id": world["h"]["m2"]}),
            c2.post(f"{P}/picks", headers=h2,
                    json={"holiday_id": world["h"]["m3"]}))
    assert sorted([r1.status_code, r2.status_code]) == [201, 409], (
        r1.text, r2.text)
    async with SessionLocal() as db:
        n = len((await db.execute(select(OptionalHolidayPick.id).where(
            OptionalHolidayPick.user_id == world["uid"]["emp"]))).all())
    assert n == 2


async def test_my_shape(api, world):
    pid = (await pick(api, world, "m1")).json()["id"]
    r = await api.get(f"{P}/my?year=2032", headers=api.emp)
    assert r.status_code == 200
    b = r.json()
    assert (b["quota"], b["used"], b["remaining"]) == (2, 1, 1)
    by = {h["id"]: h for h in b["holidays"]}
    assert by[world["h"]["m1"]]["pick"] == {"id": pid, "status": "pending"}
    assert by[world["h"]["m2"]]["pick"] is None
    assert by[world["h"]["m2"]]["is_optional"] is True
    assert by[world["h"]["mand"]]["is_optional"] is False
    assert world["h"]["pune"] not in by          # other location hidden
    assert world["h"]["all"] in by
    assert {"id", "name", "date", "location", "is_optional", "pick"} <= set(
        by[world["h"]["m1"]])
    r = await api.get(f"{P}/my", headers=api.emp)  # default year = today's
    assert r.json()["year"] == org_today().year
    assert (await api.get(f"{P}/my")).status_code == 401


async def test_list_scoping(api, world):
    pid = (await pick(api, world, "m1")).json()["id"]
    pid_p = (await pick(api, world, "pune", who="pune")).json()["id"]
    r = await api.get(f"{P}/picks?year=2032", headers=api.hr)
    ids = {x["id"] for x in r.json()}
    assert {pid, pid_p} <= ids
    r = await api.get(f"{P}/picks?status=pending&year=2032", headers=api.mgr)
    ids = {x["id"] for x in r.json()}
    assert pid in ids and pid_p not in ids
    assert (await api.get(f"{P}/picks", headers=api.plain)).status_code == 403
    assert (await api.get(f"{P}/picks?status=bogus", headers=api.hr)
            ).status_code == 422


async def test_time_rule_validation():
    from app.services import time_rules as tr
    assert tr.TIME_RULE_DEFAULTS[QKEY][0] == "2"
    async with SessionLocal() as db:
        for bad in ("21", "-1", "x"):
            with pytest.raises(ValueError):
                await tr.set_time_rules(db, {QKEY: bad})
        await db.rollback()


def _csv(sfx, extra=""):
    return (
        "name,date,location,is_optional\n"
        f"Imp A {sfx},2033-01-10,Mumbai,true\n"
        f"Imp B {sfx},2033-01-11,All,NO\n"
        f"Imp A {sfx},2033-01-10, mumbai ,false\n"      # dup (norm loc/name)
        f"Imp C {sfx},not-a-date,Mumbai,true\n"
        f"Imp D {sfx},2033-01-12,Mumbai,maybe\n"
        f"Imp E {sfx},2033-01-13,Pune,1\n" + extra)


async def test_csv_import(api, world):
    sfx = world["sfx"]
    files = lambda t: {"file": ("h.csv", t.encode(), "text/csv")}  # noqa: E731
    r = await api.post("/api/v1/hr/holidays/import", headers=api.hr,
                       files=files(_csv(sfx)))
    assert r.status_code == 200, r.text
    b = r.json()
    assert (b["created"], b["skipped"]) == (3, 1)
    assert sorted(e["row"] for e in b["errors"]) == [5, 6]
    # re-import: all valid rows skipped vs DB
    r = await api.post("/api/v1/hr/holidays/import", headers=api.hr,
                       files=files(_csv(sfx)))
    b = r.json()
    assert (b["created"], b["skipped"]) == (0, 4)
    async with SessionLocal() as db:
        rows = (await db.execute(select(HolidayCalendar).where(
            HolidayCalendar.name.like(f"Imp % {sfx}")))).scalars().all()
        assert len(rows) == 3
        assert {r.name.split()[1]: r.is_optional for r in rows} == {
            "A": True, "B": False, "E": True}
    # year filter on listing
    r = await api.get("/api/v1/hr/holidays?year=2033", headers=api.hr)
    assert sum(1 for h in r.json() if sfx in h["name"]) == 3
    r = await api.get("/api/v1/hr/holidays?year=2034", headers=api.hr)
    assert not any(sfx in h["name"] for h in r.json())
    # permissions and shape
    assert (await api.post("/api/v1/hr/holidays/import", headers=api.emp,
                           files=files(_csv(sfx)))).status_code == 403
    assert (await api.post("/api/v1/hr/holidays/import", headers=api.hr,
                           files=files("a,b\n1,2\n"))).status_code == 422


async def test_csv_import_caps(api, world):
    sfx = world["sfx"]
    many = "name,date,location,is_optional\n" + "".join(
        f"X{i} {sfx},2033-02-01,All,0\n" for i in range(1001))
    r = await api.post("/api/v1/hr/holidays/import", headers=api.hr,
                       files={"file": ("h.csv", many.encode(), "text/csv")})
    assert r.status_code == 422
    big = b"name,date,location,is_optional\n" + b"#" * (1024 * 1024 + 10)
    r = await api.post("/api/v1/hr/holidays/import", headers=api.hr,
                       files={"file": ("h.csv", big, "text/csv")})
    assert r.status_code == 413
    async with SessionLocal() as db:
        assert not (await db.execute(select(HolidayCalendar.id).where(
            HolidayCalendar.name.like(f"X% {sfx}")))).first()
