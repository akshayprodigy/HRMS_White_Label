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
    uid = user.id
    # Serialise this user's picks so quota/duplicate checks are race-free.
    await db.execute(select(User.id).where(User.id == uid).with_for_update())
    hol = await db.get(HolidayCalendar, holiday_id)
    if hol is None:
        raise HTTPException(404, "Holiday not found")
    if not hol.is_optional:
        raise HTTPException(422, "not an optional holiday")
    if not holidays_svc.applies(hol.location, await user_location(db, uid)):
        raise HTTPException(422, "This holiday is not available for your location")
    if hol.date < await local_today(db):
        raise HTTPException(422, "date has passed")
    dup = (await db.execute(select(OptionalHolidayPick.id).where(
        OptionalHolidayPick.user_id == uid,
        OptionalHolidayPick.holiday_id == hol.id,
        OptionalHolidayPick.status.in_(PickStatus.ACTIVE)
    ).limit(1).with_for_update())).first()
    if dup:
        raise HTTPException(409, "You already picked this holiday")
    q = await quota(db)
    if await used(db, uid, hol.date.year, lock=True) >= q:
        raise HTTPException(409, f"optional holiday quota ({q}) used")
    pick = OptionalHolidayPick(
        holiday_id=hol.id, user_id=uid, year=hol.date.year,
        status=PickStatus.PENDING,
        reason=(reason or "").strip() or None)
    db.add(pick)
    await db.flush()
    return pick


def _audit(db, actor_id, action, pick, details) -> None:
    db.add(AuditLog(user_id=actor_id, action=action, resource_type=RT,
                    resource_id=str(pick.id), details=details))


async def _locked(db, hol: HolidayCalendar) -> None:
    try:
        await assert_attendance_editable(db, hol.date)
    except HTTPException as e:
        if e.status_code == 409:
            raise HTTPException(409, "payroll period locked")
        raise


async def finalize(db, pick: OptionalHolidayPick, *, approved: bool,
                   actor, note) -> OptionalHolidayPick:
    """`pick` must already be row-locked by the caller."""
    if pick.status != PickStatus.PENDING:
        raise HTTPException(409, f"Pick is already {pick.status}")
    hol = await db.get(HolidayCalendar, pick.holiday_id)
    if approved and hol is not None:
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


async def cancel(db, pick: OptionalHolidayPick, *, actor,
                 is_hr: bool) -> OptionalHolidayPick:
    """`pick` must already be row-locked (and its chain instance, if any)."""
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
    inst = (await db.execute(
        select(ChainedApprovalInstance).where(
            ChainedApprovalInstance.entity_type
            == ChainEntityType.OPTIONAL_HOLIDAY,
            ChainedApprovalInstance.entity_id == pick.id,
            ChainedApprovalInstance.status == ChainedApprovalStatus.PENDING)
        .with_for_update().execution_options(populate_existing=True)
    )).scalars().first()
    if inst is not None:
        now = datetime.now(timezone.utc)
        inst.status = ChainedApprovalStatus.CANCELLED
        inst.finalized_at = now
        sis = (await db.execute(
            select(ChainedApprovalStepInstance).where(
                ChainedApprovalStepInstance.instance_id == inst.id,
                ChainedApprovalStepInstance.status
                == StepInstanceStatus.PENDING)
            .execution_options(populate_existing=True))).scalars().all()
        for si in sis:
            si.status = StepInstanceStatus.SKIPPED
            si.comment = "cancelled_by_requester"
            si.actioned_at = now
    pick.status = PickStatus.CANCELLED
    _audit(db, actor.id, "OPTIONAL_HOLIDAY_CANCEL", pick, {"is_hr": is_hr})
    return pick


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
