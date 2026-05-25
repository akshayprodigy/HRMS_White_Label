from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class BidLineItemBase(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    is_active: bool = True


class BidLineItemCreate(BidLineItemBase):
    pass


class BidLineItemUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    is_active: Optional[bool] = None


class BidLineItemRead(BidLineItemBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
