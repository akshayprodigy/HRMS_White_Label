from __future__ import annotations

from typing import Annotated, Any, List

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.api import deps
from app.models.bid_task import BidLineItem
from app.models.user import User
from app.schemas.bid_line_items import BidLineItemRead

router = APIRouter()

BID_TASK_READ = "bd bid task read"


@router.get("/bid-line-items", response_model=List[BidLineItemRead])
async def list_active_bid_line_items(
    db: deps.DBDep,
    current_user: Annotated[
        User, Depends(deps.check_permissions([BID_TASK_READ]))
    ],
) -> Any:
    res = await db.execute(
        select(BidLineItem)
        .where(BidLineItem.is_active.is_(True))
        .order_by(BidLineItem.title)
    )
    return res.scalars().all()
