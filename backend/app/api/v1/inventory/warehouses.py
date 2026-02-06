from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import require_permissions
from app.core.database import get_db
from app.db.models.inventory import Warehouse
from app.modules.inventory.schemas import (
    WarehouseCreate,
    WarehousePublic,
    WarehouseUpdate,
)
from app.modules.inventory.service import (
    create_warehouse,
    delete_warehouse,
    list_warehouses,
    update_warehouse,
)

router = APIRouter(prefix="/warehouses")

_WAREHOUSE_NOT_FOUND = "Warehouse not found"


@router.get(
    "",
    response_model=list[WarehousePublic],
    dependencies=[Depends(require_permissions({"inventory.warehouses.read"}))],
)
def api_list_warehouses(
    db: Session = Depends(get_db),
) -> list[WarehousePublic]:
    return [WarehousePublic.model_validate(r) for r in list_warehouses(db)]


@router.post(
    "",
    response_model=WarehousePublic,
    dependencies=[
        Depends(require_permissions({"inventory.warehouses.write"})),
    ],
)
def api_create_warehouse(
    payload: WarehouseCreate,
    db: Session = Depends(get_db),
) -> WarehousePublic:
    row = create_warehouse(
        db,
        code=payload.code,
        name=payload.name,
        location=payload.location,
        is_active=payload.is_active,
    )
    return WarehousePublic.model_validate(row)


@router.put(
    "/{warehouse_id}",
    response_model=WarehousePublic,
    dependencies=[
        Depends(require_permissions({"inventory.warehouses.write"})),
    ],
)
def api_update_warehouse(
    warehouse_id: int,
    payload: WarehouseUpdate,
    db: Session = Depends(get_db),
) -> WarehousePublic:
    row = db.get(Warehouse, warehouse_id)
    if not row:
        raise HTTPException(status_code=404, detail=_WAREHOUSE_NOT_FOUND)

    updated = update_warehouse(
        db,
        row=row,
        code=payload.code,
        name=payload.name,
        location=payload.location,
        is_active=payload.is_active,
    )
    return WarehousePublic.model_validate(updated)


@router.delete(
    "/{warehouse_id}",
    dependencies=[
        Depends(require_permissions({"inventory.warehouses.write"})),
    ],
)
def api_delete_warehouse(
    warehouse_id: int,
    db: Session = Depends(get_db),
) -> dict:
    row = db.get(Warehouse, warehouse_id)
    if not row:
        raise HTTPException(status_code=404, detail=_WAREHOUSE_NOT_FOUND)

    delete_warehouse(db, row=row)
    return {"ok": True}
