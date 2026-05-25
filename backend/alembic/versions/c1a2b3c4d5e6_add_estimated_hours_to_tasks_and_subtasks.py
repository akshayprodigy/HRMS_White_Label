"""Add estimated hours to tasks and subtasks

Revision ID: c1a2b3c4d5e6
Revises: 4c9e8b0f1a2b
Create Date: 2026-03-12

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c1a2b3c4d5e6"
down_revision: Union[str, None] = "4c9e8b0f1a2b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "task",
        sa.Column("estimated_hours", sa.Numeric(12, 2), nullable=True),
    )

    op.add_column(
        "subtask",
        sa.Column("estimated_hours", sa.Numeric(12, 2), nullable=True),
    )
    op.add_column(
        "subtask",
        sa.Column(
            "assignee_id",
            sa.Integer(),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        op.f("ix_task_estimated_hours"),
        "task",
        ["estimated_hours"],
        unique=False,
    )
    op.create_index(
        op.f("ix_subtask_assignee_id"),
        "subtask",
        ["assignee_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_subtask_assignee_id"), table_name="subtask")
    op.drop_index(op.f("ix_task_estimated_hours"), table_name="task")

    op.drop_column("subtask", "assignee_id")
    op.drop_column("subtask", "estimated_hours")

    op.drop_column("task", "estimated_hours")
