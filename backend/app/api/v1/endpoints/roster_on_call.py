"""On-call / standby roster (Roadmap v2 Phase 2, Task 5).

  /roster/on-call/rules   CRUD, roster admin only (GET: any roster manager)
  /roster/on-call         list / create / update / delete for employees the
                          caller may manage (manageable_subset)
  /roster/my/on-call      the caller's own upcoming on-call days

Each assignment owns a shift_allowance_entry(kind='on_call') that payroll
injects. Once that entry is stamped (paid) the assignment is frozen: update
and delete answer 409 "already paid" (decision: refuse rather than orphan a
paid allowance). Creating/changing a day in the past is limited to the last
7 days for managers; roster admins may go further back; any past day in a
month whose payroll run has locked attendance is refused.
"""
from datetime import date as pydate, datetime, time as dtime, timedelta, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from app.services.org_time import local_today
from app.api import deps
from app.api.v1.endpoints.roster_common import (
    check_window, commit_or_409, guard_conflicts, lock_row, lock_user_rows,
    names, require_admin,
)
from app.models.employee import Employee
from app.models.on_call import OnCallAssignment, OnCallPayout, OnCallRule
from app.models.shift_allowance import ShiftAllowanceEntry, ShiftAllowanceKind
from app.models.user import User
from app.schemas.roster import IntId
from app.services import on_call as oc
from app.services import roster as roster_svc
from app.services.attendance_lock import assert_attendance_editable

router = APIRouter()
BACKDATE_DAYS = 7
MAX_LIST = 2000


# ------------------------------- schemas -------------------------------

class RuleIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    payout_model: str = OnCallPayout.FLAT_PER_DAY
    flat_amount: float = Field(default=0.0, ge=0, le=10_000_000)
    hourly_rate: float = Field(default=0.0, ge=0, le=10_000_000)
    is_active: bool = True

    @field_validator("name")
    @classmethod
    def _n(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("name required")
        return v

    @field_validator("payout_model")
    @classmethod
    def _p(cls, v):
        if v not in OnCallPayout.ALL:
            raise ValueError("payout_model must be flat_per_day or hourly")
        return v


class RulePatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    payout_model: Optional[str] = None
    flat_amount: Optional[float] = Field(default=None, ge=0, le=10_000_000)
    hourly_rate: Optional[float] = Field(default=None, ge=0, le=10_000_000)
    is_active: Optional[bool] = None

    @field_validator("payout_model")
    @classmethod
    def _p(cls, v):
        if v is not None and v not in OnCallPayout.ALL:
            raise ValueError("payout_model must be flat_per_day or hourly")
        return v


class AssignIn(BaseModel):
    user_id: IntId
    work_date: pydate
    start_time: dtime
    end_time: dtime
    rule_id: IntId
    note: Optional[str] = Field(default=None, max_length=255)

    @field_validator("note")
    @classmethod
    def _blank(cls, v):
        return (v or "").strip() or None


class AssignPatch(BaseModel):
    start_time: Optional[dtime] = None
    end_time: Optional[dtime] = None
    rule_id: Optional[IntId] = None
    note: Optional[str] = Field(default=None, max_length=255)


# ------------------------------- helpers -------------------------------

def _rule_out(r: OnCallRule) -> dict:
    return {"id": r.id, "name": r.name, "payout_model": r.payout_model,
            "flat_amount": r.flat_amount, "hourly_rate": r.hourly_rate,
            "is_active": r.is_active}


def _check_rule_rates(model: str, flat: float, hourly: float) -> None:
    if model == OnCallPayout.FLAT_PER_DAY and flat <= 0:
        raise HTTPException(400, "A flat-per-day rule needs flat_amount > 0")
    if model == OnCallPayout.HOURLY and hourly <= 0:
        raise HTTPException(400, "An hourly rule needs hourly_rate > 0")


def _hhmm(t: dtime) -> str:
    return t.strftime("%H:%M")


async def _out_many(db, rows: List[OnCallAssignment]) -> List[dict]:
    if not rows:
        return []
    nm = await names(db, {r.user_id for r in rows})
    rules = {r.id: r for r in (await db.execute(select(OnCallRule).where(
        OnCallRule.id.in_({r.rule_id for r in rows})))).scalars().all()}
    ents = {(e.user_id, e.work_date): e for e in (await db.execute(
        select(ShiftAllowanceEntry).where(
            ShiftAllowanceEntry.user_id.in_({r.user_id for r in rows}),
            ShiftAllowanceEntry.work_date.in_({r.work_date for r in rows}),
            ShiftAllowanceEntry.kind == ShiftAllowanceKind.ON_CALL,
        ))).scalars().all()}
    out = []
    for r in rows:
        rule = rules.get(r.rule_id)
        e = ents.get((r.user_id, r.work_date))
        out.append({
            "id": r.id, "user_id": r.user_id, "user_name": nm.get(r.user_id),
            "work_date": r.work_date.isoformat(),
            "start_time": _hhmm(r.start_time), "end_time": _hhmm(r.end_time),
            "is_overnight": r.is_overnight,
            "rule_id": r.rule_id, "rule_name": rule.name if rule else None,
            "amount": e.amount if e else None,
            "paid": bool(e and e.payroll_run_id is not None),
            "note": r.note,
        })
    return out


async def _check_date(db, actor: User, d: pydate) -> None:
    """Past-date policy (see module docstring)."""
    today = await local_today(db)
    if d >= today:
        return
    if d < today - timedelta(days=BACKDATE_DAYS) \
            and not roster_svc.is_roster_admin(actor):
        raise HTTPException(
            400, f"Only HR/admin can change on-call more than "
                 f"{BACKDATE_DAYS} days in the past.")
    await assert_attendance_editable(db, d)


def _validate_times(start: dtime, end: dtime, rule=None) -> None:
    if start.second or end.second or start.microsecond or end.microsecond:
        raise HTTPException(422, "Times must be HH:MM")
    if (rule is not None and rule.payout_model == OnCallPayout.HOURLY
            and start == end):
        raise HTTPException(
            400, "An hourly rule needs an end time different from the start "
                 "(equal times mean 24h and are only allowed for flat rules).")


async def _require_manage(db, actor: User, uid: int) -> None:
    if not await roster_svc.can_manage_employee(db, actor, uid):
        raise HTTPException(403, "This employee is outside your roster scope.")


async def _get_assignment(db, aid: int, lock: bool = False) -> OnCallAssignment:
    q = select(OnCallAssignment).where(OnCallAssignment.id == aid)
    a = await lock_row(db, q) if lock else (
        await db.execute(q)).scalars().first()
    if a is None:
        raise HTTPException(404, "On-call assignment not found")
    return a


# ------------------------------- rules ---------------------------------

@router.get("/on-call/rules")
async def list_rules(
    db: deps.DBDep, current_user: User = Depends(deps.get_current_user),
) -> Any:
    if not roster_svc.is_roster_admin(current_user):
        scoped = await roster_svc.scoped_employees(db, current_user)
        if not scoped:
            raise HTTPException(403, "You have no roster scope.")
    rows = (await db.execute(
        select(OnCallRule).order_by(OnCallRule.name))).scalars().all()
    return [_rule_out(r) for r in rows]


@router.post("/on-call/rules")
@guard_conflicts
async def create_rule(
    body: RuleIn, *, db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    require_admin(current_user)
    _check_rule_rates(body.payout_model, body.flat_amount, body.hourly_rate)
    r = OnCallRule(**body.model_dump())
    db.add(r)
    await commit_or_409(db, "An on-call rule with this name already exists")
    await db.refresh(r)
    return _rule_out(r)


@router.patch("/on-call/rules/{rule_id}")
@guard_conflicts
async def update_rule(
    rule_id: IntId, body: RulePatch, *, db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    require_admin(current_user)
    r = await lock_row(db, select(OnCallRule).where(OnCallRule.id == rule_id))
    if r is None:
        raise HTTPException(404, "On-call rule not found")
    data = body.model_dump(exclude_unset=True)
    for k in ("name", "payout_model", "flat_amount", "hourly_rate",
              "is_active"):
        if k in data and data[k] is None:
            data.pop(k)
    if "name" in data:
        data["name"] = data["name"].strip()
        if not data["name"]:
            raise HTTPException(422, "name required")
    for k, v in data.items():
        setattr(r, k, v)
    _check_rule_rates(r.payout_model, r.flat_amount, r.hourly_rate)
    await db.flush()
    refreshed = 0
    if {"payout_model", "flat_amount", "hourly_rate"} & set(data):
        refreshed = await oc.resync_rule(db, r)
    await commit_or_409(db, "An on-call rule with this name already exists")
    return {**_rule_out(r), "entries_refreshed": refreshed}


@router.delete("/on-call/rules/{rule_id}")
@guard_conflicts
async def delete_rule(
    rule_id: IntId, *, db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    require_admin(current_user)
    r = await lock_row(db, select(OnCallRule).where(OnCallRule.id == rule_id))
    if r is None:
        raise HTTPException(404, "On-call rule not found")
    used = (await db.execute(select(OnCallAssignment.id).where(
        OnCallAssignment.rule_id == rule_id).limit(1))).first()
    if used is not None:
        raise HTTPException(
            409, "Rule is used by on-call assignments; deactivate it instead.")
    await db.delete(r)
    await commit_or_409(db)
    return {"ok": True}


# --------------------------- assignments -------------------------------

@router.get("/on-call")
async def list_on_call(
    db: deps.DBDep,
    start: pydate = Query(...), end: pydate = Query(...),
    department: Optional[str] = None,
    user_id: Optional[IntId] = None,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    check_window(start, end)
    scoped = await roster_svc.scoped_employees(db, current_user)
    if not scoped and not roster_svc.is_roster_admin(current_user):
        raise HTTPException(403, "You have no roster scope.")
    if department:
        scoped = [e for e in scoped if e.department == department]
    ids = await roster_svc.manageable_subset(
        db, current_user, {e.user_id for e in scoped})
    if user_id is not None:
        ids = ids & {user_id}
    if not ids:
        return []
    rows = (await db.execute(
        select(OnCallAssignment).where(
            OnCallAssignment.user_id.in_(ids),
            OnCallAssignment.work_date >= start,
            OnCallAssignment.work_date <= end)
        .order_by(OnCallAssignment.work_date, OnCallAssignment.user_id)
        .limit(MAX_LIST))).scalars().all()
    return await _out_many(db, list(rows))


@router.post("/on-call")
@guard_conflicts
async def create_on_call(
    body: AssignIn, *, db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    _validate_times(body.start_time, body.end_time)
    await _require_manage(db, current_user, body.user_id)
    emp = (await db.execute(select(Employee).where(
        Employee.user_id == body.user_id))).scalars().first()
    if emp is None or emp.status != "active":
        raise HTTPException(400, "Employee not found or not active")
    await _check_date(db, current_user, body.work_date)
    rule = await lock_row(db, select(OnCallRule).where(
        OnCallRule.id == body.rule_id))
    if rule is None or not rule.is_active:
        raise HTTPException(400, "On-call rule not found or inactive")
    _validate_times(body.start_time, body.end_time, rule)
    await lock_user_rows(db, [body.user_id])
    dup = await lock_row(db, select(OnCallAssignment).where(
        OnCallAssignment.user_id == body.user_id,
        OnCallAssignment.work_date == body.work_date))
    if dup is not None:
        raise HTTPException(409, "Employee is already on call that day.")
    a = OnCallAssignment(
        user_id=body.user_id, work_date=body.work_date,
        start_time=body.start_time, end_time=body.end_time,
        is_overnight=oc.is_overnight(body.start_time, body.end_time),
        rule_id=rule.id, note=body.note, created_by_id=current_user.id)
    db.add(a)
    await db.flush()
    try:
        await oc.sync_entry(db, a, rule)
    except oc.StampedEntry:
        # A paid entry with no assignment (e.g. assignment deleted before
        # payroll in an older flow) — never overwrite it.
        raise HTTPException(409, oc.ALREADY_PAID)
    await roster_svc.notify(
        db, a.user_id, "On-call duty assigned",
        f"You are on call on {a.work_date.isoformat()} "
        f"({_hhmm(a.start_time)}-{_hhmm(a.end_time)}).",
        "roster", None)
    await commit_or_409(db, "Employee is already on call that day.")
    await db.refresh(a)
    return (await _out_many(db, [a]))[0]


@router.patch("/on-call/{assignment_id}")
@guard_conflicts
async def update_on_call(
    assignment_id: IntId, body: AssignPatch, *, db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    a = await _get_assignment(db, assignment_id)
    await _require_manage(db, current_user, a.user_id)
    await lock_user_rows(db, [a.user_id])
    a = await _get_assignment(db, assignment_id, lock=True)
    await _check_date(db, current_user, a.work_date)
    data = body.model_dump(exclude_unset=True)
    start = data.get("start_time") or a.start_time
    end = data.get("end_time") or a.end_time
    _validate_times(start, end)
    rule = await lock_row(db, select(OnCallRule).where(
        OnCallRule.id == (data.get("rule_id") or a.rule_id)))
    if rule is None or (not rule.is_active and rule.id != a.rule_id):
        raise HTTPException(400, "On-call rule not found or inactive")
    _validate_times(start, end, rule)
    a.start_time, a.end_time = start, end
    a.is_overnight = oc.is_overnight(start, end)
    a.rule_id = rule.id
    if "note" in data:
        a.note = (data["note"] or "").strip() or None
    await db.flush()
    try:
        await oc.sync_entry(db, a, rule)
    except oc.StampedEntry:
        await db.rollback()
        raise HTTPException(409, oc.ALREADY_PAID)
    await commit_or_409(db)
    await db.refresh(a)
    return (await _out_many(db, [a]))[0]


@router.delete("/on-call/{assignment_id}")
@guard_conflicts
async def delete_on_call(
    assignment_id: IntId, *, db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    a = await _get_assignment(db, assignment_id)
    await _require_manage(db, current_user, a.user_id)
    await lock_user_rows(db, [a.user_id])
    a = await _get_assignment(db, assignment_id, lock=True)
    uid, d = a.user_id, a.work_date
    try:
        await oc.delete_entry(db, uid, d)
    except oc.StampedEntry:
        await db.rollback()
        raise HTTPException(409, oc.ALREADY_PAID)
    await db.delete(a)
    await roster_svc.notify(
        db, uid, "On-call duty removed",
        f"Your on-call duty on {d.isoformat()} was removed.", "roster", None)
    await commit_or_409(db)
    return {"ok": True}


@router.get("/my/on-call")
async def my_on_call(
    db: deps.DBDep,
    start: Optional[pydate] = None, end: Optional[pydate] = None,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """The caller's on-call days (default: today .. today+30)."""
    s = start or await local_today(db)
    e = end or (s + timedelta(days=30))
    check_window(s, e)
    rows = (await db.execute(
        select(OnCallAssignment).where(
            OnCallAssignment.user_id == current_user.id,
            OnCallAssignment.work_date >= s, OnCallAssignment.work_date <= e)
        .order_by(OnCallAssignment.work_date))).scalars().all()
    out = await _out_many(db, list(rows))
    for o in out:  # own days: no user fields (amount stays visible)
        o.pop("user_id", None)
        o.pop("user_name", None)
    return out
