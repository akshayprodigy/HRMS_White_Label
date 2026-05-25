"""Add subtask_id to time tracking

Revision ID: d7e8f9a0b1c2
Revises: c1a2b3c4d5e6
Create Date: 2026-03-12

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d7e8f9a0b1c2"
down_revision: Union[str, None] = "c1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "timer_session",
        sa.Column(
            "subtask_id",
            sa.Integer(),
            sa.ForeignKey("subtask.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        op.f("ix_timer_session_subtask_id"),
        "timer_session",
        ["subtask_id"],
        unique=False,
    )

    op.add_column(
        "timeentry",
        sa.Column(
            "subtask_id",
            sa.Integer(),
            sa.ForeignKey("subtask.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        op.f("ix_timeentry_subtask_id"),
        "timeentry",
        ["subtask_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_timeentry_subtask_id"), table_name="timeentry")
    op.drop_column("timeentry", "subtask_id")

    op.drop_index(
        op.f("ix_timer_session_subtask_id"), table_name="timer_session"
    )
    op.drop_column("timer_session", "subtask_id")
