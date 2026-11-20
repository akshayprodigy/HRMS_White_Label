"""Phase 6A Task 4: the single location-aware holiday reader.
Real dev DB; every row created here is removed in teardown."""
import uuid
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, select

from app.db.session import SessionLocal
from app.models.employee import Employee
from app.models.hr import HolidayCalendar
from app.models.user import User
from app.services import holidays as H
from app.services import punch as punch_svc

D_ALL = date(2031, 8, 4)
D_MUM = date(2031, 8, 5)
D_PUNE = date(2031, 8, 6)
D_OPT = date(2031, 8, 7)
D_HQ = date(2031, 8, 8)
D_NONE = date(2031, 8, 9)
RANGE = (date(2031, 8, 1), date(2031, 8, 31))


@pytest.fixture
async def world():
    tag = uuid.uuid4().hex[:8]
    user_ids: list[int] = []
    hol_ids: list[int] = []
    w = {"tag": tag}
    async with SessionLocal() as db:
        try:
            # Nothing else may sit on our dates.
            clash = (await db.execute(select(HolidayCalendar.id).where(
                HolidayCalendar.date >= RANGE[0],
                HolidayCalendar.date <= RANGE[1]))).scalars().all()
            assert not clash, "dev DB has holidays in Aug 2031"

            async def mk_user(key, location, with_emp=True):
                u = User(email=f"hol_{key}_{tag}@test.com", full_name="Hol",
                         hashed_password="x")
                db.add(u)
                await db.flush()
                user_ids.append(u.id)
                if with_emp:
                    db.add(Employee(
                        user_id=u.id, employee_id=f"HL{tag[:5]}{key}",
                        department="T", designation="T",
                        date_of_joining=date(2020, 1, 1), location=location))
                w[key] = u.id

            await mk_user("mum", "Mumbai")
            await mk_user("mum2", " mumbai ")
            await mk_user("pune", "Pune")
            await mk_user("hq", "HQ")
            await mk_user("noemp", None, with_emp=False)
            for key, d, loc, opt in [
                ("all", D_ALL, "All", False), ("mum", D_MUM, "Mumbai", False),
                ("pune", D_PUNE, "Pune", False), ("opt", D_OPT, "All", True),
                ("hq", D_HQ, "HQ", False),
            ]:
                h = HolidayCalendar(name=f"H{key}_{tag}", date=d, location=loc,
                                    is_optional=opt)
                db.add(h)
                await db.flush()
                hol_ids.append(h.id)
                w["h_" + key] = h.id
            await db.commit()
            w["db"] = db
            yield w
        finally:
            await db.rollback()
            if hol_ids:
                await db.execute(delete(HolidayCalendar).where(
                    HolidayCalendar.id.in_(hol_ids)))
            if user_ids:
                await db.execute(delete(Employee).where(
                    Employee.user_id.in_(user_ids)))
                await db.execute(delete(User).where(User.id.in_(user_ids)))
            await db.commit()


def test_applies_and_norm():
    assert H.norm_loc("  Mum  BAI ") == "mum bai"
    assert H.applies("All", None) and H.applies("ALL ", "x")
    assert H.applies("Pune", " pune ")
    assert not H.applies("Pune", "Mumbai")
    assert not H.applies("", "") and not H.applies(None, None)
    assert not H.applies("HQ", None)


async def test_holidays_for_per_location(world):
    db = world["db"]
    ids = [world[k] for k in ("mum", "mum2", "pune", "hq", "noemp")]
    res = await H.holidays_for(db, ids, *RANGE)
    assert set(res) == set(ids)
    for k in ("mum", "mum2"):
        assert set(res[world[k]]) == {D_ALL, D_MUM}
    assert set(res[world["pune"]]) == {D_ALL, D_PUNE}
    assert set(res[world["hq"]]) == {D_ALL, D_HQ}
    assert set(res[world["noemp"]]) == {D_ALL}
    for u in ids:
        assert D_OPT not in res[u]  # optional never applies yet
    info = res[world["mum"]][D_MUM]
    assert info.holiday_id == world["h_mum"] and info.is_optional is False
    assert info.name == f"Hmum_{world['tag']}"


async def test_is_holiday_single_day(world):
    db = world["db"]
    assert (await H.is_holiday(db, world["pune"], D_PUNE)).name.startswith("Hpune")
    assert await H.is_holiday(db, world["mum"], D_PUNE) is None
    assert await H.is_holiday(db, world["mum"], D_NONE) is None
    assert await H.is_holiday(db, world["noemp"], D_ALL) is not None
    assert await H.is_holiday(db, world["mum"], D_OPT) is None


async def test_every_user_key_present_even_when_empty(world):
    db = world["db"]
    res = await H.holidays_for(
        db, [world["mum"], world["pune"]], date(2031, 9, 1), date(2031, 9, 2))
    assert res == {world["mum"]: {}, world["pune"]: {}}
    assert await H.holidays_for(db, [], *RANGE) == {}


async def test_mandatory_beats_optional_same_date(world, monkeypatch):
    db = world["db"]
    opt = HolidayCalendar(name=f"Hopt2_{world['tag']}", date=D_ALL,
                          location="All", is_optional=True)
    db.add(opt)
    await db.flush()

    async def picks(_db, ids, s, e):
        return {u: {opt.id} for u in ids}
    monkeypatch.setattr(H, "_approved_pick_holiday_ids", picks)
    try:
        info = (await H.holidays_for(db, [world["mum"]], D_ALL, D_ALL))[world["mum"]][D_ALL]
        assert info.is_optional is False and info.holiday_id == world["h_all"]
        # an approved pick makes an otherwise-unmatched optional apply
        info2 = (await H.holidays_for(db, [world["mum"]], D_OPT, D_OPT))[world["mum"]]
        assert info2 == {}  # picks only name `opt`, not the D_OPT holiday
    finally:
        await db.delete(opt)
        await db.commit()


async def test_optional_applies_with_approved_pick(world, monkeypatch):
    db = world["db"]

    async def picks(_db, ids, s, e):
        return {world["mum"]: {world["h_opt"]}}
    monkeypatch.setattr(H, "_approved_pick_holiday_ids", picks)
    res = await H.holidays_for(db, [world["mum"], world["pune"]], *RANGE)
    assert res[world["mum"]][D_OPT].is_optional is True
    assert D_OPT not in res[world["pune"]]


# ---- comp-off accrual uses the shared reader ----

async def _accrual(world, monkeypatch, uid, d):
    calls = []

    async def fake_create(db, **kw):
        calls.append(kw)
        return SimpleNamespace(**kw)
    monkeypatch.setattr(punch_svc, "create_comp_off_accrual", fake_create)
    from datetime import datetime, timezone
    pin = datetime(d.year, d.month, d.day, 4, 0, tzinfo=timezone.utc)
    pout = datetime(d.year, d.month, d.day, 14, 0, tzinfo=timezone.utc)
    att = SimpleNamespace(work_date=d, id=None)
    user = SimpleNamespace(id=uid)
    res = await punch_svc._maybe_create_comp_off_accrual(
        world["db"], user=user, attendance=att, punch_in=pin, punch_out=pout)
    return res, calls


async def test_comp_off_location_matched_holiday(world, monkeypatch):
    res, calls = await _accrual(world, monkeypatch, world["pune"], D_PUNE)
    assert res is not None and calls[0]["holiday_name"] == f"Hpune_{world['tag']}"


async def test_comp_off_not_for_hq_holiday_on_pune_employee(world, monkeypatch):
    res, calls = await _accrual(world, monkeypatch, world["pune"], D_HQ)
    assert res is None and not calls
    res, calls = await _accrual(world, monkeypatch, world["hq"], D_HQ)
    assert res is not None


# ---- single reader guard ----

ALLOW = {
    "services/holidays.py",
    "api/v1/endpoints/hr.py",   # holiday CRUD + GET /hr/holidays listing
}


def test_no_holidaycalendar_reads_outside_reader():
    app = Path(__file__).resolve().parents[1] / "app"
    offenders = []
    for f in app.rglob("*.py"):
        rel = f.relative_to(app).as_posix()
        if rel.startswith("models/") or rel.startswith("schemas/") or rel in ALLOW:
            continue
        txt = f.read_text()
        if "HolidayCalendar" in txt:
            offenders.append(rel)
    assert not offenders, f"read holidays via services.holidays instead: {offenders}"
