"""BD bid task enhancements: BD estimates, deadline, archive

Revision ID: h9c0d1e2f3g4
Revises: g8b9c0d1e2f3
Create Date: 2026-03-27

"""
from alembic import op
import sqlalchemy as sa

revision = "h9c0d1e2f3g4"
down_revision = "g8b9c0d1e2f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "lead_bid_task",
        sa.Column("bd_estimated_hours", sa.Numeric(12, 2), nullable=True),
    )
    op.add_column(
        "lead_bid_task",
        sa.Column("bd_estimated_cost", sa.Numeric(12, 2), nullable=True),
    )
    op.add_column(
        "lead_bid_task",
        sa.Column(
            "is_archived",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "lead_bid_task_assignment",
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("lead_bid_task_assignment", "deadline")
    op.drop_column("lead_bid_task", "is_archived")
    op.drop_column("lead_bid_task", "bd_estimated_cost")
    op.drop_column("lead_bid_task", "bd_estimated_hours")
