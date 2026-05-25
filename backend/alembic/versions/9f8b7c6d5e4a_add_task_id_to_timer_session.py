"""add task_id to timer_session

Revision ID: 9f8b7c6d5e4a
Revises: 618c43194869
Create Date: 2026-02-27

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9f8b7c6d5e4a"
down_revision: Union[str, None] = "618c43194869"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "timer_session",
        sa.Column("task_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        op.f("ix_timer_session_task_id"),
        "timer_session",
        ["task_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_timer_session_task_id_task",
        "timer_session",
        "task",
        ["task_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_timer_session_task_id_task",
        "timer_session",
        type_="foreignkey",
    )
    op.drop_index(op.f("ix_timer_session_task_id"), table_name="timer_session")
    op.drop_column("timer_session", "task_id")
