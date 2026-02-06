from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import require_permissions
from app.core.database import get_db
from app.db.models.iam import User
from app.modules.iam.schemas import (
    AssignRolesRequest,
    UserCreate,
    UserPublic,
    UserUpdate,
)
from app.modules.iam.service import (
    create_user,
    delete_user,
    list_users,
    set_user_roles,
    update_user,
)

router = APIRouter(prefix="/users")

_USER_NOT_FOUND = "User not found"


@router.get(
    "",
    response_model=list[UserPublic],
    dependencies=[Depends(require_permissions({"admin.users.read"}))],
)
def admin_list_users(db: Session = Depends(get_db)) -> list[UserPublic]:
    return [UserPublic.model_validate(u) for u in list_users(db)]


@router.post(
    "",
    response_model=UserPublic,
    dependencies=[Depends(require_permissions({"admin.users.write"}))],
)
def admin_create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
) -> UserPublic:
    user = create_user(
        db,
        email=str(payload.email),
        password=payload.password,
        is_active=payload.is_active,
    )
    return UserPublic.model_validate(user)


@router.get(
    "/{user_id}",
    response_model=UserPublic,
    dependencies=[Depends(require_permissions({"admin.users.read"}))],
)
def admin_get_user(user_id: int, db: Session = Depends(get_db)) -> UserPublic:
    user = db.get(User, user_id)
    if not user:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=_USER_NOT_FOUND)
    return UserPublic.model_validate(user)


@router.put(
    "/{user_id}",
    response_model=UserPublic,
    dependencies=[Depends(require_permissions({"admin.users.write"}))],
)
def admin_update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
) -> UserPublic:
    user = db.get(User, user_id)
    if not user:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=_USER_NOT_FOUND)
    updated = update_user(
        db,
        user=user,
        email=payload.email,
        password=payload.password,
        is_active=payload.is_active,
    )
    return UserPublic.model_validate(updated)


@router.delete(
    "/{user_id}",
    dependencies=[Depends(require_permissions({"admin.users.write"}))],
)
def admin_delete_user(user_id: int, db: Session = Depends(get_db)) -> dict:
    user = db.get(User, user_id)
    if not user:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=_USER_NOT_FOUND)
    delete_user(db, user=user)
    return {"status": "ok"}


@router.put(
    "/{user_id}/roles",
    dependencies=[Depends(require_permissions({"admin.users.write"}))],
)
def admin_set_user_roles(
    user_id: int,
    payload: AssignRolesRequest,
    db: Session = Depends(get_db),
) -> dict:
    user = db.get(User, user_id)
    if not user:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=_USER_NOT_FOUND)
    set_user_roles(db, user_id=user_id, role_ids=payload.role_ids)
    return {"status": "ok"}
