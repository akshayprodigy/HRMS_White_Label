"""Emergency leave (Roadmap v2 Phase 2, Task 1).

Same-day / back-dated leave with deferred proof. Callers hold the request
transaction; helpers flush but never commit (except the daily job, which
commits per leave).

* `check_backdate` validates the back-date window; `proof_due_date` defers a
  REQUIRED medical certificate to end_date + `leave.emergency_proof_days`
  (other emergency leaves need no proof).
* `open_gaps_for_leave` turns the employee's PUBLISHED working roster cells
  in [max(start, today), end] into coverage gaps and sends ONE alert to the
  schedulers; `dismiss_gaps_for_leave` withdraws them when the leave is
  rejected / cancelled.
* `proof_check_job` (daily) converts approved emergency leaves whose proof is
  overdue to LOP: refunds the ledger for paid types exactly once and marks
  `converted_to_lop_at`, which payroll reads (see payroll.py).
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Iterable, List, Optional

from fastapi import HTTPException
from sqlalchemy import select

from app.models.coverage_gap import CoverageGap, GapSource, GapStatus
from app.models.leave import LeaveRequest, LeaveStatus, LeaveType
from app.models.notification import Notification
from app.models.open_shift import OpenShift, OpenShiftStatus
from app.models.user import Role, User, user_roles
from app.services.time_rules import get_emergency_leave_rules

logger = logging.getLogger(__name__)

RTYPE = "leave_request"
GAP_RTYPE = "coverage_gap"
GAP_SPAN_CAP_DAYS = 62      # bound the dense roster lookup for very long leaves
HR_NOTIFY_CAP = 25
REMINDER_TITLE = "Leave proof due tomorrow"


def _today() -> date:
    return datetime.now(timezone.utc).date()


async def check_backdate(
    db, start_date: date, today: Optional[date] = None,
) -> None:
    """400 when start_date is older than `leave.emergency_backdate_days`."""
    today = today or _today()
    rules = await get_emergency_leave_rules(db)
    oldest = today - timedelta(days=rules["backdate_days"])
    if start_date < oldest:
        raise HTTPException(
            status_code=400,
            detail=(f"Emergency leave can be back-dated at most "
                    f"{rules['backdate_days']} day(s) (earliest {oldest})"))


def cert_required(leave_type, days: float) -> bool:
    """Whether the type's `requires_medical_cert_after` rule applies."""
    thr = getattr(leave_type, "requires_medical_cert_after", None)
    return bool(thr and days >= thr)


async def proof_due_date(
    db, *, leave_type, days: float, end_date: date, has_attachment: bool,
) -> Optional[date]:
    """Proof is needed ONLY when the leave type's medical-certificate rule
    would have required an attachment (and none was sent). Emergency leave
    defers it to end_date + `leave.emergency_proof_days`; with 0 days there
    is no grace, so the attachment is required upfront (400). Anything else
    needs no proof (None)."""
    if has_attachment or not cert_required(leave_type, days):
        return None
    proof_days = (await get_emergency_leave_rules(db))["proof_days"]
    if proof_days <= 0:
        raise HTTPException(
            status_code=400,
            detail=(f"{leave_type.name} requires a medical certificate for "
                    f"{leave_type.requires_medical_cert_after}+ consecutive "
                    f"days"))
    return end_date + timedelta(days=proof_days)


# ------------------------------ coverage gaps ------------------------------

async def open_gaps_for_leave(
    db, leave: LeaveRequest, *, today: Optional[date] = None,
) -> List[CoverageGap]:
    """Open one gap per PUBLISHED working roster cell of the employee in
    [max(start, today), end]; alert schedulers once. Best-effort (never
    breaks the leave submit). Returns the OPEN gaps tied to this leave."""
    from app.services import coverage_gaps as gap_svc
    from app.services import roster as roster_svc
    from app.services.effective_shift import effective_shifts_for_range

    today = today or _today()
    first = max(leave.start_date, today)
    last = min(leave.end_date, first + timedelta(days=GAP_SPAN_CAP_DAYS))
    if last < first:
        return []
    try:
        async with db.begin_nested():
            eff = await effective_shifts_for_range(
                db, [leave.employee_id], first, last)
            gaps: List[CoverageGap] = []
            d = first
            while d <= last:
                e = eff.get((leave.employee_id, d))
                if (e is not None and e.source == "roster"
                        and not e.is_week_off and e.shift is not None):
                    g = await gap_svc.open_gap(
                        db, work_date=d, shift_template_id=e.shift.id,
                        absent_user_id=leave.employee_id,
                        source=GapSource.EMERGENCY_LEAVE,
                        source_id=leave.id, notify=False,
                        note="Emergency leave")
                    if g.status == GapStatus.OPEN and g.source_id == leave.id:
                        gaps.append(g)
                d += timedelta(days=1)
            if not gaps:
                return []
            emp = await db.get(User, leave.employee_id)
            who = (emp.full_name or emp.email) if emp else "An employee"
            dates = ", ".join(g.work_date.isoformat() for g in gaps)
            rows = [
                (uid, "Emergency leave: shifts need cover",
                 f"{who} has filed emergency leave. Uncovered shift(s) on "
                 f"{dates} need a replacement.", GAP_RTYPE, str(gaps[0].id))
                for uid in sorted(await roster_svc.schedule_approver_ids(
                    db, {leave.employee_id}))]
            await roster_svc.notify_many(db, rows)
            return gaps
    except HTTPException:
        raise
    except Exception:
        logger.warning("emergency leave gap creation failed", exc_info=True)
        return []


async def dismiss_gaps_for_leave(
    db, leave: LeaveRequest, actor_id: Optional[int],
    note: str = "Leave rejected/cancelled",
) -> int:
    """Dismiss still-OPEN emergency_leave gaps tied to `leave` (cancelling a
    linked open shift). Gaps already FILLED stay filled (the replacement
    keeps the shift). Returns the number dismissed. Does not commit."""
    from app.services import open_shifts as os_svc

    gaps = (await db.execute(select(CoverageGap).where(
        CoverageGap.source == GapSource.EMERGENCY_LEAVE,
        CoverageGap.source_id == leave.id,
        CoverageGap.status == GapStatus.OPEN,
    ).with_for_update().execution_options(populate_existing=True))
    ).scalars().all()
    now = datetime.now(timezone.utc)
    for g in gaps:
        if g.open_shift_id:
            shift = await db.get(OpenShift, g.open_shift_id)
            if shift is not None and shift.status == OpenShiftStatus.OPEN:
                shift.status = OpenShiftStatus.CANCELLED
                await os_svc.reject_pending(
                    db, shift, actor_id, note, title="Open shift cancelled")
        g.status = GapStatus.DISMISSED
        g.note = note[:255]
        g.resolved_by_id = actor_id
        g.resolved_at = now
    return len(gaps)


# ------------------------------- notifications -------------------------------

async def _safe_notify(db, **kw) -> None:
    from app.services.notifications_delivery import notify
    try:
        async with db.begin_nested():
            await notify(db, **kw)
    except Exception:  # pragma: no cover
        logger.warning("emergency leave notification failed", exc_info=True)


async def hr_user_ids(db) -> List[int]:
    return list((await db.execute(
        select(User.id).join(user_roles, user_roles.c.user_id == User.id)
        .join(Role, Role.id == user_roles.c.role_id)
        .where(Role.name == "HR", User.is_active.is_(True))
        .order_by(User.id).limit(HR_NOTIFY_CAP))).scalars().all())


# ---------------------------------- the job ----------------------------------

async def _send_reminders(db, today: date, user_ids) -> int:
    q = select(LeaveRequest).where(
        LeaveRequest.is_emergency.is_(True),
        LeaveRequest.status.in_([LeaveStatus.SUBMITTED, LeaveStatus.APPROVED]),
        LeaveRequest.proof_due_date == today + timedelta(days=1),
        LeaveRequest.proof_submitted_at.is_(None),
        LeaveRequest.converted_to_lop_at.is_(None))
    if user_ids is not None:
        q = q.where(LeaveRequest.employee_id.in_(list(user_ids)))
    sent = 0
    for lv in (await db.execute(q)).scalars().all():
        already = (await db.execute(select(Notification.id).where(
            Notification.user_id == lv.employee_id,
            Notification.resource_type == RTYPE,
            Notification.resource_id == str(lv.id),
            Notification.event_type == "leave_proof_reminder").limit(1)
        )).first()
        if already:
            continue
        msg = (f"Proof for your emergency leave {lv.start_date} to "
               f"{lv.end_date} is due by {lv.proof_due_date}. Without it the "
               f"leave converts to loss of pay.")
        await _safe_notify(
            db, user_id=lv.employee_id, event_type="leave_proof_reminder",
            title=REMINDER_TITLE, message=msg, resource_type=RTYPE,
            resource_id=str(lv.id), notif_type="warning",
            context={"title": REMINDER_TITLE, "message": msg})
        sent += 1
    return sent


async def _processed_payroll_months(db, lv: LeaveRequest) -> List[str]:
    """'YYYY-MM' of payroll runs covering the leave's months that are past
    DRAFT (their LOP will not be recomputed)."""
    from app.models.payroll import PayrollRun, PayrollRunStatus

    months, d = set(), lv.start_date.replace(day=1)
    while d <= lv.end_date:
        months.add((d.year, d.month))
        d = (d + timedelta(days=32)).replace(day=1)
    runs = (await db.execute(select(PayrollRun).where(
        PayrollRun.status != PayrollRunStatus.DRAFT))).scalars().all()
    return sorted(f"{r.year}-{r.month:02d}" for r in runs
                  if (r.year, r.month) in months)


async def convert_leave_to_lop(db, leave_id: int, now: datetime) -> bool:
    """Convert one overdue emergency leave to LOP. Locks the leave row and
    re-checks, so concurrent runs convert (and refund) exactly once. Paid
    types get their ledger `used` refunded with the same atomic UPDATE the
    approval path debits with. Returns True if converted. Does not commit."""
    from app.api.v1.endpoints.roster_common import lock_row
    from app.services.leave_approval import _bump_ledger, leave_days

    lv = await lock_row(
        db, select(LeaveRequest).where(LeaveRequest.id == leave_id))
    if (lv is None or not lv.is_emergency
            or lv.status != LeaveStatus.APPROVED
            or lv.converted_to_lop_at is not None
            or lv.proof_submitted_at is not None):
        return False
    lt = await db.get(LeaveType, lv.leave_type_id)
    lv.converted_to_lop_at = now
    if lt is not None and not lt.unpaid_allowed:
        await _bump_ledger(db, lv.employee_id, lv.leave_type_id,
                           used=-leave_days(lv))
    emp = await db.get(User, lv.employee_id)
    who = (emp.full_name or emp.email) if emp else "Employee"
    msg = (f"Proof for emergency leave {lv.start_date} to {lv.end_date} was "
           f"not submitted by {lv.proof_due_date}; the leave is now loss "
           f"of pay.")
    title = "Emergency leave converted to LOP"
    processed = await _processed_payroll_months(db, lv)
    if processed:
        logger.warning("emergency leave %s converted to LOP after payroll "
                       "was processed for %s", lv.id, ", ".join(processed))
    await _safe_notify(
        db, user_id=lv.employee_id, event_type="leave_converted_lop",
        title=title, message=msg, resource_type=RTYPE,
        resource_id=str(lv.id), notif_type="warning",
        context={"title": title, "message": msg})
    for uid in await hr_user_ids(db):
        if uid == lv.employee_id:
            continue
        hmsg = (f"{who}'s emergency leave {lv.start_date} to {lv.end_date} "
                f"was converted to LOP (no proof by {lv.proof_due_date}).")
        for m in processed:
            hmsg += f" Payroll for {m} already processed — LOP needs manual adjustment."
        await _safe_notify(
            db, user_id=uid, event_type="leave_converted_lop",
            title=f"{who}: leave converted to LOP", message=hmsg,
            resource_type=RTYPE, resource_id=str(lv.id), notif_type="warning",
            context={"title": f"{who}: leave converted to LOP",
                     "message": hmsg})
    return True


async def proof_check_job(
    db, now: Optional[datetime] = None,
    user_ids: Optional[Iterable[int]] = None,
) -> dict:
    """Daily: remind (1 day before due) and convert overdue emergency leaves.
    The stored `proof_due_date` is authoritative (later rule changes do not
    affect existing leaves). Idempotent; one failing leave never blocks the
    rest."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    today = now.date()
    uids = list(user_ids) if user_ids is not None else None
    reminded = await _send_reminders(db, today, uids)
    await db.commit()
    q = select(LeaveRequest.id).where(
        LeaveRequest.is_emergency.is_(True),
        LeaveRequest.status == LeaveStatus.APPROVED,
        LeaveRequest.proof_due_date < today,
        LeaveRequest.proof_submitted_at.is_(None),
        LeaveRequest.converted_to_lop_at.is_(None))
    if uids is not None:
        q = q.where(LeaveRequest.employee_id.in_(uids))
    ids = list((await db.execute(q.order_by(LeaveRequest.id))).scalars().all())
    converted = failed = 0
    for lid in ids:
        try:
            if await convert_leave_to_lop(db, lid, now):
                converted += 1
            await db.commit()
        except Exception:
            await db.rollback()
            failed += 1
            logger.error("emergency leave %s LOP conversion failed", lid,
                         exc_info=True)
    return {"reminded": reminded, "converted": converted, "failed": failed}
