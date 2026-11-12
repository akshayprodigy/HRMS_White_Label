"""calendar_feed_token table

Revision ID: c3f5a7b9d1e2
Revises: b8d2e4f6a1c3
Create Date: 2026-11-12
"""
from alembic import op
import sqlalchemy as sa

revision = "c3f5a7b9d1e2"
down_revision = "b8d2e4f6a1c3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "calendar_feed_token",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", name="uq_calendar_feed_token_user_id"),
        sa.UniqueConstraint("token_hash", name="uq_calendar_feed_token_token_hash"),
    )
    op.create_index("ix_calendar_feed_token_id", "calendar_feed_token", ["id"])


def downgrade():
    op.drop_table("calendar_feed_token")
