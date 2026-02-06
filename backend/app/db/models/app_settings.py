from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AppSetting(Base):
    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(
        sa.BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    key: Mapped[str] = mapped_column(
        sa.String(255),
        nullable=False,
        unique=True,
    )
    value: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    created_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
        server_onupdate=sa.text("CURRENT_TIMESTAMP"),
    )

    created_by: Mapped[int | None] = mapped_column(
        sa.BigInteger,
        nullable=True,
    )
    updated_by: Mapped[int | None] = mapped_column(
        sa.BigInteger,
        nullable=True,
    )
