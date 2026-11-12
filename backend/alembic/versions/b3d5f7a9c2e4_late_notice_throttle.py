"""late_notice posted_at / last_notified_at / cleared_at

Revision ID: b3d5f7a9c2e4
Revises: a2c4e6f8b1d3
Create Date: 2026-11-13
"""
from alembic import op
import sqlalchemy as sa

revision = "b3d5f7a9c2e4"
down_revision = "a2c4e6f8b1d3"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("late_notice", sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("late_notice", sa.Column("last_notified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("late_notice", sa.Column("cleared_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE late_notice SET posted_at = created_at, last_notified_at = created_at")


def downgrade():
    op.drop_column("late_notice", "cleared_at")
    op.drop_column("late_notice", "last_notified_at")
    op.drop_column("late_notice", "posted_at")
