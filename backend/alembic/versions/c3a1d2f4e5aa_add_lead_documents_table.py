"""Add lead documents table

Revision ID: c3a1d2f4e5aa
Revises: 7c4a9f01c8de
Create Date: 2026-03-22

Adds support for uploading multiple documents (pdf/docx/images/etc.)
against a BD Lead (opportunity).
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c3a1d2f4e5aa"
down_revision: Union[str, None] = "7c4a9f01c8de"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "lead_document",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "lead_id",
            sa.Integer(),
            sa.ForeignKey("lead.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("storage_path", sa.String(length=512), nullable=False),
        sa.Column(
            "mime_type",
            sa.String(length=80),
            nullable=False,
            server_default="application/octet-stream",
        ),
        sa.Column(
            "file_size",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "uploader_id",
            sa.Integer(),
            sa.ForeignKey("user.id"),
            nullable=False,
            index=True,
        ),
    )

    op.create_index(
        "ix_lead_document_lead_id_uploaded_at",
        "lead_document",
        ["lead_id", "uploaded_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_lead_document_lead_id_uploaded_at",
        table_name="lead_document",
    )
    op.drop_table("lead_document")
