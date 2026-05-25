"""Add bid line items table

Revision ID: d8a2b7c9f1c0
Revises: c3a1d2f4e5aa
Create Date: 2026-03-23

Adds an admin-managed catalog of bid-task line item templates.
BD can pick from these templates when creating bid tasks, while still
being able to type custom tasks.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d8a2b7c9f1c0"
down_revision: Union[str, None] = "c3a1d2f4e5aa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bid_line_item",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )

    op.create_index("ix_bid_line_item_title", "bid_line_item", ["title"])
    op.create_index(
        "ix_bid_line_item_active",
        "bid_line_item",
        ["is_active"],
    )


def downgrade() -> None:
    op.drop_index("ix_bid_line_item_active", table_name="bid_line_item")
    op.drop_index("ix_bid_line_item_title", table_name="bid_line_item")
    op.drop_table("bid_line_item")
