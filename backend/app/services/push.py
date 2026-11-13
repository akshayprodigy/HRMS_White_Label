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
Android: emergency pushes (broadcasts) are sent with channelId "emergency",
so the app MUST create an Android notification channel with that exact id
(max importance), or they fall back to the default channel.
Lock-screen privacy: pushes for payroll/expense/statutory/performance events
and for events with a sensitive template carry the generic title "New update"
and body "Open the app to view details."; the full text stays in-app.
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
EXPO_RECEIPTS_URL = "https://exp.host/--/api/v2/push/getReceipts"
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
    # Tokens the gateway accepted, with their ticket ids (token, ticket_id).
    ok_tokens: List[str] = field(default_factory=list)
    tickets: List[tuple] = field(default_factory=list)
    # True if some token hit a retryable error (HTTP/parse/ticket error).
    transient: bool = False


class PushProvider:
    name = "abstract"

    async def send(
        self, *, tokens: List[str], title: str, body: str,
        data: Dict[str, Any], category: Optional[str] = None,
        priority: str = "default",
    ) -> PushResult:
        raise NotImplementedError

    async def fetch_receipts(self, ticket_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """ticket id -> {"status": "ok"|"error", "error": str|None}. Tickets
        without a receipt yet are absent."""
        return {}


class LogPushProvider(PushProvider):
    name = "log"

    async def send(self, *, tokens, title, body, data, category=None,
                   priority="default") -> PushResult:
        log.info("[LogPushProvider] tokens=%d title=%r category=%s data=%s",
                 len(tokens), title, category, data)
        return PushResult(ok=True, provider_message_id=f"log-push-{id(self)}",
                          ok_tokens=list(tokens))


class ExpoPushProvider(PushProvider):
    name = "expo"

    def __init__(self, *, access_token: Optional[str] = None,
                 url: str = EXPO_URL, transport: Any = None,
                 receipts_url: str = EXPO_RECEIPTS_URL):
        self.access_token = access_token
        self.url = url
        self.receipts_url = receipts_url
        self.transport = transport  # httpx transport; tests inject a mock

    async def send(self, *, tokens, title, body, data, category=None,
                   priority="default") -> PushResult:
        import httpx
        headers = {"accept": "application/json",
                   "content-type": "application/json"}
        if self.access_token:
            headers["authorization"] = f"Bearer {self.access_token}"
        invalid: List[str] = []
        ok_tokens: List[str] = []
        tickets: List[tuple] = []
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
                        tks = r.json().get("data") or []
                    except Exception:
                        errors.append("expo: unparseable response")
                        continue
                    for idx, tok in enumerate(chunk):
                        tk = tks[idx] if idx < len(tks) else None
                        if tk is None:
                            errors.append(f"missing ticket for a token")
                            continue
                        if tk.get("status") == "ok":
                            ok_tokens.append(tok)
                            if tk.get("id"):
                                tickets.append((tok, str(tk["id"])))
                            continue
                        err = (tk.get("details") or {}).get("error")
                        if err == "DeviceNotRegistered":
                            invalid.append(tok)
                        else:
                            errors.append(
                                f"{err or 'error'}: {tk.get('message', '')}"[:200])
        except Exception as e:  # pragma: no cover
            return PushResult(ok=False, error=f"{type(e).__name__}: {e}",
                              invalid_tokens=invalid, ok_tokens=ok_tokens,
                              tickets=tickets, transient=True)
        err = "; ".join(errors)[:500] or None
        if not ok_tokens and invalid and not errors:
            err = "all tokens unregistered"
        return PushResult(
            ok=bool(ok_tokens),
            provider_message_id=(",".join(t for _, t in tickets)[:120]
                                 or ("ok" if ok_tokens else None)),
            error=err, invalid_tokens=invalid, ok_tokens=ok_tokens,
            tickets=tickets, transient=bool(errors))

    async def fetch_receipts(self, ticket_ids):
        import httpx
        out: Dict[str, Dict[str, Any]] = {}
        headers = {"accept": "application/json",
                   "content-type": "application/json"}
        if self.access_token:
            headers["authorization"] = f"Bearer {self.access_token}"
        async with httpx.AsyncClient(
                timeout=15.0, transport=self.transport) as c:
            for i in range(0, len(ticket_ids), 300):
                r = await c.post(
                    self.receipts_url, headers=headers,
                    json={"ids": ticket_ids[i:i + 300]})
                if r.status_code >= 400:
                    continue
                for tid, rc in (r.json().get("data") or {}).items():
                    out[tid] = {"status": rc.get("status"),
                                "error": (rc.get("details") or {}).get("error")}
        return out


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


# ---------------------------------------------------------------------------
# Receipts (Expo): detect DeviceNotRegistered that only shows up post-hoc
# ---------------------------------------------------------------------------

RECEIPT_MAX_AGE_HOURS = 24


async def poll_receipts(session: AsyncSession, now: Optional[datetime] = None) -> Dict[str, int]:
    import json
    from datetime import timedelta
    from app.models.notification_channel import Channel, NotificationDelivery

    now = now or datetime.now(timezone.utc)
    rows = (await session.execute(
        select(NotificationDelivery).where(
            NotificationDelivery.channel == Channel.PUSH,
            NotificationDelivery.provider_ticket_ids.is_not(None)).limit(500)
    )).scalars().all()
    by_ticket: Dict[str, tuple] = {}
    parsed: Dict[int, list] = {}
    for r in rows:
        try:
            pairs = json.loads(r.provider_ticket_ids or "[]")
        except Exception:
            pairs = []
        parsed[r.id] = pairs
        for tok, tid in pairs:
            by_ticket[tid] = (r.id, tok)
    receipts = {}
    if by_ticket:
        receipts = await get_push_provider().fetch_receipts(list(by_ticket))
    revoked: List[str] = []
    done = 0
    for r in rows:
        keep = []
        sent_at = r.sent_at or r.created_at
        if sent_at is not None and sent_at.tzinfo is None:
            sent_at = sent_at.replace(tzinfo=timezone.utc)
        expired = sent_at is not None and now - sent_at > timedelta(hours=RECEIPT_MAX_AGE_HOURS)
        for tok, tid in parsed[r.id]:
            rc = receipts.get(tid)
            if rc is None:
                if not expired:
                    keep.append([tok, tid])
                continue
            done += 1
            if rc.get("status") == "error" and rc.get("error") == "DeviceNotRegistered":
                revoked.append(tok)
        r.provider_ticket_ids = json.dumps(keep) if keep else None
    await revoke_tokens(session, revoked)
    await session.commit()
    return {"checked": done, "revoked": len(set(revoked))}
