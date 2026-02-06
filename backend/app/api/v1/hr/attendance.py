from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import require_permissions
from app.core.database import get_db
from app.modules.hr_attendance.schemas import (
    AttendanceEntryCreate,
    AttendanceEntryListQuery,
    AttendanceEntryPublic,
)
from app.modules.hr_attendance.service import (
    create_attendance_entry,
    list_attendance_entries,
)

router = APIRouter(prefix="/attendance")


@router.post(
    "",
    response_model=AttendanceEntryPublic,
    dependencies=[Depends(require_permissions({"hr.attendance.write"}))],
)
def hr_create_attendance_entry(
    payload: AttendanceEntryCreate,
    db: Session = Depends(get_db),
) -> AttendanceEntryPublic:
    row = create_attendance_entry(
        db,
        employee_id=payload.employee_id,
        project_id=payload.project_id,
        work_date=payload.work_date,
        hours=payload.hours,
        hourly_rate=payload.hourly_rate,
        notes=payload.notes,
    )
    return AttendanceEntryPublic.model_validate(row)


@router.get(
    "",
    response_model=list[AttendanceEntryPublic],
    dependencies=[Depends(require_permissions({"hr.attendance.read"}))],
)
def hr_list_attendance_entries(
    project_id: int | None = None,
    employee_id: int | None = None,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
) -> list[AttendanceEntryPublic]:
    q = AttendanceEntryListQuery(
        project_id=project_id,
        employee_id=employee_id,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    rows = list_attendance_entries(
        db,
        project_id=q.project_id,
        employee_id=q.employee_id,
        date_from=q.date_from,
        date_to=q.date_to,
        limit=q.limit,
        offset=q.offset,
    )
    return [AttendanceEntryPublic.model_validate(r) for r in rows]
