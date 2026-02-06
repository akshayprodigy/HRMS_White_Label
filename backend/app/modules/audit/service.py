from __future__ import annotations

import datetime as dt

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db.models.audit_logs import AuditLog


def query_audit_logs(
    db: Session,
    *,
    entity_type: str | None,
    entity_id: str | None,
    action: str | None,
    actor_user_id: int | None,
    request_id: str | None,
    created_from: dt.datetime | None,
    created_to: dt.datetime | None,
    limit: int,
    offset: int,
) -> list[AuditLog]:
    stmt = select(AuditLog)

    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if actor_user_id is not None:
        stmt = stmt.where(AuditLog.actor_user_id == actor_user_id)
    if request_id:
        stmt = stmt.where(AuditLog.request_id == request_id)
    if created_from:
        stmt = stmt.where(AuditLog.created_at >= created_from)
    if created_to:
        stmt = stmt.where(AuditLog.created_at <= created_to)

    stmt = stmt.order_by(desc(AuditLog.created_at)).limit(limit).offset(offset)
    return list(db.execute(stmt).scalars().all())
