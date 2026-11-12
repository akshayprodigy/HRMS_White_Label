"""On-call / standby roster logic (Roadmap v2 Phase 2, Task 5).

Pure helpers (`duration_minutes`, `compute_amount`) plus the entry sync that
keeps `shift_allowance_entry(kind='on_call')` aligned with assignments.

Payroll contract: an entry with payroll_run_id set has been paid (stamped by
generate_draft) and is NEVER modified or deleted here. Callers must treat
`StampedEntry` as "already paid" (HTTP 409).
"""
from datetime import date, datetime, time, timezone
from typing import Optional

from sqlalchemy import select

from app.models.on_call import OnCallAssignment, OnCallPayout, OnCallRule
from app.models.shift_allowance import ShiftAllowanceEntry, ShiftAllowanceKind

ALREADY_PAID = ("This on-call day has already been paid in a payroll run "
                "and can no longer be changed.")


class StampedEntry(Exception):
    """The allowance entry is already stamped with a payroll run."""


def is_overnight(start: time, end: time) -> bool:
    """end <= start means the window crosses midnight (equal = 24h)."""
    return end <= start


def duration_minutes(start: time, end: time) -> int:
    s = start.hour * 60 + start.minute
    e = end.hour * 60 + end.minute
    d = e - s
    if d <= 0:
        d += 24 * 60
    return d


def compute_amount(rule: OnCallRule, minutes: int) -> float:
    if rule.payout_model == OnCallPayout.HOURLY:
        return round(float(rule.hourly_rate or 0.0) * minutes / 60.0, 2)
    return round(float(rule.flat_amount or 0.0), 2)


async def _entry(db, user_id: int, work_date: date, lock: bool = True
                 ) -> Optional[ShiftAllowanceEntry]:
    q = select(ShiftAllowanceEntry).where(
        ShiftAllowanceEntry.user_id == user_id,
        ShiftAllowanceEntry.work_date == work_date,
        ShiftAllowanceEntry.kind == ShiftAllowanceKind.ON_CALL)
    if lock:
        q = q.with_for_update().execution_options(populate_existing=True)
    return (await db.execute(q)).scalars().first()


async def sync_entry(db, a: OnCallAssignment, rule: OnCallRule) -> None:
    """Create/refresh the on_call entry for assignment `a`. Raises
    StampedEntry when the existing entry has been paid."""
    minutes = duration_minutes(a.start_time, a.end_time)
    amount = compute_amount(rule, minutes)
    e = await _entry(db, a.user_id, a.work_date)
    if e is not None and e.payroll_run_id is not None:
        raise StampedEntry()
    now = datetime.now(timezone.utc)
    if e is None:
        db.add(ShiftAllowanceEntry(
            user_id=a.user_id, work_date=a.work_date,
            kind=ShiftAllowanceKind.ON_CALL, amount=amount, minutes=minutes,
            rule_id=rule.id, source_id=a.id, computed_at=now))
    else:
        e.amount, e.minutes, e.rule_id = amount, minutes, rule.id
        e.source_id, e.computed_at = a.id, now


async def delete_entry(db, user_id: int, work_date: date) -> None:
    """Remove the unpaid on_call entry. Raises StampedEntry when paid."""
    e = await _entry(db, user_id, work_date)
    if e is None:
        return
    if e.payroll_run_id is not None:
        raise StampedEntry()
    await db.delete(e)


async def resync_rule(db, rule: OnCallRule) -> int:
    """After a rule's rates change, recompute every UNPAID entry of its
    assignments. Paid entries are skipped. Returns rows refreshed."""
    rows = (await db.execute(select(OnCallAssignment).where(
        OnCallAssignment.rule_id == rule.id))).scalars().all()
    n = 0
    for a in rows:
        try:
            await sync_entry(db, a, rule)
            n += 1
        except StampedEntry:
            continue
    return n
