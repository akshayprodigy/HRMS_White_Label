"""Night-shift consent + violation insight (Roadmap v2 Phase 2, Task 8)."""
from datetime import date, time, timedelta
from types import SimpleNamespace

import pytest

from _safety_world import API, add_entry, client, login, world  # noqa: F401
from app.models.roster import RosterStatus
from app.services import schedule_rules as sr

D = date(2030, 6, 10)


@pytest.mark.parametrize("s,e,ov,exp", [
    (time(22), time(6), True, True),
    (time(23), time(7), False, True),        # end <= start => overnight
    (time(20), time(23), False, True),       # overlaps 22:00
    (time(9), time(17), False, False),
    (time(5), time(13), False, True),        # overlaps 00-06
    (time(6), time(14), False, False),       # starts exactly at 06:00
    (time(14), time(22), False, False),      # ends exactly at 22:00
])
def test_is_night_template(s, e, ov, exp):
    assert sr.is_night_template(
        SimpleNamespace(start_time=s, end_time=e, is_overnight=ov)) is exp


async def violations(client, h, dept, uid=None):
    r = await client.get(f"{API}/roster/insights", headers=h, params={
        "start": D.isoformat(), "end": (D + timedelta(days=3)).isoformat(),
        "department": dept})
    assert r.status_code == 200, r.text
    return [(v["user_id"], v["work_date"]) for v in r.json()["violations"]
            if v["rule"] == "night_consent_missing"]


async def consent(client, h, uid, **kw):
    body = {"valid_from": D.isoformat(), **kw}
    r = await client.post(f"{API}/hr/employees/{uid}/night-consents",
                          headers=h, json=body)
    assert r.status_code == 201, r.text
    return r.json()


async def test_violation_matrix(client, world):
    ids = world["ids"]
    await add_entry(ids["f"], D, ids["night"])                       # female, night
    await add_entry(ids["f"], D + timedelta(days=1), ids["day"])     # day: fine
    await add_entry(ids["m"], D, ids["night"])                       # male: none
    await add_entry(ids["plain"], D, ids["night"], status=RosterStatus.DRAFT)
    hh = await login(client, world, "head")
    hw = await login(client, world, "hrw")
    key = (ids["f"], D.isoformat())
    assert await violations(client, hh, world["dept"]) == [key]
    # active consent clears it
    c = await consent(client, hw, ids["f"])
    assert c["active"] is False or c["valid_from"] == D.isoformat()
    assert await violations(client, hh, world["dept"]) == []
    # ended before the shift date -> violation again
    r = await client.post(f"{API}/hr/employees/{ids['f']}/night-consents/{c['id']}/end",
                          headers=hw, json={"valid_to": (D - timedelta(days=1)).isoformat()})
    assert r.status_code == 422                                      # before valid_from
    r = await client.post(f"{API}/hr/employees/{ids['f']}/night-consents/{c['id']}/end",
                          headers=hw, json={"valid_to": (D - timedelta(days=0)).isoformat()})
    assert r.status_code == 200
    assert await violations(client, hh, world["dept"]) == []         # valid through D
    # an expired consent (window ends before D) does not cover
    await add_entry(ids["f"], D + timedelta(days=2), ids["late"])    # 20-23 overlaps night
    key2 = (ids["f"], (D + timedelta(days=2)).isoformat())
    assert await violations(client, hh, world["dept"]) == [key2]
    # explicit refusal is not consent
    await consent(client, hw, ids["f"], consent_given=False, valid_from=(D - timedelta(days=30)).isoformat())
    assert await violations(client, hh, world["dept"]) == [key2]
    # open-ended consent clears all
    await consent(client, hw, ids["f"], valid_from=(D - timedelta(days=5)).isoformat())
    assert await violations(client, hh, world["dept"]) == []


async def test_consent_hr_endpoints(client, world):
    ids = world["ids"]
    hw = await login(client, world, "hrw")
    hr = await login(client, world, "hrr")
    hf = await login(client, world, "f")
    base = f"{API}/hr/employees/{ids['f']}/night-consents"
    r = await client.post(base, headers=hr, json={"valid_from": D.isoformat()})
    assert r.status_code == 403                                      # read-only HR
    assert (await client.post(base, headers=hf, json={"valid_from": D.isoformat()})
            ).status_code == 403                                     # self can't grant
    assert (await client.post(base, headers=hw, json={
        "valid_from": D.isoformat(), "valid_to": (D - timedelta(days=1)).isoformat()})
    ).status_code == 422
    assert (await client.post(f"{API}/hr/employees/999999999/night-consents",
                              headers=hw, json={"valid_from": D.isoformat()})
            ).status_code == 404
    c = await consent(client, hw, ids["f"], document_url="https://x/doc.pdf", note="n")
    assert c["recorded_by_id"] == ids["hrw"]
    rows = (await client.get(base, headers=hr)).json()
    assert [x["id"] for x in rows] == [c["id"]]
    # future-dated consent with no end date is withdrawn
    fut = await consent(client, hw, ids["f"], valid_from=date(2031, 1, 1).isoformat())
    r = await client.post(f"{base}/{fut['id']}/end", headers=hw, json={})
    assert r.json()["consent_given"] is False and r.json()["active"] is False
    # ending a running consent without a date stops it today
    run = await consent(client, hw, ids["f"], valid_from="2020-01-01")
    assert run["active"] is True
    r = await client.post(f"{base}/{run['id']}/end", headers=hw, json={})
    assert r.json()["valid_to"] is not None
    assert (await client.post(f"{base}/999999999/end", headers=hw, json={})
            ).status_code == 404
