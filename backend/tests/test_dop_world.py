from datetime import date, datetime, timedelta, timezone

from _dop_world import dop  # noqa: F401
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.approver_delegation import ApproverDelegation
from app.models.dop import ManagerAssignment, ManagerKind
from app.models.employee import Employee
from app.models.user import User
from app.services.dop import resolver as R
from app.services.dop.world import load_world
from app.services.org_time import local_today


async def _kind(db):
    return (await db.execute(select(ManagerKind).where(
        ManagerKind.code == "reporting"))).scalar_one()


async def test_loads_assignment_and_live_delegation(dop):
    u = dop["uid"]
    async with SessionLocal() as db:
        today = await local_today(db)
        kind = await _kind(db)
        db.add(ManagerAssignment(
            manager_kind_id=kind.id, scope_type="department",
            scope_department_id=dop["dept_id"], manager_user_id=u["mgr"],
            subdomains=[], starts_on=date(2020, 1, 1)))
        db.add(ApproverDelegation(
            user_id=u["mgr"], delegate_id=u["act"], starts_on=today,
            ends_on=today + timedelta(days=1)))
        await db.commit()
        w = await load_world(db, today)
        r = R.resolve(w, R.Approver("manager_kind", "reporting"), None,
                      u["emp"], "leave", today)
    assert "reporting" in w.kinds
    assert sorted(r.user_ids) == sorted([u["mgr"], u["act"]])
    assert r.acting_for == {u["act"]: [u["mgr"]]}


async def test_cancelled_rows_are_ignored(dop):
    u = dop["uid"]
    async with SessionLocal() as db:
        today = await local_today(db)
        kind = await _kind(db)
        db.add(ManagerAssignment(
            manager_kind_id=kind.id, scope_type="user",
            scope_user_id=u["emp"], manager_user_id=u["mgr"], subdomains=[],
            starts_on=today, cancelled_at=datetime.now(timezone.utc)))
        await db.commit()
        w = await load_world(db, today)
    assert R.find_assignment(w, "reporting", u["emp"], "leave", today) is None


async def test_hr_admin_and_location_fallback(dop):
    u = dop["uid"]
    async with SessionLocal() as db:
        today = await local_today(db)
        w = await load_world(db, today)
        assert u["hr"] in w.hr_ids and u["admin"] in w.hr_ids
        assert w.people[u["off"]].active is False
        assert w.people[u["emp"]].location == dop["loc"]
        assert w.people[u["emp"]].department == dop["dept"]
        # blank employee location falls back to the user's
        (await db.get(User, u["emp"])).location = "UserLoc"
        emp = (await db.execute(select(Employee).where(
            Employee.user_id == u["emp"]))).scalar_one()
        emp.location = None
        await db.flush()
        w = await load_world(db, today)
        assert w.people[u["emp"]].location == "UserLoc"
        await db.rollback()
