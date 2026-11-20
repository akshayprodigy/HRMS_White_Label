"""The ONLY reader of HolidayCalendar for attendance/pay decisions.
A holiday applies to a user when:
  * mandatory (is_optional False) and location is 'All' or equals the
    employee's location (case-insensitive, trimmed), or
  * optional and the user has an APPROVED OptionalHolidayPick for it
    (picks wired in Task 6; until then optional holidays never apply)."""
from dataclasses import dataclass
from datetime import date
from typing import Iterable

from sqlalchemy import func, select

from app.models.employee import Employee
from app.models.hr import HolidayCalendar
from app.models.user import User
from app.services.time_rules import get_time_rules


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


DEFAULT_LOCATION_KEY = "holidays.default_location"


async def default_location(db) -> str:
    """The rule's fallback location for people with no location set
    (blank = no fallback)."""
    rules = await get_time_rules(db)
    return " ".join((rules.get(DEFAULT_LOCATION_KEY) or "").split())


def effective_location(
    emp_loc: str | None, user_loc: str | None, default: str,
) -> str:
    """Employee.location, else User.location, else the rule's default."""
    for cand in (emp_loc, user_loc):
        if norm_loc(cand):
            return cand  # type: ignore[return-value]
    return default


async def _approved_pick_holiday_ids(
    db, user_ids: list[int], start: date, end: date,
) -> dict[int, set[int]]:
    """user_id -> ids of optional holidays the user has an APPROVED pick for
    whose date falls in [start, end] (one query per 1000 users)."""
    from app.models.optional_holiday import OptionalHolidayPick, PickStatus
    out: dict[int, set[int]] = {}
    for i in range(0, len(user_ids), 1000):
        rows = (await db.execute(
            select(OptionalHolidayPick.user_id, OptionalHolidayPick.holiday_id)
            .join(HolidayCalendar,
                  HolidayCalendar.id == OptionalHolidayPick.holiday_id)
            .where(OptionalHolidayPick.user_id.in_(user_ids[i:i + 1000]),
                   OptionalHolidayPick.status == PickStatus.APPROVED,
                   HolidayCalendar.date >= start,
                   HolidayCalendar.date <= end)
        )).all()
        for u, h in rows:
            out.setdefault(u, set()).add(h)
    return out


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

    dflt = await default_location(db)
    locs: dict[int, str | None] = {u: dflt for u in ids}
    for i in range(0, len(ids), 1000):
        rows = (await db.execute(
            select(User.id, Employee.location, User.location)
            .outerjoin(Employee, Employee.user_id == User.id)
            .where(User.id.in_(ids[i:i + 1000]))
        )).all()
        for u, eloc, uloc in rows:
            locs[u] = effective_location(eloc, uloc, dflt)

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


async def location_counts(db) -> list[dict]:
    """Distinct non-blank effective employee locations (normalised key, first
    seen spelling as label) with employee counts. Employees with no location
    count under the rule's default location."""
    dflt = await default_location(db)
    rows = (await db.execute(
        select(Employee.location, User.location)
        .join(User, User.id == Employee.user_id)
    )).all()
    counts: dict[str, list] = {}
    for eloc, uloc in rows:
        loc = effective_location(eloc, uloc, dflt)
        key = norm_loc(loc)
        if not key:
            continue
        ent = counts.setdefault(key, [" ".join(loc.split()), 0])
        ent[1] += 1
    return [{"location": v[0], "count": v[1]}
            for _, v in sorted(counts.items())]


async def matching_employee_count(db, location: str | None) -> int:
    """How many employees a holiday at `location` would apply to."""
    key = norm_loc(location)
    if key == ALL:
        return (await db.execute(
            select(func.count(Employee.id)))).scalar_one()
    return sum(r["count"] for r in await location_counts(db)
               if norm_loc(r["location"]) == key)
