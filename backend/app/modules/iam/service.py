from __future__ import annotations

import datetime as dt

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.audit import log_audit, model_to_dict
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from app.db.models.iam import Permission, Role, RolePermission, User, UserRole
from app.db.models.refresh_tokens import RefreshToken


def authenticate_user(db: Session, *, email: str, password: str) -> User:
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    if not verify_password(password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    return user


def issue_tokens_for_user(
    db: Session,
    *,
    user: User,
    access_minutes: int,
    refresh_days: int,
) -> tuple[str, int, str, str, dt.datetime]:
    access_token, expires_in = create_access_token(
        subject=str(user.id),
        expires_in_minutes=access_minutes,
    )
    refresh_token, refresh_jti, refresh_exp = create_refresh_token(
        subject=str(user.id),
        expires_in_days=refresh_days,
    )

    db.add(
        RefreshToken(
            user_id=user.id,
            jti=refresh_jti,
            # MariaDB DATETIME is stored without timezone; treat as UTC.
            expires_at=refresh_exp.replace(tzinfo=None),
        )
    )
    db.commit()
    return access_token, expires_in, refresh_token, refresh_jti, refresh_exp


def rotate_refresh_token(
    db: Session,
    *,
    user_id: int,
    old_jti: str,
    access_minutes: int,
    refresh_days: int,
) -> tuple[str, int, str, str, dt.datetime]:
    # MariaDB DATETIME is stored without timezone; treat values as naive UTC.
    now = dt.datetime.now(tz=dt.UTC).replace(tzinfo=None)
    token_row = db.execute(
        select(RefreshToken).where(
            RefreshToken.jti == old_jti,
            RefreshToken.user_id == user_id,
        )
    ).scalar_one_or_none()

    if not token_row or token_row.revoked_at is not None or token_row.expires_at <= now:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    token_row.revoked_at = now
    db.add(token_row)
    db.commit()

    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User inactive",
        )

    return issue_tokens_for_user(
        db,
        user=user,
        access_minutes=access_minutes,
        refresh_days=refresh_days,
    )


def revoke_refresh_token(db: Session, *, jti: str) -> None:
    now = dt.datetime.now(tz=dt.UTC).replace(tzinfo=None)
    token_row = db.execute(select(RefreshToken).where(RefreshToken.jti == jti)).scalar_one_or_none()
    if token_row and token_row.revoked_at is None:
        token_row.revoked_at = now
        db.add(token_row)
        db.commit()


def list_users(db: Session) -> list[User]:
    return list(db.execute(select(User).order_by(User.id.desc())).scalars().all())


def create_user(
    db: Session,
    *,
    email: str,
    password: str,
    is_active: bool,
) -> User:
    existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Email already exists")

    user = User(
        email=email,
        password_hash=hash_password(password),
        is_active=is_active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    log_audit(
        db,
        entity_type="users",
        entity_id=str(user.id),
        action="create",
        before_json=None,
        after_json=model_to_dict(user),
    )
    return user


def update_user(
    db: Session,
    *,
    user: User,
    email: str | None,
    password: str | None,
    is_active: bool | None,
) -> User:
    before = model_to_dict(user)

    if email and email != user.email:
        existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=400, detail="Email already exists")
        user.email = email

    if password:
        user.password_hash = hash_password(password)

    if is_active is not None:
        user.is_active = is_active

    db.add(user)
    db.commit()
    db.refresh(user)

    log_audit(
        db,
        entity_type="users",
        entity_id=str(user.id),
        action="update",
        before_json=before,
        after_json=model_to_dict(user),
    )
    return user


def delete_user(db: Session, *, user: User) -> None:
    before = model_to_dict(user)
    db.delete(user)
    db.commit()

    log_audit(
        db,
        entity_type="users",
        entity_id=str(user.id),
        action="delete",
        before_json=before,
        after_json=None,
    )


def list_roles(db: Session) -> list[Role]:
    return list(db.execute(select(Role).order_by(Role.id.desc())).scalars().all())


def create_role(db: Session, *, name: str) -> Role:
    existing = db.execute(select(Role).where(Role.name == name)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Role already exists")
    role = Role(name=name)
    db.add(role)
    db.commit()
    db.refresh(role)

    log_audit(
        db,
        entity_type="roles",
        entity_id=str(role.id),
        action="create",
        before_json=None,
        after_json=model_to_dict(role),
    )
    return role


def update_role(db: Session, *, role: Role, name: str) -> Role:
    before = model_to_dict(role)
    if name != role.name:
        existing = db.execute(select(Role).where(Role.name == name)).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=400, detail="Role already exists")
        role.name = name
    db.add(role)
    db.commit()
    db.refresh(role)

    log_audit(
        db,
        entity_type="roles",
        entity_id=str(role.id),
        action="update",
        before_json=before,
        after_json=model_to_dict(role),
    )
    return role


def delete_role(db: Session, *, role: Role) -> None:
    before = model_to_dict(role)
    db.delete(role)
    db.commit()

    log_audit(
        db,
        entity_type="roles",
        entity_id=str(role.id),
        action="delete",
        before_json=before,
        after_json=None,
    )


def list_permissions(db: Session) -> list[Permission]:
    return list(db.execute(select(Permission).order_by(Permission.id.desc())).scalars().all())


def create_permission(
    db: Session,
    *,
    code: str,
    description: str | None,
) -> Permission:
    existing = db.execute(select(Permission).where(Permission.code == code)).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=400,
            detail="Permission already exists",
        )
    perm = Permission(code=code, description=description)
    db.add(perm)
    db.commit()
    db.refresh(perm)

    log_audit(
        db,
        entity_type="permissions",
        entity_id=str(perm.id),
        action="create",
        before_json=None,
        after_json=model_to_dict(perm),
    )
    return perm


def update_permission(
    db: Session,
    *,
    perm: Permission,
    description: str | None,
) -> Permission:
    before = model_to_dict(perm)
    perm.description = description
    db.add(perm)
    db.commit()
    db.refresh(perm)

    log_audit(
        db,
        entity_type="permissions",
        entity_id=str(perm.id),
        action="update",
        before_json=before,
        after_json=model_to_dict(perm),
    )
    return perm


def delete_permission(db: Session, *, perm: Permission) -> None:
    before = model_to_dict(perm)
    db.delete(perm)
    db.commit()

    log_audit(
        db,
        entity_type="permissions",
        entity_id=str(perm.id),
        action="delete",
        before_json=before,
        after_json=None,
    )


def set_user_roles(db: Session, *, user_id: int, role_ids: list[int]) -> None:
    db.execute(delete(UserRole).where(UserRole.user_id == user_id))
    for role_id in role_ids:
        db.add(UserRole(user_id=user_id, role_id=role_id))
    db.commit()


def set_role_permissions(
    db: Session,
    *,
    role_id: int,
    permission_ids: list[int],
) -> None:
    db.execute(delete(RolePermission).where(RolePermission.role_id == role_id))
    for permission_id in permission_ids:
        db.add(RolePermission(role_id=role_id, permission_id=permission_id))
    db.commit()
