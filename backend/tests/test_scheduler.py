"""Unit tests for the scheduler registry + email-sender stub (Section K Item 4)."""
import asyncio

import pytest

from app.services.scheduler import (
    EmailSender, JobSpec, REGISTRY, get_email_sender, register_job,
    set_email_sender,
)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_three_baseline_jobs_registered():
    """The 3 jobs called out in the spec (apply-due, deliver reports,
    ESIC continuation) must self-register at import time so a fresh
    scheduler startup finds them."""
    for name in (
        "apply_due_revisions",
        "deliver_scheduled_reports",
        "esic_continuation_detect",
    ):
        assert name in REGISTRY, f"job {name!r} missing"


def test_registered_jobs_have_valid_cron_and_display_name():
    for name, spec in REGISTRY.items():
        assert spec.display_name
        assert spec.default_cadence_cron
        # Cadence is space-separated 5-field cron (compat with CronTrigger).
        parts = spec.default_cadence_cron.split()
        assert len(parts) == 5, f"{name} cron has wrong field count"


def test_register_job_replaces_existing_by_name():
    async def dummy(_):
        return {"ok": True}
    prior = REGISTRY.get("apply_due_revisions")
    register_job(JobSpec(
        name="apply_due_revisions",
        display_name="test override",
        description="test",
        default_cadence_cron="* * * * *",
        fn=dummy,
    ))
    assert REGISTRY["apply_due_revisions"].display_name == "test override"
    # Restore for other tests.
    if prior is not None:
        register_job(prior)


# ---------------------------------------------------------------------------
# EmailSender stub — Part 2 replaces this
# ---------------------------------------------------------------------------


def test_default_email_sender_is_stub():
    sender = get_email_sender()
    assert isinstance(sender, EmailSender)


def test_email_sender_routes_via_provider_layer():
    """Post-Section-L: the default EmailSender is a shim over the
    notifications-delivery provider (log provider by default in dev),
    which returns ok=True. Tests exercising 'real delivery failed'
    swap in a failing provider — see test_notifications_delivery.
    """
    sender = get_email_sender()
    ok = asyncio.run(sender.send(
        to=["hr@example.com"], subject="test", body_html="hello",
    ))
    assert ok is True


def test_set_email_sender_swaps_the_transport():
    class TestSender(EmailSender):
        async def send(self, **kwargs):
            return True

    original = get_email_sender()
    try:
        set_email_sender(TestSender())
        assert isinstance(get_email_sender(), TestSender)
        ok = asyncio.run(get_email_sender().send(
            to=["x@y"], subject="t", body_html="b",
        ))
        assert ok is True
    finally:
        set_email_sender(original)


# ---------------------------------------------------------------------------
# Idempotency contract — every job is safe to re-run
# ---------------------------------------------------------------------------


def test_every_registered_job_has_a_callable_fn():
    for name, spec in REGISTRY.items():
        assert callable(spec.fn), (
            f"job {name!r} has non-callable fn — scheduler cannot run it"
        )


def test_job_specs_carry_a_description():
    for name, spec in REGISTRY.items():
        assert spec.description, (
            f"job {name!r} missing description — admin UI needs it"
        )
