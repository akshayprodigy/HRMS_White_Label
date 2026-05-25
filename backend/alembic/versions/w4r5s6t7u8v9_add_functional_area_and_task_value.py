"""add functional_area master, project.functional_area_id, task.value

Adds:
- functional_area: master taxonomy table (id, name, code, is_active)
- project.functional_area_id: FK column (nullable for backward compat)
- task.value: per-task monetary value (Numeric 14,2)

Also seeds 14 functional areas matching UEIPL's project classification.

Revision ID: w4r5s6t7u8v9
Revises: v3q4r5s6t7u8
Create Date: 2026-05-14
"""
from alembic import op
import sqlalchemy as sa

revision = "w4r5s6t7u8v9"
down_revision = "v3q4r5s6t7u8"
branch_labels = None
depends_on = None


SEED_FUNCTIONAL_AREAS = [
    ("GR", "Geological Report - Coal"),
    ("CMP", "Coal Mining Plan / Review"),
    ("DPR", "Coal DPR / FR / PFR / TEV"),
    ("CBA", "Coal Bid Advisory"),
    ("NCBA", "Non-Coal Bid Advisory / Mining Plan & DPR"),
    ("NMEDT", "NMEDT Projects"),
    ("PNM", "Projects & Monitoring"),
    ("EFC", "Environment & Forest Clearance"),
    ("MM", "Minor Minerals"),
    ("SUR", "Survey"),
    ("HGS", "Hydrogeological Study"),
    ("EXP", "Exploration"),
    ("SCI", "Scientific Projects"),
    ("ENG", "Engineering Projects"),
]


def upgrade():
    op.create_table(
        "functional_area",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("code", sa.String(20), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            server_onupdate=sa.func.now(),
        ),
        sa.UniqueConstraint("name", name="uq_functional_area_name"),
        sa.UniqueConstraint("code", name="uq_functional_area_code"),
    )
    op.create_index(
        "ix_functional_area_code", "functional_area", ["code"], unique=False
    )

    op.add_column(
        "project",
        sa.Column(
            "functional_area_id", sa.Integer(), nullable=True, index=True
        ),
    )
    op.create_foreign_key(
        "fk_project_functional_area",
        "project",
        "functional_area",
        ["functional_area_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column(
        "task",
        sa.Column("value", sa.Numeric(14, 2), nullable=True),
    )

    fa_table = sa.table(
        "functional_area",
        sa.column("name", sa.String),
        sa.column("code", sa.String),
        sa.column("is_active", sa.Boolean),
    )
    op.bulk_insert(
        fa_table,
        [
            {"code": code, "name": name, "is_active": True}
            for code, name in SEED_FUNCTIONAL_AREAS
        ],
    )


def downgrade():
    op.drop_column("task", "value")
    op.drop_constraint(
        "fk_project_functional_area", "project", type_="foreignkey"
    )
    op.drop_column("project", "functional_area_id")
    op.drop_index("ix_functional_area_code", table_name="functional_area")
    op.drop_table("functional_area")
