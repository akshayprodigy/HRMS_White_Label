"""Multi-user demo flow smoke test (production-safe).

Logs in as each demo user created by scripts/seed_demo_users.py and verifies
that their main role flows are reachable.

Writes: may mark attendance for each user if not already marked today.
All other checks are GET requests.

Run (inside backend container):
  ERP_BASE_URL=http://backend:8000/api/v1 ERP_PASSWORD=... \
  python demo_users_flow_smoke_test.py

By default uses the demo emails from seed_demo_users.py and ERP_PASSWORD.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

import httpx


BASE_URL = os.getenv(
    "ERP_BASE_URL", "http://localhost:8000/api/v1"
).rstrip("/")
PASSWORD = os.getenv("ERP_PASSWORD", "test@12345")


@dataclass(frozen=True)
class UserCase:
    email: str
    name: str
    endpoints: list[str]


BASE_ENDPOINTS = [
    "/health",
    "/auth/me",
    "/attendance/today",
    "/approvals/inbox",
    "/notifications/",
    "/admin/projects",
    "/tasks/my-tasks",
]

TIMESHEET_ENDPOINTS = [
    "/timesheets/my?range=weekly",
]

LEAVE_ENDPOINTS = [
    "/leave/balances",
]

HR_EMPLOYEES_MIN = "/hr/employees?page=1&size=1"
REPORTS_SUMMARY = "/reports/summary"


USERS: list[UserCase] = [
    UserCase(
        email="employee@gmail.com",
        name="Employee",
        endpoints=BASE_ENDPOINTS + TIMESHEET_ENDPOINTS + LEAVE_ENDPOINTS,
    ),
    UserCase(
        email="pm@gmail.com",
        name="PM",
        endpoints=BASE_ENDPOINTS
        + TIMESHEET_ENDPOINTS
        + LEAVE_ENDPOINTS
        + [
            "/bd/pipeline",
        ],
    ),
    UserCase(
        email="hr@gmail.com",
        name="HR",
        endpoints=BASE_ENDPOINTS
        + TIMESHEET_ENDPOINTS
        + LEAVE_ENDPOINTS
        + [
            "/hr/dashboard/stats",
            HR_EMPLOYEES_MIN,
            REPORTS_SUMMARY,
        ],
    ),
    UserCase(
        email="bd@gmail.com",
        name="Business Developer",
        endpoints=BASE_ENDPOINTS
        + TIMESHEET_ENDPOINTS
        + [
            "/bd/pipeline",
            "/bd/leads?limit=1",
            "/bd/dashboard",
        ],
    ),
    UserCase(
        email="ceo@gmail.com",
        name="CEO",
        endpoints=BASE_ENDPOINTS
        + TIMESHEET_ENDPOINTS
        + LEAVE_ENDPOINTS
        + [
            REPORTS_SUMMARY,
            "/bd/dashboard",
            "/bd/reports/estimate-accuracy",
            HR_EMPLOYEES_MIN,
        ],
    ),
    UserCase(
        email="admin@gmail.com",
        name="Super Admin",
        endpoints=BASE_ENDPOINTS
        + TIMESHEET_ENDPOINTS
        + LEAVE_ENDPOINTS
        + [
            REPORTS_SUMMARY,
            HR_EMPLOYEES_MIN,
            "/admin/users",
        ],
    ),
]


def fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    sys.exit(1)


def info(msg: str) -> None:
    print(msg)


async def login(client: httpx.AsyncClient, email: str, password: str) -> str:
    resp = await client.post(
        f"{BASE_URL}/auth/login",
        data={"username": email, "password": password},
    )
    if resp.status_code != 200:
        raise RuntimeError(f"login {resp.status_code}: {resp.text}")
    token = (resp.json() or {}).get("access_token")
    if not token:
        raise RuntimeError("login missing access_token")
    return token


async def ensure_attendance_marked(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    email: str,
) -> None:
    today = await client.get(f"{BASE_URL}/attendance/today", headers=headers)
    if today.status_code != 200:
        raise RuntimeError(
            f"attendance/today {today.status_code}: {today.text}"
        )
    is_marked = bool((today.json() or {}).get("is_marked"))
    if is_marked:
        return

    mark = await client.post(
        f"{BASE_URL}/attendance/mark",
        headers=headers,
        json={"mode": "office", "remarks": f"smoke test: {email}"},
    )
    if mark.status_code != 200:
        raise RuntimeError(f"attendance/mark {mark.status_code}: {mark.text}")


async def check_endpoint(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    endpoint: str,
) -> None:
    # /health is mounted at /health, so full path is /api/v1/health
    url = f"{BASE_URL}{endpoint}"
    resp = await client.get(url, headers=headers)
    if resp.status_code >= 400:
        raise RuntimeError(
            f"GET {endpoint} {resp.status_code}: {resp.text}"
        )


async def run_user_case(client: httpx.AsyncClient, case: UserCase) -> None:
    info(f"== {case.name} ({case.email}) ==")

    token = await login(client, case.email, PASSWORD)
    headers = {"Authorization": f"Bearer {token}"}

    await ensure_attendance_marked(client, headers, case.email)

    for endpoint in case.endpoints:
        await check_endpoint(client, headers, endpoint)
        info(f"OK: {case.email} {endpoint}")


async def main() -> None:
    timeout = httpx.Timeout(30.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        for case in USERS:
            try:
                await run_user_case(client, case)
            except Exception as exc:
                fail(f"{case.email}: {exc}")

    info("ALL OK")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
