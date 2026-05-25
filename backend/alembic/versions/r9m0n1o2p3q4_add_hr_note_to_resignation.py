"""add hr_note to resignation

Captures the latest HR comment when a resignation is cancelled or
expedited. Full per-action history lives in the audit log; this column
exists for at-a-glance display on the exit page.

Revision ID: r9m0n1o2p3q4
Revises: q8l9m0n1o2p3
Create Date: 2026-04-30
"""
from alembic import op
import sqlalchemy as sa

revision = "r9m0n1o2p3q4"
down_revision = "q8l9m0n1o2p3"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "resignation",
        sa.Column("hr_note", sa.Text(), nullable=True),
    )


def downgrade():
    op.drop_column("resignation", "hr_note")
