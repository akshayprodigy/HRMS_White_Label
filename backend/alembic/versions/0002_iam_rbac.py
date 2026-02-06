"""iam and rbac

Revision ID: 0002_iam_rbac
Revises: 0001_init
Create Date: 2026-02-05

"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0002_iam_rbac"
down_revision = "0001_init"
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
        "users",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        *_audit_columns(),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "roles",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        *_audit_columns(),
        sa.UniqueConstraint("name", name="uq_roles_name"),
    )
    op.create_index("ix_roles_name", "roles", ["name"], unique=True)

    op.create_table(
        "permissions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(length=150), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        *_audit_columns(),
        sa.UniqueConstraint("code", name="uq_permissions_code"),
    )
    op.create_index(
        "ix_permissions_code",
        "permissions",
        ["code"],
        unique=True,
    )

    op.create_table(
        "user_roles",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("role_id", sa.BigInteger(), nullable=False),
        *_audit_columns(),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_user_roles_user",
        ),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["roles.id"],
            name="fk_user_roles_role",
        ),
        sa.UniqueConstraint(
            "user_id",
            "role_id",
            name="uq_user_roles_user_id_role_id",
        ),
    )
    op.create_index("ix_user_roles_user_id", "user_roles", ["user_id"])
    op.create_index("ix_user_roles_role_id", "user_roles", ["role_id"])

    op.create_table(
        "role_permissions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("role_id", sa.BigInteger(), nullable=False),
        sa.Column("permission_id", sa.BigInteger(), nullable=False),
        *_audit_columns(),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["roles.id"],
            name="fk_role_permissions_role",
        ),
        sa.ForeignKeyConstraint(
            ["permission_id"],
            ["permissions.id"],
            name="fk_role_permissions_permission",
        ),
        sa.UniqueConstraint(
            "role_id",
            "permission_id",
            name="uq_role_permissions_role_id_permission_id",
        ),
    )
    op.create_index(
        "ix_role_permissions_role_id",
        "role_permissions",
        ["role_id"],
    )
    op.create_index(
        "ix_role_permissions_permission_id",
        "role_permissions",
        ["permission_id"],
    )

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("jti", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        *_audit_columns(),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_refresh_tokens_user",
        ),
        sa.UniqueConstraint("jti", name="uq_refresh_tokens_jti"),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index(
        "ix_refresh_tokens_expires_at",
        "refresh_tokens",
        ["expires_at"],
    )
    op.create_index(
        "ix_refresh_tokens_jti",
        "refresh_tokens",
        ["jti"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_refresh_tokens_jti", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_expires_at", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")

    op.drop_index(
        "ix_role_permissions_permission_id",
        table_name="role_permissions",
    )
    op.drop_index("ix_role_permissions_role_id", table_name="role_permissions")
    op.drop_table("role_permissions")

    op.drop_index("ix_user_roles_role_id", table_name="user_roles")
    op.drop_index("ix_user_roles_user_id", table_name="user_roles")
    op.drop_table("user_roles")

    op.drop_index("ix_permissions_code", table_name="permissions")
    op.drop_table("permissions")

    op.drop_index("ix_roles_name", table_name="roles")
    op.drop_table("roles")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
