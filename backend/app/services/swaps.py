"""Shift swaps: pure cell exchange + DB helpers (apply, validate, rule check).

A *cell* is `(shift_template_id | None, is_week_off)` resolved from the
effective published schedule (published roster -> assignment -> none). A swap
exchanges both employees' cells on every distinct date in
{requester_date, counterparty_date}. `employee_id`/user ids are User ids.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy import select

from app.models.employee import Employee
from app.models.roster import RosterChangeRequest, RosterEntry, RosterStatus
from app.models.user import User
from app.models.shift import ShiftTemplate
from app.services import roster as roster_svc
from app.services import schedule_rules
from app.api.v1.endpoints.roster_common import lock_rows, lock_user_rows
from app.services.availability import availability_by_day
from app.services.effective_shift import EffectiveShift, effective_shifts_for_range
from app.services.time_rules import get_schedule_rules

Cell = Tuple[Optional[int], bool]  # (template_id, is_week_off)

MAX_AHEAD_DAYS = 90
MAX_GAP_DAYS = 14


def swapped_cells(
    a_cells: Dict[date, Cell], b_cells: Dict[date, Cell], dates: List[date]
) -> Tuple[Dict[date, Cell], Dict[date, Cell]]:
    """Return (new_a, new_b) for the given dates: values exchanged."""
    new_a = {d: b_cells[d] for d in dates}
    new_b = {d: a_cells[d] for d in dates}
    return new_a, new_b


def swap_dates(requester_date: date, counterparty_date: date) -> List[date]:
    return sorted({requester_date, counterparty_date})


def cell_of(es: EffectiveShift) -> Cell:
    if es.is_week_off:
        return (None, True)
    return (es.shift.id if es.shift is not None else None, False)


def written_cell(cell: Cell) -> Cell:
    """What actually gets stored for a NEW cell. A PUBLISHED blank entry is
    ignored by effective_shift (falls back to the assignment), so a person
    who ends up with no shift is written as an explicit week-off."""
    return (None, True) if cell == (None, False) else cell


def is_working(cell: Cell) -> bool:
    return cell[0] is not None and not cell[1]


async def load_effective(
    db, a: int, b: int, start: date, end: date
) -> Dict[Tuple[int, date], EffectiveShift]:
    return await effective_shifts_for_range(db, [a, b], start, end)


def cells_for(
    eff: Dict[Tuple[int, date], EffectiveShift], uid: int, dates
) -> Dict[date, Cell]:
    return {d: cell_of(eff[(uid, d)]) for d in dates}


def make_snapshot(a_cells: Dict[date, Cell], b_cells: Dict[date, Cell]) -> dict:
    return {
        "a": {d.isoformat(): list(c) for d, c in a_cells.items()},
        "b": {d.isoformat(): list(c) for d, c in b_cells.items()},
    }


def snapshot_matches(
    snap: Optional[dict], a_cells: Dict[date, Cell], b_cells: Dict[date, Cell]
) -> bool:
    if not snap:
        return True
    cur = make_snapshot(a_cells, b_cells)
    return snap == cur


def changes_something(
    a_cells: Dict[date, Cell], b_cells: Dict[date, Cell], dates: List[date]
) -> bool:
    return any(a_cells[d] != b_cells[d] for d in dates)


def validate_dates_open(
    requester_date: date, counterparty_date: date, today: date
) -> None:
    for d in (requester_date, counterparty_date):
        if d < today:
            raise HTTPException(
                status_code=400, detail=f"{d.isoformat()} is in the past")
        if d > today + timedelta(days=MAX_AHEAD_DAYS):
            raise HTTPException(
                status_code=400,
                detail=f"Swaps can be requested at most {MAX_AHEAD_DAYS} days ahead")
    if abs((counterparty_date - requester_date).days) > MAX_GAP_DAYS:
        raise HTTPException(
            status_code=400,
            detail=f"The two dates must be within {MAX_GAP_DAYS} days of each other")


async def check_leave_free(
    db, a: int, b: int, dates: List[date],
    new_a: Dict[date, Cell], new_b: Dict[date, Cell],
) -> None:
    leave = await roster_svc.approved_leave_days(db, [a, b], dates[0], dates[-1])
    for d in dates:
        for uid, cells in ((a, new_a), (b, new_b)):
            if (uid, d) in leave and is_working(cells[d]):
                raise HTTPException(
                    status_code=409,
                    detail=f"An employee is on approved leave on {d.isoformat()}")


async def apply_swap(db, swap, actor_id: int, a_cells, b_cells) -> Dict[int, set]:
    """Write the exchanged cells as PUBLISHED roster entries and record
    history. Returns {user_id: {changed dates}}. Caller commits."""
    dates = swap_dates(swap.requester_date, swap.counterparty_date)
    new_a, new_b = swapped_cells(a_cells, b_cells, dates)
    dept = {
        e.user_id: e.department
        for e in (await db.execute(select(Employee).where(
            Employee.user_id.in_([swap.requester_id, swap.counterparty_id])
        ))).scalars().all()
    }
    changed: Dict[int, set] = {}
    # Lock window: the approver's rights apply (the employees initiated it).
    actor = await roster_svc.actor_user(db, actor_id)
    locked = await roster_svc.lock_guard(db, actor, [
        (uid, d, tuple(old[d]), tuple(written_cell(new[d])))
        for uid, old, new in (
            (swap.requester_id, a_cells, new_a),
            (swap.counterparty_id, b_cells, new_b))
        for d in dates
    ], reason=f"Shift swap #{swap.id}")
    for uid, old, new in (
        (swap.requester_id, a_cells, new_a),
        (swap.counterparty_id, b_cells, new_b),
    ):
        for d in dates:
            tpl, off = written_cell(new[d])
            if old[d] == (tpl, off):
                continue
            entry, _o = await roster_svc.upsert_entry(
                db, employee_id=uid, work_date=d, shift_template_id=tpl,
                is_week_off=off, status=RosterStatus.PUBLISHED,
                actor_id=actor_id, department=dept.get(uid), overwrite=True,
            )
            await db.flush()
            roster_svc.record_change(
                db, entry, employee_id=uid, work_date=d,
                old_tpl=old[d][0], old_off=old[d][1],
                new_tpl=tpl, new_off=off, action="update",
                reason=f"Shift swap #{swap.id}", actor_id=actor_id,
                emergency=(uid, d) in locked,
            )
            changed.setdefault(uid, set()).add(d)
    return changed


async def _unpublished_conflicts(db, written) -> List[schedule_rules.Violation]:
    """Drafts and pending change requests sitting on cells a swap will write."""
    if not written:
        return []
    uids = {u for u, _ in written}
    dts = {d for _, d in written}
    nm = {r[0]: (r[1] or r[2]) for r in (await db.execute(
        select(User.id, User.full_name, User.email).where(User.id.in_(uids))
    )).all()}
    out: List[schedule_rules.Violation] = []
    for e in (await db.execute(select(RosterEntry).where(
        RosterEntry.employee_id.in_(uids), RosterEntry.work_date.in_(dts),
        RosterEntry.status == RosterStatus.DRAFT,
    ))).scalars().all():
        if (e.employee_id, e.work_date) in written:
            out.append(schedule_rules.Violation(
                e.employee_id, e.work_date, "draft_replaced",
                f"Unpublished draft for {nm.get(e.employee_id)} on "
                f"{e.work_date.isoformat()} will be replaced"))
    for c in await pending_requests(db, written):
        out.append(schedule_rules.Violation(
            c.employee_id, c.work_date, "pending_change_request",
            f"Pending change request by {nm.get(c.employee_id)} on "
            f"{c.work_date.isoformat()} will be cancelled"))
    return out


async def pending_requests(
    db, written, lock: bool = False
) -> List[RosterChangeRequest]:
    if not written:
        return []
    q = select(RosterChangeRequest).where(
        RosterChangeRequest.employee_id.in_({u for u, _ in written}),
        RosterChangeRequest.work_date.in_({d for _, d in written}),
        RosterChangeRequest.status == "pending",
    ).order_by(RosterChangeRequest.id)
    if lock:  # fresh locked read; a concurrently decided request drops out
        q = q.with_for_update().execution_options(populate_existing=True)
    rows = (await db.execute(q)).scalars().all()
    return [c for c in rows if (c.employee_id, c.work_date) in written]


def written_keys(swap, a_cells, b_cells) -> set:
    dates = swap_dates(swap.requester_date, swap.counterparty_date)
    new_a, new_b = swapped_cells(a_cells, b_cells, dates)
    return (
        {(swap.requester_id, d) for d in dates if a_cells[d] != new_a[d]}
        | {(swap.counterparty_id, d) for d in dates if b_cells[d] != new_b[d]}
    )


async def swap_warnings(db, swap) -> List[schedule_rules.Violation]:
    """Advisory warnings the swap would CREATE: work-rule + availability
    violations (diffed by (user, date, rule), so a pre-existing violation is
    not reported) plus drafts / pending change requests it will replace.
    Never blocking."""
    a, b = swap.requester_id, swap.counterparty_id
    dates = swap_dates(swap.requester_date, swap.counterparty_date)
    start, end = dates[0] - timedelta(days=7), dates[-1] + timedelta(days=7)
    eff = await load_effective(db, a, b, start, end)
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    cur = {uid: {d: cell_of(eff[(uid, d)]) for d in days} for uid in (a, b)}
    new_a, new_b = swapped_cells(cur[a], cur[b], dates)
    after = {a: dict(cur[a]), b: dict(cur[b])}
    after[a].update(new_a)
    after[b].update(new_b)

    templates = {t.id: t for t in (await db.execute(
        select(ShiftTemplate))).scalars().all()}
    rules = await get_schedule_rules(db)

    def violations(cells):
        spans = schedule_rules.build_spans(
            [(uid, d, c[0]) for uid, m in cells.items()
             for d, c in m.items() if is_working(c)], templates)
        return schedule_rules.check_rules(spans, rules, window_start=dates[0])

    def key(v):
        return (v.user_id, v.work_date, v.rule)

    before_keys = {key(v) for v in violations(cur)}
    out = [v for v in violations(after) if key(v) not in before_keys]
    avail = await availability_by_day(db, [a, b], dates[0], dates[-1])
    for uid in (a, b):
        for d in dates:
            if after[uid][d] == cur[uid][d] or not is_working(after[uid][d]):
                continue
            day = avail.get((uid, d))
            if day is not None and day.blocks(after[uid][d][0]):
                out.append(schedule_rules.Violation(
                    uid, d, "unavailable", "Scheduled on a day marked unavailable"))
    written = {
        (uid, d) for uid in (a, b) for d in dates
        if after[uid][d] != cur[uid][d]}
    out += await _unpublished_conflicts(db, written)
    out.sort(key=lambda v: (v.work_date, v.user_id, v.rule))
    return out


async def load_locked_cells(db, swap):
    """(dates, a_cells, b_cells) read under locks: user rows, then the roster
    entries on the swap dates (FOR UPDATE, fresh), so a concurrent claim /
    give-away / swap that already committed is visible (the request's
    REPEATABLE READ snapshot predates the lock). Raises 409 when a published
    cell vanished since the snapshot."""
    a, b = swap.requester_id, swap.counterparty_id
    dates = swap_dates(swap.requester_date, swap.counterparty_date)
    await lock_user_rows(db, [a, b])
    entries = {
        (e.employee_id, e.work_date): e for e in await lock_rows(
            db, select(RosterEntry).where(
                RosterEntry.employee_id.in_([a, b]),
                RosterEntry.work_date.in_(dates),
            ).order_by(RosterEntry.id))
    }
    eff = await load_effective(db, a, b, dates[0], dates[-1])
    out = {}
    for uid in (a, b):
        cells: Dict[date, Cell] = {}
        for d in dates:
            e = entries.get((uid, d))
            if (e is not None and e.status == RosterStatus.PUBLISHED
                    and (e.is_week_off or e.shift_template_id is not None)):
                cells[d] = (None, True) if e.is_week_off else (
                    e.shift_template_id, False)
            elif eff[(uid, d)].source == "roster":
                raise HTTPException(
                    status_code=409,
                    detail="Schedule changed since the request was made")
            else:
                cells[d] = cell_of(eff[(uid, d)])
        out[uid] = cells
    return dates, out[a], out[b]
