from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.services.org_time import (
    local_today_for, org_tz, tz_name, utc_offset_minutes,
)

router = APIRouter()


@router.get("/org-time")
async def org_time(db: AsyncSession = Depends(deps.get_db)) -> Any:
    """Public: org timezone so clients can render the org's 'today'."""
    tz = await org_tz(db)
    return {
        "timezone": tz_name(tz),
        "utc_offset_minutes": utc_offset_minutes(tz),
        "today": local_today_for(tz).isoformat(),
    }
