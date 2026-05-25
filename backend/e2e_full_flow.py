import asyncio
import os
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

import httpx

BASE_URL = os.getenv("ERP_BASE_URL", "http://localhost:8001/api/v1")
PASSWORD = os.getenv("ERP_PASSWORD", "test@12345")


def _fail(step: str, resp: httpx.Response) -> None:
    raise RuntimeError(f"{step} failed: {resp.status_code} {resp.text}")


async def login(client: httpx.AsyncClient, username: str, password: str) -> Tuple[str, Dict[str, str]]:
    resp = await client.post(f"{BASE_URL}/auth/login", data={"username": username, "password": password})
    if resp.status_code != 200:
        _fail(f"Login({username})", resp)
    token = resp.json()["access_token"]
    return token, {"Authorization": f"Bearer {token}"}


async def ensure_attendance(client: httpx.AsyncClient, headers: Dict[str, str]) -> None:
    today = await client.get(f"{BASE_URL}/attendance/today", headers=headers)
    if today.status_code == 200 and today.json().get("is_marked") is True:
        return

    mark = await client.post(
        f"{BASE_URL}/attendance/mark",
        headers=headers,
        json={"mode": "office", "remarks": "E2E full flow"},
    )
    if mark.status_code == 200:
        return
    if mark.status_code == 400:
        try:
            if (mark.json() or {}).get("error", {}).get("code") == "ALREADY_MARKED":
                return
        except Exception:
            pass
    _fail("Attendance mark", mark)


async def get_admin_user_ids(client: httpx.AsyncClient, admin_headers: Dict[str, str]) -> Dict[str, int]:
    resp = await client.get(f"{BASE_URL}/admin/users", headers=admin_headers)
    if resp.status_code != 200:
        _fail("Admin list users", resp)
    users = resp.json()
    lookup = {u["email"]: u["id"] for u in users}
    for required in ["admin@gmail.com", "hr@gmail.com", "pm@gmail.com", "employee@gmail.com", "bd@gmail.com", "ceo@gmail.com"]:
        if required not in lookup:
            raise RuntimeError(f"Seed user missing: {required}")
    return lookup


async def pick_project_id(client: httpx.AsyncClient, admin_headers: Dict[str, str]) -> Optional[int]:
    resp = await client.get(f"{BASE_URL}/admin/projects", headers=admin_headers)
    if resp.status_code != 200:
        return None
    items = resp.json() or []
    if not items:
        return None
    # API returns list; pick newest
    return int(items[-1]["id"])


async def hr_create_employee(
    client: httpx.AsyncClient,
    admin_headers: Dict[str, str],
    hr_headers: Dict[str, str],
) -> None:
    unique = int(time.time())
    email = f"e2e.employee.{unique}@example.com"

    user_resp = await client.post(
        f"{BASE_URL}/admin/users",
        headers=admin_headers,
        json={"email": email, "password": PASSWORD, "full_name": f"E2E Employee {unique}", "is_active": True},
    )
    if user_resp.status_code not in (200, 201):
        _fail("Admin create user", user_resp)
    user_id = int(user_resp.json()["id"])

    emp_payload = {
        "employee_id": f"E2E-{unique}",
        "department": "Engineering",
        "designation": "Developer",
        "date_of_joining": str(date.today()),
        "user_id": user_id,
        "salary": 100000.0,
        "bank_account": "000111222333",
        "pan_number": "ABCDE1234F",
    }
    emp_resp = await client.post(f"{BASE_URL}/hr/employees", headers=hr_headers, json=emp_payload)
    if emp_resp.status_code != 200:
        _fail("HR create employee", emp_resp)

    list_resp = await client.get(f"{BASE_URL}/hr/employees", headers=hr_headers)
    if list_resp.status_code != 200:
        _fail("HR list employees", list_resp)


async def apply_leave_with_retry(
    client: httpx.AsyncClient,
    employee_headers: Dict[str, str],
    leave_type_id: int,
    *,
    is_half_day: bool,
) -> int:
    def _parse_date(value: Any) -> Optional[date]:
        if not value:
            return None
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        try:
            return date.fromisoformat(str(value))
        except Exception:
            return None

    base_start = date.today() + timedelta(days=30)
    mine = await client.get(f"{BASE_URL}/leave/my", headers=employee_headers)
    if mine.status_code == 200:
        items = mine.json() or []
        max_end: Optional[date] = None
        for item in items:
            status = str(item.get("status") or "").lower()
            if status in {"rejected", "cancelled", "canceled"}:
                continue
            end_dt = _parse_date(item.get("end_date"))
            if end_dt and (max_end is None or end_dt > max_end):
                max_end = end_dt
        if max_end:
            base_start = max(base_start, max_end + timedelta(days=7))

    # Search forward for a date window that doesn't overlap existing requests.
    # Some test DBs accumulate lots of future leaves across runs.
    max_attempts = 60
    step_days = 3
    for attempt in range(max_attempts):
        start = base_start + timedelta(days=attempt * step_days)
        end = start if is_half_day else start + timedelta(days=1)
        apply = await client.post(
            f"{BASE_URL}/leave/apply",
            headers=employee_headers,
            json={
                "leave_type_id": leave_type_id,
                "start_date": str(start),
                "end_date": str(end),
                "is_half_day": is_half_day,
                "half_day_session": "AM" if is_half_day else None,
                "reason": f"E2E vacation (attempt {attempt + 1})",
            },
        )
        if apply.status_code == 200:
            return int(apply.json()["id"])

        if apply.status_code == 400:
            try:
                err = (apply.json() or {}).get("error", {})
                if "overlaps" in str(err.get("message", "")).lower():
                    continue
            except Exception:
                pass

        _fail("Leave apply", apply)

    raise RuntimeError("Unable to apply leave without overlapping existing requests")


def find_approval_item(
    inbox_items: list[dict[str, Any]],
    leave_id: int,
) -> Optional[dict[str, Any]]:
    return next(
        (
            item
            for item in (inbox_items or [])
            if str(item.get("resource_id")) == str(leave_id)
        ),
        None,
    )


async def leave_flow(
    client: httpx.AsyncClient,
    employee_headers: Dict[str, str],
    pm_headers: Dict[str, str],
    hr_headers: Dict[str, str],
) -> None:
    bal = await client.get(
        f"{BASE_URL}/leave/balances", headers=employee_headers
    )
    if bal.status_code != 200:
        _fail("Leave balances", bal)
    balances = bal.json() or []
    best = max(
        balances,
        key=lambda b: float(b.get("remaining") or 0),
        default=None,
    )
    if not best or float(best.get("remaining") or 0) <= 0:
        raise RuntimeError("No leave balance available to run leave E2E")

    leave_type_id = int(best["leave_type"]["id"])
    remaining = float(best.get("remaining") or 0)
    use_half_day = remaining < 1 and remaining >= 0.5

    leave_id = await apply_leave_with_retry(
        client,
        employee_headers,
        leave_type_id,
        is_half_day=use_half_day,
    )

    inbox_pm = await client.get(
        f"{BASE_URL}/leave/approvals/inbox", headers=pm_headers
    )
    if inbox_pm.status_code != 200:
        _fail("PM leave inbox", inbox_pm)
    pm_item = find_approval_item(inbox_pm.json() or [], leave_id)
    if not pm_item:
        raise RuntimeError("PM approval item not found")

    act = await client.post(
        f"{BASE_URL}/leave/approvals/{pm_item['id']}/action",
        headers=pm_headers,
        json={"status": "approved", "comment": "E2E manager approval"},
    )
    if act.status_code != 200:
        _fail("PM approve leave", act)

    inbox_hr = await client.get(
        f"{BASE_URL}/leave/approvals/inbox", headers=hr_headers
    )
    if inbox_hr.status_code != 200:
        _fail("HR leave inbox", inbox_hr)
    hr_item = find_approval_item(inbox_hr.json() or [], leave_id)
    if not hr_item:
        raise RuntimeError("HR approval item not found")

    act2 = await client.post(
        f"{BASE_URL}/leave/approvals/{hr_item['id']}/action",
        headers=hr_headers,
        json={"status": "approved", "comment": "E2E HR approval"},
    )
    if act2.status_code != 200:
        _fail("HR approve leave", act2)

    mine = await client.get(f"{BASE_URL}/leave/my", headers=employee_headers)
    if mine.status_code != 200:
        _fail("Leave my", mine)
    target = next(
        (
            leave_item
            for leave_item in (mine.json() or [])
            if leave_item.get("id") == leave_id
        ),
        None,
    )
    if not target:
        raise RuntimeError("Leave not found in employee list")
    if target.get("status") != "approved":
        raise RuntimeError(f"Expected approved, got {target.get('status')}")


async def timesheet_timer_flow(
    client: httpx.AsyncClient,
    employee_headers: Dict[str, str],
    project_id: int,
) -> None:
    status0 = await client.get(
        f"{BASE_URL}/timesheets/timer/status", headers=employee_headers
    )
    if status0.status_code != 200:
        _fail("Timer status", status0)

    # Ensure idempotency: previous runs may have left an active timer.
    try:
        if (status0.json() or {}).get("is_active") is True:
            cleanup = await client.post(
                f"{BASE_URL}/timesheets/timer/stop",
                headers=employee_headers,
            )
            if cleanup.status_code != 200:
                _fail("Timer cleanup stop", cleanup)
    except Exception:
        pass

    start = await client.post(
        f"{BASE_URL}/timesheets/timer/start",
        headers=employee_headers,
        json={"project_id": project_id, "notes": "E2E work"},
    )
    if start.status_code != 200:
        retryable = False
        if start.status_code == 400:
            try:
                err = (start.json() or {}).get("error", {})
                retryable = err.get("code") == "ACTIVE_TIMER_EXISTS"
            except Exception:
                retryable = False
        if retryable:
            cleanup = await client.post(
                f"{BASE_URL}/timesheets/timer/stop",
                headers=employee_headers,
            )
            if cleanup.status_code != 200:
                _fail("Timer cleanup stop", cleanup)
            start = await client.post(
                f"{BASE_URL}/timesheets/timer/start",
                headers=employee_headers,
                json={"project_id": project_id, "notes": "E2E work"},
            )
        if start.status_code != 200:
            _fail("Timer start", start)

    # One-active-timer rule: starting again should fail
    start2 = await client.post(
        f"{BASE_URL}/timesheets/timer/start",
        headers=employee_headers,
        json={"project_id": project_id, "notes": "Should fail"},
    )
    if start2.status_code == 200:
        raise RuntimeError(
            "Timer started twice; expected one-active-timer rule enforcement"
        )

    pause = await client.post(
        f"{BASE_URL}/timesheets/timer/pause", headers=employee_headers
    )
    if pause.status_code != 200:
        _fail("Timer pause", pause)

    resume = await client.post(
        f"{BASE_URL}/timesheets/timer/resume", headers=employee_headers
    )
    if resume.status_code != 200:
        _fail("Timer resume", resume)

    stop = await client.post(
        f"{BASE_URL}/timesheets/timer/stop", headers=employee_headers
    )
    if stop.status_code != 200:
        _fail("Timer stop", stop)

    my = await client.get(
        f"{BASE_URL}/timesheets/my", headers=employee_headers
    )
    if my.status_code != 200:
        _fail("Timesheets my", my)


async def payroll_flow(
    client: httpx.AsyncClient, hr_headers: Dict[str, str]
) -> None:
    now = datetime.now(timezone.utc)
    run = await client.post(
        f"{BASE_URL}/hr/payroll/run",
        headers=hr_headers,
        json={"month": now.month, "year": now.year},
    )
    run_id: Optional[int] = None
    run_status: Optional[str] = None

    if run.status_code == 200:
        run_id = int(run.json()["id"])
        run_status = str(run.json().get("status"))
    elif run.status_code == 400:
        dash = await client.get(
            f"{BASE_URL}/hr/payroll/dashboard", headers=hr_headers
        )
        if dash.status_code != 200:
            _fail("Payroll dashboard", dash)
        active = (dash.json() or {}).get("active_runs") or []
        match = next(
            (
                r
                for r in active
                if int(r.get("month")) == now.month
                and int(r.get("year")) == now.year
            ),
            None,
        )
        if match:
            run_id = int(match["id"])
            run_status = str(match.get("status"))
        else:
            # Likely already PUBLISHED (dashboard only includes non-published).
            return
    else:
        _fail("Payroll create run", run)

    if run_id is None:
        raise RuntimeError("Unable to resolve payroll run id")

    async def post_action(path: str) -> dict[str, Any]:
        resp = await client.post(path, headers=hr_headers)
        if resp.status_code != 200:
            _fail(f"Payroll action {path}", resp)
        return resp.json().get("run") or {}

    # Advance run through the lifecycle based on current status.
    for _ in range(8):
        if run_status in ("published", None):
            break

        if run_status == "draft":
            run_obj = await post_action(
                f"{BASE_URL}/hr/payroll/{run_id}/lock-attendance"
            )
        elif run_status == "attendance_locked":
            run_obj = await post_action(
                f"{BASE_URL}/hr/payroll/{run_id}/lock-leaves"
            )
        elif run_status == "leaves_locked":
            run_obj = await post_action(
                f"{BASE_URL}/hr/payroll/{run_id}/generate-draft"
            )
        elif run_status == "draft_generated":
            run_obj = await post_action(
                f"{BASE_URL}/hr/payroll/{run_id}/finalize"
            )
        elif run_status == "finalized":
            run_obj = await post_action(
                f"{BASE_URL}/hr/payroll/{run_id}/publish"
            )
        else:
            raise RuntimeError(f"Unknown payroll run status: {run_status}")

        run_status = str(run_obj.get("status"))

    dash = await client.get(
        f"{BASE_URL}/hr/payroll/dashboard", headers=hr_headers
    )
    if dash.status_code != 200:
        _fail("Payroll dashboard", dash)


async def project_milestone_flow(
    client: httpx.AsyncClient,
    pm_headers: Dict[str, str],
    project_id: int,
) -> None:
    due = (datetime.now(timezone.utc) + timedelta(days=14)).isoformat()
    resp = await client.post(
        f"{BASE_URL}/projects/{project_id}/milestones",
        headers=pm_headers,
        json={
            "title": "E2E Milestone",
            "description": "E2E milestone",
            "due_date": due,
            "status": "pending",
        },
    )
    if resp.status_code != 200:
        _fail("Create milestone", resp)

    lst = await client.get(
        f"{BASE_URL}/projects/{project_id}/milestones", headers=pm_headers
    )
    if lst.status_code != 200:
        _fail("List milestones", lst)


async def main() -> None:
    async with httpx.AsyncClient(timeout=45.0) as client:
        # Logins
        _, admin_headers = await login(client, "admin@gmail.com", PASSWORD)
        _, hr_headers = await login(client, "hr@gmail.com", PASSWORD)
        _, pm_headers = await login(client, "pm@gmail.com", PASSWORD)
        _, employee_headers = await login(
            client, "employee@gmail.com", PASSWORD
        )

        # Attendance gating (skip admin; required for others)
        await ensure_attendance(client, hr_headers)
        await ensure_attendance(client, pm_headers)
        await ensure_attendance(client, employee_headers)

        # Admin data
        _ = await get_admin_user_ids(client, admin_headers)
        project_id = await pick_project_id(client, admin_headers)

        # HR: create employee (needs admin user creation first)
        await hr_create_employee(client, admin_headers, hr_headers)

        # Leave approvals: employee -> PM -> HR
        await leave_flow(client, employee_headers, pm_headers, hr_headers)

        if project_id is None:
            raise RuntimeError(
                "No projects found. Create a project "
                "(e.g. via BD happy-path conversion) "
                "before running this E2E."
            )

        # Timesheets: enforce one-active-timer rule
        await timesheet_timer_flow(client, employee_headers, project_id)

        # Payroll lifecycle
        await payroll_flow(client, hr_headers)

        # Projects: milestone create/list (if we have a project)
        if project_id is not None:
            await project_milestone_flow(client, pm_headers, project_id)

        print("✅ E2E full flow OK")


if __name__ == "__main__":
    asyncio.run(main())
