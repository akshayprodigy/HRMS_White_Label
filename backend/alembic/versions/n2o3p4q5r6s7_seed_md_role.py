"""seed MD (Managing Director) role (F4)

Adds a top-level MD approver role used by the ceo/md approver types in the
generic approval engine (e.g. salary-revision final sign-off).

Revision ID: n2o3p4q5r6s7
Revises: m1n2o3p4q5r6
Create Date: 2026-08-03
"""
from alembic import op

revision = "n2o3p4q5r6s7"
down_revision = "m1n2o3p4q5r6"
branch_labels = None
depends_on = None

ROLE = "MD"


def upgrade():
    op.execute(
        f"""
        INSERT INTO role (name, description)
        VALUES ('{ROLE}', 'Managing Director — top-level approver')
        ON DUPLICATE KEY UPDATE description = VALUES(description);
        """
    )


def downgrade():
    # Association rows (user_roles/role_permissions) cascade via their FKs.
    op.execute(f"DELETE FROM role WHERE name = '{ROLE}';")
