from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.auth import require_permissions
from app.core.database import get_db
from app.db.models.hr import HolidayCalendar
from app.modules.hr.leave_service import (
    create_holiday,
    delete_holiday,
    list_holidays,
)
from app.modules.hr.schemas import HolidayCalendarCreate, HolidayCalendarPublic

router = APIRouter(prefix="/holidays")

_ERR_NOT_FOUND = "Holiday not found"


@router.get(
    "",
    response_model=list[HolidayCalendarPublic],
    dependencies=[Depends(require_permissions({"hr.holiday_calendars.read"}))],
)
def hr_list_holidays(
    date_from: dt.date | None = Query(default=None),
    date_to: dt.date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[HolidayCalendarPublic]:
    rows = list_holidays(db, date_from=date_from, date_to=date_to)
    return [HolidayCalendarPublic.model_validate(r) for r in rows]


@router.post(
    "",
    response_model=HolidayCalendarPublic,
    dependencies=[
        Depends(require_permissions({"hr.holiday_calendars.write"}))
    ],
)
def hr_create_holiday(
    payload: HolidayCalendarCreate,
    db: Session = Depends(get_db),
) -> HolidayCalendarPublic:
    row = create_holiday(
        db,
        holiday_date=payload.holiday_date,
        name=payload.name,
        is_optional=payload.is_optional,
    )
    return HolidayCalendarPublic.model_validate(row)


@router.delete(
    "/{holiday_id}",
    dependencies=[
        Depends(require_permissions({"hr.holiday_calendars.write"}))
    ],
)
def hr_delete_holiday(
    holiday_id: int,
    db: Session = Depends(get_db),
) -> dict:
    holiday = db.get(HolidayCalendar, holiday_id)
    if not holiday:
        raise HTTPException(status_code=404, detail=_ERR_NOT_FOUND)

    delete_holiday(db, holiday=holiday)
    return {"status": "ok"}
