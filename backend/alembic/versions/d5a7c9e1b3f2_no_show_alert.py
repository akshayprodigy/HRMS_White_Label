"""no_show_alert table

Revision ID: d5a7c9e1b3f2
Revises: c3f5a7b9d1e2
Create Date: 2026-11-12
"""
from alembic import op
import sqlalchemy as sa

revision = "d5a7c9e1b3f2"
down_revision = "c3f5a7b9d1e2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "no_show_alert",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("shift_template_id", sa.Integer(), sa.ForeignKey("shift_template.id", ondelete="CASCADE"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "work_date", name="uq_no_show_alert_user_date"),
    )
    op.create_index("ix_no_show_alert_id", "no_show_alert", ["id"])
    op.create_index("ix_no_show_alert_shift_template_id", "no_show_alert", ["shift_template_id"])


def downgrade():
    op.drop_table("no_show_alert")
