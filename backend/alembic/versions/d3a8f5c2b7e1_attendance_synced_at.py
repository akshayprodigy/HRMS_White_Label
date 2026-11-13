"""attendance.synced_at (server receipt time of offline punches)

Revision ID: d3a8f5c2b7e1
Revises: c7d1e4f8a2b9
Create Date: 2026-11-13
"""
import sqlalchemy as sa
from alembic import op

revision = "d3a8f5c2b7e1"
down_revision = "c7d1e4f8a2b9"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("attendance", sa.Column(
        "synced_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("attendance", "synced_at")
