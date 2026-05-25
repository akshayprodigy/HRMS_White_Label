from app.models.project import Project
from app.schemas.project import ProjectRead
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select, update as sql_update, func
from sqlalchemy.orm import selectinload
from app.api import deps
from app.core.security import get_password_hash
from app.models.audit import AuditLog
from app.models.user import User, Role, Permission
from app.schemas.user import (
    UserRead, UserCreate, UserAdminUpdate,
    RoleSchema, RoleCreate, RoleUpdate, PermissionSchema
)
from app.schemas.leave import LeaveTypeRead, LeaveTypeCreate, LeaveTypeUpdate
from app.models.leave import LeaveType
from app.models.department import Department
from app.models.employee import Employee
from app.models.required_document_type import RequiredDocumentType
from app.schemas.department import (
    DepartmentRead, DepartmentCreate, DepartmentUpdate
)
from app.models.functional_area import FunctionalArea
from app.schemas.functional_area import (
    FunctionalAreaRead, FunctionalAreaCreate, FunctionalAreaUpdate
)
from app.models.project import Project as ProjectModel

router = APIRouter()

ADMIN_ACCESS = "admin access"

# User Management
@router.get("/leave-types", response_model=List[LeaveTypeRead])
async def list_leave_types(
    db: deps.DBDep,
    current_user: User = Depends(deps.check_permissions([ADMIN_ACCESS]))
) -> Any:
    """List all leave types."""
    result = await db.execute(select(LeaveType))
    return result.scalars().all()


@router.get("/departments", response_model=List[DepartmentRead])
async def list_departments(
    db: deps.DBDep,
    current_user: User = Depends(deps.check_permissions([ADMIN_ACCESS]))
) -> Any:
    """List all departments."""
    result = await db.execute(select(Department))
    return result.scalars().all()


@router.post("/departments", response_model=DepartmentRead)
async def create_department(
    *,
    db: deps.DBDep,
    dept_in: DepartmentCreate,
    current_user: User = Depends(deps.check_permissions([ADMIN_ACCESS]))
) -> Any:
    """Create a new department."""
    result = await db.execute(
        select(Department).where(Department.name == dept_in.name)
    )
    if result.scalars().first():
        raise HTTPException(status_code=400, detail="Department already exists")
    
    db_obj = Department(**dept_in.model_dump())
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj


@router.patch("/departments/{dept_id}", response_model=DepartmentRead)
async def update_department(
    *,
    db: deps.DBDep,
    dept_id: int,
    dept_in: DepartmentUpdate,
    current_user: User = Depends(deps.check_permissions([ADMIN_ACCESS]))
) -> Any:
    """Update a department. Renaming also rewrites `employee.department` so the
    admin list stays the single source of truth."""
    db_obj = await db.get(Department, dept_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Department not found")

    update_data = dept_in.model_dump(exclude_unset=True)

    new_name = update_data.get("name")
    old_name = db_obj.name
    if new_name is not None and new_name != old_name:
        clash = (await db.execute(
            select(Department.id).where(
                Department.name == new_name, Department.id != dept_id
            ).limit(1)
        )).scalar_one_or_none()
        if clash is not None:
            raise HTTPException(
                status_code=400,
                detail=f"Department '{new_name}' already exists",
            )
        await db.execute(
            sql_update(Employee)
            .where(Employee.department == old_name)
            .values(department=new_name)
        )

    for field, value in update_data.items():
        setattr(db_obj, field, value)

    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj


@router.delete("/departments/{dept_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_department(
    *,
    db: deps.DBDep,
    dept_id: int,
    current_user: User = Depends(deps.check_permissions([ADMIN_ACCESS]))
) -> None:
    """Delete a department. Blocked if any employee is still on it."""
    db_obj = await db.get(Department, dept_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Department not found")

    in_use = (await db.execute(
        select(func.count()).select_from(Employee).where(
            Employee.department == db_obj.name
        )
    )).scalar_one()
    if in_use:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot delete '{db_obj.name}' — {in_use} employee(s) "
                "are still assigned. Reassign them first."
            ),
        )

    await db.delete(db_obj)
    await db.commit()
    return None


# Functional Areas (project classification taxonomy)
@router.get("/functional-areas", response_model=List[FunctionalAreaRead])
async def list_functional_areas(
    db: deps.DBDep,
    include_inactive: bool = Query(False),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """List functional areas. Any authenticated user can list (used by
    project-create UI). Admin gate applies to write operations."""
    stmt = select(FunctionalArea)
    if not include_inactive:
        stmt = stmt.where(FunctionalArea.is_active.is_(True))
    stmt = stmt.order_by(FunctionalArea.name)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/functional-areas", response_model=FunctionalAreaRead)
async def create_functional_area(
    *,
    db: deps.DBDep,
    fa_in: FunctionalAreaCreate,
    current_user: User = Depends(deps.check_permissions([ADMIN_ACCESS])),
) -> Any:
    """Create a new functional area (admin only)."""
    code_upper = fa_in.code.strip().upper()
    name_clean = fa_in.name.strip()
    clash = (await db.execute(
        select(FunctionalArea).where(
            (FunctionalArea.code == code_upper) | (FunctionalArea.name == name_clean)
        )
    )).scalars().first()
    if clash is not None:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Functional area with code '{code_upper}' "
                f"or name '{name_clean}' already exists"
            ),
        )
    db_obj = FunctionalArea(
        name=name_clean, code=code_upper, is_active=fa_in.is_active
    )
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj


@router.patch("/functional-areas/{fa_id}", response_model=FunctionalAreaRead)
async def update_functional_area(
    *,
    db: deps.DBDep,
    fa_id: int,
    fa_in: FunctionalAreaUpdate,
    current_user: User = Depends(deps.check_permissions([ADMIN_ACCESS])),
) -> Any:
    """Update a functional area (admin only)."""
    db_obj = await db.get(FunctionalArea, fa_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Functional area not found")
    update_data = fa_in.model_dump(exclude_unset=True)
    if "code" in update_data and update_data["code"]:
        update_data["code"] = update_data["code"].strip().upper()
    if "name" in update_data and update_data["name"]:
        update_data["name"] = update_data["name"].strip()
    # Uniqueness checks if name/code changed
    new_name = update_data.get("name")
    new_code = update_data.get("code")
    if new_name and new_name != db_obj.name:
        clash = (await db.execute(
            select(FunctionalArea.id).where(
                FunctionalArea.name == new_name,
                FunctionalArea.id != fa_id,
            ).limit(1)
        )).scalar_one_or_none()
        if clash is not None:
            raise HTTPException(
                status_code=400,
                detail=f"Functional area '{new_name}' already exists",
            )
    if new_code and new_code != db_obj.code:
        clash = (await db.execute(
            select(FunctionalArea.id).where(
                FunctionalArea.code == new_code,
                FunctionalArea.id != fa_id,
            ).limit(1)
        )).scalar_one_or_none()
        if clash is not None:
            raise HTTPException(
                status_code=400,
                detail=f"Functional area code '{new_code}' already exists",
            )
    for field, value in update_data.items():
        setattr(db_obj, field, value)
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj


@router.delete(
    "/functional-areas/{fa_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_functional_area(
    *,
    db: deps.DBDep,
    fa_id: int,
    current_user: User = Depends(deps.check_permissions([ADMIN_ACCESS])),
) -> None:
    """Delete a functional area (admin only). Blocked if any project still
    references it — deactivate instead by setting is_active=false."""
    db_obj = await db.get(FunctionalArea, fa_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Functional area not found")
    in_use = (await db.execute(
        select(func.count()).select_from(ProjectModel).where(
            ProjectModel.functional_area_id == fa_id
        )
    )).scalar_one()
    if in_use:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot delete '{db_obj.name}' — {in_use} project(s) "
                "still reference it. Deactivate instead."
            ),
        )
    await db.delete(db_obj)
    await db.commit()
    return None


@router.post("/leave-types", response_model=LeaveTypeRead)
async def create_leave_type(
    *,
    db: deps.DBDep,
    leave_type_in: LeaveTypeCreate,
    current_user: User = Depends(deps.check_permissions([ADMIN_ACCESS]))
) -> Any:
    """Create a new leave type."""
    result = await db.execute(select(LeaveType).where(LeaveType.name == leave_type_in.name))
    if result.scalars().first():
        raise HTTPException(status_code=400, detail="Leave type already exists")
    
    db_obj = LeaveType(**leave_type_in.model_dump())
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj


@router.patch("/leave-types/{type_id}", response_model=LeaveTypeRead)
async def update_leave_type(
    *,
    db: deps.DBDep,
    type_id: int,
    leave_type_in: LeaveTypeUpdate,
    current_user: User = Depends(deps.check_permissions([ADMIN_ACCESS]))
) -> Any:
    """Update a leave type."""
    db_obj = await db.get(LeaveType, type_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Leave type not found")
    
    update_data = leave_type_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_obj, field, value)
    
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj


@router.delete("/leave-types/{type_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_leave_type(
    *,
    db: deps.DBDep,
    type_id: int,
    current_user: User = Depends(deps.check_permissions([ADMIN_ACCESS]))
) -> None:
    """Delete a leave type."""
    db_obj = await db.get(LeaveType, type_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Leave type not found")
    
    await db.delete(db_obj)
    await db.commit()
    return None


@router.get("/users", response_model=List[UserRead])
async def list_users(
    db: deps.DBDep,
    current_user: User = Depends(deps.check_permissions([ADMIN_ACCESS]))
) -> Any:
    result = await db.execute(select(User))
    return result.scalars().all()


@router.post("/users", response_model=UserRead)
async def create_user(
    *,
    db: deps.DBDep,
    user_in: UserCreate,
    current_user: User = Depends(deps.check_permissions([ADMIN_ACCESS]))
) -> Any:
    result = await db.execute(select(User).where(User.email == user_in.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="User already exists")
    
    db_obj = User(
        email=user_in.email,
        hashed_password=get_password_hash(user_in.password),
        full_name=user_in.full_name,
        is_active=user_in.is_active,
    )
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj


@router.patch("/users/{user_id}", response_model=UserRead)
async def update_user_admin(
    *,
    db: deps.DBDep,
    user_id: int,
    user_in: UserAdminUpdate,
    current_user: User = Depends(deps.check_permissions([ADMIN_ACCESS]))
) -> Any:
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if user_in.email is not None:
        user.email = user_in.email
    if user_in.full_name is not None:
        user.full_name = user_in.full_name
    if user_in.is_active is not None:
        user.is_active = user_in.is_active
    if user_in.password is not None:
        user.hashed_password = get_password_hash(user_in.password)
    if user_in.manager_id is not None:
        user.manager_id = user_in.manager_id
    
    if user_in.role_ids is not None:
        result = await db.execute(
            select(Role).where(Role.id.in_(user_in.role_ids))
        )
        user.roles = list(result.scalars().all())
    
    await db.commit()
    await db.refresh(user)
    return user


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    *,
    db: deps.DBDep,
    user_id: int,
    current_user: User = Depends(deps.check_permissions([ADMIN_ACCESS]))
) -> None:
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete self")
    
    await db.delete(user)
    await db.commit()
    return None


# Role Management
@router.get("/roles", response_model=List[RoleSchema])
async def list_roles(
    db: deps.DBDep,
    current_user: User = Depends(deps.check_permissions([ADMIN_ACCESS]))
) -> Any:
    result = await db.execute(select(Role))
    return result.scalars().all()


@router.post("/roles", response_model=RoleSchema)
async def create_role(
    *,
    db: deps.DBDep,
    role_in: RoleCreate,
    current_user: User = Depends(deps.check_permissions([ADMIN_ACCESS]))
) -> Any:
    db_obj = Role(
        name=role_in.name,
        description=role_in.description
    )
    if role_in.permission_ids:
        result = await db.execute(
            select(Permission).where(Permission.id.in_(role_in.permission_ids))
        )
        db_obj.permissions = list(result.scalars().all())
    
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj


@router.patch("/roles/{role_id}", response_model=RoleSchema)
async def update_role(
    *,
    db: deps.DBDep,
    role_id: int,
    role_in: RoleUpdate,
    current_user: User = Depends(deps.check_permissions([ADMIN_ACCESS]))
) -> Any:
    role = await db.get(Role, role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    
    if role_in.name is not None:
        role.name = role_in.name
    if role_in.description is not None:
        role.description = role_in.description
    
    if role_in.permission_ids is not None:
        result = await db.execute(
            select(Permission).where(Permission.id.in_(role_in.permission_ids))
        )
        role.permissions = list(result.scalars().all())
    
    await db.commit()
    await db.refresh(role)
    return role


@router.delete("/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
    *,
    db: deps.DBDep,
    role_id: int,
    current_user: User = Depends(deps.check_permissions([ADMIN_ACCESS]))
) -> None:
    role = await db.get(Role, role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    
    await db.delete(role)
    await db.commit()
    return None


# Permission Management
@router.get("/permissions", response_model=List[PermissionSchema])
async def list_permissions(
    db: deps.DBDep,
    current_user: User = Depends(deps.check_permissions([ADMIN_ACCESS]))
) -> Any:
    result = await db.execute(select(Permission))
    return result.scalars().all()


# Project Management
@router.get("/projects", response_model=List[ProjectRead])
async def list_projects(
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user)
) -> Any:
    """List projects for timer selection and portfolio overview using RLS."""
    from datetime import timedelta
    from app.models.project import ProjectMember
    from app.models.bd import Lead

    # Base query
    query = select(Project).options(
        selectinload(Project.members).selectinload(ProjectMember.user),
        selectinload(Project.cost_baselines),
        selectinload(Project.lead).selectinload(Lead.account),
        selectinload(Project.client),
    )

    # Apply RLS if not superuser or elevated roles
    user_roles = [r.name.lower() for r in current_user.roles]
    elevated = {
        "super admin",
        "dop",
        "coo",
        "ceo",
        "admin",
        "cto",
        "bd manager",
        "operations head",
        "ops head",
        "operations",
    }
    is_admin = current_user.is_superuser or bool(set(user_roles) & elevated)
    
    if not is_admin:
        # Join with members to filter by user_id.
        # Use a join/where to avoid duplicates.
        query = query.join(Project.members).where(
            ProjectMember.user_id == current_user.id
        )

    result = await db.execute(query)
    projects = result.scalars().all()
    
    read_projects = []
    for p in projects:
        # Get manager name
        manager = next(
            (m.user.full_name for m in p.members if m.role == "manager"),
            None,
        )
        
        # Get active baseline
        active_baseline = next(
            (b for b in p.cost_baselines if b.is_active),
            None,
        )
        budget = active_baseline.amount if active_baseline else 0.0
        budget_hours = (
            float(active_baseline.budget_hours)
            if active_baseline and active_baseline.budget_hours
            else None
        )
        
        # Resolve client name: prefer direct client FK, else lead.account
        client_name = "Internal"
        client_id_val = p.client_id
        if p.client is not None:
            client_name = p.client.name
        elif p.lead and p.lead.account:
            client_name = p.lead.account.name
            client_id_val = p.lead.account.id

        read_projects.append(ProjectRead(
            id=p.id,
            name=p.name,
            description=p.description,
            code=p.code,
            status=p.status,
            created_at=p.created_at,
            manager_name=manager,
            budget=budget,
            budget_hours=budget_hours,
            actual_cost=0.0,
            client_id=client_id_val,
            client_name=client_name,
            start_date=p.created_at,
            end_date=p.created_at + timedelta(days=90)
        ))

    return read_projects


# ─── Required Document Types ──────────────────────────────────

class RequiredDocTypeCreate(BaseModel):
    doc_type: str
    description: Optional[str] = None
    is_active: bool = True


class RequiredDocTypeUpdate(BaseModel):
    doc_type: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


def _serialize_required_type(r: RequiredDocumentType) -> dict:
    return {
        "id": r.id,
        "doc_type": r.doc_type,
        "description": r.description,
        "is_active": r.is_active,
    }


@router.get("/required-documents")
async def list_required_doc_types(
    db: deps.DBDep,
    current_user: User = Depends(deps.check_permissions([ADMIN_ACCESS])),
) -> Any:
    rows = (await db.execute(
        select(RequiredDocumentType).order_by(RequiredDocumentType.doc_type)
    )).scalars().all()
    return [_serialize_required_type(r) for r in rows]


@router.post("/required-documents")
async def create_required_doc_type(
    *,
    db: deps.DBDep,
    body: RequiredDocTypeCreate,
    current_user: User = Depends(deps.check_permissions([ADMIN_ACCESS])),
) -> Any:
    name = (body.doc_type or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="doc_type is required")
    existing = (await db.execute(
        select(RequiredDocumentType.id).where(RequiredDocumentType.doc_type == name).limit(1)
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="That document type already exists")
    row = RequiredDocumentType(
        doc_type=name,
        description=body.description,
        is_active=body.is_active,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _serialize_required_type(row)


@router.patch("/required-documents/{type_id}")
async def update_required_doc_type(
    *,
    db: deps.DBDep,
    type_id: int,
    body: RequiredDocTypeUpdate,
    current_user: User = Depends(deps.check_permissions([ADMIN_ACCESS])),
) -> Any:
    row = await db.get(RequiredDocumentType, type_id)
    if not row:
        raise HTTPException(status_code=404, detail="Required document type not found")
    data = body.model_dump(exclude_unset=True)
    if "doc_type" in data:
        new_name = (data["doc_type"] or "").strip()
        if not new_name:
            raise HTTPException(status_code=400, detail="doc_type cannot be empty")
        clash = (await db.execute(
            select(RequiredDocumentType.id).where(
                RequiredDocumentType.doc_type == new_name,
                RequiredDocumentType.id != type_id,
            ).limit(1)
        )).scalar_one_or_none()
        if clash:
            raise HTTPException(status_code=400, detail="That document type already exists")
        row.doc_type = new_name
    if "description" in data:
        row.description = data["description"]
    if "is_active" in data:
        row.is_active = bool(data["is_active"])
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _serialize_required_type(row)


@router.delete("/required-documents/{type_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_required_doc_type(
    *,
    db: deps.DBDep,
    type_id: int,
    current_user: User = Depends(deps.check_permissions([ADMIN_ACCESS])),
) -> None:
    row = await db.get(RequiredDocumentType, type_id)
    if not row:
        raise HTTPException(status_code=404, detail="Required document type not found")
    await db.delete(row)
    await db.commit()
    return None


# ─── Audit Log Viewer ─────────────────────────────────────────

@router.get("/audit-log")
async def list_audit_log(
    *,
    db: deps.DBDep,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    action: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    user_id: Optional[int] = Query(None),
    current_user: User = Depends(deps.check_permissions([ADMIN_ACCESS])),
) -> Any:
    """Paginated, filterable view of system audit events.

    Filters are AND'd together. Latest entries first.
    """
    query = select(AuditLog).options(selectinload(AuditLog.user))
    if action:
        query = query.where(AuditLog.action == action)
    if resource_type:
        query = query.where(AuditLog.resource_type == resource_type)
    if user_id is not None:
        query = query.where(AuditLog.user_id == user_id)

    total = (await db.execute(
        select(func.count()).select_from(query.subquery())
    )).scalar() or 0

    rows = (await db.execute(
        query.order_by(AuditLog.created_at.desc())
        .offset((page - 1) * size).limit(size)
    )).scalars().all()

    return {
        "items": [
            {
                "id": r.id,
                "user_id": r.user_id,
                "user_name": r.user.full_name if r.user else None,
                "user_email": r.user.email if r.user else None,
                "action": r.action,
                "resource_type": r.resource_type,
                "resource_id": r.resource_id,
                "details": r.details,
                "ip_address": r.ip_address,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
        "total": total,
        "page": page,
        "size": size,
    }


@router.get("/audit-log/distinct")
async def audit_log_distinct_values(
    *,
    db: deps.DBDep,
    current_user: User = Depends(deps.check_permissions([ADMIN_ACCESS])),
) -> Any:
    """Power the filter dropdowns on the audit-log viewer."""
    actions = (await db.execute(
        select(AuditLog.action).distinct().order_by(AuditLog.action)
    )).scalars().all()
    resources = (await db.execute(
        select(AuditLog.resource_type).distinct().order_by(AuditLog.resource_type)
    )).scalars().all()
    return {
        "actions": [a for a in actions if a],
        "resource_types": [r for r in resources if r],
    }
