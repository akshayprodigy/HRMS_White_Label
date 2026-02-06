from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# Masters


class UomPublic(ORMModel):
    id: int
    code: str
    name: str
    symbol: str | None
    is_active: bool
    created_at: dt.datetime
    updated_at: dt.datetime


class UomCreate(BaseModel):
    code: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=100)
    symbol: str | None = Field(default=None, max_length=20)
    is_active: bool = True


class UomUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=20)
    name: str | None = Field(default=None, min_length=1, max_length=100)
    symbol: str | None = Field(default=None, max_length=20)
    is_active: bool | None = None


class WarehousePublic(ORMModel):
    id: int
    code: str
    name: str
    location: str | None
    is_active: bool
    created_at: dt.datetime
    updated_at: dt.datetime


class WarehouseCreate(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=255)
    location: str | None = Field(default=None, max_length=255)
    is_active: bool = True


class WarehouseUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=50)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    location: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None


class ItemPublic(ORMModel):
    id: int
    sku: str
    name: str
    description: str | None
    base_uom_id: int
    is_active: bool
    created_at: dt.datetime
    updated_at: dt.datetime


class ItemCreate(BaseModel):
    sku: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=500)
    base_uom_id: int
    is_active: bool = True


class ItemUpdate(BaseModel):
    sku: str | None = Field(default=None, min_length=1, max_length=50)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=500)
    base_uom_id: int | None = None
    is_active: bool | None = None


# Transactions


class PurchaseOrderPublic(ORMModel):
    id: int
    po_number: str
    vendor_name: str | None
    po_date: dt.date
    warehouse_id: int | None
    item_id: int
    uom_id: int
    qty_ordered: float
    unit_cost: float | None
    status: str
    created_at: dt.datetime
    updated_at: dt.datetime


class PurchaseOrderCreate(BaseModel):
    po_number: str = Field(min_length=1, max_length=50)
    vendor_name: str | None = Field(default=None, max_length=255)
    po_date: dt.date
    warehouse_id: int | None = None
    item_id: int
    uom_id: int
    qty_ordered: float
    unit_cost: float | None = None
    status: str = Field(default="open", min_length=1, max_length=30)


class GrnPublic(ORMModel):
    id: int
    grn_number: str
    grn_date: dt.date
    purchase_order_id: int | None
    vendor_name: str | None
    warehouse_id: int
    item_id: int
    uom_id: int
    qty_received: float
    unit_cost: float | None
    notes: str | None
    created_at: dt.datetime
    updated_at: dt.datetime


class GrnCreate(BaseModel):
    grn_number: str = Field(min_length=1, max_length=50)
    grn_date: dt.date
    purchase_order_id: int | None = None
    vendor_name: str | None = Field(default=None, max_length=255)
    warehouse_id: int
    item_id: int
    uom_id: int
    qty_received: float
    unit_cost: float | None = None
    notes: str | None = Field(default=None, max_length=500)


class MaterialIssuePublic(ORMModel):
    id: int
    issue_number: str
    issue_date: dt.date
    project_id: int
    cost_center_id: int
    warehouse_id: int
    item_id: int
    uom_id: int
    qty_issued: float
    unit_cost: float | None
    remarks: str | None
    created_at: dt.datetime
    updated_at: dt.datetime


class MaterialIssueCreate(BaseModel):
    issue_number: str = Field(min_length=1, max_length=50)
    issue_date: dt.date
    project_id: int
    cost_center_id: int
    warehouse_id: int
    item_id: int
    uom_id: int
    qty_issued: float
    unit_cost: float | None = None
    remarks: str | None = Field(default=None, max_length=500)


class StockLedgerPublic(ORMModel):
    id: int
    txn_date: dt.date
    item_id: int
    warehouse_id: int
    uom_id: int
    source_type: str
    source_id: int
    qty_in: float
    qty_out: float
    unit_cost: float | None
    project_id: int | None
    cost_center_id: int | None
    created_at: dt.datetime
    updated_at: dt.datetime


# Reports


class ProjectConsumptionRow(BaseModel):
    project_id: int
    item_id: int
    qty_issued: float


class ProjectConsumptionQuery(BaseModel):
    date_from: dt.date
    date_to: dt.date
    project_id: int | None = None
    item_id: int | None = None
