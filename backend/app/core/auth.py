from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.request_context import actor_user_id_var
from app.core.security import decode_token
from app.db.models.iam import Permission, RolePermission, User, UserRole

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

_INVALID_ACCESS_TOKEN = "Invalid access token"


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    try:
        payload = decode_token(token)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_INVALID_ACCESS_TOKEN,
        ) from None

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_INVALID_ACCESS_TOKEN,
        )

    subject = payload.get("sub")
    if not subject:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_INVALID_ACCESS_TOKEN,
        )

    user_id = int(subject)
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User inactive or not found",
        )

    actor_user_id_var.set(user.id)
    return user


def get_user_permissions(db: Session, user_id: int) -> set[str]:
    stmt = (
        select(Permission.code)
        .join(RolePermission, Permission.id == RolePermission.permission_id)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .where(UserRole.user_id == user_id)
    )
    rows = db.execute(stmt).all()
    return {row[0] for row in rows}


def require_permissions(required: set[str]) -> Callable:
    def _dep(
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        perms = get_user_permissions(db, user.id)
        if not required.issubset(perms):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Missing required permissions",
            )
        return user

    return _dep
