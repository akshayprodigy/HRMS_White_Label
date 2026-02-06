from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column


class AuditMixin:
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
