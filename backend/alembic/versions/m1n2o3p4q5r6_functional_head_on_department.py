"""functional head: head/deputy on department + permission (F1)

Adds head_user_id + deputy_head_user_id FKs to the department table, and a
'department head write' permission granted to the HR and Super Admin roles.

Revision ID: m1n2o3p4q5r6
Revises: l9g0h1i2j3k4
Create Date: 2026-08-03
"""
from alembic import op
import sqlalchemy as sa


revision = "m1n2o3p4q5r6"
down_revision = "l9g0h1i2j3k4"
branch_labels = None
depends_on = None

PERM = "department head write"


def upgrade():
    op.add_column("department", sa.Column("head_user_id", sa.Integer(), nullable=True))
    op.add_column("department", sa.Column("deputy_head_user_id", sa.Integer(), nullable=True))
    op.create_index("ix_department_head_user_id", "department", ["head_user_id"])
    op.create_index("ix_department_deputy_head_user_id", "department", ["deputy_head_user_id"])
    op.create_foreign_key(
        "fk_department_head_user", "department", "user",
        ["head_user_id"], ["id"], ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_department_deputy_head_user", "department", "user",
        ["deputy_head_user_id"], ["id"], ondelete="SET NULL",
    )

    op.execute(
        f"""
        INSERT INTO permission (name, description)
        VALUES ('{PERM}', 'Assign functional head / deputy to a department')
        ON DUPLICATE KEY UPDATE description = VALUES(description);
        """
    )
    op.execute(
        f"""
        INSERT IGNORE INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id
        FROM role r
        JOIN permission p ON p.name = '{PERM}'
        WHERE r.name IN ('HR', 'Super Admin');
        """
    )


def downgrade():
    op.execute(
        f"""
        DELETE rp FROM role_permissions rp
        JOIN permission p ON p.id = rp.permission_id
        WHERE p.name = '{PERM}';
        """
    )
    op.execute(f"DELETE FROM permission WHERE name = '{PERM}';")
    op.drop_constraint("fk_department_deputy_head_user", "department", type_="foreignkey")
    op.drop_constraint("fk_department_head_user", "department", type_="foreignkey")
    op.drop_index("ix_department_deputy_head_user_id", table_name="department")
    op.drop_index("ix_department_head_user_id", table_name="department")
    op.drop_column("department", "deputy_head_user_id")
    op.drop_column("department", "head_user_id")
