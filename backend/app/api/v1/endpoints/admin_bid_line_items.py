from __future__ import annotations

from typing import Annotated, Any, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.api import deps
from app.models.bid_task import BidLineItem
from app.models.user import User
from app.schemas.bid_line_items import (
    BidLineItemCreate,
    BidLineItemRead,
    BidLineItemUpdate,
)

_JSON = "application/json"

_COMMON_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {
        "description": "Validation error",
        "content": {_JSON: {"example": {"error": {}}}},
    },
    401: {
        "description": "Unauthorized",
        "content": {_JSON: {"example": {"error": {}}}},
    },
    403: {
        "description": "Forbidden",
        "content": {_JSON: {"example": {"error": {}}}},
    },
    404: {
        "description": "Not found",
        "content": {_JSON: {"example": {"error": {}}}},
    },
}


router = APIRouter(responses=_COMMON_ERROR_RESPONSES)

ADMIN_ACCESS = "admin access"


def _err(code: str, message: str, details: dict | None = None) -> dict:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
        }
    }


@router.get(
    "/bid-line-items",
    response_model=List[BidLineItemRead],
    responses=_COMMON_ERROR_RESPONSES,
)
async def list_bid_line_items(
    db: deps.DBDep,
    current_user: Annotated[
        User, Depends(deps.check_permissions([ADMIN_ACCESS]))
    ],
) -> Any:
    res = await db.execute(select(BidLineItem).order_by(BidLineItem.title))
    return res.scalars().all()


@router.post(
    "/bid-line-items",
    response_model=BidLineItemRead,
    responses=_COMMON_ERROR_RESPONSES,
)
async def create_bid_line_item(
    *,
    db: deps.DBDep,
    item_in: BidLineItemCreate,
    current_user: Annotated[
        User, Depends(deps.check_permissions([ADMIN_ACCESS]))
    ],
) -> Any:
    title = item_in.title.strip()
    if not title:
        raise HTTPException(
            status_code=400,
            detail=_err("VALIDATION_ERROR", "Title is required"),
        )

    obj = BidLineItem(
        title=title,
        description=(item_in.description or None),
        is_active=bool(item_in.is_active),
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.patch(
    "/bid-line-items/{item_id}",
    response_model=BidLineItemRead,
    responses=_COMMON_ERROR_RESPONSES,
)
async def update_bid_line_item(
    *,
    db: deps.DBDep,
    item_id: int,
    item_in: BidLineItemUpdate,
    current_user: Annotated[
        User, Depends(deps.check_permissions([ADMIN_ACCESS]))
    ],
) -> Any:
    obj = await db.get(BidLineItem, item_id)
    if not obj:
        raise HTTPException(
            status_code=404,
            detail=_err(
                "BID_LINE_ITEM_NOT_FOUND",
                "Bid line item not found",
                {"item_id": item_id},
            ),
        )

    data = item_in.model_dump(exclude_unset=True)
    if "title" in data and data["title"] is not None:
        data["title"] = data["title"].strip()

    for field, value in data.items():
        setattr(obj, field, value)

    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete(
    "/bid-line-items/{item_id}",
    status_code=status.HTTP_200_OK,
    responses=_COMMON_ERROR_RESPONSES,
)
async def delete_bid_line_item(
    *,
    db: deps.DBDep,
    item_id: int,
    current_user: Annotated[
        User, Depends(deps.check_permissions([ADMIN_ACCESS]))
    ],
) -> dict[str, bool]:
    obj = await db.get(BidLineItem, item_id)
    if not obj:
        raise HTTPException(
            status_code=404,
            detail=_err(
                "BID_LINE_ITEM_NOT_FOUND",
                "Bid line item not found",
                {"item_id": item_id},
            ),
        )

    await db.delete(obj)
    await db.commit()
    return {"ok": True}
