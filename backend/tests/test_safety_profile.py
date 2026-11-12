"""Emergency profile data, privacy, team contacts, transport flag
(Roadmap v2 Phase 2, Task 8)."""
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from _safety_world import API, add_entry, client, login, world  # noqa: F401
from app.db.session import SessionLocal
from app.models.roster import RosterEntry, RosterEntryHistory, RosterStatus
from app.models.system import SystemSetting
from app.models.roster import ScheduleChangeAck
from app.services import time_rules

D = date(2030, 6, 10)
C = {"name": "Asha", "relation": "Spouse", "phone": "+91 98765 43210"}


async def test_profile_validation_and_roundtrip(client, world):
    h = await login(client, world, "m")
    u = f"{API}/me/safety-profile"
    for bad in ({"gender": "robot"}, {"blood_group": "Z+"}):
        assert (await client.put(u, headers=h, json=bad)).status_code == 422
    r = await client.put(u, headers=h, json={"gender": "Male", "blood_group": "o+"})
    assert r.status_code == 200, r.text
    assert (r.json()["gender"], r.json()["blood_group"]) == ("male", "O+")
    assert (await client.get(u, headers=h)).json()["blood_group"] == "O+"
    r = await client.put(u, headers=h, json={"blood_group": None})
    assert r.json()["blood_group"] is None and r.json()["gender"] == "male"


async def test_contact_invariants(client, world):
    h = await login(client, world, "m")
    u = f"{API}/me/emergency-contacts"
    assert (await client.post(u, headers=h, json={**C, "phone": "abc"})).status_code == 422
    a = (await client.post(u, headers=h, json=C)).json()
    assert a["is_primary"] is True            # first is always primary
    b = (await client.post(u, headers=h, json={**C, "name": "B"})).json()
    assert b["is_primary"] is False
    c = (await client.post(u, headers=h, json={**C, "name": "C", "is_primary": True})).json()
    rows = (await client.get(u, headers=h)).json()
    assert [r["is_primary"] for r in rows].count(True) == 1 and rows[0]["id"] == c["id"]
    r = await client.post(u, headers=h, json={**C, "name": "D"})
    assert r.status_code == 400                # max 3
    r = await client.put(f"{u}/{c['id']}", headers=h, json={"is_primary": False})
    assert r.status_code == 400                # must keep a primary
    r = await client.put(f"{u}/{b['id']}", headers=h, json={"is_primary": True})
    assert r.status_code == 200
    rows = (await client.get(u, headers=h)).json()
    assert [r_["id"] for r_ in rows if r_["is_primary"]] == [b["id"]]
    assert (await client.delete(f"{u}/{b['id']}", headers=h)).status_code == 200
    rows = (await client.get(u, headers=h)).json()
    assert len(rows) == 2 and [r_["is_primary"] for r_ in rows].count(True) == 1
    # cannot touch another employee's contact
    h2 = await login(client, world, "f")
    assert (await client.delete(f"{u}/{a['id']}", headers=h2)).status_code == 404
    assert (await client.get(u, headers=h2)).json() == []


async def test_privacy_hr_and_general_lists(client, world):
    ids = world["ids"]
    hm = await login(client, world, "m")
    await client.put(f"{API}/me/safety-profile", headers=hm,
                     json={"gender": "male", "blood_group": "A+"})
    await client.post(f"{API}/me/emergency-contacts", headers=hm, json=C)
    url = f"{API}/hr/employees/{ids['m']}"
    # employee / manager / plain users: no access to HR route
    for tag in ("f", "head", "plain"):
        h = await login(client, world, tag)
        assert (await client.get(f"{url}/safety-profile", headers=h)).status_code == 403
        assert (await client.get(f"{url}/night-consents", headers=h)).status_code == 403
    # HR read: may read, not write
    hr = await login(client, world, "hrr")
    r = await client.get(f"{url}/safety-profile", headers=hr)
    assert r.status_code == 200 and r.json()["blood_group"] == "A+"
    assert len(r.json()["contacts"]) == 1
    assert (await client.put(f"{url}/safety-profile", headers=hr,
                             json={"gender": "male"})).status_code == 403
    assert (await client.post(f"{url}/emergency-contacts", headers=hr,
                              json=C)).status_code == 403
    # HR write: edits
    hw = await login(client, world, "hrw")
    r = await client.put(f"{url}/safety-profile", headers=hw, json={"blood_group": "B-"})
    assert r.status_code == 200 and r.json()["blood_group"] == "B-"
    r = await client.post(f"{url}/emergency-contacts", headers=hw, json={**C, "name": "Z"})
    assert r.status_code == 201
    assert (await client.get(f"{API}/hr/employees/999999999/safety-profile",
                             headers=hw)).status_code == 404
    # general employee payloads never carry the sensitive fields
    blob = (await client.get(f"{API}/hr/employees", headers=hr,
                                 params={"size": 100})).text
    assert '"gender"' not in blob and '"blood_group"' not in blob
    assert world["sfx"] in blob                      # sanity: list returned our users
    for u in (f"{API}/hr/employees/me", f"{API}/auth/me"):
        t = (await client.get(u, headers=hm)).text
        assert '"gender"' not in t and '"blood_group"' not in t


async def test_team_contacts_scope_and_no_gender(client, world):
    ids = world["ids"]
    hf = await login(client, world, "f")
    await client.put(f"{API}/me/safety-profile", headers=hf,
                     json={"gender": "female", "blood_group": "AB+"})
    await client.post(f"{API}/me/emergency-contacts", headers=hf, json=C)
    hh = await login(client, world, "head")
    r = await client.get(f"{API}/roster/team-contacts", headers=hh)
    assert r.status_code == 200, r.text
    got = {x["user_id"]: x for x in r.json()}
    assert set(got) == {ids["head"], ids["f"], ids["m"], ids["plain"]}
    assert got[ids["f"]]["blood_group"] == "AB+"
    assert got[ids["f"]]["contacts"][0]["phone"] == C["phone"]
    assert got[ids["f"]]["phone"] == "9000000001"
    assert "gender" not in r.text
    r = await client.get(f"{API}/roster/team-contacts",
                         params={"department": world["other"]}, headers=hh)
    assert r.json() == []                            # other dept is out of scope
    # no scope -> 403; a plain employee / HR-only user can't use it
    for tag in ("plain", "x", "hrw"):
        h = await login(client, world, tag)
        assert (await client.get(f"{API}/roster/team-contacts",
                                 headers=h)).status_code == 403


async def test_transport_toggle(client, world):
    ids = world["ids"]
    tomorrow = datetime.now(timezone.utc).date() + timedelta(days=1)
    pub = await add_entry(ids["f"], tomorrow, ids["day"])
    drf = await add_entry(ids["m"], D, ids["day"], status=RosterStatus.DRAFT)
    off = await add_entry(ids["plain"], D, None, off=True)
    hh = await login(client, world, "head")
    hx = await login(client, world, "x")
    url = lambda i: f"{API}/roster/entries/{i}/transport"  # noqa: E731
    assert (await client.patch(url(pub), headers=hx, json={"required": True})
            ).status_code == 403
    assert (await client.patch(url(off), headers=hh, json={"required": True})
            ).status_code == 400
    assert (await client.patch(url(999999999), headers=hh, json={"required": True})
            ).status_code == 404
    # inside an active lock window: still allowed, no history / ack rows
    async with SessionLocal() as db:
        prior = await db.get(SystemSetting, "schedule.lock_days")
        prior_val = prior.value if prior else None
        await time_rules.set_time_rules(db, {"schedule.lock_days": "30"})
    try:
        r = await client.patch(url(pub), headers=hh, json={"required": True})
        assert r.status_code == 200 and r.json()["transport_required"] is True
        assert (await client.patch(url(drf), headers=hh, json={"required": True})
                ).status_code == 200
    finally:
        async with SessionLocal() as db:
            row = await db.get(SystemSetting, "schedule.lock_days")
            if prior_val is None:
                if row:
                    await db.delete(row)
            else:
                row.value = prior_val
            await db.commit()
    async with SessionLocal() as db:
        uids = list(ids[t] for t in ("f", "m", "plain"))
        assert (await db.execute(select(RosterEntryHistory).where(
            RosterEntryHistory.employee_id.in_(uids)))).first() is None
        assert (await db.execute(select(ScheduleChangeAck).where(
            ScheduleChangeAck.user_id.in_(uids)))).first() is None
    # grid / my-week / live board expose it
    r = await client.get(f"{API}/roster/plan", headers=hh, params={
        "start": tomorrow.isoformat(), "end": tomorrow.isoformat()})
    cell = [c for row in r.json()["rows"] if row["employee_id"] == ids["f"]
            for c in row["cells"]][0]
    assert cell["transport_required"] is True
    hf = await login(client, world, "f")
    r = await client.get(f"{API}/roster/my/week", headers=hf,
                         params={"start": tomorrow.isoformat()})
    assert r.json()["days"][0]["shift"]["transport_required"] is True
    r = await client.patch(url(pub), headers=hh, json={"required": False})
    assert r.json()["transport_required"] is False


async def test_concurrent_adds_respect_cap_and_primary(client, world):
    import asyncio
    h = await login(client, world, "m")
    u = f"{API}/me/emergency-contacts"
    rs = await asyncio.gather(*[
        client.post(u, headers=h, json={**C, "name": f"P{i}", "is_primary": i % 2 == 0})
        for i in range(4)])
    assert sorted(r.status_code for r in rs).count(201) == 3, [r.text for r in rs]
    rows = (await client.get(u, headers=h)).json()
    assert len(rows) == 3 and [r["is_primary"] for r in rows].count(True) == 1


async def test_hr_profile_reports_can_write_and_list_is_audited(client, world):
    from app.models.audit import AuditLog
    ids = world["ids"]
    for tag, exp in (("hrr", False), ("hrw", True)):
        h = await login(client, world, tag)
        r = await client.get(f"{API}/hr/employees/{ids['m']}/safety-profile", headers=h)
        assert r.json()["can_write"] is exp
    h = await login(client, world, "hrr")
    await client.get(f"{API}/hr/employees/{ids['m']}/night-consents", headers=h)
    async with SessionLocal() as db:
        assert (await db.execute(select(AuditLog).where(
            AuditLog.user_id == ids["hrr"],
            AuditLog.action == "safety.consent.list"))).first() is not None
