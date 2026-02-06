from __future__ import annotations

import datetime as dt

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.mixins import AuditMixin


class RefreshToken(AuditMixin, Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(
        sa.BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    user_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey("users.id"),
        nullable=False,
    )
    jti: Mapped[str] = mapped_column(
        sa.String(64),
        nullable=False,
        unique=True,
    )
    expires_at: Mapped[dt.datetime] = mapped_column(
        sa.DateTime(),
        nullable=False,
    )
    revoked_at: Mapped[dt.datetime | None] = mapped_column(
        sa.DateTime(),
        nullable=True,
    )

    user = relationship("app.db.models.iam.User")

    __table_args__ = (
        sa.Index("ix_refresh_tokens_user_id", "user_id"),
        sa.Index("ix_refresh_tokens_expires_at", "expires_at"),
    )
