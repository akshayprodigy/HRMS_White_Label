from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class FunctionalAreaBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    code: str = Field(..., min_length=1, max_length=20)
    is_active: bool = True


class FunctionalAreaCreate(FunctionalAreaBase):
    pass


class FunctionalAreaUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    code: Optional[str] = Field(default=None, min_length=1, max_length=20)
    is_active: Optional[bool] = None


class FunctionalAreaRead(FunctionalAreaBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
