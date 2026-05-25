"""Add task completion request workflow

Revision ID: c9d0e1f2a3b4
Revises: b2c3d4e5f6a7, 17441bc84e66
Create Date: 2026-03-25
"""

from alembic import op
import sqlalchemy as sa

revision = "c9d0e1f2a3b4"
down_revision = ("b2c3d4e5f6a7", "17441bc84e66")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "task_completion_request",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("submitted_by_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("reviewer_notes", sa.Text(), nullable=True),
        sa.Column("reviewed_by_id", sa.Integer(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["task.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["submitted_by_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["reviewed_by_id"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_task_completion_request_id", "task_completion_request", ["id"])
    op.create_index("ix_task_completion_request_task_id", "task_completion_request", ["task_id"])
    op.create_index("ix_task_completion_request_status", "task_completion_request", ["status"])
    op.create_index("ix_task_completion_request_submitted_by_id", "task_completion_request", ["submitted_by_id"])

    op.create_table(
        "task_completion_document",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.Integer(), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("file_path", sa.String(512), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("mime_type", sa.String(100), nullable=True),
        sa.Column("uploaded_by_id", sa.Integer(), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["request_id"], ["task_completion_request.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["uploaded_by_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_task_completion_document_id", "task_completion_document", ["id"])
    op.create_index("ix_task_completion_document_request_id", "task_completion_document", ["request_id"])


def downgrade() -> None:
    op.drop_table("task_completion_document")
    op.drop_table("task_completion_request")
