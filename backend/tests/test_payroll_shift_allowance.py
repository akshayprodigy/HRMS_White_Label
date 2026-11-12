"""Payroll parity + on-call/callback injection (Roadmap v2 Phase 2, Task 5).

Isolation: throwaway MONTHLY run (2018-04) scoped to one synthetic employee.
Everything created is removed in finally; time-rule settings are restored.
The PARITY golden below was captured on the code BEFORE the shift-allowance
change; a run with only OT + night entries must stay byte-identical."""
import json
import uuid
from datetime import date

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core.config import settings
from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.main import create_app
from app.models.audit import AuditLog
from app.models.employee import Employee
from app.models.overtime import NightAllowanceEntry, OvertimeEntry
from app.models.payroll import PayrollLine, PayrollRun, PayrollRunStatus
from app.models.shift_allowance import ShiftAllowanceEntry
from app.models.system import SystemSetting
from app.models.user import User
from app.services.time_rules import set_time_rules

BASE = f"{settings.API_V1_STR}/hr/payroll"
YEAR, MONTH = 2018, 4
K_ON = "attendance.absence_lop_enabled"
K_OFF = "attendance.default_weekly_offs"

LINE_FIELDS = ("base_salary", "payable_days", "lop_days", "gross_pay",
               "net_pay", "arrear", "incentive", "advance_deduction",
               "allowances", "deductions")

GOLDEN = json.loads('''{"advance_deduction": 0.0, "allowances": {"arrear": 0.0, "basic_salary_actual": 31000, "conveyance_actual": 9300, "conveyance_fixed": 9300.0, "effective_components_source": "employee_master", "hra_actual": 15500, "hra_fixed": 15500.0, "incentive": 0.0, "night_allowance": 150.5, "night_minutes": 900, "other_allowance_actual": 6200, "other_allowance_fixed": 6200.0, "overtime": 450.5, "overtime_minutes": 180, "revision_arrears": 0.0, "revision_arrears_detail": [], "total_fixed_earnings": 62000.0}, "arrear": 0.0, "base_salary": 31000.0, "deductions": {"advance_recovery": 0.0, "edli_charges": 75.0, "employee_esi": 0.0, "employee_pf": 1800.0, "employer_esic": 0.0, "employer_pf": 1800.0, "engine": "unified_v1", "epf_admin_charges": 75.0, "epf_wages": 15000.0, "esic_applicable": false, "esic_basis": "not_covered", "esic_covered": false, "guest_house": 0.0, "professional_tax": 200.0, "pt_state": "WEST BENGAL", "tds": 0.0, "tds_auto": 0.0, "tds_note": "no_tax_slab_config", "tds_regime": "new", "total_deductions": 2000.0, "total_employer_cost": 62551.0, "voluntary_pf": 0.0}, "gross_pay": 62601.0, "incentive": 0.0, "lop_days": 0.0, "net_pay": 60601.0, "payable_days": 30.0}''')


@pytest.fixture
async def client():
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _admin(client):
    r = await client.post(f"{settings.API_V1_STR}/auth/login",
                          data={"username": "admin@gmail.com",
                                "password": "test@12345"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


class Env:
    """Synthetic employee + payroll run harness with guaranteed cleanup."""

    def __init__(self, tag):
        self.tag = tag
        self.uid = self.eid = self.run_id = None
        self.original = {}

    async def setup(self, client, *, ot=True, night=True):
        async with SessionLocal() as db:
            for k in (K_ON, K_OFF):
                row = await db.get(SystemSetting, k)
                self.original[k] = row.value if row else None
            u = User(email=f"sa_{self.tag}@test.com", full_name="SA Test",
                     hashed_password=get_password_hash("x"), is_active=True)
            db.add(u)
            await db.flush()
            self.uid = u.id
            e = Employee(user_id=self.uid, employee_id=f"SA{self.tag}",
                         department="T", designation="T",
                         date_of_joining=date(2017, 1, 1), status="active",
                         salary=31000.0, location="HQ")
            db.add(e)
            await db.flush()
            self.eid = e.id
            if ot:
                db.add(OvertimeEntry(
                    user_id=self.uid, work_date=date(2018, 4, 10),
                    ot_minutes=120, ot_amount=300.0, status="approved"))
                db.add(OvertimeEntry(
                    user_id=self.uid, work_date=date(2018, 4, 11),
                    ot_minutes=60, ot_amount=150.5, status="auto_approved"))
            if night:
                db.add(NightAllowanceEntry(
                    user_id=self.uid, work_date=date(2018, 4, 12),
                    night_minutes=480, amount=75.25))
                db.add(NightAllowanceEntry(
                    user_id=self.uid, work_date=date(2018, 4, 13),
                    night_minutes=420, amount=75.25))
            await db.commit()
            await set_time_rules(db, {K_ON: "0", K_OFF: "6"})
        self.h = await _admin(client)
        r = await client.post(f"{BASE}/run", json={"month": MONTH, "year": YEAR},
                              headers=self.h)
        assert r.status_code == 200, r.text
        self.run_id = r.json()["id"]
        async with SessionLocal() as db:
            run = await db.get(PayrollRun, self.run_id)
            run.scope_user_ids = [self.uid]
            await db.commit()
        for step in ("lock-attendance", "lock-leaves"):
            r = await client.post(f"{BASE}/{self.run_id}/{step}", headers=self.h)
            assert r.status_code == 200, r.text

    async def generate(self, client, *, relock=False):
        if relock:
            async with SessionLocal() as db:
                run = await db.get(PayrollRun, self.run_id)
                run.status = PayrollRunStatus.LEAVES_LOCKED
                await db.commit()
        r = await client.post(f"{BASE}/{self.run_id}/generate-draft",
                              headers=self.h)
        assert r.status_code == 200, r.text
        return await self.line()

    async def line(self):
        async with SessionLocal() as db:
            ln = (await db.execute(select(PayrollLine).where(
                PayrollLine.payroll_run_id == self.run_id,
                PayrollLine.user_id == self.uid))).scalar_one()
            return {f: getattr(ln, f) for f in LINE_FIELDS} | {"id": ln.id}

    async def run_row(self):
        async with SessionLocal() as db:
            run = await db.get(PayrollRun, self.run_id)
            return run.total_gross, run.total_net

    async def cleanup(self):
        async with SessionLocal() as db:
            await db.rollback()
            if self.uid:
                for m in (OvertimeEntry, NightAllowanceEntry):
                    await db.execute(delete(m).where(m.user_id == self.uid))
                await db.execute(delete(ShiftAllowanceEntry).where(
                    ShiftAllowanceEntry.user_id == self.uid))
            if self.run_id:
                await db.execute(delete(PayrollLine).where(
                    PayrollLine.payroll_run_id == self.run_id))
                await db.execute(delete(AuditLog).where(
                    AuditLog.resource_type.in_(
                        ("payroll_run", "payroll_line")),
                    AuditLog.resource_id == str(self.run_id)))
                await db.execute(delete(PayrollRun).where(
                    PayrollRun.id == self.run_id))
            if self.uid:
                await db.execute(delete(PayrollLine).where(
                    PayrollLine.user_id == self.uid))
            if self.eid:
                await db.execute(delete(Employee).where(Employee.id == self.eid))
            if self.uid:
                await db.execute(delete(User).where(User.id == self.uid))
            for k, v in self.original.items():
                row = await db.get(SystemSetting, k)
                if v is None:
                    if row:
                        await db.delete(row)
                elif row:
                    row.value = v
                else:
                    db.add(SystemSetting(key=k, value=v))
            await db.commit()


def _snap(line):
    return {k: v for k, v in line.items() if k != "id"}


async def test_parity_ot_night_only_unchanged(client):
    env = Env(uuid.uuid4().hex[:8])
    try:
        await env.setup(client)
        line = await env.generate(client)
        snap = _snap(line)
        assert json.dumps(snap, sort_keys=True) == json.dumps(GOLDEN, sort_keys=True)
    finally:
        await env.cleanup()


def _sa(uid, d, kind, amount, minutes=0, run_id=None):
    return ShiftAllowanceEntry(
        user_id=uid, work_date=d, kind=kind, amount=amount, minutes=minutes,
        payroll_run_id=run_id)


async def _add(*rows):
    async with SessionLocal() as db:
        db.add_all(rows)
        await db.commit()


async def _entries(uid):
    async with SessionLocal() as db:
        return {(e.kind, e.work_date): (e.amount, e.payroll_run_id)
                for e in (await db.execute(select(ShiftAllowanceEntry).where(
                    ShiftAllowanceEntry.user_id == uid))).scalars().all()}


async def test_injection_stamping_regenerate_and_editor(client):
    env = Env(uuid.uuid4().hex[:8])
    try:
        # no OT/night here: generate_draft's pre-existing behaviour is that a
        # re-generate drops already-stamped OT/night, which would mask the
        # idempotency this test asserts for the new kinds.
        await env.setup(client, ot=False, night=False)
        other_id = None
        await _add(
            _sa(env.uid, date(2018, 4, 5), "on_call", 500.0, 1440),
            _sa(env.uid, date(2018, 4, 6), "on_call", 250.5, 720),
            _sa(env.uid, date(2018, 4, 20), "callback", 300.0, 90),
            # outside the month window -> never injected
            _sa(env.uid, date(2018, 5, 2), "on_call", 999.0, 60),
            # already stamped by some OTHER run -> never injected / touched
            _sa(env.uid, date(2018, 4, 25), "callback", 777.0, 30, run_id=None),
        )
        # stamp the 04-25 row with a foreign (existing) run id
        async with SessionLocal() as db:
            other = PayrollRun(month=3, year=2018, status=PayrollRunStatus.DRAFT)
            db.add(other)
            await db.flush()
            other_id = other.id
            e = (await db.execute(select(ShiftAllowanceEntry).where(
                ShiftAllowanceEntry.user_id == env.uid,
                ShiftAllowanceEntry.work_date == date(2018, 4, 25)))).scalar_one()
            e.payroll_run_id = other_id
            await db.commit()
        try:
            line = await env.generate(client)
            al = line["allowances"]
            assert al["on_call"] == 750.5 and al["on_call_minutes"] == 2160
            assert al["callback"] == 300.0 and al["callback_minutes"] == 90
            # existing keys untouched
            assert al["overtime"] == 0.0 and al["night_allowance"] == 0.0
            base = GOLDEN["gross_pay"] - 450.5 - 150.5
            assert line["gross_pay"] == base + 750.5 + 300.0
            ded = line["deductions"]
            assert line["net_pay"] == round(
                line["gross_pay"] - ded["total_deductions"], 2)
            # PT / statutory ran on the FULL gross (same engine as night)
            assert ded["engine"] == "unified_v1"
            ents = await _entries(env.uid)
            assert ents[("on_call", date(2018, 4, 5))][1] == env.run_id
            assert ents[("on_call", date(2018, 4, 6))][1] == env.run_id
            assert ents[("callback", date(2018, 4, 20))][1] == env.run_id
            assert ents[("on_call", date(2018, 5, 2))][1] is None
            assert ents[("callback", date(2018, 4, 25))] == (777.0, other_id)
            tg, tn = await env.run_row()
            assert tg == line["gross_pay"]

            # regenerate: same numbers, no double counting, nothing lost
            line2 = await env.generate(client, relock=True)
            assert _snap(line2) == _snap(line)
            assert (await env.run_row())[0] == line["gross_pay"]
            ents2 = await _entries(env.uid)
            assert ents2 == ents

            # line editor keeps on_call/callback in gross
            r = await client.patch(
                f"{BASE}/{env.run_id}/lines/{line2['id']}",
                json={"incentive": 100.0, "reason": "test"}, headers=env.h)
            assert r.status_code == 200, r.text
            after = await env.line()
            assert after["allowances"]["on_call"] == 750.5
            assert after["allowances"]["callback"] == 300.0
            assert after["gross_pay"] == pytest.approx(
                line["gross_pay"] + 100.0, abs=0.01)
        finally:
            async with SessionLocal() as db:
                await db.execute(delete(ShiftAllowanceEntry).where(
                    ShiftAllowanceEntry.user_id == env.uid))
                await db.execute(delete(PayrollRun).where(
                    PayrollRun.id == other_id))
                await db.commit()
    finally:
        await env.cleanup()
