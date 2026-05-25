import asyncio
import os
from datetime import datetime, timezone

import httpx


BASE_URL = os.getenv(
    "ERP_BASE_URL",
    "http://localhost:8000/api/v1",
).rstrip("/")
PASSWORD = os.getenv("ERP_PASSWORD", "test@12345")


def _ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())


async def _login(client: httpx.AsyncClient, email: str) -> str:
    r = await client.post(
        f"{BASE_URL}/auth/login",
        data={"username": email, "password": PASSWORD},
    )
    r.raise_for_status()
    return r.json()["access_token"]


async def _ensure_attendance(client: httpx.AsyncClient, headers: dict) -> None:
    today = await client.get(f"{BASE_URL}/attendance/today", headers=headers)
    if today.status_code == 200 and (today.json() or {}).get("is_marked"):
        return

    r = await client.post(
        f"{BASE_URL}/attendance/mark",
        headers=headers,
        json={"mode": "office", "remarks": "smoke"},
    )
    if r.status_code in (200, 201):
        return
    # Some environments may already have it marked and return 400.
    if r.status_code == 400:
        return
    r.raise_for_status()


async def main() -> None:
    async with httpx.AsyncClient(timeout=60.0) as client:
        admin_token = await _login(client, "admin@gmail.com")
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        await _ensure_attendance(client, admin_headers)

        users = (
            await client.get(
                f"{BASE_URL}/admin/users",
                headers=admin_headers,
            )
        ).json()
        pm = next(u for u in users if u["email"] == "pm@gmail.com")
        bd = next(u for u in users if u["email"] == "bd@gmail.com")
        ceo = next(u for u in users if u["email"] == "ceo@gmail.com")
        admin = next(u for u in users if u["email"] == "admin@gmail.com")

        bd_token = await _login(client, "bd@gmail.com")
        bd_headers = {"Authorization": f"Bearer {bd_token}"}
        await _ensure_attendance(client, bd_headers)

        lead_resp = await client.post(
            f"{BASE_URL}/bd/leads",
            headers=bd_headers,
            json={
                "lead_id": f"LS{_ts()}",
                "owner_user_id": bd["id"],
                "title": "Smoke Lead Bid Task Hours",
                "estimated_value": 123456.0,
                "source": "Direct",
                "industry": "Tech",
                "notes": "seed bid tasks with hours",
            },
        )
        lead_resp.raise_for_status()
        lead_id = lead_resp.json()["id"]

        est_resp = await client.post(
            f"{BASE_URL}/bd/leads/{lead_id}/estimates",
            headers=bd_headers,
            json={
                "name": "Smoke Estimate",
                "currency": "INR",
                "contingency_percent": 10.0,
                "margin_percent": 20.0,
                "phases": [
                    {
                        "phase_name": "Phase 1",
                        "duration_days": 10,
                        "description": "d",
                    }
                ],
                "resource_lines": [
                    {
                        "role_name": "Dev",
                        "quantity": 1,
                        "hours": 10,
                        "rate": 100,
                    }
                ],
            },
        )
        est_resp.raise_for_status()
        version_id = est_resp.json()["id"]

        bt_resp = await client.post(
            f"{BASE_URL}/bd/leads/{lead_id}/bid-tasks",
            headers=bd_headers,
            json={
                "title": "Bid Task: Discovery",
                "description": "Do discovery & plan",
            },
        )
        bt_resp.raise_for_status()
        bid_task_id = bt_resp.json()["id"]

        asg_resp = await client.post(
            f"{BASE_URL}/bd/leads/{lead_id}/bid-tasks/{bid_task_id}/assign",
            headers=bd_headers,
            json={"pm_user_ids": [pm["id"]]},
        )
        asg_resp.raise_for_status()
        assignment_id = asg_resp.json()[0]["id"]

        pm_token = await _login(client, "pm@gmail.com")
        pm_headers = {"Authorization": f"Bearer {pm_token}"}
        await _ensure_attendance(client, pm_headers)

        latest = await client.get(
            (
                f"{BASE_URL}/bd/bid-task-assignments/{assignment_id}/reviews/"
                "latest"
            ),
            headers=pm_headers,
            params={"estimate_version_id": version_id},
        )
        latest.raise_for_status()
        review_id = latest.json()["id"]

        upsert = await client.put(
            f"{BASE_URL}/bd/bid-task-reviews/{review_id}",
            headers=pm_headers,
            json={
                "pm_notes": "Hours estimated",
                "lines": [
                    {
                        "title": "Interview stakeholders",
                        "role": "PM",
                        "description": "",
                        "hours": 6.5,
                        "cost": 0,
                        "sort_order": 0,
                    },
                    {
                        "title": "Draft plan",
                        "role": "PM",
                        "description": "",
                        "hours": 4.0,
                        "cost": 0,
                        "sort_order": 1,
                    },
                ],
            },
        )
        upsert.raise_for_status()

        submit = await client.post(
            f"{BASE_URL}/bd/bid-task-reviews/{review_id}/submit",
            headers=pm_headers,
        )
        submit.raise_for_status()

        patch = await client.patch(
            f"{BASE_URL}/bd/leads/{lead_id}",
            headers=bd_headers,
            json={"stage": "negotiation"},
        )
        if patch.status_code not in (200, 204):
            patch.raise_for_status()

        subm = await client.post(
            f"{BASE_URL}/bd/estimates/{version_id}/submit",
            headers=bd_headers,
            json={"approver_id": ceo["id"]},
        )
        subm.raise_for_status()

        ceo_token = await _login(client, "ceo@gmail.com")
        ceo_headers = {"Authorization": f"Bearer {ceo_token}"}
        await _ensure_attendance(client, ceo_headers)

        inbox_ceo = (
            await client.get(
                f"{BASE_URL}/approvals/inbox",
                headers=ceo_headers,
            )
        ).json()
        appr_ceo = next(
            a
            for a in inbox_ceo
            if str(a.get("resource_id")) == str(version_id)
        )
        r = await client.post(
            f"{BASE_URL}/approvals/{appr_ceo['id']}/action",
            headers=ceo_headers,
            json={
                "status": "approved",
                "comment": "ok",
                "next_approver_id": admin["id"],
            },
        )
        r.raise_for_status()

        inbox_admin = (
            await client.get(
                f"{BASE_URL}/approvals/inbox",
                headers=admin_headers,
            )
        ).json()
        appr_admin = next(
            a
            for a in inbox_admin
            if str(a.get("resource_id")) == str(version_id)
        )
        r = await client.post(
            f"{BASE_URL}/approvals/{appr_admin['id']}/action",
            headers=admin_headers,
            json={"status": "approved", "comment": "final"},
        )
        r.raise_for_status()

        conv = await client.post(
            f"{BASE_URL}/bd/leads/{lead_id}/convert-to-project",
            headers=bd_headers,
            json={
                "project_name": "Smoke Converted Project",
                "project_code": f"SM{_ts()}",
                "project_manager_id": pm["id"],
                "start_date": "2026-01-01",
            },
        )
        if conv.status_code >= 400:
            print("CONVERT_STATUS", conv.status_code)
            print("CONVERT_BODY", conv.text)
            conv.raise_for_status()
        project_payload = conv.json()
        project_id = project_payload.get("project_id") or project_payload.get("id")
        if project_id is None:
            raise RuntimeError(f"Unexpected convert response: {project_payload}")

        my_tasks = await client.get(
            f"{BASE_URL}/tasks/my-tasks",
            headers=pm_headers,
        )
        my_tasks.raise_for_status()
        payload = my_tasks.json()

        # Endpoint contract: List[ProjectWithTasks]
        # Each element has {id, ... , tasks: [TaskRead...]}
        project_obj = None
        if isinstance(payload, list):
            project_obj = next(
                (
                    p
                    for p in payload
                    if str(p.get("id")) == str(project_id)
                ),
                None,
            )

        project_tasks = (project_obj or {}).get("tasks", [])

        print("PROJECT_ID", project_id)
        print("TASK_COUNT", len(project_tasks))
        for t in project_tasks:
            print("TASK", t.get("title"))
            print("DESC", (t.get("description") or "").replace("\n", " "))
            for s in (t.get("subtasks") or []):
                print("  SUB", s.get("title"))


if __name__ == "__main__":
    asyncio.run(main())
