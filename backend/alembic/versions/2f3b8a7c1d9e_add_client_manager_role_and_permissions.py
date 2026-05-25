"""add client manager role and client permissions

Revision ID: 2f3b8a7c1d9e
Revises: 820fe877db81
Create Date: 2026-03-05

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "2f3b8a7c1d9e"
down_revision: Union[str, None] = "820fe877db81"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Permissions
    op.execute(
        """
        INSERT INTO permission (name, description)
        VALUES ('client read', 'List/search clients for selection'),
               ('client create', 'Create new client records'),
               ('client write', 'Update client records')
        ON DUPLICATE KEY UPDATE description = VALUES(description);
        """
    )

    # Role
    op.execute(
        """
        INSERT INTO role (name, description)
        VALUES ('Client Manager', 'Create and maintain client master data')
        ON DUPLICATE KEY UPDATE description = VALUES(description);
        """
    )

    # Role -> permissions mapping
    op.execute(
        """
        INSERT IGNORE INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id
        FROM role r
        JOIN permission p
          ON p.name IN ('client read', 'client create', 'client write')
        WHERE r.name = 'Client Manager';
        """
    )

    # Grant BD the ability to select clients and add new ones (minimal).
    op.execute(
        """
        INSERT IGNORE INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id
        FROM role r
        JOIN permission p
          ON p.name IN ('client read', 'client create')
        WHERE r.name = 'Business Developer';
        """
    )

    # Grant Super Admin (if present) the client permissions too.
    op.execute(
        """
        INSERT IGNORE INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id
        FROM role r
        JOIN permission p
          ON p.name IN ('client read', 'client create', 'client write')
        WHERE r.name = 'Super Admin';
        """
    )


def downgrade() -> None:
    # Remove mappings first
    op.execute(
        """
        DELETE rp
        FROM role_permissions rp
        JOIN role r ON r.id = rp.role_id
        JOIN permission p ON p.id = rp.permission_id
        WHERE (r.name = 'Client Manager'
               AND p.name IN ('client read', 'client create', 'client write'))
           OR (r.name = 'Business Developer'
               AND p.name IN ('client read', 'client create'))
           OR (r.name = 'Super Admin'
               AND p.name IN ('client read', 'client create', 'client write'));
        """
    )

    # Drop role
    op.execute("DELETE FROM role WHERE name = 'Client Manager';")

    # Drop permissions
    op.execute(
        """
        DELETE FROM permission
        WHERE name IN ('client read', 'client create', 'client write');
        """
    )
