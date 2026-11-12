"""lock window: history.is_emergency, schedule_change_ack, delegation override

Revision ID: d6f8a1c3e5b7
Revises: c4e6a8b1d3f5
Create Date: 2026-11-13
"""
from alembic import op
import sqlalchemy as sa

revision = "d6f8a1c3e5b7"
down_revision = "c4e6a8b1d3f5"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("roster_entry_history", sa.Column(
        "is_emergency", sa.Boolean(), nullable=False, server_default="0"))
    op.add_column("schedule_delegation", sa.Column(
        "can_emergency_override", sa.Boolean(), nullable=False,
        server_default="0"))
    op.create_table(
        "schedule_change_ack",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("history_id", sa.Integer(), sa.ForeignKey(
            "roster_entry_history.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey(
            "user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("history_id", "user_id",
                            name="uq_sched_ack_hist_user"),
    )
    op.create_index("ix_schedule_change_ack_id", "schedule_change_ack", ["id"])
    op.create_index("ix_schedule_change_ack_history_id",
                    "schedule_change_ack", ["history_id"])
    op.create_index("ix_schedule_change_ack_user_id",
                    "schedule_change_ack", ["user_id"])


def downgrade():
    op.drop_table("schedule_change_ack")
    op.drop_column("schedule_delegation", "can_emergency_override")
    op.drop_column("roster_entry_history", "is_emergency")
