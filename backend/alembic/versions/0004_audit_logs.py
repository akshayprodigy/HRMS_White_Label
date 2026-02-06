"""audit logs

Revision ID: 0004_audit_logs
Revises: 0003_core_entities
Create Date: 2026-02-05

"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0004_audit_logs"
down_revision = "0003_core_entities"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("entity_type", sa.String(length=100), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("before_json", sa.JSON(), nullable=True),
        sa.Column("after_json", sa.JSON(), nullable=True),
        sa.Column("actor_user_id", sa.BigInteger(), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name="fk_audit_logs_actor_user",
        ),
    )

    op.create_index(
        "ix_audit_logs_entity",
        "audit_logs",
        ["entity_type", "entity_id"],
    )
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index(
        "ix_audit_logs_actor_user_id",
        "audit_logs",
        ["actor_user_id"],
    )
    op.create_index(
        "ix_audit_logs_created_at",
        "audit_logs",
        ["created_at"],
    )
    op.create_index(
        "ix_audit_logs_request_id",
        "audit_logs",
        ["request_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_audit_logs_request_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
    op.drop_index("ix_audit_logs_actor_user_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_action", table_name="audit_logs")
    op.drop_index("ix_audit_logs_entity", table_name="audit_logs")
    op.drop_table("audit_logs")
