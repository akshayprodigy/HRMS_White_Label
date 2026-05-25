"""Add delivery PM to bid task

Revision ID: 3d4c7a8b9c1e
Revises: 8f2c1a7d9b3e
Create Date: 2026-03-23

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "3d4c7a8b9c1e"
down_revision = "8f2c1a7d9b3e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    existing_cols = {
        c.get("name") for c in inspector.get_columns("lead_bid_task")
    }
    if "delivery_pm_user_id" not in existing_cols:
        op.add_column(
            "lead_bid_task",
            sa.Column(
                "delivery_pm_user_id",
                sa.Integer(),
                sa.ForeignKey("user.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )

    existing_indexes = {
        i.get("name") for i in inspector.get_indexes("lead_bid_task")
    }
    if "ix_lead_bid_task_delivery_pm_user_id" not in existing_indexes:
        op.create_index(
            "ix_lead_bid_task_delivery_pm_user_id",
            "lead_bid_task",
            ["delivery_pm_user_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    existing_indexes = {
        i.get("name") for i in inspector.get_indexes("lead_bid_task")
    }
    if "ix_lead_bid_task_delivery_pm_user_id" in existing_indexes:
        op.drop_index(
            "ix_lead_bid_task_delivery_pm_user_id",
            table_name="lead_bid_task",
        )

    existing_cols = {
        c.get("name") for c in inspector.get_columns("lead_bid_task")
    }
    if "delivery_pm_user_id" in existing_cols:
        op.drop_column("lead_bid_task", "delivery_pm_user_id")
