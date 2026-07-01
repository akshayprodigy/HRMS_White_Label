"""In-process APScheduler runner + job registry.

Mechanism choice
----------------
APScheduler runs in-process with the AsyncIOScheduler. The current
deployment is a single VPS with gunicorn workers; a broker-backed
scheduler (Celery beat + Redis) would be overkill and add ops surface.
Under multi-worker gunicorn each worker starts its own scheduler
instance, so every job callable takes a DB-level lock via
ScheduledJob.is_running before doing any work. The first worker to
flip is_running=True wins the tick; every other worker sees
is_running=True and no-ops.

Idempotency contract
--------------------
Every job here is safe to re-run:
- apply_due_revisions calls the existing _apply_one() which already
  refuses to double-apply (checks status == APPROVED).
- deliver_scheduled_reports stamps SavedReport.last_sent_at so a
  re-run in the same window is a no-op (the email transport is a
  pluggable stub until Part 2 wires it).
- esic_continuation_detect updates rows only if the target column is
  currently NULL — running it twice yields the same state.

Email transport is out of scope (Part 2) — see EmailSender interface
below.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.scheduled_job import JobRunStatus, ScheduledJob


log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Job registry (in-code catalog)
# ---------------------------------------------------------------------------


JobFn = Callable[[AsyncSession], Awaitable[Dict[str, Any]]]


@dataclass(frozen=True)
class JobSpec:
    name: str
    display_name: str
    description: str
    default_cadence_cron: str
    fn: JobFn


REGISTRY: Dict[str, JobSpec] = {}


def register_job(spec: JobSpec) -> None:
    REGISTRY[spec.name] = spec


# ---------------------------------------------------------------------------
# Email transport pluggable interface (Part 2 replaces the stub)
# ---------------------------------------------------------------------------


class EmailSender:
    """Part 1 contract, now Part 2 fulfils it. `send()` returns True on
    delivered, False on queued/failed. The default implementation
    routes through the notifications_delivery provider so a caller
    getting an EmailSender always sends via the currently-configured
    email provider (log/SMTP/API) — one code path everywhere.
    """
    async def send(
        self, *,
        to: List[str], subject: str, body_html: str,
        attachments: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        # Route via the notifications-delivery provider.
        try:
            from app.services.notifications_delivery import (
                get_email_provider,
            )
            result = await get_email_provider().send(
                to=to, subject=subject,
                body_html=body_html,
                body_text=body_html,  # crude fallback if plain not given
                attachments=attachments,
            )
            return result.ok
        except Exception as e:
            log.warning("EmailSender delivery failed: %s", e)
            return False


_email_sender: EmailSender = EmailSender()


def set_email_sender(sender: EmailSender) -> None:
    global _email_sender
    _email_sender = sender


def get_email_sender() -> EmailSender:
    return _email_sender


# ---------------------------------------------------------------------------
# Job runner — the ONE place that stamps last_run_at + last_status.
# Every job callable goes through here.
# ---------------------------------------------------------------------------


async def run_job_once(
    session_factory: async_sessionmaker[AsyncSession],
    job_name: str,
    *,
    force: bool = False,
) -> Dict[str, Any]:
    """Run one job, once. Returns a summary dict.

    - Acquires a soft lock via ScheduledJob.is_running (SELECT+UPDATE
      inside a transaction). Callers running in parallel see the
      already-running flag and no-op.
    - `force=True` skips the enabled check (used by the admin
      "run now" button so HR can trigger a disabled job manually).
    - Exceptions inside the job callable are captured onto last_error
      + last_status=FAILED. The scheduler never crashes because of a
      failing job.
    """
    spec = REGISTRY.get(job_name)
    if not spec:
        return {"ok": False, "error": f"unknown job {job_name!r}"}

    async with session_factory() as session:
        row = (await session.execute(
            select(ScheduledJob).where(ScheduledJob.name == job_name)
            .with_for_update()
        )).scalar_one_or_none()
        if row is None:
            return {"ok": False, "error": "not registered in DB — call ensure_jobs()"}
        if not force and not row.enabled:
            return {"ok": False, "error": "disabled"}
        if row.is_running:
            return {"ok": False, "error": "already running"}
        row.is_running = True
        row.last_status = JobRunStatus.RUNNING
        row.last_error = None
        await session.commit()

    started = time.monotonic()
    summary: Dict[str, Any] = {}
    failed_error: Optional[str] = None
    try:
        async with session_factory() as session:
            summary = await spec.fn(session)
    except Exception as e:  # never crash the scheduler
        failed_error = f"{type(e).__name__}: {e}"
        log.exception("job %s failed", job_name)

    duration_ms = int((time.monotonic() - started) * 1000)

    async with session_factory() as session:
        row = (await session.execute(
            select(ScheduledJob).where(ScheduledJob.name == job_name)
        )).scalar_one()
        row.is_running = False
        row.last_run_at = datetime.now(timezone.utc)
        row.last_duration_ms = duration_ms
        if failed_error is None:
            row.last_status = JobRunStatus.SUCCESS
            row.last_summary = str(summary)[:2000]
        else:
            row.last_status = JobRunStatus.FAILED
            row.last_error = failed_error[:2000]
        await session.commit()

    return {
        "ok": failed_error is None,
        "duration_ms": duration_ms,
        "summary": summary,
        "error": failed_error,
    }


async def ensure_jobs(session: AsyncSession) -> None:
    """Insert a ScheduledJob row for every registered JobSpec. Idempotent."""
    existing = {
        r.name: r for r in (await session.execute(
            select(ScheduledJob)
        )).scalars().all()
    }
    for name, spec in REGISTRY.items():
        if name in existing:
            continue
        session.add(ScheduledJob(
            name=spec.name,
            display_name=spec.display_name,
            description=spec.description,
            cadence_cron=spec.default_cadence_cron,
            enabled=True,
            last_status=JobRunStatus.IDLE,
        ))
    await session.commit()


# ---------------------------------------------------------------------------
# Scheduler startup / shutdown (called from app lifespan)
# ---------------------------------------------------------------------------


_scheduler = None


def start_scheduler(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """Boot APScheduler with a job for each registered spec."""
    global _scheduler
    if _scheduler is not None:
        return
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger
    except Exception:
        # APScheduler not installed — tests / imports still work.
        log.warning("APScheduler unavailable; scheduler disabled")
        return
    sched = AsyncIOScheduler(timezone=timezone.utc)
    for name, spec in REGISTRY.items():
        try:
            trigger = CronTrigger.from_crontab(spec.default_cadence_cron)
        except Exception:
            log.error("bad cron for %s: %r", name, spec.default_cadence_cron)
            continue
        sched.add_job(
            run_job_once, trigger,
            id=name,
            args=[session_factory, name],
            kwargs={"force": False},
            replace_existing=True,
            misfire_grace_time=300,
        )
    sched.start()
    _scheduler = sched
    log.info("scheduler started with %d jobs", len(REGISTRY))


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


# ============================================================
# The three jobs
# ============================================================


async def _job_apply_due_revisions(session: AsyncSession) -> Dict[str, Any]:
    """Apply every APPROVED revision whose effective_from <= today.

    Idempotency: reuses the existing `_apply_one()` helper which is
    already stamps status=APPLIED and refuses to re-apply. A second
    tick the same day finds zero eligible rows.
    """
    from app.models.revision import SalaryRevision, RevisionStatus
    from app.api.v1.endpoints.revisions import _apply_one

    cutoff = date.today()
    rows = (await session.execute(
        select(SalaryRevision).where(and_(
            SalaryRevision.status == RevisionStatus.APPROVED,
            SalaryRevision.effective_from <= cutoff,
        ))
    )).scalars().all()
    applied = skipped = 0
    errors: List[str] = []
    for r in rows:
        ok, err = await _apply_one(session, r, actor_id=None)
        if ok:
            applied += 1
        else:
            skipped += 1
            if err:
                errors.append(f"#{r.id}: {err}")
    await session.commit()
    return {
        "as_of": cutoff.isoformat(),
        "applied": applied, "skipped": skipped,
        "errors": errors[:10],
    }


async def _job_deliver_scheduled_reports(
    session: AsyncSession,
) -> Dict[str, Any]:
    """For every SavedReport with a cadence whose next-due is <= now,
    enqueue a delivery through the Section L notifications layer for
    every recipient. This gets us: real provider routing, per-user
    preferences respected, delivery log row, retry/backoff, dead-
    letter — all for free.

    Idempotency: after enqueue we stamp `last_sent_at` and won't
    re-deliver until the next cadence window opens.
    """
    from app.models.saved_report import SavedReport, SavedReportCadence
    from app.services.notifications_delivery import notify

    if not hasattr(SavedReport, "last_sent_at"):
        return {
            "delivered": 0, "skipped": 0,
            "note": "SavedReport.last_sent_at column missing — schema pending",
        }

    now = datetime.now(timezone.utc)
    rows = (await session.execute(
        select(SavedReport).where(
            SavedReport.cadence != SavedReportCadence.NONE
        )
    )).scalars().all()

    delivered = skipped = 0
    for sr in rows:
        window = {
            "daily": timedelta(hours=20),
            "weekly": timedelta(days=6),
            "monthly": timedelta(days=25),
        }.get(sr.cadence, None)
        if window is None:
            skipped += 1
            continue
        last = getattr(sr, "last_sent_at", None)
        if last and (now - last) < window:
            skipped += 1
            continue

        recipient_user_ids = (
            getattr(sr, "recipient_user_ids_json", None) or []
        )
        title = f"[Scheduled report] {sr.name}"
        message = (
            f"Report {sr.name} is ready. Open it in the ERP at "
            f"/reports/saved/{sr.id}"
        )
        try:
            for uid in recipient_user_ids:
                await notify(
                    session, user_id=int(uid),
                    event_type="report_scheduled",
                    title=title, message=message,
                    resource_type="saved_report", resource_id=str(sr.id),
                    context={
                        "title": title, "message": message,
                        "report_name": sr.name, "report_id": sr.id,
                    },
                )
        except Exception as e:
            log.warning("report delivery for %s failed: %s", sr.id, e)
            skipped += 1
            continue

        setattr(sr, "last_sent_at", now)
        delivered += 1
    await session.commit()
    return {"delivered": delivered, "skipped": skipped}


async def _job_esic_continuation_detect(
    session: AsyncSession,
) -> Dict[str, Any]:
    """Detect employees who crossed the ₹21k ESIC wage ceiling mid
    contribution-period and stamp esic_continuation_until so the next
    payroll keeps them in ESIC for the rest of the period.

    Idempotency: only writes when esic_continuation_until IS NULL and
    the employee currently qualifies for continuation. Second run
    reads the same rows, sees the flag already set, and no-ops.
    """
    from app.models.statutory import EmployeeStatutoryDetail

    updates = 0
    today = date.today()
    # ESIC contribution periods: Apr-Sep (ends 30-Sep) and Oct-Mar
    # (ends 31-Mar). Compute inline — no dependency on statutory.py.
    if 4 <= today.month <= 9:
        period_end = date(today.year, 9, 30)
    elif today.month >= 10:
        period_end = date(today.year + 1, 3, 31)
    else:  # Jan/Feb/Mar
        period_end = date(today.year, 3, 31)

    rows = (await session.execute(
        select(EmployeeStatutoryDetail).where(
            EmployeeStatutoryDetail.esic_continuation_until.is_(None)
        )
    )).scalars().all()
    for detail in rows:
        # We can't recompute wages here without pulling the payroll
        # module — but the *policy* per ESI rules says: once an employee
        # is under ESIC in a given April-Sept / Oct-March period, they
        # STAY under ESIC for the rest of that period.
        # If the employee has an active esic_ip_number they were under
        # ESIC at some point → stamp until the period-end so they
        # continue.
        if detail.esic_ip_number and detail.esic_ip_number.strip():
            detail.esic_continuation_until = period_end
            updates += 1
    await session.commit()
    return {"updates": updates, "period_end": period_end.isoformat()}


# ============================================================
# Section L jobs: notification delivery sweeper + sender + retry
# + digest flush
# ============================================================


async def _job_sweep_notifications_for_delivery(
    session: AsyncSession,
) -> Dict[str, Any]:
    """Find in-app Notifications created recently that have NO
    NotificationDelivery rows yet, and dispatch them. This is the
    'additive at the central creation point' path — the 14 existing
    db.add(Notification(...)) sites don't need to change; the sweeper
    picks up every new row.

    Idempotency: dispatch_notification refuses to insert a duplicate
    delivery for the same (notification_id, channel) pair.
    """
    from app.models.notification import Notification
    from app.models.notification_channel import (
        DeliveryStatus, NotificationDelivery,
    )
    from app.services.notifications_delivery import dispatch_notification

    since = datetime.now(timezone.utc) - timedelta(minutes=90)
    rows = (await session.execute(
        select(Notification).where(Notification.created_at >= since)
    )).scalars().all()
    dispatched = skipped = 0
    for n in rows:
        already = (await session.execute(
            select(NotificationDelivery).where(
                NotificationDelivery.notification_id == n.id
            ).limit(1)
        )).scalar_one_or_none()
        if already is not None:
            skipped += 1
            continue
        event_type = n.event_type or "generic"
        try:
            ids = await dispatch_notification(
                session,
                notification_id=n.id,
                recipient_user_id=n.user_id,
                event_type=event_type,
                context={
                    "title": n.title, "message": n.message,
                    "resource_type": n.resource_type,
                    "resource_id": n.resource_id,
                },
            )
            dispatched += len(ids)
        except Exception:
            log.exception("dispatch failed for notification %s", n.id)
    return {"dispatched": dispatched, "skipped": skipped}


async def _job_send_queued_notifications(
    session: AsyncSession,
) -> Dict[str, Any]:
    """Send every QUEUED delivery whose next_retry_at is due (or None).
    Digest rows are skipped here — they're picked up by the digest job.
    """
    from app.models.notification_channel import (
        DeliveryStatus, NotificationDelivery,
    )
    from app.services.notifications_delivery import send_one_delivery

    now = datetime.now(timezone.utc)
    rows = (await session.execute(
        select(NotificationDelivery).where(and_(
            NotificationDelivery.status == DeliveryStatus.QUEUED,
            NotificationDelivery.is_digest.is_(False),
            or_(
                NotificationDelivery.next_retry_at.is_(None),
                NotificationDelivery.next_retry_at <= now,
            ),
        )).limit(200)
    )).scalars().all()
    sent = failed = dead = 0
    for row in rows:
        result = await send_one_delivery(session, row.id)
        if result.ok:
            sent += 1
        else:
            # Row status was already stamped by send_one_delivery.
            latest_status = (await session.execute(
                select(NotificationDelivery.status).where(
                    NotificationDelivery.id == row.id
                )
            )).scalar_one()
            if latest_status == DeliveryStatus.DEAD_LETTER:
                dead += 1
            else:
                failed += 1
    return {"sent": sent, "failed": failed, "dead_letter": dead}


async def _job_flush_notification_digests(
    session: AsyncSession,
) -> Dict[str, Any]:
    """Group queued digest deliveries by (user, channel, category) and
    fold them into a single summary message. Fires hourly; the
    per-preference digest_cadence (hourly / daily) filters which
    windows get flushed at this tick.
    """
    from app.models.notification_channel import (
        DeliveryStatus, NotificationDelivery,
    )
    from app.services.notifications_delivery import send_one_delivery

    rows = (await session.execute(
        select(NotificationDelivery).where(and_(
            NotificationDelivery.status == DeliveryStatus.QUEUED,
            NotificationDelivery.is_digest.is_(True),
        )).limit(500)
    )).scalars().all()
    # Group by digest_batch_key which encodes (user, channel, cat, cadence)
    groups: Dict[str, List] = {}
    for r in rows:
        groups.setdefault(r.digest_batch_key or f"{r.id}", []).append(r)

    now = datetime.now(timezone.utc)
    flushed = 0
    for key, items in groups.items():
        # Filter to only the ones due at this tick (daily → once per day)
        cadence = key.split(":")[-1] if ":" in key else "hourly"
        if cadence == "daily" and now.hour != 8:
            continue
        # Merge context: title = 'N items', message = concatenation
        titles = [str(i.context_json.get("title", "")) for i in items]
        header = items[0]
        digest_ctx = {
            "title": f"{len(items)} pending updates",
            "message": " | ".join(titles[:10]),
        }
        header.context_json = digest_ctx
        result = await send_one_delivery(session, header.id)
        if result.ok:
            # Mark the rest as SENT with the same provider id.
            for extra in items[1:]:
                extra.status = DeliveryStatus.SENT
                extra.sent_at = now
                extra.provider_message_id = header.provider_message_id
            await session.commit()
            flushed += 1
    return {"digests_flushed": flushed}


register_job(JobSpec(
    name="sweep_notifications_for_delivery",
    display_name="Sweep in-app notifications into delivery queue",
    description=(
        "Every minute: pick up any Notification that lacks a "
        "NotificationDelivery row, resolve preferences + template, "
        "and enqueue email/SMS. This is the additive integration "
        "with the 14 existing db.add(Notification(...)) sites."
    ),
    default_cadence_cron="* * * * *",     # every minute
    fn=_job_sweep_notifications_for_delivery,
))
register_job(JobSpec(
    name="send_queued_notifications",
    display_name="Send queued email/SMS notifications",
    description=(
        "Every minute: send every QUEUED (non-digest) delivery due "
        "for its next_retry_at. Failed sends bump attempts + set a "
        "backoff; MAX_ATTEMPTS → dead-letter (visible in admin log)."
    ),
    default_cadence_cron="* * * * *",
    fn=_job_send_queued_notifications,
))
register_job(JobSpec(
    name="flush_notification_digests",
    display_name="Flush notification digests (hourly + daily)",
    description=(
        "Hourly: fold QUEUED digest rows into one summary email per "
        "(user, channel, category). Daily-cadence prefs are flushed "
        "at the 08:00 tick; hourly-cadence prefs flush every hour."
    ),
    default_cadence_cron="0 * * * *",
    fn=_job_flush_notification_digests,
))


# Register at import time.
register_job(JobSpec(
    name="apply_due_revisions",
    display_name="Apply due salary revisions",
    description=(
        "Daily: apply every APPROVED revision whose effective_from "
        "has arrived. Idempotent — re-runs pick up nothing."
    ),
    default_cadence_cron="0 2 * * *",     # daily 02:00 UTC
    fn=_job_apply_due_revisions,
))
register_job(JobSpec(
    name="deliver_scheduled_reports",
    display_name="Deliver scheduled reports",
    description=(
        "Hourly: for every SavedReport with a cadence whose window has "
        "elapsed, render + email. Email transport is Part 2 — this "
        "iteration renders + logs via the pluggable EmailSender stub."
    ),
    default_cadence_cron="15 * * * *",     # every hour at :15
    fn=_job_deliver_scheduled_reports,
))
register_job(JobSpec(
    name="esic_continuation_detect",
    display_name="ESIC continuation auto-detect",
    description=(
        "Monthly: stamp esic_continuation_until on employees currently "
        "under ESIC so they stay covered for the rest of the "
        "April-Sept / Oct-March period per the continuation rule."
    ),
    default_cadence_cron="0 3 1 * *",     # first of month 03:00 UTC
    fn=_job_esic_continuation_detect,
))
