from __future__ import annotations

import datetime as dt

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import log_audit, model_to_dict
from app.db.models.core import CostCenter, Project
from app.db.models.inventory import (
    Grn,
    Item,
    MaterialIssue,
    StockLedger,
    Uom,
    Warehouse,
)

# Masters


def list_uoms(db: Session) -> list[Uom]:
    return list(
        db.execute(select(Uom).order_by(Uom.id.desc())).scalars().all()
    )


def create_uom(
    db: Session,
    *,
    code: str,
    name: str,
    symbol: str | None,
    is_active: bool,
) -> Uom:
    existing = db.execute(
        select(Uom).where(Uom.code == code)
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="UOM code exists")

    row = Uom(code=code, name=name, symbol=symbol, is_active=is_active)
    db.add(row)
    db.commit()
    db.refresh(row)

    log_audit(
        db,
        entity_type="uoms",
        entity_id=str(row.id),
        action="create",
        before_json=None,
        after_json=model_to_dict(row),
    )
    return row


def update_uom(
    db: Session,
    *,
    row: Uom,
    code: str | None,
    name: str | None,
    symbol: str | None,
    is_active: bool | None,
) -> Uom:
    before = model_to_dict(row)

    if code and code != row.code:
        existing = db.execute(
            select(Uom).where(Uom.code == code)
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=400, detail="UOM code exists")
        row.code = code

    if name is not None:
        row.name = name
    if symbol is not None:
        row.symbol = symbol
    if is_active is not None:
        row.is_active = is_active

    db.add(row)
    db.commit()
    db.refresh(row)

    log_audit(
        db,
        entity_type="uoms",
        entity_id=str(row.id),
        action="update",
        before_json=before,
        after_json=model_to_dict(row),
    )
    return row


def delete_uom(db: Session, *, row: Uom) -> None:
    before = model_to_dict(row)
    db.delete(row)
    db.commit()

    log_audit(
        db,
        entity_type="uoms",
        entity_id=str(row.id),
        action="delete",
        before_json=before,
        after_json=None,
    )


def list_warehouses(db: Session) -> list[Warehouse]:
    return list(
        db.execute(select(Warehouse).order_by(Warehouse.id.desc()))
        .scalars()
        .all()
    )


def create_warehouse(
    db: Session,
    *,
    code: str,
    name: str,
    location: str | None,
    is_active: bool,
) -> Warehouse:
    existing = db.execute(
        select(Warehouse).where(Warehouse.code == code)
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Warehouse code exists")

    row = Warehouse(
        code=code,
        name=name,
        location=location,
        is_active=is_active,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    log_audit(
        db,
        entity_type="warehouses",
        entity_id=str(row.id),
        action="create",
        before_json=None,
        after_json=model_to_dict(row),
    )
    return row


def update_warehouse(
    db: Session,
    *,
    row: Warehouse,
    code: str | None,
    name: str | None,
    location: str | None,
    is_active: bool | None,
) -> Warehouse:
    before = model_to_dict(row)

    if code and code != row.code:
        existing = db.execute(
            select(Warehouse).where(Warehouse.code == code)
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(
                status_code=400,
                detail="Warehouse code exists",
            )
        row.code = code

    if name is not None:
        row.name = name
    if location is not None:
        row.location = location
    if is_active is not None:
        row.is_active = is_active

    db.add(row)
    db.commit()
    db.refresh(row)

    log_audit(
        db,
        entity_type="warehouses",
        entity_id=str(row.id),
        action="update",
        before_json=before,
        after_json=model_to_dict(row),
    )
    return row


def delete_warehouse(db: Session, *, row: Warehouse) -> None:
    before = model_to_dict(row)
    db.delete(row)
    db.commit()

    log_audit(
        db,
        entity_type="warehouses",
        entity_id=str(row.id),
        action="delete",
        before_json=before,
        after_json=None,
    )


def list_items(db: Session) -> list[Item]:
    return list(
        db.execute(select(Item).order_by(Item.id.desc())).scalars().all()
    )


def create_item(
    db: Session,
    *,
    sku: str,
    name: str,
    description: str | None,
    base_uom_id: int,
    is_active: bool,
) -> Item:
    if not db.get(Uom, base_uom_id):
        raise HTTPException(status_code=400, detail="Invalid base_uom_id")

    existing = db.execute(
        select(Item).where(Item.sku == sku)
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="SKU exists")

    row = Item(
        sku=sku,
        name=name,
        description=description,
        base_uom_id=base_uom_id,
        is_active=is_active,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    log_audit(
        db,
        entity_type="items",
        entity_id=str(row.id),
        action="create",
        before_json=None,
        after_json=model_to_dict(row),
    )
    return row


def update_item(
    db: Session,
    *,
    row: Item,
    sku: str | None,
    name: str | None,
    description: str | None,
    base_uom_id: int | None,
    is_active: bool | None,
) -> Item:
    before = model_to_dict(row)

    if sku and sku != row.sku:
        existing = db.execute(
            select(Item).where(Item.sku == sku)
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=400, detail="SKU exists")
        row.sku = sku

    if base_uom_id is not None:
        if not db.get(Uom, base_uom_id):
            raise HTTPException(status_code=400, detail="Invalid base_uom_id")
        row.base_uom_id = base_uom_id

    if name is not None:
        row.name = name
    if description is not None:
        row.description = description
    if is_active is not None:
        row.is_active = is_active

    db.add(row)
    db.commit()
    db.refresh(row)

    log_audit(
        db,
        entity_type="items",
        entity_id=str(row.id),
        action="update",
        before_json=before,
        after_json=model_to_dict(row),
    )
    return row


def delete_item(db: Session, *, row: Item) -> None:
    before = model_to_dict(row)
    db.delete(row)
    db.commit()

    log_audit(
        db,
        entity_type="items",
        entity_id=str(row.id),
        action="delete",
        before_json=before,
        after_json=None,
    )


# Transactions + stock ledger


def get_stock_on_hand(
    db: Session,
    *,
    warehouse_id: int,
    item_id: int,
) -> float:
    on_hand_expr = (
        func.coalesce(func.sum(StockLedger.qty_in), 0)
        - func.coalesce(func.sum(StockLedger.qty_out), 0)
    ).label("on_hand")

    stmt = select(on_hand_expr).where(
        StockLedger.warehouse_id == warehouse_id,
        StockLedger.item_id == item_id,
    )
    value = db.execute(stmt).scalar_one()
    return float(value or 0)


def create_grn(
    db: Session,
    *,
    grn_number: str,
    grn_date: dt.date,
    purchase_order_id: int | None,
    vendor_name: str | None,
    warehouse_id: int,
    item_id: int,
    uom_id: int,
    qty_received: float,
    unit_cost: float | None,
    notes: str | None,
) -> Grn:
    existing = db.execute(select(Grn).where(Grn.grn_number == grn_number))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=400, detail="GRN number exists")

    if not db.get(Warehouse, warehouse_id):
        raise HTTPException(status_code=400, detail="Invalid warehouse_id")
    if not db.get(Item, item_id):
        raise HTTPException(status_code=400, detail="Invalid item_id")
    if not db.get(Uom, uom_id):
        raise HTTPException(status_code=400, detail="Invalid uom_id")

    row = Grn(
        grn_number=grn_number,
        grn_date=grn_date,
        purchase_order_id=purchase_order_id,
        vendor_name=vendor_name,
        warehouse_id=warehouse_id,
        item_id=item_id,
        uom_id=uom_id,
        qty_received=qty_received,
        unit_cost=unit_cost,
        notes=notes,
    )
    db.add(row)
    db.flush()

    ledger = StockLedger(
        txn_date=row.grn_date,
        item_id=row.item_id,
        warehouse_id=row.warehouse_id,
        uom_id=row.uom_id,
        source_type="grn",
        source_id=row.id,
        qty_in=row.qty_received,
        qty_out=0,
        unit_cost=row.unit_cost,
        project_id=None,
        cost_center_id=None,
    )
    db.add(ledger)
    db.commit()
    db.refresh(row)

    log_audit(
        db,
        entity_type="grns",
        entity_id=str(row.id),
        action="create",
        before_json=None,
        after_json=model_to_dict(row),
    )
    return row


def create_material_issue(
    db: Session,
    *,
    issue_number: str,
    issue_date: dt.date,
    project_id: int,
    cost_center_id: int,
    warehouse_id: int,
    item_id: int,
    uom_id: int,
    qty_issued: float,
    unit_cost: float | None,
    remarks: str | None,
) -> MaterialIssue:
    existing = db.execute(
        select(MaterialIssue).where(MaterialIssue.issue_number == issue_number)
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=400, detail="Issue number exists")

    if not db.get(Project, project_id):
        raise HTTPException(status_code=400, detail="Invalid project_id")
    if not db.get(CostCenter, cost_center_id):
        raise HTTPException(status_code=400, detail="Invalid cost_center_id")

    if not db.get(Warehouse, warehouse_id):
        raise HTTPException(status_code=400, detail="Invalid warehouse_id")
    if not db.get(Item, item_id):
        raise HTTPException(status_code=400, detail="Invalid item_id")
    if not db.get(Uom, uom_id):
        raise HTTPException(status_code=400, detail="Invalid uom_id")

    on_hand = get_stock_on_hand(
        db,
        warehouse_id=warehouse_id,
        item_id=item_id,
    )
    if qty_issued > on_hand:
        raise HTTPException(status_code=400, detail="Insufficient stock")

    row = MaterialIssue(
        issue_number=issue_number,
        issue_date=issue_date,
        project_id=project_id,
        cost_center_id=cost_center_id,
        warehouse_id=warehouse_id,
        item_id=item_id,
        uom_id=uom_id,
        qty_issued=qty_issued,
        unit_cost=unit_cost,
        remarks=remarks,
    )
    db.add(row)
    db.flush()

    ledger = StockLedger(
        txn_date=row.issue_date,
        item_id=row.item_id,
        warehouse_id=row.warehouse_id,
        uom_id=row.uom_id,
        source_type="issue",
        source_id=row.id,
        qty_in=0,
        qty_out=row.qty_issued,
        unit_cost=row.unit_cost,
        project_id=row.project_id,
        cost_center_id=row.cost_center_id,
    )
    db.add(ledger)
    db.commit()
    db.refresh(row)

    log_audit(
        db,
        entity_type="material_issues",
        entity_id=str(row.id),
        action="create",
        before_json=None,
        after_json=model_to_dict(row),
    )
    return row


def list_grns(db: Session) -> list[Grn]:
    return list(
        db.execute(select(Grn).order_by(Grn.id.desc())).scalars().all()
    )


def list_material_issues(db: Session) -> list[MaterialIssue]:
    return list(
        db.execute(select(MaterialIssue).order_by(MaterialIssue.id.desc()))
        .scalars()
        .all()
    )


def get_project_consumption(
    db: Session,
    *,
    date_from,
    date_to,
    project_id: int | None,
    item_id: int | None,
) -> list[tuple[int, int, float]]:
    stmt = (
        select(
            StockLedger.project_id,
            StockLedger.item_id,
            func.coalesce(func.sum(StockLedger.qty_out), 0).label(
                "qty_issued"
            ),
        )
        .where(
            StockLedger.source_type == "issue",
            StockLedger.txn_date >= date_from,
            StockLedger.txn_date <= date_to,
            StockLedger.project_id.is_not(None),
        )
        .group_by(StockLedger.project_id, StockLedger.item_id)
        .order_by(StockLedger.project_id.asc())
    )

    if project_id is not None:
        stmt = stmt.where(StockLedger.project_id == project_id)
    if item_id is not None:
        stmt = stmt.where(StockLedger.item_id == item_id)

    rows = list(db.execute(stmt).all())
    out: list[tuple[int, int, float]] = []
    for prj_id, it_id, qty in rows:
        out.append((int(prj_id), int(it_id), float(qty or 0)))
    return out
