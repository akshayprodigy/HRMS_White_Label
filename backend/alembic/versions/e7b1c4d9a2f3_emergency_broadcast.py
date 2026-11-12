"""emergency broadcast + 'broadcast send' permission + emergency templates

Revision ID: e7b1c4d9a2f3
Revises: 013b7dbef090
Create Date: 2026-11-13
"""
import sqlalchemy as sa
from alembic import op

revision = "e7b1c4d9a2f3"
down_revision = "013b7dbef090"
branch_labels = None
depends_on = None

_ROLES = "('HR', 'Super Admin', 'Admin')"
_PERM_DESC = "Send and manage emergency broadcasts"

_TEMPLATES = [
    ("emergency_broadcast", "email", "[{severity}] {title}",
     "<p><b>{title}</b></p><p>{message}</p><p>Open the app to acknowledge or mark yourself safe.</p>",
     "{title}\n\n{message}\n\nOpen the app to acknowledge or mark yourself safe."),
    ("emergency_broadcast", "sms", None, None,
     "EMERGENCY: {title} - {message}"),
    ("emergency_need_help", "email", "NEEDS HELP: {title}",
     "<p><b>{title}</b></p><p>{message}</p><p>Open the Emergency broadcast dashboard.</p>",
     "{title}\n\n{message}\n\nOpen the Emergency broadcast dashboard."),
    ("emergency_need_help", "sms", None, None,
     "NEEDS HELP: {title} - {message}"),
]


def upgrade():
    op.create_table(
        "broadcast",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("severity", sa.String(16), nullable=False, server_default="info"),
        sa.Column("audience", sa.String(16), nullable=False),
        sa.Column("audience_value", sa.String(100), nullable=True),
        sa.Column("requires_ack", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("safety_check", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_by_id", sa.Integer,
                  sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_broadcast_id", "broadcast", ["id"])
    op.create_index("ix_broadcast_created_by_id", "broadcast", ["created_by_id"])
    op.create_table(
        "broadcast_recipient",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("broadcast_id", sa.Integer,
                  sa.ForeignKey("broadcast.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer,
                  sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("safety_status", sa.String(16), nullable=True),
        sa.Column("safety_note", sa.String(500), nullable=True),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("broadcast_id", "user_id", name="uq_broadcast_recipient"),
    )
    op.create_index("ix_broadcast_recipient_id", "broadcast_recipient", ["id"])
    op.create_index("ix_broadcast_recipient_user_id", "broadcast_recipient", ["user_id"])
    op.create_index("ix_broadcast_recipient_status", "broadcast_recipient",
                    ["broadcast_id", "safety_status"])

    op.execute(
        "INSERT INTO permission (name, description) "
        f"SELECT 'broadcast send', '{_PERM_DESC}' "
        "FROM DUAL WHERE NOT EXISTS "
        "(SELECT 1 FROM permission WHERE name = 'broadcast send')"
    )
    op.execute(
        "INSERT IGNORE INTO role_permissions (role_id, permission_id) "
        "SELECT r.id, p.id FROM role r, permission p "
        f"WHERE r.name IN {_ROLES} AND p.name = 'broadcast send'"
    )
    from app.core.config import settings
    dlt = {"emergency_broadcast": settings.EMERGENCY_BROADCAST_DLT_TEMPLATE_ID,
           "emergency_need_help": settings.EMERGENCY_NEED_HELP_DLT_TEMPLATE_ID}
    conn = op.get_bind()
    for ev, ch, subj, html, text in _TEMPLATES:
        conn.execute(sa.text(
            "INSERT INTO notification_template (event_type, channel, category, "
            "subject, body_html, body_text, dlt_template_id, is_sensitive, is_active, created_at, updated_at) "
            "SELECT :ev, :ch, 'emergency', :subj, :html, :text, :dlt, 0, 1, NOW(), NOW() "
            "FROM DUAL WHERE NOT EXISTS (SELECT 1 FROM notification_template "
            "WHERE event_type = :ev AND channel = :ch)"),
            {"ev": ev, "ch": ch, "subj": subj, "html": html, "text": text,
             "dlt": dlt[ev] if ch == "sms" else None})


def downgrade():
    # Remove only what this migration inserted: templates whose body still
    # matches the shipped text (admin-edited rows are kept), and - only if
    # the permission row is ours (marker description) - its grants + row.
    conn = op.get_bind()
    for ev, ch, _subj, _html, text in _TEMPLATES:
        conn.execute(sa.text(
            "DELETE FROM notification_template WHERE event_type = :ev "
            "AND channel = :ch AND body_text = :text"),
            {"ev": ev, "ch": ch, "text": text})
    op.execute(
        "DELETE rp FROM role_permissions rp "
        "JOIN permission p ON p.id = rp.permission_id "
        f"WHERE p.name = 'broadcast send' AND p.description = '{_PERM_DESC}'"
    )
    op.execute(
        "DELETE FROM permission WHERE name = 'broadcast send' "
        f"AND description = '{_PERM_DESC}'"
    )
    op.drop_table("broadcast_recipient")
    op.drop_table("broadcast")
