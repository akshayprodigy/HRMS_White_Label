"""Consent-based live location tracking (Roadmap v2 Phase 3, Task 3).

Shift times are wall-clock compared as UTC (same convention as live_ops /
shift_resolver). The ping window is the effective working shift of a work
date widened by WINDOW_MARGIN on both sides; week-off / holiday / leave days
have no window. All DB access is batched; helpers take an AsyncSession.
"""
import logging
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.models.attendance import Attendance
from app.models.audit import AuditLog
from app.models.employee import Employee
from app.models.location import (
    LocationPing, TrackingAlert, TrackingConsent, TrackingOverride,
    TrackingPolicy,
)
from app.models.user import User, user_roles
from app.services import roster as roster_svc
from app.services.absence_lop import (
    default_offs_from_rules, is_non_working_day, load_holidays,
)
from app.services.effective_shift import effective_shifts_for_range
from app.services.geofence import haversine_meters
from app.services.org_time import local_date, local_today_for, org_tz
from app.services.time_rules import get_time_rules

logger = logging.getLogger(__name__)

WINDOW_MARGIN = timedelta(minutes=30)
DEFAULT_INTERVAL = 300
DEFAULT_DISTANCE = 100
MAX_BATCH = 200
FUTURE_SKEW = timedelta(minutes=2)
MAX_AGE = timedelta(hours=24)
STALE_AFTER = timedelta(minutes=15)
EXIT_BUFFER_M = 100.0
MAX_ACCURACY_M = 5000.0
MAX_SPEED_MS = 200.0
PURGE_BATCH = 5000
ALERT_GEOFENCE_EXIT = "geofence_exit"


def aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


@dataclass
class Requirement:
    required: bool
    interval_seconds: int = DEFAULT_INTERVAL
    distance_filter_m: int = DEFAULT_DISTANCE


async def requirements(db, user_ids: Iterable[int]) -> Dict[int, Requirement]:
    """Override if present, else any role with an enabled policy (smallest
    interval/distance among the enabled ones win)."""
    ids = sorted(set(user_ids))
    out: Dict[int, Requirement] = {}
    if not ids:
        return out
    roles: Dict[int, set] = {}
    for i in range(0, len(ids), 500):
        for uid, rid in (await db.execute(
            select(user_roles.c.user_id, user_roles.c.role_id)
            .where(user_roles.c.user_id.in_(ids[i:i + 500])))).all():
            roles.setdefault(uid, set()).add(rid)
    pol = {p.role_id: p for p in (await db.execute(
        select(TrackingPolicy).where(TrackingPolicy.enabled.is_(True))
    )).scalars().all()}
    ovr: Dict[int, bool] = {}
    for i in range(0, len(ids), 500):
        for o in (await db.execute(
            select(TrackingOverride).where(
                TrackingOverride.user_id.in_(ids[i:i + 500])))).scalars().all():
            ovr[o.user_id] = o.enabled
    for uid in ids:
        ps = [pol[r] for r in roles.get(uid, ()) if r in pol]
        interval = min((p.interval_seconds for p in ps), default=DEFAULT_INTERVAL)
        dist = min((p.distance_filter_m for p in ps), default=DEFAULT_DISTANCE)
        required = ovr[uid] if uid in ovr else bool(ps)
        out[uid] = Requirement(required, interval, dist)
    return out


async def active_consents(db, user_ids: Iterable[int]) -> Dict[int, TrackingConsent]:
    """user id -> latest consent row, only when it is not revoked."""
    ids = sorted(set(user_ids))
    out: Dict[int, TrackingConsent] = {}
    for i in range(0, len(ids), 500):
        rows = (await db.execute(
            select(TrackingConsent)
            .where(TrackingConsent.user_id.in_(ids[i:i + 500]))
            .order_by(TrackingConsent.id))).scalars().all()
        for r in rows:  # ascending: the last one per user is the latest
            out[r.user_id] = r
    return {u: r for u, r in out.items() if r.revoked_at is None}


async def windows_for(
    db, user_id: int, d_from: date, d_to: date,
) -> List[Tuple[date, datetime, datetime, Any]]:
    """[(work_date, window_start, window_end, shift)] for every WORKING shift
    on work dates in [d_from, d_to]; the window is the shift +/- 30 min
    (an overnight shift ends the next calendar day)."""
    from app.services.live_ops import shift_bounds
    tz = await org_tz(db)
    eff = await effective_shifts_for_range(db, [user_id], d_from, d_to)
    emp = (await db.execute(
        select(Employee).where(Employee.user_id == user_id))).scalars().first()
    loc = (emp.location if emp else None) or "HQ"
    holidays = await load_holidays(db, d_from, d_to)
    default_offs = default_offs_from_rules(await get_time_rules(db))
    leave = await roster_svc.approved_leave_days(db, [user_id], d_from, d_to)
    out = []
    d = d_from
    while d <= d_to:
        e = eff.get((user_id, d))
        if (e is not None and e.shift is not None
                and (user_id, d) not in leave
                and not is_non_working_day(
                    e, d, loc, holidays, default_offs,
                    roster_beats_holiday=True)):
            s, en = shift_bounds(e.shift, d, tz)
            out.append((d, s - WINDOW_MARGIN, en + WINDOW_MARGIN, e.shift))
        d += timedelta(days=1)
    return out


def current_window(windows, now: datetime):
    """The window containing `now`; else the next upcoming; else the latest."""
    for w in windows:
        if w[1] <= now <= w[2]:
            return w
    upcoming = [w for w in windows if w[1] > now]
    if upcoming:
        return min(upcoming, key=lambda w: w[1])
    return windows[-1] if windows else None


async def my_status(db, user_id: int, now: datetime) -> Dict[str, Any]:
    req = (await requirements(db, [user_id]))[user_id]
    consent = (await active_consents(db, [user_id])).get(user_id)
    w = None
    if req.required:
        today = local_today_for(await org_tz(db), now)
        w = current_window(
            await windows_for(db, user_id, today - timedelta(days=1), today),
            now)
        if w is not None and w[2] < now and w[0] != today:
            w = None
    return {
        "required": req.required,
        "consented": consent is not None,
        "consented_at": aware(consent.consented_at).isoformat() if consent else None,
        "active": req.required and consent is not None,
        "window": ({
            "work_date": w[0].isoformat(),
            "start": w[1].isoformat(), "end": w[2].isoformat(),
            "shift_start": (w[1] + WINDOW_MARGIN).isoformat(),
            "shift_end": (w[2] - WINDOW_MARGIN).isoformat(),
            "in_window": w[1] <= now <= w[2],
        } if w else None),
        "interval_seconds": req.interval_seconds,
        "distance_filter_m": req.distance_filter_m,
    }


def validate_ping(p, now: datetime) -> Optional[str]:
    """Drop reason for a structurally bad / out-of-range ping, else None."""
    vals = [p.lat, p.lng] + [v for v in (p.accuracy, p.speed, p.battery)
                             if v is not None]
    if any(not math.isfinite(v) for v in vals):
        return "invalid"
    if not (-90 <= p.lat <= 90 and -180 <= p.lng <= 180):
        return "invalid"
    if p.accuracy is not None and not 0 <= p.accuracy <= MAX_ACCURACY_M:
        return "invalid"
    if p.speed is not None and not 0 <= p.speed <= MAX_SPEED_MS:
        return "invalid"
    if p.battery is not None and not 0 <= p.battery <= 100:
        return "invalid"
    cap = aware(p.captured_at)
    if cap > now + FUTURE_SKEW:
        return "future"
    if cap < now - MAX_AGE:
        return "too_old"
    return None


def _outside(ping, fences) -> bool:
    edge = min(haversine_meters(ping.lat, ping.lng, f.latitude, f.longitude)
               - f.radius_meters for f in fences)
    return edge > (ping.accuracy or 0.0) + EXIT_BUFFER_M


async def ingest_pings(
    db, user_id: int, pings: List[Any], now: datetime,
) -> Dict[str, Any]:
    """Validate + store a batch. The caller holds the user-row lock and
    commits. Returns {accepted, dropped: {reason: n}}."""
    dropped: Dict[str, int] = {}

    def drop(reason: str, n: int = 1):
        dropped[reason] = dropped.get(reason, 0) + n

    req = (await requirements(db, [user_id]))[user_id]
    if not req.required:
        return {"accepted": 0, "dropped": {"not_required": len(pings)} if pings else {}}
    consent = (await active_consents(db, [user_id])).get(user_id)
    if consent is None:
        return {"accepted": 0, "dropped": {"no_consent": len(pings)} if pings else {}}

    since = consent_floor(consent)
    ok = []
    for p in pings:
        r = validate_ping(p, now)
        if r is None and aware(p.captured_at) < since:
            r = "before_consent"
        if r:
            drop(r)
        else:
            ok.append(p)
    if not ok:
        return {"accepted": 0, "dropped": dropped}

    caps = [aware(p.captured_at).replace(microsecond=0) for p in ok]
    tz = await org_tz(db)
    wins = await windows_for(
        db, user_id, local_date(min(caps), tz) - timedelta(days=1),
        local_date(max(caps), tz))
    existing = {aware(c) for c in (await db.execute(
        select(LocationPing.captured_at).where(
            LocationPing.user_id == user_id,
            LocationPing.captured_at >= min(caps),
            LocationPing.captured_at <= max(caps)))).scalars().all()}
    seen = set(existing)
    new_rows: List[LocationPing] = []
    for p, cap in sorted(zip(ok, caps), key=lambda x: x[1]):
        wd = next((w[0] for w in wins if w[1] <= cap <= w[2]), None)
        if wd is None:
            drop("outside_window")
            continue
        if cap in seen:
            drop("duplicate")
            continue
        seen.add(cap)
        new_rows.append(LocationPing(
            user_id=user_id, captured_at=cap, lat=p.lat, lng=p.lng,
            accuracy=p.accuracy, speed=p.speed, battery=p.battery,
            work_date=wd, received_at=now))
    if new_rows:
        db.add_all(new_rows)
        await db.flush()
        await _check_geofence_exit(
            db, user_id, new_rows, wins, req.interval_seconds, now)
    return {"accepted": len(new_rows), "dropped": dropped}


def consent_floor(consent) -> datetime:
    """Pings older than the active consent are never stored or shown
    (compared at whole-second precision, like stored pings)."""
    return aware(consent.consented_at).replace(microsecond=0)


async def _check_geofence_exit(
    db, user_id: int, new_rows, wins, interval: int, now: datetime,
):
    """Alert once per (user, work_date) when two consecutive pings (at most
    2x interval apart) are both outside the fences, counting only pings
    inside the ACTUAL shift (no +/-30 min margin) and, if the user has
    punched in that day, only from the punch-in on."""
    from app.services.punch import _load_geo_config_with_fences
    geo_enabled, _mode, fences = await _load_geo_config_with_fences(db, user_id)
    if not geo_enabled or not fences:
        return
    by_wd: Dict[date, datetime] = {}
    for r in new_rows:
        c = aware(r.captured_at)
        by_wd[r.work_date] = min(c, by_wd.get(r.work_date, c))
    shifts = {w[0]: (w[1] + WINDOW_MARGIN, w[2] - WINDOW_MARGIN) for w in wins}
    max_gap = timedelta(seconds=2 * interval)
    for wd in sorted(by_wd):
        if wd not in shifts:
            continue
        already = (await db.execute(
            select(TrackingAlert.id).where(
                TrackingAlert.user_id == user_id, TrackingAlert.work_date == wd,
                TrackingAlert.kind == ALERT_GEOFENCE_EXIT))).first()
        if already:
            continue
        lo, hi = shifts[wd]
        pin = (await db.execute(
            select(Attendance.captured_at).where(
                Attendance.user_id == user_id, Attendance.work_date == wd)
            .order_by(Attendance.captured_at).limit(1))).scalar()
        if pin is not None:
            lo = max(lo, aware(pin))
        rows = (await db.execute(
            select(LocationPing.captured_at, LocationPing.lat,
                   LocationPing.lng, LocationPing.accuracy).where(
                LocationPing.user_id == user_id, LocationPing.work_date == wd,
                LocationPing.captured_at >= max(lo, by_wd[wd] - max_gap),
                LocationPing.captured_at <= hi)
            .order_by(LocationPing.captured_at))).all()
        trigger = None
        for a, b in zip(rows, rows[1:]):
            if (aware(b.captured_at) - aware(a.captured_at) <= max_gap
                    and _outside(a, fences) and _outside(b, fences)):
                trigger = b
                break
        if trigger is None:
            continue
        try:
            async with db.begin_nested():
                db.add(TrackingAlert(
                    user_id=user_id, work_date=wd, kind=ALERT_GEOFENCE_EXIT))
                await db.flush()
        except IntegrityError:
            continue
        await _send_exit_alert(db, user_id, wd, trigger, now)


async def _send_exit_alert(db, user_id, wd, ping, now):
    from app.services.live_ops import _alert_recipients
    u = await db.get(User, user_id)
    name = (u.full_name or u.email) if u else f"User {user_id}"
    recips = (await _alert_recipients(
        db, [SimpleNamespace(user_id=user_id)],
        local_today_for(await org_tz(db), now))).get(user_id, set())
    await roster_svc.notify_many(db, [
        (rid, "Employee left work area",
         f"{name} appears to be outside their assigned work area during "
         f"their shift ({wd}).",
         "tracking", str(user_id), "tracking_geofence_exit")
        for rid in sorted(recips)])
    db.add(AuditLog(
        user_id=user_id, action="TRACKING_GEOFENCE_EXIT",
        resource_type="tracking_alert", resource_id=str(user_id),
        details={"work_date": wd.isoformat(),
                 "captured_at": aware(ping.captured_at).isoformat(),
                 "notified": sorted(recips)}))


def ping_row(p: LocationPing) -> Dict[str, Any]:
    return {"captured_at": aware(p.captured_at).isoformat(),
            "lat": p.lat, "lng": p.lng, "accuracy": p.accuracy,
            "speed": p.speed, "battery": p.battery}


async def _purge_batched(session, model, cond) -> int:
    """Delete matching rows PURGE_BATCH at a time, committing per batch."""
    total = 0
    while True:
        ids = list((await session.execute(
            select(model.id).where(cond).limit(PURGE_BATCH))).scalars().all())
        if not ids:
            return total
        await session.execute(delete(model).where(model.id.in_(ids)))
        await session.commit()
        total += len(ids)
        if len(ids) < PURGE_BATCH:
            return total


async def purge_pings(session, now: Optional[datetime] = None) -> Dict[str, Any]:
    now = aware(now) if now else datetime.now(timezone.utc)
    rules = await get_time_rules(session)
    try:
        days = int(str(rules.get("tracking.retention_days", "30")).strip())
        if not 1 <= days <= 365:
            raise ValueError
    except ValueError:
        days = 30
    cutoff = now - timedelta(days=days)
    pings = await _purge_batched(
        session, LocationPing, LocationPing.captured_at < cutoff)
    alerts = await _purge_batched(
        session, TrackingAlert, TrackingAlert.work_date < cutoff.date())
    return {"retention_days": days, "pings_deleted": pings,
            "alerts_deleted": alerts}


async def delete_user_data(db, user_id: int) -> Dict[str, int]:
    """Employee data control: remove own pings + alerts. Caller commits."""
    p = (await db.execute(
        delete(LocationPing).where(LocationPing.user_id == user_id))).rowcount or 0
    a = (await db.execute(
        delete(TrackingAlert).where(TrackingAlert.user_id == user_id))).rowcount or 0
    return {"pings": p, "alerts": a}
