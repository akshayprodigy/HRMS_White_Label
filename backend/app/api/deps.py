from typing import Annotated, List, AsyncGenerator
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.user import User
from app.models.attendance import Attendance
from app.schemas.user import TokenPayload

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/auth/login"
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


DBDep = Annotated[AsyncSession, Depends(get_db)]


def get_token_payload(
    token: Annotated[str, Depends(oauth2_scheme)]
) -> TokenPayload:
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        token_data = TokenPayload(**payload)
        return token_data
    except (JWTError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )


async def get_current_user(
    db: DBDep, token_data: Annotated[TokenPayload, Depends(get_token_payload)]
) -> User:
    if token_data.refresh:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )
    
    # Use selectinload to ensure roles and permissions are loaded
    from sqlalchemy.orm import selectinload
    from app.models.user import Role
    
    query = select(User).where(User.id == token_data.sub).options(
        selectinload(User.roles).selectinload(Role.permissions)
    )
    result = await db.execute(query)
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Inactive user"
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def verify_attendance(
    db: DBDep,
    current_user: CurrentUser
) -> User:
    """ Gating attendance: if not marked today, block the request. """
    if current_user.is_superuser:
        return current_user

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today = now.date()

    # 24x7 rule: a night-shift punch-in is attributed to YESTERDAY's
    # work_date, so a plain captured_at >= today check locks the
    # employee out of the whole app after midnight, mid-shift. Accept:
    # a punch captured today, a row attributed to today, or
    # yesterday's cross-midnight shift that is still open / ended today.
    query = select(Attendance).where(
        and_(
            Attendance.user_id == current_user.id,
            or_(
                Attendance.captured_at >= today_start,
                Attendance.work_date == today,
                and_(
                    Attendance.work_date == today - timedelta(days=1),
                    Attendance.is_cross_midnight.is_(True),
                    or_(
                        Attendance.punch_out_time.is_(None),
                        Attendance.punch_out_time >= today_start,
                    ),
                ),
            ),
        )
    ).limit(1)
    result = await db.execute(query)
    marked = result.scalars().first()
    
    if not marked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": {
                    "code": "ATTENDANCE_REQUIRED",
                    "message": "Please mark your attendance first."
                }
            }
        )
    return current_user


def check_permissions(required_permissions: List[str]):
    async def permission_dependency(
        current_user: CurrentUser,
    ) -> User:
        user_permissions = set()
        for role in current_user.roles:
            for permission in role.permissions:
                user_permissions.add(permission.name)
        
        if not current_user.is_superuser:
            for perm in required_permissions:
                if perm not in user_permissions:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"Not enough permissions: {perm}"
                    )
        return current_user

    return permission_dependency
