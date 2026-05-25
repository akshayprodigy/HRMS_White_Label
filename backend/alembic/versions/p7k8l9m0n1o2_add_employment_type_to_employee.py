"""add employment_type to employee

Revision ID: p7k8l9m0n1o2
Revises: o6j7k8l9m0n1
Create Date: 2026-04-03
"""
from alembic import op
import sqlalchemy as sa

revision = "p7k8l9m0n1o2"
down_revision = "o6j7k8l9m0n1"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "employee",
        sa.Column("employment_type", sa.String(20), nullable=False, server_default="permanent")
    )


def downgrade():
    op.drop_column("employee", "employment_type")
