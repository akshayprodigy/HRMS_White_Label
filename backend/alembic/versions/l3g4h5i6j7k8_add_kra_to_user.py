"""add kra to user

Revision ID: l3g4h5i6j7k8
Revises: k2f3g4h5i6j7
Create Date: 2026-03-29
"""
from alembic import op
import sqlalchemy as sa

revision = "l3g4h5i6j7k8"
down_revision = "k2f3g4h5i6j7"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("user", sa.Column("kra", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("user", "kra")
