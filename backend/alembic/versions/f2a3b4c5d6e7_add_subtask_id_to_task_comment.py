"""Add subtask_id to task_comment

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-03-25

"""

from alembic import op
import sqlalchemy as sa

revision = "f2a3b4c5d6e7"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "taskcomment",
        sa.Column("subtask_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_tc_subtask_id",
        "taskcomment",
        "subtask",
        ["subtask_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_taskcomment_subtask_id",
        "taskcomment",
        ["subtask_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_taskcomment_subtask_id", table_name="taskcomment")
    op.drop_constraint("fk_tc_subtask_id", "taskcomment", type_="foreignkey")
    op.drop_column("taskcomment", "subtask_id")
