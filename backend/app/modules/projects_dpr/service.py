from __future__ import annotations

import datetime as dt

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.audit import log_audit, model_to_dict
from app.db.models.core import Project
from app.db.models.projects_dpr import (
    DprActivityLine,
    DprConsumptionLine,
    DprDrillingLine,
    DprHeader,
)


def _validate_unique_line_nos(lines: list[object], *, field: str) -> None:
    seen: set[int] = set()
    for line in lines:
        line_no = int(getattr(line, field))
        if line_no in seen:
            raise HTTPException(status_code=400, detail="Duplicate line_no")
        seen.add(line_no)


def create_dpr(
    db: Session,
    *,
    project_id: int,
    dpr_date: dt.date,
    shift: str | None,
    remarks: str | None,
    drilling_lines,
    activity_lines,
    consumption_lines,
) -> DprHeader:
    if not db.get(Project, project_id):
        raise HTTPException(status_code=400, detail="Invalid project_id")

    _validate_unique_line_nos(drilling_lines, field="line_no")
    _validate_unique_line_nos(activity_lines, field="line_no")
    _validate_unique_line_nos(consumption_lines, field="line_no")

    header = DprHeader(
        project_id=project_id,
        dpr_date=dpr_date,
        shift=shift,
        remarks=remarks,
    )
    db.add(header)
    db.flush()

    for dl in drilling_lines:
        db.add(
            DprDrillingLine(
                header_id=header.id,
                line_no=dl.line_no,
                location=dl.location,
                meters_drilled=dl.meters_drilled,
                recovered_meters=dl.recovered_meters,
            )
        )

    for al in activity_lines:
        db.add(
            DprActivityLine(
                header_id=header.id,
                line_no=al.line_no,
                activity=al.activity,
                hours=al.hours,
                remarks=al.remarks,
            )
        )

    for cl in consumption_lines:
        db.add(
            DprConsumptionLine(
                header_id=header.id,
                line_no=cl.line_no,
                item_id=cl.item_id,
                uom_id=cl.uom_id,
                qty=cl.qty,
                remarks=cl.remarks,
            )
        )

    db.commit()
    db.refresh(header)

    log_audit(
        db,
        entity_type="dpr_headers",
        entity_id=str(header.id),
        action="create",
        before_json=None,
        after_json=model_to_dict(header),
    )

    return header


def list_dprs(
    db: Session,
    *,
    project_id: int | None,
    date_from: dt.date | None,
    date_to: dt.date | None,
    include_lines: bool,
    limit: int,
    offset: int,
) -> list[DprHeader]:
    stmt = select(DprHeader)

    if include_lines:
        stmt = stmt.options(
            selectinload(DprHeader.drilling_lines),
            selectinload(DprHeader.activity_lines),
            selectinload(DprHeader.consumption_lines),
        )

    if project_id is not None:
        stmt = stmt.where(DprHeader.project_id == project_id)
    if date_from is not None:
        stmt = stmt.where(DprHeader.dpr_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(DprHeader.dpr_date <= date_to)

    stmt = stmt.order_by(DprHeader.dpr_date.desc(), DprHeader.id.desc())
    stmt = stmt.limit(limit).offset(offset)

    return list(db.execute(stmt).scalars().all())


def compute_dpr_metrics(
    db: Session,
    *,
    dpr_id: int,
) -> tuple[float, float, float]:
    header = db.get(DprHeader, dpr_id)
    if header is None:
        raise HTTPException(status_code=404, detail="DPR not found")

    meters, recovered = db.execute(
        select(
            func.coalesce(func.sum(DprDrillingLine.meters_drilled), 0),
            func.coalesce(func.sum(DprDrillingLine.recovered_meters), 0),
        ).where(DprDrillingLine.header_id == dpr_id)
    ).one()

    meters_total = float(meters or 0)
    recovered_total = float(recovered or 0)
    recovery_percent = (
        0.0 if meters_total <= 0 else (recovered_total / meters_total) * 100.0
    )

    return meters_total, recovered_total, float(recovery_percent)


def compute_project_metrics(
    db: Session,
    *,
    project_id: int,
    date_from: dt.date,
    date_to: dt.date,
) -> tuple[float, float, float]:
    if not db.get(Project, project_id):
        raise HTTPException(status_code=400, detail="Invalid project_id")

    meters, recovered = db.execute(
        select(
            func.coalesce(func.sum(DprDrillingLine.meters_drilled), 0),
            func.coalesce(func.sum(DprDrillingLine.recovered_meters), 0),
        )
        .select_from(DprDrillingLine)
        .join(DprHeader, DprHeader.id == DprDrillingLine.header_id)
        .where(
            DprHeader.project_id == project_id,
            DprHeader.dpr_date >= date_from,
            DprHeader.dpr_date <= date_to,
        )
    ).one()

    meters_total = float(meters or 0)
    recovered_total = float(recovered or 0)
    recovery_percent = (
        0.0 if meters_total <= 0 else (recovered_total / meters_total) * 100.0
    )

    return meters_total, recovered_total, float(recovery_percent)
