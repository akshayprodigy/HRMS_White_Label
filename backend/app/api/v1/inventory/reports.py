from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import require_permissions
from app.core.database import get_db
from app.modules.inventory.schemas import (
    ProjectConsumptionQuery,
    ProjectConsumptionRow,
)
from app.modules.inventory.service import get_project_consumption

router = APIRouter(prefix="/reports")


@router.get(
    "/project-consumption",
    response_model=list[ProjectConsumptionRow],
    dependencies=[
        Depends(
            require_permissions(
                {"inventory.reports.project_consumption.read"}
            )
        ),
    ],
)
def api_project_consumption(
    q: ProjectConsumptionQuery = Depends(),
    db: Session = Depends(get_db),
) -> list[ProjectConsumptionRow]:
    rows = get_project_consumption(
        db,
        date_from=q.date_from,
        date_to=q.date_to,
        project_id=q.project_id,
        item_id=q.item_id,
    )
    return [
        ProjectConsumptionRow(
            project_id=project_id,
            item_id=item_id,
            qty_issued=qty_issued,
        )
        for project_id, item_id, qty_issued in rows
    ]
