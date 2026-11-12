"""Emergency broadcast & mark-me-safe (Roadmap v2 Phase 2, Task 7).

Sender endpoints need 'broadcast send'. /broadcasts/my, /read, /ack and
/safety are open to any authenticated user (own recipient row only) and are
deliberately NOT attendance-gated: people must be able to respond before they
punch in.
"""
from datetime import datetime, timezone
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import case, func, select

from app.api import deps
from app.api.v1.endpoints.roster_common import commit_or_409, retry_on_lock
from app.models.broadcast import (
    Broadcast, BroadcastAudience, BroadcastRecipient, BroadcastSeverity,
    SafetyStatus,
)
from app.models.employee import Employee
from app.models.user import Permission, User, role_permissions, user_roles
from app.services import broadcast as svc
from app.services.notifications_delivery import notify

router = APIRouter()
SENDER = Depends(deps.check_permissions(["broadcast send"]))
PAGE_MAX = 200


class BroadcastIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=900)
    severity: Literal["info", "warning", "critical"] = "warning"
    audience: Literal["all", "location", "department", "on_shift"]
    audience_value: Optional[str] = Field(default=None, max_length=100)
    requires_ack: bool = False
    safety_check: bool = False

    @field_validator("title", "message")
    @classmethod
    def _strip(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v


class SafetyIn(BaseModel):
    status: Literal["safe", "need_help"]
    note: Optional[str] = Field(default=None, max_length=500)


def _aware(dt):
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _iso(dt):
    dt = _aware(dt)
    return dt.isoformat() if dt else None


def _no_response(b: Broadcast):
    """SQL predicate: recipient has not taken the action the broadcast asks for."""
    R = BroadcastRecipient
    if b.safety_check:
        return R.safety_status.is_(None)
    if b.requires_ack:
        return R.acked_at.is_(None)
    return R.read_at.is_(None)


async def _counts(db, ids: List[int]) -> dict:
    if not ids:
        return {}
    R = BroadcastRecipient
    rows = (await db.execute(
        select(
            R.broadcast_id, func.count(),
            func.count(R.read_at), func.count(R.acked_at),
            func.sum(case((R.safety_status == "safe", 1), else_=0)),
            func.sum(case((R.safety_status == "need_help", 1), else_=0)),
        ).where(R.broadcast_id.in_(ids)).group_by(R.broadcast_id)
    )).all()
    return {r[0]: {"total": r[1], "read": r[2], "acked": r[3],
                   "safe": int(r[4] or 0), "need_help": int(r[5] or 0)}
            for r in rows}


def _summary(b: Broadcast, c: dict, creator: Optional[str]) -> dict:
    c = c or {"total": 0, "read": 0, "acked": 0, "safe": 0, "need_help": 0}
    responded = c["safe"] + c["need_help"]
    if b.safety_check:
        no_resp = c["total"] - responded
    elif b.requires_ack:
        no_resp = c["total"] - c["acked"]
    else:
        no_resp = c["total"] - c["read"]
    return {
        "id": b.id, "title": b.title, "message": b.message,
        "severity": b.severity, "audience": b.audience,
        "audience_value": b.audience_value,
        "requires_ack": b.requires_ack, "safety_check": b.safety_check,
        "created_by_id": b.created_by_id, "created_by_name": creator,
        "created_at": _iso(b.created_at), "closed_at": _iso(b.closed_at),
        "counts": {**c, "no_response": max(no_resp, 0)},
    }


async def _creator_names(db, bs):
    ids = {b.created_by_id for b in bs}
    if not ids:
        return {}
    return {i: (n or e) for i, n, e in (await db.execute(
        select(User.id, User.full_name, User.email).where(User.id.in_(ids))
    )).all()}


# ------------------------------ sender side ------------------------------

@router.post("")
async def send_broadcast(body: BroadcastIn, db: deps.DBDep,
                         me: User = SENDER):
    if body.audience in ("location", "department") and not (
            body.audience_value or "").strip():
        raise HTTPException(400, "audience_value is required")
    b = await svc.create_and_send(
        db, sender_id=me.id, title=body.title, message=body.message,
        severity=body.severity, audience=body.audience,
        audience_value=(body.audience_value or "").strip() or None,
        requires_ack=body.requires_ack, safety_check=body.safety_check)
    await commit_or_409(db)
    c = await _counts(db, [b.id])
    return _summary(b, c.get(b.id), me.full_name or me.email)


@router.get("")
async def list_broadcasts(
    db: deps.DBDep, me: User = SENDER,
    page: int = Query(1, ge=1, le=10000), page_size: int = Query(50, ge=1, le=PAGE_MAX),
):
    total = (await db.execute(select(func.count()).select_from(Broadcast))).scalar_one()
    bs = (await db.execute(
        select(Broadcast).order_by(Broadcast.created_at.desc(), Broadcast.id.desc())
        .limit(page_size).offset((page - 1) * page_size)
    )).scalars().all()
    counts = await _counts(db, [b.id for b in bs])
    names = await _creator_names(db, bs)
    return {"total": total, "page": page, "page_size": page_size,
            "items": [_summary(b, counts.get(b.id), names.get(b.created_by_id))
                      for b in bs]}


@router.get("/audience-options")
async def audience_options(db: deps.DBDep, me: User = SENDER):
    """Distinct departments / locations of active employees (with headcount)
    for the compose form."""
    from app.models.employee import EmployeeStatus

    async def grp(col):
        return [{"value": v, "count": n} for v, n in (await db.execute(
            select(col, func.count()).where(
                Employee.status == EmployeeStatus.ACTIVE,
                col.is_not(None), col != "")
            .group_by(col).order_by(col))).all()]
    return {"departments": await grp(Employee.department),
            "locations": await grp(Employee.location)}


# --------------------------- recipient side (own) ---------------------------

def _my_row(b: Broadcast, r: BroadcastRecipient) -> dict:
    pending = ((b.safety_check and r.safety_status is None)
               or (b.requires_ack and r.acked_at is None)
               or (not b.safety_check and not b.requires_ack and r.read_at is None))
    return {
        "id": b.id, "title": b.title, "message": b.message,
        "severity": b.severity, "requires_ack": b.requires_ack,
        "safety_check": b.safety_check, "created_at": _iso(b.created_at),
        "read_at": _iso(r.read_at), "acked_at": _iso(r.acked_at),
        "safety_status": r.safety_status, "safety_note": r.safety_note,
        "responded_at": _iso(r.responded_at), "pending": bool(pending),
    }


@router.get("/my")
async def my_broadcasts(db: deps.DBDep, me: deps.CurrentUser):
    rows = (await db.execute(
        select(Broadcast, BroadcastRecipient)
        .join(BroadcastRecipient, BroadcastRecipient.broadcast_id == Broadcast.id)
        .where(BroadcastRecipient.user_id == me.id, Broadcast.closed_at.is_(None))
        .order_by(Broadcast.created_at.desc(), Broadcast.id.desc())
        .limit(50)
    )).all()
    return [_my_row(b, r) for b, r in rows]


async def _own(db, broadcast_id: int, me_id: int):
    # The caller's own recipient row is the very first thing locked/read so
    # concurrent responders serialise on it.
    r = (await db.execute(
        select(BroadcastRecipient)
        .where(BroadcastRecipient.broadcast_id == broadcast_id,
               BroadcastRecipient.user_id == me_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )).scalar_one_or_none()
    b = await db.get(Broadcast, broadcast_id, populate_existing=True)
    if b is None or r is None:
        raise HTTPException(404, "Broadcast not found")
    return b, r


async def _respond(db, fn):
    """Recipient write via retry_on_lock: concurrent duplicates serialise on
    the recipient row and all return the idempotent result. `fn` must return
    a plain dict and must not commit."""
    return await retry_on_lock(db, fn, commit=True)


@router.post("/{broadcast_id}/read")
async def mark_read(broadcast_id: int, db: deps.DBDep, me: deps.CurrentUser):
    me_id = me.id

    async def go():
        b, r = await _own(db, broadcast_id, me_id)
        if r.read_at is None:
            r.read_at = datetime.now(timezone.utc).replace(microsecond=0)
        return _my_row(b, r)
    return await _respond(db, go)


@router.post("/{broadcast_id}/ack")
async def acknowledge(broadcast_id: int, db: deps.DBDep, me: deps.CurrentUser):
    me_id = me.id

    async def go():
        b, r = await _own(db, broadcast_id, me_id)
        if b.closed_at is not None and r.acked_at is None:
            raise HTTPException(400, "Broadcast is closed")
        if r.acked_at is None:
            now = datetime.now(timezone.utc).replace(microsecond=0)
            r.acked_at = now
            r.read_at = r.read_at or now
            r.responded_at = r.responded_at or now
        return _my_row(b, r)
    return await _respond(db, go)


async def _alert_recipients(db, b: Broadcast, exclude: int) -> List[int]:
    """Who is alerted on need_help: the broadcast's creator plus every active
    holder of 'broadcast send' via a role (superusers need not be listed)."""
    holders = (await db.execute(
        select(User.id).distinct()
        .join(user_roles, user_roles.c.user_id == User.id)
        .join(role_permissions, role_permissions.c.role_id == user_roles.c.role_id)
        .join(Permission, Permission.id == role_permissions.c.permission_id)
        .where(Permission.name == "broadcast send", User.is_active.is_(True))
    )).scalars().all()
    return sorted(({b.created_by_id, *holders}) - {exclude})


@router.post("/{broadcast_id}/safety")
async def mark_safety(broadcast_id: int, body: SafetyIn, db: deps.DBDep,
                      me: deps.CurrentUser):
    me_id, me_name = me.id, (me.full_name or me.email)

    async def go():
        return await _safety(db, broadcast_id, body, me_id, me_name)
    return await _respond(db, go)


async def _safety(db, broadcast_id, body, me_id, me_name):
    b, r = await _own(db, broadcast_id, me_id)
    if not b.safety_check:
        raise HTTPException(400, "This broadcast has no safety check")
    if b.closed_at is not None:
        raise HTTPException(400, "Broadcast is closed")
    note = (body.note or "").strip() or None
    unchanged = (r.safety_status == body.status
                 and (r.safety_note or None) == note)
    if unchanged:
        return _my_row(b, r)
    became_help = (body.status == SafetyStatus.NEED_HELP
                   and r.safety_status != SafetyStatus.NEED_HELP)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    r.safety_status = body.status
    r.safety_note = note
    r.responded_at = now
    r.read_at = r.read_at or now
    if b.requires_ack and r.acked_at is None:
        r.acked_at = now  # responding to the safety check acknowledges it
    if became_help:
        emp = (await db.execute(
            select(Employee.department, Employee.location)
            .where(Employee.user_id == me_id))).first()
        who = me_name
        where = ", ".join(x for x in (emp or ()) if x)
        title = f"{who} needs help"[:200]
        msg = (f"{who} reported NEED HELP for broadcast '{b.title}'"
               + (f" ({where})" if where else "")
               + (f": {note}" if note else ""))[:1000]
        for uid in await _alert_recipients(db, b, me_id):
            await notify(
                db, user_id=uid, event_type="emergency_need_help",
                title=title, message=msg, resource_type="broadcast",
                resource_id=str(b.id), notif_type="error",
                context={"title": title, "message": msg})
    return _my_row(b, r)


# ------------------------- sender detail / close -------------------------

@router.post("/{broadcast_id}/close")
async def close_broadcast(broadcast_id: int, db: deps.DBDep, me: User = SENDER):
    b = (await db.execute(
        select(Broadcast).where(Broadcast.id == broadcast_id).with_for_update()
    )).scalar_one_or_none()
    if b is None:
        raise HTTPException(404, "Broadcast not found")
    if b.closed_at is None:
        b.closed_at = datetime.now(timezone.utc)
        await commit_or_409(db)
    c = await _counts(db, [b.id])
    n = await _creator_names(db, [b])
    return _summary(b, c.get(b.id), n.get(b.created_by_id))


@router.get("/{broadcast_id}")
async def broadcast_dashboard(
    broadcast_id: int, db: deps.DBDep, me: User = SENDER,
    filter: Optional[Literal["need_help", "no_response", "safe",
                             "acked", "read"]] = None,
    search: Optional[str] = Query(None, max_length=100),
    page: int = Query(1, ge=1, le=10000), page_size: int = Query(50, ge=1, le=PAGE_MAX),
):
    b = await db.get(Broadcast, broadcast_id)
    if b is None:
        raise HTTPException(404, "Broadcast not found")
    R = BroadcastRecipient
    q = (select(R, User.full_name, User.email, Employee.department,
                Employee.location)
         .join(User, User.id == R.user_id)
         .outerjoin(Employee, Employee.user_id == R.user_id)
         .where(R.broadcast_id == b.id))
    if filter == "need_help":
        q = q.where(R.safety_status == "need_help")
    elif filter == "safe":
        q = q.where(R.safety_status == "safe")
    elif filter == "no_response":
        q = q.where(_no_response(b))
    elif filter == "acked":
        q = q.where(R.acked_at.is_not(None))
    elif filter == "read":
        q = q.where(R.read_at.is_not(None))
    if search:
        like = f"%{search.strip()}%"
        q = q.where((User.full_name.ilike(like)) | (User.email.ilike(like)))
    total = (await db.execute(
        select(func.count()).select_from(q.subquery()))).scalar_one()
    q = q.order_by(
        case((R.safety_status == "need_help", 0), else_=1),
        case((_no_response(b), 0), else_=1),
        User.full_name, R.id,
    ).limit(page_size).offset((page - 1) * page_size)
    rows = (await db.execute(q)).all()
    c = await _counts(db, [b.id])
    n = await _creator_names(db, [b])
    return {
        **_summary(b, c.get(b.id), n.get(b.created_by_id)),
        "recipients_total": total, "page": page, "page_size": page_size,
        "recipients": [{
            "user_id": r.user_id, "name": name or email, "email": email,
            "department": dept, "location": loc,
            "read_at": _iso(r.read_at), "acked_at": _iso(r.acked_at),
            "safety_status": r.safety_status, "safety_note": r.safety_note,
            "responded_at": _iso(r.responded_at),
        } for r, name, email, dept, loc in rows],
    }
