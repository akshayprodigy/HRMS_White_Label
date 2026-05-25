"""add project_document table

Stores arbitrary project-attached files (workorder, contract, etc.).
Filenames are uuid-prefixed on disk to avoid collisions; the original
client filename is kept for download. CASCADE on project ensures the
folder cleanup helper isn't load-bearing for DB integrity.

Revision ID: s0n1o2p3q4r5
Revises: r9m0n1o2p3q4
Create Date: 2026-04-30
"""
from alembic import op
import sqlalchemy as sa

revision = "s0n1o2p3q4r5"
down_revision = "r9m0n1o2p3q4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "project_document",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "project_id", sa.Integer(),
            sa.ForeignKey("project.id", ondelete="CASCADE"),
            nullable=False, index=True,
        ),
        sa.Column("doc_type", sa.String(50), nullable=False, server_default="Workorder"),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("stored_filename", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False, server_default="application/octet-stream"),
        sa.Column("file_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column(
            "uploaded_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.Column(
            "uploaded_by_id", sa.Integer(),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade():
    op.drop_table("project_document")
