from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import require_permissions
from app.core.database import get_db
from app.db.models.iam import Role
from app.modules.iam.schemas import RoleCreate, RolePublic, RoleUpdate
from app.modules.iam.service import (
    create_role,
    delete_role,
    list_roles,
    update_role,
)

router = APIRouter(prefix="/roles")


@router.get(
    "",
    response_model=list[RolePublic],
    dependencies=[Depends(require_permissions({"admin.roles.read"}))],
)
def admin_list_roles(db: Session = Depends(get_db)) -> list[RolePublic]:
    return [RolePublic.model_validate(r) for r in list_roles(db)]


@router.post(
    "",
    response_model=RolePublic,
    dependencies=[Depends(require_permissions({"admin.roles.write"}))],
)
def admin_create_role(
    payload: RoleCreate,
    db: Session = Depends(get_db),
) -> RolePublic:
    return RolePublic.model_validate(create_role(db, name=payload.name))


@router.put(
    "/{role_id}",
    response_model=RolePublic,
    dependencies=[Depends(require_permissions({"admin.roles.write"}))],
)
def admin_update_role(
    role_id: int,
    payload: RoleUpdate,
    db: Session = Depends(get_db),
) -> RolePublic:
    role = db.get(Role, role_id)
    if not role:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Role not found")
    updated = update_role(db, role=role, name=payload.name)
    return RolePublic.model_validate(updated)


@router.delete(
    "/{role_id}",
    dependencies=[Depends(require_permissions({"admin.roles.write"}))],
)
def admin_delete_role(role_id: int, db: Session = Depends(get_db)) -> dict:
    role = db.get(Role, role_id)
    if not role:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Role not found")
    delete_role(db, role=role)
    return {"status": "ok"}
