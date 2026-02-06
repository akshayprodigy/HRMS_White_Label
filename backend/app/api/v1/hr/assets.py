from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import require_permissions
from app.core.database import get_db
from app.db.models.hr import Employee, EmployeeAsset
from app.modules.hr.schemas import (
    EmployeeAssetCreate,
    EmployeeAssetPublic,
    EmployeeAssetUpdate,
)
from app.modules.hr.service import (
    assign_employee_asset,
    delete_employee_asset,
    list_employee_assets,
    update_employee_asset,
)

router = APIRouter(prefix="/employees/{employee_id}/assets")

_ERR_EMPLOYEE_NOT_FOUND = "Employee not found"


@router.get(
    "",
    response_model=list[EmployeeAssetPublic],
    dependencies=[Depends(require_permissions({"hr.employee_assets.read"}))],
)
def hr_list_employee_assets(
    employee_id: int,
    db: Session = Depends(get_db),
) -> list[EmployeeAssetPublic]:
    employee = db.get(Employee, employee_id)
    if not employee:
        raise HTTPException(status_code=404, detail=_ERR_EMPLOYEE_NOT_FOUND)

    assets = list_employee_assets(db, employee_id=employee_id)
    return [EmployeeAssetPublic.model_validate(a) for a in assets]


@router.post(
    "",
    response_model=EmployeeAssetPublic,
    dependencies=[Depends(require_permissions({"hr.employee_assets.write"}))],
)
def hr_assign_employee_asset(
    employee_id: int,
    payload: EmployeeAssetCreate,
    db: Session = Depends(get_db),
) -> EmployeeAssetPublic:
    employee = db.get(Employee, employee_id)
    if not employee:
        raise HTTPException(status_code=404, detail=_ERR_EMPLOYEE_NOT_FOUND)

    asset = assign_employee_asset(db, employee=employee, payload=payload)
    return EmployeeAssetPublic.model_validate(asset)


@router.put(
    "/{asset_id}",
    response_model=EmployeeAssetPublic,
    dependencies=[Depends(require_permissions({"hr.employee_assets.write"}))],
)
def hr_update_employee_asset(
    employee_id: int,
    asset_id: int,
    payload: EmployeeAssetUpdate,
    db: Session = Depends(get_db),
) -> EmployeeAssetPublic:
    employee = db.get(Employee, employee_id)
    if not employee:
        raise HTTPException(status_code=404, detail=_ERR_EMPLOYEE_NOT_FOUND)

    asset = db.get(EmployeeAsset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    updated = update_employee_asset(
        db,
        employee_id=employee_id,
        asset=asset,
        payload=payload,
    )
    return EmployeeAssetPublic.model_validate(updated)


@router.delete(
    "/{asset_id}",
    dependencies=[Depends(require_permissions({"hr.employee_assets.write"}))],
)
def hr_delete_employee_asset(
    employee_id: int,
    asset_id: int,
    db: Session = Depends(get_db),
) -> dict:
    employee = db.get(Employee, employee_id)
    if not employee:
        raise HTTPException(status_code=404, detail=_ERR_EMPLOYEE_NOT_FOUND)

    asset = db.get(EmployeeAsset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    delete_employee_asset(db, employee_id=employee_id, asset=asset)
    return {"status": "ok"}
