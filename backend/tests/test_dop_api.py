"""DOP D1 Task 7: the /dop admin API. Real HTTP through ASGI on the dev DB;
teardown removes everything created here (matched by this run's suffix)."""
import asyncio
from datetime import date, timedelta

import pytest
from _dop_world import dop  # noqa: F401
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, event, select
from sqlalchemy.exc import OperationalError

from app.api import deps
from app.core.security import get_password_hash
from app.db.session import SessionLocal, engine
from app.main import create_app
from app.models.audit import AuditLog
from app.models.dop import ManagerAssignment, ManagerKind, Post
from app.models.employee import Employee, EmployeeStatus
from app.models.user import User
from app.services.dop import assignments as A
from app.services.org_time import local_today

H = "/api/v1/dop"
HR = "/api/v1/hr"


async def _login(c, email):
    r = await c.post("/api/v1/auth/login",
                     data={"username": email, "password": "x"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
async def api(dop):
    sfx = dop["sfx"]
    app = create_app()
    app.dependency_overrides[deps.verify_attendance] = lambda: None
    c = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    c.h = await _login(c, f"dop_admin_{sfx}@test.com")
    c.hr_h = await _login(c, f"dop_hr_{sfx}@test.com")
    c.emp_h = await _login(c, f"dop_emp_{sfx}@test.com")
    c.u = dop["uid"]
    c.sfx = sfx
    c.today = None
    async with SessionLocal() as db:
        c.today = await local_today(db)
    r = await c.get(H + "/meta", headers=c.h)
    c.rep = next(k["id"] for k in r.json()["kinds"] if k["code"] == "reporting")
    c.fun = next(k["id"] for k in r.json()["kinds"] if k["code"] == "functional")
    yield c
    await c.aclose()
    async with SessionLocal() as db:       # kinds made by this run
        ids = list((await db.execute(select(ManagerKind.id).where(
            ManagerKind.code.like(f"%{sfx}")))).scalars().all())
        if ids:
            await db.execute(delete(ManagerAssignment).where(
                ManagerAssignment.manager_kind_id.in_(ids)))
            await db.execute(delete(ManagerKind).where(
                ManagerKind.id.in_(ids)))
        await db.execute(delete(AuditLog).where(
            AuditLog.resource_type == "manager_kind",
            AuditLog.resource_id.in_([str(i) for i in ids])))
        await db.commit()


async def _mgr(uid):
    async with SessionLocal() as db:
        return (await db.execute(select(User.manager_id).where(
            User.id == uid))).scalar_one()


async def _rows(uids):
    async with SessionLocal() as db:
        return (await db.execute(select(ManagerAssignment).where(
            ManagerAssignment.scope_user_id.in_(uids)))).scalars().all()


def _bulk(api, ids, mgr, **kw):
    return {"user_ids": ids, "kind_id": api.rep, "manager_user_id": mgr,
            "starts_on": api.today.isoformat(), **kw}


async def _mk_users(sfx, n, tag="b"):
    h = get_password_hash("x")
    async with SessionLocal() as db:
        us = [User(email=f"dop_{tag}{i}_{sfx}@test.com",
                   full_name=f"Bulk {tag}{i:03d} {sfx}", hashed_password=h,
                   is_active=True) for i in range(n)]
        db.add_all(us)
        await db.flush()
        db.add_all(Employee(
            user_id=u.id, employee_id=f"{tag}{i}{sfx}", department="X",
            designation="T", location="Y", date_of_joining=date(2020, 1, 1),
            status=EmployeeStatus.ACTIVE) for i, u in enumerate(us))
        await db.commit()
        return [u.id for u in us]


# ---------------------------------------------------------------- access

MUTATIONS = [
    ("POST", "/kinds", {"code": "zz", "name": "x"}),
    ("PATCH", "/kinds/1", {"name": "x"}),
    ("POST", "/assignments/bulk", {}),
    ("POST", "/assignments/1/end", {}),
    ("POST", "/posts", {}), ("PATCH", "/posts/1", {}),
    ("POST", "/posts/1/holders", {}),
    ("POST", "/posts/1/holders/1/end", {}),
    ("POST", "/posts/1/holders/1/remove", {}),
    ("POST", "/acting", {}), ("PATCH", "/acting/1", {}),
    ("POST", "/acting/1/revoke", {}),
    ("POST", "/check", {}), ("POST", "/check/all", {}),
]


async def test_everything_is_403_without_dop_manage(api):
    for hdr in (api.hr_h, api.emp_h):
        for path in ("/meta", "/people", "/managers", "/assignments",
                     "/posts", "/posts/1/holders", "/acting"):
            assert (await api.get(H + path, headers=hdr)).status_code == 403
        for m, path, body in MUTATIONS:
            r = await api.request(m, H + path, headers=hdr, json=body)
            assert r.status_code == 403, (m, path, r.text)
    assert (await api.get(H + "/meta")).status_code == 401


async def test_meta_and_people(api):
    r = await api.get(H + "/meta", headers=api.h)
    assert r.status_code == 200, r.text
    m = r.json()
    assert {"reporting", "functional"} <= {k["code"] for k in m["kinds"]}
    assert "leave" in {s["code"] for s in m["subdomains"]}
    assert m["scopes"] == ["user", "department", "location", "company"]
    assert any(d["name"] == f"DOP{api.sfx}" for d in m["departments"])
    assert f"Mumbai{api.sfx}" in m["locations"]
    assert "reporting_manager" in m["approver_types"]
    r = await api.get(H + "/people", params={"q": api.sfx}, headers=api.h)
    names = {p["id"] for p in r.json()}
    assert api.u["emp"] in names and api.u["off"] not in names   # active only
    assert set(r.json()[0]) == {"id", "name", "email"}
    r = await api.get(H + "/people", params={"q": "%"}, headers=api.h)
    assert r.status_code == 200 and len(r.json()) <= 20
    assert all("%" in p["name"] or "%" in p["email"] for p in r.json())


# ------------------------------------------------------------------ bulk

async def test_bulk_assign_replace_conflict_rollback(api):
    u = api.u
    r = await api.post(H + "/assignments/bulk", headers=api.h,
                       json=_bulk(api, [u["emp"], u["act"]], u["mgr"]))
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 2 and r.json()["replaced"] == 0
    assert len(r.json()["assignment_ids"]) == 2
    assert await _mgr(u["emp"]) == u["mgr"] == await _mgr(u["act"])
    # again: conflict, nothing changes
    n = len(await _rows([u["emp"], u["act"]]))
    r = await api.post(H + "/assignments/bulk", headers=api.h,
                       json=_bulk(api, [u["emp"], u["act"]], u["mgr2"]))
    assert r.status_code == 409
    assert len(await _rows([u["emp"], u["act"]])) == n
    assert await _mgr(u["emp"]) == u["mgr"]
    # replace
    r = await api.post(H + "/assignments/bulk", headers=api.h, json=_bulk(
        api, [u["emp"], u["act"]], u["mgr2"], replace=True))
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 2 and r.json()["replaced"] == 2
    assert await _mgr(u["emp"]) == u["mgr2"] == await _mgr(u["act"])
    # one bad id rolls everything back
    n = len(await _rows([u["emp"], u["act"], u["mgr"]]))
    r = await api.post(H + "/assignments/bulk", headers=api.h, json=_bulk(
        api, [u["mgr"], 999999999], u["mgr2"]))
    assert r.status_code == 422
    assert len(await _rows([u["emp"], u["act"], u["mgr"]])) == n
    # inactive employee, own manager
    r = await api.post(H + "/assignments/bulk", headers=api.h,
                       json=_bulk(api, [u["off"]], u["mgr"]))
    assert r.status_code == 422
    r = await api.post(H + "/assignments/bulk", headers=api.h,
                       json=_bulk(api, [u["mgr"], u["emp"]], u["mgr"],
                                  replace=True))
    assert r.status_code == 422
    assert await _mgr(u["emp"]) == u["mgr2"]
    # duplicates collapse
    r = await api.post(H + "/assignments/bulk", headers=api.h,
                       json=_bulk(api, [u["mgr"], u["mgr"]], u["mgr2"]))
    assert r.status_code == 200 and r.json()["created"] == 1


async def test_bulk_replace_cannot_cut_a_started_future_row(api):
    u = api.u
    d = api.today
    # a row that started 10 days ago cannot be cut by a new row starting
    # 12 days ago (it would have to be cancelled): 409, nothing changes
    r = await api.post(H + "/assignments/bulk", headers=api.h, json={
        **_bulk(api, [u["emp"]], u["mgr"]),
        "starts_on": (d - timedelta(days=10)).isoformat()})
    assert r.status_code == 200
    r = await api.post(H + "/assignments/bulk", headers=api.h, json={
        **_bulk(api, [u["emp"], u["act"]], u["mgr2"], replace=True),
        "starts_on": (d - timedelta(days=12)).isoformat()})
    assert r.status_code == 409, r.text
    assert await _mgr(u["emp"]) == u["mgr"]
    assert await _mgr(u["act"]) is None
    # a future row starting after the new start is cancelled
    r = await api.post(H + "/assignments/bulk", headers=api.h, json={
        "user_ids": [u["act"]], "kind_id": api.rep,
        "manager_user_id": u["mgr"],
        "starts_on": (d + timedelta(days=3)).isoformat()})
    assert r.status_code == 200
    r = await api.post(H + "/assignments/bulk", headers=api.h, json={
        **_bulk(api, [u["act"]], u["mgr2"], replace=True),
        "starts_on": (d + timedelta(days=1)).isoformat()})
    assert r.status_code == 200 and r.json()["replaced"] == 1, r.text
    rows = [x for x in await _rows([u["act"]]) if x.cancelled_at is None]
    assert [x.manager_user_id for x in rows] == [u["mgr2"]]


async def test_bulk_validation(api):
    u = api.u
    ok = _bulk(api, [u["emp"]], u["mgr"])
    cases = [
        {**ok, "extra": 1},                                  # unknown field
        {**ok, "user_ids": []},
        {**ok, "user_ids": list(range(1, 202))},
        {**ok, "user_ids": [True]},
        {**ok, "replace": "yes"},
        {**ok, "starts_on": "not-a-date"},
        {**ok, "starts_on": 20260101},
        {**ok, "starts_on": "1900-01-01"},
        {**ok, "ends_on": (api.today - timedelta(days=9)).isoformat()},
        {**ok, "note": "x" * 256},
        {**ok, "subdomains": ["nope"]},
        {**ok, "manager_user_id": None},
        {**ok, "manager_post_id": 1},                        # both
        {**ok, "kind_id": 999999999},
        {k: v for k, v in ok.items() if k != "user_ids"},   # no target
        {**ok, "scope_type": "department"},                 # both targets
    ]
    for body in cases:
        r = await api.post(H + "/assignments/bulk", headers=api.h, json=body)
        assert r.status_code == 422, (body, r.status_code, r.text)
    assert await _rows([u["emp"]]) == []
    # note is trimmed
    r = await api.post(H + "/assignments/bulk", headers=api.h,
                       json={**ok, "note": "  hello  "})
    assert r.status_code == 200
    r = await api.get(H + "/assignments", params={"user_id": u["emp"]},
                      headers=api.h)
    assert r.json()["items"][0]["note"] == "hello"


async def test_assignments_list_and_end(api):
    u = api.u
    r = await api.post(H + "/assignments/bulk", headers=api.h,
                       json=_bulk(api, [u["emp"]], u["mgr"], note="n", starts_on=(
                           api.today - timedelta(days=10)).isoformat()))
    aid = r.json()["assignment_ids"][0]
    r = await api.get(H + "/assignments", params={"user_id": u["emp"]},
                      headers=api.h)
    assert r.status_code == 200, r.text
    row = r.json()["items"][0]
    assert row["id"] == aid and row["status"] == "live"
    assert row["scope_user_name"] and row["manager_user_name"].startswith("Dop mgr")
    assert row["kind_code"] == "reporting" and row["subdomains"] == []
    # end it yesterday: ends, mirror cleared
    y = (api.today - timedelta(days=1)).isoformat()
    r = await api.post(H + f"/assignments/{aid}/end", headers=api.h,
                       json={"ends_on": y})
    assert r.status_code == 200, r.text
    assert r.json()["ends_on"] == y and r.json()["status"] == "ended"
    assert await _mgr(u["emp"]) is None
    r = await api.get(H + "/assignments", params={"user_id": u["emp"]},
                      headers=api.h)
    assert r.json()["items"] == []
    r = await api.get(H + "/assignments", headers=api.h,
                      params={"user_id": u["emp"], "history": "true"})
    assert [x["id"] for x in r.json()["items"]] == [aid]   # before the second row
    # a row that starts today and is ended yesterday is cancelled
    r = await api.post(H + "/assignments/bulk", headers=api.h,
                       json=_bulk(api, [u["emp"]], u["mgr"]))
    cid = r.json()["assignment_ids"][0]
    r = await api.post(H + f"/assignments/{cid}/end", headers=api.h,
                       json={"ends_on": y})
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert (await api.post(H + "/assignments/999999999/end", headers=api.h,
                           json={"ends_on": y})).status_code == 404
    assert (await api.post(H + f"/assignments/{aid}/end", headers=api.h,
                           json={"ends_on": "bad"})).status_code == 422
    assert (await api.post(H + f"/assignments/{aid}/end", headers=api.h,
                           json={})).status_code == 422


# -------------------------------------------------------------- managers

async def test_managers_page(api):
    u = api.u
    await api.post(H + "/assignments/bulk", headers=api.h,
                   json=_bulk(api, [u["act"]], u["mgr"]))
    q = {"q": api.sfx, "department": f"DOP{api.sfx}"}
    r = await api.get(H + "/managers", headers=api.h,
                      params={**q, "missing": "reporting"})
    assert r.status_code == 200, r.text
    ids = {x["user_id"] for x in r.json()["items"]}
    assert u["mgr"] in ids and u["act"] not in ids and u["off"] not in ids
    assert r.json()["total"] == len(ids)
    r = await api.get(H + "/managers", headers=api.h,
                      params={**q, "include_inactive": "true"})
    ids = {x["user_id"] for x in r.json()["items"]}
    assert u["off"] in ids and u["act"] in ids
    row = next(x for x in r.json()["items"] if x["user_id"] == u["act"])
    rep = row["managers"]["reporting"]
    assert rep["manager_user_id"] == u["mgr"] and rep["source"] == "user"
    assert rep["manager_name"].startswith("Dop mgr")
    assert row["managers"]["functional"] is None
    assert {k["code"] for k in r.json()["kinds"]} >= {"reporting"}
    # paging, sorted by name
    r = await api.get(H + "/managers", headers=api.h,
                      params={"q": api.sfx, "limit": 2, "offset": 1})
    assert len(r.json()["items"]) == 2 and r.json()["total"] >= 6
    names = [x["name"] for x in (await api.get(
        H + "/managers", headers=api.h,
        params={"q": api.sfx, "limit": 100})).json()["items"]]
    assert names == sorted(names, key=str.casefold)
    for bad in ({"limit": 101}, {"limit": 0}, {"offset": -1},
                {"missing": "nope"}):
        assert (await api.get(H + "/managers", headers=api.h,
                              params=bad)).status_code == 422


async def test_managers_scope_source_and_post_title(api):
    u = api.u
    r = await api.post(H + "/posts", headers=api.h, json={
        "code": f"MG{api.sfx}", "title": "Plant Head"})
    pid = r.json()["id"]
    r = await api.post(H + f"/posts/{pid}/holders", headers=api.h,
                       json={"user_id": u["mgr"]})
    assert r.status_code == 200, r.text
    r = await api.post(H + "/assignments/bulk", headers=api.h, json={
        "scope_type": "department", "kind_id": api.fun,
        "manager_post_id": pid, "starts_on": api.today.isoformat()})
    assert r.status_code == 422                       # missing target
    dept = next(d["id"] for d in (await api.get(
        H + "/meta", headers=api.h)).json()["departments"]
        if d["name"] == f"DOP{api.sfx}")
    r = await api.post(H + "/assignments/bulk", headers=api.h, json={
        "scope_type": "department", "scope_department_id": dept,
        "kind_id": api.fun, "manager_post_id": pid,
        "starts_on": api.today.isoformat()})
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 1
    r = await api.get(H + "/managers", headers=api.h,
                      params={"q": "emp " + api.sfx})
    fun = r.json()["items"][0]["managers"]["functional"]
    assert fun["source"] == "department" and fun["post_title"] == "Plant Head"
    assert fun["manager_user_id"] == u["mgr"]


# ----------------------------------------------------------------- kinds

async def test_kinds(api):
    code = f"k_{api.sfx}"
    r = await api.post(H + "/kinds", headers=api.h,
                       json={"code": code, "name": " Project lead ",
                             "sort_order": 7})
    assert r.status_code == 200, r.text
    k = r.json()
    assert k["name"] == "Project lead" and k["is_active"] is True
    assert k["is_system"] is False and k["code"] == code
    assert (await api.post(H + "/kinds", headers=api.h,
                           json={"code": code, "name": "x"})).status_code == 409
    for body in ({"code": "Bad Code", "name": "x"}, {"code": "a", "name": "x"},
                 {"code": "1abc", "name": "x"}, {"code": "x" * 41, "name": "x"},
                 {"code": f"z_{api.sfx}", "name": ""},
                 {"code": f"z_{api.sfx}", "name": "n" * 81},
                 {"code": f"z_{api.sfx}", "name": "x", "is_system": True},
                 {"code": f"z_{api.sfx}", "name": "x", "sort_order": "3"}):
        assert (await api.post(H + "/kinds", headers=api.h,
                               json=body)).status_code == 422, body
    # code is immutable
    assert (await api.patch(H + f"/kinds/{k['id']}", headers=api.h,
                            json={"code": "other"})).status_code == 422
    r = await api.patch(H + f"/kinds/{k['id']}", headers=api.h,
                        json={"name": "Lead", "sort_order": 9})
    assert r.status_code == 200 and r.json()["name"] == "Lead"
    # system kinds cannot be deactivated
    assert (await api.patch(H + f"/kinds/{api.rep}", headers=api.h,
                            json={"is_active": False})).status_code == 422
    assert (await api.patch(H + f"/kinds/{k['id']}", headers=api.h,
                            json={"is_active": "no"})).status_code == 422
    assert (await api.patch(H + "/kinds/999999999", headers=api.h,
                            json={"name": "x"})).status_code == 404
    # a kind with a live or future assignment cannot be deactivated
    r = await api.post(H + "/assignments/bulk", headers=api.h, json={
        **_bulk(api, [api.u["emp"]], api.u["mgr"]), "kind_id": k["id"]})
    assert r.status_code == 200, r.text
    r = await api.patch(H + f"/kinds/{k['id']}", headers=api.h,
                        json={"is_active": False})
    assert r.status_code == 409
    aid = r.status_code and (await api.get(
        H + "/assignments", headers=api.h,
        params={"kind_id": k["id"]})).json()["items"][0]["id"]
    y = (api.today - timedelta(days=1)).isoformat()
    assert (await api.post(H + f"/assignments/{aid}/end", headers=api.h,
                           json={"ends_on": y})).status_code == 200
    r = await api.patch(H + f"/kinds/{k['id']}", headers=api.h,
                        json={"is_active": False})
    assert r.status_code == 200 and r.json()["is_active"] is False
    # inactive kind: no new assignments
    r = await api.post(H + "/assignments/bulk", headers=api.h, json={
        **_bulk(api, [api.u["emp"]], api.u["mgr"]), "kind_id": k["id"]})
    assert r.status_code == 422
    # audited
    async with SessionLocal() as db:
        acts = [a for a in (await db.execute(select(AuditLog.action).where(
            AuditLog.resource_type == "manager_kind",
            AuditLog.resource_id == str(k["id"])))).scalars().all()]
    assert acts.count("dop.kind.create") == 1
    assert acts.count("dop.kind.update") == 2
    # a non-reporting kind assignment never touches manager_id
    assert await _mgr(api.u["emp"]) is None


# ----------------------------------------------------------------- posts

async def _post(api, code="P", **kw):
    r = await api.post(H + "/posts", headers=api.h, json={
        "code": f"{code}{api.sfx}", "title": "HR Manager", **kw})
    assert r.status_code == 200, r.text
    return r.json()


async def test_posts_holders_and_check_via_post(api):
    u = api.u
    p = await _post(api)
    assert p["holder"] is None and p["acting"] == [] and p["is_active"]
    r = await api.post(H + f"/posts/{p['id']}/holders", headers=api.h,
                       json={"user_id": u["mgr"]})
    assert r.status_code == 200, r.text
    assert r.json()["post"]["holder"]["user_id"] == u["mgr"]
    assert r.json()["holders"][0]["user_name"].startswith("Dop mgr")
    # post as functional manager of emp
    r = await api.post(H + "/assignments/bulk", headers=api.h, json={
        "user_ids": [u["emp"]], "kind_id": api.fun,
        "manager_post_id": p["id"], "starts_on": api.today.isoformat()})
    assert r.status_code == 200, r.text
    chk = {"user_id": u["emp"], "subdomain": "leave",
           "approver": {"type": "manager_kind", "ref": "functional"}}
    r = await api.post(H + "/check", headers=api.h, json=chk)
    assert r.status_code == 200, r.text
    c = r.json()
    assert c["via"] == "primary" and c["approvers"][0]["user_id"] == u["mgr"]
    assert c["approvers"][0]["name"].startswith("Dop mgr")
    assert c["via_post"]["id"] == p["id"] and c["acting_for"] == []
    text = "\n".join(c["explanation"])
    assert "@" not in text and "Dop mgr" in text      # ids became names
    assert "assignment #" in text                     # assignment ids kept
    # acting cover on the post
    r = await api.post(H + "/acting", headers=api.h, json={
        "covers_post_id": p["id"], "acting_user_id": u["act"],
        "starts_on": api.today.isoformat()})
    assert r.status_code == 200, r.text
    assert r.json()["covers_post_title"] == "HR Manager"
    r = await api.post(H + "/check", headers=api.h, json=chk)
    c = r.json()
    assert [a["user_id"] for a in c["approvers"]] == [u["act"]]
    assert c["acting_for"][0]["user_id"] == u["act"]
    assert c["acting_for"][0]["covers"][0]["user_id"] == u["mgr"]
    r = await api.get(H + "/posts", headers=api.h)
    mine = next(x for x in r.json() if x["id"] == p["id"])
    assert mine["holder"]["user_id"] == u["mgr"]
    assert mine["acting"][0]["acting_user_id"] == u["act"]
    # patch, bad bool, duplicate code
    r = await api.patch(H + f"/posts/{p['id']}", headers=api.h,
                        json={"title": " Head of HR "})
    assert r.status_code == 200 and r.json()["title"] == "Head of HR"
    assert (await api.patch(H + f"/posts/{p['id']}", headers=api.h,
                            json={"is_active": 0})).status_code == 422
    assert (await api.post(H + "/posts", headers=api.h, json={
        "code": f"P{api.sfx}", "title": "x"})).status_code == 409
    assert (await api.patch(H + "/posts/999999999", headers=api.h,
                            json={"title": "x"})).status_code == 404
    assert (await api.post(H + "/posts", headers=api.h, json={
        "code": "c", "title": "t", "nope": 1})).status_code == 422
    assert (await api.post(H + "/posts", headers=api.h, json={
        "code": "c" * 41, "title": "t"})).status_code == 422
    r = await api.get(H + "/posts", params={"include_inactive": "false"},
                      headers=api.h)
    assert r.status_code == 200


async def test_holder_end_and_remove_reopen(api):
    u = api.u
    p = await _post(api, "R")
    pid = p["id"]
    t = api.today
    r = await api.post(H + f"/posts/{pid}/holders", headers=api.h,
                       json={"user_id": u["mgr"],
                             "starts_on": (t - timedelta(days=30)).isoformat()})
    assert r.status_code == 200
    first = r.json()["holders"][0]["id"]
    r = await api.post(H + f"/posts/{pid}/holders", headers=api.h, json={
        "user_id": u["mgr2"], "starts_on": (t + timedelta(days=2)).isoformat()})
    assert r.status_code == 200, r.text
    second = next(h["id"] for h in r.json()["holders"] if h["user_id"] == u["mgr2"])
    assert next(h for h in r.json()["holders"] if h["id"] == first)["ends_on"] \
        == (t + timedelta(days=1)).isoformat()
    # remove the not-yet-started one, reopening the first
    r = await api.post(H + f"/posts/{pid}/holders/{second}/remove",
                       headers=api.h, json={"reopen_previous": True})
    assert r.status_code == 200, r.text
    assert [h["id"] for h in r.json()["holders"]] == [first]
    assert r.json()["holders"][0]["ends_on"] is None
    assert r.json()["post"]["holder"]["user_id"] == u["mgr"]
    # without reopen the first stays ended
    r = await api.post(H + f"/posts/{pid}/holders", headers=api.h, json={
        "user_id": u["mgr2"], "starts_on": (t + timedelta(days=2)).isoformat()})
    second = next(h["id"] for h in r.json()["holders"] if h["user_id"] == u["mgr2"])
    r = await api.post(H + f"/posts/{pid}/holders/{second}/remove",
                       headers=api.h, json={})
    assert r.status_code == 200
    assert r.json()["holders"][0]["ends_on"] == (t + timedelta(days=1)).isoformat()
    # a holder that already started cannot be removed; bad types are 422
    r = await api.post(H + f"/posts/{pid}/holders/{first}/remove",
                       headers=api.h, json={})
    assert r.status_code == 422
    assert (await api.post(H + f"/posts/{pid}/holders/{first}/remove",
                           headers=api.h,
                           json={"reopen_previous": "yes"})).status_code == 422
    # end the first holder
    r = await api.post(H + f"/posts/{pid}/holders/{first}/end", headers=api.h,
                       json={"ends_on": t.isoformat()})
    assert r.status_code == 200, r.text
    assert r.json()["holders"][0]["ends_on"] == t.isoformat()
    r = await api.get(H + f"/posts/{pid}/holders", headers=api.h)
    assert r.status_code == 200 and len(r.json()["holders"]) == 1
    assert (await api.get(H + "/posts/999999999/holders",
                          headers=api.h)).status_code == 404


# ---------------------------------------------------------------- acting

async def test_acting_crud_and_out_of_office(api):
    u = api.u
    t = api.today
    r = await api.post(H + "/acting", headers=api.h, json={
        "covers_user_id": u["mgr"], "acting_user_id": u["act"],
        "subdomains": ["leave"], "reason": " holiday ",
        "original_can_act": True})
    assert r.status_code == 200, r.text
    c = r.json()
    assert c["source"] == "acting" and c["read_only"] is False
    assert c["reason"] == "holiday" and c["status"] == "live"
    assert c["covers_user_name"].startswith("Dop mgr")
    assert c["acting_user_name"].startswith("Dop act")
    aid = c["id"]
    for body in ({"covers_user_id": u["mgr"]},                       # no actor
                 {"covers_user_id": u["mgr"], "acting_user_id": u["mgr"]},
                 {"acting_user_id": u["act"]},                       # no target
                 {"covers_user_id": u["mgr"], "acting_user_id": u["act"],
                  "original_can_act": "true"},
                 {"covers_user_id": u["mgr"], "acting_user_id": u["act"],
                  "reason": "r" * 256},
                 {"covers_user_id": u["mgr"], "acting_user_id": u["act"],
                  "starts_on": "2026-13-45"},
                 {"covers_user_id": u["mgr"], "acting_user_id": u["act"],
                  "x": 1}):
        assert (await api.post(H + "/acting", headers=api.h,
                               json=body)).status_code == 422, body
    r = await api.patch(H + f"/acting/{aid}", headers=api.h, json={
        "original_can_act": False, "ends_on": (t + timedelta(days=5)).isoformat()})
    assert r.status_code == 200, r.text
    assert r.json()["original_can_act"] is False
    assert r.json()["ends_on"] == (t + timedelta(days=5)).isoformat()
    assert (await api.patch(H + f"/acting/{aid}", headers=api.h,
                            json={"acting_user_id": u["emp"]})
            ).status_code == 422
    # live out-of-office delegation is listed read-only
    from app.models.approver_delegation import ApproverDelegation
    async with SessionLocal() as db:
        d = ApproverDelegation(user_id=u["mgr2"], delegate_id=u["emp"],
                               starts_on=t, note="trip")
        db.add(d)
        await db.commit()
        did = d.id
    r = await api.get(H + "/acting", headers=api.h)
    items = r.json()
    ooo = next(x for x in items if x["source"] == "out_of_office"
               and x["id"] == did)
    assert ooo["read_only"] is True and ooo["covers_user_id"] == u["mgr2"]
    assert ooo["acting_user_id"] == u["emp"] and ooo["reason"] == "trip"
    # it is what the resolver reads: check shows emp acting for mgr2
    r = await api.post(H + "/check", headers=api.h, json={
        "user_id": u["act"], "subdomain": "leave",
        "approver": {"type": "specific_user", "ref": str(u["mgr2"])}})
    assert [a["user_id"] for a in r.json()["approvers"]] == [u["emp"], u["mgr2"]]
    # revoke; ended covers are hidden unless asked for
    r = await api.post(H + f"/acting/{aid}/revoke", headers=api.h)
    assert r.status_code == 200 and r.json()["status"] == "revoked"
    assert aid not in {x["id"] for x in (await api.get(
        H + "/acting", headers=api.h)).json() if x["source"] == "acting"}
    r = await api.get(H + "/acting", params={"include_ended": "true"},
                      headers=api.h)
    assert aid in {x["id"] for x in r.json() if x["source"] == "acting"}
    assert (await api.post(H + f"/acting/{aid}/revoke",
                           headers=api.h)).status_code == 409
    assert (await api.post(H + "/acting/999999999/revoke",
                           headers=api.h)).status_code == 404
    async with SessionLocal() as db:
        await db.execute(delete(ApproverDelegation).where(
            ApproverDelegation.id == did))
        await db.commit()


# ----------------------------------------------------------------- check

async def test_check_validation(api):
    u = api.u
    base = {"user_id": u["emp"], "subdomain": "leave",
            "approver": {"type": "reporting_manager"}}
    r = await api.post(H + "/check", headers=api.h, json=base)
    assert r.status_code == 200, r.text
    assert r.json()["via"] in ("hr", "blocked", "fallback", "primary")
    bad = [
        {**base, "subdomain": "nope"},
        {**base, "user_id": 999999999},
        {**base, "approver": {"type": "wizard"}},
        {**base, "approver": {"type": "specific_user", "ref": "abc"}},
        {**base, "approver": {"type": "specific_user", "ref": "999999999"}},
        {**base, "approver": {"type": "specific_user"}},
        {**base, "approver": {"type": "role", "ref": f"nope{api.sfx}"}},
        {**base, "approver": {"type": "post", "ref": "999999999"}},
        {**base, "approver": {"type": "post", "ref": "x"}},
        {**base, "approver": {"type": "manager_kind", "ref": "nope"}},
        {**base, "approver": {"type": "manager_kind"}},
        {**base, "fallback": {"type": "role", "ref": f"nope{api.sfx}"}},
        {**base, "on_date": "2026-02-30"},
        {**base, "extra": 1},
        {**base, "approver": {"type": "role", "ref": "HR", "x": 1}},
    ]
    for body in bad:
        r = await api.post(H + "/check", headers=api.h, json=body)
        assert r.status_code == 422, (body, r.status_code)
        if body.get("user_id") == 999999999:
            continue
        r = await api.post(H + "/check/all", headers=api.h, json={
            k: v for k, v in body.items() if k != "user_id"})
        assert r.status_code == 422, (body, r.status_code)
    # valid refs
    r = await api.post(H + "/check", headers=api.h, json={
        **base, "approver": {"type": "role", "ref": "HR"},
        "fallback": {"type": "dept_head_of_requester"}})
    assert r.status_code == 200, r.text
    r = await api.post(H + "/check", headers=api.h, json={
        **base, "approver": {"type": "specific_user", "ref": u["mgr"]}})
    assert r.status_code == 200, r.text            # int ref is accepted
    assert r.json()["approvers"][0]["user_id"] == u["mgr"]
    assert "Named person Dop mgr" in " ".join(r.json()["explanation"])


async def test_check_all_totals_and_cap(api):
    u = api.u
    p = await _post(api, "V")                      # vacant post
    body = {"subdomain": "leave",
            "approver": {"type": "post", "ref": str(p["id"])}}
    r = await api.post(H + "/check/all", headers=api.h, json=body)
    assert r.status_code == 200, r.text
    c = r.json()
    assert c["checked"] >= 7 and c["blocked_count"] == 0
    assert c["via_hr_count"] == c["checked"]       # nobody holds the post
    assert len(c["via_hr"]) == min(200, c["via_hr_count"])
    assert c["truncated"] == (c["via_hr_count"] > 200)
    names = [x["name"] for x in c["via_hr"]]
    assert names == sorted(names, key=str.casefold)
    assert set(c["via_hr"][0]) >= {"user_id", "name", "department", "reason"}
    ids = {x["user_id"] for x in c["via_hr"]}
    assert u["off"] not in ids                     # inactive never checked
    # a named person: everyone but that person goes to them, no HR
    r = await api.post(H + "/check/all", headers=api.h, json={
        "subdomain": "leave",
        "approver": {"type": "specific_user", "ref": str(u["mgr"])}})
    c = r.json()
    assert c["via_hr_count"] <= 1                  # mgr themself
    assert c["blocked_count"] == 0


# ------------------------------------------------------- bulk, at scale

class _Q:
    def __enter__(self):
        self.n = 0

        def cb(conn, cursor, statement, parameters, context, many):
            self.n += 1
        self.cb = cb
        event.listen(engine.sync_engine, "before_cursor_execute", cb)
        return self

    def __exit__(self, *a):
        event.remove(engine.sync_engine, "before_cursor_execute", self.cb)


async def test_bulk_60_users_query_count(api):
    ids = await _mk_users(api.sfx, 60)
    with _Q() as q:
        r = await api.post(H + "/assignments/bulk", headers=api.h,
                           json=_bulk(api, ids, api.u["mgr"]))
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 60
    print("QUERIES bulk 60:", q.n)
    assert q.n < 400
    async with SessionLocal() as db:
        got = set((await db.execute(select(User.manager_id).where(
            User.id.in_(ids)))).scalars().all())
    assert got == {api.u["mgr"]}
    # replace them all in one go, still bounded
    with _Q() as q:
        r = await api.post(H + "/assignments/bulk", headers=api.h, json=_bulk(
            api, ids, api.u["mgr2"], replace=True))
    assert r.status_code == 200 and r.json()["replaced"] == 60, r.text
    print("QUERIES bulk 60 replace:", q.n)
    assert q.n < 400


async def test_bulk_200_users_query_count(api):
    ids = await _mk_users(api.sfx, 200, "c")
    with _Q() as q:
        r = await api.post(H + "/assignments/bulk", headers=api.h,
                           json=_bulk(api, ids, api.u["mgr"]))
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 200
    print("QUERIES bulk 200:", q.n)
    assert q.n < 1000


# ------------------------------------------------------------ concurrency

async def test_two_identical_bulks_no_5xx(api):
    u = api.u
    body = _bulk(api, [u["emp"], u["act"]], u["mgr"])
    r1, r2 = await asyncio.gather(
        api.post(H + "/assignments/bulk", headers=api.h, json=body),
        api.post(H + "/assignments/bulk", headers=api.h, json=body))
    assert sorted([r1.status_code, r2.status_code]) == [200, 409], (
        r1.text, r2.text)
    ok = r1 if r1.status_code == 200 else r2
    assert ok.json()["created"] == 2
    rows = [x for x in await _rows([u["emp"], u["act"]])]
    assert len(rows) == 2


async def test_bulk_vs_hr_patch_no_5xx(api):
    u = api.u
    async with SessionLocal() as db:
        eid = (await db.execute(select(Employee.id).where(
            Employee.user_id == u["emp"]))).scalar_one()
    for _ in range(3):
        rs = await asyncio.gather(
            api.post(H + "/assignments/bulk", headers=api.h, json=_bulk(
                api, [u["emp"], u["act"]], u["mgr"], replace=True)),
            api.patch(f"{HR}/employees/{eid}", headers=api.h,
                      json={"manager_id": u["mgr2"]}))
        assert all(r.status_code < 500 for r in rs), [r.text for r in rs]
    # exactly one live all-subdomain row for emp and the mirror agrees
    live = [x for x in await _rows([u["emp"]]) if x.cancelled_at is None
            and (x.ends_on is None or x.ends_on >= api.today)]
    assert len(live) == 1
    assert await _mgr(u["emp"]) == live[0].manager_user_id


async def test_two_posts_same_code_no_5xx(api):
    body = {"code": f"DUP{api.sfx}", "title": "T"}
    rs = await asyncio.gather(
        api.post(H + "/posts", headers=api.h, json=body),
        api.post(H + "/posts", headers=api.h, json=body))
    assert sorted(r.status_code for r in rs) == [200, 409], [r.text for r in rs]


async def test_response_after_forced_retry_is_complete(api, monkeypatch):
    u = api.u
    real = A.create_many
    calls = {"n": 0}

    class _Orig(Exception):
        args = (1020, "snapshot")

    async def flaky(db, **kw):
        calls["n"] += 1
        out = await real(db, **kw)            # work done, then the conflict
        if calls["n"] == 1:
            raise OperationalError("stmt", {}, _Orig())
        return out
    monkeypatch.setattr(A, "create_many", flaky)
    r = await api.post(H + "/assignments/bulk", headers=api.h,
                       json=_bulk(api, [u["emp"], u["act"]], u["mgr"]))
    assert r.status_code == 200, r.text
    assert calls["n"] == 2
    assert r.json()["created"] == 2 and len(r.json()["assignment_ids"]) == 2
    assert await _mgr(u["emp"]) == u["mgr"]
    # same for a post: row comes back whole after a retry
    real_p = __import__("app.services.dop.posts", fromlist=["x"])
    rc = real_p.create
    n = {"n": 0}

    async def flaky_post(db, **kw):
        n["n"] += 1
        out = await rc(db, **kw)
        if n["n"] == 1:
            raise OperationalError("stmt", {}, _Orig())
        return out
    monkeypatch.setattr(real_p, "create", flaky_post)
    r = await api.post(H + "/posts", headers=api.h, json={
        "code": f"RT{api.sfx}", "title": "Retry"})
    assert r.status_code == 200 and n["n"] == 2, r.text
    assert r.json()["title"] == "Retry" and r.json()["code"] == f"RT{api.sfx}"
    assert r.json()["holder"] is None and r.json()["acting"] == []


async def test_dev_users_untouched(api):
    """Read-only endpoints never change anyone's manager."""
    async with SessionLocal() as db:
        before = dict((await db.execute(select(
            User.id, User.manager_id).where(
            User.id.in_([135, 70898, 70900, 72360, 173062])))).all())
    await api.get(H + "/managers", headers=api.h, params={"limit": 100})
    await api.post(H + "/check/all", headers=api.h, json={
        "subdomain": "leave", "approver": {"type": "reporting_manager"}})
    async with SessionLocal() as db:
        after = dict((await db.execute(select(
            User.id, User.manager_id).where(
            User.id.in_([135, 70898, 70900, 72360, 173062])))).all())
    assert before == after
