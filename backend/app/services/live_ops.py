"""Live operations board + no-show detection (Roadmap v2 Phase 1B, Task 9).

Shift start/end are wall-clock times compared as UTC, exactly like
shift_resolver / attendance (no org timezone yet). `classify` is pure; the
loader batches every query (no per-employee DB access).
"""
import enum
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance import Attendance
from app.models.employee import Employee, EmployeeStatus
from app.models.no_show import NoShowAlert
from app.models.schedule_delegation import ScheduleDelegation
from app.models.user import Permission, Role, User
from app.services import roster as roster_svc
from app.services.effective_shift import effective_shifts_for_range
from app.services.shift_resolver import _combine
from app.services.time_rules import get_schedule_rules

logger = logging.getLogger(__name__)

ID_CHUNK = 500


class LiveStatus(str, enum.Enum):
    OFF = "off"
    ON_LEAVE = "on_leave"
    UPCOMING = "upcoming"
    NOT_ARRIVED = "not_arrived"
    NO_SHOW = "no_show"
    ON_SHIFT = "on_shift"
    COMPLETED = "completed"


def shift_bounds(shift, work_date: date) -> Tuple[datetime, datetime]:
    """Nominal (start, end) of `shift` for `work_date`, UTC-aware; an
    overnight shift ends on the next calendar day."""
    start = _combine(work_date, shift.start_time)
    end = _combine(
        work_date + timedelta(days=1) if shift.is_overnight else work_date,
        shift.end_time)
    return start, end


def classify(
    *, now: datetime, start: Optional[datetime], end: Optional[datetime],
    grace_in: int, punch_in: Optional[datetime], punch_out: Optional[datetime],
    on_leave: bool, no_show_minutes: int,
) -> Tuple[LiveStatus, int]:
    """(status, late_minutes). All datetimes are UTC-aware."""
    if start is None or end is None:
        if punch_in is not None:
            return (LiveStatus.COMPLETED if punch_out is not None
                    else LiveStatus.ON_SHIFT), 0
        return LiveStatus.OFF, 0
    if on_leave:
        return LiveStatus.ON_LEAVE, 0
    if punch_in is not None:
        status = (LiveStatus.COMPLETED if punch_out is not None
                  else LiveStatus.ON_SHIFT)
        threshold = start + timedelta(minutes=grace_in)
        late = 0
        if punch_in > threshold:
            late = int((punch_in - threshold).total_seconds() // 60)
        return status, late
    if now < start:
        return LiveStatus.UPCOMING, 0
    if no_show_minutes > 0 and now >= start + timedelta(minutes=no_show_minutes):
        return LiveStatus.NO_SHOW, 0
    if now >= end:
        return LiveStatus.NO_SHOW, 0
    return LiveStatus.NOT_ARRIVED, 0


@dataclass
class LiveRow:
    user_id: int
    name: str
    department: Optional[str]
    location: Optional[str]
    work_date: date
    shift_template_id: Optional[int]
    shift_name: Optional[str]
    start: Optional[datetime]
    end: Optional[datetime]
    start_hhmm: Optional[str]
    end_hhmm: Optional[str]
    status: LiveStatus
    late_minutes: int
    punch_in: Optional[datetime]
    punch_out: Optional[datetime]
    alerted: bool = False


def _chunks(ids, n=ID_CHUNK):
    ids = sorted(set(ids))
    for i in range(0, len(ids), n):
        yield ids[i:i + n]


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _punches(rows: List[Attendance]) -> Tuple[Optional[datetime], Optional[datetime]]:
    """Collapse a day's attendance rows: earliest punch-in; punch-out only
    when every row is closed (latest out)."""
    if not rows:
        return None, None
    pin = min(_aware(r.captured_at) for r in rows)
    if any(r.punch_out_time is None for r in rows):
        return pin, None
    return pin, max(_aware(r.punch_out_time) for r in rows)


async def live_board(
    db: AsyncSession, user_ids, now: datetime, *, no_show_minutes: Optional[int] = None,
) -> List[LiveRow]:
    """One row per ACTIVE employee in `user_ids`. Query count is constant in
    the number of employees (chunked only for very large IN lists)."""
    now = _aware(now)
    today = now.date()
    yday = today - timedelta(days=1)
    ids = sorted(set(user_ids))
    if not ids:
        return []
    if no_show_minutes is None:
        no_show_minutes = (await get_schedule_rules(db))["no_show_minutes"]

    people: Dict[int, Tuple[str, Optional[str], Optional[str]]] = {}
    att_rows: List[Attendance] = []
    alerts: set = set()
    for ch in _chunks(ids):
        for emp, full_name, email in (await db.execute(
            select(Employee, User.full_name, User.email)
            .join(User, User.id == Employee.user_id)
            .where(Employee.user_id.in_(ch),
                   Employee.status == EmployeeStatus.ACTIVE,
                   User.is_active.is_(True))
        )).all():
            people[emp.user_id] = (
                full_name or email or f"User {emp.user_id}",
                emp.department, emp.location)
    ids = sorted(people)
    if not ids:
        return []

    eff: Dict[Tuple[int, date], Any] = {}
    for ch in _chunks(ids):
        eff.update(await effective_shifts_for_range(db, ch, yday, today))
        att_rows += list((await db.execute(
            select(Attendance).where(
                Attendance.user_id.in_(ch),
                Attendance.work_date.in_([yday, today]))
        )).scalars().all())
        alerts |= {(u, d) for u, d in (await db.execute(
            select(NoShowAlert.user_id, NoShowAlert.work_date).where(
                NoShowAlert.user_id.in_(ch),
                NoShowAlert.work_date.in_([yday, today])))).all()}
    leave = await roster_svc.approved_leave_days(db, ids, yday, today)

    by_key: Dict[Tuple[int, date], List[Attendance]] = {}
    for a in att_rows:
        by_key.setdefault((a.user_id, a.work_date), []).append(a)

    out: List[LiveRow] = []
    for uid in ids:
        name, dept, loc = people[uid]
        chosen = None  # (work_date, shift, start, end)
        ye = eff.get((uid, yday))
        if ye is not None and ye.shift is not None and not ye.is_week_off \
                and ye.shift.is_overnight:
            s, e = shift_bounds(ye.shift, yday)
            _, pout = _punches(by_key.get((uid, yday), []))
            # Yesterday's overnight shift is still running (and the person
            # has not already clocked out of it).
            if now < e and pout is None:
                chosen = (yday, ye.shift, s, e)
        if chosen is None:
            te = eff.get((uid, today))
            if te is not None and te.shift is not None and not te.is_week_off:
                s, e = shift_bounds(te.shift, today)
                chosen = (today, te.shift, s, e)
        if chosen is not None:
            wd, shift, s, e = chosen
            pin, pout = _punches(by_key.get((uid, wd), []))
            status, late = classify(
                now=now, start=s, end=e, grace_in=shift.grace_in_minutes,
                punch_in=pin, punch_out=pout, on_leave=(uid, wd) in leave,
                no_show_minutes=no_show_minutes)
            out.append(LiveRow(
                uid, name, dept, loc, wd, shift.id, shift.name, s, e,
                shift.start_time.strftime("%H:%M"),
                shift.end_time.strftime("%H:%M"),
                status, late, pin, pout, (uid, wd) in alerts))
        else:
            pin, pout = _punches(by_key.get((uid, today), []))
            status, late = classify(
                now=now, start=None, end=None, grace_in=0, punch_in=pin,
                punch_out=pout, on_leave=False, no_show_minutes=no_show_minutes)
            out.append(LiveRow(
                uid, name, dept, loc, today, None, None, None, None, None,
                None, status, late, pin, pout, False))
    out.sort(key=lambda r: (r.name or "").lower())
    return out


# --- no-show job ---------------------------------------------------------


async def _alert_recipients(
    db: AsyncSession, rows: List[LiveRow], today: date,
) -> Dict[int, set]:
    """employee user id -> set of user ids to notify besides the employee:
    manager + active delegates covering them; roster admins if none."""
    uids = {r.user_id for r in rows}
    out: Dict[int, set] = {u: set() for u in uids}
    for ch in _chunks(uids):
        for uid, mgr in (await db.execute(
            select(User.id, User.manager_id).where(User.id.in_(ch)))).all():
            if mgr:
                out[uid].add(mgr)
    delegs = (await db.execute(
        select(ScheduleDelegation).where(
            ScheduleDelegation.revoked_at.is_(None),
            ScheduleDelegation.valid_from <= today,
            or_(ScheduleDelegation.valid_to.is_(None),
                ScheduleDelegation.valid_to >= today)))).scalars().all()
    for d in delegs:
        covered = (await roster_svc.delegation_user_ids(db, d)) & uids
        for u in covered:
            out[u].add(d.grantee_id)
    # Drop inactive recipients.
    cand = set().union(*out.values()) if out else set()
    active = set()
    if cand:
        active = set((await db.execute(
            select(User.id).where(User.id.in_(cand),
                                  User.is_active.is_(True)))).scalars().all())
    admins: Optional[set] = None
    for u in out:
        out[u] = (out[u] & active) - {u}
        if not out[u]:
            if admins is None:
                admins = set((await db.execute(
                    select(User.id).where(User.is_active.is_(True),
                                          User.is_superuser.is_(True)))).scalars().all())
                admins |= set((await db.execute(
                    select(User.id).join(User.roles).join(Role.permissions)
                    .where(User.is_active.is_(True),
                           Permission.name == roster_svc.PERM_ROSTER))).scalars().all())
            out[u] = admins - {u}
    return out


async def no_show_job(
    session: AsyncSession, now: Optional[datetime] = None,
    user_ids: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """Create one NoShowAlert per (user, work_date) for every NO_SHOW row and
    notify the employee + their schedulers. Idempotent."""
    now = _aware(now) if now else datetime.now(timezone.utc)
    minutes = (await get_schedule_rules(session))["no_show_minutes"]
    if minutes <= 0:
        return {"skipped": "disabled"}
    q = (select(Employee.user_id).join(User, User.id == Employee.user_id)
         .where(Employee.status == EmployeeStatus.ACTIVE,
                User.is_active.is_(True), Employee.user_id.is_not(None)))
    if user_ids is not None:  # tests / targeted runs
        q = q.where(Employee.user_id.in_(list(user_ids)))
    ids = list((await session.execute(q)).scalars().all())
    rows = await live_board(session, ids, now, no_show_minutes=minutes)
    cands = [r for r in rows if r.status == LiveStatus.NO_SHOW and not r.alerted]
    created: List[LiveRow] = []
    for r in cands:
        try:
            async with session.begin_nested():
                session.add(NoShowAlert(
                    user_id=r.user_id, work_date=r.work_date,
                    shift_template_id=r.shift_template_id))
                await session.flush()
            created.append(r)
        except IntegrityError:
            continue
    notified = 0
    if created:
        recips = await _alert_recipients(session, created, now.date())
        notes = []
        for r in created:
            shift = r.shift_name or "your shift"
            hhmm = r.start_hhmm or ""
            notes.append((
                r.user_id, "No-show: missed punch-in",
                f"You haven't punched in for {shift} at {hhmm}.",
                "attendance", None))
            for rid in sorted(recips.get(r.user_id, ())):
                notes.append((
                    rid, "Employee no-show",
                    f"{r.name} hasn't punched in for {shift} at {hhmm} "
                    f"({r.work_date}).",
                    "roster", None))
        await roster_svc.notify_many(session, notes)
        notified = len(notes)
    await session.commit()
    return {"checked": len(rows), "alerts_created": len(created),
            "notifications": notified}
