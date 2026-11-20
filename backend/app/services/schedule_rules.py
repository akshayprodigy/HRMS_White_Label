"""Pure scheduling work-rule + coverage checks (Roadmap v2 Phase 1A).

No DB access here: callers load cells/templates/leave/requirements and pass
plain data in. Rule values of 0 (or missing) disable that rule.
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, Iterable, List, Optional, Set, Tuple


@dataclass(frozen=True)
class ShiftSpan:
    user_id: int
    work_date: date
    template_id: int
    start: datetime
    end: datetime
    hours: float
    is_overnight: bool


@dataclass(frozen=True)
class Violation:
    user_id: int
    work_date: date
    rule: str
    message: str


@dataclass(frozen=True)
class CoverageCell:
    date: date
    shift_template_id: int
    department: Optional[str]
    location: Optional[str]
    required_min: int
    required_max: Optional[int]
    scheduled: int
    status: str  # under | ok | over


def build_spans(cells: Iterable[Tuple[int, date, int]], templates) -> List[ShiftSpan]:
    """Spans are NAIVE org-local wall-clock datetimes on purpose: every
    consumer only compares spans with each other (rest gaps, hours, sort), all
    in the same org timezone, so no UTC conversion is needed (and none would
    change the result apart from DST transitions)."""
    out: List[ShiftSpan] = []
    for uid, d, tid in cells:
        t = templates.get(tid)
        if t is None:
            continue
        start = datetime.combine(d, t.start_time)
        overnight = bool(t.is_overnight) or t.end_time <= t.start_time
        end = datetime.combine(d, t.end_time)
        if overnight:
            end += timedelta(days=1)
        hours = (end - start).total_seconds() / 3600.0 - (t.break_minutes or 0) / 60.0
        out.append(ShiftSpan(uid, d, tid, start, end, max(0.0, hours), overnight))
    return out


def _by_user(spans) -> Dict[int, List[ShiftSpan]]:
    m: Dict[int, List[ShiftSpan]] = defaultdict(list)
    for s in spans:
        m[s.user_id].append(s)
    for v in m.values():
        v.sort(key=lambda s: (s.start, s.end))
    return m


def _fmt(x: float) -> str:
    return f"{x:.1f}"


def _run_breaches(
    spans: List[ShiftSpan], limit: int, window_start: Optional[date] = None
) -> List[date]:
    """One date per run of calendar-consecutive working dates longer than
    `limit`: the first breaching day (the limit+1-th) or, when
    `window_start` is given and the run began earlier, the first breaching
    day on/after window_start (so a run continuing into the window is
    reported inside it)."""
    dates = sorted({s.work_date for s in spans})
    runs: List[List[date]] = []
    for d in dates:
        if runs and d == runs[-1][-1] + timedelta(days=1):
            runs[-1].append(d)
        else:
            runs.append([d])
    out: List[date] = []
    for run in runs:
        breach = run[limit:]
        if not breach:
            continue
        pick = breach[0]
        if window_start is not None:
            pick = next((d for d in breach if d >= window_start), breach[0])
        out.append(pick)
    return out


def check_rules(
    spans, rules: Dict[str, int], window_start: Optional[date] = None
) -> List[Violation]:
    min_rest = rules.get("min_rest_hours", 0) or 0
    max_days = rules.get("max_consecutive_days", 0) or 0
    max_nights = rules.get("max_consecutive_nights", 0) or 0
    max_week = rules.get("max_weekly_hours", 0) or 0
    out: List[Violation] = []
    for uid, lst in _by_user(spans).items():
        if min_rest > 0:
            max_end = lst[0].end
            for nxt in lst[1:]:
                rest = (nxt.start - max_end).total_seconds() / 3600.0
                max_end = max(max_end, nxt.end)
                if rest < min_rest:
                    out.append(Violation(
                        uid, nxt.work_date, "min_rest",
                        f"Only {_fmt(max(rest, 0.0))}h rest before this shift "
                        f"(min {min_rest}h)",
                    ))
        if max_days > 0:
            for d in _run_breaches(lst, max_days, window_start):
                out.append(Violation(
                    uid, d, "max_consecutive_days",
                    f"More than {max_days} consecutive working days",
                ))
        if max_nights > 0:
            nights = [s for s in lst if s.is_overnight]
            for d in _run_breaches(nights, max_nights, window_start):
                out.append(Violation(
                    uid, d, "max_consecutive_nights",
                    f"More than {max_nights} consecutive night shifts",
                ))
        if max_week > 0:
            weeks: Dict[date, List[ShiftSpan]] = defaultdict(list)
            for s in lst:
                weeks[s.work_date - timedelta(days=s.work_date.weekday())].append(s)
            for _wk, ws in sorted(weeks.items()):
                total = sum(s.hours for s in ws)
                if total > max_week:
                    out.append(Violation(
                        uid, ws[-1].work_date, "max_weekly_hours",
                        f"{_fmt(total)}h scheduled this week (max {max_week}h)",
                    ))
    out.sort(key=lambda v: (v.work_date, v.user_id, v.rule))
    return out


def check_leave_conflicts(
    spans, approved_leave_days: Set[Tuple[int, date]]
) -> List[Violation]:
    out = [
        Violation(s.user_id, s.work_date, "on_leave",
                  "Scheduled on a day of approved leave")
        for s in spans if (s.user_id, s.work_date) in approved_leave_days
    ]
    out.sort(key=lambda v: (v.work_date, v.user_id))
    return out


def compute_coverage(
    spans, requirements, emp_meta: Dict[int, Tuple[Optional[str], Optional[str]]],
    dates: Iterable[date],
) -> List[CoverageCell]:
    dates = list(dates)
    # (date, template) -> list of user ids (for per-requirement filtering)
    users: Dict[Tuple[date, int], List[int]] = defaultdict(list)
    for s in spans:
        users[(s.work_date, s.template_id)].append(s.user_id)
    out: List[CoverageCell] = []
    for r in requirements:
        for d in dates:
            if r.weekday is not None and r.weekday != d.weekday():
                continue
            n = 0
            for uid in users.get((d, r.shift_template_id), ()):
                dept, loc = emp_meta.get(uid, (None, None))
                if r.department is not None and r.department != dept:
                    continue
                if r.location is not None and r.location != loc:
                    continue
                n += 1
            if n < r.min_headcount:
                st = "under"
            elif r.max_headcount is not None and n > r.max_headcount:
                st = "over"
            else:
                st = "ok"
            out.append(CoverageCell(
                d, r.shift_template_id, r.department, r.location,
                r.min_headcount, r.max_headcount, n, st,
            ))
    return out


# ---- night-shift consent (Phase 2 Task 8) ----

NIGHT_START_H = 22
NIGHT_END_H = 6


def is_night_template(t) -> bool:
    """Overnight template, or one overlapping 22:00-06:00 wall-clock."""
    if bool(t.is_overnight) or t.end_time <= t.start_time:
        return True
    s = t.start_time.hour * 60 + t.start_time.minute
    e = t.end_time.hour * 60 + t.end_time.minute
    return e > NIGHT_START_H * 60 or s < NIGHT_END_H * 60


def consent_active(consents, d: date) -> bool:
    """`consents`: iterable of (id, consent_given, valid_from, valid_to).
    Among rows covering `d`, the latest recorded (highest id) decides, so a
    later refusal overrides an earlier grant and vice versa."""
    covering = [c for c in consents if c[2] <= d and (c[3] is None or c[3] >= d)]
    return bool(covering) and max(covering, key=lambda c: c[0])[1]


def check_night_consent(
    spans, templates, female_ids: Set[int],
    consents: Dict[int, list],
) -> List[Violation]:
    out: List[Violation] = []
    for s in spans:
        if s.user_id not in female_ids:
            continue
        t = templates.get(s.template_id)
        if t is None or not is_night_template(t):
            continue
        if not consent_active(consents.get(s.user_id, ()), s.work_date):
            out.append(Violation(
                s.user_id, s.work_date, "night_consent_missing",
                "Night-shift consent record missing"))
    return out
