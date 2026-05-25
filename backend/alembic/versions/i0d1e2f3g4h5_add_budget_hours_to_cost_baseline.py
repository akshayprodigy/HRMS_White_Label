"""Add budget_hours to cost_baseline

Revision ID: i0d1e2f3g4h5
Revises: h9c0d1e2f3g4
Create Date: 2026-03-27

"""
from alembic import op
import sqlalchemy as sa

revision = "i0d1e2f3g4h5"
down_revision = "h9c0d1e2f3g4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "costbaseline",
        sa.Column(
            "budget_hours",
            sa.Numeric(12, 2),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("costbaseline", "budget_hours")
