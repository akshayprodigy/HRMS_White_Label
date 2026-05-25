"""Read-only production smoke test.

Goal: Validate that auth + attendance gate + key list endpoints are working,
without creating business data like leads/projects/tasks.

This script MAY mark attendance for the smoke-test user if not already marked.
That is the only write operation.

Run inside backend container:
  ERP_BASE_URL=http://backend:8000/api/v1 \
  ERP_USERNAME=admin@gmail.com \
  ERP_PASSWORD=... \
  python readonly_smoke_test.py
"""

import os
import sys
import httpx


BASE_URL = os.getenv(
    "ERP_BASE_URL", "http://localhost:8000/api/v1"
).rstrip("/")
USERNAME = os.getenv("ERP_USERNAME")
PASSWORD = os.getenv("ERP_PASSWORD")


def fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    sys.exit(1)


def ok(msg: str) -> None:
    print(f"OK: {msg}")


async def login_and_get_headers(client: httpx.AsyncClient) -> dict:
    resp = await client.post(
        f"{BASE_URL}/auth/login",
        data={"username": USERNAME, "password": PASSWORD},
    )
    if resp.status_code != 200:
        fail(f"login {resp.status_code}: {resp.text}")
    token = (resp.json() or {}).get("access_token")
    if not token:
        fail("login did not return access_token")
    ok("login")
    return {"Authorization": f"Bearer {token}"}


async def get_ok(
    client: httpx.AsyncClient, *, name: str, url: str, headers: dict
) -> httpx.Response:
    r = await client.get(url, headers=headers)
    if r.status_code >= 400:
        fail(f"{name} {r.status_code}: {r.text}")
    ok(name)
    return r


async def ensure_attendance_marked(
    client: httpx.AsyncClient, *, headers: dict
) -> None:
    today = await get_ok(
        client,
        name="attendance/today",
        url=f"{BASE_URL}/attendance/today",
        headers=headers,
    )
    is_marked = bool((today.json() or {}).get("is_marked"))
    if is_marked:
        ok("attendance already marked")
        return

    mark = await client.post(
        f"{BASE_URL}/attendance/mark",
        headers=headers,
        json={"mode": "office", "remarks": "prod smoke test"},
    )
    if mark.status_code != 200:
        fail(f"attendance/mark {mark.status_code}: {mark.text}")
    ok("attendance/mark (was not marked)")


async def check_payroll_readonly(
    client: httpx.AsyncClient, *, headers: dict
) -> None:
    # NOTE: Do NOT create/lock/finalize/publish runs in production smoke tests.
    dashboard = await get_ok(
        client,
        name="payroll dashboard",
        url=f"{BASE_URL}/hr/payroll/dashboard",
        headers=headers,
    )
    data = dashboard.json() or {}
    active_runs = data.get("active_runs") or []
    if not active_runs:
        ok("payroll lines (skipped: no active runs)")
        return

    run_id = (active_runs[0] or {}).get("id")
    if not isinstance(run_id, int):
        ok("payroll lines (skipped: run_id missing)")
        return

    await get_ok(
        client,
        name=f"payroll lines (run_id={run_id})",
        url=f"{BASE_URL}/hr/payroll/{run_id}/lines",
        headers=headers,
    )


async def main() -> None:
    if not USERNAME or not PASSWORD:
        fail("ERP_USERNAME and ERP_PASSWORD must be set")

    timeout = httpx.Timeout(20.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        # 1) Login
        headers = await login_and_get_headers(client)

        # 2) /auth/me
        await get_ok(
            client,
            name="auth/me",
            url=f"{BASE_URL}/auth/me",
            headers=headers,
        )

        # 3) Attendance gate helper
        await ensure_attendance_marked(client, headers=headers)

        # 4) Key read-only endpoints (typically attendance-gated)
        endpoints = [
            ("health", f"{BASE_URL}/health"),
            ("projects list", f"{BASE_URL}/admin/projects"),
            ("tasks my-tasks", f"{BASE_URL}/tasks/my-tasks"),
            ("leave balances", f"{BASE_URL}/leave/balances"),
            (
                "timesheets my (weekly)",
                f"{BASE_URL}/timesheets/my?range=weekly",
            ),
            ("approvals inbox", f"{BASE_URL}/approvals/inbox"),
            ("notifications", f"{BASE_URL}/notifications/"),
        ]

        for name, url in endpoints:
            await get_ok(client, name=name, url=url, headers=headers)

        # 5) Payroll Bureau (read-only)
        await check_payroll_readonly(client, headers=headers)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
