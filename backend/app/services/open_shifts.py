"""Open shifts: eligibility, creation (+ notification) and claim confirmation.

Callers hold the request transaction; these functions flush but never commit.
`confirm_claim` expects the OpenShift row to be locked (FOR UPDATE) by the
caller, so `filled` / `status` are fresh.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Dict, Iterable, List, Optional

from fastapi import HTTPException
from sqlalchemy import select

from app.api.v1.endpoints.roster_common import lock_row, lock_user_rows
from app.models.employee import Employee, EmployeeStatus
from app.models.open_shift import (
    ClaimStatus, OpenShift, OpenShiftClaim, OpenShiftStatus,
)
from app.models.roster import RosterEntry, RosterStatus
from app.models.shift import ShiftTemplate
from app.models.user import User
from app.services import roster as roster_svc
from app.services import swaps as swap_svc
from app.services.availability import availability_by_day
from app.services.effective_shift import effective_shifts_for_range

RTYPE = "open_shift"
NOTIFY_CAP = 500


def today() -> date:
    return datetime.now(timezone.utc).date()


# ----------------------------- eligibility -----------------------------

async def eligibility_reasons(
    db, shift: OpenShift, user_ids: Iterable[int]
) -> Dict[int, Optional[str]]:
    """user_id -> None when eligible, else the first failing reason."""
    ids = sorted(set(user_ids))
    out: Dict[int, Optional[str]] = {u: None for u in ids}
    if not ids:
        return out
    # 1. active employee matching department / location
    emps = {
        e.user_id: e for e in (await db.execute(
            select(Employee).join(User, User.id == Employee.user_id).where(
                Employee.user_id.in_(ids),
                Employee.status == EmployeeStatus.ACTIVE,
                User.is_active.is_(True),
            ))).scalars().all()
    }
    for u in ids:
        e = emps.get(u)
        if e is None:
            out[u] = "Not an active employee"
        elif shift.department and e.department != shift.department:
            out[u] = f"Not in the {shift.department} department"
        elif shift.location and (e.location or "") != shift.location:
            out[u] = f"Not at the {shift.location} location"
    # 2. the creator can publish for the user
    creator = (await db.get(User, shift.created_by_id)
               if shift.created_by_id else None)
    pending = [u for u in ids if out[u] is None]
    if pending:
        ok = (
            await roster_svc.publishable_subset(db, creator, pending)
            if creator is not None and creator.is_active else set()
        )
        for u in pending:
            if u not in ok:
                out[u] = "Outside the scope of the scheduler who posted this shift"
    # 3. not in the past
    if shift.work_date < today():
        for u in ids:
            out[u] = out[u] or "This shift is in the past"
    pending = [u for u in ids if out[u] is None]
    if not pending:
        return out
    d = shift.work_date
    # 4. no working shift that day
    eff = await effective_shifts_for_range(db, pending, d, d)
    for u in pending:
        es = eff[(u, d)]
        if es.shift is not None and not es.is_week_off:
            out[u] = "Already scheduled to work that day"
    pending = [u for u in ids if out[u] is None]
    if not pending:
        return out
    # 5. not on approved leave, not unavailable for the shift
    leave = await roster_svc.approved_leave_days(db, pending, d, d)
    avail = await availability_by_day(db, pending, d, d)
    for u in pending:
        if (u, d) in leave:
            out[u] = "On approved leave that day"
        elif (u, d) in avail and avail[(u, d)].blocks(shift.shift_template_id):
            out[u] = "Marked unavailable for this shift"
    return out


async def eligible_reason(db, shift: OpenShift, user_id: int) -> Optional[str]:
    return (await eligibility_reasons(db, shift, [user_id]))[user_id]


async def eligible_user_ids(
    db, shift: OpenShift, candidate_ids: Iterable[int]
) -> List[int]:
    r = await eligibility_reasons(db, shift, candidate_ids)
    return sorted(u for u, why in r.items() if why is None)


# ------------------------------- creation -------------------------------

async def create_open_shift(
    db, actor: User, *, work_date: date, shift_template_id: int,
    department: Optional[str] = None, location: Optional[str] = None,
    slots: int = 1, note: Optional[str] = None, auto_confirm: bool = False,
    source_drop_id: Optional[int] = None, check_scope: bool = True,
) -> OpenShift:
    """Validate, insert and notify eligible employees. Flushes, never
    commits. Raises HTTPException (400 validation, 403 scope)."""
    if work_date < today():
        raise HTTPException(status_code=400, detail="work_date cannot be in the past")
    if not 1 <= slots <= 50:
        raise HTTPException(status_code=400, detail="slots must be between 1 and 50")
    tpl = await db.get(ShiftTemplate, shift_template_id)
    if tpl is None or not tpl.is_active:
        raise HTTPException(
            status_code=400, detail="Unknown or inactive shift template")
    q = select(Employee.user_id).join(User, User.id == Employee.user_id).where(
        Employee.status == EmployeeStatus.ACTIVE,
        Employee.user_id.is_not(None), User.is_active.is_(True),
    )
    if department:
        q = q.where(Employee.department == department)
    if location:
        q = q.where(Employee.location == location)
    cand = set((await db.execute(q)).scalars().all())
    cand.discard(actor.id)
    scope = await roster_svc.publishable_subset(db, actor, cand)
    if check_scope and not scope:
        raise HTTPException(
            status_code=403,
            detail="No employees matching this shift are within your scheduling scope.")
    shift = OpenShift(
        work_date=work_date, shift_template_id=shift_template_id,
        department=department or None, location=location or None,
        slots=slots, filled=0, note=(note or None),
        status=OpenShiftStatus.OPEN, auto_confirm=bool(auto_confirm),
        created_by_id=actor.id, source_drop_id=source_drop_id,
    )
    db.add(shift)
    await db.flush()
    elig = (await eligible_user_ids(db, shift, scope))[:NOTIFY_CAP]
    await roster_svc.notify_many(db, [
        (u, "Open shift available",
         f"{tpl.name} {tpl.start_time.strftime('%H:%M')}-"
         f"{tpl.end_time.strftime('%H:%M')} on {work_date.isoformat()} "
         f"is open to claim",
         RTYPE, str(shift.id))
        for u in elig
    ])
    return shift


# ------------------------------ confirmation ------------------------------

def _label(shift: OpenShift) -> str:
    return f"open shift on {shift.work_date.isoformat()}"


async def reject_pending(
    db, shift: OpenShift, actor_id: Optional[int], message: str,
    title: str = "Open shift claim rejected", exclude_id: Optional[int] = None,
) -> int:
    """Reject every pending claim (locked read) and notify claimants."""
    rows = (await db.execute(
        select(OpenShiftClaim).where(
            OpenShiftClaim.open_shift_id == shift.id,
            OpenShiftClaim.status == ClaimStatus.PENDING,
        ).with_for_update().execution_options(populate_existing=True)
    )).scalars().all()
    now = datetime.now(timezone.utc)
    hit = [c for c in rows if c.id != exclude_id]
    for c in hit:
        c.status = ClaimStatus.REJECTED
        c.decided_by_id = actor_id
        c.decided_at = now
    await roster_svc.notify_many(db, [
        (c.user_id, title, message, RTYPE, str(shift.id)) for c in hit])
    return len(hit)


async def confirm_claim(
    db, shift: OpenShift, claim: OpenShiftClaim, actor_id: Optional[int],
) -> None:
    """Approve `claim`: re-check eligibility, write a PUBLISHED cell, record
    history, bump `filled`, close the shift when full. The caller must have
    locked `shift` (lock_row). Raises HTTPException 400/409."""
    if shift.status != OpenShiftStatus.OPEN:
        raise HTTPException(status_code=409, detail="Open shift is no longer open")
    if shift.filled >= shift.slots:
        raise HTTPException(status_code=409, detail="Open shift is already filled")
    uid, d = claim.user_id, shift.work_date
    # Serialize against other writers of this person's day, then read their
    # cell with a locking read (the request snapshot predates the lock).
    await lock_user_rows(db, [uid])
    entry = await lock_row(
        db, select(RosterEntry).where(
            RosterEntry.employee_id == uid, RosterEntry.work_date == d),
        "Roster changed concurrently; retry")
    if (entry is not None and entry.status == RosterStatus.PUBLISHED
            and not entry.is_week_off and entry.shift_template_id is not None):
        raise HTTPException(
            status_code=400, detail="Already scheduled to work that day")
    reason = await eligible_reason(db, shift, uid)
    if reason:
        raise HTTPException(status_code=400, detail=reason)
    eff = (await effective_shifts_for_range(db, [uid], d, d))[(uid, d)]
    old = swap_svc.cell_of(eff)
    # Pending change requests on this cell are superseded.
    now = datetime.now(timezone.utc)
    crs = await swap_svc.pending_requests(db, {(uid, d)}, lock=True)
    for c in crs:
        c.status = "cancelled"
        c.decision_note = f"Superseded by open shift #{shift.id}"
        c.decided_by_id = actor_id
        c.decided_at = now
    await roster_svc.notify_many(db, [
        (c.employee_id, "Change request superseded",
         f"Your change request for {c.work_date.isoformat()} was cancelled "
         f"because you were confirmed for an open shift that day",
         RTYPE, str(shift.id)) for c in crs])
    dept = (await db.execute(
        select(Employee.department).where(Employee.user_id == uid))).scalar()
    entry, _o = await roster_svc.upsert_entry(
        db, employee_id=uid, work_date=d,
        shift_template_id=shift.shift_template_id, is_week_off=False,
        status=RosterStatus.PUBLISHED, actor_id=actor_id, department=dept,
        overwrite=True,
    )
    await db.flush()
    roster_svc.record_change(
        db, entry, employee_id=uid, work_date=d,
        old_tpl=old[0], old_off=old[1],
        new_tpl=shift.shift_template_id, new_off=False, action="update",
        reason=f"Open shift #{shift.id}", actor_id=actor_id,
    )
    claim.status = ClaimStatus.APPROVED
    claim.decided_by_id = actor_id
    claim.decided_at = now
    shift.filled = shift.filled + 1
    await roster_svc.notify_many(db, [
        (uid, "Open shift confirmed",
         f"You were confirmed for the {_label(shift)}", RTYPE, str(shift.id))])
    if shift.filled >= shift.slots:
        shift.status = OpenShiftStatus.FILLED
        await reject_pending(
            db, shift, actor_id,
            f"The {_label(shift)} was filled by someone else",
            exclude_id=claim.id)
