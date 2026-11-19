"""asset management: asset register tables, employee_asset link, backfill,
'asset manage' permission

Roadmap v2 Phase 5, Task 1.

Revision ID: e5a7c9b1d3f2
Revises: c4e8a2f6b1d9
Create Date: 2026-11-19
"""
import re

import sqlalchemy as sa
from alembic import op

revision = "e5a7c9b1d3f2"
down_revision = "c4e8a2f6b1d9"
branch_labels = None
depends_on = None

_ROLES = "('HR', 'Super Admin')"


def _code_for(name: str, used: set) -> str:
    alnum = re.sub(r"[^A-Za-z0-9]", "", name).upper()
    base = alnum[:3]
    if len(base) < 2:
        base = base.ljust(2, "X")
    code, n = base, 1
    while code in used:
        n += 1
        code = f"{base}{n}"
    return code


def upgrade():
    op.create_table(
        "asset_category",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False, unique=True),
        sa.Column("code", sa.String(10), nullable=False, unique=True),
        sa.Column("default_useful_life_months", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "asset",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("asset_tag", sa.String(32), nullable=False, unique=True),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("model", sa.String(150), nullable=True),
        sa.Column("serial_no", sa.String(100), nullable=True),
        sa.Column("status", sa.String(16), nullable=False,
                  server_default="in_stock"),
        sa.Column("location_id", sa.Integer(), nullable=True),
        sa.Column("vendor", sa.String(150), nullable=True),
        sa.Column("invoice_no", sa.String(64), nullable=True),
        sa.Column("purchase_date", sa.Date(), nullable=True),
        sa.Column("purchase_cost_paise", sa.Integer(), nullable=True),
        sa.Column("salvage_value_paise", sa.Integer(), nullable=False,
                  server_default="0"),
        sa.Column("useful_life_months", sa.Integer(), nullable=True),
        sa.Column("warranty_expiry", sa.Date(), nullable=True),
        sa.Column("amc_vendor", sa.String(150), nullable=True),
        sa.Column("amc_expiry", sa.Date(), nullable=True),
        sa.Column("warranty_alert_for", sa.Date(), nullable=True),
        sa.Column("amc_alert_for", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["asset_category.id"],
                                ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["location_id"], ["geofence_location.id"],
                                ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["user.id"],
                                ondelete="SET NULL"),
    )
    op.create_index("ix_asset_category_id", "asset", ["category_id"])
    op.create_index("ix_asset_serial_no", "asset", ["serial_no"])
    op.create_index("ix_asset_status", "asset", ["status"])
    op.create_index("ix_asset_warranty_expiry", "asset", ["warranty_expiry"])
    op.create_index("ix_asset_amc_expiry", "asset", ["amc_expiry"])

    op.create_table(
        "asset_maintenance",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("vendor", sa.String(150), nullable=True),
        sa.Column("cost_paise", sa.Integer(), nullable=False,
                  server_default="0"),
        sa.Column("started_on", sa.Date(), nullable=False),
        sa.Column("completed_on", sa.Date(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["asset.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["user.id"],
                                ondelete="SET NULL"),
    )
    op.create_index("ix_asset_maintenance_asset_id", "asset_maintenance",
                    ["asset_id"])

    # employee_asset additions (before asset_request, which references it)
    op.add_column("employee_asset", sa.Column("asset_id", sa.Integer(),
                                              nullable=True))
    op.add_column("employee_asset", sa.Column("allocated_by_id", sa.Integer(),
                                              nullable=True))
    op.add_column("employee_asset", sa.Column("returned_condition",
                                              sa.String(50), nullable=True))
    op.add_column("employee_asset", sa.Column("returned_to_id", sa.Integer(),
                                              nullable=True))
    op.create_index("ix_employee_asset_asset_id", "employee_asset",
                    ["asset_id"])
    op.create_foreign_key("fk_employee_asset_asset", "employee_asset", "asset",
                          ["asset_id"], ["id"], ondelete="RESTRICT")
    op.create_foreign_key("fk_employee_asset_allocated_by", "employee_asset",
                          "user", ["allocated_by_id"], ["id"],
                          ondelete="SET NULL")
    op.create_foreign_key("fk_employee_asset_returned_to", "employee_asset",
                          "user", ["returned_to_id"], ["id"],
                          ondelete="SET NULL")

    op.create_table(
        "asset_request",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("needed_by", sa.Date(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False,
                  server_default="pending"),
        sa.Column("approval_instance_id", sa.Integer(), nullable=True),
        sa.Column("decided_by_id", sa.Integer(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.String(500), nullable=True),
        sa.Column("fulfilled_asset_id", sa.Integer(), nullable=True),
        sa.Column("allocation_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["employee_id"], ["employee.id"],
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["category_id"], ["asset_category.id"],
                                ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["approval_instance_id"],
                                ["chained_approval_instance.id"],
                                ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["decided_by_id"], ["user.id"],
                                ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["fulfilled_asset_id"], ["asset.id"],
                                ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["allocation_id"], ["employee_asset.id"],
                                ondelete="SET NULL"),
    )
    op.create_index("ix_asset_request_employee_id", "asset_request",
                    ["employee_id"])
    op.create_index("ix_asset_request_status", "asset_request", ["status"])

    _backfill()

    op.execute(
        "INSERT INTO permission (name, description) "
        "SELECT 'asset manage', 'Manage the asset register, allocations, "
        "maintenance and asset requests' "
        "FROM DUAL WHERE NOT EXISTS "
        "(SELECT 1 FROM permission WHERE name = 'asset manage')"
    )
    op.execute(
        "INSERT IGNORE INTO role_permissions (role_id, permission_id) "
        "SELECT r.id, p.id FROM role r, permission p "
        f"WHERE r.name IN {_ROLES} AND p.name = 'asset manage'"
    )


def _backfill():
    bind = op.get_bind()
    types = [r[0] for r in bind.execute(
        sa.text("SELECT DISTINCT asset_type FROM employee_asset"))]
    cat_by_type, used = {}, set()
    for t in types:
        name = (t or "").strip() or "Other"
        if name in cat_by_type:
            cat_by_type[t] = cat_by_type[name]
            continue
        code = _code_for(name, used)
        used.add(code)
        bind.execute(
            sa.text("INSERT INTO asset_category (name, code, is_active, "
                    "created_at) VALUES (:n, :c, 1, NOW())"),
            {"n": name[:80], "c": code})
        cid = bind.execute(sa.text(
            "SELECT id FROM asset_category WHERE code = :c"), {"c": code}
        ).scalar_one()
        cat_by_type[name] = (cid, code)
        cat_by_type[t] = (cid, code)

    rows = bind.execute(sa.text(
        "SELECT id, asset_type, model, serial_no, status, created_at "
        "FROM employee_asset ORDER BY id")).all()
    for rid, atype, model, serial, status, created_at in rows:
        cid, code = cat_by_type[atype]
        astatus = {"allocated": "allocated", "lost": "lost"}.get(
            status, "in_stock")
        bind.execute(
            sa.text(
                "INSERT INTO asset (asset_tag, category_id, name, model, "
                "serial_no, status, salvage_value_paise, created_at, "
                "updated_at) VALUES (:tag, :cid, :name, :model, :serial, "
                ":status, 0, :ca, :ca)"),
            {"tag": f"TMP-{rid}", "cid": cid, "name": model, "model": model,
             "serial": serial, "status": astatus, "ca": created_at})
        aid = bind.execute(sa.text(
            "SELECT id FROM asset WHERE asset_tag = :t"),
            {"t": f"TMP-{rid}"}).scalar_one()
        bind.execute(sa.text(
            "UPDATE asset SET asset_tag = :t WHERE id = :i"),
            {"t": f"{code}-{aid:06d}", "i": aid})
        bind.execute(sa.text(
            "UPDATE employee_asset SET asset_id = :a WHERE id = :i"),
            {"a": aid, "i": rid})


def downgrade():
    op.execute(
        "DELETE rp FROM role_permissions rp "
        "JOIN role r ON r.id = rp.role_id "
        "JOIN permission p ON p.id = rp.permission_id "
        f"WHERE r.name IN {_ROLES} AND p.name = 'asset manage'"
    )
    op.execute(
        "DELETE FROM permission WHERE name = 'asset manage' AND NOT EXISTS "
        "(SELECT 1 FROM role_permissions rp WHERE rp.permission_id = "
        "permission.id)"
    )

    op.drop_table("asset_request")
    op.drop_constraint("fk_employee_asset_returned_to", "employee_asset",
                       type_="foreignkey")
    op.drop_constraint("fk_employee_asset_allocated_by", "employee_asset",
                       type_="foreignkey")
    op.drop_constraint("fk_employee_asset_asset", "employee_asset",
                       type_="foreignkey")
    op.drop_index("ix_employee_asset_asset_id", table_name="employee_asset")
    for c in ("returned_to_id", "returned_condition", "allocated_by_id",
              "asset_id"):
        op.drop_column("employee_asset", c)
    op.drop_table("asset_maintenance")
    op.drop_table("asset")
    op.drop_table("asset_category")
