from __future__ import annotations

import datetime as dt

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.mixins import AuditMixin

_FK_COST_CENTERS_ID = "cost_centers.id"
_FK_ITEMS_ID = "items.id"
_FK_PROJECTS_ID = "projects.id"
_FK_UOMS_ID = "uoms.id"
_FK_WAREHOUSES_ID = "warehouses.id"


class Uom(AuditMixin, Base):
    __tablename__ = "uoms"

    id: Mapped[int] = mapped_column(
        sa.BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    code: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        unique=True,
    )
    name: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    symbol: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean(),
        nullable=False,
        server_default=sa.text("1"),
    )

    __table_args__ = (sa.Index("ix_uoms_is_active", "is_active"),)


class Item(AuditMixin, Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(
        sa.BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    sku: Mapped[str] = mapped_column(
        sa.String(50),
        nullable=False,
        unique=True,
    )
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(
        sa.String(500),
        nullable=True,
    )
    base_uom_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey(_FK_UOMS_ID),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean(),
        nullable=False,
        server_default=sa.text("1"),
    )

    __table_args__ = (
        sa.Index("ix_items_base_uom_id", "base_uom_id"),
        sa.Index("ix_items_is_active", "is_active"),
    )


class Warehouse(AuditMixin, Base):
    __tablename__ = "warehouses"

    id: Mapped[int] = mapped_column(
        sa.BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    code: Mapped[str] = mapped_column(
        sa.String(50),
        nullable=False,
        unique=True,
    )
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    location: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean(),
        nullable=False,
        server_default=sa.text("1"),
    )

    __table_args__ = (sa.Index("ix_warehouses_is_active", "is_active"),)


class PurchaseOrder(AuditMixin, Base):
    __tablename__ = "purchase_orders"

    id: Mapped[int] = mapped_column(
        sa.BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    po_number: Mapped[str] = mapped_column(
        sa.String(50),
        nullable=False,
        unique=True,
    )
    vendor_name: Mapped[str | None] = mapped_column(
        sa.String(255),
        nullable=True,
    )
    po_date: Mapped[dt.date] = mapped_column(sa.Date(), nullable=False)

    warehouse_id: Mapped[int | None] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey(_FK_WAREHOUSES_ID),
        nullable=True,
    )

    item_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey(_FK_ITEMS_ID),
        nullable=False,
    )
    uom_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey(_FK_UOMS_ID),
        nullable=False,
    )

    qty_ordered: Mapped[float] = mapped_column(
        sa.Numeric(14, 3),
        nullable=False,
    )
    unit_cost: Mapped[float | None] = mapped_column(
        sa.Numeric(14, 2),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        sa.String(30),
        nullable=False,
        server_default=sa.text("'open'"),
    )

    __table_args__ = (
        sa.Index("ix_purchase_orders_po_date", "po_date"),
        sa.Index("ix_purchase_orders_item_id", "item_id"),
    )


class Grn(AuditMixin, Base):
    __tablename__ = "grns"

    id: Mapped[int] = mapped_column(
        sa.BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    grn_number: Mapped[str] = mapped_column(
        sa.String(50),
        nullable=False,
        unique=True,
    )
    grn_date: Mapped[dt.date] = mapped_column(sa.Date(), nullable=False)

    purchase_order_id: Mapped[int | None] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey("purchase_orders.id"),
        nullable=True,
    )
    vendor_name: Mapped[str | None] = mapped_column(
        sa.String(255),
        nullable=True,
    )

    warehouse_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey(_FK_WAREHOUSES_ID),
        nullable=False,
    )
    item_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey(_FK_ITEMS_ID),
        nullable=False,
    )
    uom_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey(_FK_UOMS_ID),
        nullable=False,
    )

    qty_received: Mapped[float] = mapped_column(
        sa.Numeric(14, 3),
        nullable=False,
    )
    unit_cost: Mapped[float | None] = mapped_column(
        sa.Numeric(14, 2),
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)

    __table_args__ = (
        sa.Index("ix_grns_grn_date", "grn_date"),
        sa.Index("ix_grns_item_id", "item_id"),
        sa.Index("ix_grns_warehouse_id", "warehouse_id"),
    )


class MaterialIssue(AuditMixin, Base):
    __tablename__ = "material_issues"

    id: Mapped[int] = mapped_column(
        sa.BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    issue_number: Mapped[str] = mapped_column(
        sa.String(50),
        nullable=False,
        unique=True,
    )
    issue_date: Mapped[dt.date] = mapped_column(sa.Date(), nullable=False)

    project_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey(_FK_PROJECTS_ID),
        nullable=False,
    )
    cost_center_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey(_FK_COST_CENTERS_ID),
        nullable=False,
    )

    warehouse_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey(_FK_WAREHOUSES_ID),
        nullable=False,
    )
    item_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey(_FK_ITEMS_ID),
        nullable=False,
    )
    uom_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey(_FK_UOMS_ID),
        nullable=False,
    )

    qty_issued: Mapped[float] = mapped_column(
        sa.Numeric(14, 3),
        nullable=False,
    )
    unit_cost: Mapped[float | None] = mapped_column(
        sa.Numeric(14, 2),
        nullable=True,
    )
    remarks: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)

    __table_args__ = (
        sa.Index("ix_material_issues_issue_date", "issue_date"),
        sa.Index("ix_material_issues_project_id", "project_id"),
        sa.Index("ix_material_issues_cost_center_id", "cost_center_id"),
        sa.Index(
            "ix_material_issues_project_id_issue_date",
            "project_id",
            "issue_date",
        ),
    )


class StockLedger(AuditMixin, Base):
    __tablename__ = "stock_ledger"

    id: Mapped[int] = mapped_column(
        sa.BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    txn_date: Mapped[dt.date] = mapped_column(sa.Date(), nullable=False)

    item_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey(_FK_ITEMS_ID),
        nullable=False,
    )
    warehouse_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey(_FK_WAREHOUSES_ID),
        nullable=False,
    )
    uom_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey(_FK_UOMS_ID),
        nullable=False,
    )

    source_type: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    source_id: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)

    qty_in: Mapped[float] = mapped_column(
        sa.Numeric(14, 3),
        nullable=False,
        server_default=sa.text("0"),
    )
    qty_out: Mapped[float] = mapped_column(
        sa.Numeric(14, 3),
        nullable=False,
        server_default=sa.text("0"),
    )
    unit_cost: Mapped[float | None] = mapped_column(
        sa.Numeric(14, 2),
        nullable=True,
    )

    project_id: Mapped[int | None] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey(_FK_PROJECTS_ID),
        nullable=True,
    )
    cost_center_id: Mapped[int | None] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey(_FK_COST_CENTERS_ID),
        nullable=True,
    )

    __table_args__ = (
        sa.Index("ix_stock_ledger_txn_date", "txn_date"),
        sa.Index("ix_stock_ledger_item_id", "item_id"),
        sa.Index("ix_stock_ledger_warehouse_id", "warehouse_id"),
        sa.Index("ix_stock_ledger_project_id", "project_id"),
        sa.Index(
            "ix_stock_ledger_project_id_txn_date",
            "project_id",
            "txn_date",
        ),
        sa.Index(
            "ix_stock_ledger_item_wh_date",
            "item_id",
            "warehouse_id",
            "txn_date",
        ),
    )
