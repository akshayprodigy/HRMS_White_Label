"""salary component hard rupee min/max (replaces percent bounds)

Replaces the short-lived min_percent/max_percent config-guardrails with hard
rupee bounds min_amount/max_amount that clamp the resolved component value at
payroll time (e.g. HRA 50% of basic, capped ₹1500, floored ₹100). Nullable —
existing components stay unbounded, payroll output unchanged.

Revision ID: a5b6c7d8e9f0
Revises: z4a5b6c7d8e9
Create Date: 2026-08-06
"""
from alembic import op
import sqlalchemy as sa

revision = "a5b6c7d8e9f0"
down_revision = "z4a5b6c7d8e9"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("salary_component", sa.Column("min_amount", sa.Float(), nullable=True))
    op.add_column("salary_component", sa.Column("max_amount", sa.Float(), nullable=True))
    op.drop_column("salary_component", "min_percent")
    op.drop_column("salary_component", "max_percent")


def downgrade():
    op.add_column("salary_component", sa.Column("min_percent", sa.Float(), nullable=True))
    op.add_column("salary_component", sa.Column("max_percent", sa.Float(), nullable=True))
    op.drop_column("salary_component", "max_amount")
    op.drop_column("salary_component", "min_amount")
