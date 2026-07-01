"""Notification delivery admin + user preferences (Section L).

Endpoints:
  Preferences (self):
    GET  /me/notifications/preferences
    PUT  /me/notifications/preferences
    GET  /me/notifications/quiet-hours
    PUT  /me/notifications/quiet-hours

  Admin (HR / Super Admin):
    GET  /notifications/providers            active provider status
    POST /notifications/test-send            send a sample
    GET  /notifications/templates            list
    POST /notifications/templates            create
    PUT  /notifications/templates/{id}       update
    POST /notifications/templates/seed       seed starter set (idempotent)
    GET  /notifications/deliveries           search delivery log
    POST /notifications/deliveries/{id}/resend
    GET  /notifications/dead-letter          all DEAD_LETTER rows
"""
from __future__ import annotations

from datetime import datetime, time, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import selectinload

from app.api import deps
from app.api.v1.endpoints.approval_chains import _is_hr_or_admin
from app.api.v1.endpoints.hr import log_audit
from app.models.notification_channel import (
    Channel, DeliveryStatus, DigestCadence, EventCategory,
    EVENT_CATEGORY_MAP,
    NotificationDelivery, NotificationTemplate,
    UserNotificationPreference, UserQuietHours,
)
from app.models.user import User
from app.services.notifications_delivery import (
    LogEmailProvider, get_email_provider, get_sms_provider,
    send_one_delivery,
)


router = APIRouter()


# ============================================================
# Preferences (self)
# ============================================================


class PreferenceIn(BaseModel):
    category: str
    channel: str
    enabled: bool
    digest_cadence: str = DigestCadence.IMMEDIATE


class PreferenceOut(BaseModel):
    id: int
    category: str
    channel: str
    enabled: bool
    digest_cadence: str


def _pref_dict(p: UserNotificationPreference) -> dict:
    return {
        "id": p.id, "category": p.category, "channel": p.channel,
        "enabled": p.enabled, "digest_cadence": p.digest_cadence,
    }


@router.get("/me/notifications/preferences")
async def get_my_preferences(
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    rows = (await db.execute(
        select(UserNotificationPreference).where(
            UserNotificationPreference.user_id == current_user.id
        )
    )).scalars().all()
    return [_pref_dict(p) for p in rows]


@router.put("/me/notifications/preferences")
async def upsert_my_preferences(
    payload: List[PreferenceIn],
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Bulk upsert: each item creates or updates the row identified by
    (user_id, category, channel). Not present = no change."""
    for p in payload:
        row = (await db.execute(
            select(UserNotificationPreference).where(and_(
                UserNotificationPreference.user_id == current_user.id,
                UserNotificationPreference.category == p.category,
                UserNotificationPreference.channel == p.channel,
            ))
        )).scalar_one_or_none()
        if row is None:
            row = UserNotificationPreference(
                user_id=current_user.id,
                category=p.category, channel=p.channel,
                enabled=p.enabled, digest_cadence=p.digest_cadence,
            )
            db.add(row)
        else:
            row.enabled = p.enabled
            row.digest_cadence = p.digest_cadence
    await db.commit()
    return await get_my_preferences(db, current_user=current_user)


class QuietHoursIn(BaseModel):
    quiet_from: Optional[time] = None
    quiet_to: Optional[time] = None
    hard_opt_out: bool = False


@router.get("/me/notifications/quiet-hours")
async def get_quiet_hours(
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    row = (await db.execute(
        select(UserQuietHours).where(
            UserQuietHours.user_id == current_user.id
        )
    )).scalar_one_or_none()
    if not row:
        return {
            "quiet_from": None, "quiet_to": None, "hard_opt_out": False,
        }
    return {
        "quiet_from": row.quiet_from,
        "quiet_to": row.quiet_to,
        "hard_opt_out": row.hard_opt_out,
    }


@router.put("/me/notifications/quiet-hours")
async def upsert_quiet_hours(
    payload: QuietHoursIn,
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    row = (await db.execute(
        select(UserQuietHours).where(
            UserQuietHours.user_id == current_user.id
        )
    )).scalar_one_or_none()
    if not row:
        row = UserQuietHours(user_id=current_user.id)
        db.add(row)
    row.quiet_from = payload.quiet_from
    row.quiet_to = payload.quiet_to
    row.hard_opt_out = payload.hard_opt_out
    await db.commit()
    return await get_quiet_hours(db, current_user=current_user)


# ============================================================
# Provider status
# ============================================================


@router.get("/notifications/providers")
async def provider_status(
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    if not _is_hr_or_admin(current_user):
        raise HTTPException(403, "HR/Admin only")
    e = get_email_provider()
    s = get_sms_provider()
    return {
        "email": {
            "provider": e.name,
            "is_dev": isinstance(e, LogEmailProvider),
        },
        "sms": {
            "provider": s.name,
            "is_dev": s.name == "log",
        },
        "hint": (
            "Set SMTP_HOST/PORT/USER/PASS/FROM in env to enable real email. "
            "Set MSG91_AUTH_KEY/MSG91_SENDER_ID for real SMS. "
            "Without creds the log provider prints to the app log."
        ),
    }


class TestSendIn(BaseModel):
    channel: str            # 'email' | 'sms'
    to: str
    subject: Optional[str] = None
    body: str = "This is a Section L test send from the ERP."
    dlt_template_id: Optional[str] = None


@router.post("/notifications/test-send")
async def test_send(
    payload: TestSendIn,
    request: Request,
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    if not _is_hr_or_admin(current_user):
        raise HTTPException(403, "HR/Admin only")
    if payload.channel == Channel.EMAIL:
        r = await get_email_provider().send(
            to=[payload.to],
            subject=payload.subject or "Test send",
            body_html=f"<p>{payload.body}</p>",
            body_text=payload.body,
        )
    elif payload.channel == Channel.SMS:
        r = await get_sms_provider().send(
            to=payload.to, body_text=payload.body,
            dlt_template_id=payload.dlt_template_id,
        )
    else:
        raise HTTPException(400, "channel must be 'email' or 'sms'")
    await log_audit(
        db, current_user.id, "notification_test_send",
        "notification_delivery", "*",
        {"channel": payload.channel, "to": payload.to, "ok": r.ok,
         "error": r.error, "message_id": r.provider_message_id},
        request,
    )
    return {
        "ok": r.ok, "message_id": r.provider_message_id, "error": r.error,
    }


# ============================================================
# Template CRUD
# ============================================================


class TemplateIn(BaseModel):
    event_type: str
    channel: str
    category: str = EventCategory.OTHER
    subject: Optional[str] = None
    body_html: Optional[str] = None
    body_text: str
    dlt_template_id: Optional[str] = None
    is_sensitive: bool = False
    is_active: bool = True


def _template_dict(t: NotificationTemplate) -> dict:
    return {
        "id": t.id, "event_type": t.event_type, "channel": t.channel,
        "category": t.category, "subject": t.subject,
        "body_html": t.body_html, "body_text": t.body_text,
        "dlt_template_id": t.dlt_template_id,
        "is_sensitive": t.is_sensitive,
        "is_active": t.is_active,
        "updated_at": t.updated_at,
    }


@router.get("/notifications/templates")
async def list_templates(
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    if not _is_hr_or_admin(current_user):
        raise HTTPException(403, "HR/Admin only")
    rows = (await db.execute(
        select(NotificationTemplate).order_by(
            NotificationTemplate.event_type, NotificationTemplate.channel
        )
    )).scalars().all()
    return [_template_dict(t) for t in rows]


@router.post("/notifications/templates")
async def create_template(
    payload: TemplateIn,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    if not _is_hr_or_admin(current_user):
        raise HTTPException(403, "HR/Admin only")
    t = NotificationTemplate(**payload.model_dump())
    db.add(t)
    await db.commit()
    await log_audit(
        db, current_user.id, "notification_template_create",
        "notification_template", str(t.id),
        payload.model_dump(), request,
    )
    return _template_dict(t)


@router.put("/notifications/templates/{template_id}")
async def update_template(
    template_id: int,
    payload: TemplateIn,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    if not _is_hr_or_admin(current_user):
        raise HTTPException(403, "HR/Admin only")
    t = await db.get(NotificationTemplate, template_id)
    if not t:
        raise HTTPException(404, "Template not found")
    for k, v in payload.model_dump().items():
        setattr(t, k, v)
    await db.commit()
    await log_audit(
        db, current_user.id, "notification_template_update",
        "notification_template", str(t.id),
        payload.model_dump(), request,
    )
    return _template_dict(t)


@router.post("/notifications/templates/seed")
async def seed_templates(
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    if not _is_hr_or_admin(current_user):
        raise HTTPException(403, "HR/Admin only")
    from app.services.notifications_seed import seed_starter_templates
    inserted = await seed_starter_templates(db)
    await log_audit(
        db, current_user.id, "notification_template_seed",
        "notification_template", "*",
        {"inserted": inserted}, request,
    )
    return {"inserted": inserted}


# ============================================================
# Delivery log + resend + dead-letter
# ============================================================


def _delivery_dict(d: NotificationDelivery) -> dict:
    return {
        "id": d.id, "notification_id": d.notification_id,
        "event_type": d.event_type,
        "recipient_user_id": d.recipient_user_id,
        "channel": d.channel, "status": d.status,
        "attempts": d.attempts,
        "provider_message_id": d.provider_message_id,
        "error": d.error,
        "next_retry_at": d.next_retry_at,
        "is_digest": d.is_digest,
        "digest_batch_key": d.digest_batch_key,
        "created_at": d.created_at, "sent_at": d.sent_at,
    }


@router.get("/notifications/deliveries")
async def list_deliveries(
    db: deps.DBDep,
    status: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
    recipient_user_id: Optional[int] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    if not _is_hr_or_admin(current_user):
        raise HTTPException(403, "HR/Admin only")
    stmt = select(NotificationDelivery)
    if status:
        stmt = stmt.where(NotificationDelivery.status == status)
    if event_type:
        stmt = stmt.where(NotificationDelivery.event_type == event_type)
    if recipient_user_id is not None:
        stmt = stmt.where(
            NotificationDelivery.recipient_user_id == recipient_user_id
        )
    stmt = stmt.order_by(NotificationDelivery.id.desc()).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    return [_delivery_dict(d) for d in rows]


@router.post("/notifications/deliveries/{delivery_id}/resend")
async def resend_delivery(
    delivery_id: int,
    db: deps.DBDep,
    request: Request,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    if not _is_hr_or_admin(current_user):
        raise HTTPException(403, "HR/Admin only")
    d = await db.get(NotificationDelivery, delivery_id)
    if not d:
        raise HTTPException(404, "Delivery not found")
    # Reset to QUEUED then invoke the sender inline.
    d.status = DeliveryStatus.QUEUED
    d.next_retry_at = None
    d.error = None
    await db.commit()
    result = await send_one_delivery(db, delivery_id)
    await log_audit(
        db, current_user.id, "notification_delivery_resend",
        "notification_delivery", str(delivery_id),
        {"ok": result.ok, "error": result.error}, request,
    )
    return {"ok": result.ok, "error": result.error,
            "message_id": result.provider_message_id}


@router.get("/notifications/dead-letter")
async def dead_letter(
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    if not _is_hr_or_admin(current_user):
        raise HTTPException(403, "HR/Admin only")
    rows = (await db.execute(
        select(NotificationDelivery).where(
            NotificationDelivery.status == DeliveryStatus.DEAD_LETTER
        ).order_by(NotificationDelivery.id.desc()).limit(500)
    )).scalars().all()
    return [_delivery_dict(d) for d in rows]
