from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.core.request_context import get_actor_user_id, get_request_id
from app.db.models.audit_logs import AuditLog

_EXCLUDE_FIELDS = {"password_hash"}


def _jsonify(value: Any) -> Any:  # noqa: ANN401
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    return value


def model_to_dict(model: Any) -> dict[str, Any]:  # noqa: ANN401
    mapper = inspect(model).mapper
    out: dict[str, Any] = {}
    for attr in mapper.column_attrs:
        key = attr.key
        if key in _EXCLUDE_FIELDS:
            continue
        out[key] = _jsonify(getattr(model, key))
    return out


def log_audit(
    db: Session,
    *,
    entity_type: str,
    entity_id: str,
    action: str,
    before_json: dict[str, Any] | None,
    after_json: dict[str, Any] | None,
) -> None:
    row = AuditLog(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        before_json=before_json,
        after_json=after_json,
        actor_user_id=get_actor_user_id(),
        request_id=get_request_id(),
    )

    try:
        db.add(row)
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
