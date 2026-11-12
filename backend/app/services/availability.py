"""Availability expansion: recurring/one-off rules -> per (user, day) facts."""
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, Iterable, Optional, Set, Tuple

from sqlalchemy import select

from app.models.availability import AvailabilityKind, EmployeeAvailability


@dataclass
class AvailabilityDay:
    unavailable_all_day: bool = False
    unavailable_templates: Set[int] = field(default_factory=set)
    preferred_templates: Set[int] = field(default_factory=set)

    def blocks(self, template_id: Optional[int]) -> bool:
        return self.unavailable_all_day or (
            template_id is not None
            and template_id in self.unavailable_templates)


def expand_availability(
    rules, start: date, end: date
) -> Dict[Tuple[int, date], AvailabilityDay]:
    """Only (user, day) pairs with at least one applicable rule appear."""
    out: Dict[Tuple[int, date], AvailabilityDay] = {}
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    for r in rules:
        if r.specific_date is not None:
            applicable = [r.specific_date] if start <= r.specific_date <= end else []
        else:
            applicable = [
                d for d in days
                if d.weekday() == r.weekday
                and (r.valid_from is None or d >= r.valid_from)
                and (r.valid_to is None or d <= r.valid_to)
            ]
        for d in applicable:
            day = out.setdefault((r.user_id, d), AvailabilityDay())
            if r.kind == AvailabilityKind.UNAVAILABLE.value:
                if r.shift_template_id is None:
                    day.unavailable_all_day = True
                else:
                    day.unavailable_templates.add(r.shift_template_id)
            elif r.kind == AvailabilityKind.PREFERRED.value:
                if r.shift_template_id is not None:
                    day.preferred_templates.add(r.shift_template_id)
    return out


async def availability_by_day(
    db, user_ids: Iterable[int], start: date, end: date
) -> Dict[Tuple[int, date], AvailabilityDay]:
    ids = list(user_ids)
    if not ids:
        return {}
    rules = (await db.execute(
        select(EmployeeAvailability).where(
            EmployeeAvailability.user_id.in_(ids))
    )).scalars().all()
    return expand_availability(rules, start, end)
