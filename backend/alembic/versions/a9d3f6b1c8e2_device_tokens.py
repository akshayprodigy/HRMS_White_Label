"""device tokens for mobile push

Revision ID: a9d3f6b1c8e2
Revises: c4f8a1d2e9b6
Create Date: 2026-11-13
"""
import sqlalchemy as sa
from alembic import op

revision = "a9d3f6b1c8e2"
down_revision = "c4f8a1d2e9b6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "device_token",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer,
                  sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("platform", sa.String(10), nullable=False),
        sa.Column("token", sa.String(255), nullable=False),
        sa.Column("app_version", sa.String(32), nullable=True),
        sa.Column("tenant", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("token", name="uq_device_token_token"),
    )
    op.create_index("ix_device_token_id", "device_token", ["id"])
    op.create_index("ix_device_token_user_id", "device_token", ["user_id"])


def downgrade():
    op.drop_table("device_token")
