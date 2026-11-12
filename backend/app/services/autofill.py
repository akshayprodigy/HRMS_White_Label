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
    off is respected);
  * no working span that day at all (roster cell OR assignment fallback):
    such people are already counted toward coverage, so candidates are only
    people who are otherwise off / unscheduled that day;
  * adding the shift does not break or worsen any work rule for that
    employee: rest vs. nearby shifts, the consecutive day/night run that
    would contain the day, and the ISO week's hours (an already-breached
    run/week rejects the candidate too).

Overlapping requirements (e.g. dept-wide and global for one template): more
specific slots are filled first, and a suggestion decrements the need of
every other same-day same-template slot the employee also satisfies.

Score (higher is better): +3 preferred template; -1 per shift already
carrying in the window (existing + suggested); -1 per night (overnight shift);
-1 per weekend (Sat/Sun) shift for weekend slots. Ties: lower user_id.
Deterministic.
"""
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import date, time, timedelta
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
    taken |= {(s.user_id, s.work_date) for s in base_spans
              if s.work_date in day_set}

    min_rest = rules.get("min_rest_hours", 0) or 0
    max_days = rules.get("max_consecutive_days", 0) or 0
    max_nights = rules.get("max_consecutive_nights", 0) or 0
    max_week = rules.get("max_weekly_hours", 0) or 0
    margin = timedelta(days=max(max_days, max_nights, 7) + 1)

    def _run_len(dates: Set[date], d: date) -> int:
        n = 1
        x = d - timedelta(days=1)
        while x in dates:
            n += 1
            x -= timedelta(days=1)
        x = d + timedelta(days=1)
        while x in dates:
            n += 1
            x += timedelta(days=1)
        return n

    def _breaks_rules(uid: int, span: ShiftSpan) -> bool:
        d = span.work_date
        near = [o for o in user_spans[uid]
                if o.work_date != d and abs(o.work_date - d) <= margin]
        if min_rest > 0:
            for o in near:
                if o.end <= span.start:
                    rest = (span.start - o.end).total_seconds() / 3600.0
                elif span.end <= o.start:
                    rest = (o.start - span.end).total_seconds() / 3600.0
                else:
                    rest = -1.0
                if rest < min_rest:
                    return True
        if max_days > 0:
            ds = {o.work_date for o in near} | {d}
            if _run_len(ds, d) > max_days:
                return True
        if max_nights > 0 and span.is_overnight:
            ds = {o.work_date for o in near if o.is_overnight} | {d}
            if _run_len(ds, d) > max_nights:
                return True
        if max_week > 0:
            wk = d - timedelta(days=d.weekday())
            total = span.hours + sum(
                o.hours for o in near
                if o.work_date - timedelta(days=o.work_date.weekday()) == wk)
            if total > max_week:
                return True
        return False

    def _tstart(tid):
        t = templates.get(tid)
        return t.start_time if t else time.min

    ordered = sorted(
        (s for s in slots if s.day in day_set and s.need > 0),
        key=lambda s: (s.day, _tstart(s.template_id), s.template_id,
                       -((s.department is not None) + (s.location is not None)),
                       s.department or "", s.location or ""))
    remaining = [s.need for s in ordered]
    suggestions: List[Suggestion] = []

    def _matches(sl: Slot, e) -> bool:
        return ((sl.department is None or e.department == sl.department)
                and (sl.location is None or e.location == sl.location))

    for idx, sl in enumerate(ordered):
        if remaining[idx] <= 0 or sl.template_id not in templates:
            continue
        proto = schedule_rules.build_spans(
            [(0, sl.day, sl.template_id)], templates)[0]
        overnight = proto.is_overnight
        weekend = _is_weekend(sl.day)

        pool = []
        for e in emps:
            uid = e.user_id
            if not _matches(sl, e):
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

        for e in ranked:
            if remaining[idx] <= 0:
                break
            uid = e.user_id
            span = replace(proto, user_id=uid)
            if _breaks_rules(uid, span):
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
            user_spans[uid].append(span)
            taken.add((uid, sl.day))
            shifts[uid] += 1
            nights[uid] += int(overnight)
            weekends[uid] += int(weekend)
            for j, o in enumerate(ordered):
                if (o.day == sl.day and o.template_id == sl.template_id
                        and _matches(o, e)):
                    remaining[j] -= 1
    unfilled = [replace(sl, need=remaining[i]) for i, sl in enumerate(ordered)
                if remaining[i] > 0]
    return suggestions, unfilled
