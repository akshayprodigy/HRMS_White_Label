"""add termination_type column to resignation (Section M B4)

Pure additive — nullable, no backfill. Fetcher treats NULL as VOLUNTARY.

Revision ID: j7e8f9g0h1i2
Revises: i6d7e8f9g0h1
Create Date: 2026-07-01
"""
from alembic import op
import sqlalchemy as sa


revision = "j7e8f9g0h1i2"
down_revision = "i6d7e8f9g0h1"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "resignation",
        sa.Column("termination_type", sa.String(16), nullable=True),
    )
    op.create_index(
        "ix_resignation_termination_type",
        "resignation", ["termination_type"],
    )


def downgrade():
    op.drop_index(
        "ix_resignation_termination_type", table_name="resignation"
    )
    op.drop_column("resignation", "termination_type")
