"""roster_entry_history + roster_publish_request tables

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-11-12
"""
from alembic import op
import sqlalchemy as sa

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "roster_entry_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("roster_entry_id", sa.Integer(), sa.ForeignKey("roster_entry.id", ondelete="SET NULL"), nullable=True),
        sa.Column("old_shift_template_id", sa.Integer(), nullable=True),
        sa.Column("old_is_week_off", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("new_shift_template_id", sa.Integer(), nullable=True),
        sa.Column("new_is_week_off", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("changed_by_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_roster_entry_history_id", "roster_entry_history", ["id"])
    op.create_index("ix_roster_entry_history_employee_id", "roster_entry_history", ["employee_id"])
    op.create_index("ix_roster_entry_history_work_date", "roster_entry_history", ["work_date"])
    op.create_index("ix_roster_entry_history_changed_at", "roster_entry_history", ["changed_at"])

    op.create_table(
        "roster_publish_request",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("requested_by_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("start", sa.Date(), nullable=False),
        sa.Column("end", sa.Date(), nullable=False),
        sa.Column("department", sa.String(100), nullable=True),
        sa.Column("employee_ids", sa.JSON(), nullable=False),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("decided_by_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_roster_publish_request_id", "roster_publish_request", ["id"])
    op.create_index("ix_roster_publish_request_requested_by_id", "roster_publish_request", ["requested_by_id"])
    op.create_index("ix_roster_publish_request_status", "roster_publish_request", ["status"])


def downgrade():
    op.drop_table("roster_publish_request")
    op.drop_table("roster_entry_history")
