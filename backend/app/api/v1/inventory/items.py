from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import require_permissions
from app.core.database import get_db
from app.db.models.inventory import Item
from app.modules.inventory.schemas import ItemCreate, ItemPublic, ItemUpdate
from app.modules.inventory.service import (
    create_item,
    delete_item,
    list_items,
    update_item,
)

router = APIRouter(prefix="/items")

_ITEM_NOT_FOUND = "Item not found"


@router.get(
    "",
    response_model=list[ItemPublic],
    dependencies=[Depends(require_permissions({"inventory.items.read"}))],
)
def api_list_items(db: Session = Depends(get_db)) -> list[ItemPublic]:
    return [ItemPublic.model_validate(r) for r in list_items(db)]


@router.post(
    "",
    response_model=ItemPublic,
    dependencies=[Depends(require_permissions({"inventory.items.write"}))],
)
def api_create_item(
    payload: ItemCreate,
    db: Session = Depends(get_db),
) -> ItemPublic:
    row = create_item(
        db,
        sku=payload.sku,
        name=payload.name,
        description=payload.description,
        base_uom_id=payload.base_uom_id,
        is_active=payload.is_active,
    )
    return ItemPublic.model_validate(row)


@router.put(
    "/{item_id}",
    response_model=ItemPublic,
    dependencies=[Depends(require_permissions({"inventory.items.write"}))],
)
def api_update_item(
    item_id: int,
    payload: ItemUpdate,
    db: Session = Depends(get_db),
) -> ItemPublic:
    row = db.get(Item, item_id)
    if not row:
        raise HTTPException(status_code=404, detail=_ITEM_NOT_FOUND)

    updated = update_item(
        db,
        row=row,
        sku=payload.sku,
        name=payload.name,
        description=payload.description,
        base_uom_id=payload.base_uom_id,
        is_active=payload.is_active,
    )
    return ItemPublic.model_validate(updated)


@router.delete(
    "/{item_id}",
    dependencies=[Depends(require_permissions({"inventory.items.write"}))],
)
def api_delete_item(item_id: int, db: Session = Depends(get_db)) -> dict:
    row = db.get(Item, item_id)
    if not row:
        raise HTTPException(status_code=404, detail=_ITEM_NOT_FOUND)

    delete_item(db, row=row)
    return {"ok": True}
