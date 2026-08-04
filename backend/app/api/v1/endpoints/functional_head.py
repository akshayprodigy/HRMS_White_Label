from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.api import deps
from app.models.user import User
from app.models.department import Department
from app.models.employee import Employee
from app.schemas.department import DepartmentRead, DepartmentHeadUpdate, TeamMemberRead, HeadOfEmployeeRead
from app.services import functional_head as fh_service

router = APIRouter()

PERM_HEAD_WRITE = "department head write"


@router.get("/departments", response_model=List[DepartmentRead])
async def list_departments_with_heads(
    db: deps.DBDep, current_user: deps.CurrentUser,
) -> Any:
    """All departments with their current head/deputy user ids — powers the
    head-assignment screen. Read-only; any authenticated user."""
    return (await db.execute(select(Department).order_by(Department.name))).scalars().all()


@router.patch("/departments/{dept_id}", response_model=DepartmentRead)
async def assign_department_head(
    *,
    db: deps.DBDep,
    dept_id: int,
    payload: DepartmentHeadUpdate,
    current_user: User = Depends(deps.check_permissions([PERM_HEAD_WRITE])),
) -> Any:
    """Assign or clear a department's functional head and/or deputy head.
    Only provided fields change; pass null to clear. HR / Super Admin only."""
    dept = await db.get(Department, dept_id)
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")

    data = payload.model_dump(exclude_unset=True)
    for field in ("head_user_id", "deputy_head_user_id"):
        if field not in data:
            continue
        value = data[field]
        if value is not None:
            u = await db.get(User, value)
            if u is None:
                raise HTTPException(status_code=400, detail=f"User {value} not found")
            if not u.is_active:
                raise HTTPException(
                    status_code=400,
                    detail=f"User {value} is inactive and cannot be a department head",
                )
        setattr(dept, field, value)

    db.add(dept)
    await db.commit()
    await db.refresh(dept)
    return dept


@router.get("/my-team", response_model=List[TeamMemberRead])
async def my_team(db: deps.DBDep, current_user: deps.CurrentUser) -> Any:
    """Active employees in every department the current user heads."""
    team = await fh_service.resolve_team(db, current_user)
    return [
        TeamMemberRead(
            employee_id=e.employee_id,
            user_id=e.user_id,
            full_name=(e.user.full_name if e.user else None),
            department=e.department,
            designation=e.designation,
            status=e.status,
        )
        for e in team
    ]


@router.get("/of-employee/{employee_id}", response_model=HeadOfEmployeeRead)
async def head_of_employee(
    employee_id: int, db: deps.DBDep, current_user: deps.CurrentUser
) -> Any:
    """Resolve the functional head governing a given employee."""
    emp = await db.get(Employee, employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    head = await fh_service.resolve_head(db, emp)
    if head is None:
        return {"employee_id": employee_id, "head_user_id": None, "head_name": None}
    return {"employee_id": employee_id, "head_user_id": head.id, "head_name": head.full_name}
