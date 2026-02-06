from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import require_permissions
from app.core.database import get_db
from app.db.models.hr import Employee
from app.modules.hr.schemas import (
    EmployeeCreate,
    EmployeePublic,
    EmployeeUpdate,
)
from app.modules.hr.service import (
    create_employee,
    delete_employee,
    list_employees,
    update_employee,
)

router = APIRouter(prefix="/employees")

_ERR_EMPLOYEE_NOT_FOUND = "Employee not found"


@router.get(
    "",
    response_model=list[EmployeePublic],
    dependencies=[Depends(require_permissions({"hr.employees.read"}))],
)
def hr_list_employees(db: Session = Depends(get_db)) -> list[EmployeePublic]:
    return [EmployeePublic.model_validate(e) for e in list_employees(db)]


@router.post(
    "",
    response_model=EmployeePublic,
    dependencies=[Depends(require_permissions({"hr.employees.write"}))],
)
def hr_create_employee(
    payload: EmployeeCreate,
    db: Session = Depends(get_db),
) -> EmployeePublic:
    employee = create_employee(db, payload=payload)
    return EmployeePublic.model_validate(employee)


@router.get(
    "/{employee_id}",
    response_model=EmployeePublic,
    dependencies=[Depends(require_permissions({"hr.employees.read"}))],
)
def hr_get_employee(
    employee_id: int,
    db: Session = Depends(get_db),
) -> EmployeePublic:
    employee = db.get(Employee, employee_id)
    if not employee:
        raise HTTPException(status_code=404, detail=_ERR_EMPLOYEE_NOT_FOUND)
    return EmployeePublic.model_validate(employee)


@router.put(
    "/{employee_id}",
    response_model=EmployeePublic,
    dependencies=[Depends(require_permissions({"hr.employees.write"}))],
)
def hr_update_employee(
    employee_id: int,
    payload: EmployeeUpdate,
    db: Session = Depends(get_db),
) -> EmployeePublic:
    employee = db.get(Employee, employee_id)
    if not employee:
        raise HTTPException(status_code=404, detail=_ERR_EMPLOYEE_NOT_FOUND)

    updated = update_employee(db, employee=employee, payload=payload)
    return EmployeePublic.model_validate(updated)


@router.delete(
    "/{employee_id}",
    dependencies=[Depends(require_permissions({"hr.employees.write"}))],
)
def hr_delete_employee(
    employee_id: int,
    db: Session = Depends(get_db),
) -> dict:
    employee = db.get(Employee, employee_id)
    if not employee:
        raise HTTPException(status_code=404, detail=_ERR_EMPLOYEE_NOT_FOUND)
    delete_employee(db, employee=employee)
    return {"status": "ok"}
