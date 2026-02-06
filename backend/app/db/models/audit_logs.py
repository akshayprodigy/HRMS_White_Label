from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(
        sa.BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    entity_type: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    entity_id: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    action: Mapped[str] = mapped_column(sa.String(20), nullable=False)

    before_json: Mapped[dict | None] = mapped_column(sa.JSON(), nullable=True)
    after_json: Mapped[dict | None] = mapped_column(sa.JSON(), nullable=True)

    actor_user_id: Mapped[int | None] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey("users.id"),
        nullable=True,
    )

    request_id: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)

    created_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        sa.Index("ix_audit_logs_entity", "entity_type", "entity_id"),
        sa.Index("ix_audit_logs_action", "action"),
        sa.Index("ix_audit_logs_actor_user_id", "actor_user_id"),
        sa.Index("ix_audit_logs_created_at", "created_at"),
        sa.Index("ix_audit_logs_request_id", "request_id"),
    )
