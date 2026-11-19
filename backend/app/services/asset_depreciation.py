"""Straight-line depreciation. Pure, integer paise only, no DB."""
from dataclasses import dataclass
from datetime import date
from typing import Optional

DEFAULT_LIFE_MONTHS = 36


@dataclass(frozen=True)
class BookValue:
    cost_paise: int
    salvage_paise: int
    life_months: int
    months_elapsed: int
    accumulated_paise: int
    book_value_paise: int
    fully_depreciated: bool


def months_between(start: date, on: date) -> int:
    """Whole months elapsed; a month counts once its day-of-month is reached."""
    if on < start:
        return 0
    m = (on.year - start.year) * 12 + (on.month - start.month)
    if on.day < start.day:
        m -= 1
    return max(m, 0)


def book_value(*, cost_paise: Optional[int], salvage_paise: int,
               purchase_date: Optional[date], life_months: Optional[int],
               on: date) -> Optional[BookValue]:
    if cost_paise is None or purchase_date is None or cost_paise < 0:
        return None
    life = life_months if life_months and life_months > 0 else DEFAULT_LIFE_MONTHS
    salvage = min(max(salvage_paise or 0, 0), cost_paise)
    elapsed = months_between(purchase_date, on)
    depreciable = cost_paise - salvage
    acc = depreciable if elapsed >= life else (depreciable * elapsed) // life
    return BookValue(cost_paise, salvage, life, elapsed, acc,
                     cost_paise - acc, elapsed >= life)
