"""notification_delivery.provider_ticket_ids for push receipt polling

Revision ID: b5e2c7a9d1f4
Revises: a9d3f6b1c8e2
Create Date: 2026-11-13
"""
import sqlalchemy as sa
from alembic import op

revision = "b5e2c7a9d1f4"
down_revision = "a9d3f6b1c8e2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("notification_delivery",
                  sa.Column("provider_ticket_ids", sa.Text, nullable=True))


def downgrade():
    op.drop_column("notification_delivery", "provider_ticket_ids")
