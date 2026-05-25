"""add avatar_url to user

Revision ID: m4h5i6j7k8l9
Revises: l3g4h5i6j7k8
Create Date: 2026-03-31
"""
from alembic import op
import sqlalchemy as sa

revision = "m4h5i6j7k8l9"
down_revision = "l3g4h5i6j7k8"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("user", sa.Column("avatar_url", sa.String(255), nullable=True))


def downgrade():
    op.drop_column("user", "avatar_url")
