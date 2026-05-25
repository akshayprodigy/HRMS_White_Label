"""add salary heads and payroll components

Revision ID: o6j7k8l9m0n1
Revises: n5i6j7k8l9m0
Create Date: 2026-04-03
"""
from alembic import op
import sqlalchemy as sa

revision = "o6j7k8l9m0n1"
down_revision = "n5i6j7k8l9m0"
branch_labels = None
depends_on = None


def upgrade():
    # New employee fields
    op.add_column("employee", sa.Column("bank_name", sa.String(100), nullable=True))
    op.add_column("employee", sa.Column("grade", sa.String(20), nullable=True))
    op.add_column("employee", sa.Column("level", sa.String(20), nullable=True))
    op.add_column("employee", sa.Column("voluntary_pf", sa.Float(), nullable=True))

    # New payroll line fields
    op.add_column("payrollline", sa.Column("arrear", sa.Float(), nullable=True, server_default="0"))
    op.add_column("payrollline", sa.Column("incentive", sa.Float(), nullable=True, server_default="0"))


def downgrade():
    op.drop_column("payrollline", "incentive")
    op.drop_column("payrollline", "arrear")
    op.drop_column("employee", "voluntary_pf")
    op.drop_column("employee", "level")
    op.drop_column("employee", "grade")
    op.drop_column("employee", "bank_name")
