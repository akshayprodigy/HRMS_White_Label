"""Add parent_project_id to project for hierarchy

Revision ID: a1b2c3d4e5f6
Revises: 3d4c7a8b9c1e
Create Date: 2026-03-24

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "a1b2c3d4e5f6"
down_revision = "3d4c7a8b9c1e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    existing_cols = {c.get("name") for c in inspector.get_columns("project")}
    if "parent_project_id" not in existing_cols:
        op.add_column(
            "project",
            sa.Column(
                "parent_project_id",
                sa.Integer(),
                sa.ForeignKey("project.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )

    existing_indexes = {i.get("name") for i in inspector.get_indexes("project")}
    if "ix_project_parent_project_id" not in existing_indexes:
        op.create_index(
            "ix_project_parent_project_id",
            "project",
            ["parent_project_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    existing_indexes = {i.get("name") for i in inspector.get_indexes("project")}
    if "ix_project_parent_project_id" in existing_indexes:
        op.drop_index("ix_project_parent_project_id", table_name="project")

    existing_cols = {c.get("name") for c in inspector.get_columns("project")}
    if "parent_project_id" in existing_cols:
        op.drop_column("project", "parent_project_id")
