"""add saved_report table

Additive — the reporting layer itself is read-only over existing data,
this table only stores saved filter presets + recipient lists for
scheduled runs. The scheduler cron is a documented follow-up (like the
apply-due job on salary revisions).

Revision ID: e2z3a4b5c6d7
Revises: d1y2z3a4b5c6
Create Date: 2026-07-01
"""
from alembic import op
import sqlalchemy as sa


revision = "e2z3a4b5c6d7"
down_revision = "d1y2z3a4b5c6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "saved_report",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("report_key", sa.String(60), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("filters_json", sa.JSON(), nullable=False,
                  server_default=sa.text("'{}'::json")),
        sa.Column("default_format", sa.String(10),
                  nullable=False, server_default="xlsx"),
        sa.Column("cadence", sa.String(20),
                  nullable=False, server_default="none"),
        sa.Column("recipients_json", sa.JSON(), nullable=False,
                  server_default=sa.text("'[]'::json")),
        sa.Column("is_active", sa.Boolean(),
                  nullable=False, server_default=sa.true()),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "owner_id", sa.Integer(),
            sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_saved_report_key", "saved_report", ["report_key"])
    op.create_index("ix_saved_report_name", "saved_report", ["name"])


def downgrade():
    op.drop_index("ix_saved_report_name", table_name="saved_report")
    op.drop_index("ix_saved_report_key", table_name="saved_report")
    op.drop_table("saved_report")
