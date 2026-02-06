"""inventory module

Revision ID: 0007
Revises: 0006_hr_leaves
Create Date: 2026-02-05

"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "0007"
down_revision = "0006_hr_leaves"
branch_labels = None
depends_on = None

_FK_COST_CENTERS_ID = "cost_centers.id"
_FK_ITEMS_ID = "items.id"
_FK_PROJECTS_ID = "projects.id"
_FK_UOMS_ID = "uoms.id"
_FK_WAREHOUSES_ID = "warehouses.id"


def upgrade() -> None:
    op.create_table(
        "uoms",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(length=20), nullable=False, unique=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
        ),
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
    )
    op.create_index("ix_uoms_is_active", "uoms", ["is_active"], unique=False)

    op.create_table(
        "warehouses",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(length=50), nullable=False, unique=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
        ),
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
    )
    op.create_index(
        "ix_warehouses_is_active",
        "warehouses",
        ["is_active"],
        unique=False,
    )

    op.create_table(
        "items",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("sku", sa.String(length=50), nullable=False, unique=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column(
            "base_uom_id",
            sa.BigInteger(),
            sa.ForeignKey(_FK_UOMS_ID),
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
        ),
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
    )
    op.create_index(
        "ix_items_base_uom_id",
        "items",
        ["base_uom_id"],
        unique=False,
    )
    op.create_index("ix_items_is_active", "items", ["is_active"], unique=False)

    op.create_table(
        "purchase_orders",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "po_number",
            sa.String(length=50),
            nullable=False,
            unique=True,
        ),
        sa.Column("vendor_name", sa.String(length=255), nullable=True),
        sa.Column("po_date", sa.Date(), nullable=False),
        sa.Column(
            "warehouse_id",
            sa.BigInteger(),
            sa.ForeignKey(_FK_WAREHOUSES_ID),
            nullable=True,
        ),
        sa.Column(
            "item_id",
            sa.BigInteger(),
            sa.ForeignKey(_FK_ITEMS_ID),
            nullable=False,
        ),
        sa.Column(
            "uom_id",
            sa.BigInteger(),
            sa.ForeignKey(_FK_UOMS_ID),
            nullable=False,
        ),
        sa.Column("qty_ordered", sa.Numeric(14, 3), nullable=False),
        sa.Column("unit_cost", sa.Numeric(14, 2), nullable=True),
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
            server_default=sa.text("'open'"),
        ),
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
    )
    op.create_index(
        "ix_purchase_orders_po_date",
        "purchase_orders",
        ["po_date"],
        unique=False,
    )
    op.create_index(
        "ix_purchase_orders_item_id",
        "purchase_orders",
        ["item_id"],
        unique=False,
    )

    op.create_table(
        "grns",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "grn_number",
            sa.String(length=50),
            nullable=False,
            unique=True,
        ),
        sa.Column("grn_date", sa.Date(), nullable=False),
        sa.Column(
            "purchase_order_id",
            sa.BigInteger(),
            sa.ForeignKey("purchase_orders.id"),
            nullable=True,
        ),
        sa.Column("vendor_name", sa.String(length=255), nullable=True),
        sa.Column(
            "warehouse_id",
            sa.BigInteger(),
            sa.ForeignKey(_FK_WAREHOUSES_ID),
            nullable=False,
        ),
        sa.Column(
            "item_id",
            sa.BigInteger(),
            sa.ForeignKey(_FK_ITEMS_ID),
            nullable=False,
        ),
        sa.Column(
            "uom_id",
            sa.BigInteger(),
            sa.ForeignKey(_FK_UOMS_ID),
            nullable=False,
        ),
        sa.Column("qty_received", sa.Numeric(14, 3), nullable=False),
        sa.Column("unit_cost", sa.Numeric(14, 2), nullable=True),
        sa.Column("notes", sa.String(length=500), nullable=True),
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
    )
    op.create_index("ix_grns_grn_date", "grns", ["grn_date"], unique=False)
    op.create_index("ix_grns_item_id", "grns", ["item_id"], unique=False)
    op.create_index(
        "ix_grns_warehouse_id",
        "grns",
        ["warehouse_id"],
        unique=False,
    )

    op.create_table(
        "material_issues",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "issue_number",
            sa.String(length=50),
            nullable=False,
            unique=True,
        ),
        sa.Column("issue_date", sa.Date(), nullable=False),
        sa.Column(
            "project_id",
            sa.BigInteger(),
            sa.ForeignKey(_FK_PROJECTS_ID),
            nullable=False,
        ),
        sa.Column(
            "cost_center_id",
            sa.BigInteger(),
            sa.ForeignKey(_FK_COST_CENTERS_ID),
            nullable=False,
        ),
        sa.Column(
            "warehouse_id",
            sa.BigInteger(),
            sa.ForeignKey(_FK_WAREHOUSES_ID),
            nullable=False,
        ),
        sa.Column(
            "item_id",
            sa.BigInteger(),
            sa.ForeignKey(_FK_ITEMS_ID),
            nullable=False,
        ),
        sa.Column(
            "uom_id",
            sa.BigInteger(),
            sa.ForeignKey(_FK_UOMS_ID),
            nullable=False,
        ),
        sa.Column("qty_issued", sa.Numeric(14, 3), nullable=False),
        sa.Column("unit_cost", sa.Numeric(14, 2), nullable=True),
        sa.Column("remarks", sa.String(length=500), nullable=True),
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
    )
    op.create_index(
        "ix_material_issues_issue_date",
        "material_issues",
        ["issue_date"],
        unique=False,
    )
    op.create_index(
        "ix_material_issues_project_id",
        "material_issues",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "ix_material_issues_cost_center_id",
        "material_issues",
        ["cost_center_id"],
        unique=False,
    )
    op.create_index(
        "ix_material_issues_project_id_issue_date",
        "material_issues",
        ["project_id", "issue_date"],
        unique=False,
    )

    op.create_table(
        "stock_ledger",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("txn_date", sa.Date(), nullable=False),
        sa.Column(
            "item_id",
            sa.BigInteger(),
            sa.ForeignKey(_FK_ITEMS_ID),
            nullable=False,
        ),
        sa.Column(
            "warehouse_id",
            sa.BigInteger(),
            sa.ForeignKey(_FK_WAREHOUSES_ID),
            nullable=False,
        ),
        sa.Column(
            "uom_id",
            sa.BigInteger(),
            sa.ForeignKey(_FK_UOMS_ID),
            nullable=False,
        ),
        sa.Column("source_type", sa.String(length=20), nullable=False),
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "qty_in",
            sa.Numeric(14, 3),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "qty_out",
            sa.Numeric(14, 3),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("unit_cost", sa.Numeric(14, 2), nullable=True),
        sa.Column(
            "project_id",
            sa.BigInteger(),
            sa.ForeignKey(_FK_PROJECTS_ID),
            nullable=True,
        ),
        sa.Column(
            "cost_center_id",
            sa.BigInteger(),
            sa.ForeignKey(_FK_COST_CENTERS_ID),
            nullable=True,
        ),
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
    )
    op.create_index(
        "ix_stock_ledger_txn_date",
        "stock_ledger",
        ["txn_date"],
        unique=False,
    )
    op.create_index(
        "ix_stock_ledger_item_id",
        "stock_ledger",
        ["item_id"],
        unique=False,
    )
    op.create_index(
        "ix_stock_ledger_warehouse_id",
        "stock_ledger",
        ["warehouse_id"],
        unique=False,
    )
    op.create_index(
        "ix_stock_ledger_project_id",
        "stock_ledger",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "ix_stock_ledger_project_id_txn_date",
        "stock_ledger",
        ["project_id", "txn_date"],
        unique=False,
    )
    op.create_index(
        "ix_stock_ledger_item_wh_date",
        "stock_ledger",
        ["item_id", "warehouse_id", "txn_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_stock_ledger_item_wh_date", table_name="stock_ledger")
    op.drop_index(
        "ix_stock_ledger_project_id_txn_date",
        table_name="stock_ledger",
    )
    op.drop_index("ix_stock_ledger_project_id", table_name="stock_ledger")
    op.drop_index("ix_stock_ledger_warehouse_id", table_name="stock_ledger")
    op.drop_index("ix_stock_ledger_item_id", table_name="stock_ledger")
    op.drop_index("ix_stock_ledger_txn_date", table_name="stock_ledger")
    op.drop_table("stock_ledger")

    op.drop_index(
        "ix_material_issues_project_id_issue_date",
        table_name="material_issues",
    )
    op.drop_index(
        "ix_material_issues_cost_center_id",
        table_name="material_issues",
    )
    op.drop_index(
        "ix_material_issues_project_id",
        table_name="material_issues",
    )
    op.drop_index(
        "ix_material_issues_issue_date",
        table_name="material_issues",
    )
    op.drop_table("material_issues")

    op.drop_index("ix_grns_warehouse_id", table_name="grns")
    op.drop_index("ix_grns_item_id", table_name="grns")
    op.drop_index("ix_grns_grn_date", table_name="grns")
    op.drop_table("grns")

    op.drop_index("ix_purchase_orders_item_id", table_name="purchase_orders")
    op.drop_index("ix_purchase_orders_po_date", table_name="purchase_orders")
    op.drop_table("purchase_orders")

    op.drop_index("ix_items_is_active", table_name="items")
    op.drop_index("ix_items_base_uom_id", table_name="items")
    op.drop_table("items")

    op.drop_index("ix_warehouses_is_active", table_name="warehouses")
    op.drop_table("warehouses")

    op.drop_index("ix_uoms_is_active", table_name="uoms")
    op.drop_table("uoms")
