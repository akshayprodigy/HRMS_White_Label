"""Client Details write smoke test.

Goal: Validate that client create + client details GET/PATCH are working.

This script WILL create (or reuse) a deterministic "SMOKE" client record
and will update its client_details fields.

Run inside backend container:
  ERP_BASE_URL=http://backend:8000/api/v1 \
  ERP_USERNAME=someone@company.com \
  ERP_PASSWORD=... \
  python client_details_smoke_test.py

Optional (to also confirm BD is read-only):
  ERP_BD_USERNAME=bd@company.com \
  ERP_BD_PASSWORD=... \

Notes:
- Clients routes are attendance-gated; this script may mark attendance
  for the smoke-test user if not already marked.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

import httpx


BASE_URL = os.getenv(
    "ERP_BASE_URL", "http://localhost:8000/api/v1"
).rstrip("/")
USERNAME = os.getenv("ERP_USERNAME")
PASSWORD = os.getenv("ERP_PASSWORD")
BD_USERNAME = os.getenv("ERP_BD_USERNAME")
BD_PASSWORD = os.getenv("ERP_BD_PASSWORD")


def fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    sys.exit(1)


def ok(msg: str) -> None:
    print(f"OK: {msg}")


async def login_and_get_headers(
    client: httpx.AsyncClient, *, username: str, password: str
) -> dict:
    resp = await client.post(
        f"{BASE_URL}/auth/login",
        data={"username": username, "password": password},
    )
    if resp.status_code != 200:
        fail(f"login({username}) {resp.status_code}: {resp.text}")
    token = (resp.json() or {}).get("access_token")
    if not token:
        fail(f"login({username}) did not return access_token")
    return {"Authorization": f"Bearer {token}"}


async def ensure_attendance_marked(
    client: httpx.AsyncClient, *, headers: dict
) -> None:
    today = await client.get(f"{BASE_URL}/attendance/today", headers=headers)
    if today.status_code >= 400:
        fail(f"attendance/today {today.status_code}: {today.text}")

    is_marked = bool((today.json() or {}).get("is_marked"))
    if is_marked:
        ok("attendance already marked")
        return

    mark = await client.post(
        f"{BASE_URL}/attendance/mark",
        headers=headers,
        json={"mode": "office", "remarks": "client details smoke test"},
    )
    if mark.status_code != 200:
        fail(f"attendance/mark {mark.status_code}: {mark.text}")
    ok("attendance/mark (was not marked)")


def assert_ok(
    resp: httpx.Response, *, name: str, allow: tuple[int, ...] = (200,)
) -> None:
    if resp.status_code not in allow:
        fail(f"{name} {resp.status_code}: {resp.text}")


def _smoke_client_name() -> str:
    # Deterministic name per day to avoid unbounded client creation.
    today_utc = datetime.now(timezone.utc).date().isoformat()
    return f"SMOKE Client Details {today_utc}"


async def main() -> None:
    if not USERNAME or not PASSWORD:
        fail("ERP_USERNAME and ERP_PASSWORD must be set")

    assert USERNAME is not None
    assert PASSWORD is not None
    username: str = USERNAME
    password: str = PASSWORD

    timeout = httpx.Timeout(25.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        # 1) Login as writer user
        headers = await login_and_get_headers(
            client, username=username, password=password
        )
        ok("login")

        # 2) Attendance gating
        await ensure_attendance_marked(client, headers=headers)

        # 3) Create/reuse client
        name = _smoke_client_name()
        create_payload = {
            "name": name,
            "domain": "smoke.local",
            "industry": "SmokeTest",
        }
        created = await client.post(
            f"{BASE_URL}/clients/",
            headers=headers,
            json=create_payload,
        )
        assert_ok(created, name="clients create", allow=(200, 201))
        client_obj = created.json() or {}
        client_id = client_obj.get("id")
        if not isinstance(client_id, int):
            fail(f"clients create did not return id: {client_obj}")
        ok(f"client ready (id={client_id})")

        # 4) Patch details
        details_payload = {
            "address": "Smoke Address, Example Street",
            "email": "smoke.client@example.com",
            "website": "https://example.com",
            "contact_person_name": "Smoke Person",
            "contact_person_phone": "+91-9999999999",
            "contact_person_email": "smoke.contact@example.com",
            "gst_number": "SMOKE-GST-1234",
        }
        patch = await client.patch(
            f"{BASE_URL}/clients/{client_id}/details",
            headers=headers,
            json=details_payload,
        )
        assert_ok(patch, name="clients details patch")
        ok("client details patched")

        # 5) Get details and verify
        details = await client.get(
            f"{BASE_URL}/clients/{client_id}/details",
            headers=headers,
        )
        assert_ok(details, name="clients details get")
        data = details.json() or {}
        for key, expected in details_payload.items():
            if (data.get(key) or "") != expected:
                got = data.get(key)
                fail(
                    "details mismatch for "
                    f"{key}: expected={expected!r} got={got!r}"
                )
        if data.get("account_id") != client_id:
            got_id = data.get("account_id")
            fail(
                "details account_id mismatch: "
                f"expected {client_id} got {got_id}"
            )
        ok("client details verified")

        # 6) Optional: BD user cannot patch
        if BD_USERNAME and BD_PASSWORD:
            bd_headers = await login_and_get_headers(
                client, username=BD_USERNAME, password=BD_PASSWORD
            )
            await ensure_attendance_marked(client, headers=bd_headers)
            bd_patch = await client.patch(
                f"{BASE_URL}/clients/{client_id}/details",
                headers=bd_headers,
                json={"address": "BD should not be able to write"},
            )
            if bd_patch.status_code < 400:
                fail(
                    "BD patch unexpectedly succeeded; "
                    "expected permission error"
                )
            ok("BD write blocked (as expected)")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
