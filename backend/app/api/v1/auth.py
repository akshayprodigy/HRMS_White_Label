from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, get_user_permissions
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import decode_token
from app.db.models.iam import User
from app.modules.iam.schemas import (
    AuthResponse,
    AuthUser,
    LoginRequest,
    LogoutResponse,
    MeResponse,
)
from app.modules.iam.service import (
    authenticate_user,
    issue_tokens_for_user,
    revoke_refresh_token,
    rotate_refresh_token,
)

router = APIRouter(prefix="/auth", tags=["auth"])

_INVALID_REFRESH_TOKEN = "Invalid refresh token"


def _set_refresh_cookie(
    response: Response,
    refresh_token: str,
    max_age_seconds: int,
) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=refresh_token,
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite=settings.refresh_cookie_samesite,
        max_age=max_age_seconds,
        path=settings.refresh_cookie_path,
    )


def _clear_refresh_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        path=settings.refresh_cookie_path,
    )


@router.post("/login", response_model=AuthResponse)
def login(
    payload: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> AuthResponse:
    settings = get_settings()
    user = authenticate_user(
        db,
        email=str(payload.email),
        password=payload.password,
    )

    (
        access_token,
        expires_in,
        refresh_token,
        _jti,
        _exp,
    ) = issue_tokens_for_user(
        db,
        user=user,
        access_minutes=settings.access_token_minutes,
        refresh_days=settings.refresh_token_days,
    )
    _set_refresh_cookie(
        response,
        refresh_token,
        max_age_seconds=settings.refresh_token_days * 86400,
    )

    perms = sorted(get_user_permissions(db, user.id))
    return AuthResponse(
        access_token=access_token,
        expires_in=expires_in,
        user=AuthUser(id=user.id, email=user.email),
        permissions=perms,
    )


@router.post("/refresh", response_model=AuthResponse)
def refresh(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> AuthResponse:
    settings = get_settings()
    token = request.cookies.get(settings.refresh_cookie_name)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing refresh token",
        )

    try:
        payload = decode_token(token)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_INVALID_REFRESH_TOKEN,
        ) from None

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_INVALID_REFRESH_TOKEN,
        )

    subject = payload.get("sub")
    jti = payload.get("jti")
    if not subject or not jti:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_INVALID_REFRESH_TOKEN,
        )

    (
        access_token,
        expires_in,
        new_refresh_token,
        _new_jti,
        _new_exp,
    ) = rotate_refresh_token(
        db,
        user_id=int(subject),
        old_jti=str(jti),
        access_minutes=settings.access_token_minutes,
        refresh_days=settings.refresh_token_days,
    )

    _set_refresh_cookie(
        response,
        new_refresh_token,
        max_age_seconds=settings.refresh_token_days * 86400,
    )

    user = db.get(User, int(subject))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    perms = sorted(get_user_permissions(db, user.id))
    return AuthResponse(
        access_token=access_token,
        expires_in=expires_in,
        user=AuthUser(id=user.id, email=user.email),
        permissions=perms,
    )


@router.post("/logout", response_model=LogoutResponse)
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> LogoutResponse:
    settings = get_settings()
    token = request.cookies.get(settings.refresh_cookie_name)
    if token:
        try:
            payload = decode_token(token)
            if payload.get("type") == "refresh" and payload.get("jti"):
                revoke_refresh_token(db, jti=str(payload["jti"]))
        except ValueError:
            pass

    _clear_refresh_cookie(response)
    return LogoutResponse(status="ok")


@router.get("/me", response_model=MeResponse)
def me(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MeResponse:
    perms = sorted(get_user_permissions(db, current_user.id))
    return MeResponse(
        user=AuthUser(id=current_user.id, email=current_user.email),
        permissions=perms,
    )
