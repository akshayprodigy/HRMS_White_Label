"""Add COO role, permissions, and extend bid task review status enum

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-24

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text


revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None

COO_ROLE = "COO"
COO_PERMISSIONS = [
    ("project coo view", "COO-level visibility across all projects and PM progress"),
    ("coo dashboard view", "Access to COO cross-project monitoring dashboard"),
    ("project write", "Create and manage projects"),
    ("project cost approve dop", "Approve cost changes above threshold"),
]


def upgrade() -> None:
    bind = op.get_bind()

    # --- Extend the review status enum (MariaDB/MySQL approach) ---
    # MariaDB stores ENUMs as column constraints, so we alter the column directly.
    try:
        op.execute(
            text(
                "ALTER TABLE lead_bid_task_review "
                "MODIFY COLUMN status ENUM('draft','submitted','accepted','revision_requested') "
                "NOT NULL DEFAULT 'draft'"
            )
        )
    except Exception:
        pass  # Already extended or not applicable

    # --- COO Permissions ---
    for perm_name, perm_desc in COO_PERMISSIONS:
        op.execute(
            text(
                f"INSERT INTO permission (name, description) "
                f"VALUES (:name, :desc) "
                f"ON DUPLICATE KEY UPDATE description = VALUES(description)"
            ).bindparams(name=perm_name, desc=perm_desc)
        )

    # --- COO Role ---
    op.execute(
        text(
            "INSERT INTO role (name, description) "
            "VALUES (:name, :desc) "
            "ON DUPLICATE KEY UPDATE description = VALUES(description)"
        ).bindparams(
            name=COO_ROLE,
            desc="Chief Operating Officer — cross-project oversight and monitoring",
        )
    )

    # --- Map COO role -> all COO permissions ---
    for perm_name, _ in COO_PERMISSIONS:
        op.execute(
            text(
                "INSERT IGNORE INTO role_permissions (role_id, permission_id) "
                "SELECT r.id, p.id FROM role r "
                "JOIN permission p ON p.name = :perm "
                "WHERE r.name = :role"
            ).bindparams(perm=perm_name, role=COO_ROLE)
        )

    # Also grant Super Admin the new COO perms
    for perm_name, _ in [
        ("project coo view", ""),
        ("coo dashboard view", ""),
    ]:
        op.execute(
            text(
                "INSERT IGNORE INTO role_permissions (role_id, permission_id) "
                "SELECT r.id, p.id FROM role r "
                "JOIN permission p ON p.name = :perm "
                "WHERE r.name IN ('Super Admin', 'super admin', 'admin', 'Admin', 'CEO', 'ceo')"
            ).bindparams(perm=perm_name)
        )


def downgrade() -> None:
    # Revert enum
    try:
        op.execute(
            text(
                "ALTER TABLE lead_bid_task_review "
                "MODIFY COLUMN status ENUM('draft','submitted') "
                "NOT NULL DEFAULT 'draft'"
            )
        )
    except Exception:
        pass

    # Remove COO role mappings
    op.execute(
        text(
            "DELETE rp FROM role_permissions rp "
            "JOIN role r ON r.id = rp.role_id "
            "WHERE r.name = :role"
        ).bindparams(role=COO_ROLE)
    )
    op.execute(
        text("DELETE FROM role WHERE name = :role").bindparams(role=COO_ROLE)
    )
    for perm_name, _ in COO_PERMISSIONS:
        op.execute(
            text("DELETE FROM permission WHERE name = :name").bindparams(name=perm_name)
        )
