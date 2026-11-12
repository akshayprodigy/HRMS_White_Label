"""Bulk approve/reject (Roadmap v2 Phase 2, Task 6)."""
from datetime import date

from sqlalchemy import select

from _appr_world import (  # noqa: F401
    client, login, mk_chain, mk_delegation, mk_item, world,
)
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.approval import ApprovalItem, ApprovalStatus, ApprovalStep
from app.models.approval_chain import ChainedApprovalInstance
from app.models.leave import LeaveBalanceLedger, LeaveRequest, LeaveStatus

API = settings.API_V1_STR
URL = f"{API}/approvals/bulk-action"


async def test_mixed_results(client, world):
    ids = world["ids"]
    a1, _ = await mk_item(world, "apr")
    a2, _ = await mk_item(world, "apr")
    foreign, _ = await mk_item(world, "oth")          # not mine -> 403
    own, _ = await mk_item(world, "apr", requester="apr")  # SoD -> 403
    inst, _s = await mk_chain(world, "apr")
    ha = await login(client, world, "apr")
    r = await client.post(URL, headers=ha, json={
        "action": "approve", "comment": "bulk",
        "items": [{"kind": "legacy", "id": a1}, {"kind": "legacy", "id": a2},
                  {"kind": "legacy", "id": foreign},
                  {"kind": "legacy", "id": own},
                  {"kind": "legacy", "id": 999999999},
                  {"kind": "chain", "id": inst},
                  {"kind": "chain", "id": 999999999},
                  {"kind": "legacy", "id": a1},       # duplicate
                  {"kind": "bogus", "id": 1}]})
    assert r.status_code == 200, r.text
    res = r.json()["results"]
    ok = [x["ok"] for x in res]
    assert ok == [True, True, False, False, False, True, False, False, False]
    assert all(x["error"] for x in res if not x["ok"])
    assert r.json()["ok_count"] == 3 and r.json()["failed_count"] == 6
    async with SessionLocal() as db:
        for i in (a1, a2):
            it = await db.get(ApprovalItem, i)
            assert it.status == ApprovalStatus.APPROVED
        assert (await db.get(ApprovalItem, foreign)).status \
            == ApprovalStatus.PENDING
        inst_row = await db.get(ChainedApprovalInstance, inst)
        assert inst_row.status == "approved"


async def test_bulk_reject_and_delegate_items(client, world):
    ids = world["ids"]
    mine, _ = await mk_item(world, "dlg")
    acting, _ = await mk_item(world, "apr")
    await mk_delegation(world, "apr", "dlg")
    hd = await login(client, world, "dlg")
    r = await client.post(URL, headers=hd, json={
        "action": "reject",
        "items": [{"kind": "legacy", "id": mine},
                  {"kind": "legacy", "id": acting}]})
    assert [x["ok"] for x in r.json()["results"]] == [True, True]
    async with SessionLocal() as db:
        assert (await db.get(ApprovalItem, acting)).status \
            == ApprovalStatus.REJECTED


async def test_leave_via_shared_service(client, world):
    ids = world["ids"]
    async with SessionLocal() as db:
        lv = LeaveRequest(
            employee_id=ids["req"], leave_type_id=ids["lt"],
            start_date=date(2031, 4, 7), end_date=date(2031, 4, 8),
            reason="t", status=LeaveStatus.SUBMITTED,
            created_by_user_id=ids["req"])
        db.add(lv)
        await db.flush()
        item = ApprovalItem(resource_type="leave_request",
                            resource_id=str(lv.id),
                            status=ApprovalStatus.PENDING,
                            current_step_number=1,
                            requested_by_id=ids["req"])
        db.add(item)
        await db.flush()
        db.add(ApprovalStep(approval_item_id=item.id, step_number=1,
                            approver_id=ids["apr"],
                            status=ApprovalStatus.PENDING))
        await db.commit()
        iid, lid = item.id, lv.id
    ha = await login(client, world, "apr")
    r = await client.post(URL, headers=ha, json={
        "action": "approve", "items": [{"kind": "legacy", "id": iid}]})
    assert r.json()["results"][0]["ok"], r.text
    async with SessionLocal() as db:
        assert (await db.get(LeaveRequest, lid)).status == LeaveStatus.APPROVED
        led = (await db.execute(select(LeaveBalanceLedger).where(
            LeaveBalanceLedger.user_id == ids["req"]))).scalars().first()
        assert led.used == 2.0
    # second pass: already actioned -> error, ledger not double-debited
    r = await client.post(URL, headers=ha, json={
        "action": "approve", "items": [{"kind": "legacy", "id": iid}]})
    assert r.json()["results"][0]["ok"] is False
    async with SessionLocal() as db:
        led = (await db.execute(select(LeaveBalanceLedger).where(
            LeaveBalanceLedger.user_id == ids["req"]))).scalars().first()
        assert led.used == 2.0


async def test_limits_and_validation(client, world):
    ha = await login(client, world, "apr")
    big = [{"kind": "legacy", "id": i} for i in range(101)]
    assert (await client.post(URL, headers=ha, json={
        "action": "approve", "items": big})).status_code == 400
    assert (await client.post(URL, headers=ha, json={
        "action": "approve", "items": []})).status_code == 400
    assert (await client.post(URL, headers=ha, json={
        "action": "maybe", "items": [{"kind": "legacy", "id": 1}]
    })).status_code == 400
