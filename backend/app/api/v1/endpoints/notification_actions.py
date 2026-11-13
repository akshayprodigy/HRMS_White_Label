"""Actionable push notifications (Roadmap v2 Phase 3, Task 1).

POST /notifications/actions routes a push action button to the SAME service
function the normal endpoint uses, with the caller's own auth, so every
permission / SoD / delegation / ownership check still applies. The only
thing trusted from the client is the notification id, and that row must be
owned by the caller. Mounted without the attendance gate (broadcast
responses must work before punching in); approval and open-shift actions
re-apply the gate explicitly to match their normal endpoints.
"""
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api import deps
from app.models.approval import ApprovalItem, ApprovalStatus
from app.models.notification import Notification
from app.schemas.approval import ApprovalAction
from app.services import push as push_svc

router = APIRouter()

APPROVAL_ACTIONS = ("approve", "reject")
BROADCAST_ACTIONS = ("safe", "need_help", "acknowledge")


class NotificationActionIn(BaseModel):
    notification_id: int
    action: Literal["approve", "reject", "claim", "safe", "need_help",
                    "acknowledge"]
    comment: Optional[str] = Field(default=None, max_length=500)


@router.post("/actions")
async def notification_action(
    body: NotificationActionIn, request: Request, db: deps.DBDep,
    me: deps.CurrentUser,
):
    n = await db.get(Notification, body.notification_id)
    if n is None or n.user_id != me.id:
        raise HTTPException(404, "Notification not found")
    nid, rtype, rid = n.id, n.resource_type, n.resource_id
    action = body.action
    if not rtype or not rid:
        raise HTTPException(400, "This notification has no actionable target")

    if action in APPROVAL_ACTIONS:
        if rtype in ("broadcast", "open_shift"):
            raise HTTPException(400, "Action not valid for this notification")
        await deps.verify_attendance(db, me)
        target = await push_svc.find_approval_target(db, n, strict=False)
        if target is None:
            raise HTTPException(
                400, "This approval is no longer pending")
        kind, tid = target
        if kind == "legacy":
            from app.api.v1.endpoints.approvals import action_approval
            await action_approval(
                tid, ApprovalAction(
                    status=(ApprovalStatus.APPROVED if action == "approve"
                            else ApprovalStatus.REJECTED),
                    comment=body.comment), db, me)
            st = (await db.execute(select(ApprovalItem.status).where(
                ApprovalItem.id == tid))).scalar_one()
            result = {"status": getattr(st, "value", st)}
        else:
            from app.api.v1.endpoints.approval_chains import act_on_instance
            res = await act_on_instance(
                db, tid, action, body.comment, request, me)
            result = res if isinstance(res, dict) else {}
        out = {"type": "approval", "kind": kind, "id": tid}
    elif action == "claim":
        if rtype != "open_shift":
            raise HTTPException(400, "Action not valid for this notification")
        await deps.verify_attendance(db, me)
        from app.api.v1.endpoints.roster_open_shifts import claim_open_shift
        try:
            sid = int(rid)
        except ValueError:
            raise HTTPException(400, "Invalid open shift reference")
        r = await claim_open_shift(
            db=db, request=request, shift_id=sid, current_user=me)
        result = r.model_dump(mode="json")
        out = {"type": "open_shift", "kind": "open_shift", "id": sid}
    else:  # safe / need_help / acknowledge
        if rtype != "broadcast":
            raise HTTPException(400, "Action not valid for this notification")
        try:
            bid = int(rid)
        except ValueError:
            raise HTTPException(400, "Invalid broadcast reference")
        from app.api.v1.endpoints import broadcasts as bc
        if action == "acknowledge":
            result = await bc.acknowledge(bid, db, me)
        else:
            result = await bc.mark_safety(
                bid, bc.SafetyIn(status=action, note=body.comment), db, me)
        out = {"type": "broadcast", "kind": "broadcast", "id": bid}

    # Best-effort: the action was taken, so the notification is read.
    try:
        n2 = await db.get(Notification, nid)
        if n2 is not None and not n2.is_read:
            n2.is_read = True
            await db.commit()
    except Exception:  # pragma: no cover
        await db.rollback()
    return {"notification_id": nid, "action": action, "target": out,
            "result": result}
