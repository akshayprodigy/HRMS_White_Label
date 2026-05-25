"""add timer_session table

Revision ID: 2d5a9455d95c
Revises: 163a6257061f
Create Date: 2026-02-22 07:06:10.346635

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2d5a9455d95c'
down_revision: Union[str, None] = '163a6257061f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "timer_session",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("running", "paused", "stopped", name="timerstatus"),
            nullable=False,
            server_default="running",
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "accumulated_seconds",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "last_state_change_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"], ["project.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_timer_session_id"), "timer_session", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_timer_session_user_id"),
        "timer_session",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_timer_session_project_id"),
        "timer_session",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_timer_session_status"),
        "timer_session",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_timer_session_status"), table_name="timer_session")
    op.drop_index(
        op.f("ix_timer_session_project_id"), table_name="timer_session"
    )
    op.drop_index(op.f("ix_timer_session_user_id"), table_name="timer_session")
    op.drop_index(op.f("ix_timer_session_id"), table_name="timer_session")
    op.drop_table("timer_session")
