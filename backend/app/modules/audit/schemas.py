from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class AuditLogPublic(ORMModel):
    id: int
    entity_type: str
    entity_id: str
    action: str
    before_json: dict | None = None
    after_json: dict | None = None
    actor_user_id: int | None = None
    request_id: str | None = None
    created_at: dt.datetime
