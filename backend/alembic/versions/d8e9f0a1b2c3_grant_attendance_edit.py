"""grant 'attendance edit' to HR / Super Admin

The 'attendance edit' permission guards HR punch edits / manual attendance
and org-wide approval of attendance regularization requests. It was only
ever created by the dev seed (scripts/seed_month_data.py), so real
deployments had no role holding it. Create it if absent and grant it to
HR + Super Admin.

Downgrade removes only the grants; the permission row is left in place
because the dev seed may have created it before this migration ran.

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-11-12
"""
from alembic import op

revision = "d8e9f0a1b2c3"
down_revision = "c7d8e9f0a1b2"
branch_labels = None
depends_on = None

_ROLES = "('HR', 'Super Admin')"


def upgrade():
    op.execute(
        "INSERT INTO permission (name, description) "
        "SELECT 'attendance edit', 'Directly edit/create employee punch records' "
        "FROM DUAL WHERE NOT EXISTS "
        "(SELECT 1 FROM permission WHERE name = 'attendance edit')"
    )
    op.execute(
        "INSERT IGNORE INTO role_permissions (role_id, permission_id) "
        "SELECT r.id, p.id FROM role r, permission p "
        f"WHERE r.name IN {_ROLES} AND p.name = 'attendance edit'"
    )


def downgrade():
    op.execute(
        "DELETE rp FROM role_permissions rp "
        "JOIN role r ON r.id = rp.role_id "
        "JOIN permission p ON p.id = rp.permission_id "
        f"WHERE r.name IN {_ROLES} AND p.name = 'attendance edit'"
    )
