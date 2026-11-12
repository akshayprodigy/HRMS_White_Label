"""emergency leave columns

Revision ID: f1c3e5a7b9d2
Revises: e7b9d1f3a5c4
Create Date: 2026-11-13
"""
from alembic import op
import sqlalchemy as sa

revision = "f1c3e5a7b9d2"
down_revision = "e7b9d1f3a5c4"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("leaverequest", sa.Column(
        "is_emergency", sa.Boolean(), nullable=False, server_default="0"))
    op.add_column("leaverequest", sa.Column("proof_due_date", sa.Date(), nullable=True))
    op.add_column("leaverequest", sa.Column(
        "proof_submitted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("leaverequest", sa.Column(
        "converted_to_lop_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("leaverequest", "converted_to_lop_at")
    op.drop_column("leaverequest", "proof_submitted_at")
    op.drop_column("leaverequest", "proof_due_date")
    op.drop_column("leaverequest", "is_emergency")
