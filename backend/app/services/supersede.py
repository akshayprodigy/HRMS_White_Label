"""Cross-feature supersede: when a flow rewrites roster cells, every other
pending request that touches the same (user, date) cells is cancelled.

Covers RosterChangeRequests, open ShiftSwapRequests (pending_peer /
pending_approval) and pending ShiftDropRequests. Rows are locked FOR UPDATE
(fresh read) so one that was decided concurrently drops out. Callers hold
the request transaction; nothing is committed here.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Set, Tuple

from sqlalchemy import or_, select

from app.models.open_shift import DropStatus, ShiftDropRequest
from app.models.roster import RosterChangeRequest
from app.models.shift_swap import ShiftSwapRequest, SwapStatus
from app.services import roster as roster_svc

Key = Tuple[int, object]


def _fresh(q):
    return q.with_for_update().execution_options(populate_existing=True)


async def supersede_pending(
    db, written: Set[Key], label: str, op_id: int, actor_id: Optional[int],
    rtype: str, *, skip_swap_id: Optional[int] = None,
    skip_drop_id: Optional[int] = None,
) -> None:
    """`label` e.g. "shift swap" -> decision_note "Superseded by shift swap #5"."""
    if not written:
        return
    uids = {u for u, _ in written}
    dts = {d for _, d in written}
    note = f"Superseded by {label} #{op_id}"
    now = datetime.now(timezone.utc)
    rows = []

    for c in (await db.execute(_fresh(
        select(RosterChangeRequest).where(
            RosterChangeRequest.employee_id.in_(uids),
            RosterChangeRequest.work_date.in_(dts),
            RosterChangeRequest.status == "pending",
        ).order_by(RosterChangeRequest.id)))).scalars().all():
        if (c.employee_id, c.work_date) not in written:
            continue
        c.status = "cancelled"
        c.decision_note = note
        c.decided_by_id = actor_id
        c.decided_at = now
        rows.append((
            c.employee_id, "Change request superseded",
            f"Your change request for {c.work_date.isoformat()} was cancelled "
            f"because of a {label} on that day", rtype, str(op_id)))

    for d in (await db.execute(_fresh(
        select(ShiftDropRequest).where(
            ShiftDropRequest.user_id.in_(uids),
            ShiftDropRequest.work_date.in_(dts),
            ShiftDropRequest.status == DropStatus.PENDING,
        ).order_by(ShiftDropRequest.id)))).scalars().all():
        if d.id == skip_drop_id or (d.user_id, d.work_date) not in written:
            continue
        d.status = DropStatus.CANCELLED
        d.decision_note = note
        d.decided_by_id = actor_id
        d.decided_at = now
        rows.append((
            d.user_id, "Give-away superseded",
            f"Your give-away for {d.work_date.isoformat()} was cancelled "
            f"because of a {label} on that day", "shift_drop", str(d.id)))

    for s in (await db.execute(_fresh(
        select(ShiftSwapRequest).where(
            ShiftSwapRequest.status.in_(SwapStatus.OPEN),
            or_(ShiftSwapRequest.requester_id.in_(uids),
                ShiftSwapRequest.counterparty_id.in_(uids)),
        ).order_by(ShiftSwapRequest.id)))).scalars().all():
        if s.id == skip_swap_id:
            continue
        hit = any(
            (u, d) in written
            for u in (s.requester_id, s.counterparty_id)
            for d in (s.requester_date, s.counterparty_date))
        if not hit:
            continue
        s.status = SwapStatus.CANCELLED
        s.decision_note = note
        s.decided_by_id = actor_id
        s.decided_at = now
        for u in (s.requester_id, s.counterparty_id):
            rows.append((
                u, "Shift swap superseded",
                f"Your shift swap request was cancelled because of a {label}"
                f" on {s.requester_date.isoformat()}", "shift_swap", str(s.id)))
    await roster_svc.notify_many(db, rows)
