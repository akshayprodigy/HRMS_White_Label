"""phase6a: optional holiday picks + work-location requests tables

Roadmap v2 Phase 6A, Task 5.

NOTE: MariaDB DDL is not transactional. If the upgrade fails midway, drop
work_location_request and optional_holiday_pick manually before retrying.

Revision ID: a6b8d0f2c4e7
Revises: e5a7c9b1d3f2
Create Date: 2026-11-20
"""
import sqlalchemy as sa
from alembic import op

revision = "a6b8d0f2c4e7"
down_revision = "e5a7c9b1d3f2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "optional_holiday_pick",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("holiday_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False,
                  server_default="pending"),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("decided_by_id", sa.Integer(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["holiday_id"], ["holidaycalendar.id"],
                                name="fk_ohp_holiday", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"],
                                name="fk_ohp_user", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["decided_by_id"], ["user.id"],
                                name="fk_ohp_decided_by",
                                ondelete="SET NULL"),
    )
    op.create_index("ix_optional_holiday_pick_holiday_id",
                    "optional_holiday_pick", ["holiday_id"])
    op.create_index("ix_ohp_user_year_status", "optional_holiday_pick",
                    ["user_id", "year", "status"])

    op.create_table(
        "work_location_request",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("day_portion", sa.String(16), nullable=False,
                  server_default="full"),
        sa.Column("place", sa.String(200), nullable=True),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False,
                  server_default="pending"),
        sa.Column("decided_by_id", sa.Integer(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"],
                                name="fk_wlr_user", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["decided_by_id"], ["user.id"],
                                name="fk_wlr_decided_by",
                                ondelete="SET NULL"),
    )
    op.create_index("ix_wlr_user_status", "work_location_request",
                    ["user_id", "status"])
    op.create_index("ix_wlr_dates", "work_location_request",
                    ["start_date", "end_date"])


def downgrade():
    # Chain instances/steps created for these entities would be orphaned
    # (no entity left to finalize); remove them and their notifications.
    conn = op.get_bind()
    ids = ("SELECT id FROM chained_approval_instance WHERE entity_type IN "
           "('optional_holiday','work_location')")
    conn.execute(sa.text(
        "DELETE FROM notification WHERE resource_type = "
        "'chained_approval_instance' AND resource_id IN "
        f"(SELECT CAST(id AS CHAR) FROM ({ids}) AS i)"))
    conn.execute(sa.text(
        "DELETE FROM chained_approval_step_instance WHERE instance_id IN "
        f"({ids})"))
    conn.execute(sa.text(
        "DELETE FROM chained_approval_instance WHERE entity_type IN "
        "('optional_holiday','work_location')"))
    op.drop_table("work_location_request")
    op.drop_table("optional_holiday_pick")
