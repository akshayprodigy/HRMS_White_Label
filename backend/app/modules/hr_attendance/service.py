from __future__ import annotations

import datetime as dt

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import log_audit, model_to_dict
from app.db.models.core import Project
from app.db.models.hr import Employee
from app.db.models.hr_attendance import AttendanceEntry


def create_attendance_entry(
    db: Session,
    *,
    employee_id: int,
    project_id: int,
    work_date: dt.date,
    hours: float,
    hourly_rate: float,
    notes: str | None,
) -> AttendanceEntry:
    if not db.get(Employee, employee_id):
        raise HTTPException(status_code=400, detail="Invalid employee_id")
    if not db.get(Project, project_id):
        raise HTTPException(status_code=400, detail="Invalid project_id")

    row = AttendanceEntry(
        employee_id=employee_id,
        project_id=project_id,
        work_date=work_date,
        hours=hours,
        hourly_rate=hourly_rate,
        notes=notes,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    log_audit(
        db,
        entity_type="attendance_entries",
        entity_id=str(row.id),
        action="create",
        before_json=None,
        after_json=model_to_dict(row),
    )

    return row


def list_attendance_entries(
    db: Session,
    *,
    project_id: int | None,
    employee_id: int | None,
    date_from: dt.date | None,
    date_to: dt.date | None,
    limit: int,
    offset: int,
) -> list[AttendanceEntry]:
    stmt = select(AttendanceEntry)

    if project_id is not None:
        stmt = stmt.where(AttendanceEntry.project_id == project_id)
    if employee_id is not None:
        stmt = stmt.where(AttendanceEntry.employee_id == employee_id)
    if date_from is not None:
        stmt = stmt.where(AttendanceEntry.work_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(AttendanceEntry.work_date <= date_to)

    stmt = stmt.order_by(
        AttendanceEntry.work_date.desc(),
        AttendanceEntry.id.desc(),
    )
    stmt = stmt.limit(limit).offset(offset)

    return list(db.execute(stmt).scalars().all())
