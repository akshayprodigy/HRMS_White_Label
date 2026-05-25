"""Add bid task assignment documents

Revision ID: 8f2c1a7d9b3e
Revises: d8a2b7c9f1c0
Create Date: 2026-03-23

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "8f2c1a7d9b3e"
down_revision = "d8a2b7c9f1c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bid_task_assignment_document",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "assignment_id",
            sa.Integer(),
            sa.ForeignKey("lead_bid_task_assignment.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "lead_document_id",
            sa.Integer(),
            sa.ForeignKey("lead_document.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "assignment_id",
            "lead_document_id",
            name="uq_bid_task_assignment_document_assignment_doc",
        ),
    )
    op.create_index(
        "ix_bid_task_assignment_document_assignment_id",
        "bid_task_assignment_document",
        ["assignment_id"],
    )
    op.create_index(
        "ix_bid_task_assignment_document_lead_document_id",
        "bid_task_assignment_document",
        ["lead_document_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_bid_task_assignment_document_lead_document_id",
        table_name="bid_task_assignment_document",
    )
    op.drop_index(
        "ix_bid_task_assignment_document_assignment_id",
        table_name="bid_task_assignment_document",
    )
    op.drop_table("bid_task_assignment_document")
