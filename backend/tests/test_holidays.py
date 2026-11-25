"""Phase 6A Task 4: the single location-aware holiday reader.
Real dev DB; every row created here is removed in teardown."""
import uuid
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, select

from app.db.session import SessionLocal
from app.models.attendance import Attendance
from app.models.employee import Employee
from app.models.hr import HolidayCalendar
from app.models.system import SystemSetting
from app.models.user import User
from app.services import holidays as H
from app.services import punch as punch_svc
from app.services import time_rules as tr

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
            async def mk_user(key, location, with_emp=True, user_loc=None):
                u = User(email=f"hol_{key}_{tag}@test.com", full_name="Hol",
                         hashed_password="x", location=user_loc)
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
            await mk_user("blank", "  ")          # blank employee location
            await mk_user("ufall", None, with_emp=False, user_loc="Pune")
            await mk_user("beu", "", user_loc="Mumbai")
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
            w["hol_ids"] = set(hol_ids)
            yield w
        finally:
            await db.rollback()
            if user_ids:
                await db.execute(delete(Attendance).where(
                    Attendance.user_id.in_(user_ids)))
            if hol_ids:
                await db.execute(delete(HolidayCalendar).where(
                    HolidayCalendar.id.in_(hol_ids)))
            if user_ids:
                await db.execute(delete(Employee).where(
                    Employee.user_id.in_(user_ids)))
                await db.execute(delete(User).where(User.id.in_(user_ids)))
            await db.commit()


def ours(w, res_for_user):
    """Only this run's holidays (ignores unrelated rows in the dev DB)."""
    return {d: i for d, i in res_for_user.items() if i.holiday_id in w["hol_ids"]}


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
    o = lambda k: set(ours(world, res[world[k]]))  # noqa: E731
    for k in ("mum", "mum2"):
        assert o(k) == {D_ALL, D_MUM}
    assert o("pune") == {D_ALL, D_PUNE}
    assert o("hq") == {D_ALL, D_HQ}
    assert o("noemp") == {D_ALL, D_HQ}  # default location HQ
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
    assert await H.is_holiday(db, world["noemp"], D_PUNE) is None
    assert await H.is_holiday(db, world["mum"], D_OPT) is None


async def test_every_user_key_present_even_when_empty(world):
    db = world["db"]
    res = await H.holidays_for(
        db, [world["mum"], world["pune"]], date(2031, 9, 1), date(2031, 9, 2))
    assert res == {world["mum"]: {}, world["pune"]: {}}
    res = await H.holidays_for(db, [world["mum"], world["pune"]], *RANGE)
    assert set(res) == {world["mum"], world["pune"]}
    assert await H.holidays_for(db, [], *RANGE) == {}


@pytest.mark.parametrize("optional_first", [False, True])
async def test_mandatory_beats_optional_same_date(world, monkeypatch, optional_first):
    """Mandatory wins whichever of the two rows has the lower id."""
    db = world["db"]
    mand = world["h_all"]  # mandatory All on D_ALL
    if optional_first:
        # Recreate so the optional row has the LOWER id than the mandatory.
        old = await db.get(HolidayCalendar, mand)
        await db.delete(old)
        await db.flush()
    opt = HolidayCalendar(name=f"Hopt2_{world['tag']}", date=D_ALL,
                          location="All", is_optional=True)
    db.add(opt)
    await db.flush()
    new_mand = None
    if optional_first:
        new_mand = HolidayCalendar(name=f"Hall2_{world['tag']}", date=D_ALL,
                                   location="All", is_optional=False)
        db.add(new_mand)
        await db.flush()
        assert opt.id < new_mand.id
        mand = new_mand.id
    world["hol_ids"].update({opt.id, mand})

    async def picks(_db, ids, s_, e_):
        return {u: {opt.id} for u in ids}
    monkeypatch.setattr(H, "_approved_pick_holiday_ids", picks)
    try:
        info = (await H.holidays_for(db, [world["mum"]], D_ALL, D_ALL))[world["mum"]][D_ALL]
        assert info.is_optional is False and info.holiday_id == mand
    finally:
        await db.delete(opt)
        if new_mand is not None:
            await db.delete(new_mand)
        await db.commit()


async def _set_default(db, value):
    await tr.set_time_rules(db, {"holidays.default_location": value})


@pytest.fixture
async def restore_default():
    async with SessionLocal() as db:
        before = (await tr.get_time_rules(db))["holidays.default_location"]
        row = await db.get(SystemSetting, "holidays.default_location")
        existed = row is not None
    yield
    async with SessionLocal() as db:
        if existed:
            await _set_default(db, before)
        else:
            await db.execute(delete(SystemSetting).where(
                SystemSetting.key == "holidays.default_location"))
            await db.commit()


async def test_blank_location_gets_default_hq_holiday(world, restore_default):
    db = world["db"]
    await _set_default(db, "HQ")
    res = await H.holidays_for(
        db, [world["blank"], world["ufall"], world["beu"]], *RANGE)
    assert D_HQ in res[world["blank"]]            # blank -> default HQ
    assert D_HQ not in res[world["ufall"]]        # User.location = Pune wins
    assert D_PUNE in res[world["ufall"]]
    assert D_MUM in res[world["beu"]]  # blank emp loc -> User.location
    assert D_HQ not in res[world["beu"]]


async def test_blank_default_rule_means_no_fallback(world, restore_default):
    db = world["db"]
    await _set_default(db, "")
    res = await H.holidays_for(db, [world["blank"], world["noemp"]], *RANGE)
    for k in ("blank", "noemp"):
        assert set(ours(world, res[world[k]])) == {D_ALL}
    assert (await tr.get_time_rules(db))["holidays.default_location"] == ""


async def test_default_location_rule_validation(world, restore_default):
    db = world["db"]
    out = await tr.set_time_rules(db, {"holidays.default_location": "  Pune   Office "})
    assert out["holidays.default_location"] == "Pune Office"
    with pytest.raises(ValueError):
        await tr.set_time_rules(db, {"holidays.default_location": "x" * 101})


async def test_location_counts_and_matching(world, restore_default):
    db = world["db"]
    await _set_default(db, "HQ")
    counts = {norm: c for norm, c in (
        (H.norm_loc(r["location"]), r["count"]) for r in await H.location_counts(db))}
    assert counts["mumbai"] >= 3 and counts["pune"] >= 1 and counts["hq"] >= 2
    assert await H.matching_employee_count(db, "Nowhere-land") == 0
    assert await H.matching_employee_count(db, " MUMBAI ") == counts["mumbai"]
    assert await H.matching_employee_count(db, "All") >= sum(counts.values())


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


# ---- per-user holidays in OT recompute and muster ----

def _att(uid, d):
    from datetime import datetime, timezone
    return Attendance(user_id=uid, mode="web", work_date=d,
                      captured_at=datetime(d.year, d.month, d.day, 4, 0,
                                           tzinfo=timezone.utc))


async def test_overtime_recompute_uses_per_user_holidays(world, monkeypatch):
    from app.api.v1.endpoints import overtime as ot
    db = world["db"]
    db.add_all([_att(world["mum"], D_MUM), _att(world["pune"], D_MUM)])
    await db.commit()
    seen = {}

    async def fake(db_, *, user_id, work_date, attendance, holiday_set, **kw):
        seen[user_id] = work_date in holiday_set
        return (0, 0, 0)
    monkeypatch.setattr(ot, "_resolve_one", fake)
    await ot.recompute_range(db, *RANGE, [world["mum"], world["pune"]], None)
    assert seen == {world["mum"]: True, world["pune"]: False}
    # user_ids=None path also resolves holidays per attendance user
    seen.clear()
    await ot.recompute_range(db, *RANGE, None, None)
    assert seen[world["mum"]] is True and seen[world["pune"]] is False


async def test_muster_is_holiday_is_per_user(world, monkeypatch):
    from app.api.v1.endpoints import reports as rp
    db = world["db"]
    db.add_all([_att(world["mum"], D_MUM), _att(world["pune"], D_MUM)])
    await db.commit()
    got = {}

    def fake_build(records, filters):
        got.update({r.user_id: r.is_holiday for r in records})
        return None
    monkeypatch.setattr(rp._rep, "build_muster_roll", fake_build)
    await rp._fetch_muster_roll(db, rp._rep.ReportFilter(start=RANGE[0], end=RANGE[1]))
    assert got == {world["mum"]: True, world["pune"]: False}


async def test_holiday_endpoints_report_matching_count(world):
    from app.api.v1.endpoints import hr
    from app.schemas.hr import HolidayCalendarCreate
    db = world["db"]
    loc = await hr.holiday_locations(db=db, current_user=None)
    assert "default_location" in loc
    assert any(r["location"].lower() == "mumbai" and r["count"] >= 3
               for r in loc["locations"])
    made = await hr.create_holiday(db=db, current_user=None, obj_in=HolidayCalendarCreate(
        name=f"Hnone_{world['tag']}", date=D_NONE, location="Nowhere-land"))
    try:
        assert made.matching_employee_count == 0
        upd = await hr.update_holiday(
            db=db, current_user=SimpleNamespace(id=world["mum"]),
            holiday_id=made.id,
            obj_in=HolidayCalendarCreate(
                name=made.name, date=D_NONE, location=" mumbai "))
        assert upd.matching_employee_count >= 3
    finally:
        await db.delete(await db.get(HolidayCalendar, made.id))
        await db.commit()


# ---- single reader guard ----

ALLOW = {
    "services/holidays.py",
    "api/v1/endpoints/hr.py",   # holiday CRUD + GET /hr/holidays listing
    # optional-pick catalogue lookups (is_optional/date/location of the
    # holiday being picked/listed); pay/attendance decisions still go
    # through services.holidays
    "services/optional_holidays.py",
    "api/v1/endpoints/holidays.py",
}


def test_no_holidaycalendar_reads_outside_reader():
    app = Path(__file__).resolve().parents[1] / "app"
    offenders = []
    for f in app.rglob("*.py"):
        rel = f.relative_to(app).as_posix()
        if rel.startswith("models/") or rel.startswith("schemas/") or rel in ALLOW:
            continue
        txt = f.read_text()
        if "HolidayCalendar" in txt or "holidaycalendar" in txt.lower():
            offenders.append(rel)
    assert not offenders, f"read holidays via services.holidays instead: {offenders}"
