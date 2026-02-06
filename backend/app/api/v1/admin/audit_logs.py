from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import require_permissions
from app.core.database import get_db
from app.modules.audit.schemas import AuditLogPublic
from app.modules.audit.service import query_audit_logs

router = APIRouter(prefix="/audit-logs")


@router.get(
    "",
    response_model=list[AuditLogPublic],
    dependencies=[Depends(require_permissions({"admin.audit_logs.read"}))],
)
def admin_query_audit_logs(
    entity_type: str | None = None,
    entity_id: str | None = None,
    action: str | None = None,
    actor_user_id: int | None = None,
    request_id: str | None = None,
    created_from: dt.datetime | None = None,
    created_to: dt.datetime | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[AuditLogPublic]:
    rows = query_audit_logs(
        db,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        actor_user_id=actor_user_id,
        request_id=request_id,
        created_from=created_from,
        created_to=created_to,
        limit=limit,
        offset=offset,
    )
    return [AuditLogPublic.model_validate(r) for r in rows]
