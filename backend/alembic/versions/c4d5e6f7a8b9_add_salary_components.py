"""add salary components

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-03-26

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "c4d5e6f7a8b9"
down_revision = "b3c4d5e6f7a8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("employee", sa.Column("conveyance_allowance", sa.Float(), nullable=True))
    op.add_column("employee", sa.Column("hra", sa.Float(), nullable=True))
    op.add_column("employee", sa.Column("other_allowance", sa.Float(), nullable=True))
    op.add_column(
        "employee",
        sa.Column("esic_applicable", sa.Boolean(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("employee", "esic_applicable")
    op.drop_column("employee", "other_allowance")
    op.drop_column("employee", "hra")
    op.drop_column("employee", "conveyance_allowance")
