from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import require_permissions
from app.core.database import get_db
from app.modules.inventory.schemas import (
    MaterialIssueCreate,
    MaterialIssuePublic,
)
from app.modules.inventory.service import (
    create_material_issue,
    list_material_issues,
)

router = APIRouter(prefix="/issues")


@router.get(
    "",
    response_model=list[MaterialIssuePublic],
    dependencies=[Depends(require_permissions({"inventory.issues.read"}))],
)
def api_list_issues(
    db: Session = Depends(get_db),
) -> list[MaterialIssuePublic]:
    return [
        MaterialIssuePublic.model_validate(r)
        for r in list_material_issues(db)
    ]


@router.post(
    "",
    response_model=MaterialIssuePublic,
    dependencies=[Depends(require_permissions({"inventory.issues.write"}))],
)
def api_create_issue(
    payload: MaterialIssueCreate,
    db: Session = Depends(get_db),
) -> MaterialIssuePublic:
    row = create_material_issue(
        db,
        issue_number=payload.issue_number,
        issue_date=payload.issue_date,
        project_id=payload.project_id,
        cost_center_id=payload.cost_center_id,
        warehouse_id=payload.warehouse_id,
        item_id=payload.item_id,
        uom_id=payload.uom_id,
        qty_issued=payload.qty_issued,
        unit_cost=payload.unit_cost,
        remarks=payload.remarks,
    )
    return MaterialIssuePublic.model_validate(row)
