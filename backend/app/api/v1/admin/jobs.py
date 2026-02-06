from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import require_permissions
from app.core.database import get_db
from app.modules.hr.leave_service import credit_monthly_leave_balances

router = APIRouter(prefix="/jobs")


class LeaveCreditRequest(BaseModel):
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)
    policy_id: int | None = Field(default=None, ge=1)
    leave_type_id: int | None = Field(default=None, ge=1)


@router.post(
    "/leave-credit",
    dependencies=[Depends(require_permissions({"admin.jobs.leave_credit"}))],
)
def admin_trigger_leave_credit(
    payload: LeaveCreditRequest,
    db: Session = Depends(get_db),
) -> dict:
    # Stub job: manual trigger for monthly credit.
    return credit_monthly_leave_balances(
        db,
        year=payload.year,
        month=payload.month,
        policy_id=payload.policy_id,
        leave_type_id=payload.leave_type_id,
    )


@router.post(
    "/leave-credit/current-month",
    dependencies=[Depends(require_permissions({"admin.jobs.leave_credit"}))],
)
def admin_trigger_leave_credit_current_month(
    db: Session = Depends(get_db),
) -> dict:
    today = dt.date.today()
    return credit_monthly_leave_balances(
        db,
        year=today.year,
        month=today.month,
    )
