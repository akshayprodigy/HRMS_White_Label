"""add notification delivery: templates, preferences, delivery log,
event_type column on notification.

Pure additive — existing rows unchanged. In-app notifications keep
firing exactly as before; the delivery layer sits alongside.

Revision ID: i6d7e8f9g0h1
Revises: h5c6d7e8f9g0
Create Date: 2026-07-01
"""
from alembic import op
import sqlalchemy as sa


revision = "i6d7e8f9g0h1"
down_revision = "h5c6d7e8f9g0"
branch_labels = None
depends_on = None


def upgrade():
    # ---- notification.event_type ---------------------------------
    op.add_column(
        "notification",
        sa.Column("event_type", sa.String(64), nullable=True),
    )
    op.create_index(
        "ix_notification_event_type", "notification", ["event_type"]
    )

    # ---- notification_template -----------------------------------
    op.create_table(
        "notification_template",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("category", sa.String(24),
                  nullable=False, server_default="other"),
        sa.Column("subject", sa.String(240), nullable=True),
        sa.Column("body_html", sa.Text(), nullable=True),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column("dlt_template_id", sa.String(64), nullable=True),
        sa.Column("is_sensitive", sa.Boolean(),
                  nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(),
                  nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "event_type", "channel",
            name="uq_notification_template_event_channel",
        ),
    )
    op.create_index(
        "ix_notification_template_event_type",
        "notification_template", ["event_type"],
    )

    # ---- user_notification_preference ----------------------------
    op.create_table(
        "user_notification_preference",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("category", sa.String(24), nullable=False),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("enabled", sa.Boolean(),
                  nullable=False, server_default=sa.true()),
        sa.Column("digest_cadence", sa.String(16),
                  nullable=False, server_default="immediate"),
        sa.UniqueConstraint(
            "user_id", "category", "channel",
            name="uq_user_pref_user_cat_channel",
        ),
    )
    op.create_index(
        "ix_user_pref_user_id", "user_notification_preference", ["user_id"]
    )

    # ---- user_quiet_hours ----------------------------------------
    op.create_table(
        "user_quiet_hours",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False, unique=True,
        ),
        sa.Column("quiet_from", sa.Time(), nullable=True),
        sa.Column("quiet_to", sa.Time(), nullable=True),
        sa.Column("hard_opt_out", sa.Boolean(),
                  nullable=False, server_default=sa.false()),
    )

    # ---- notification_delivery -----------------------------------
    op.create_table(
        "notification_delivery",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "notification_id", sa.Integer(),
            sa.ForeignKey("notification.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column(
            "recipient_user_id", sa.Integer(),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16),
                  nullable=False, server_default="queued"),
        sa.Column("provider_message_id", sa.String(120), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(),
                  nullable=False, server_default="0"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_digest", sa.Boolean(),
                  nullable=False, server_default=sa.false()),
        sa.Column("digest_batch_key", sa.String(64), nullable=True),
        sa.Column("context_json", sa.JSON(),
                  nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_notification_delivery_notification_id",
        "notification_delivery", ["notification_id"],
    )
    op.create_index(
        "ix_notification_delivery_status",
        "notification_delivery", ["status"],
    )
    op.create_index(
        "ix_notification_delivery_recipient",
        "notification_delivery", ["recipient_user_id"],
    )
    op.create_index(
        "ix_notification_delivery_event",
        "notification_delivery", ["event_type"],
    )
    op.create_index(
        "ix_notification_delivery_digest_batch",
        "notification_delivery", ["digest_batch_key"],
    )


def downgrade():
    for idx in (
        "ix_notification_delivery_digest_batch",
        "ix_notification_delivery_event",
        "ix_notification_delivery_recipient",
        "ix_notification_delivery_status",
        "ix_notification_delivery_notification_id",
    ):
        op.drop_index(idx, table_name="notification_delivery")
    op.drop_table("notification_delivery")

    op.drop_table("user_quiet_hours")

    op.drop_index(
        "ix_user_pref_user_id", table_name="user_notification_preference"
    )
    op.drop_table("user_notification_preference")

    op.drop_index(
        "ix_notification_template_event_type",
        table_name="notification_template",
    )
    op.drop_table("notification_template")

    op.drop_index("ix_notification_event_type", table_name="notification")
    op.drop_column("notification", "event_type")
