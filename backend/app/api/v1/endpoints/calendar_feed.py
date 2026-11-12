"""Personal ICS calendar feed (Roadmap v2 Phase 1B, Task 5).

`router` (token management) is mounted under /roster with auth + attendance
gating. `public_router` is mounted at /calendar with NO dependencies: the
secret token in the URL is the credential.
"""
import hashlib
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import delete, select, update

from app.api import deps
from app.api.v1.endpoints.roster_common import commit_or_409, guard_conflicts
from app.core.config import settings
from app.models.calendar_feed import CalendarFeedToken
from app.models.roster import RosterEntry, RosterStatus
from app.models.shift import ShiftTemplate
from app.models.user import User
from app.services.ics import IcsEvent, render_ics

logger = logging.getLogger(__name__)

router = APIRouter()
public_router = APIRouter()

_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{32,64}$")
PAST_DAYS = 30
FUTURE_DAYS = 90
LAST_USED_THROTTLE = timedelta(minutes=5)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@router.get("/my/calendar-feed")
async def feed_status(
    db: deps.DBDep, current_user: User = Depends(deps.get_current_user),
) -> Any:
    row = (await db.execute(select(CalendarFeedToken).where(
        CalendarFeedToken.user_id == current_user.id))).scalar_one_or_none()
    return {"active": row is not None,
            "created_at": row.created_at if row else None}


@router.post("/my/calendar-feed")
@guard_conflicts
async def rotate_feed(
    request: Request, response: Response, *, db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    token = secrets.token_urlsafe(32)
    await db.execute(delete(CalendarFeedToken).where(
        CalendarFeedToken.user_id == current_user.id))
    db.add(CalendarFeedToken(user_id=current_user.id, token_hash=_hash(token)))
    await commit_or_409(db)
    response.headers["Cache-Control"] = "no-store"
    base = (settings.PUBLIC_BASE_URL or str(request.base_url)).rstrip("/")
    return {"url": f"{base}{settings.API_V1_STR}/calendar/{token}.ics"}


@router.delete("/my/calendar-feed", status_code=204)
async def delete_feed(
    db: deps.DBDep, current_user: User = Depends(deps.get_current_user),
) -> Response:
    await db.execute(delete(CalendarFeedToken).where(
        CalendarFeedToken.user_id == current_user.id))
    await db.commit()
    return Response(status_code=204)


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Calendar feed not found")


@public_router.get("/{token}.ics")
async def public_feed(token: str, db: deps.DBDep) -> Response:
    if not _TOKEN_RE.match(token):
        raise _not_found()
    feed = (await db.execute(select(CalendarFeedToken).where(
        CalendarFeedToken.token_hash == _hash(token)))).scalar_one_or_none()
    if feed is None:
        raise _not_found()
    user = await db.get(User, feed.user_id)
    if user is None or not user.is_active:
        raise _not_found()

    now = datetime.now(timezone.utc)
    today = now.date()
    rows = (await db.execute(
        select(RosterEntry, ShiftTemplate)
        .join(ShiftTemplate, ShiftTemplate.id == RosterEntry.shift_template_id)
        .where(
            RosterEntry.employee_id == user.id,
            RosterEntry.status == RosterStatus.PUBLISHED,
            RosterEntry.is_week_off.is_(False),
            RosterEntry.work_date >= today - timedelta(days=PAST_DAYS),
            RosterEntry.work_date <= today + timedelta(days=FUTURE_DAYS),
        ).order_by(RosterEntry.work_date, RosterEntry.id))).all()
    events = []
    for entry, tpl in rows:
        start = datetime.combine(entry.work_date, tpl.start_time)
        end = datetime.combine(entry.work_date, tpl.end_time)
        if tpl.is_overnight or end <= start:
            end += timedelta(days=1)
        desc = f"{tpl.start_time:%H:%M}-{tpl.end_time:%H:%M}"
        if entry.note:
            desc += f" | {entry.note}"
        events.append(IcsEvent(
            uid=f"roster-{entry.id}@hrms", start=start, end=end,
            summary=tpl.name, description=desc))
    body = render_ics(events, cal_name="My shifts", now=now)

    last = feed.last_used_at
    if last is not None and last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    if last is None or now - last >= LAST_USED_THROTTLE:
        try:  # best-effort; never fail the feed
            await db.execute(update(CalendarFeedToken)
                             .where(CalendarFeedToken.id == feed.id)
                             .values(last_used_at=now))
            await db.commit()
        except Exception:
            await db.rollback()
            logger.warning("calendar feed last_used_at update failed",
                           exc_info=True)

    return Response(
        content=body.encode("utf-8"),
        media_type="text/calendar; charset=utf-8",
        headers={"Cache-Control": "private, max-age=900"})
