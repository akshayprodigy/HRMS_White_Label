"""add client details table

Revision ID: 3c1a0c2b9f7d
Revises: 2f3b8a7c1d9e
Create Date: 2026-03-06

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "3c1a0c2b9f7d"
down_revision: Union[str, None] = "2f3b8a7c1d9e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "client_details",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("website", sa.String(length=255), nullable=True),
        sa.Column("contact_person_name", sa.String(length=255), nullable=True),
        sa.Column("contact_person_phone", sa.String(length=50), nullable=True),
        sa.Column(
            "contact_person_email", sa.String(length=255), nullable=True
        ),
        sa.Column("gst_number", sa.String(length=30), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["account.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", name="uq_client_details_account_id"),
    )

    op.create_index(
        op.f("ix_client_details_account_id"),
        "client_details",
        ["account_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_client_details_gst_number"),
        "client_details",
        ["gst_number"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_client_details_gst_number"),
        table_name="client_details",
    )
    op.drop_index(
        op.f("ix_client_details_account_id"),
        table_name="client_details",
    )
    op.drop_table("client_details")
