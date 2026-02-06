"""core entities

Revision ID: 0003_core_entities
Revises: 0002_iam_rbac
Create Date: 2026-02-05

"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0003_core_entities"
down_revision = "0002_iam_rbac"
branch_labels = None
depends_on = None


def _audit_columns() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            server_onupdate=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("updated_by", sa.BigInteger(), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        *_audit_columns(),
        sa.UniqueConstraint("code", name="uq_organizations_code"),
        sa.UniqueConstraint("name", name="uq_organizations_name"),
    )
    op.create_index(
        "ix_organizations_code",
        "organizations",
        ["code"],
        unique=True,
    )
    op.create_index(
        "ix_organizations_name",
        "organizations",
        ["name"],
        unique=True,
    )

    op.create_table(
        "sites",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.BigInteger(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        *_audit_columns(),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_sites_organization",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "code",
            name="uq_sites_org_id_code",
        ),
    )
    op.create_index("ix_sites_organization_id", "sites", ["organization_id"])

    op.create_table(
        "projects",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.BigInteger(), nullable=False),
        sa.Column("site_id", sa.BigInteger(), nullable=True),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        *_audit_columns(),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_projects_organization",
        ),
        sa.ForeignKeyConstraint(
            ["site_id"],
            ["sites.id"],
            name="fk_projects_site",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "code",
            name="uq_projects_org_id_code",
        ),
    )
    op.create_index(
        "ix_projects_organization_id",
        "projects",
        ["organization_id"],
    )
    op.create_index("ix_projects_site_id", "projects", ["site_id"])

    op.create_table(
        "cost_centers",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.BigInteger(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        *_audit_columns(),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_cost_centers_organization",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "code",
            name="uq_cost_centers_org_id_code",
        ),
    )
    op.create_index(
        "ix_cost_centers_organization_id",
        "cost_centers",
        ["organization_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_cost_centers_organization_id", table_name="cost_centers")
    op.drop_table("cost_centers")

    op.drop_index("ix_projects_site_id", table_name="projects")
    op.drop_index("ix_projects_organization_id", table_name="projects")
    op.drop_table("projects")

    op.drop_index("ix_sites_organization_id", table_name="sites")
    op.drop_table("sites")

    op.drop_index("ix_organizations_name", table_name="organizations")
    op.drop_index("ix_organizations_code", table_name="organizations")
    op.drop_table("organizations")
