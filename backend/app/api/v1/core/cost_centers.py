from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import require_permissions
from app.core.database import get_db
from app.db.models.core import CostCenter
from app.modules.core.schemas import (
    CostCenterCreate,
    CostCenterPublic,
    CostCenterUpdate,
)
from app.modules.core.service import (
    create_cost_center,
    delete_cost_center,
    list_cost_centers,
    update_cost_center,
)

router = APIRouter(prefix="/cost-centers")

_COST_CENTER_NOT_FOUND = "Cost center not found"


@router.get(
    "",
    response_model=list[CostCenterPublic],
    dependencies=[Depends(require_permissions({"core.cost_centers.read"}))],
)
def core_list_cost_centers(
    db: Session = Depends(get_db),
) -> list[CostCenterPublic]:
    return [CostCenterPublic.model_validate(c) for c in list_cost_centers(db)]


@router.post(
    "",
    response_model=CostCenterPublic,
    dependencies=[Depends(require_permissions({"core.cost_centers.write"}))],
)
def core_create_cost_center(
    payload: CostCenterCreate,
    db: Session = Depends(get_db),
) -> CostCenterPublic:
    cc = create_cost_center(
        db,
        organization_id=payload.organization_id,
        code=payload.code,
        name=payload.name,
        is_active=payload.is_active,
    )
    return CostCenterPublic.model_validate(cc)


@router.get(
    "/{cost_center_id}",
    response_model=CostCenterPublic,
    dependencies=[Depends(require_permissions({"core.cost_centers.read"}))],
)
def core_get_cost_center(
    cost_center_id: int,
    db: Session = Depends(get_db),
) -> CostCenterPublic:
    cc = db.get(CostCenter, cost_center_id)
    if not cc:
        raise HTTPException(status_code=404, detail=_COST_CENTER_NOT_FOUND)
    return CostCenterPublic.model_validate(cc)


@router.put(
    "/{cost_center_id}",
    response_model=CostCenterPublic,
    dependencies=[Depends(require_permissions({"core.cost_centers.write"}))],
)
def core_update_cost_center(
    cost_center_id: int,
    payload: CostCenterUpdate,
    db: Session = Depends(get_db),
) -> CostCenterPublic:
    cc = db.get(CostCenter, cost_center_id)
    if not cc:
        raise HTTPException(status_code=404, detail=_COST_CENTER_NOT_FOUND)

    updated = update_cost_center(
        db,
        cost_center=cc,
        organization_id=payload.organization_id,
        code=payload.code,
        name=payload.name,
        is_active=payload.is_active,
    )
    return CostCenterPublic.model_validate(updated)


@router.delete(
    "/{cost_center_id}",
    dependencies=[Depends(require_permissions({"core.cost_centers.write"}))],
)
def core_delete_cost_center(
    cost_center_id: int,
    db: Session = Depends(get_db),
) -> dict:
    cc = db.get(CostCenter, cost_center_id)
    if not cc:
        raise HTTPException(status_code=404, detail=_COST_CENTER_NOT_FOUND)
    delete_cost_center(db, cost_center=cc)
    return {"status": "ok"}
