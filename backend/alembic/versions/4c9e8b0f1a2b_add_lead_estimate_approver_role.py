"""Add Lead Estimate Approver role and permission

Revision ID: 4c9e8b0f1a2b
Revises: 3f1c2a9d8b77
Create Date: 2026-03-12

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "4c9e8b0f1a2b"
down_revision: Union[str, None] = "3f1c2a9d8b77"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


LEAD_ESTIMATE_APPROVE = "lead estimate approve"
LEAD_ESTIMATE_APPROVER_ROLE = "Lead Estimate Approver"


def upgrade() -> None:
    # Permission
    op.execute(
        f"""
        INSERT INTO permission (name, description)
        VALUES (
            '{LEAD_ESTIMATE_APPROVE}',
            'Approve lead estimate value (final approval gating lead '
            'conversion)'
        )
        ON DUPLICATE KEY UPDATE description = VALUES(description);
        """
    )

    # Role
    op.execute(
        f"""
        INSERT INTO role (name, description)
        VALUES (
            '{LEAD_ESTIMATE_APPROVER_ROLE}',
            'Users allowed to approve lead estimate value'
        )
        ON DUPLICATE KEY UPDATE description = VALUES(description);
        """
    )

    # Map role -> permission
    op.execute(
        f"""
        INSERT IGNORE INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id
        FROM role r
        JOIN permission p ON p.name = '{LEAD_ESTIMATE_APPROVE}'
        WHERE r.name = '{LEAD_ESTIMATE_APPROVER_ROLE}';
        """
    )

    # Also grant existing authority roles the same permission (so
    # BD Manager/CEO/Admin can approve).
    op.execute(
        f"""
        INSERT IGNORE INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id
        FROM role r
        JOIN permission p ON p.name = '{LEAD_ESTIMATE_APPROVE}'
        WHERE r.name IN (
            'BD MANAGER',
            'CEO',
            'admin',
            'Admin',
            'Super Admin',
            'super admin'
        );
        """
    )


def downgrade() -> None:
    # Remove mappings first
    op.execute(
        f"""
        DELETE rp
        FROM role_permissions rp
        JOIN permission p ON p.id = rp.permission_id
        WHERE p.name = '{LEAD_ESTIMATE_APPROVE}';
        """
    )

    op.execute(
        f"DELETE FROM role WHERE name = '{LEAD_ESTIMATE_APPROVER_ROLE}';"
    )
    op.execute(
        f"DELETE FROM permission WHERE name = '{LEAD_ESTIMATE_APPROVE}';"
    )
