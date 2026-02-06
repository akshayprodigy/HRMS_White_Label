from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import require_permissions
from app.core.database import get_db
from app.modules.projects_profitability.schemas import (
    ProjectProfitabilityPublic,
)
from app.modules.projects_profitability.service import (
    get_project_profitability,
)

router = APIRouter(tags=["Projects • Profitability"])


@router.get(
    "/{project_id}/profitability",
    response_model=ProjectProfitabilityPublic,
    dependencies=[
        Depends(require_permissions({"projects.profitability.read"}))
    ],
)
def projects_get_profitability(
    project_id: int,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    db: Session = Depends(get_db),
) -> ProjectProfitabilityPublic:
    return get_project_profitability(
        db,
        project_id=project_id,
        date_from=date_from,
        date_to=date_to,
    )
