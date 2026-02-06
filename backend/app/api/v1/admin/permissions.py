from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import require_permissions
from app.core.database import get_db
from app.db.models.iam import Permission
from app.modules.iam.schemas import (
    PermissionCreate,
    PermissionPublic,
    PermissionUpdate,
)
from app.modules.iam.service import (
    create_permission,
    delete_permission,
    list_permissions,
    update_permission,
)

router = APIRouter(prefix="/permissions")


@router.get(
    "",
    response_model=list[PermissionPublic],
    dependencies=[Depends(require_permissions({"admin.permissions.read"}))],
)
def admin_list_permissions(
    db: Session = Depends(get_db),
) -> list[PermissionPublic]:
    return [PermissionPublic.model_validate(p) for p in list_permissions(db)]


@router.post(
    "",
    response_model=PermissionPublic,
    dependencies=[Depends(require_permissions({"admin.permissions.write"}))],
)
def admin_create_permission(
    payload: PermissionCreate,
    db: Session = Depends(get_db),
) -> PermissionPublic:
    perm = create_permission(
        db,
        code=payload.code,
        description=payload.description,
    )
    return PermissionPublic.model_validate(perm)


@router.put(
    "/{permission_id}",
    response_model=PermissionPublic,
    dependencies=[Depends(require_permissions({"admin.permissions.write"}))],
)
def admin_update_permission(
    permission_id: int,
    payload: PermissionUpdate,
    db: Session = Depends(get_db),
) -> PermissionPublic:
    perm = db.get(Permission, permission_id)
    if not perm:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Permission not found")
    updated = update_permission(db, perm=perm, description=payload.description)
    return PermissionPublic.model_validate(updated)


@router.delete(
    "/{permission_id}",
    dependencies=[Depends(require_permissions({"admin.permissions.write"}))],
)
def admin_delete_permission(
    permission_id: int,
    db: Session = Depends(get_db),
) -> dict:
    perm = db.get(Permission, permission_id)
    if not perm:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Permission not found")
    delete_permission(db, perm=perm)
    return {"status": "ok"}
