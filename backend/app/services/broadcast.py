"""Emergency broadcast: audience resolution + send (Roadmap v2 Phase 2, T7)."""
from datetime import datetime, timezone
from typing import Iterable, List, Optional

from fastapi import HTTPException
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.broadcast import (
    Broadcast, BroadcastAudience, BroadcastRecipient, BroadcastSeverity,
)
from app.models.employee import Employee, EmployeeStatus
from app.models.user import User
from app.services import live_ops
from app.services.notifications_delivery import notify_emergency_bulk

ON_SHIFT_STATUSES = (
    live_ops.LiveStatus.ON_SHIFT,
    live_ops.LiveStatus.NOT_ARRIVED,
    live_ops.LiveStatus.RUNNING_LATE,
)
_CHUNK = 500


async def resolve_audience(
    db: AsyncSession, audience: str, value: Optional[str] = None, *,
    now: Optional[datetime] = None,
    user_scope: Optional[Iterable[int]] = None,
) -> List[int]:
    """User ids for the audience. `user_scope` (tests / future restricted
    senders) intersects the result with the given user ids."""
    if audience not in BroadcastAudience.ALL:
        raise HTTPException(400, "Invalid audience")
    q = (select(Employee.user_id)
         .join(User, User.id == Employee.user_id)
         .where(Employee.status == EmployeeStatus.ACTIVE,
                User.is_active.is_(True)))
    if audience == BroadcastAudience.LOCATION:
        if not value:
            raise HTTPException(400, "audience_value is required for location")
        q = q.where(Employee.location == value)
    elif audience == BroadcastAudience.DEPARTMENT:
        if not value:
            raise HTTPException(400, "audience_value is required for department")
        q = q.where(Employee.department == value)
    if user_scope is not None:
        scope = list(set(user_scope))
        if not scope:
            return []
        q = q.where(Employee.user_id.in_(scope))
    ids = sorted((await db.execute(q)).scalars().all())
    if audience == BroadcastAudience.ON_SHIFT and ids:
        rows = await live_ops.live_board(
            db, ids, now or datetime.now(timezone.utc))
        ids = sorted(r.user_id for r in rows if r.status in ON_SHIFT_STATUSES)
    return ids


async def create_and_send(
    db: AsyncSession, *, sender_id: int, title: str, message: str,
    severity: str, audience: str, audience_value: Optional[str],
    requires_ack: bool, safety_check: bool,
    now: Optional[datetime] = None,
    user_scope: Optional[Iterable[int]] = None,
) -> Broadcast:
    """Create the broadcast, its recipients and all notifications /
    deliveries in batches. Caller commits."""
    if severity not in BroadcastSeverity.ALL:
        raise HTTPException(400, "Invalid severity")
    ids = await resolve_audience(
        db, audience, audience_value, now=now, user_scope=user_scope)
    if not ids:
        raise HTTPException(400, "No recipients match this audience")
    b = Broadcast(
        title=title, message=message, severity=severity, audience=audience,
        audience_value=audience_value if audience in ("location", "department") else None,
        requires_ack=requires_ack, safety_check=safety_check,
        created_by_id=sender_id)
    db.add(b)
    await db.flush()
    for i in range(0, len(ids), _CHUNK):
        await db.execute(insert(BroadcastRecipient), [
            {"broadcast_id": b.id, "user_id": u} for u in ids[i:i + _CHUNK]])
    await notify_emergency_bulk(
        db, user_ids=ids, event_type="emergency_broadcast",
        title=title, message=message,
        resource_type="broadcast", resource_id=str(b.id),
        context={"title": title, "message": message,
                 "severity": severity.upper()},
        notif_type="error" if severity == BroadcastSeverity.CRITICAL else "warning")
    return b
