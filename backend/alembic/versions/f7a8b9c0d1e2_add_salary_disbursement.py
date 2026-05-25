"""add salary disbursement table

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-03-27

"""
from alembic import op
import sqlalchemy as sa

revision = "f7a8b9c0d1e2"
down_revision = "e6f7a8b9c0d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "salarydisbursement",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "payroll_line_id",
            sa.Integer(),
            sa.ForeignKey("payrollline.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column(
            "payment_mode",
            sa.String(30),
            nullable=False,
            server_default="bank_transfer",
        ),
        sa.Column("reference", sa.String(100), nullable=True),
        sa.Column("remarks", sa.String(255), nullable=True),
        sa.Column(
            "disbursed_by_id",
            sa.Integer(),
            sa.ForeignKey("user.id"),
            nullable=False,
        ),
        sa.Column(
            "disbursed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("salarydisbursement")
