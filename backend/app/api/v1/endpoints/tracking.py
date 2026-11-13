"""Live location tracking (Roadmap v2 Phase 3, Task 3).

Mounted WITHOUT the attendance gate: tracking runs during the rostered shift
regardless of a web punch. Auth is always required. Privacy: pings are never
returned outside the caller's scope, and scheduler views hide anyone who is
not currently required AND consented.
"""
from datetime import date as pydate, datetime, timedelta, timezone
from typing import Any, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api import deps
from app.api.v1.endpoints.roster_common import (
    lock_row, lock_user_rows, retry_on_lock,
)
from app.models.audit import AuditLog
from app.models.location import (
    LocationPing, TrackingConsent, TrackingOverride, TrackingPolicy,
)
from app.models.user import Role, User
from app.services import location_tracking as lt
from app.services import live_ops
from app.services import roster as roster_svc

router = APIRouter()

HR_READ = "hr employee read"
HR_WRITE = "hr employee write"
MAX_EMPLOYEES = 2000
MAX_TRAIL = 2000


def _iso(x):
    x = lt.aware(x)
    return x.isoformat() if x else None


class ConsentIn(BaseModel):
    app_version: Optional[str] = Field(default=None, max_length=32)


class PingIn(BaseModel):
    captured_at: datetime
    lat: float
    lng: float
    accuracy: Optional[float] = None
    speed: Optional[float] = None
    battery: Optional[float] = None


class PingBatch(BaseModel):
    pings: List[PingIn] = Field(max_length=lt.MAX_BATCH)


class PolicyIn(BaseModel):
    enabled: bool
    interval_seconds: int = Field(default=lt.DEFAULT_INTERVAL, ge=60, le=3600)
    distance_filter_m: int = Field(default=lt.DEFAULT_DISTANCE, ge=10, le=2000)


class OverrideIn(BaseModel):
    enabled: bool


# --- employee ------------------------------------------------------------


@router.get("/my-status")
async def my_status(db: deps.DBDep, me: deps.CurrentUser):
    return await lt.my_status(db, me.id, datetime.now(timezone.utc))


@router.post("/consent")
async def give_consent(db: deps.DBDep, me: deps.CurrentUser,
                       body: Optional[ConsentIn] = None):
    uid = me.id
    ver = body.app_version if body else None

    async def go():
        await lock_user_rows(db, [uid])
        cur = (await lt.active_consents(db, [uid])).get(uid)
        if cur is None:
            cur = TrackingConsent(user_id=uid, app_version=ver)
            db.add(cur)
            db.add(AuditLog(
                user_id=uid, action="TRACKING_CONSENT_GIVEN",
                resource_type="tracking_consent", resource_id=str(uid),
                details={"app_version": ver}))
        await db.flush()
        return lt.aware(cur.consented_at)

    at = await retry_on_lock(db, go, commit=True)
    return {"consented": True, "consented_at": at.isoformat() if at else None}


@router.delete("/consent")
async def revoke_consent(db: deps.DBDep, me: deps.CurrentUser,
                         delete_data: bool = False):
    uid = me.id

    async def go():
        await lock_user_rows(db, [uid])
        cur = (await lt.active_consents(db, [uid])).get(uid)
        if cur is not None:
            cur.revoked_at = datetime.now(timezone.utc)
            db.add(AuditLog(
                user_id=uid, action="TRACKING_CONSENT_REVOKED",
                resource_type="tracking_consent", resource_id=str(uid)))
        deleted = None
        if delete_data:
            deleted = await lt.delete_user_data(db, uid)
            db.add(AuditLog(
                user_id=uid, action="TRACKING_DATA_DELETED",
                resource_type="location_ping", resource_id=str(uid),
                details={"counts": deleted, "with_consent_revoke": True}))
        return cur is not None, deleted

    changed, deleted = await retry_on_lock(db, go, commit=True)
    out = {"consented": False, "revoked": changed}
    if deleted is not None:
        out["deleted"] = deleted
    return out


@router.delete("/my-data")
async def delete_my_data(db: deps.DBDep, me: deps.CurrentUser):
    """Employee data control: erase own pings and tracking alerts."""
    uid = me.id

    async def go():
        await lock_user_rows(db, [uid])
        deleted = await lt.delete_user_data(db, uid)
        db.add(AuditLog(
            user_id=uid, action="TRACKING_DATA_DELETED",
            resource_type="location_ping", resource_id=str(uid),
            details={"counts": deleted}))
        return deleted

    return {"deleted": await retry_on_lock(db, go, commit=True)}


@router.post("/pings")
async def post_pings(body: PingBatch, db: deps.DBDep, me: deps.CurrentUser):
    uid = me.id

    async def go():
        await lock_user_rows(db, [uid])
        return await lt.ingest_pings(
            db, uid, body.pings, datetime.now(timezone.utc))

    return await retry_on_lock(db, go, commit=True)


@router.get("/my-trail")
async def my_trail(
    db: deps.DBDep, me: deps.CurrentUser,
    work_date: Optional[pydate] = Query(default=None, alias="date"),
):
    d = work_date or datetime.now(timezone.utc).date()
    return await _trail(db, me.id, d)


async def _trail(db, user_id: int, d: pydate, since=None) -> dict:
    q = select(LocationPing).where(
        LocationPing.user_id == user_id, LocationPing.work_date == d)
    if since is not None:
        q = q.where(LocationPing.captured_at >= since)
    rows = (await db.execute(
        q.order_by(LocationPing.captured_at).limit(MAX_TRAIL + 1))
    ).scalars().all()
    return {"user_id": user_id, "date": d.isoformat(),
            "truncated": len(rows) > MAX_TRAIL,
            "points": [lt.ping_row(p) for p in rows[:MAX_TRAIL]]}


# --- schedulers ----------------------------------------------------------


@router.get("/field-now")
async def field_now(
    db: deps.DBDep, me: deps.CurrentUser, department: Optional[str] = None,
):
    scoped = await roster_svc.scoped_employees(db, me)
    if not scoped and not roster_svc.is_roster_admin(me):
        raise HTTPException(status_code=403, detail="You have no roster scope.")
    cands = [e for e in scoped if e.user_id is not None
             and (not department or e.department == department)]
    allowed = await roster_svc.manageable_subset(
        db, me, {e.user_id for e in cands})
    ids = [e.user_id for e in cands if e.user_id in allowed]
    if len(ids) > MAX_EMPLOYEES:
        raise HTTPException(
            status_code=400,
            detail=f"Too many employees ({len(ids)}); filter by department "
                   f"(max {MAX_EMPLOYEES}).")
    now = datetime.now(timezone.utc)
    reqs = await lt.requirements(db, ids)
    consents = await lt.active_consents(db, ids)
    tracked = [u for u in ids if reqs[u].required and u in consents]
    latest = {}
    if tracked:
        for p in (await db.execute(
            select(LocationPing).where(
                LocationPing.user_id.in_(tracked),
                LocationPing.captured_at >= now - lt.STALE_AFTER)
            .order_by(LocationPing.captured_at))).scalars().all():
            if lt.aware(p.captured_at) >= lt.consent_floor(consents[p.user_id]):
                latest[p.user_id] = p  # ascending: last wins
    board = {r.user_id: r for r in await live_ops.live_board(db, tracked, now)}
    rows = []
    for uid in tracked:
        r = board.get(uid)
        if r is None:
            continue
        p = latest.get(uid)
        rows.append({
            "user_id": uid, "name": r.name, "department": r.department,
            "status": r.status.value, "late_minutes": r.late_minutes,
            "shift_name": r.shift_name,
            "start_hhmm": r.start_hhmm, "end_hhmm": r.end_hhmm,
            "ping": lt.ping_row(p) if p else None,
        })
    me_id = me.id
    db.add(AuditLog(
        user_id=me_id, action="TRACKING_FIELD_NOW_VIEWED",
        resource_type="location_field_now", resource_id=None,
        details={"department": department, "count": len(rows)}))
    await db.commit()
    return {"now": now.isoformat(), "tracked": len(rows),
            "with_location": sum(1 for r in rows if r["ping"]), "rows": rows}


@router.get("/trail")
async def trail(
    db: deps.DBDep, me: deps.CurrentUser, user_id: int,
    work_date: Optional[pydate] = Query(default=None, alias="date"),
):
    d = work_date or datetime.now(timezone.utc).date()
    if user_id == me.id:
        return await _trail(db, user_id, d)
    allowed = await roster_svc.manageable_subset(db, me, {user_id})
    if user_id not in allowed:
        raise HTTPException(
            status_code=403, detail="This employee is outside your scope.")
    req = (await lt.requirements(db, [user_id]))[user_id]
    consent = (await lt.active_consents(db, [user_id])).get(user_id)
    if not req.required or consent is None:
        raise HTTPException(
            status_code=403,
            detail="Location tracking is not active for this employee.")
    out = await _trail(db, user_id, d, since=lt.consent_floor(consent))
    me_id = me.id
    db.add(AuditLog(
        user_id=me_id, action="TRACKING_TRAIL_VIEWED",
        resource_type="location_trail", resource_id=str(user_id),
        details={"date": d.isoformat(), "points": len(out["points"])}))
    await db.commit()
    return out


# --- HR admin ------------------------------------------------------------


@router.get("/policies")
async def list_policies(
    db: deps.DBDep, _: User = Depends(deps.check_permissions([HR_READ])),
):
    pols = {p.role_id: p for p in (await db.execute(
        select(TrackingPolicy))).scalars().all()}
    roles = (await db.execute(select(Role).order_by(Role.name))).scalars().all()
    return [{
        "role_id": r.id, "role_name": r.name,
        "enabled": pols[r.id].enabled if r.id in pols else False,
        "interval_seconds": pols[r.id].interval_seconds if r.id in pols
        else lt.DEFAULT_INTERVAL,
        "distance_filter_m": pols[r.id].distance_filter_m if r.id in pols
        else lt.DEFAULT_DISTANCE,
        "configured": r.id in pols,
        "updated_at": _iso(pols[r.id].updated_at) if r.id in pols else None,
    } for r in roles]


@router.put("/policies/{role_id}")
async def put_policy(
    role_id: int, body: PolicyIn, db: deps.DBDep,
    me: User = Depends(deps.check_permissions([HR_WRITE])),
):
    me_id = me.id

    async def go():
        role = await db.get(Role, role_id)
        if role is None:
            raise HTTPException(status_code=404, detail="Role not found")
        pol = await lock_row(
            db, select(TrackingPolicy).where(TrackingPolicy.role_id == role_id))
        before = None
        if pol is None:
            pol = TrackingPolicy(role_id=role_id)
            db.add(pol)
        else:
            before = {"enabled": pol.enabled,
                      "interval_seconds": pol.interval_seconds,
                      "distance_filter_m": pol.distance_filter_m}
        pol.enabled = body.enabled
        pol.interval_seconds = body.interval_seconds
        pol.distance_filter_m = body.distance_filter_m
        pol.updated_by_id = me_id
        pol.updated_at = datetime.now(timezone.utc)
        db.add(AuditLog(
            user_id=me_id, action="TRACKING_POLICY_UPDATED",
            resource_type="tracking_policy", resource_id=str(role_id),
            details={"before": before, **body.model_dump()}))
        return {"role_id": role_id, "role_name": role.name, **body.model_dump()}

    return await retry_on_lock(db, go, commit=True)


@router.get("/overrides")
async def list_overrides(
    db: deps.DBDep, _: User = Depends(deps.check_permissions([HR_READ])),
):
    rows = (await db.execute(
        select(TrackingOverride, User.full_name, User.email)
        .join(User, User.id == TrackingOverride.user_id)
        .order_by(User.full_name))).all()
    return [{"user_id": o.user_id, "name": n or e, "email": e,
             "enabled": o.enabled, "updated_at": _iso(o.updated_at)}
            for o, n, e in rows]


@router.put("/overrides/{user_id}")
async def put_override(
    user_id: int, body: OverrideIn, db: deps.DBDep,
    me: User = Depends(deps.check_permissions([HR_WRITE])),
):
    me_id = me.id

    async def go():
        if await db.get(User, user_id) is None:
            raise HTTPException(status_code=404, detail="User not found")
        o = await lock_row(
            db, select(TrackingOverride).where(
                TrackingOverride.user_id == user_id))
        if o is None:
            o = TrackingOverride(user_id=user_id, enabled=body.enabled)
            db.add(o)
        o.enabled = body.enabled
        o.updated_by_id = me_id
        o.updated_at = datetime.now(timezone.utc)
        db.add(AuditLog(
            user_id=me_id, action="TRACKING_OVERRIDE_SET",
            resource_type="tracking_override", resource_id=str(user_id),
            details={"enabled": body.enabled}))
        return {"user_id": user_id, "enabled": body.enabled}

    return await retry_on_lock(db, go, commit=True)


@router.delete("/overrides/{user_id}")
async def delete_override(
    user_id: int, db: deps.DBDep,
    me: User = Depends(deps.check_permissions([HR_WRITE])),
):
    me_id = me.id

    async def go():
        o = await lock_row(
            db, select(TrackingOverride).where(
                TrackingOverride.user_id == user_id))
        if o is None:
            raise HTTPException(status_code=404, detail="No override set")
        await db.delete(o)
        db.add(AuditLog(
            user_id=me_id, action="TRACKING_OVERRIDE_REMOVED",
            resource_type="tracking_override", resource_id=str(user_id)))
        return {"user_id": user_id, "removed": True}

    return await retry_on_lock(db, go, commit=True)


@router.get("/consents")
async def list_consents(
    db: deps.DBDep, _: User = Depends(deps.check_permissions([HR_READ])),
    status: Literal["all", "active", "revoked"] = "all",
    limit: int = Query(default=500, ge=1, le=2000),
):
    latest = (select(func.max(TrackingConsent.id).label("mid"))
              .group_by(TrackingConsent.user_id).subquery())
    q = (select(TrackingConsent, User.full_name, User.email)
         .join(latest, latest.c.mid == TrackingConsent.id)
         .join(User, User.id == TrackingConsent.user_id))
    if status == "active":
        q = q.where(TrackingConsent.revoked_at.is_(None))
    elif status == "revoked":
        q = q.where(TrackingConsent.revoked_at.is_not(None))
    rows = (await db.execute(
        q.order_by(TrackingConsent.consented_at.desc()).limit(limit))).all()
    return [{
        "user_id": c.user_id, "name": n or e, "email": e,
        "status": "revoked" if c.revoked_at else "active",
        "consented_at": _iso(c.consented_at), "revoked_at": _iso(c.revoked_at),
        "app_version": c.app_version,
    } for c, n, e in rows]
