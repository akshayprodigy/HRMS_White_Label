"""deduction caps on statutory config (W4)

HR-configurable caps on the resulting deduction amount (distinct from the
wage-base ceilings). NULL = no cap, so existing installs are unchanged.

Revision ID: s7t8u9v0w1x2
Revises: r6s7t8u9v0w1
Create Date: 2026-08-04
"""
from alembic import op
import sqlalchemy as sa

revision = "s7t8u9v0w1x2"
down_revision = "r6s7t8u9v0w1"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("statutory_config", sa.Column("pf_employee_max_amount", sa.Float(), nullable=True))
    op.add_column("statutory_config", sa.Column("vpf_max_amount", sa.Float(), nullable=True))


def downgrade():
    op.drop_column("statutory_config", "vpf_max_amount")
    op.drop_column("statutory_config", "pf_employee_max_amount")
