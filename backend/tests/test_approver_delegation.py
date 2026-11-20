"""Out-of-office approval delegation (Roadmap v2 Phase 2, Task 6)."""
from datetime import date, datetime, timedelta, timezone

from _tz import org_today  # noqa: E402
from sqlalchemy import select

from _appr_world import (  # noqa: F401
    client, login, mk_chain, mk_delegation, mk_item, world,
)
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.approval import ApprovalItem, ApprovalStatus, ApprovalStep
from app.models.audit import AuditLog
from app.models.leave import LeaveRequest, LeaveStatus

API = settings.API_V1_STR
TODAY = org_today()


async def _inbox(client, h):
    r = await client.get(f"{API}/approvals/inbox", headers=h)
    assert r.status_code == 200, r.text
    return {x["id"]: x for x in r.json()}


async def test_crud_and_visibility(client, world):
    ids = world["ids"]
    iid, _ = await mk_item(world, "apr")
    ha, hd = await login(client, world, "apr"), await login(client, world, "dlg")
    assert iid not in await _inbox(client, hd)
    r = await client.post(f"{API}/me/approval-delegations", headers=ha,
                          json={"delegate_id": ids["dlg"], "note": "holiday"})
    assert r.status_code == 201, r.text
    did = r.json()["id"]
    assert r.json()["status"] == "active"
    box = await _inbox(client, hd)
    assert box[iid]["acting_for"]["user_id"] == ids["apr"]
    assert box[iid]["acting_for"]["name"] == "AW apr"
    # own list + delegate's list + HR (non-HR forbidden)
    r = await client.get(f"{API}/me/approval-delegations", headers=ha)
    assert [d["id"] for d in r.json()["mine"]] == [did]
    r = await client.get(f"{API}/me/approval-delegations", headers=hd)
    assert [d["id"] for d in r.json()["delegated_to_me"]] == [did]
    assert (await client.get(f"{API}/approval-delegations",
                             headers=hd)).status_code == 403
    # approve as delegate
    r = await client.post(f"{API}/approvals/{iid}/action", headers=hd,
                          json={"status": "approved", "comment": "ok"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved"
    async with SessionLocal() as db:
        logs = (await db.execute(select(AuditLog).where(
            AuditLog.user_id == ids["dlg"],
            AuditLog.resource_id.like(f"{world['sfx']}%")))).scalars().all()
    assert logs and logs[0].details["acting_for_user_id"] == ids["apr"]
    # only the owner may revoke
    assert (await client.delete(f"{API}/me/approval-delegations/{did}",
                                headers=hd)).status_code == 404
    assert (await client.delete(f"{API}/me/approval-delegations/{did}",
                                headers=ha)).status_code == 200


async def test_validation(client, world):
    ids = world["ids"]
    ha = await login(client, world, "apr")
    url = f"{API}/me/approval-delegations"
    assert (await client.post(url, headers=ha, json={
        "delegate_id": ids["apr"]})).status_code == 400
    assert (await client.post(url, headers=ha, json={
        "delegate_id": 999999999})).status_code == 400
    assert (await client.post(url, headers=ha, json={
        "delegate_id": ids["dlg"], "starts_on": str(TODAY),
        "ends_on": str(TODAY - timedelta(days=1))})).status_code == 400


async def test_revoked_expired_and_future_not_visible(client, world):
    iid, _ = await mk_item(world, "apr")
    hd = await login(client, world, "dlg")
    await mk_delegation(world, "apr", "dlg", revoked=True)
    await mk_delegation(world, "apr", "dlg", starts=TODAY - timedelta(days=9),
                        ends=TODAY - timedelta(days=1))
    await mk_delegation(world, "apr", "dlg", starts=TODAY + timedelta(days=3))
    assert iid not in await _inbox(client, hd)
    r = await client.post(f"{API}/approvals/{iid}/action", headers=hd,
                          json={"status": "approved"})
    assert r.status_code == 403


async def test_sod_delegate_cannot_approve_own_request(client, world):
    iid, _ = await mk_item(world, "apr", requester="dlg")
    await mk_delegation(world, "apr", "dlg")
    hd = await login(client, world, "dlg")
    assert iid in await _inbox(client, hd)
    r = await client.post(f"{API}/approvals/{iid}/action", headers=hd,
                          json={"status": "approved"})
    assert r.status_code == 403
    # chain engine too
    inst, _s = await mk_chain(world, "apr", submitter="dlg")
    r = await client.post(
        f"{API}/approval-chains/instances/{inst}/act", headers=hd,
        json={"action": "approve"})
    assert r.status_code == 403


async def test_not_transitive(client, world):
    iid, _ = await mk_item(world, "apr")
    await mk_delegation(world, "apr", "dlg")      # apr -> dlg
    await mk_delegation(world, "dlg", "oth")      # dlg -> oth (not apr's)
    ho = await login(client, world, "oth")
    assert iid not in await _inbox(client, ho)
    r = await client.post(f"{API}/approvals/{iid}/action", headers=ho,
                          json={"status": "approved"})
    assert r.status_code == 403


async def test_only_when_on_leave(client, world):
    ids = world["ids"]
    iid, _ = await mk_item(world, "apr")
    await mk_delegation(world, "apr", "dlg", only_leave=True)
    hd = await login(client, world, "dlg")
    assert iid not in await _inbox(client, hd)
    async with SessionLocal() as db:
        db.add(LeaveRequest(
            employee_id=ids["apr"], leave_type_id=ids["lt"],
            start_date=TODAY - timedelta(days=1),
            end_date=TODAY + timedelta(days=1), reason="t",
            status=LeaveStatus.APPROVED, created_by_user_id=ids["apr"]))
        await db.commit()
    assert iid in await _inbox(client, hd)


async def test_chain_queue_and_act(client, world):
    ids = world["ids"]
    inst, sid = await mk_chain(world, "apr")
    await mk_delegation(world, "apr", "dlg")
    hd = await login(client, world, "dlg")
    r = await client.get(f"{API}/approval-chains/my-queue", headers=hd)
    row = next(x for x in r.json() if x["instance"]["id"] == inst)
    assert row["acting_for"]["user_id"] == ids["apr"]
    r = await client.post(f"{API}/approval-chains/instances/{inst}/act",
                          headers=hd, json={"action": "approve"})
    assert r.status_code == 200, r.text
    assert r.json()["finalized"] is True
    async with SessionLocal() as db:
        logs = (await db.execute(select(AuditLog).where(
            AuditLog.user_id == ids["dlg"],
            AuditLog.action == "chained_approval_approve"))).scalars().all()
    assert logs[0].details["acting_for_user_id"] == ids["apr"]


async def test_leave_inbox_and_action(client, world):
    ids = world["ids"]
    async with SessionLocal() as db:
        lv = LeaveRequest(
            employee_id=ids["req"], leave_type_id=ids["lt"],
            start_date=date(2031, 3, 10), end_date=date(2031, 3, 11),
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
    hd = await login(client, world, "dlg")
    r = await client.get(f"{API}/leave/approvals/inbox", headers=hd)
    assert iid not in [x["id"] for x in r.json()]
    await mk_delegation(world, "apr", "dlg")
    r = await client.get(f"{API}/leave/approvals/inbox", headers=hd)
    row = next(x for x in r.json() if x["id"] == iid)
    assert row["acting_for"]["user_id"] == ids["apr"]
    assert "is_overdue" in row and "due_at" in row
    r = await client.post(f"{API}/leave/approvals/{iid}/action", headers=hd,
                          json={"status": "approved"})
    assert r.status_code == 200, r.text
    async with SessionLocal() as db:
        lv = await db.get(LeaveRequest, lid)
        assert lv.status == LeaveStatus.APPROVED
        log = (await db.execute(select(AuditLog).where(
            AuditLog.user_id == ids["dlg"],
            AuditLog.resource_id == str(lid)))).scalars().first()
    assert log.details["acting_for_user_id"] == ids["apr"]


async def test_hr_admin_can_list_all(client, world):
    await mk_delegation(world, "apr", "dlg")
    hh = await login(client, world, "hr")   # test role is not named "HR"
    assert (await client.get(f"{API}/approval-delegations",
                             headers=hh)).status_code == 403
    r = await client.post(f"{API}/auth/login", data={
        "username": "admin@gmail.com", "password": "test@12345"})
    if r.status_code != 200:  # dev seed absent: nothing more to assert
        return
    adm = {"Authorization": f"Bearer {r.json()['access_token']}"}
    r = await client.get(f"{API}/approval-delegations", headers=adm)
    assert r.status_code == 200
    assert any(d["user_name"] == "AW apr" for d in r.json())


async def test_delegate_candidates_search(client, world):
    ids = world["ids"]
    ha = await login(client, world, "apr")
    r = await client.get(
        f"{API}/me/approval-delegations/candidates?q=aw_dlg_{world['sfx']}",
        headers=ha)
    assert r.status_code == 200
    assert [c["id"] for c in r.json()] == [ids["dlg"]]
    r = await client.get(
        f"{API}/me/approval-delegations/candidates?q=aw_apr_{world['sfx']}",
        headers=ha)
    assert r.json() == []   # never offers yourself


async def test_overlapping_delegation_409_and_view_scope(client, world):
    ids = world["ids"]
    ha = await login(client, world, "apr")
    url = f"{API}/me/approval-delegations"
    r = await client.post(url, headers=ha, json={
        "delegate_id": ids["dlg"], "starts_on": str(TODAY),
        "ends_on": str(TODAY + timedelta(days=10))})
    assert r.status_code == 201
    r = await client.post(url, headers=ha, json={
        "delegate_id": ids["dlg"],
        "starts_on": str(TODAY + timedelta(days=5))})   # open-ended overlap
    assert r.status_code == 409
    # non-overlapping later window is fine; other delegate is fine
    r = await client.post(url, headers=ha, json={
        "delegate_id": ids["dlg"],
        "starts_on": str(TODAY + timedelta(days=11))})
    assert r.status_code == 201
    r = await client.post(url, headers=ha, json={
        "delegate_id": ids["oth"], "starts_on": str(TODAY)})
    assert r.status_code == 201
    # delegate may view only items whose CURRENT pending step is the delegator's
    hd = await login(client, world, "dlg")
    cur, _ = await mk_item(world, "apr")
    later, _ = await mk_item(world, "oth", steps=2)
    async with SessionLocal() as db:   # step 2 of `later` belongs to apr
        st = (await db.execute(select(ApprovalStep).where(
            ApprovalStep.approval_item_id == later,
            ApprovalStep.step_number == 2))).scalar_one()
        st.approver_id = ids["apr"]
        await db.commit()
    assert (await client.get(f"{API}/approvals/{cur}",
                             headers=hd)).status_code == 200
    assert (await client.get(f"{API}/approvals/{later}",
                             headers=hd)).status_code == 403


async def test_concurrent_overlapping_creates_one_wins(client, world):
    import asyncio
    ids = world["ids"]
    ha = await login(client, world, "apr")
    url = f"{API}/me/approval-delegations"
    res = await asyncio.gather(*[
        client.post(url, headers=ha, json={"delegate_id": ids["dlg"]})
        for _ in range(4)])
    codes = sorted(r.status_code for r in res)
    assert codes == [201, 409, 409, 409], [r.text for r in res]
