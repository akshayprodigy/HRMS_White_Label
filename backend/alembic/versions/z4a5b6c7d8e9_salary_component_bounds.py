"""salary component min/max percent bounds

Adds min_percent / max_percent guardrails to salary_component so HR/Accounts
can bound a component's percent-of-basic (e.g. HRA 40-50%). Nullable — existing
components are unbounded, so payroll output is unchanged.

Revision ID: z4a5b6c7d8e9
Revises: y3z4a5b6c7d8
Create Date: 2026-08-06
"""
from alembic import op
import sqlalchemy as sa

revision = "z4a5b6c7d8e9"
down_revision = "y3z4a5b6c7d8"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("salary_component", sa.Column("min_percent", sa.Float(), nullable=True))
    op.add_column("salary_component", sa.Column("max_percent", sa.Float(), nullable=True))


def downgrade():
    op.drop_column("salary_component", "max_percent")
    op.drop_column("salary_component", "min_percent")
