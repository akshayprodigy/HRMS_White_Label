"""projects dpr

Revision ID: 0008_projects_dpr
Revises: 0007
Create Date: 2026-02-05

"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0008_projects_dpr"
down_revision = "0007"
branch_labels = None
depends_on = None

_FK_ITEMS_ID = "items.id"
_FK_PROJECTS_ID = "projects.id"
_FK_UOMS_ID = "uoms.id"
_FK_DPR_HEADERS_ID = "dpr_headers.id"


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
        "dpr_headers",
        sa.Column(
            "id",
            sa.BigInteger(),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column(
            "project_id",
            sa.BigInteger(),
            sa.ForeignKey(_FK_PROJECTS_ID),
            nullable=False,
        ),
        sa.Column("dpr_date", sa.Date(), nullable=False),
        sa.Column("shift", sa.String(length=20), nullable=True),
        sa.Column("remarks", sa.String(length=500), nullable=True),
        *_audit_columns(),
    )
    op.create_index("ix_dpr_headers_project_id", "dpr_headers", ["project_id"])
    op.create_index("ix_dpr_headers_dpr_date", "dpr_headers", ["dpr_date"])
    op.create_index(
        "ix_dpr_headers_project_id_dpr_date",
        "dpr_headers",
        ["project_id", "dpr_date"],
    )

    op.create_table(
        "dpr_drilling_lines",
        sa.Column(
            "id",
            sa.BigInteger(),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column(
            "header_id",
            sa.BigInteger(),
            sa.ForeignKey(_FK_DPR_HEADERS_ID, ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column(
            "meters_drilled",
            sa.Numeric(14, 3),
            nullable=False,
        ),
        sa.Column(
            "recovered_meters",
            sa.Numeric(14, 3),
            nullable=True,
        ),
        *_audit_columns(),
        sa.UniqueConstraint("header_id", "line_no"),
    )
    op.create_index(
        "ix_dpr_drilling_lines_header_id",
        "dpr_drilling_lines",
        ["header_id"],
    )

    op.create_table(
        "dpr_activity_lines",
        sa.Column(
            "id",
            sa.BigInteger(),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column(
            "header_id",
            sa.BigInteger(),
            sa.ForeignKey(_FK_DPR_HEADERS_ID, ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("activity", sa.String(length=255), nullable=False),
        sa.Column("hours", sa.Numeric(8, 2), nullable=True),
        sa.Column("remarks", sa.String(length=500), nullable=True),
        *_audit_columns(),
        sa.UniqueConstraint("header_id", "line_no"),
    )
    op.create_index(
        "ix_dpr_activity_lines_header_id",
        "dpr_activity_lines",
        ["header_id"],
    )

    op.create_table(
        "dpr_consumption_lines",
        sa.Column(
            "id",
            sa.BigInteger(),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column(
            "header_id",
            sa.BigInteger(),
            sa.ForeignKey(_FK_DPR_HEADERS_ID, ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column(
            "item_id",
            sa.BigInteger(),
            sa.ForeignKey(_FK_ITEMS_ID),
            nullable=True,
        ),
        sa.Column(
            "uom_id",
            sa.BigInteger(),
            sa.ForeignKey(_FK_UOMS_ID),
            nullable=True,
        ),
        sa.Column(
            "qty",
            sa.Numeric(14, 3),
            nullable=False,
        ),
        sa.Column("remarks", sa.String(length=500), nullable=True),
        *_audit_columns(),
        sa.UniqueConstraint("header_id", "line_no"),
    )
    op.create_index(
        "ix_dpr_consumption_lines_header_id",
        "dpr_consumption_lines",
        ["header_id"],
    )
    op.create_index(
        "ix_dpr_consumption_lines_item_id",
        "dpr_consumption_lines",
        ["item_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_dpr_consumption_lines_item_id",
        table_name="dpr_consumption_lines",
    )
    op.drop_index(
        "ix_dpr_consumption_lines_header_id",
        table_name="dpr_consumption_lines",
    )
    op.drop_table("dpr_consumption_lines")

    op.drop_index(
        "ix_dpr_activity_lines_header_id",
        table_name="dpr_activity_lines",
    )
    op.drop_table("dpr_activity_lines")

    op.drop_index(
        "ix_dpr_drilling_lines_header_id",
        table_name="dpr_drilling_lines",
    )
    op.drop_table("dpr_drilling_lines")

    op.drop_index(
        "ix_dpr_headers_project_id_dpr_date",
        table_name="dpr_headers",
    )
    op.drop_index("ix_dpr_headers_dpr_date", table_name="dpr_headers")
    op.drop_index("ix_dpr_headers_project_id", table_name="dpr_headers")
    op.drop_table("dpr_headers")
