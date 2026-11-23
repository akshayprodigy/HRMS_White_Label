"""On-duty / client-visit / WFH requests (Phase 6A Task 7). An APPROVED
request relaxes the geofence and counts a no-punch day as present (the
effects are wired in Task 8 through approved_portions / approved_kinds).

Services never commit; the endpoint commits once. Errors are HTTPException
(message is safe to show)."""
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select

from app.models.audit import AuditLog
from app.models.leave import HalfDaySession, LeaveRequest, LeaveStatus
from app.models.work_location import (
    DayPortion, WorkLocationKind, WorkLocationRequest, WorkLocationStatus,
)
from app.services import roster as roster_svc
from app.services.chain_routing import assert_dates_unlocked, close_instance
from app.services.org_time import local_today
from app.services.time_rules import get_time_rules

RT = "work_location"
BACKDATE_KEY = "attendance.work_location_backdate_days"
MAX_SPAN_DAYS = 31
KIND_LABEL = {WorkLocationKind.ON_DUTY: "On duty",
              WorkLocationKind.CLIENT_VISIT: "Client visit",
              WorkLocationKind.WFH: "WFH"}
_HALF_LABEL = {DayPortion.FIRST_HALF: " (first half)",
               DayPortion.SECOND_HALF: " (second half)"}


async def backdate_days(db) -> int:
    try:
        v = int(str((await get_time_rules(db)).get(BACKDATE_KEY, "7")).strip())
    except (TypeError, ValueError):
        return 7
    return v if 0 <= v <= 60 else 7


def _fmt(d: date) -> str:
    return f"{d.day} {d.strftime('%b')}"


def summary(kind, place, start: date, end: date, portion) -> str:
    """'WFH 20–22 Nov' / 'Client visit: Acme, 20 Nov (first half)'."""
    label = KIND_LABEL.get(kind, kind)
    if start == end:
        when = _fmt(start)
    elif (start.year, start.month) == (end.year, end.month):
        when = f"{start.day}–{_fmt(end)}"
    else:
        when = f"{_fmt(start)} – {_fmt(end)}"
    head = f"{label}: {place}, {when}" if place else f"{label} {when}"
    return head + _HALF_LABEL.get(portion, "")


def req_summary(r: WorkLocationRequest) -> str:
    return summary(r.kind, r.place, r.start_date, r.end_date, r.day_portion)


def _conflicts(a_start, a_end, a_portion, b_start, b_end, b_portion) -> bool:
    if a_end < b_start or b_end < a_start:
        return False
    if (a_start == a_end == b_start == b_end
            and {a_portion, b_portion}
            == {DayPortion.FIRST_HALF, DayPortion.SECOND_HALF}):
        return False
    return True


_LEAVE_PORTION = {HalfDaySession.MORNING: DayPortion.FIRST_HALF,
                  HalfDaySession.AFTERNOON: DayPortion.SECOND_HALF}


async def assert_no_approved_leave(db, user_id: int, start_date: date,
                                   end_date: date, day_portion: str) -> None:
    """409 when APPROVED leave already covers any of these dates. Pending
    leave does not block: only an approved request is "taken". A half-day
    leave and the opposite half-day request on the same date may coexist;
    a half-day leave with no session blocks the whole date."""
    rows = (await db.execute(
        select(LeaveRequest.start_date, LeaveRequest.end_date,
               LeaveRequest.is_half_day, LeaveRequest.half_day_session).where(
            LeaveRequest.employee_id == user_id,
            LeaveRequest.status == LeaveStatus.APPROVED,
            LeaveRequest.end_date >= start_date,
            LeaveRequest.start_date <= end_date))).all()
    for s, e, half, session in rows:
        portion = (_LEAVE_PORTION.get(session, DayPortion.FULL) if half
                   else DayPortion.FULL)
        if _conflicts(start_date, end_date, day_portion, s, e, portion):
            raise HTTPException(
                409, "You have approved leave on these dates")


async def create(db, *, user, kind, start_date, end_date, day_portion,
                 place, purpose) -> WorkLocationRequest:
    """The CALLER must hold the user-row lock (fresh transaction) so the
    single user-scoped overlap read below is race-free without locking other
    users' rows."""
    uid = user.id
    if kind not in WorkLocationKind.ALL:
        raise HTTPException(422, "Unknown kind")
    if day_portion not in DayPortion.ALL:
        raise HTTPException(422, "Unknown day portion")
    if end_date < start_date:
        raise HTTPException(422, "end_date must not be before start_date")
    if (end_date - start_date).days + 1 > MAX_SPAN_DAYS:
        raise HTTPException(
            422, f"A request may span at most {MAX_SPAN_DAYS} days")
    if day_portion != DayPortion.FULL and start_date != end_date:
        raise HTTPException(422, "Half-day requests must be a single day")
    place = (place or "").strip()
    if len(place) > 200:
        raise HTTPException(422, "place must be at most 200 characters")
    if kind in WorkLocationKind.NEEDS_PLACE and not place:
        raise HTTPException(422, "place is required for this kind")
    purpose = (purpose or "").strip()
    if not 1 <= len(purpose) <= 1000:
        raise HTTPException(422, "purpose must be 1-1000 characters")
    earliest = await local_today(db) - timedelta(days=await backdate_days(db))
    if start_date < earliest:
        raise HTTPException(
            422, f"Start date cannot be before {earliest.isoformat()}")
    await assert_dates_unlocked(db, start_date, end_date)
    await assert_no_approved_leave(db, uid, start_date, end_date, day_portion)
    rows = (await db.execute(
        select(WorkLocationRequest.start_date, WorkLocationRequest.end_date,
               WorkLocationRequest.day_portion).where(
            WorkLocationRequest.user_id == uid,
            WorkLocationRequest.status.in_(WorkLocationStatus.ACTIVE),
            WorkLocationRequest.end_date >= start_date,
            WorkLocationRequest.start_date <= end_date))).all()
    for s, e, p in rows:
        if _conflicts(start_date, end_date, day_portion, s, e, p):
            raise HTTPException(
                409, "You already have a work-location request on these dates")
    req = WorkLocationRequest(
        user_id=uid, kind=kind, start_date=start_date, end_date=end_date,
        day_portion=day_portion, place=place or None, purpose=purpose,
        status=WorkLocationStatus.PENDING)
    db.add(req)
    await db.flush()
    return req


def _audit(db, actor_id, action, req, details) -> None:
    db.add(AuditLog(user_id=actor_id, action=action, resource_type=RT,
                    resource_id=str(req.id), details=details))


def audit_create(db, actor_id, req, routed_via: str) -> None:
    _audit(db, actor_id, "WORK_LOCATION_CREATE", req, {
        "kind": req.kind, "start": req.start_date.isoformat(),
        "end": req.end_date.isoformat(), "portion": req.day_portion,
        "routed_via": routed_via})


async def finalize(db, req: WorkLocationRequest, *, approved: bool, actor,
                   note) -> WorkLocationRequest:
    """`req` must already be row-locked by the caller."""
    if req.status != WorkLocationStatus.PENDING:
        raise HTTPException(409, f"Request is already {req.status}")
    if approved:
        await assert_dates_unlocked(db, req.start_date, req.end_date)
        await assert_no_approved_leave(db, req.user_id, req.start_date,
                                       req.end_date, req.day_portion)
    req.status = (WorkLocationStatus.APPROVED if approved
                  else WorkLocationStatus.REJECTED)
    req.decided_by_id = getattr(actor, "id", None)
    req.decided_at = datetime.now(timezone.utc)
    req.decision_note = (note or "").strip() or None
    _audit(db, req.decided_by_id, "WORK_LOCATION_DECIDE", req, {
        "approved": approved, "note": req.decision_note})
    await roster_svc.notify_many(db, [(
        req.user_id, f"Work-location request {req.status}",
        f"Your request ({req_summary(req)}) was {req.status}."
        + (f" Note: {req.decision_note}" if req.decision_note else ""),
        RT, str(req.id), "work_location_cancelled")])
    return req


async def cancel(db, req: WorkLocationRequest, *, actor, is_hr: bool,
                 inst=None) -> WorkLocationRequest:
    """`req` row-locked by the caller; `inst` its locked chain instance or
    None when direct."""
    if req.status not in WorkLocationStatus.ACTIVE:
        raise HTTPException(409, f"Request is {req.status}; cannot cancel")
    if not is_hr:
        if req.user_id != actor.id:
            raise HTTPException(404, "Request not found")
        if req.start_date < await local_today(db):
            raise HTTPException(409, "The request has already started")
    if req.status == WorkLocationStatus.APPROVED:
        await assert_dates_unlocked(db, req.start_date, req.end_date)
    await close_instance(db, inst)
    req.status = WorkLocationStatus.CANCELLED
    _audit(db, actor.id, "WORK_LOCATION_CANCEL", req, {"is_hr": is_hr})
    if req.user_id != actor.id:
        await roster_svc.notify_many(db, [(
            req.user_id, "Work-location request cancelled",
            f"Your request ({req_summary(req)}) was cancelled by HR.",
            RT, str(req.id), "work_location_cancelled")])
    return req


_RANK = {DayPortion.FULL: 0, DayPortion.FIRST_HALF: 1,
         DayPortion.SECOND_HALF: 2}


async def approved_info(db, user_ids, start: date, end: date):
    """(portions, kinds) for APPROVED requests overlapping [start, end],
    expanded per date and clipped to the range.
    portions: uid -> {date: "full"|"first_half"|"second_half"} (a first and a
    second half on one date merge to "full").
    kinds: uid -> {date: kind}; when several requests cover a date the
    full-day one wins, else the first-half one (deterministic).
    Every requested user id is a key. One query per 1000 ids."""
    ids = sorted({int(u) for u in user_ids})
    best: dict = {u: {} for u in ids}   # uid -> date -> (rank, kind)
    seen: dict = {u: {} for u in ids}   # uid -> date -> set(portions)
    for i in range(0, len(ids), 1000):
        rows = (await db.execute(
            select(WorkLocationRequest.user_id, WorkLocationRequest.kind,
                   WorkLocationRequest.start_date,
                   WorkLocationRequest.end_date,
                   WorkLocationRequest.day_portion).where(
                WorkLocationRequest.user_id.in_(ids[i:i + 1000]),
                WorkLocationRequest.status == WorkLocationStatus.APPROVED,
                WorkLocationRequest.end_date >= start,
                WorkLocationRequest.start_date <= end)
            .order_by(WorkLocationRequest.id))).all()
        for uid, kind, s, e, portion in rows:
            d, last = max(s, start), min(e, end)
            while d <= last:
                seen[uid].setdefault(d, set()).add(portion)
                cand = (_RANK[portion], kind)
                if d not in best[uid] or cand[0] < best[uid][d][0]:
                    best[uid][d] = cand
                d += timedelta(days=1)
    portions: dict = {}
    kinds: dict = {}
    for uid in ids:
        portions[uid] = {
            d: (DayPortion.FULL if len(ps) > 1 or DayPortion.FULL in ps
                else next(iter(ps)))
            for d, ps in seen[uid].items()}
        kinds[uid] = {d: v[1] for d, v in best[uid].items()}
    return portions, kinds


async def approved_portions(db, user_ids, start: date, end: date) -> dict:
    return (await approved_info(db, user_ids, start, end))[0]


async def approved_kinds(db, user_ids, start: date, end: date) -> dict:
    return (await approved_info(db, user_ids, start, end))[1]


async def approved_portion(db, user_id: int, d: date):
    return (await approved_portions(db, [user_id], d, d))[int(user_id)].get(d)
