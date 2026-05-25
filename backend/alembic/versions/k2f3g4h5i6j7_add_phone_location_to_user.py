"""add phone and location to user

Revision ID: k2f3g4h5i6j7
Revises: j1e2f3g4h5i6
Create Date: 2026-03-29
"""
from alembic import op
import sqlalchemy as sa

revision = "k2f3g4h5i6j7"
down_revision = "j1e2f3g4h5i6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("user", sa.Column("phone", sa.String(20), nullable=True))
    op.add_column("user", sa.Column("location", sa.String(100), nullable=True))


def downgrade():
    op.drop_column("user", "location")
    op.drop_column("user", "phone")
