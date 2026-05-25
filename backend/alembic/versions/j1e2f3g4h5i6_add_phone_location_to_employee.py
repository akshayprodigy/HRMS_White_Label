"""add phone and location to employee

Revision ID: j1e2f3g4h5i6
Revises: i0d1e2f3g4h5
Create Date: 2026-03-29
"""
from alembic import op
import sqlalchemy as sa

revision = "j1e2f3g4h5i6"
down_revision = "i0d1e2f3g4h5"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("employee", sa.Column("phone", sa.String(20), nullable=True))
    op.add_column("employee", sa.Column("location", sa.String(100), nullable=True))


def downgrade():
    op.drop_column("employee", "location")
    op.drop_column("employee", "phone")
