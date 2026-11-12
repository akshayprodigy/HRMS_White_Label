"""Auto-fill suggestions (Roadmap v2 Phase 1B, Task 8). Pure, no DB.

Given coverage slots (with the headcount still missing), the candidate
employees and everything that constrains them, propose who should work what.
Nothing is written; the planner shows suggestions and the scheduler applies
the ones they accept as DRAFT entries.

Candidate rules for (employee, day, template):
  * department/location match the slot (None = any);
  * no roster cell that day (draft/published, incl. explicit week-off) —
    existing cells are never overwritten;
  * not on approved leave, not marked unavailable for the day/template;
  * the day is not a weekly-off of their shift assignment (mandatory weekly
    off is respected). An employee whose assignment is a WORKING day but has
    no roster cell remains a candidate: a suggestion replaces the assignment
    for that day, and the scheduler can untick it;
  * adding the shift creates no NEW work-rule violation for that employee
    (min rest, consecutive days/nights, weekly hours).

Score (higher is better): +3 preferred template; -1 per shift already
carrying in the window (existing + suggested); -1 per night (overnight shift);
-1 per weekend (Sat/Sun) shift for weekend slots. Ties: lower user_id.
Deterministic.
"""
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import date, time
from typing import Dict, Iterable, List, Optional, Set, Tuple

from app.services import schedule_rules
from app.services.schedule_rules import ShiftSpan

PREFERRED_BONUS = 3.0


@dataclass(frozen=True)
class Slot:
    day: date
    template_id: int
    department: Optional[str]
    location: Optional[str]
    need: int


@dataclass(frozen=True)
class Suggestion:
    user_id: int
    day: date
    template_id: int
    score: float
    reasons: Tuple[str, ...]


def _is_weekend(d: date) -> bool:
    return d.weekday() >= 5


def suggest(
    *,
    employees,
    days: Iterable[date],
    templates,
    slots: Iterable[Slot],
    existing_cells: Dict[Tuple[int, date], tuple],
    leave_days: Set[Tuple[int, date]],
    availability,
    rules: Dict[str, int],
    window_start: date,
    base_spans: Iterable[ShiftSpan] = (),
    weekly_off_days: Set[Tuple[int, date]] = frozenset(),
) -> Tuple[List[Suggestion], List[Slot]]:
    """`base_spans` are the employees' current working spans (roster cells
    plus assignment fallbacks, incl. a lookback/lookahead margin) used for rule
    checks and load counting. `existing_cells` maps (user, day) ->
    (template_id|None, is_week_off). `availability` maps (user, day) ->
    AvailabilityDay."""
    days = sorted(set(days))
    day_set = set(days)
    end = days[-1] if days else window_start
    emps = sorted(employees, key=lambda e: e.user_id)

    user_spans: Dict[int, List[ShiftSpan]] = defaultdict(list)
    shifts: Dict[int, int] = defaultdict(int)
    nights: Dict[int, int] = defaultdict(int)
    weekends: Dict[int, int] = defaultdict(int)
    for s in base_spans:
        user_spans[s.user_id].append(s)
        if window_start <= s.work_date <= end:
            shifts[s.user_id] += 1
            nights[s.user_id] += int(s.is_overnight)
            weekends[s.user_id] += int(_is_weekend(s.work_date))

    taken: Set[Tuple[int, date]] = set(existing_cells)

    ordered = sorted((s for s in slots if s.day in day_set and s.need > 0),
                     key=lambda s: (s.day, templates[s.template_id].start_time
                                    if s.template_id in templates else time.min,
                                    s.template_id, s.department or "",
                                    s.location or ""))
    suggestions: List[Suggestion] = []
    unfilled: List[Slot] = []

    for sl in ordered:
        tpl = templates.get(sl.template_id)
        if tpl is None:
            unfilled.append(sl)
            continue
        new_span_proto = schedule_rules.build_spans(
            [(0, sl.day, sl.template_id)], templates)[0]
        overnight = new_span_proto.is_overnight
        weekend = _is_weekend(sl.day)

        pool = []
        for e in emps:
            uid = e.user_id
            if sl.department is not None and e.department != sl.department:
                continue
            if sl.location is not None and e.location != sl.location:
                continue
            key = (uid, sl.day)
            if key in taken or key in leave_days or key in weekly_off_days:
                continue
            av = availability.get(key)
            if av is not None and av.blocks(sl.template_id):
                continue
            pool.append(e)

        def score(uid: int) -> float:
            av = availability.get((uid, sl.day))
            sc = -float(shifts[uid])
            if av is not None and sl.template_id in av.preferred_templates:
                sc += PREFERRED_BONUS
            if overnight:
                sc -= nights[uid]
            if weekend:
                sc -= weekends[uid]
            return sc

        ranked = sorted(pool, key=lambda e: (-score(e.user_id), e.user_id))
        min_shifts = min((shifts[e.user_id] for e in pool), default=0)
        min_nights = min((nights[e.user_id] for e in pool), default=0)
        min_wk = min((weekends[e.user_id] for e in pool), default=0)

        filled = 0
        for e in ranked:
            if filled >= sl.need:
                break
            uid = e.user_id
            cur = [s for s in user_spans[uid] if s.work_date != sl.day]
            before = len(schedule_rules.check_rules(cur, rules))
            span = replace(new_span_proto, user_id=uid)
            after = len(schedule_rules.check_rules(cur + [span], rules))
            if after > before:
                continue
            av = availability.get((uid, sl.day))
            reasons: List[str] = []
            if av is not None and sl.template_id in av.preferred_templates:
                reasons.append("preferred shift")
            if overnight and nights[uid] == min_nights:
                reasons.append("fewest nights")
            if weekend and weekends[uid] == min_wk:
                reasons.append("fewest weekends")
            if shifts[uid] == min_shifts:
                reasons.append("lightest load")
            if not reasons:
                reasons.append("available")
            suggestions.append(Suggestion(
                uid, sl.day, sl.template_id, score(uid), tuple(reasons)))
            user_spans[uid] = cur + [span]
            taken.add((uid, sl.day))
            shifts[uid] += 1
            nights[uid] += int(overnight)
            weekends[uid] += int(weekend)
            filled += 1
        if filled < sl.need:
            unfilled.append(replace(sl, need=sl.need - filled))
    return suggestions, unfilled
