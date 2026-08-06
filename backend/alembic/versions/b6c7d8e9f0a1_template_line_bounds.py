"""per-template-line hard rupee bounds

Adds min_amount/max_amount to salary_template_component so a template LINE can
set its own floor/cap (overriding the component default). Nullable — existing
lines are unbounded, payroll output unchanged.

Revision ID: b6c7d8e9f0a1
Revises: a5b6c7d8e9f0
Create Date: 2026-08-06
"""
from alembic import op
import sqlalchemy as sa

revision = "b6c7d8e9f0a1"
down_revision = "a5b6c7d8e9f0"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("salary_template_component", sa.Column("min_amount", sa.Float(), nullable=True))
    op.add_column("salary_template_component", sa.Column("max_amount", sa.Float(), nullable=True))


def downgrade():
    op.drop_column("salary_template_component", "max_amount")
    op.drop_column("salary_template_component", "min_amount")
