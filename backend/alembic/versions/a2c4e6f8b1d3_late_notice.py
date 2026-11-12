"""late_notice table

Revision ID: a2c4e6f8b1d3
Revises: f1c3e5a7b9d2
Create Date: 2026-11-13
"""
from alembic import op
import sqlalchemy as sa

revision = "a2c4e6f8b1d3"
down_revision = "f1c3e5a7b9d2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "late_notice",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("expected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "work_date", name="uq_late_notice_user_date"),
    )
    op.create_index("ix_late_notice_id", "late_notice", ["id"])


def downgrade():
    op.drop_index("ix_late_notice_id", table_name="late_notice")
    op.drop_table("late_notice")
