"""The ONLY reader of HolidayCalendar for attendance/pay decisions.
A holiday applies to a user when:
  * mandatory (is_optional False) and location is 'All' or equals the
    employee's location (case-insensitive, trimmed), or
  * optional and the user has an APPROVED OptionalHolidayPick for it
    (picks wired in Task 6; until then optional holidays never apply)."""
from dataclasses import dataclass
from datetime import date
from typing import Iterable

from sqlalchemy import select

from app.models.employee import Employee
from app.models.hr import HolidayCalendar


@dataclass(frozen=True)
class HolidayInfo:
    holiday_id: int
    name: str
    is_optional: bool


ALL = "all"


def norm_loc(loc: str | None) -> str:
    return " ".join((loc or "").split()).casefold()


def applies(holiday_location: str | None, employee_location: str | None) -> bool:
    h = norm_loc(holiday_location)
    return h == ALL or (h != "" and h == norm_loc(employee_location))


async def _approved_pick_holiday_ids(
    db, user_ids: list[int], start: date, end: date,
) -> dict[int, set[int]]:
    """HOOK (Phase 6A Task 6): user_id -> ids of optional holidays the user
    has an APPROVED pick for. Until picks exist, optional holidays never
    apply, so this returns an empty mapping."""
    return {}


async def holidays_for(
    db, user_ids: Iterable[int], start: date, end: date,
) -> dict[int, dict[date, HolidayInfo]]:
    """user_id -> {date: HolidayInfo} for [start, end]. Every requested user
    id is a key. One query each for holidays, employee locations, picks.
    Users with no Employee row get only 'All' holidays. A mandatory holiday
    wins over an optional one on the same date."""
    ids = list(dict.fromkeys(user_ids))
    out: dict[int, dict[date, HolidayInfo]] = {u: {} for u in ids}
    if not ids or end < start:
        return out

    hols = (await db.execute(
        select(HolidayCalendar).where(
            HolidayCalendar.date >= start, HolidayCalendar.date <= end,
        ).order_by(HolidayCalendar.id)
    )).scalars().all()
    if not hols:
        return out

    locs: dict[int, str | None] = {}
    for i in range(0, len(ids), 1000):
        rows = (await db.execute(
            select(Employee.user_id, Employee.location).where(
                Employee.user_id.in_(ids[i:i + 1000]))
        )).all()
        locs.update({u: loc for u, loc in rows})

    picks = await _approved_pick_holiday_ids(db, ids, start, end)

    for u in ids:
        mine = out[u]
        picked = picks.get(u, set())
        for h in hols:
            if h.is_optional:
                if h.id not in picked:
                    continue
            elif not applies(h.location, locs.get(u)):
                continue
            cur = mine.get(h.date)
            if cur is None or (cur.is_optional and not h.is_optional):
                mine[h.date] = HolidayInfo(h.id, h.name, bool(h.is_optional))
    return out


async def is_holiday(db, user_id: int, d: date) -> HolidayInfo | None:
    return (await holidays_for(db, [user_id], d, d)).get(user_id, {}).get(d)
