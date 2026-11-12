"""Coverage gaps (Roadmap v2 Phase 2, Task 3).

A gap is a shift that needs a replacement. `open_gap` is idempotent and is
called by the triggers (no-show job, approved give-away without an open shift,
emergency leave, manual). `suggest_replacements` ranks candidates; ranking is
pure (`rank_candidates`) so it is unit-testable.

Callers hold the request transaction; functions flush but never commit.

Ranking (deterministic): a candidate must be (1) eligible exactly as for an
open shift (`open_shifts.eligibility_matrix`), (2) not breaking/worsening any
work rule (min rest / consecutive days or nights / weekly hours; same
before/after violation diff as claim warnings), (3) under the monthly OT cap
of the applicable overtime rule (approved/pending OT minutes this month
< cap; no cap = unlimited). Survivors are ordered by fewest scheduled hours
in the gap's calendar month (score = -hours), then lowest user id.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from app.api.v1.endpoints.roster_common import lock_user_rows
from app.models.coverage_gap import CoverageGap, GapSource, GapStatus
from app.models.department import Department
from app.models.employee import Employee, EmployeeStatus
from app.models.open_shift import OpenShift, OpenShiftStatus
from app.models.overtime import OvertimeEntry, OvertimeRule, OvertimeScope
from app.models.shift import ShiftTemplate
from app.models.user import User
from app.services import open_shifts as os_svc
from app.services import roster as roster_svc
from app.services import schedule_rules
from app.services import swaps as swap_svc
from app.services.effective_shift import effective_shifts_for_range
from app.services.time_rules import get_schedule_rules

RTYPE = "coverage_gap"
MAX_SUGGESTIONS = 10
OT_COUNTED = ("pending", "approved", "auto_approved")


# ------------------------------- opening -------------------------------

async def _scheduler_ids(db, gap: CoverageGap) -> set:
    if gap.absent_user_id:
        return await roster_svc.schedule_approver_ids(db, {gap.absent_user_id})
    ids: set = set()
    if gap.department:
        for h in (await db.execute(
            select(Department.head_user_id, Department.deputy_head_user_id)
            .where(Department.name == gap.department))).all():
            ids |= {x for x in h if x}
        if ids:
            ids = set((await db.execute(select(User.id).where(
                User.id.in_(ids), User.is_active.is_(True)))).scalars().all())
    if ids:
        return ids
    return await roster_svc.schedule_approver_ids(db, set())


def _key_stmt(absent_user_id, work_date, source):
    return select(CoverageGap).where(
        CoverageGap.absent_user_id == absent_user_id,
        CoverageGap.work_date == work_date, CoverageGap.source == source)


async def _find_committed(db, absent_user_id, work_date, source):
    """The gap for the idempotency key, including one committed by a
    concurrent transaction AFTER this transaction's snapshot. A FOR UPDATE
    read of such a row fails on MariaDB with 1020 and rolls the whole
    transaction back, so the (already-committed) row is read through a short
    separate session and attached without reloading; callers only need
    id/status, and a later commit makes this session see it normally."""
    from app.db.session import SessionLocal
    stmt = _key_stmt(absent_user_id, work_date, source)
    async with SessionLocal() as other:
        row = (await other.execute(stmt)).scalars().first()
        if row is None:
            return None
        other.expunge(row)
    return await db.merge(row, load=False)


async def open_gap(
    db, *, work_date: date, shift_template_id: int,
    department: Optional[str] = None, location: Optional[str] = None,
    absent_user_id: Optional[int] = None, source: str,
    source_id: Optional[int] = None, note: Optional[str] = None,
    notify: bool = True, notify_exclude: Iterable[int] = (),
) -> CoverageGap:
    """Create the gap and (when `notify`) notify the schedulers in-app,
    except `notify_exclude` (e.g. the approver who triggered it).

    Idempotent per (absent_user_id, work_date, source): an existing row is
    returned AS IS, whatever its status (a dismissed/filled gap is not
    reopened by a repeat trigger). Race-safe: concurrent openers are
    serialized on the absentee's user row (lock_user_rows; a FOR UPDATE on
    the missing key would take gap locks and deadlock concurrent inserters),
    and the unique key is the backstop: a duplicate insert falls back to
    `_find_committed`, which sees the winner even when the REPEATABLE READ
    snapshot predates its commit."""
    if source not in GapSource.ALL:
        raise ValueError(f"unknown gap source {source!r}")
    if absent_user_id is not None:
        await lock_user_rows(db, [absent_user_id])
        existing = (await db.execute(_key_stmt(
            absent_user_id, work_date, source).execution_options(
                populate_existing=True))).scalars().first()
        if existing is not None:
            return existing
        if department is None or location is None:
            emp = (await db.execute(select(Employee).where(
                Employee.user_id == absent_user_id))).scalars().first()
            if emp is not None:
                department = department or emp.department
                location = location or emp.location
    gap = CoverageGap(
        work_date=work_date, shift_template_id=shift_template_id,
        department=department or None, location=location or None,
        absent_user_id=absent_user_id, source=source, source_id=source_id,
        status=GapStatus.OPEN, note=(note or None))
    try:
        async with db.begin_nested():
            db.add(gap)
            await db.flush()
    except IntegrityError:  # lost the race to an identical gap
        again = await _find_committed(db, absent_user_id, work_date, source)
        if again is None:
            raise
        return again
    if not notify:
        return gap
    tpl = await db.get(ShiftTemplate, shift_template_id)
    who = None
    if absent_user_id:
        u = await db.get(User, absent_user_id)
        who = (u.full_name or u.email) if u else None
    label = (f"{tpl.name} {tpl.start_time.strftime('%H:%M')}-"
             f"{tpl.end_time.strftime('%H:%M')}" if tpl else "A shift")
    await roster_svc.notify_many(db, [
        (uid, "Coverage gap needs a replacement",
         f"{label} on {work_date.isoformat()}"
         + (f" ({who} absent)" if who else "") + " needs a replacement",
         RTYPE, str(gap.id))
        for uid in sorted((await _scheduler_ids(db, gap)) - set(notify_exclude))])
    return gap


# --------------------------- open shift link hooks ---------------------------

async def mark_filled_by_open_shift(db, shift: OpenShift, user_id: int) -> None:
    """The linked open shift filled: the gap is filled. Caller holds the
    open shift lock (lock order: open shift, then gap)."""
    for g in (await db.execute(select(CoverageGap).where(
            CoverageGap.open_shift_id == shift.id,
            CoverageGap.status == GapStatus.OPEN).with_for_update()
            .execution_options(populate_existing=True))).scalars().all():
        g.status = GapStatus.FILLED
        g.filled_by_user_id = user_id
        g.resolved_at = datetime.now(timezone.utc)


async def release_open_shift(db, shift: OpenShift) -> None:
    """The linked open shift was cancelled: the gap can be re-broadcast."""
    for g in (await db.execute(select(CoverageGap).where(
            CoverageGap.open_shift_id == shift.id,
            CoverageGap.status == GapStatus.OPEN).with_for_update()
            .execution_options(populate_existing=True))).scalars().all():
        g.open_shift_id = None


async def dismiss_noshow_gap_if_present(
    db, user_id: int, work_date: date, actor_id: int,
    note: str = "Marked present by supervisor",
) -> int:
    """The absentee was marked present: dismiss their OPEN no-show gap for
    that date (cancelling a linked open shift). Lock order: open shift, then
    gap. Returns the number of gaps dismissed. Flushes, never commits."""
    from app.api.v1.endpoints.roster_common import lock_row
    from app.services import open_shifts as os_svc
    peek = (await db.execute(select(CoverageGap).where(
        CoverageGap.absent_user_id == user_id,
        CoverageGap.work_date == work_date,
        CoverageGap.source == GapSource.NO_SHOW,
        CoverageGap.status == GapStatus.OPEN))).scalars().first()
    if peek is None:
        return 0
    shift = None
    if peek.open_shift_id:
        shift = await lock_row(
            db, select(OpenShift).where(OpenShift.id == peek.open_shift_id),
            "Coverage gap changed concurrently; retry")
    gap = await lock_row(
        db, select(CoverageGap).where(
            CoverageGap.id == peek.id, CoverageGap.status == GapStatus.OPEN),
        "Coverage gap changed concurrently; retry")
    if gap is None:
        return 0
    if gap.open_shift_id != (shift.id if shift else None):
        # The link moved between peek and lock: lock and cancel the real one.
        shift = (await lock_row(
            db, select(OpenShift).where(OpenShift.id == gap.open_shift_id),
            "Coverage gap changed concurrently; retry")
            if gap.open_shift_id else None)
    if shift is not None and shift.status == OpenShiftStatus.OPEN:
        shift.status = OpenShiftStatus.CANCELLED
        await os_svc.reject_pending(
            db, shift, actor_id, note, title="Open shift cancelled")
    gap.status = GapStatus.DISMISSED
    gap.note = note[:255]
    gap.resolved_by_id = actor_id
    gap.resolved_at = datetime.now(timezone.utc)
    await db.flush()
    return 1


# ------------------------------- ranking -------------------------------

@dataclass(frozen=True)
class Candidate:
    user_id: int
    eligible_reason: Optional[str] = None      # None = eligible
    rule_violations: Tuple[str, ...] = ()      # newly created by this shift
    month_hours: float = 0.0
    ot_used_minutes: int = 0
    ot_cap_minutes: Optional[int] = None       # None = no cap


@dataclass(frozen=True)
class Suggestion:
    user_id: int
    score: float
    reasons: Tuple[str, ...]
    month_hours: float
    ot_headroom_minutes: Optional[int]


def _h(x: float) -> str:
    return f"{x:.1f}".rstrip("0").rstrip(".")


def rank_candidates(
    cands: Iterable[Candidate], limit: int = MAX_SUGGESTIONS,
    exclude: Iterable[int] = (),
) -> List[Suggestion]:
    skip = set(exclude)
    pool: List[Candidate] = []
    for c in cands:
        if c.user_id in skip or c.eligible_reason is not None:
            continue
        if c.rule_violations:
            continue
        if (c.ot_cap_minutes is not None
                and c.ot_used_minutes >= c.ot_cap_minutes):
            continue
        pool.append(c)
    pool.sort(key=lambda c: (c.month_hours, c.user_id))
    least = pool[0].month_hours if pool else 0.0
    out: List[Suggestion] = []
    for c in pool[:max(0, limit)]:
        reasons = ["Eligible: free, not on leave, within scope"]
        if c.month_hours == least:
            reasons.append(
                f"Lightest load this month ({_h(c.month_hours)}h scheduled)")
        else:
            reasons.append(f"{_h(c.month_hours)}h scheduled this month")
        reasons.append("No rest / consecutive-day / weekly-hours breach")
        headroom = None
        if c.ot_cap_minutes is not None:
            headroom = c.ot_cap_minutes - c.ot_used_minutes
            reasons.append(
                f"{_h(headroom / 60)}h overtime headroom this month")
        out.append(Suggestion(
            c.user_id, round(-c.month_hours, 2), tuple(reasons),
            round(c.month_hours, 2), headroom))
    return out


def transient_shift(gap: CoverageGap, created_by_id: Optional[int] = None) -> OpenShift:
    """An unsaved OpenShift mirroring the gap so the open-shift eligibility
    rules can be reused verbatim (never added to the session)."""
    return OpenShift(
        id=gap.id, work_date=gap.work_date,
        shift_template_id=gap.shift_template_id, department=gap.department,
        location=gap.location, slots=1, filled=0,
        status=OpenShiftStatus.OPEN, created_by_id=created_by_id,
        excluded_user_id=None)


async def _candidate_pool(db, gap: CoverageGap) -> List[int]:
    q = select(Employee.user_id).join(User, User.id == Employee.user_id).where(
        Employee.status == EmployeeStatus.ACTIVE,
        Employee.user_id.is_not(None), User.is_active.is_(True))
    if gap.department:
        q = q.where(Employee.department == gap.department)
    if gap.location:
        q = q.where(Employee.location == gap.location)
    ids = set((await db.execute(q)).scalars().all())
    ids.discard(gap.absent_user_id)
    return sorted(ids)


async def _ot_caps(db, tpl_id: int) -> Optional[int]:
    """Tightest monthly OT cap among active rules that apply to the shift."""
    caps = (await db.execute(select(OvertimeRule.monthly_ot_cap_minutes).where(
        OvertimeRule.is_active.is_(True),
        OvertimeRule.monthly_ot_cap_minutes.is_not(None),
        or_(OvertimeRule.scope == OvertimeScope.ORG_DEFAULT,
            OvertimeRule.shift_template_id == tpl_id)))).scalars().all()
    return min(caps) if caps else None


async def ot_usage(db, user_ids, tpl_id: int, d: date):
    """(monthly cap minutes or None, {user_id: OT minutes used in d's month})."""
    cap = await _ot_caps(db, tpl_id)
    if cap is None:
        return None, {}
    m0 = d.replace(day=1)
    m1 = d.replace(day=calendar.monthrange(d.year, d.month)[1])
    return cap, {u: int(m or 0) for u, m in (await db.execute(
        select(OvertimeEntry.user_id,
               func.coalesce(func.sum(OvertimeEntry.ot_minutes), 0))
        .where(OvertimeEntry.user_id.in_(list(user_ids)),
               OvertimeEntry.work_date >= m0, OvertimeEntry.work_date <= m1,
               OvertimeEntry.status.in_(OT_COUNTED))
        .group_by(OvertimeEntry.user_id))).all()}


async def suggest_replacements(
    db, gap: CoverageGap, actor: Optional[User] = None,
    limit: int = MAX_SUGGESTIONS,
) -> List[dict]:
    """Ranked replacements (<= limit, hard cap 10). With `actor`, candidates
    are limited to people the actor may publish for. Returns dicts: user_id,
    name, department, score, reasons, month_hours, ot_headroom_minutes."""
    limit = min(limit, MAX_SUGGESTIONS)
    pool = await _candidate_pool(db, gap)
    if actor is not None:
        pool = sorted(await roster_svc.publishable_subset(db, actor, pool))
    if not pool or gap.status != GapStatus.OPEN:
        return []
    d = gap.work_date
    shift = transient_shift(gap)
    elig = await os_svc.eligibility_matrix(
        db, [(shift, u) for u in pool], approver=actor)
    ok = [u for u in pool if elig[(shift.id, u)] is None]
    if not ok:
        return []
    tpl = await db.get(ShiftTemplate, gap.shift_template_id)
    templates = {t.id: t for t in (await db.execute(
        select(ShiftTemplate))).scalars().all()}
    rules = await get_schedule_rules(db)
    m0 = d.replace(day=1)
    m1 = d.replace(day=calendar.monthrange(d.year, d.month)[1])
    lo = min(m0, d - timedelta(days=7))
    hi = max(m1, d + timedelta(days=7))
    eff = await effective_shifts_for_range(db, ok, lo, hi)
    days = [lo + timedelta(days=i) for i in range((hi - lo).days + 1)]
    cap, used = await ot_usage(db, ok, gap.shift_template_id, d)
    cands: List[Candidate] = []
    for u in ok:
        cur = {x: swap_svc.cell_of(eff[(u, x)]) for x in days}
        month = [(u, x, c[0]) for x, c in cur.items()
                 if m0 <= x <= m1 and swap_svc.is_working(c)]
        hours = sum(s.hours for s in schedule_rules.build_spans(month, templates))
        cands.append(Candidate(
            u, None, tuple(_new_violations(u, cur, gap, templates, rules)),
            hours, used.get(u, 0), cap))
    ranked = rank_candidates(cands, limit)
    info = {r[0]: r for r in (await db.execute(
        select(User.id, User.full_name, User.email, Employee.department)
        .join(Employee, Employee.user_id == User.id)
        .where(User.id.in_([s.user_id for s in ranked]))
        )).all()} if ranked else {}
    return [{
        "user_id": s.user_id,
        "name": (info[s.user_id][1] or info[s.user_id][2]) if s.user_id in info else str(s.user_id),
        "department": info[s.user_id][3] if s.user_id in info else None,
        "score": s.score, "reasons": list(s.reasons),
        "month_hours": s.month_hours,
        "ot_headroom_minutes": s.ot_headroom_minutes,
    } for s in ranked]


def _new_violations(uid, cur, gap, templates, rules) -> List[str]:
    d = gap.work_date
    after = dict(cur)
    after[d] = (gap.shift_template_id, False)

    def viol(cells):
        spans = schedule_rules.build_spans(
            [(uid, x, c[0]) for x, c in cells.items()
             if swap_svc.is_working(c) and abs((x - d).days) <= 7], templates)
        return schedule_rules.check_rules(spans, rules, window_start=d)

    before = {(v.user_id, v.work_date, v.rule) for v in viol(cur)}
    return [v.message for v in viol(after)
            if (v.user_id, v.work_date, v.rule) not in before]
