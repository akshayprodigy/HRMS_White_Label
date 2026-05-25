"""add punch_out_time to attendance

Pairs with the new POST /attendance/punch-out endpoint. Nullable so existing
rows (already punched in but never punched out) stay valid.

Revision ID: u2p3q4r5s6t7
Revises: t1o2p3q4r5s6
Create Date: 2026-04-30
"""
from alembic import op
import sqlalchemy as sa

revision = "u2p3q4r5s6t7"
down_revision = "t1o2p3q4r5s6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "attendance",
        sa.Column(
            "punch_out_time",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade():
    op.drop_column("attendance", "punch_out_time")
