"""custom letter templates (W10a)

Creates the lettertemplate table backing HR-authored custom letter
templates ({{token}} placeholders). No changes to the existing
employeeletter table — rendered custom letters persist there with
letter_type='custom' and reference_number generated at runtime.

Revision ID: x2y3z4a5b6c7
Revises: w1x2y3z4a5b6
Create Date: 2026-08-05
"""
from alembic import op
import sqlalchemy as sa

revision = "x2y3z4a5b6c7"
down_revision = "w1x2y3z4a5b6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "lettertemplate",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column(
            "category", sa.String(50), nullable=False,
            server_default="custom",
        ),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by_id"], ["user.id"], ondelete="SET NULL"
        ),
    )
    op.create_index(
        "ix_lettertemplate_name", "lettertemplate", ["name"]
    )
    op.create_index(
        "ix_lettertemplate_category", "lettertemplate", ["category"]
    )


def downgrade():
    op.drop_index("ix_lettertemplate_category", table_name="lettertemplate")
    op.drop_index("ix_lettertemplate_name", table_name="lettertemplate")
    op.drop_table("lettertemplate")
