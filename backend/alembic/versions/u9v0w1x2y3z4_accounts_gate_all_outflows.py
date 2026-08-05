"""accounts gate on all outflows (W13)

Extends the F6 payroll Accounts gate to expense reimbursement, salary
advances, and travel advances. Statuses are String columns (no ENUM ALTER);
only stamp columns + the shared 'accounts payment verify' permission are
added. Permission granted to the Accounts role + Super Admin.

Revision ID: u9v0w1x2y3z4
Revises: t8u9v0w1x2y3
Create Date: 2026-08-05
"""
from alembic import op
import sqlalchemy as sa

revision = "u9v0w1x2y3z4"
down_revision = "t8u9v0w1x2y3"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("expense_claim", sa.Column("accounts_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("expense_claim", sa.Column("accounts_verified_by_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_expense_claim_accts_verified_by", "expense_claim", "user", ["accounts_verified_by_id"], ["id"], ondelete="SET NULL")

    op.add_column("salaryadvance", sa.Column("accounts_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("salaryadvance", sa.Column("accounts_verified_by_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_salaryadvance_accts_verified_by", "salaryadvance", "user", ["accounts_verified_by_id"], ["id"], ondelete="SET NULL")

    op.add_column("travel_request", sa.Column("advance_paid_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("travel_request", sa.Column("accounts_verified_by_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_travel_request_accts_verified_by", "travel_request", "user", ["accounts_verified_by_id"], ["id"], ondelete="SET NULL")

    op.execute(
        "INSERT INTO permission (name, description) VALUES "
        "('accounts payment verify', 'Accounts: verify expense/advance/travel payouts before payment') "
        "ON DUPLICATE KEY UPDATE description = VALUES(description);"
    )
    op.execute(
        """
        INSERT IGNORE INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM role r, permission p
        WHERE r.name IN ('Accounts', 'Super Admin') AND p.name = 'accounts payment verify';
        """
    )


def downgrade():
    op.execute(
        "DELETE rp FROM role_permissions rp JOIN permission p ON rp.permission_id = p.id "
        "WHERE p.name = 'accounts payment verify';"
    )
    op.execute("DELETE FROM permission WHERE name = 'accounts payment verify';")
    op.drop_constraint("fk_travel_request_accts_verified_by", "travel_request", type_="foreignkey")
    op.drop_column("travel_request", "accounts_verified_by_id")
    op.drop_column("travel_request", "advance_paid_at")
    op.drop_constraint("fk_salaryadvance_accts_verified_by", "salaryadvance", type_="foreignkey")
    op.drop_column("salaryadvance", "accounts_verified_by_id")
    op.drop_column("salaryadvance", "accounts_verified_at")
    op.drop_constraint("fk_expense_claim_accts_verified_by", "expense_claim", type_="foreignkey")
    op.drop_column("expense_claim", "accounts_verified_by_id")
    op.drop_column("expense_claim", "accounts_verified_at")
