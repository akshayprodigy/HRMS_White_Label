from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import require_permissions
from app.core.database import get_db
from app.modules.inventory.schemas import GrnCreate, GrnPublic
from app.modules.inventory.service import create_grn, list_grns

router = APIRouter(prefix="/grns")


@router.get(
    "",
    response_model=list[GrnPublic],
    dependencies=[Depends(require_permissions({"inventory.grns.read"}))],
)
def api_list_grns(db: Session = Depends(get_db)) -> list[GrnPublic]:
    return [GrnPublic.model_validate(r) for r in list_grns(db)]


@router.post(
    "",
    response_model=GrnPublic,
    dependencies=[Depends(require_permissions({"inventory.grns.write"}))],
)
def api_create_grn(
    payload: GrnCreate,
    db: Session = Depends(get_db),
) -> GrnPublic:
    row = create_grn(
        db,
        grn_number=payload.grn_number,
        grn_date=payload.grn_date,
        purchase_order_id=payload.purchase_order_id,
        vendor_name=payload.vendor_name,
        warehouse_id=payload.warehouse_id,
        item_id=payload.item_id,
        uom_id=payload.uom_id,
        qty_received=payload.qty_received,
        unit_cost=payload.unit_cost,
        notes=payload.notes,
    )
    return GrnPublic.model_validate(row)
