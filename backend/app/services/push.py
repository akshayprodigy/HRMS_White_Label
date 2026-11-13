"""Mobile push (Roadmap v2 Phase 3, Task 1).

Providers: `log` (default, sends nothing) and `expo` (Expo Push Service).
Delivery rows for the PUSH channel are created by
`notifications_delivery.dispatch_notification` and sent by the normal
`send_queued_notifications` job via `send_one_delivery`.

Push `data` payload contract (mobile app):
  {
    "notification_id": int,        # Notification row; the action endpoint key
    "event_type": str | null,
    "resource_type": str | null,
    "resource_id": str | null,
    "category": "approval" | "open_shift" | "broadcast_safety"
                | "broadcast_ack" | "none",
    "actions": [str, ...]          # action ids valid for `category`
  }
Action ids: approval -> approve, reject; open_shift -> claim;
broadcast_safety -> safe, need_help; broadcast_ack -> acknowledge.
Actions are performed with POST /notifications/actions.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)

EXPO_URL = "https://exp.host/--/api/v2/push/send"
EXPO_BATCH = 100
PUSH_BODY_MAX = 178

CATEGORY_ACTIONS: Dict[str, List[str]] = {
    "approval": ["approve", "reject"],
    "open_shift": ["claim"],
    "broadcast_safety": ["safe", "need_help"],
    "broadcast_ack": ["acknowledge"],
    "none": [],
}


@dataclass
class PushResult:
    ok: bool
    provider_message_id: Optional[str] = None
    error: Optional[str] = None
    # Tokens the gateway says are dead (DeviceNotRegistered): revoke them.
    invalid_tokens: List[str] = field(default_factory=list)


class PushProvider:
    name = "abstract"

    async def send(
        self, *, tokens: List[str], title: str, body: str,
        data: Dict[str, Any], category: Optional[str] = None,
        priority: str = "default",
    ) -> PushResult:
        raise NotImplementedError


class LogPushProvider(PushProvider):
    name = "log"

    async def send(self, *, tokens, title, body, data, category=None,
                   priority="default") -> PushResult:
        log.info("[LogPushProvider] tokens=%d title=%r category=%s data=%s",
                 len(tokens), title, category, data)
        return PushResult(ok=True, provider_message_id=f"log-push-{id(self)}")


class ExpoPushProvider(PushProvider):
    name = "expo"

    def __init__(self, *, access_token: Optional[str] = None,
                 url: str = EXPO_URL, transport: Any = None):
        self.access_token = access_token
        self.url = url
        self.transport = transport  # httpx transport; tests inject a mock

    async def send(self, *, tokens, title, body, data, category=None,
                   priority="default") -> PushResult:
        import httpx
        headers = {"accept": "application/json",
                   "content-type": "application/json"}
        if self.access_token:
            headers["authorization"] = f"Bearer {self.access_token}"
        invalid: List[str] = []
        ok_ids: List[str] = []
        errors: List[str] = []
        try:
            async with httpx.AsyncClient(
                    timeout=15.0, transport=self.transport) as c:
                for i in range(0, len(tokens), EXPO_BATCH):
                    chunk = tokens[i:i + EXPO_BATCH]
                    msgs = []
                    for t in chunk:
                        m: Dict[str, Any] = {
                            "to": t, "title": title, "body": body,
                            "data": data, "sound": "default",
                            "priority": "high" if priority == "high"
                            else "default",
                        }
                        if category and category != "none":
                            m["categoryId"] = category
                        if priority == "high":
                            m["interruptionLevel"] = "time-sensitive"
                            m["channelId"] = "emergency"
                        msgs.append(m)
                    try:
                        r = await c.post(self.url, headers=headers, json=msgs)
                    except Exception as e:
                        errors.append(f"{type(e).__name__}: {e}")
                        continue
                    if r.status_code >= 400:
                        errors.append(
                            f"expo http {r.status_code}: {r.text[:200]}")
                        continue
                    try:
                        tickets = r.json().get("data") or []
                    except Exception:
                        errors.append("expo: unparseable response")
                        continue
                    for tok, tk in zip(chunk, tickets):
                        if tk.get("status") == "ok":
                            if tk.get("id"):
                                ok_ids.append(str(tk["id"]))
                            else:
                                ok_ids.append("ok")
                            continue
                        err = (tk.get("details") or {}).get("error")
                        if err == "DeviceNotRegistered":
                            invalid.append(tok)
                        else:
                            errors.append(
                                f"{err or 'error'}: {tk.get('message', '')}"[:200])
        except Exception as e:  # pragma: no cover
            return PushResult(ok=False, error=f"{type(e).__name__}: {e}",
                              invalid_tokens=invalid)
        if ok_ids:
            return PushResult(
                ok=True, provider_message_id=",".join(ok_ids)[:120],
                invalid_tokens=invalid)
        if invalid and not errors:
            return PushResult(ok=False, error="all tokens unregistered",
                              invalid_tokens=invalid)
        return PushResult(ok=False, error="; ".join(errors)[:500] or "no tickets",
                          invalid_tokens=invalid)


_push_provider: PushProvider = LogPushProvider()


def set_push_provider(p: PushProvider) -> None:
    global _push_provider
    _push_provider = p


def get_push_provider() -> PushProvider:
    return _push_provider


def provider_from_settings() -> PushProvider:
    from app.core.config import settings
    if (settings.PUSH_PROVIDER or "log").lower() == "expo":
        return ExpoPushProvider(access_token=settings.EXPO_ACCESS_TOKEN)
    return LogPushProvider()


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------


async def active_tokens(session: AsyncSession, user_id: int) -> List[str]:
    from app.models.device import DeviceToken
    return list((await session.execute(
        select(DeviceToken.token).where(
            DeviceToken.user_id == user_id,
            DeviceToken.revoked_at.is_(None)).order_by(DeviceToken.id)
    )).scalars().all())


async def users_with_tokens(session: AsyncSession, user_ids) -> set:
    from app.models.device import DeviceToken
    ids = list(user_ids)
    if not ids:
        return set()
    return set((await session.execute(
        select(DeviceToken.user_id).distinct().where(
            DeviceToken.user_id.in_(ids),
            DeviceToken.revoked_at.is_(None))
    )).scalars().all())


async def revoke_tokens(session: AsyncSession, tokens: List[str]) -> None:
    from app.models.device import DeviceToken
    if not tokens:
        return
    now = datetime.now(timezone.utc)
    for d in (await session.execute(select(DeviceToken).where(
            DeviceToken.token.in_(tokens),
            DeviceToken.revoked_at.is_(None)))).scalars().all():
        d.revoked_at = now


# ---------------------------------------------------------------------------
# Actionable payload
# ---------------------------------------------------------------------------


async def action_category(session: AsyncSession, n) -> str:
    """State-based: which action set (if any) is currently valid for this
    notification's recipient. Never trusts anything but the Notification row
    and live DB state."""
    rtype, rid = n.resource_type, n.resource_id
    if not rtype or not rid:
        return "none"
    try:
        if rtype == "broadcast":
            if n.event_type != "emergency_broadcast":
                return "none"
            from app.models.broadcast import Broadcast, BroadcastRecipient
            b = await session.get(Broadcast, int(rid))
            if b is None or b.closed_at is not None:
                return "none"
            r = (await session.execute(select(BroadcastRecipient).where(
                BroadcastRecipient.broadcast_id == b.id,
                BroadcastRecipient.user_id == n.user_id))).scalar_one_or_none()
            if r is None:
                return "none"
            if b.safety_check:
                return "broadcast_safety"
            if b.requires_ack:
                return "broadcast_ack"
            return "none"
        if rtype == "open_shift":
            if n.event_type != "open_shift_available":
                return "none"
            from app.models.open_shift import OpenShift, OpenShiftStatus
            s = await session.get(OpenShift, int(rid))
            return ("open_shift" if s is not None
                    and s.status == OpenShiftStatus.OPEN else "none")
        if await find_approval_target(session, n) is not None:
            return "approval"
    except Exception:  # never let payload building break a send
        log.warning("action category failed for notification %s", n.id,
                    exc_info=True)
    return "none"


async def find_approval_target(session: AsyncSession, n, *, strict: bool = True):
    """('legacy'|'chain', id) of the pending approval a notification refers
    to. strict=True (offering actions): only if the recipient holds the
    current step directly or by role. strict=False (action endpoint): any
    pending match; the approval service then does the real authorisation
    (delegation, admin override, SoD)."""
    from app.models.approval import ApprovalItem, ApprovalStatus, ApprovalStep
    from app.models.approval_chain import (
        ChainedApprovalInstance, ChainedApprovalStepInstance,
    )
    from app.models.user import Role, User
    from sqlalchemy.orm import selectinload

    rtype, rid = n.resource_type, n.resource_id
    if rtype in ("broadcast", "open_shift", "approver_delegation"):
        return None
    if rtype == "chained_approval_instance":
        try:
            iid = int(rid)
        except (TypeError, ValueError):
            return None
        inst = await session.get(ChainedApprovalInstance, iid)
        if inst is None or inst.status != "pending":
            return None
        row = (await session.execute(select(
            ChainedApprovalStepInstance.id).where(
            ChainedApprovalStepInstance.instance_id == iid,
            ChainedApprovalStepInstance.step_order == inst.current_step_order,
            ChainedApprovalStepInstance.status == "pending",
            ChainedApprovalStepInstance.approver_user_id == n.user_id,
        ).limit(1))).first()
        return ("chain", iid) if (row or not strict) else None
    user = (await session.execute(select(User).where(User.id == n.user_id)
            .options(selectinload(User.roles)))).scalar_one_or_none()
    if user is None:
        return None
    role_ids = [r.id for r in user.roles]
    items = (await session.execute(
        select(ApprovalItem).where(
            ApprovalItem.resource_type == rtype,
            ApprovalItem.resource_id == str(rid),
            ApprovalItem.status == ApprovalStatus.PENDING)
        .order_by(ApprovalItem.id.desc()).options(
            selectinload(ApprovalItem.steps)))).scalars().all()
    for it in items:
        st = next((s for s in it.steps
                   if s.step_number == it.current_step_number), None)
        if st is None or st.status != ApprovalStatus.PENDING:
            continue
        if not strict:
            return ("legacy", it.id)
        if st.approver_id == user.id or (st.role_id and st.role_id in role_ids):
            return ("legacy", it.id)
    return None


async def build_payload(session: AsyncSession, n) -> Dict[str, Any]:
    cat = await action_category(session, n)
    return {
        "notification_id": n.id,
        "event_type": n.event_type,
        "resource_type": n.resource_type,
        "resource_id": n.resource_id,
        "category": cat,
        "actions": list(CATEGORY_ACTIONS[cat]),
    }
