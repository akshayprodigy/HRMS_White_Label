from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from app.api import deps
from app.models.user import User
from app.models.notification import Notification
from app.schemas.notification import NotificationRead, NotificationUpdate

router = APIRouter()


@router.get("/", response_model=List[NotificationRead])
async def get_my_notifications(
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
    limit: int = 20,
    offset: int = 0
) -> Any:
    query = select(Notification).where(
        Notification.user_id == current_user.id
    ).order_by(Notification.created_at.desc()).limit(limit).offset(offset)
    
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/{id}/read", response_model=NotificationRead)
async def mark_notification_read(
    id: int,
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user)
) -> Any:
    notification = await db.get(Notification, id)
    if not notification or notification.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Notification not found")
        
    notification.is_read = True
    await db.commit()
    await db.refresh(notification)
    return notification


@router.post("/mark-all-read")
async def mark_all_notifications_read(
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user)
) -> Any:
    await db.execute(
        update(Notification).where(
            Notification.user_id == current_user.id
        ).values(is_read=True)
    )
    await db.commit()
    return {"message": "All notifications marked as read"}
