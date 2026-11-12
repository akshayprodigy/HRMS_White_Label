"""shift_drop_request table

Revision ID: b8d2e4f6a1c3
Revises: a7c1d9e3f5b2
Create Date: 2026-11-12
"""
from alembic import op
import sqlalchemy as sa

revision = "b8d2e4f6a1c3"
down_revision = "a7c1d9e3f5b2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "shift_drop_request",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("shift_template_id", sa.Integer(), sa.ForeignKey("shift_template.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("post_open_shift", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("open_shift_id", sa.Integer(), sa.ForeignKey("open_shift.id", ondelete="SET NULL"), nullable=True),
        sa.Column("decided_by_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_shift_drop_request_id", "shift_drop_request", ["id"])
    op.create_index("ix_shift_drop_user_status", "shift_drop_request", ["user_id", "status"])
    op.create_index("ix_shift_drop_status_date", "shift_drop_request", ["status", "work_date"])


def downgrade():
    op.drop_table("shift_drop_request")
