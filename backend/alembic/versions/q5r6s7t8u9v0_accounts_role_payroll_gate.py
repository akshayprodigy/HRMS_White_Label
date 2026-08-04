"""accounts role + payroll accounts-approval gate (F6)

Adds an Accounts actor that verifies a FINALIZED payroll run before it can
be published/paid. Extends the run status enum with ACCOUNTS_APPROVED, adds
accounts_approved_at/by columns, seeds the `payroll accounts verify`
permission + `Accounts` role, and gives Accounts ownership of income-tax/TDS
config (tax config write/view/verify/generate) per the locked decision.

Revision ID: q5r6s7t8u9v0
Revises: p4q5r6s7t8u9
Create Date: 2026-08-04
"""
from alembic import op
import sqlalchemy as sa

revision = "q5r6s7t8u9v0"
down_revision = "p4q5r6s7t8u9"
branch_labels = None
depends_on = None

# DB stores enum by NAME (uppercase), NOT NULL.
NEW_ENUM = (
    "ENUM('DRAFT','ATTENDANCE_LOCKED','LEAVES_LOCKED','DRAFT_GENERATED',"
    "'FINALIZED','ACCOUNTS_APPROVED','PUBLISHED')"
)
OLD_ENUM = (
    "ENUM('DRAFT','ATTENDANCE_LOCKED','LEAVES_LOCKED','DRAFT_GENERATED',"
    "'FINALIZED','PUBLISHED')"
)

ACCOUNTS_PERMS = [
    "payroll accounts verify",
    "hr payroll view",
    "tax config write",
    "tax view all",
    "tax declaration verify",
    "tax generate",
]


def upgrade():
    # 1. Extend the run status enum.
    op.execute(f"ALTER TABLE payrollrun MODIFY COLUMN status {NEW_ENUM} NOT NULL;")

    # 2. Accounts-approval stamp columns.
    op.add_column("payrollrun", sa.Column("accounts_approved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("payrollrun", sa.Column("accounts_approved_by_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_payrollrun_accounts_approved_by", "payrollrun", "user",
        ["accounts_approved_by_id"], ["id"],
    )

    # 3. Permission + Accounts role.
    op.execute(
        "INSERT INTO permission (name, description) VALUES "
        "('payroll accounts verify', 'Accounts: verify/approve finalized payroll before payment') "
        "ON DUPLICATE KEY UPDATE description = VALUES(description);"
    )
    op.execute(
        "INSERT INTO role (name, description) VALUES "
        "('Accounts', 'Accounts — verifies payroll before payment & owns income-tax/TDS config') "
        "ON DUPLICATE KEY UPDATE description = VALUES(description);"
    )

    # 4. Grant the Accounts role its permissions.
    perm_list = ",".join(f"'{p}'" for p in ACCOUNTS_PERMS)
    op.execute(
        f"""
        INSERT IGNORE INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM role r, permission p
        WHERE r.name = 'Accounts' AND p.name IN ({perm_list});
        """
    )
    # Super Admin gets the verify perm explicitly (superusers bypass anyway).
    op.execute(
        """
        INSERT IGNORE INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM role r, permission p
        WHERE r.name = 'Super Admin' AND p.name = 'payroll accounts verify';
        """
    )


def downgrade():
    op.execute(
        "DELETE rp FROM role_permissions rp JOIN permission p ON rp.permission_id = p.id "
        "WHERE p.name = 'payroll accounts verify';"
    )
    op.execute("DELETE FROM permission WHERE name = 'payroll accounts verify';")
    op.execute("DELETE FROM role WHERE name = 'Accounts';")
    op.drop_constraint("fk_payrollrun_accounts_approved_by", "payrollrun", type_="foreignkey")
    op.drop_column("payrollrun", "accounts_approved_by_id")
    op.drop_column("payrollrun", "accounts_approved_at")
    # Revert enum (any ACCOUNTS_APPROVED rows must be resolved first).
    op.execute(f"ALTER TABLE payrollrun MODIFY COLUMN status {OLD_ENUM} NOT NULL;")
