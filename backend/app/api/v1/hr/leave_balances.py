from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import require_permissions
from app.core.database import get_db
from app.modules.hr.leave_service import list_leave_balances
from app.modules.hr.schemas import LeaveBalancePublic

router = APIRouter(prefix="/leave-balances")


@router.get(
    "/employees/{employee_id}",
    response_model=list[LeaveBalancePublic],
    dependencies=[Depends(require_permissions({"hr.leave_balances.read"}))],
)
def hr_list_leave_balances(
    employee_id: int,
    db: Session = Depends(get_db),
) -> list[LeaveBalancePublic]:
    rows = list_leave_balances(db, employee_id=employee_id)
    return [LeaveBalancePublic.model_validate(r) for r in rows]
