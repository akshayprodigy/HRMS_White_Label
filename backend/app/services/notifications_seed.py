"""Starter template seed for the highest-value events.

`{...}` placeholders are interpolated at render time via
render_template(). Missing keys render as literal '{key}' so no send
ever fails on a variable mismatch.

Sensitive-content rule: templates for events that reference money
(payslip_published, salary_revised) carry `is_sensitive=True` — the
dispatcher strips money keys before render, so the emailed body
NEVER carries the figures. It links into the app instead.

DLT-template-id is REQUIRED on SMS templates for production India
sends. Deployment supplies the id per template row (via HR admin).
Log-provider dev sends ignore it.
"""
from __future__ import annotations

from typing import Any, Dict, List

from app.models.notification_channel import Channel, EventCategory


def _t(
    *,
    event_type: str, channel: str, category: str,
    subject: str = "", body_html: str = "", body_text: str = "",
    dlt_template_id: str | None = None,
    is_sensitive: bool = False,
) -> Dict[str, Any]:
    return {
        "event_type": event_type,
        "channel": channel,
        "category": category,
        "subject": subject,
        "body_html": body_html,
        "body_text": body_text,
        "dlt_template_id": dlt_template_id,
        "is_sensitive": is_sensitive,
    }


STARTER_TEMPLATES: List[Dict[str, Any]] = [
    # ---- Approvals ----
    _t(
        event_type="approval_pending", channel=Channel.EMAIL,
        category=EventCategory.APPROVALS,
        subject="Action required: {title}",
        body_html=(
            "<p>You have a new approval awaiting your action.</p>"
            "<p><b>{title}</b></p>"
            "<p>{message}</p>"
            "<p>Open the ERP to approve or reject.</p>"
        ),
        body_text=(
            "You have a new approval awaiting your action.\n"
            "{title}\n\n{message}\n\n"
            "Open the ERP to approve or reject."
        ),
    ),
    _t(
        event_type="approval_pending", channel=Channel.SMS,
        category=EventCategory.APPROVALS,
        body_text="New approval pending: {title}. Open the ERP to act.",
        dlt_template_id=None,   # deployment fills this
    ),

    # ---- Leave ----
    _t(
        event_type="leave_approved", channel=Channel.EMAIL,
        category=EventCategory.LEAVE,
        subject="Leave approved",
        body_html=(
            "<p>Your leave request has been approved.</p>"
            "<p>{message}</p>"
        ),
        body_text="Your leave request has been approved.\n{message}",
    ),
    _t(
        event_type="leave_rejected", channel=Channel.EMAIL,
        category=EventCategory.LEAVE,
        subject="Leave rejected",
        body_html=(
            "<p>Your leave request was rejected.</p>"
            "<p>{message}</p>"
        ),
        body_text="Your leave request was rejected.\n{message}",
    ),

    # ---- Payroll (SENSITIVE — link only, no figures) ----
    _t(
        event_type="payslip_published", channel=Channel.EMAIL,
        category=EventCategory.PAYROLL,
        subject="Your payslip is ready",
        body_html=(
            "<p>Your latest payslip is available.</p>"
            "<p>Open the ERP to view or download: "
            "<a href='/my-payslips'>My Payslips</a></p>"
        ),
        body_text=(
            "Your latest payslip is available. "
            "Open the ERP → My Payslips to view or download."
        ),
        is_sensitive=True,
    ),
    _t(
        event_type="salary_revised", channel=Channel.EMAIL,
        category=EventCategory.PAYROLL,
        subject="Your salary revision has been applied",
        body_html=(
            "<p>A salary revision has been applied to your record.</p>"
            "<p>Open the ERP to view the letter and effective dates: "
            "<a href='/my-revisions'>My Revisions</a></p>"
        ),
        body_text=(
            "A salary revision has been applied. "
            "Open the ERP → My Revisions for details."
        ),
        is_sensitive=True,
    ),

    # ---- Expense ----
    _t(
        event_type="expense_reimbursed", channel=Channel.EMAIL,
        category=EventCategory.EXPENSE,
        subject="Expense reimbursed",
        body_html=(
            "<p>Your expense claim has been reimbursed.</p>"
            "<p>{message}</p>"
        ),
        body_text="Your expense claim has been reimbursed.\n{message}",
    ),
    _t(
        event_type="expense_rejected", channel=Channel.EMAIL,
        category=EventCategory.EXPENSE,
        subject="Expense claim rejected",
        body_html=(
            "<p>Your expense claim was rejected.</p><p>{message}</p>"
        ),
        body_text="Your expense claim was rejected.\n{message}",
    ),

    # ---- Performance ----
    _t(
        event_type="review_released", channel=Channel.EMAIL,
        category=EventCategory.PERFORMANCE,
        subject="Your performance review is available",
        body_html=(
            "<p>Your performance review has been released.</p>"
            "<p>Open the ERP → Performance to view.</p>"
        ),
        body_text=(
            "Your performance review has been released. "
            "Open the ERP → Performance to view."
        ),
    ),

    # ---- Scheduled reports (Part 1 → real send here) ----
    _t(
        event_type="report_scheduled", channel=Channel.EMAIL,
        category=EventCategory.OTHER,
        subject="{title}",
        body_html=(
            "<p>{message}</p>"
            "<p>Open the report inside the ERP.</p>"
        ),
        body_text="{message}",
    ),

    # ---- Statutory ----
    _t(
        event_type="statutory_due", channel=Channel.EMAIL,
        category=EventCategory.STATUTORY,
        subject="Statutory filing due: {title}",
        body_html=(
            "<p>{message}</p>"
            "<p>Open the ERP → Statutory Filings.</p>"
        ),
        body_text="{message}\nOpen the ERP → Statutory Filings.",
    ),
]


async def seed_starter_templates(session) -> int:
    """Insert every STARTER_TEMPLATES row not already present (by
    event_type+channel). Returns the number inserted."""
    from sqlalchemy import select
    from app.models.notification_channel import NotificationTemplate

    existing = {
        (r.event_type, r.channel)
        for r in (await session.execute(
            select(NotificationTemplate)
        )).scalars().all()
    }
    inserted = 0
    for spec in STARTER_TEMPLATES:
        key = (spec["event_type"], spec["channel"])
        if key in existing:
            continue
        session.add(NotificationTemplate(**spec))
        inserted += 1
    await session.commit()
    return inserted
