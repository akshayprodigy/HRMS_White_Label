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
    ChainedApprovalStepInstance, StepInstanceStatus,
)
from app.models.audit import AuditLog
from app.models.employee import Employee
from app.models.hr import HolidayCalendar
from app.models.optional_holiday import OptionalHolidayPick, PickStatus
from app.models.user import Permission, Role, User
from app.services import holidays as holidays_svc
from app.services import roster as roster_svc
from app.services.attendance_lock import assert_attendance_editable
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


async def _locked(db, hol: HolidayCalendar) -> None:
    await _locked_date(db, hol.date)


async def _locked_date(db, d) -> None:
    try:
        await assert_attendance_editable(db, d, fresh=True)
    except HTTPException as e:
        if e.status_code == 409:
            raise HTTPException(409, f"payroll period locked: {e.detail}")
        raise


async def finalize(db, pick: OptionalHolidayPick, *, approved: bool,
                   actor, note) -> OptionalHolidayPick:
    """`pick` must already be row-locked by the caller."""
    if pick.status != PickStatus.PENDING:
        raise HTTPException(409, f"Pick is already {pick.status}")
    hol = await db.get(HolidayCalendar, pick.holiday_id)
    if approved:
        if hol is None or not hol.is_optional:
            raise HTTPException(409, "holiday is no longer an optional holiday")
        await _locked(db, hol)
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


async def close_instance(db, inst) -> None:
    """Cancel a (locked) pending chain instance and skip its pending steps."""
    if inst is None or inst.status != ChainedApprovalStatus.PENDING:
        return
    now = datetime.now(timezone.utc)
    inst.status = ChainedApprovalStatus.CANCELLED
    inst.finalized_at = now
    sis = (await db.execute(
        select(ChainedApprovalStepInstance).where(
            ChainedApprovalStepInstance.instance_id == inst.id,
            ChainedApprovalStepInstance.status == StepInstanceStatus.PENDING)
        .execution_options(populate_existing=True))).scalars().all()
    for si in sis:
        si.status = StepInstanceStatus.SKIPPED
        si.comment = "cancelled_by_requester"
        si.actioned_at = now


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
        await _locked(db, hol)
    await close_instance(db, inst)
    pick.status = PickStatus.CANCELLED
    _audit(db, actor.id, "OPTIONAL_HOLIDAY_CANCEL", pick, {"is_hr": is_hr})
    return pick


async def _active_picks(db, holiday_id: int):
    return (await db.execute(
        select(OptionalHolidayPick).where(
            OptionalHolidayPick.holiday_id == holiday_id,
            OptionalHolidayPick.status.in_(PickStatus.ACTIVE))
        .execution_options(populate_existing=True))).scalars().all()


async def _pending_instance(db, pick_id: int):
    return (await db.execute(
        select(ChainedApprovalInstance).where(
            ChainedApprovalInstance.entity_type
            == ChainEntityType.OPTIONAL_HOLIDAY,
            ChainedApprovalInstance.entity_id == pick_id,
            ChainedApprovalInstance.status == ChainedApprovalStatus.PENDING)
        .with_for_update().execution_options(populate_existing=True)
    )).scalars().first()


async def reconcile_holiday_update(db, hol: HolidayCalendar, old: dict,
                                   actor) -> None:
    """Keep picks consistent after HR edits a holiday (call before commit,
    after the new values are set). `old` = {date,is_optional,location}.
    Rules (kept deliberately simple):
      * active picks get year = new date's year;
      * PENDING picks that are no longer eligible (holiday became mandatory,
        or its location no longer matches the employee) are cancelled and
        their pending chain instance closed;
      * APPROVED picks on a holiday that became mandatory are cancelled (it
        applies to everyone anyway and the quota slot is freed);
      * other APPROVED picks that fall ineligible, or whose date moved into a
        payroll-locked month, are left approved and flagged in the audit log
        (pay is never changed silently)."""
    new = {"date": hol.date, "is_optional": bool(hol.is_optional),
           "location": hol.location}
    if all(old[k] == new[k] for k in new):
        return
    for p in await _active_picks(db, hol.id):
        p.year = hol.date.year
        eligible = bool(hol.is_optional) and holidays_svc.applies(
            hol.location, await user_location(db, p.user_id))
        detail = {"holiday_id": hol.id, "old": {k: str(v) for k, v in old.items()},
                  "new": {k: str(v) for k, v in new.items()}}
        if p.status == PickStatus.PENDING and not eligible:
            await close_instance(db, await _pending_instance(db, p.id))
            p.status = PickStatus.CANCELLED
            _audit(db, getattr(actor, "id", None), "OPTIONAL_HOLIDAY_AUTO_CANCEL", p, detail)
            await roster_svc.notify_many(db, [(
                p.user_id, "Optional holiday pick cancelled",
                f"Your pick for {hol.name} was cancelled because the holiday "
                "changed.", RT, str(p.id), "optional_holiday_decided")])
        elif p.status == PickStatus.APPROVED and not hol.is_optional:
            p.status = PickStatus.CANCELLED
            _audit(db, getattr(actor, "id", None), "OPTIONAL_HOLIDAY_AUTO_CANCEL", p, detail)
        elif p.status == PickStatus.APPROVED:
            flag = None
            if not eligible:
                flag = "no longer eligible"
            elif old["date"] != hol.date:
                try:
                    await _locked_date(db, hol.date)
                except HTTPException:
                    flag = "date moved into a payroll-locked month"
            if flag:
                _audit(db, getattr(actor, "id", None), "OPTIONAL_HOLIDAY_PICK_FLAGGED", p,
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
        await _locked(db, hol)
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


async def direct_approver_ids(db, employee_user_id: int) -> list[int]:
    """Who to notify on the direct path: the reporting manager, else HR
    (holders of 'hr employee write') and superusers."""
    mgr = (await db.execute(select(User.manager_id).where(
        User.id == employee_user_id))).scalar_one_or_none()
    if mgr:
        return [mgr]
    sup = (await db.execute(select(User.id).where(
        User.is_active.is_(True), User.is_superuser.is_(True)))).scalars().all()
    perm = (await db.execute(
        select(User.id).join(User.roles).join(Role.permissions)
        .where(User.is_active.is_(True),
               Permission.name == "hr employee write")
    )).scalars().all()
    return sorted((set(sup) | set(perm)) - {employee_user_id})
