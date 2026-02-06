from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import require_permissions
from app.core.database import get_db
from app.db.models.inventory import Uom
from app.modules.inventory.schemas import UomCreate, UomPublic, UomUpdate
from app.modules.inventory.service import (
    create_uom,
    delete_uom,
    list_uoms,
    update_uom,
)

router = APIRouter(prefix="/uoms")

_UOM_NOT_FOUND = "UOM not found"


@router.get(
    "",
    response_model=list[UomPublic],
    dependencies=[Depends(require_permissions({"inventory.uoms.read"}))],
)
def api_list_uoms(db: Session = Depends(get_db)) -> list[UomPublic]:
    return [UomPublic.model_validate(r) for r in list_uoms(db)]


@router.post(
    "",
    response_model=UomPublic,
    dependencies=[Depends(require_permissions({"inventory.uoms.write"}))],
)
def api_create_uom(
    payload: UomCreate,
    db: Session = Depends(get_db),
) -> UomPublic:
    row = create_uom(
        db,
        code=payload.code,
        name=payload.name,
        symbol=payload.symbol,
        is_active=payload.is_active,
    )
    return UomPublic.model_validate(row)


@router.put(
    "/{uom_id}",
    response_model=UomPublic,
    dependencies=[Depends(require_permissions({"inventory.uoms.write"}))],
)
def api_update_uom(
    uom_id: int,
    payload: UomUpdate,
    db: Session = Depends(get_db),
) -> UomPublic:
    row = db.get(Uom, uom_id)
    if not row:
        raise HTTPException(status_code=404, detail=_UOM_NOT_FOUND)

    updated = update_uom(
        db,
        row=row,
        code=payload.code,
        name=payload.name,
        symbol=payload.symbol,
        is_active=payload.is_active,
    )
    return UomPublic.model_validate(updated)


@router.delete(
    "/{uom_id}",
    dependencies=[Depends(require_permissions({"inventory.uoms.write"}))],
)
def api_delete_uom(uom_id: int, db: Session = Depends(get_db)) -> dict:
    row = db.get(Uom, uom_id)
    if not row:
        raise HTTPException(status_code=404, detail=_UOM_NOT_FOUND)

    delete_uom(db, row=row)
    return {"ok": True}
