"""Add parent_subtask_id to subtask

Revision ID: f1c0d2e4a6b8
Revises: d7e8f9a0b1c2
Create Date: 2026-03-12

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f1c0d2e4a6b8"
down_revision: Union[str, None] = "d7e8f9a0b1c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "subtask",
        sa.Column(
            "parent_subtask_id",
            sa.Integer(),
            sa.ForeignKey("subtask.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_index(
        op.f("ix_subtask_parent_subtask_id"),
        "subtask",
        ["parent_subtask_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_subtask_parent_subtask_id"),
        table_name="subtask",
    )
    op.drop_column("subtask", "parent_subtask_id")
