"""Open shifts: eligibility, creation (+ notification) and claim confirmation.

Callers hold the request transaction; these functions flush but never commit.
`confirm_claim` expects the OpenShift row to be locked (FOR UPDATE) by the
caller, so `filled` / `status` are fresh.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Tuple

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
from app.services import schedule_rules
from app.services import swaps as swap_svc
from app.services.time_rules import get_schedule_rules
from app.services.availability import availability_by_day
from app.services.effective_shift import effective_shifts_for_range

RTYPE = "open_shift"
NOTIFY_CAP = 500


def today() -> date:
    return datetime.now(timezone.utc).date()


# ----------------------------- eligibility -----------------------------

async def eligibility_matrix(
    db, pairs: Iterable[Tuple[OpenShift, int]], approver: Optional[User] = None,
) -> Dict[Tuple[int, int], Optional[str]]:
    """THE eligibility rules, evaluated over (shift, user_id) pairs with the
    shared lookups (employees, creators' publish scope, effective shifts,
    leave, availability) loaded once. Returns {(shift.id, user_id): None when
    eligible, else the first failing reason}. `approver` (decide time) may
    also supply the publish rights the creator lacks."""
    pairs = list(pairs)
    out: Dict[Tuple[int, int], Optional[str]] = {}
    if not pairs:
        return out
    uids = {u for _, u in pairs}
    shifts = {s.id: s for s, _ in pairs}
    emps = {
        e.user_id: e for e in (await db.execute(
            select(Employee).join(User, User.id == Employee.user_id).where(
                Employee.user_id.in_(uids),
                Employee.status == EmployeeStatus.ACTIVE,
                User.is_active.is_(True),
            ))).scalars().all()
    }
    cids = {s.created_by_id for s in shifts.values() if s.created_by_id}
    creators = {u.id: u for u in (await db.execute(
        select(User).where(User.id.in_(cids)))).scalars().all()} if cids else {}
    creator_pub: Dict[int, set] = {}
    creator_admin: Dict[int, bool] = {}
    for cid, cu in creators.items():
        creator_admin[cid] = roster_svc.is_roster_admin(cu)
        creator_pub[cid] = (
            await roster_svc.publishable_subset(db, cu, uids)
            if cu.is_active else set())
    approver_pub = (
        await roster_svc.publishable_subset(db, approver, uids)
        if approver is not None else set())
    t = today()
    live = [s for s in shifts.values() if s.work_date >= t]
    eff: dict = {}
    leave: set = set()
    avail: dict = {}
    if live:
        lo = min(s.work_date for s in live)
        hi = max(s.work_date for s in live)
        eff = await effective_shifts_for_range(db, sorted(uids), lo, hi)
        leave = await roster_svc.approved_leave_days(db, uids, lo, hi)
        avail = await availability_by_day(db, uids, lo, hi)
    for sh, u in pairs:
        out[(sh.id, u)] = _reason(
            sh, u, emps.get(u), creator_pub.get(sh.created_by_id, set()),
            creator_admin.get(sh.created_by_id, False), approver_pub, t,
            eff, leave, avail)
    return out


def _reason(sh, u, emp, creator_pub, creator_is_admin, approver_pub, t,
            eff, leave, avail) -> Optional[str]:
    d = sh.work_date
    # 0. the poster cannot take their own shift (unless roster admin), and
    # the person who gave a shift away cannot take it back.
    if sh.created_by_id == u and not creator_is_admin:
        return "You posted this shift"
    if sh.excluded_user_id is not None and sh.excluded_user_id == u:
        return "You gave away this shift"
    # 1. active employee matching department / location
    if emp is None:
        return "Not an active employee"
    if sh.department and emp.department != sh.department:
        return f"Not in the {sh.department} department"
    if sh.location and (emp.location or "") != sh.location:
        return f"Not at the {sh.location} location"
    # 2. publish scope: the creator's, or (decide time) the approver's
    if u not in creator_pub and u not in approver_pub:
        return "Outside the scope of the scheduler who posted this shift"
    # 3. not in the past
    if d < t:
        return "This shift is in the past"
    # 4. no working shift that day
    es = eff[(u, d)]
    if es.shift is not None and not es.is_week_off:
        return "Already scheduled to work that day"
    # 5. not on approved leave (half-day leave does not block, by convention
    # shared with the rest of the roster), not unavailable for the shift
    if (u, d) in leave:
        return "On approved leave that day"
    day = avail.get((u, d))
    if day is not None and day.blocks(sh.shift_template_id):
        return "Marked unavailable for this shift"
    return None


async def eligibility_reasons(
    db, shift: OpenShift, user_ids: Iterable[int],
    approver: Optional[User] = None,
) -> Dict[int, Optional[str]]:
    ids = sorted(set(user_ids))
    m = await eligibility_matrix(db, [(shift, u) for u in ids], approver)
    return {u: m[(shift.id, u)] for u in ids}


async def eligible_reason(
    db, shift: OpenShift, user_id: int, approver: Optional[User] = None,
) -> Optional[str]:
    return (await eligibility_reasons(db, shift, [user_id], approver))[user_id]


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
    excluded_user_id: Optional[int] = None,
    exclude_user_ids: Iterable[int] = (),
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
    skip = set(exclude_user_ids) | (
        {excluded_user_id} if excluded_user_id else set())
    cand -= skip
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
        excluded_user_id=excluded_user_id,
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


async def _claim_warnings(db, shift, uid, entry) -> List[str]:
    """Advisory warnings: a replaced DRAFT, and work-rule violations (min
    rest / consecutive days / weekly hours) the claim would CREATE (same
    machinery as swap_warnings: diff of before/after violations)."""
    out: List[str] = []
    if (entry is not None and entry.status == RosterStatus.DRAFT
            and (entry.is_week_off
                 or entry.shift_template_id != shift.shift_template_id)):
        out.append(
            f"An unpublished draft for {shift.work_date.isoformat()} was "
            f"replaced")
    d = shift.work_date
    start, end = d - timedelta(days=7), d + timedelta(days=7)
    eff = await effective_shifts_for_range(db, [uid], start, end)
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    cur = {x: swap_svc.cell_of(eff[(uid, x)]) for x in days}
    after = dict(cur)
    after[d] = (shift.shift_template_id, False)
    templates = {t.id: t for t in (await db.execute(
        select(ShiftTemplate))).scalars().all()}
    rules = await get_schedule_rules(db)

    def violations(cells):
        spans = schedule_rules.build_spans(
            [(uid, x, c[0]) for x, c in cells.items() if swap_svc.is_working(c)],
            templates)
        return schedule_rules.check_rules(spans, rules, window_start=d)

    before = {(v.user_id, v.work_date, v.rule) for v in violations(cur)}
    for v in violations(after):
        if (v.user_id, v.work_date, v.rule) not in before:
            out.append(v.message)
    return out


async def confirm_claim(
    db, shift: OpenShift, claim: OpenShiftClaim, actor_id: Optional[int],
    approver: Optional[User] = None,
) -> List[str]:
    """Approve `claim`: re-check eligibility, write a PUBLISHED cell, record
    history, bump `filled`, close the shift when full. The caller must have
    locked `shift` (lock_row). `approver` (decide time) may supply publish
    rights the creator lacks; the auto-confirm path leaves it None. Returns
    advisory warnings. Raises HTTPException 400/409."""
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
    reason = await eligible_reason(db, shift, uid, approver)
    if reason:
        raise HTTPException(status_code=400, detail=reason)
    warnings = await _claim_warnings(db, shift, uid, entry)
    if entry is not None and entry.status == RosterStatus.PUBLISHED:
        old = (entry.shift_template_id, bool(entry.is_week_off))
    else:  # no live roster cell: the live state is the assignment fallback
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
    return warnings
