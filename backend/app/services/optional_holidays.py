"""Optional-holiday picks (Phase 6A Task 6). An employee picks up to
`holidays.optional_quota_per_year` optional holidays per calendar year; an
APPROVED pick makes the holiday count for that user (holidays.holidays_for).

Services never commit; the endpoint commits once (commit_or_409). Errors are
HTTPException (message is safe to show)."""
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select

from app.models.approval_chain import (
    ChainEntityType, ChainedApprovalInstance, ChainedApprovalStatus,
)
from app.models.audit import AuditLog
from app.models.employee import Employee
from app.models.hr import HolidayCalendar
from app.models.optional_holiday import OptionalHolidayPick, PickStatus
from app.models.user import User
from app.services import holidays as holidays_svc
from app.services import roster as roster_svc
from app.services.attendance_lock import LockRetry
from app.services.chain_routing import assert_dates_unlocked, close_instance
from app.services.org_time import local_today
from app.services.time_rules import get_time_rules

QUOTA_KEY = "holidays.optional_quota_per_year"
RT = "optional_holiday"


async def quota(db) -> int:
    try:
        v = int(str((await get_time_rules(db)).get(QUOTA_KEY, "2")).strip())
    except (TypeError, ValueError):
        return 2
    return v if 0 <= v <= 20 else 2


async def user_location(db, user_id: int) -> str:
    row = (await db.execute(
        select(Employee.location, User.location)
        .select_from(User).outerjoin(Employee, Employee.user_id == User.id)
        .where(User.id == user_id))).first()
    dflt = await holidays_svc.default_location(db)
    if row is None:
        return dflt
    return holidays_svc.effective_location(row[0], row[1], dflt)


async def holiday_of(db, pick: OptionalHolidayPick):
    return await db.get(HolidayCalendar, pick.holiday_id)


async def used(db, user_id: int, year: int, *, lock: bool = False) -> int:
    q = select(OptionalHolidayPick.id).where(
        OptionalHolidayPick.user_id == user_id,
        OptionalHolidayPick.year == year,
        OptionalHolidayPick.status.in_(PickStatus.ACTIVE))
    if lock:
        q = q.with_for_update()
    return len((await db.execute(q)).all())


async def create_pick(db, *, user, holiday_id: int, reason) -> OptionalHolidayPick:
    """The CALLER must hold the user-row lock (taken at the start of a fresh
    transaction, before any consistent read) so the plain, user-scoped
    duplicate/quota read below is race-free without locking other users'
    pick rows."""
    uid = user.id
    hol = await db.get(HolidayCalendar, holiday_id)
    if hol is None:
        raise HTTPException(404, "Holiday not found")
    if not hol.is_optional:
        raise HTTPException(422, "not an optional holiday")
    if not holidays_svc.applies(hol.location, await user_location(db, uid)):
        raise HTTPException(422, "This holiday is not available for your location")
    if hol.date < await local_today(db):
        raise HTTPException(422, "date has passed")
    ids = [r[0] for r in (await db.execute(
        select(OptionalHolidayPick.holiday_id).where(
            OptionalHolidayPick.user_id == uid,
            OptionalHolidayPick.year == hol.date.year,
            OptionalHolidayPick.status.in_(PickStatus.ACTIVE)))).all()]
    if hol.id in ids:
        raise HTTPException(409, "You already picked this holiday")
    q = await quota(db)
    if len(ids) >= q:
        raise HTTPException(409, f"optional holiday quota ({q}) used")
    pick = OptionalHolidayPick(
        holiday_id=hol.id, user_id=uid, year=hol.date.year,
        status=PickStatus.PENDING,
        reason=(reason or "").strip() or None)
    db.add(pick)
    await db.flush()
    return pick


def audit_create(db, actor_id, pick, routed_via: str) -> None:
    _audit(db, actor_id, "OPTIONAL_HOLIDAY_CREATE", pick, {
        "holiday_id": pick.holiday_id, "year": pick.year,
        "routed_via": routed_via})


def _audit(db, actor_id, action, pick, details) -> None:
    db.add(AuditLog(user_id=actor_id, action=action, resource_type=RT,
                    resource_id=str(pick.id), details=details))


async def finalize(db, pick: OptionalHolidayPick, *, approved: bool,
                   actor, note) -> OptionalHolidayPick:
    """`pick` must already be row-locked by the caller."""
    if pick.status != PickStatus.PENDING:
        raise HTTPException(409, f"Pick is already {pick.status}")
    hol = await db.get(HolidayCalendar, pick.holiday_id)
    if approved:
        if hol is None or not hol.is_optional:
            raise HTTPException(409, "holiday is no longer an optional holiday")
        await assert_dates_unlocked(db, hol.date)
    pick.status = PickStatus.APPROVED if approved else PickStatus.REJECTED
    pick.decided_by_id = getattr(actor, "id", None)
    pick.decided_at = datetime.now(timezone.utc)
    pick.decision_note = (note or "").strip() or None
    _audit(db, pick.decided_by_id, "OPTIONAL_HOLIDAY_DECIDE", pick, {
        "approved": approved, "note": pick.decision_note,
        "holiday_id": pick.holiday_id})
    await roster_svc.notify_many(db, [(
        pick.user_id, f"Optional holiday {pick.status}",
        f"Your optional holiday pick"
        f"{' (' + hol.name + ')' if hol else ''} was {pick.status}."
        + (f" Note: {pick.decision_note}" if pick.decision_note else ""),
        RT, str(pick.id), "optional_holiday_decided")])
    return pick


async def cancel(db, pick: OptionalHolidayPick, *, actor, is_hr: bool,
                 inst=None) -> OptionalHolidayPick:
    """`pick` must already be row-locked; `inst` is its chain instance, also
    locked by the caller (instance first, then pick), or None when direct."""
    if pick.status not in PickStatus.ACTIVE:
        raise HTTPException(409, f"Pick is {pick.status}; cannot cancel")
    hol = await db.get(HolidayCalendar, pick.holiday_id)
    if not is_hr:
        if pick.user_id != actor.id:
            raise HTTPException(404, "Pick not found")
        if hol is not None and hol.date < await local_today(db):
            raise HTTPException(409, "date has passed")
    if pick.status == PickStatus.APPROVED and hol is not None:
        await assert_dates_unlocked(db, hol.date)
    await close_instance(db, inst)
    pick.status = PickStatus.CANCELLED
    _audit(db, actor.id, "OPTIONAL_HOLIDAY_CANCEL", pick, {"is_hr": is_hr})
    return pick


async def _active_picks(db, holiday_id: int, *, lock: bool = False):
    q = select(OptionalHolidayPick).where(
        OptionalHolidayPick.holiday_id == holiday_id,
        OptionalHolidayPick.status.in_(PickStatus.ACTIVE)
    ).order_by(OptionalHolidayPick.id)
    if lock:
        q = q.with_for_update()
    return (await db.execute(
        q.execution_options(populate_existing=True))).scalars().all()


async def _pending_instance(db, pick_id: int):
    return (await db.execute(
        select(ChainedApprovalInstance).where(
            ChainedApprovalInstance.entity_type
            == ChainEntityType.OPTIONAL_HOLIDAY,
            ChainedApprovalInstance.entity_id == pick_id,
            ChainedApprovalInstance.status == ChainedApprovalStatus.PENDING)
        .with_for_update().execution_options(populate_existing=True)
    )).scalars().first()


def _becomes_cancelled(*, status: str, optional: bool,
                       eligible: bool, applies_now: bool) -> bool:
    """Pure rule: does editing the holiday auto-cancel this active pick?
    PENDING and no longer eligible -> yes. APPROVED and the holiday became
    mandatory -> yes only when that mandatory holiday applies to the user
    (otherwise the pick is kept and flagged)."""
    if status == PickStatus.PENDING:
        return not eligible
    if status == PickStatus.APPROVED:
        return (not optional) and applies_now
    return False


async def reconcile_holiday_update(db, hol: HolidayCalendar, old: dict,
                                   actor) -> None:
    """Keep picks consistent after HR edits a holiday (call before commit,
    after the new values are set; inside retry_on_lock so a LockRetry
    propagates). `old` = {date,is_optional,location}.
    Rules (kept deliberately simple):
      * active picks get year = new date's year;
      * PENDING picks that are no longer eligible (holiday became mandatory,
        or its location no longer matches the employee) are cancelled and
        their pending chain instance closed;
      * APPROVED picks on a holiday that became mandatory are cancelled only
        when the new mandatory holiday applies to that user (location); the
        quota slot is then freed. If any such pick sits in a payroll-locked
        month the edit is refused with 409;
      * other APPROVED picks that fall ineligible (incl. a mandatory holiday
        that does not apply to the user), or whose date moved into a
        payroll-locked month, are left approved and flagged in the audit log
        (pay is never changed silently).
    Lock order: chain instances first, then the pick rows."""
    new = {"date": hol.date, "is_optional": bool(hol.is_optional),
           "location": hol.location}
    if all(old[k] == new[k] for k in new):
        return
    # Lock order (chain instance -> pick): instances of pending picks first.
    snap = (await db.execute(
        select(OptionalHolidayPick.id).where(
            OptionalHolidayPick.holiday_id == hol.id,
            OptionalHolidayPick.status == PickStatus.PENDING)
        .order_by(OptionalHolidayPick.id))).scalars().all()
    instances = {pid: await _pending_instance(db, pid) for pid in snap}
    picks = await _active_picks(db, hol.id, lock=True)
    plan = []
    for p in picks:
        applies_now = holidays_svc.applies(
            hol.location, await user_location(db, p.user_id))
        eligible = bool(hol.is_optional) and applies_now
        plan.append((p, eligible, _becomes_cancelled(
            status=p.status, optional=bool(hol.is_optional),
            eligible=eligible, applies_now=applies_now)))
    if any(p.status == PickStatus.PENDING and p.id not in instances
           for p, _, _ in plan):
        # A pick turned pending after the snapshot: re-run in a fresh
        # transaction rather than lock the instance after the pick.
        raise LockRetry("Pick changed while editing; retry")
    # Cancelling an approved pick changes pay for its date: refuse in a
    # payroll-locked month (old and new date), before touching anything.
    if any(p.status == PickStatus.APPROVED and cancel for p, _, cancel in plan):
        for d in {old["date"], hol.date}:
            await assert_dates_unlocked(db, d)
    actor_id = getattr(actor, "id", None)
    for p, eligible, cancel in plan:
        p.year = hol.date.year
        detail = {"holiday_id": hol.id,
                  "old": {k: str(v) for k, v in old.items()},
                  "new": {k: str(v) for k, v in new.items()}}
        if p.status == PickStatus.PENDING and cancel:
            await close_instance(db, instances.get(p.id))
            p.status = PickStatus.CANCELLED
            _audit(db, actor_id, "OPTIONAL_HOLIDAY_AUTO_CANCEL", p, detail)
            await roster_svc.notify_many(db, [(
                p.user_id, "Optional holiday pick cancelled",
                f"Your pick for {hol.name} was cancelled because the holiday "
                "changed.", RT, str(p.id), "optional_holiday_decided")])
        elif p.status == PickStatus.APPROVED and cancel:
            p.status = PickStatus.CANCELLED
            _audit(db, actor_id, "OPTIONAL_HOLIDAY_AUTO_CANCEL", p, detail)
        elif p.status == PickStatus.APPROVED:
            flag = None
            if not eligible:
                flag = ("holiday is now mandatory at a location that does "
                        "not apply to this employee; pick kept"
                        if not hol.is_optional else "no longer eligible")
            elif old["date"] != hol.date:
                try:
                    await assert_dates_unlocked(db, hol.date)
                except LockRetry:
                    raise
                except HTTPException:
                    flag = "date moved into a payroll-locked month"
            if flag:
                _audit(db, actor_id, "OPTIONAL_HOLIDAY_PICK_FLAGGED", p,
                       {**detail, "note": flag})


async def prepare_holiday_delete(db, hol: HolidayCalendar, actor) -> None:
    """Before deleting a holiday: refuse (409) when an approved pick sits in
    a payroll-locked month; close pending chain instances of its picks and
    write an audit row (the picks themselves cascade-delete)."""
    picks = (await db.execute(
        select(OptionalHolidayPick).where(
            OptionalHolidayPick.holiday_id == hol.id)
        .execution_options(populate_existing=True))).scalars().all()
    if any(p.status == PickStatus.APPROVED for p in picks):
        await assert_dates_unlocked(db, hol.date)
    for p in picks:
        if p.status == PickStatus.PENDING:
            await close_instance(db, await _pending_instance(db, p.id))
    db.add(AuditLog(user_id=getattr(actor, "id", None), action="HOLIDAY_DELETE",
                    resource_type="holiday_calendar", resource_id=str(hol.id),
                    details={"name": hol.name, "date": hol.date.isoformat(),
                             "location": hol.location,
                             "picks_removed": [
                                 {"id": p.id, "user_id": p.user_id,
                                  "status": p.status} for p in picks]}))
