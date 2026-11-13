"""live location tracking (policy, override, consent, ping, alert)

Revision ID: e5b9c3d7a1f4
Revises: d3a8f5c2b7e1
Create Date: 2026-11-13
"""
import sqlalchemy as sa
from alembic import op

revision = "e5b9c3d7a1f4"
down_revision = "d3a8f5c2b7e1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tracking_policy",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("role_id", sa.Integer, sa.ForeignKey("role.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("interval_seconds", sa.Integer, nullable=False, server_default="300"),
        sa.Column("distance_filter_m", sa.Integer, nullable=False, server_default="100"),
        sa.Column("updated_by_id", sa.Integer, sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "tracking_override",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("enabled", sa.Boolean, nullable=False),
        sa.Column("updated_by_id", sa.Integer, sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "tracking_consent",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("consented_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("app_version", sa.String(32), nullable=True),
    )
    op.create_index("ix_tracking_consent_user_id", "tracking_consent", ["user_id"])
    op.create_table(
        "location_ping",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lat", sa.Float, nullable=False),
        sa.Column("lng", sa.Float, nullable=False),
        sa.Column("accuracy", sa.Float, nullable=True),
        sa.Column("speed", sa.Float, nullable=True),
        sa.Column("battery", sa.Float, nullable=True),
        sa.Column("work_date", sa.Date, nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "captured_at", name="uq_location_ping_user_ts"),
    )
    op.create_index("ix_location_ping_captured", "location_ping", ["captured_at"])
    op.create_table(
        "tracking_alert",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("work_date", sa.Date, nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "work_date", "kind", name="uq_tracking_alert"),
    )


def downgrade():
    op.drop_table("tracking_alert")
    op.drop_table("location_ping")
    op.drop_table("tracking_consent")
    op.drop_table("tracking_override")
    op.drop_table("tracking_policy")
