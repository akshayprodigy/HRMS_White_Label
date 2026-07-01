"""Notification delivery layer (Section L).

Provider abstraction + pure dispatch + template render helpers.

Deployment default
------------------
The module boots with the LOG providers active — no real messages
leave the process unless SMTP/SMS credentials are configured via env.
`configure_providers_from_env()` upgrades to real providers on
startup when creds are present. This keeps the branch safe to run
without secrets (constraint).

Sensitive-content rule
----------------------
Templates flagged `is_sensitive=True` render with the money/amount
keys STRIPPED from context. Their body must direct the reader to
open the ERP, not carry the figures. Enforced in `render_template()`.

Idempotency
-----------
Every send goes through a NotificationDelivery row. The sender only
processes rows in QUEUED status; once flipped to SENT (with a
provider_message_id), a re-run never re-sends.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import smtplib
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from email.message import EmailMessage
from typing import Any, Dict, Iterable, List, Optional, Set

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession


log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public types + constants
# ---------------------------------------------------------------------------


MAX_ATTEMPTS = 5
RETRY_BACKOFF_MINUTES = [1, 5, 15, 60, 240]   # per attempt (0-indexed)

# Keys stripped from the interpolation context when a template is
# flagged sensitive. Case-insensitive substring match on the KEY name.
SENSITIVE_KEY_HINTS = (
    "amount", "salary", "basic", "gross", "net", "ctc", "hra",
    "allowance", "deduction", "paise",
)


@dataclass
class SendResult:
    ok: bool
    provider_message_id: Optional[str] = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Email providers
# ---------------------------------------------------------------------------


class EmailProvider:
    name: str = "abstract"

    async def send(
        self, *,
        to: List[str], subject: str, body_html: str,
        body_text: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
    ) -> SendResult:
        raise NotImplementedError


class LogEmailProvider(EmailProvider):
    """Dev/test default. Never sends anything real. Logs the message
    and returns ok=True with a synthetic message id so the delivery
    log clearly marks 'sent via log-provider'."""
    name = "log"

    async def send(
        self, *,
        to: List[str], subject: str, body_html: str,
        body_text: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
    ) -> SendResult:
        log.info(
            "[LogEmailProvider] to=%s subject=%r body_text=%r attachments=%d",
            to, subject, (body_text or "")[:200], len(attachments or []),
        )
        return SendResult(ok=True, provider_message_id=f"log-{id(self)}")


class SMTPEmailProvider(EmailProvider):
    """Concrete SMTP-based provider.

    Env config (all required for real sends):
      SMTP_HOST      hostname (e.g. smtp.gmail.com)
      SMTP_PORT      integer (default 587)
      SMTP_USER      username
      SMTP_PASS      password
      SMTP_FROM      sender address ('ERP <no-reply@example.com>')
      SMTP_STARTTLS  '1'/'0' (default '1')
    """
    name = "smtp"

    def __init__(
        self, *,
        host: str, port: int, user: str, password: str,
        from_addr: str, use_starttls: bool = True,
    ):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.from_addr = from_addr
        self.use_starttls = use_starttls

    async def send(
        self, *,
        to: List[str], subject: str, body_html: str,
        body_text: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
    ) -> SendResult:
        msg = EmailMessage()
        msg["From"] = self.from_addr
        msg["To"] = ", ".join(to)
        msg["Subject"] = subject
        msg.set_content(body_text or "")
        if body_html:
            msg.add_alternative(body_html, subtype="html")
        try:
            # smtplib is sync — run in a threadpool so we don't block
            # the event loop.
            def _blocking():
                with smtplib.SMTP(self.host, self.port, timeout=15) as s:
                    if self.use_starttls:
                        s.starttls()
                    s.login(self.user, self.password)
                    s.send_message(msg)
            await asyncio.get_event_loop().run_in_executor(None, _blocking)
            return SendResult(ok=True, provider_message_id=None)
        except Exception as e:
            return SendResult(ok=False, error=f"{type(e).__name__}: {e}")


class TransactionalEmailAdapter(EmailProvider):
    """Adapter shell for a transactional-API provider (SendGrid/SES/
    Postmark-style). Not the default. Deployments that want the API
    path implement `.send()` against their provider's SDK and register
    with `set_email_provider(TransactionalEmailAdapter(...))`.
    """
    name = "transactional"

    def __init__(self, *, api_key: str, from_addr: str):
        self.api_key = api_key
        self.from_addr = from_addr

    async def send(
        self, *,
        to: List[str], subject: str, body_html: str,
        body_text: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
    ) -> SendResult:
        return SendResult(
            ok=False,
            error="TransactionalEmailAdapter not implemented — plug in your provider SDK here",
        )


# ---------------------------------------------------------------------------
# SMS providers
# ---------------------------------------------------------------------------


class SMSProvider:
    name: str = "abstract"

    async def send(
        self, *,
        to: str, body_text: str,
        dlt_template_id: Optional[str] = None,
        sender_id: Optional[str] = None,
    ) -> SendResult:
        raise NotImplementedError


class LogSMSProvider(SMSProvider):
    name = "log"

    async def send(
        self, *,
        to: str, body_text: str,
        dlt_template_id: Optional[str] = None,
        sender_id: Optional[str] = None,
    ) -> SendResult:
        log.info(
            "[LogSMSProvider] to=%s dlt=%s body=%r",
            to, dlt_template_id, body_text[:160],
        )
        return SendResult(ok=True, provider_message_id=f"log-sms-{id(self)}")


class MSG91SMSProvider(SMSProvider):
    """Reference India SMS adapter — MSG91 style. DLT template id is
    REQUIRED by regulation for transactional SMS; the caller (a
    template row) must supply it.

    Env config:
      MSG91_AUTH_KEY   auth key from MSG91 dashboard
      MSG91_SENDER_ID  6-char sender id
    """
    name = "msg91"

    def __init__(self, *, auth_key: str, sender_id: str, base_url: str = "https://control.msg91.com/api/v5"):
        self.auth_key = auth_key
        self.sender_id = sender_id
        self.base_url = base_url

    async def send(
        self, *,
        to: str, body_text: str,
        dlt_template_id: Optional[str] = None,
        sender_id: Optional[str] = None,
    ) -> SendResult:
        if not dlt_template_id:
            return SendResult(
                ok=False,
                error="MSG91 requires a DLT template id — refusing to send",
            )
        try:
            import httpx  # already installed for testing
        except Exception:
            return SendResult(
                ok=False, error="httpx not available for MSG91 provider",
            )
        try:
            async with httpx.AsyncClient(timeout=10.0) as c:
                r = await c.post(
                    f"{self.base_url}/flow/",
                    headers={
                        "authkey": self.auth_key,
                        "content-type": "application/json",
                    },
                    json={
                        "template_id": dlt_template_id,
                        "sender": sender_id or self.sender_id,
                        "short_url": "1",
                        "recipients": [{
                            "mobiles": to,
                            "body": body_text,
                        }],
                    },
                )
                if r.status_code >= 400:
                    return SendResult(
                        ok=False,
                        error=f"msg91 http {r.status_code}: {r.text[:240]}",
                    )
                data = r.json()
                mid = data.get("request_id") or data.get("message")
                return SendResult(ok=True, provider_message_id=str(mid))
        except Exception as e:
            return SendResult(ok=False, error=f"{type(e).__name__}: {e}")


# ---------------------------------------------------------------------------
# Provider registry (module-global, swappable at test time)
# ---------------------------------------------------------------------------


_email_provider: EmailProvider = LogEmailProvider()
_sms_provider: SMSProvider = LogSMSProvider()


def set_email_provider(p: EmailProvider) -> None:
    global _email_provider
    _email_provider = p


def set_sms_provider(p: SMSProvider) -> None:
    global _sms_provider
    _sms_provider = p


def get_email_provider() -> EmailProvider:
    return _email_provider


def get_sms_provider() -> SMSProvider:
    return _sms_provider


def configure_providers_from_env() -> Dict[str, str]:
    """Called from the app startup. If SMTP creds present, install
    SMTPEmailProvider — otherwise leave LogEmailProvider.
    Same for SMS. Returns a dict describing the active providers.
    """
    active: Dict[str, str] = {}
    if os.environ.get("SMTP_HOST"):
        try:
            set_email_provider(SMTPEmailProvider(
                host=os.environ["SMTP_HOST"],
                port=int(os.environ.get("SMTP_PORT", "587")),
                user=os.environ.get("SMTP_USER", ""),
                password=os.environ.get("SMTP_PASS", ""),
                from_addr=os.environ.get("SMTP_FROM", "no-reply@localhost"),
                use_starttls=os.environ.get("SMTP_STARTTLS", "1") == "1",
            ))
        except Exception as e:
            log.warning("SMTP config failed: %s — staying on log provider", e)
    active["email"] = get_email_provider().name

    if os.environ.get("MSG91_AUTH_KEY"):
        try:
            set_sms_provider(MSG91SMSProvider(
                auth_key=os.environ["MSG91_AUTH_KEY"],
                sender_id=os.environ.get("MSG91_SENDER_ID", "ERPAPP"),
            ))
        except Exception as e:
            log.warning("MSG91 config failed: %s — staying on log provider", e)
    active["sms"] = get_sms_provider().name

    return active


# ---------------------------------------------------------------------------
# Template rendering (pure)
# ---------------------------------------------------------------------------


class _SafeDict(dict):
    """`str.format_map` companion that renders missing keys as '{key}'
    literally instead of raising KeyError. Templates written to a slightly
    different context still render — never fail a send because of a
    template/context mismatch."""
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _strip_sensitive_keys(context: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy with any key matching SENSITIVE_KEY_HINTS removed."""
    out: Dict[str, Any] = {}
    for k, v in context.items():
        if any(h in k.lower() for h in SENSITIVE_KEY_HINTS):
            continue
        out[k] = v
    return out


@dataclass
class RenderedMessage:
    subject: str
    body_html: str
    body_text: str
    dlt_template_id: Optional[str] = None
    is_sensitive: bool = False


def render_template(
    *,
    template_subject: Optional[str],
    template_body_html: Optional[str],
    template_body_text: str,
    context: Dict[str, Any],
    is_sensitive: bool = False,
    dlt_template_id: Optional[str] = None,
) -> RenderedMessage:
    """Pure render. Sensitive templates run against a stripped context
    so amounts / salary figures NEVER reach the wire.
    """
    ctx = _strip_sensitive_keys(context) if is_sensitive else dict(context)
    safe = _SafeDict(**{
        k: ("" if v is None else str(v))
        for k, v in ctx.items()
    })
    subj = (template_subject or "").format_map(safe)
    body_html = (template_body_html or "").format_map(safe)
    body_text = template_body_text.format_map(safe)
    return RenderedMessage(
        subject=subj, body_html=body_html, body_text=body_text,
        dlt_template_id=dlt_template_id, is_sensitive=is_sensitive,
    )


def fallback_from_notification(
    *,
    title: str, message: str,
    channel: str,
) -> RenderedMessage:
    """Template-missing safety net. Renders a generic message from the
    in-app Notification's title + message. NEVER carries money keys
    (we don't know if the parent Notification is sensitive), so uses
    generic phrasing."""
    if channel == "sms":
        # SMS = short. First 160 chars of message.
        return RenderedMessage(
            subject="", body_html="", body_text=message[:160],
        )
    return RenderedMessage(
        subject=title[:240],
        body_html=(
            f"<p>{message}</p>"
            "<p>Open the ERP to view details.</p>"
        ),
        body_text=f"{message}\n\nOpen the ERP to view details.",
    )


# ---------------------------------------------------------------------------
# Preferences (pure)
# ---------------------------------------------------------------------------


DEFAULT_ENABLED_CHANNELS_BY_CATEGORY: Dict[str, Set[str]] = {
    "approvals":   {"in_app", "email"},
    "leave":       {"in_app", "email"},
    "overtime":    {"in_app"},
    "payroll":     {"in_app", "email"},
    "performance": {"in_app", "email"},
    "expense":     {"in_app", "email"},
    "statutory":   {"in_app", "email"},
    "other":       {"in_app"},  # marketing-ish: opt-in
}


def channel_enabled(
    *,
    category: str, channel: str,
    prefs: Iterable[Any],
    hard_opt_out: bool,
) -> bool:
    """Pure resolver: given a user's preference rows + their
    hard_opt_out flag, decide whether a given (category, channel) is
    enabled.

    In-app is ALWAYS on — the delivery layer can never suppress
    in-app.
    """
    if channel == "in_app":
        return True
    if hard_opt_out and channel != "in_app":
        return False
    for p in prefs:
        if p.category == category and p.channel == channel:
            return bool(p.enabled)
    defaults = DEFAULT_ENABLED_CHANNELS_BY_CATEGORY.get(category, set())
    return channel in defaults


def is_within_quiet_hours(
    *, now: datetime, quiet_from: Optional[time], quiet_to: Optional[time],
) -> bool:
    """Pure quiet-hours check. Windows that cross midnight (e.g.
    22:00 → 07:00) are supported."""
    if quiet_from is None or quiet_to is None:
        return False
    t = now.time()
    if quiet_from <= quiet_to:
        return quiet_from <= t < quiet_to
    return t >= quiet_from or t < quiet_to


# ---------------------------------------------------------------------------
# Retry / backoff (pure)
# ---------------------------------------------------------------------------


def next_retry_delay_minutes(attempt_number: int) -> int:
    """0-indexed attempt → minutes to wait before the next try."""
    idx = min(attempt_number, len(RETRY_BACKOFF_MINUTES) - 1)
    return RETRY_BACKOFF_MINUTES[idx]


def should_dead_letter(attempts: int) -> bool:
    return attempts >= MAX_ATTEMPTS


# ---------------------------------------------------------------------------
# notify() helper — for new call sites. Legacy sites keep working
# via the sweeper.
# ---------------------------------------------------------------------------


async def notify(
    session: AsyncSession,
    *,
    user_id: int,
    event_type: str,
    title: str,
    message: str,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
    notif_type: str = "info",
) -> int:
    """One-line notification-creation helper. Creates the in-app
    Notification row (unchanged behaviour), then enqueues channel
    deliveries via `dispatch_notification` immediately (skipping the
    minute-later sweeper for a snappier UX)."""
    from app.models.notification import Notification

    n = Notification(
        user_id=user_id, title=title, message=message,
        type=notif_type,
        resource_type=resource_type, resource_id=resource_id,
        event_type=event_type,
    )
    session.add(n)
    await session.flush()
    await dispatch_notification(
        session,
        notification_id=n.id,
        recipient_user_id=user_id,
        event_type=event_type,
        context=context or {"title": title, "message": message},
    )
    return n.id


# ---------------------------------------------------------------------------
# Dispatcher — the central fan-out
# ---------------------------------------------------------------------------


async def dispatch_notification(
    session: AsyncSession,
    *,
    notification_id: Optional[int],
    recipient_user_id: int,
    event_type: str,
    context: Optional[Dict[str, Any]] = None,
) -> List[int]:
    """Create NotificationDelivery rows for the (recipient, event) tuple
    across every channel the recipient has enabled. Returns the list of
    delivery ids created. Never sends — the scheduler sender picks the
    rows up. Idempotent for a given notification_id: if a row already
    exists for (notification_id, channel), it's not duplicated.
    """
    from app.models.notification_channel import (
        Channel, DeliveryStatus, EVENT_CATEGORY_MAP,
        NotificationDelivery, UserNotificationPreference,
        UserQuietHours,
    )

    context = context or {}
    category = EVENT_CATEGORY_MAP.get(event_type, "other")

    prefs = list((await session.execute(
        select(UserNotificationPreference).where(
            UserNotificationPreference.user_id == recipient_user_id
        )
    )).scalars().all())
    qh = (await session.execute(
        select(UserQuietHours).where(
            UserQuietHours.user_id == recipient_user_id
        )
    )).scalar_one_or_none()
    hard_opt_out = bool(qh and qh.hard_opt_out)

    # Dedup — never create a duplicate delivery for the same
    # notification + channel (idempotency guard).
    existing_channels: Set[str] = set()
    if notification_id is not None:
        existing_channels = {
            d.channel
            for d in (await session.execute(
                select(NotificationDelivery).where(
                    NotificationDelivery.notification_id == notification_id
                )
            )).scalars().all()
        }

    created: List[int] = []
    now = datetime.now(timezone.utc)
    for channel in (Channel.EMAIL, Channel.SMS):
        if channel in existing_channels:
            continue
        if not channel_enabled(
            category=category, channel=channel,
            prefs=prefs, hard_opt_out=hard_opt_out,
        ):
            row = NotificationDelivery(
                notification_id=notification_id,
                event_type=event_type,
                recipient_user_id=recipient_user_id,
                channel=channel, status=DeliveryStatus.SKIPPED_PREF,
                context_json=context,
            )
            session.add(row)
            continue
        if qh and is_within_quiet_hours(
            now=now, quiet_from=qh.quiet_from, quiet_to=qh.quiet_to,
        ):
            # Delay until the window closes.
            row = NotificationDelivery(
                notification_id=notification_id,
                event_type=event_type,
                recipient_user_id=recipient_user_id,
                channel=channel, status=DeliveryStatus.QUEUED,
                context_json=context,
                next_retry_at=_next_after_quiet(now, qh.quiet_to),
            )
            session.add(row)
            await session.flush()
            created.append(row.id)
            continue

        # Digest opt-in
        digest_cadence = _resolve_digest_cadence(prefs, category, channel)
        is_digest = digest_cadence in ("hourly", "daily")

        row = NotificationDelivery(
            notification_id=notification_id,
            event_type=event_type,
            recipient_user_id=recipient_user_id,
            channel=channel, status=DeliveryStatus.QUEUED,
            context_json=context,
            is_digest=is_digest,
            digest_batch_key=(
                f"{recipient_user_id}:{channel}:{category}:{digest_cadence}"
                if is_digest else None
            ),
        )
        session.add(row)
        await session.flush()
        created.append(row.id)

    return created


def _next_after_quiet(now: datetime, quiet_to: Optional[time]) -> datetime:
    if quiet_to is None:
        return now + timedelta(minutes=30)
    target = now.replace(
        hour=quiet_to.hour, minute=quiet_to.minute,
        second=0, microsecond=0,
    )
    if target <= now:
        target = target + timedelta(days=1)
    return target


def _resolve_digest_cadence(prefs, category, channel) -> str:
    for p in prefs:
        if p.category == category and p.channel == channel:
            return p.digest_cadence or "immediate"
    return "immediate"


# ---------------------------------------------------------------------------
# Sender — the scheduler job pulls QUEUED rows and calls this per row
# ---------------------------------------------------------------------------


async def send_one_delivery(
    session: AsyncSession, delivery_id: int,
) -> SendResult:
    """Pick a QUEUED delivery, resolve template + recipient contact,
    call the provider, stamp SENT/FAILED. Idempotent — a SENT row is
    left alone; a QUEUED row with attempts>=MAX_ATTEMPTS is
    dead-lettered.
    """
    from app.models.notification_channel import (
        Channel, DeliveryStatus, NotificationTemplate,
        NotificationDelivery,
    )
    from app.models.user import User

    row = (await session.execute(
        select(NotificationDelivery).where(
            NotificationDelivery.id == delivery_id
        )
    )).scalar_one_or_none()
    if row is None:
        return SendResult(ok=False, error="no such delivery")
    if row.status not in (DeliveryStatus.QUEUED,):
        return SendResult(ok=False, error=f"not queued (status={row.status})")

    # Recipient contact
    recipient = await session.get(User, row.recipient_user_id)
    if recipient is None:
        row.status = DeliveryStatus.FAILED
        row.error = "recipient user not found"
        await session.commit()
        return SendResult(ok=False, error="recipient not found")

    # Template
    template = (await session.execute(
        select(NotificationTemplate).where(and_(
            NotificationTemplate.event_type == row.event_type,
            NotificationTemplate.channel == row.channel,
            NotificationTemplate.is_active.is_(True),
        ))
    )).scalar_one_or_none()

    if template is not None:
        rendered = render_template(
            template_subject=template.subject,
            template_body_html=template.body_html,
            template_body_text=template.body_text,
            context=row.context_json or {},
            is_sensitive=template.is_sensitive,
            dlt_template_id=template.dlt_template_id,
        )
    else:
        # Missing template → fall back so we never fail to send.
        from app.models.notification import Notification
        title = ""
        message = "Notification"
        if row.notification_id:
            n = await session.get(Notification, row.notification_id)
            if n:
                title, message = n.title, n.message
        rendered = fallback_from_notification(
            title=title or row.event_type, message=message,
            channel=row.channel,
        )

    # Provider dispatch
    result: SendResult
    if row.channel == Channel.EMAIL:
        to = [recipient.email] if recipient.email else []
        if not to:
            result = SendResult(ok=False, error="recipient email missing")
        else:
            result = await get_email_provider().send(
                to=to, subject=rendered.subject,
                body_html=rendered.body_html, body_text=rendered.body_text,
            )
    elif row.channel == Channel.SMS:
        phone = getattr(recipient, "phone", None)
        if not phone:
            result = SendResult(ok=False, error="recipient phone missing")
        else:
            result = await get_sms_provider().send(
                to=phone, body_text=rendered.body_text,
                dlt_template_id=rendered.dlt_template_id,
            )
    else:
        result = SendResult(
            ok=False, error=f"unknown channel {row.channel!r}"
        )

    # Stamp the row
    row.attempts = (row.attempts or 0) + 1
    if result.ok:
        row.status = DeliveryStatus.SENT
        row.sent_at = datetime.now(timezone.utc)
        row.provider_message_id = result.provider_message_id
        row.error = None
    else:
        if should_dead_letter(row.attempts):
            row.status = DeliveryStatus.DEAD_LETTER
        else:
            row.status = DeliveryStatus.QUEUED
            row.next_retry_at = (
                datetime.now(timezone.utc)
                + timedelta(minutes=next_retry_delay_minutes(row.attempts))
            )
        row.error = result.error
    await session.commit()
    return result
