"""add client_id FK to project

Allows a Project to be linked directly to an Account (client). Existing
projects converted from a Lead derive their client via lead.account; this
column lets PMs/super admins create projects against a client picker without
requiring a lead first, and is the column populated by the bulk upload flow.

Revision ID: t1o2p3q4r5s6
Revises: s0n1o2p3q4r5
Create Date: 2026-04-30
"""
from alembic import op
import sqlalchemy as sa

revision = "t1o2p3q4r5s6"
down_revision = "s0n1o2p3q4r5"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "project",
        sa.Column(
            "client_id", sa.Integer(),
            sa.ForeignKey("account.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_project_client_id", "project", ["client_id"]
    )


def downgrade():
    op.drop_index("ix_project_client_id", table_name="project")
    op.drop_column("project", "client_id")
