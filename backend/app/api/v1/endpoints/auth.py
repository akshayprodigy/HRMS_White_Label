import logging
from typing import Any, Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from jose import jwt, JWTError
from pydantic import ValidationError

from app.api import deps
from app.core import security
from app.core.config import settings
from app.models.user import User
from app.schemas.user import Token, UserRead, TokenPayload, TokenRefresh
from pydantic import BaseModel as PydanticBaseModel

class ChangePasswordRequest(PydanticBaseModel):
    current_password: str
    new_password: str

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/login", response_model=Token)
async def login(
    db: deps.DBDep, form_data: OAuth2PasswordRequestForm = Depends()
) -> Any:
    """
    OAuth2 compatible token login, get an access token for future requests.
    """
    logger.info(f"Login attempt for user: {form_data.username}")
    result = await db.execute(
        select(User).where(User.email == form_data.username).limit(1)
    )
    user = result.scalars().first()
    
    if not user or not security.verify_password(
        form_data.password, user.hashed_password
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    elif not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user"
        )
    
    return {
        "access_token": security.create_access_token(user.id),
        "refresh_token": security.create_refresh_token(user.id),
        "token_type": "bearer",
    }


@router.post("/refresh", response_model=Token)
async def refresh_token(db: deps.DBDep, body: TokenRefresh) -> Any:
    """
    Refresh tokens using a valid refresh token.
    """
    try:
        payload = jwt.decode(
            body.refresh_token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )
        token_data = TokenPayload(**payload)
        if not token_data.refresh:
            raise HTTPException(status_code=401, detail="Invalid token type")
    except (JWTError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )
    
    result = await db.execute(select(User).where(User.id == token_data.sub))
    user = result.scalar_one_or_none()
    
    if not user or not user.is_active:
        raise HTTPException(status_code=404, detail="User not found")
        
    return {
        "access_token": security.create_access_token(user.id),
        "refresh_token": security.create_refresh_token(user.id),
        "token_type": "bearer",
    }

@router.get("/me", response_model=UserRead)
async def read_user_me(
    current_user: deps.CurrentUser,
    token_payload: TokenPayload = Depends(deps.get_token_payload),
) -> Any:
    """
    Get current user.
    """
    user_data = UserRead.model_validate(current_user)
    user_data.is_impersonated = token_payload.impersonator_id is not None
    return user_data

@router.post("/change-password")
async def change_password(
    db: deps.DBDep,
    current_user: deps.CurrentUser,
    body: ChangePasswordRequest,
) -> Any:
    """
    Change password for the currently authenticated user.
    Requires current_password and new_password in request body.
    """
    current_password = body.current_password
    new_password = body.new_password

    if len(new_password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be at least 6 characters",
        )

    if not security.verify_password(current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    current_user.hashed_password = security.get_password_hash(new_password)
    db.add(current_user)
    await db.commit()

    return {"message": "Password changed successfully"}


@router.post("/logout")
async def logout() -> Any:
    """
    Logout (usually client side clears token, backend can blacklist if needed).
    """
    return {"message": "Successfully logged out"}


@router.post("/impersonate/{user_id}", response_model=Token)
async def impersonate_user(
    user_id: int,
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user)
) -> Any:
    """
    Superadmin only: Impersonate any user.
    """
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Only superadmins can impersonate")
    
    result = await db.execute(select(User).where(User.id == user_id))
    target_user = result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=404, detail="User to impersonate not found")
    
    extra = {"impersonator_id": current_user.id}
    return {
        "access_token": security.create_access_token(target_user.id, extra_claims=extra),
        "refresh_token": security.create_refresh_token(target_user.id, extra_claims=extra),
        "token_type": "bearer",
    }


@router.post("/stop-impersonation", response_model=Token)
async def stop_impersonation(
    db: deps.DBDep,
    token: Annotated[str, Depends(deps.oauth2_scheme)]
) -> Any:
    """
    Stop impersonation and return to superadmin profile.
    """
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        token_data = TokenPayload(**payload)
    except (JWTError, ValidationError):
        raise HTTPException(status_code=403, detail="Invalid token")
    
    if not token_data.impersonator_id:
        raise HTTPException(status_code=400, detail="Not currently impersonating")
    
    result = await db.execute(select(User).where(User.id == token_data.impersonator_id))
    original_user = result.scalar_one_or_none()
    if not original_user or not original_user.is_superuser:
        raise HTTPException(status_code=403, detail="Original superadmin not found")
    
    return {
        "access_token": security.create_access_token(original_user.id),
        "refresh_token": security.create_refresh_token(original_user.id),
        "token_type": "bearer",
    }
