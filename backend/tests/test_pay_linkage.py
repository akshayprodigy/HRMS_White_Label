"""Pay linkage (Roadmap v2 Phase 1B, Task 10): roster-aware OT day type,
week-off comp-off, nightly OT recompute.

Part 1 is a characterization (parity) test: a fixed synthetic dataset with
NO roster involvement must produce exactly the OT / night entries recorded in
tests/golden/pay_linkage_parity.json (captured before the change).
"""
import json
import os
import uuid
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from _cleanup import purge_shift_templates
from app.api import deps
from app.core.config import settings
from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.main import create_app
from app.models.approval import ApprovalItem, ApprovalStep
from app.models.attendance import Attendance
from app.models.audit import AuditLog
from app.models.comp_off import CompOffAccrual
from app.models.employee import Employee, EmployeeStatus
from app.models.hr import HolidayCalendar
from app.models.notification import Notification
from app.models.overtime import (
    NightAllowanceEntry, NightShiftAllowanceRule, OvertimeEntry, OvertimeRule,
)
from app.models.roster import RosterEntry, RosterEntryHistory, RosterStatus
from app.models.shift import EmployeeShiftAssignment, ShiftTemplate
from app.models.system import SystemSetting
from app.models.user import Role, User

PW = "test@12345"
UTC = timezone.utc
GOLDEN = Path(__file__).parent / "golden" / "pay_linkage_parity.json"
WEEKOFF_KEY = "attendance.weekoff_comp_off_enabled"

MON = date(2030, 6, 10)            # weekday 0
HOLIDAY = date(2030, 6, 12)        # Wed
SUN = date(2030, 6, 16)            # weekday 6 (template weekly off)
SAT = date(2030, 6, 15)            # weekday 5 (working day on templates)
PARITY_TAGS = ("wd", "wo", "hol", "ovn", "nos")
ALL_TAGS = PARITY_TAGS + ("rwo", "rchg", "cmp", "nsn")


def at(d, h, m=0):
    return datetime(d.year, d.month, d.day, h, m, tzinfo=UTC)


@pytest.fixture
async def client():
    app = create_app()
    app.dependency_overrides[deps.verify_attendance] = lambda: None
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as c:
        yield c


async def _login(client, email):
    r = await client.post(f"{settings.API_V1_STR}/auth/login",
                          data={"username": email, "password": PW})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
async def world():
    sfx = uuid.uuid4().hex[:8]
    async with SessionLocal() as db:
        prior = await db.get(SystemSetting, WEEKOFF_KEY)
        prior_val = (prior.value, prior.description) if prior else None
    try:
        async with SessionLocal() as db:
            def mk(tag, **kw):
                return User(email=f"pl_{tag}_{sfx}@t.com",
                            full_name=f"PL {tag} {sfx}",
                            hashed_password=get_password_hash(PW),
                            is_active=True, **kw)
            admin = mk("admin", is_superuser=True)
            us = {t: mk(t) for t in ALL_TAGS}
            db.add(admin)
            db.add_all(us.values())
            t_day = ShiftTemplate(name=f"PLD{sfx}", start_time=time(9),
                                  end_time=time(18), full_day_hours=8.0,
                                  weekly_offs=[6])
            t_night = ShiftTemplate(name=f"PLN{sfx}", start_time=time(22),
                                    end_time=time(6), is_overnight=True,
                                    full_day_hours=8.0, weekly_offs=[6])
            t_alt = ShiftTemplate(name=f"PLA{sfx}", start_time=time(9),
                                  end_time=time(15), full_day_hours=6.0,
                                  weekly_offs=[])
            db.add_all([t_day, t_night, t_alt])
            await db.flush()
            for t, u in us.items():
                db.add(Employee(user_id=u.id, employee_id=f"PL{sfx}{t}",
                                department="PLD", location="LocA",
                                designation="T", salary=26000.0,
                                date_of_joining=date(2020, 1, 1),
                                status=EmployeeStatus.ACTIVE))
            db.add_all([
                OvertimeRule(name=f"PLOT-org-{sfx}", scope="org_default",
                             requires_approval=True, is_active=True),
                OvertimeRule(name=f"PLOT-day-{sfx}", scope="shift",
                             shift_template_id=t_day.id, ot_rate_multiplier=1.5,
                             weekly_off_multiplier=2.0, holiday_multiplier=2.5,
                             requires_approval=False, is_active=True),
                OvertimeRule(name=f"PLOT-night-{sfx}", scope="shift",
                             shift_template_id=t_night.id,
                             ot_rate_multiplier=1.25, weekly_off_multiplier=1.75,
                             holiday_multiplier=2.25,
                             requires_approval=False, is_active=True),
                OvertimeRule(name=f"PLOT-alt-{sfx}", scope="shift",
                             shift_template_id=t_alt.id, ot_rate_multiplier=1.1,
                             weekly_off_multiplier=3.0, holiday_multiplier=3.5,
                             requires_approval=False, is_active=True),
                HolidayCalendar(name=f"PLH{sfx}", date=HOLIDAY, location="All"),
            ])
            await db.commit()
            for t in ("wd", "wo", "hol", "rwo", "cmp", "nsn"):
                db.add(EmployeeShiftAssignment(
                    employee_id=us[t].id, shift_template_id=t_day.id,
                    effective_from=date(2030, 1, 1)))
            db.add(EmployeeShiftAssignment(
                employee_id=us["ovn"].id, shift_template_id=t_night.id,
                effective_from=date(2030, 1, 1)))
            db.add(EmployeeShiftAssignment(
                employee_id=us["rchg"].id, shift_template_id=t_day.id,
                effective_from=date(2030, 1, 1)))
            await db.commit()
            ids = {t: u.id for t, u in us.items()}
            ids.update(admin=admin.id, t_day=t_day.id, t_night=t_night.id,
                       t_alt=t_alt.id)
        names = {v: k for k, v in ids.items()}
        yield {"ids": ids, "sfx": sfx, "names": names,
               "admin_email": f"pl_admin_{sfx}@t.com"}
    finally:
        async with SessionLocal() as db:
            uids = list((await db.execute(select(User.id).where(
                User.email.like(f"pl\\_%\\_{sfx}@t.com")))).scalars().all())
            items = (await db.execute(select(ApprovalItem.id).where(
                ApprovalItem.requested_by_id.in_(uids)))).scalars().all()
            if items:
                await db.execute(delete(ApprovalStep).where(
                    ApprovalStep.approval_item_id.in_(items)))
            rule_ids = (await db.execute(select(OvertimeRule.id).where(
                OvertimeRule.name.like(f"PLOT-%-{sfx}")))).scalars().all()
            await db.execute(delete(OvertimeEntry).where(
                OvertimeEntry.user_id.in_(uids)))
            if rule_ids:
                await db.execute(delete(OvertimeEntry).where(
                    OvertimeEntry.rule_id.in_(rule_ids)))
            await db.execute(delete(NightAllowanceEntry).where(
                NightAllowanceEntry.user_id.in_(uids)))
            await db.execute(delete(CompOffAccrual).where(
                CompOffAccrual.user_id.in_(uids)))
            if items:
                await db.execute(delete(ApprovalItem).where(
                    ApprovalItem.id.in_(items)))
            await db.execute(delete(Attendance).where(Attendance.user_id.in_(uids)))
            await db.execute(delete(RosterEntryHistory).where(
                RosterEntryHistory.employee_id.in_(uids)))
            await db.execute(delete(RosterEntry).where(
                RosterEntry.employee_id.in_(uids)))
            await db.execute(delete(Notification).where(
                Notification.user_id.in_(uids)))
            await db.execute(delete(Notification).where(
                Notification.message.like(f"%{sfx}%")))
            await db.execute(delete(AuditLog).where(AuditLog.user_id.in_(uids)))
            await db.execute(delete(EmployeeShiftAssignment).where(
                EmployeeShiftAssignment.employee_id.in_(uids)))
            await db.execute(delete(OvertimeRule).where(
                OvertimeRule.name.like(f"PLOT-%-{sfx}")))
            await db.execute(delete(NightShiftAllowanceRule).where(
                NightShiftAllowanceRule.name.like(f"PLNT-%-{sfx}")))
            await db.execute(delete(Employee).where(Employee.user_id.in_(uids)))
            tids = (await db.execute(select(ShiftTemplate.id).where(
                ShiftTemplate.name.like(f"PL_{sfx}")))).scalars().all()
            await purge_shift_templates(db, tids)
            await db.execute(delete(User).where(User.id.in_(uids)))
            await db.execute(delete(HolidayCalendar).where(
                HolidayCalendar.name == f"PLH{sfx}"))
            await db.execute(delete(SystemSetting).where(
                SystemSetting.key == WEEKOFF_KEY))
            if prior_val is not None:
                db.add(SystemSetting(key=WEEKOFF_KEY, value=prior_val[0],
                                     description=prior_val[1]))
            await db.commit()


async def _add_night_rule(w):
    async with SessionLocal() as db:
        db.add(NightShiftAllowanceRule(
            name=f"PLNT-org-{w['sfx']}", scope="org_default",
            payout_model="flat", flat_amount=200.0,
            night_window_start=time(22), night_window_end=time(6),
            min_night_minutes=60, is_active=True))
        await db.commit()


async def _punch(uid, work_date, tpl, pin, pout):
    async with SessionLocal() as db:
        a = Attendance(user_id=uid, mode="web", work_date=work_date,
                       shift_template_id=tpl, captured_at=pin,
                       punch_out_time=pout)
        db.add(a)
        await db.commit()
        return a.id


async def _snapshot(w, tags):
    """Normalised OT + night entries for the given user tags."""
    ids = [w["ids"][t] for t in tags]
    names = w["names"]
    rid_name = {}
    async with SessionLocal() as db:
        for r in (await db.execute(select(OvertimeRule))).scalars():
            rid_name[("ot", r.id)] = r.name.replace(f"-{w['sfx']}", "")
        for r in (await db.execute(select(NightShiftAllowanceRule))).scalars():
            rid_name[("nt", r.id)] = r.name.replace(f"-{w['sfx']}", "")
        ots = (await db.execute(select(OvertimeEntry).where(
            OvertimeEntry.user_id.in_(ids)))).scalars().all()
        nts = (await db.execute(select(NightAllowanceEntry).where(
            NightAllowanceEntry.user_id.in_(ids)))).scalars().all()
    out = {"ot": [], "night": []}
    for e in sorted(ots, key=lambda e: (names[e.user_id], e.work_date)):
        out["ot"].append({
            "user": names[e.user_id], "date": e.work_date.isoformat(),
            "shift": names.get(e.shift_template_id), "rule": rid_name[("ot", e.rule_id)],
            "ot_minutes": e.ot_minutes, "ot_amount": e.ot_amount,
            "hourly_rate_used": e.hourly_rate_used,
            "multiplier_used": e.multiplier_used, "day_type": e.day_type,
            "status": str(e.status),
        })
    for e in sorted(nts, key=lambda e: (names[e.user_id], e.work_date)):
        out["night"].append({
            "user": names[e.user_id], "date": e.work_date.isoformat(),
            "rule": rid_name[("nt", e.rule_id)],
            "night_minutes": e.night_minutes, "amount": e.amount,
            "payout_model_used": e.payout_model_used,
        })
    return out


async def _recompute(client, w, tags, start, end):
    h = await _login(client, w["admin_email"])
    r = await client.post(
        f"{settings.API_V1_STR}/overtime/recompute", headers=h,
        json={"start_date": start.isoformat(), "end_date": end.isoformat(),
              "user_ids": [w["ids"][t] for t in tags]})
    assert r.status_code == 200, r.text
    return r.json()


async def _seed_parity(w):
    i = w["ids"]
    # assignment-only weekday: 9:00-19:30 on Monday (2.5h beyond 8h -> OT)
    await _punch(i["wd"], MON, i["t_day"], at(MON, 9), at(MON, 19, 30))
    # assignment weekly-off (Sunday)
    await _punch(i["wo"], SUN, i["t_day"], at(SUN, 9), at(SUN, 19))
    # holiday
    await _punch(i["hol"], HOLIDAY, i["t_day"], at(HOLIDAY, 9), at(HOLIDAY, 20))
    # overnight: 22:00 -> 07:30 next day (night allowance + OT)
    await _punch(i["ovn"], MON, i["t_night"], at(MON, 22),
                 at(MON + timedelta(days=1), 7, 30))
    # no shift snapshot
    await _punch(i["nos"], MON, None, at(MON, 9), at(MON, 20))


async def test_parity_golden(world, client):
    await _seed_parity(world)
    res = await _recompute(client, world, PARITY_TAGS, MON, SUN)
    snap = await _snapshot(world, PARITY_TAGS)
    snap["response"] = res
    # second recompute is a no-op on values
    await _recompute(client, world, PARITY_TAGS, MON, SUN)
    assert await _snapshot(world, PARITY_TAGS) == {
        k: v for k, v in snap.items() if k != "response"}
    if os.environ.get("UPDATE_GOLDEN"):
        GOLDEN.write_text(json.dumps(snap, indent=2, sort_keys=True) + "\n")
    assert json.loads(json.dumps(snap)) == json.loads(GOLDEN.read_text())


# ---------------- new behaviour ----------------


async def _roster(uid, d, *, tpl=None, week_off=False):
    async with SessionLocal() as db:
        db.add(RosterEntry(employee_id=uid, work_date=d, shift_template_id=tpl,
                           is_week_off=week_off, status=RosterStatus.PUBLISHED))
        await db.commit()


async def test_rostered_week_off_uses_weekly_off_multiplier(world, client):
    i = world["ids"]
    # SAT is a working day on the template; the published roster makes it off.
    await _roster(i["rwo"], SAT, week_off=True)
    await _punch(i["rwo"], SAT, i["t_day"], at(SAT, 9), at(SAT, 19))
    await _recompute(client, world, ("rwo",), SAT, SAT)
    ot = (await _snapshot(world, ("rwo",)))["ot"]
    assert len(ot) == 1
    assert ot[0]["day_type"] == "weekly_off"
    assert ot[0]["multiplier_used"] == 2.0
    assert ot[0]["ot_minutes"] == 60 and ot[0]["rule"] == "PLOT-day"


async def test_without_roster_same_day_is_weekday(world, client):
    i = world["ids"]
    await _punch(i["rwo"], SAT, i["t_day"], at(SAT, 9), at(SAT, 19))
    await _recompute(client, world, ("rwo",), SAT, SAT)
    ot = (await _snapshot(world, ("rwo",)))["ot"]
    assert ot[0]["day_type"] == "weekday" and ot[0]["multiplier_used"] == 1.5


async def test_roster_shift_changed_after_punch_is_baseline(world, client):
    i = world["ids"]
    await _punch(i["rchg"], MON, i["t_day"], at(MON, 9), at(MON, 18))  # net 8h
    await _recompute(client, world, ("rchg",), MON, MON)
    assert (await _snapshot(world, ("rchg",)))["ot"] == []  # 8h vs 8h baseline
    # Roster published afterwards moves them to the 6h shift.
    await _roster(i["rchg"], MON, tpl=i["t_alt"])
    res = await _recompute(client, world, ("rchg",), MON, MON)
    assert res["ot_entries_created"] == 1
    ot = (await _snapshot(world, ("rchg",)))["ot"]
    assert ot[0]["shift"] == "t_alt" and ot[0]["rule"] == "PLOT-alt"
    assert ot[0]["ot_minutes"] == 120 and ot[0]["multiplier_used"] == 1.1


async def test_night_allowance_with_rule_and_naive_db_datetimes(world, client):
    await _add_night_rule(world)
    i = world["ids"]
    await _punch(i["ovn"], MON, i["t_night"], at(MON, 22),
                 at(MON + timedelta(days=1), 7, 30))
    await _recompute(client, world, ("ovn",), MON, MON)
    nt = (await _snapshot(world, ("ovn",)))["night"]
    assert len(nt) == 1 and nt[0]["night_minutes"] == 480
    assert nt[0]["amount"] == 200.0 and nt[0]["rule"] == "PLNT-org"


async def test_nightly_job_processes_lookback_window_only(world):
    from app.services.scheduler import REGISTRY
    spec = REGISTRY["overtime_recompute_yesterday"]
    assert spec.default_cadence_cron == "30 1 * * *"
    i = world["ids"]
    today = datetime.now(UTC).date()
    yday, d2 = today - timedelta(days=1), today - timedelta(days=5)
    async with SessionLocal() as db:  # keep the job off real data
        for r in (await db.execute(select(OvertimeRule).where(
                OvertimeRule.name == f"PLOT-org-{world['sfx']}"))).scalars():
            r.is_active = False
        await db.commit()
    await _punch(i["wd"], yday, i["t_day"], at(yday, 9), at(yday, 19, 30))
    await _punch(i["wo"], d2, i["t_day"], at(d2, 9), at(d2, 19, 30))
    await _punch(i["hol"], yday, i["t_day"], at(yday, 9), None)  # still open
    async with SessionLocal() as db:
        res = await spec.fn(db)
    assert res["work_date"] == yday.isoformat()
    async with SessionLocal() as db:
        rows = (await db.execute(select(OvertimeEntry).where(
            OvertimeEntry.user_id.in_([i["wd"], i["wo"], i["hol"]])
        ))).scalars().all()
    got = {(world["names"][r.user_id], r.work_date) for r in rows}
    assert got == {("wd", yday)}


async def _comp_off(uid, d, pin, pout):
    from app.api.v1.endpoints.attendance import _maybe_create_comp_off_accrual
    async with SessionLocal() as db:
        user = await db.get(User, uid)
        att = (await db.execute(select(Attendance).where(
            Attendance.user_id == uid, Attendance.work_date == d))).scalar_one()
        acc = await _maybe_create_comp_off_accrual(
            db, user=user, attendance=att, punch_in=pin, punch_out=pout)
        await db.commit()
        return None if acc is None else (acc.holiday_name, acc.holiday_date)


async def _set_weekoff(value):
    async with SessionLocal() as db:
        row = await db.get(SystemSetting, WEEKOFF_KEY)
        if row:
            row.value = value
        else:
            db.add(SystemSetting(key=WEEKOFF_KEY, value=value, description="t"))
        await db.commit()


async def test_weekoff_comp_off_enabled_vs_disabled(world):
    i = world["ids"]
    await _punch(i["cmp"], SUN, i["t_day"], at(SUN, 9), at(SUN, 17))
    await _set_weekoff("0")
    assert await _comp_off(i["cmp"], SUN, at(SUN, 9), at(SUN, 17)) is None
    await _set_weekoff("1")
    assert await _comp_off(i["cmp"], SUN, at(SUN, 9), at(SUN, 17)) == (
        "Week-off work", SUN)
    # idempotent
    assert await _comp_off(i["cmp"], SUN, at(SUN, 9), at(SUN, 17)) is None


async def test_weekoff_comp_off_roster_week_off_and_threshold(world):
    i = world["ids"]
    await _set_weekoff("1")
    await _roster(i["cmp"], SAT, week_off=True)
    await _punch(i["cmp"], SAT, i["t_day"], at(SAT, 9), at(SAT, 12))
    assert await _comp_off(i["cmp"], SAT, at(SAT, 9), at(SAT, 12)) is None  # < 6.5h
    # a normal working day never accrues
    await _punch(i["cmp"], MON, i["t_day"], at(MON, 9), at(MON, 18))
    assert await _comp_off(i["cmp"], MON, at(MON, 9), at(MON, 18)) is None


async def test_holiday_comp_off_path_unchanged(world):
    i = world["ids"]
    await _set_weekoff("0")  # rule off: holiday still accrues
    await _punch(i["cmp"], HOLIDAY, i["t_day"], at(HOLIDAY, 9), at(HOLIDAY, 17))
    got = await _comp_off(i["cmp"], HOLIDAY, at(HOLIDAY, 9), at(HOLIDAY, 17))
    assert got == (f"PLH{world['sfx']}", HOLIDAY)


async def test_weekoff_rule_validation_and_default(world):
    from app.services.time_rules import (
        TIME_RULE_DEFAULTS, get_time_rules, set_time_rules,
    )
    assert TIME_RULE_DEFAULTS[WEEKOFF_KEY][0] == "0"
    async with SessionLocal() as db:
        with pytest.raises(ValueError):
            await set_time_rules(db, {WEEKOFF_KEY: "yes"})
        out = await set_time_rules(db, {WEEKOFF_KEY: " 1 "})
        assert out[WEEKOFF_KEY] == "1"
        assert (await get_time_rules(db))[WEEKOFF_KEY] == "1"


async def _deactivate_org_rule(w):
    async with SessionLocal() as db:  # keep the job off real data
        for r in (await db.execute(select(OvertimeRule).where(
                OvertimeRule.name == f"PLOT-org-{w['sfx']}"))).scalars():
            r.is_active = False
        await db.commit()


async def _entries(w, tag):
    async with SessionLocal() as db:
        return (await db.execute(select(OvertimeEntry).where(
            OvertimeEntry.user_id == w["ids"][tag]))).scalars().all()


async def test_assignment_present_snapshot_null_keeps_legacy_numbers(world, client):
    """I1: no roster -> the baseline is the snapshot only (None stays None),
    exactly like a no-assignment employee: org rule, fallback hours."""
    i = world["ids"]
    await _punch(i["nsn"], MON, None, at(MON, 9), at(MON, 20))
    await _recompute(client, world, ("nsn",), MON, MON)
    got = (await _snapshot(world, ("nsn",)))["ot"]
    gold = [e for e in json.loads(GOLDEN.read_text())["ot"] if e["user"] == "nos"]
    assert len(got) == 1 and len(gold) == 1
    got[0]["user"] = "nos"
    assert got == gold


async def test_nightly_job_retries_punch_opened_on_earlier_night(world):
    from app.services.scheduler import REGISTRY
    fn = REGISTRY["overtime_recompute_yesterday"].fn
    i = world["ids"]
    await _deactivate_org_rule(world)
    d1 = datetime.now(UTC).date() - timedelta(days=2)
    aid = await _punch(i["wd"], d1, i["t_day"], at(d1, 9), None)
    async with SessionLocal() as db:
        await fn(db)
    assert await _entries(world, "wd") == []
    async with SessionLocal() as db:
        a = await db.get(Attendance, aid)
        a.punch_out_time = at(d1, 19, 30)
        await db.commit()
    async with SessionLocal() as db:
        r1 = await fn(db)
    ents = await _entries(world, "wd")
    assert len(ents) == 1 and ents[0].ot_minutes == 90
    async with SessionLocal() as db:  # idempotent
        r2 = await fn(db)
    assert r2["ot_created"] == 0 and len(await _entries(world, "wd")) == 1


async def _lock_entries(tag, w, year):
    from app.models.payroll import PayrollRun
    async with SessionLocal() as db:
        run = PayrollRun(month=1, year=year)
        db.add(run)
        await db.flush()
        for e in (await db.execute(select(OvertimeEntry).where(
                OvertimeEntry.user_id == w["ids"][tag]))).scalars():
            e.payroll_run_id = run.id
        await db.commit()
        return run.id


async def test_payroll_locked_entry_untouched_by_recompute_and_job(world):
    from app.api.v1.endpoints.overtime import recompute_range
    from app.models.payroll import PayrollRun
    from app.services.scheduler import REGISTRY
    fn = REGISTRY["overtime_recompute_yesterday"].fn
    i = world["ids"]
    await _deactivate_org_rule(world)
    yday = datetime.now(UTC).date() - timedelta(days=1)
    run_ids = []
    try:
        for tag, d in (("wd", MON), ("wo", yday)):
            await _punch(i[tag], d, i["t_day"], at(d, 9), at(d, 19, 30))
            async with SessionLocal() as db:
                if d == yday:
                    await fn(db)
                else:
                    await recompute_range(db, d, d, [i[tag]], i["admin"])
                    await db.commit()
            before = [(e.ot_minutes, e.ot_amount, e.day_type, e.rule_id)
                      for e in await _entries(world, tag)]
            assert len(before) == 1
            run_ids.append(await _lock_entries(tag, world, 2031 + len(run_ids)))
            # roster change after lock: published week-off + shorter shift
            await _roster(i[tag], d, week_off=True)
            async with SessionLocal() as db:
                if d == yday:
                    await fn(db)
                    res = None
                else:
                    res = await recompute_range(db, d, d, [i[tag]], i["admin"])
                    await db.commit()
            after = [(e.ot_minutes, e.ot_amount, e.day_type, e.rule_id)
                     for e in await _entries(world, tag)]
            assert after == before
            if res is not None:
                assert res["ot_skipped_finalized"] == 1
                assert res["ot_updated"] == 0
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(OvertimeEntry).where(
                OvertimeEntry.user_id.in_([i["wd"], i["wo"]])))
            if run_ids:
                await db.execute(delete(PayrollRun).where(
                    PayrollRun.id.in_(run_ids)))
            await db.commit()


async def test_pending_ot_approver_job_vs_manual(world, client):
    from app.api.v1.endpoints.overtime import recompute_range
    i = world["ids"]
    await _punch(i["nos"], MON, None, at(MON, 9), at(MON, 20))  # org rule: pending
    async with SessionLocal() as db:
        await recompute_range(db, MON, MON, [i["nos"]], None)  # job-style
        await db.commit()
    async with SessionLocal() as db:
        hr = (await db.execute(select(Role.id).where(Role.name == "HR"))).scalar_one()
        e = (await db.execute(select(OvertimeEntry).where(
            OvertimeEntry.user_id == i["nos"]))).scalar_one()
        st = (await db.execute(select(ApprovalStep).where(
            ApprovalStep.approval_item_id == e.approval_item_id))).scalar_one()
        assert st.role_id == hr and st.approver_id is None
        # reset and take the manual endpoint path
        iid = e.approval_item_id
        await db.execute(delete(ApprovalStep).where(
            ApprovalStep.approval_item_id == iid))
        e.approval_item_id = None
        await db.flush()
        await db.execute(delete(ApprovalItem).where(ApprovalItem.id == iid))
        await db.commit()
    await _recompute(client, world, ("nos",), MON, MON)
    async with SessionLocal() as db:
        e = (await db.execute(select(OvertimeEntry).where(
            OvertimeEntry.user_id == i["nos"]))).scalar_one()
        st = (await db.execute(select(ApprovalStep).where(
            ApprovalStep.approval_item_id == e.approval_item_id))).scalar_one()
        assert st.approver_id == i["admin"] and st.role_id is None
