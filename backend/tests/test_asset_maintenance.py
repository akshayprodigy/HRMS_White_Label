"""Asset maintenance log (Roadmap v2 Phase 5, Task 5). Real dev DB, full teardown."""
from datetime import date, timedelta

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.asset import AssetMaintenance
from app.models.audit import AuditLog
from tests.test_assets_api import P, api, cat, mk, world  # noqa: F401

TODAY = date.today().isoformat()
YEST = (date.today() - timedelta(days=1)).isoformat()


def body(**kw):
    b = {"kind": "service", "description": "Routine service",
         "started_on": YEST}
    b.update(kw)
    return b


async def post(api, aid, **kw):
    return await api.post(f"{P}/{aid}/maintenance", headers=api.hr,
                          json=body(**kw))


async def status_of(api, aid):
    return (await api.get(f"{P}/{aid}", headers=api.hr)).json()["status"]


async def test_log_service_listed_and_in_detail(api, cat):
    a = await mk(api, cat)
    r = await post(api, a["id"], cost_paise=5000, vendor="ACME")
    assert r.status_code in (200, 201), r.text
    m = r.json()
    assert m["kind"] == "service" and m["cost_paise"] == 5000
    assert m["completed_on"] is None and m["asset_id"] == a["id"]
    assert await status_of(api, a["id"]) == "in_stock"
    await post(api, a["id"], cost_paise=700, started_on=TODAY)
    lst = (await api.get(f"{P}/{a['id']}/maintenance", headers=api.hr)).json()
    assert [x["started_on"] for x in lst] == [TODAY, YEST]
    d = (await api.get(f"{P}/{a['id']}", headers=api.hr)).json()
    assert len(d["maintenance"]) == 2
    assert d["maintenance_cost_total_paise"] == 5700
    async with SessionLocal() as db:
        n = (await db.execute(select(AuditLog).where(
            AuditLog.action == "ASSET_MAINTENANCE_ADD",
            AuditLog.resource_id == str(a["id"])))).scalars().all()
        assert len(n) == 2


async def test_repair_move_and_complete(api, cat):
    a = await mk(api, cat)
    r = await post(api, a["id"], kind="repair", move_to_repair=True)
    assert r.status_code in (200, 201), r.text
    assert await status_of(api, a["id"]) == "in_repair"
    r = await api.patch(f"{P}/maintenance/{r.json()['id']}", headers=api.hr,
                        json={"complete": True})
    assert r.status_code == 200, r.text
    assert r.json()["completed_on"] == TODAY
    assert await status_of(api, a["id"]) == "in_stock"


async def test_two_open_repairs(api, cat):
    a = await mk(api, cat)
    m1 = (await post(api, a["id"], kind="repair", move_to_repair=True)).json()
    r = await post(api, a["id"], kind="repair", move_to_repair=True)
    assert r.status_code in (200, 201), r.text  # already in_repair is fine
    m2 = r.json()
    r = await api.patch(f"{P}/maintenance/{m1['id']}", headers=api.hr,
                        json={"complete": True})
    assert r.status_code == 200
    assert await status_of(api, a["id"]) == "in_repair"
    r = await api.patch(f"{P}/maintenance/{m2['id']}", headers=api.hr,
                        json={"complete": True})
    assert r.status_code == 200
    assert await status_of(api, a["id"]) == "in_stock"


async def test_complete_no_return_and_twice(api, cat):
    a = await mk(api, cat)
    m = (await post(api, a["id"], kind="repair", move_to_repair=True)).json()
    r = await api.patch(f"{P}/maintenance/{m['id']}", headers=api.hr,
                        json={"complete": True, "return_to_stock": False})
    assert r.status_code == 200
    assert await status_of(api, a["id"]) == "in_repair"
    r = await api.patch(f"{P}/maintenance/{m['id']}", headers=api.hr,
                        json={"complete": True})
    assert r.status_code == 409


async def test_move_to_repair_state_rules(api, cat, world):
    a = await mk(api, cat)
    r = await api.post(f"{P}/{a['id']}/allocate", headers=api.hr,
                       json={"employee_id": world["emp_id"]})
    assert r.status_code == 200, r.text
    r = await post(api, a["id"], kind="repair", move_to_repair=True)
    assert r.status_code == 409 and "Return the asset first" in r.text
    assert await status_of(api, a["id"]) == "allocated"
    # nothing was logged on the failed attempt
    assert (await api.get(f"{P}/{a['id']}/maintenance",
                          headers=api.hr)).json() == []
    b = await mk(api, cat)
    r = await api.post(f"{P}/{b['id']}/status", headers=api.hr,
                       json={"to_status": "retired"})
    assert r.status_code == 200
    r = await post(api, b["id"], kind="repair", move_to_repair=True)
    assert r.status_code == 409
    c = await mk(api, cat)
    r = await post(api, c["id"], kind="repair", move_to_repair=True,
                   completed_on=TODAY)
    assert r.status_code == 422


async def test_validation(api, cat):
    a = await mk(api, cat)
    fut = (date.today() + timedelta(days=2)).isoformat()
    for kw in ({"completed_on": (date.today() - timedelta(days=5)).isoformat()},
               {"started_on": fut}, {"cost_paise": -1}, {"kind": "bogus"},
               {"description": "   "}):
        r = await post(api, a["id"], **kw)
        assert r.status_code == 422, (kw, r.status_code)
    m = (await post(api, a["id"])).json()
    r = await api.patch(f"{P}/maintenance/{m['id']}", headers=api.hr,
                        json={"completed_on": (date.today() - timedelta(days=5)
                                               ).isoformat()})
    assert r.status_code == 422


async def test_patch_edit(api, cat):
    a = await mk(api, cat)
    m = (await post(api, a["id"])).json()
    r = await api.patch(f"{P}/maintenance/{m['id']}", headers=api.hr,
                        json={"cost_paise": 900, "vendor": "V2",
                              "kind": "upgrade"})
    assert r.status_code == 200
    assert (r.json()["cost_paise"], r.json()["vendor"], r.json()["kind"]) == (
        900, "V2", "upgrade")
    async with SessionLocal() as db:
        n = (await db.execute(select(AuditLog).where(
            AuditLog.action == "ASSET_MAINTENANCE_UPDATE",
            AuditLog.resource_id == str(a["id"])))).scalars().all()
        assert len(n) == 1


async def test_delete_rules(api, cat):
    a = await mk(api, cat)
    costed = (await post(api, a["id"], cost_paise=10)).json()
    done = (await post(api, a["id"], completed_on=TODAY)).json()
    free = (await post(api, a["id"])).json()
    for m in (costed, done):
        r = await api.delete(f"{P}/maintenance/{m['id']}", headers=api.hr)
        assert r.status_code == 409, r.text
        assert "are kept" in r.text
    r = await api.delete(f"{P}/maintenance/{free['id']}", headers=api.hr)
    assert r.status_code in (200, 204), r.text
    ids = [x["id"] for x in (await api.get(
        f"{P}/{a['id']}/maintenance", headers=api.hr)).json()]
    assert free["id"] not in ids and len(ids) == 2
    async with SessionLocal() as db:
        n = (await db.execute(select(AuditLog).where(
            AuditLog.action == "ASSET_MAINTENANCE_DELETE",
            AuditLog.resource_id == str(a["id"])))).scalars().all()
        assert len(n) == 1


async def test_permission_denied(api):
    reqs = [("GET", f"{P}/1/maintenance", None),
            ("POST", f"{P}/1/maintenance", body()),
            ("PATCH", f"{P}/maintenance/1", {"cost_paise": 1}),
            ("DELETE", f"{P}/maintenance/1", None)]
    for m, p, b in reqs:
        r = await api.request(m, p, headers=api.plain, json=b)
        assert r.status_code == 403, (m, p, r.status_code)


async def test_unknown_404(api):
    r = await api.get(f"{P}/99999999/maintenance", headers=api.hr)
    assert r.status_code == 404
    r = await post(api, 99999999)
    assert r.status_code == 404
    r = await api.patch(f"{P}/maintenance/99999999", headers=api.hr,
                        json={"cost_paise": 1})
    assert r.status_code == 404
    r = await api.delete(f"{P}/maintenance/99999999", headers=api.hr)
    assert r.status_code == 404

