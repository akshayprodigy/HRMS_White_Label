"""Add subtask_id to task_completion_request

Revision ID: e1f2a3b4c5d6
Revises: c9d0e1f2a3b4, a1b2c3d4e5f6
Create Date: 2026-03-25

"""

from alembic import op
import sqlalchemy as sa

revision = "e1f2a3b4c5d6"
down_revision = ("c9d0e1f2a3b4", "a1b2c3d4e5f6")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "task_completion_request",
        sa.Column("subtask_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_tcr_subtask_id",
        "task_completion_request",
        "subtask",
        ["subtask_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_task_completion_request_subtask_id",
        "task_completion_request",
        ["subtask_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_task_completion_request_subtask_id", table_name="task_completion_request")
    op.drop_constraint("fk_tcr_subtask_id", "task_completion_request", type_="foreignkey")
    op.drop_column("task_completion_request", "subtask_id")
