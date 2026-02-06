from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import require_permissions
from app.core.database import get_db
from app.modules.projects_dpr.schemas import (
    DprCreate,
    DprHeaderPublic,
    DprListQuery,
    DprMetricsPublic,
)
from app.modules.projects_dpr.service import (
    compute_dpr_metrics,
    compute_project_metrics,
    create_dpr,
    list_dprs,
)

router = APIRouter(prefix="/dprs", tags=["Projects • DPR"])


@router.post(
    "",
    response_model=DprHeaderPublic,
    dependencies=[Depends(require_permissions({"projects.dprs.write"}))],
)
def projects_create_dpr(
    payload: DprCreate,
    db: Session = Depends(get_db),
) -> DprHeaderPublic:
    header = create_dpr(
        db,
        project_id=payload.project_id,
        dpr_date=payload.dpr_date,
        shift=payload.shift,
        remarks=payload.remarks,
        drilling_lines=payload.drilling_lines,
        activity_lines=payload.activity_lines,
        consumption_lines=payload.consumption_lines,
    )
    return DprHeaderPublic.model_validate(header)


@router.get(
    "",
    response_model=list[DprHeaderPublic],
    dependencies=[Depends(require_permissions({"projects.dprs.read"}))],
)
def projects_list_dprs(
    project_id: int | None = None,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    include_lines: bool = False,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
) -> list[DprHeaderPublic]:
    q = DprListQuery(
        project_id=project_id,
        date_from=date_from,
        date_to=date_to,
        include_lines=include_lines,
        limit=limit,
        offset=offset,
    )
    rows = list_dprs(
        db,
        project_id=q.project_id,
        date_from=q.date_from,
        date_to=q.date_to,
        include_lines=q.include_lines,
        limit=q.limit,
        offset=q.offset,
    )
    return [DprHeaderPublic.model_validate(r) for r in rows]


@router.get(
    "/{dpr_id}/metrics",
    response_model=DprMetricsPublic,
    dependencies=[
        Depends(require_permissions({"projects.dprs.metrics.read"}))
    ],
)
def projects_dpr_metrics(
    dpr_id: int,
    db: Session = Depends(get_db),
) -> DprMetricsPublic:
    meters, recovered, recovery_percent = compute_dpr_metrics(
        db,
        dpr_id=dpr_id,
    )
    return DprMetricsPublic(
        dpr_id=dpr_id,
        meters_drilled_total=meters,
        recovered_meters_total=recovered,
        recovery_percent=recovery_percent,
    )


@router.get(
    "/metrics",
    response_model=DprMetricsPublic,
    dependencies=[
        Depends(require_permissions({"projects.dprs.metrics.read"}))
    ],
)
def projects_project_metrics(
    project_id: int,
    date_from: dt.date,
    date_to: dt.date,
    db: Session = Depends(get_db),
) -> DprMetricsPublic:
    meters, recovered, recovery_percent = compute_project_metrics(
        db,
        project_id=project_id,
        date_from=date_from,
        date_to=date_to,
    )
    return DprMetricsPublic(
        dpr_id=0,
        meters_drilled_total=meters,
        recovered_meters_total=recovered,
        recovery_percent=recovery_percent,
    )
