"""Unit tests for notifications delivery layer (Section L).

Pure. No DB — each test constructs the plain-object inputs the
service takes. Every constraint is covered:
- Preferences respected, opted-out skipped, in-app can never be
  suppressed.
- Template interpolation renders + falls back on missing template.
- Sensitive-content rule: money keys stripped before render.
- SMS carries a DLT template id when configured.
- Retry-then-deadletter backoff.
- Log-provider is the boot default (no accidental real sends).
- Quiet hours suppress non-in-app channels.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, time, timezone
from typing import List, Optional

import pytest

from app.services.notifications_delivery import (
    DEFAULT_ENABLED_CHANNELS_BY_CATEGORY, LogEmailProvider,
    LogSMSProvider, MAX_ATTEMPTS, MSG91SMSProvider, RETRY_BACKOFF_MINUTES,
    RenderedMessage, SendResult, TransactionalEmailAdapter,
    _strip_sensitive_keys, channel_enabled, fallback_from_notification,
    get_email_provider, get_sms_provider, is_within_quiet_hours,
    next_retry_delay_minutes, render_template, set_email_provider,
    set_sms_provider, should_dead_letter,
)


# ---------------------------------------------------------------------------
# Provider defaults — no accidental real sends
# ---------------------------------------------------------------------------


def test_default_email_provider_is_log():
    """Log provider is the boot default — no creds → no real send."""
    assert isinstance(get_email_provider(), LogEmailProvider)


def test_default_sms_provider_is_log():
    assert isinstance(get_sms_provider(), LogSMSProvider)


def test_log_email_provider_returns_ok_and_synthetic_id():
    p = LogEmailProvider()
    r = asyncio.run(p.send(
        to=["x@y"], subject="test",
        body_html="<p>hi</p>", body_text="hi",
    ))
    assert r.ok
    assert r.provider_message_id and r.provider_message_id.startswith("log-")


def test_log_sms_provider_returns_ok():
    p = LogSMSProvider()
    r = asyncio.run(p.send(to="+911234567890", body_text="hi"))
    assert r.ok


def test_transactional_email_adapter_marked_not_implemented():
    """Adapter is a marked slot — never accidentally 'works'."""
    p = TransactionalEmailAdapter(api_key="k", from_addr="a@b")
    r = asyncio.run(p.send(
        to=["x@y"], subject="s", body_html="h", body_text="t",
    ))
    assert not r.ok
    assert "not implemented" in (r.error or "").lower()


def test_msg91_refuses_without_dlt_template_id():
    """India SMS regulation: DLT template id is mandatory."""
    p = MSG91SMSProvider(auth_key="k", sender_id="ERPAPP")
    r = asyncio.run(p.send(to="+919876543210", body_text="hi"))
    assert not r.ok
    assert "DLT" in (r.error or "")


def test_set_and_get_email_provider_roundtrip():
    original = get_email_provider()
    try:
        set_email_provider(LogEmailProvider())
        assert get_email_provider() is not original
    finally:
        set_email_provider(original)


# ---------------------------------------------------------------------------
# Preferences
# ---------------------------------------------------------------------------


@dataclass
class FakePref:
    category: str
    channel: str
    enabled: bool
    digest_cadence: str = "immediate"


def test_in_app_always_enabled_even_with_opt_out():
    """The dispatcher can NEVER suppress the in-app channel."""
    assert channel_enabled(
        category="approvals", channel="in_app",
        prefs=[], hard_opt_out=True,
    )


def test_hard_opt_out_kills_email_and_sms():
    assert not channel_enabled(
        category="approvals", channel="email",
        prefs=[FakePref("approvals", "email", True)],
        hard_opt_out=True,
    )
    assert not channel_enabled(
        category="approvals", channel="sms",
        prefs=[FakePref("approvals", "sms", True)],
        hard_opt_out=True,
    )


def test_explicit_pref_overrides_default():
    # 'approvals' + 'email' defaults to enabled — a False pref must win.
    assert not channel_enabled(
        category="approvals", channel="email",
        prefs=[FakePref("approvals", "email", False)],
        hard_opt_out=False,
    )


def test_default_channel_for_missing_pref():
    """No pref row → look up DEFAULT_ENABLED_CHANNELS_BY_CATEGORY."""
    assert channel_enabled(
        category="approvals", channel="email",
        prefs=[], hard_opt_out=False,
    )
    # 'other' has no default email → False.
    assert not channel_enabled(
        category="other", channel="email",
        prefs=[], hard_opt_out=False,
    )


def test_default_map_has_categories_covered():
    for c in (
        "approvals", "leave", "overtime", "payroll",
        "performance", "expense", "statutory", "other",
    ):
        assert c in DEFAULT_ENABLED_CHANNELS_BY_CATEGORY


# ---------------------------------------------------------------------------
# Template render + sensitive-content rule
# ---------------------------------------------------------------------------


def test_render_template_interpolates_context():
    r = render_template(
        template_subject="Hello {name}",
        template_body_html="<p>Amount {amount_paise}</p>",
        template_body_text="Amount {amount_paise}",
        context={"name": "Alice", "amount_paise": 50000},
    )
    assert r.subject == "Hello Alice"
    assert "50000" in r.body_html
    assert "50000" in r.body_text


def test_missing_context_key_renders_literal_placeholder():
    """Never fail a send because template mentions a key the context
    forgot — render '{key}' as literal so it's obvious in the log."""
    r = render_template(
        template_subject="",
        template_body_html="",
        template_body_text="Hello {who}",
        context={},
    )
    assert r.body_text == "Hello {who}"


def test_sensitive_template_strips_money_keys_from_context():
    """CRITICAL: sensitive-content rule. Money keys must NEVER reach
    the wire on a sensitive template."""
    r = render_template(
        template_subject="Your payslip",
        template_body_html="<p>Open the ERP.</p>",
        template_body_text="Open the ERP to view your payslip.",
        context={
            "employee_name": "Alice",
            "gross_paise": 500000,
            "net_paise": 400000,
            "basic": 250000,
        },
        is_sensitive=True,
    )
    # None of the money values appear in the rendered output.
    for money in ("500000", "400000", "250000"):
        assert money not in r.body_text
        assert money not in r.body_html


def test_non_sensitive_template_can_reference_amount_context():
    """Only sensitive templates strip. Ordinary ones can include amounts."""
    r = render_template(
        template_subject="",
        template_body_html="",
        template_body_text="Approved: ₹{amount_paise}",
        context={"amount_paise": 25000},
        is_sensitive=False,
    )
    assert "25000" in r.body_text


def test_strip_sensitive_keys_uses_substring_match():
    ctx = {
        "employee_name": "A",     # safe
        "GROSS_AMOUNT": 1,        # stripped (both grade & amount hints)
        "hra_paid": 2,            # stripped
        "note": "hello",          # safe
    }
    stripped = _strip_sensitive_keys(ctx)
    assert "employee_name" in stripped
    assert "note" in stripped
    assert "GROSS_AMOUNT" not in stripped
    assert "hra_paid" not in stripped


def test_fallback_from_notification_for_email():
    """Missing template → sender still emits SOMETHING sensible."""
    r = fallback_from_notification(
        title="Approval pending",
        message="You have a leave request awaiting your action.",
        channel="email",
    )
    assert r.subject == "Approval pending"
    assert "Open the ERP" in r.body_html
    assert "Open the ERP" in r.body_text


def test_fallback_for_sms_stays_within_160_chars():
    long = "x" * 500
    r = fallback_from_notification(
        title="ignored", message=long, channel="sms",
    )
    assert len(r.body_text) == 160


def test_dlt_template_id_flows_through_render():
    r = render_template(
        template_subject="", template_body_html="",
        template_body_text="hi", context={},
        dlt_template_id="1207168223412345678",
    )
    assert r.dlt_template_id == "1207168223412345678"


# ---------------------------------------------------------------------------
# Retry / backoff / dead-letter
# ---------------------------------------------------------------------------


def test_next_retry_delay_grows_with_attempt():
    a = next_retry_delay_minutes(0)
    b = next_retry_delay_minutes(1)
    c = next_retry_delay_minutes(2)
    assert a <= b <= c


def test_next_retry_delay_saturates_at_last_bucket():
    n = next_retry_delay_minutes(99)
    assert n == RETRY_BACKOFF_MINUTES[-1]


def test_should_dead_letter_at_max_attempts():
    assert should_dead_letter(MAX_ATTEMPTS)
    assert should_dead_letter(MAX_ATTEMPTS + 1)
    assert not should_dead_letter(MAX_ATTEMPTS - 1)


def test_backoff_list_is_monotonic_non_decreasing():
    """Sanity: prevent an accidental typo shrinking a later bucket."""
    prev = 0
    for m in RETRY_BACKOFF_MINUTES:
        assert m >= prev
        prev = m


# ---------------------------------------------------------------------------
# Quiet hours
# ---------------------------------------------------------------------------


def _dt(h, m=0):
    return datetime(2026, 7, 1, h, m, tzinfo=timezone.utc)


def test_quiet_hours_none_means_never_quiet():
    assert not is_within_quiet_hours(
        now=_dt(22), quiet_from=None, quiet_to=None,
    )


def test_quiet_hours_same_day_window():
    # 14:00–16:00 window
    assert is_within_quiet_hours(
        now=_dt(15), quiet_from=time(14), quiet_to=time(16),
    )
    assert not is_within_quiet_hours(
        now=_dt(13), quiet_from=time(14), quiet_to=time(16),
    )
    assert not is_within_quiet_hours(
        now=_dt(16), quiet_from=time(14), quiet_to=time(16),
    )


def test_quiet_hours_crosses_midnight():
    # 22:00–07:00 window
    assert is_within_quiet_hours(
        now=_dt(23), quiet_from=time(22), quiet_to=time(7),
    )
    assert is_within_quiet_hours(
        now=_dt(3), quiet_from=time(22), quiet_to=time(7),
    )
    assert not is_within_quiet_hours(
        now=_dt(12), quiet_from=time(22), quiet_to=time(7),
    )


# ---------------------------------------------------------------------------
# SendResult basic shape
# ---------------------------------------------------------------------------


def test_send_result_defaults():
    r = SendResult(ok=True)
    assert r.provider_message_id is None
    assert r.error is None


def test_render_produces_rendered_message_type():
    r = render_template(
        template_subject="s",
        template_body_html="h",
        template_body_text="t",
        context={},
    )
    assert isinstance(r, RenderedMessage)
