from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db

router = APIRouter(prefix="/db", tags=["db"])


class DbPingResponse(BaseModel):
    status: str


@router.get("/ping", response_model=DbPingResponse)
def db_ping(db: Session = Depends(get_db)) -> DbPingResponse:
    value = db.execute(text("SELECT 1")).scalar_one()
    if value != 1:
        return DbPingResponse(status="degraded")
    return DbPingResponse(status="ok")
