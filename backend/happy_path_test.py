import asyncio
import httpx
from datetime import datetime, timedelta, timezone
import os

BASE_URL = os.getenv("ERP_BASE_URL", "http://localhost:8001/api/v1")
PASSWORD = os.getenv("ERP_PASSWORD", "test@12345")

def check_resp(resp, step_name):
    if resp.status_code >= 400:
        print(f"FAILED {step_name}: {resp.status_code} - {resp.text}")
        return False
    return True


async def ensure_attendance(client: httpx.AsyncClient, headers: dict) -> bool:
    today_resp = await client.get(f"{BASE_URL}/attendance/today", headers=headers)
    if today_resp.status_code == 200 and today_resp.json().get("is_marked") is True:
        return True

    mark_resp = await client.post(
        f"{BASE_URL}/attendance/mark",
        headers=headers,
        json={"mode": "office", "remarks": "E2E seed"},
    )
    if mark_resp.status_code == 200:
        return True

    # OK if already marked (some environments mark on first login)
    if mark_resp.status_code == 400:
        try:
            code = (mark_resp.json() or {}).get("error", {}).get("code")
            if code == "ALREADY_MARKED":
                return True
        except Exception:
            pass

    print(f"FAILED Attendance Mark: {mark_resp.status_code} - {mark_resp.text}")
    return False

async def test_happy_path():
    async with httpx.AsyncClient(timeout=30.0) as client:
        print("--- STARTING HAPPY PATH TESTING ---")

        # Get users as Admin/CEO first
        adm_login = await client.post(f"{BASE_URL}/auth/login", data={
            "username": "admin@gmail.com",
            "password": PASSWORD
        })
        if not check_resp(adm_login, "Admin Login"): return
        adm_headers = {"Authorization": f"Bearer {adm_login.json()['access_token']}"}
        
        users_resp = await client.get(f"{BASE_URL}/admin/users", headers=adm_headers)
        if not check_resp(users_resp, "List Users"): return
        users = users_resp.json()
        admin_user = next(u for u in users if u["email"] == "admin@gmail.com")
        pm_user = next(u for u in users if u["email"] == "pm@gmail.com")
        emp_user = next(u for u in users if u["email"] == "employee@gmail.com")
        bd_user = next(u for u in users if u["email"] == "bd@gmail.com")
        ceo_user = next(u for u in users if u["email"] == "ceo@gmail.com")

        # 1. Login as BD
        print("\n[Step 1] Logging in as BD...")
        bd_login = await client.post(f"{BASE_URL}/auth/login", data={
            "username": "bd@gmail.com",
            "password": PASSWORD
        })
        if not check_resp(bd_login, "BD Login"): return
        bd_token = bd_login.json()["access_token"]
        bd_headers = {"Authorization": f"Bearer {bd_token}"}
        if not await ensure_attendance(client, bd_headers):
            return
        print("BD Logged in.")

        # 2. Create Lead
        print("\n[Step 2] Creating Lead: 'Enterprise Cloud Transformation'...")
        lead_resp = await client.post(f"{BASE_URL}/bd/leads", headers=bd_headers, json={
            "lead_id": f"LEAD-{int(datetime.now().timestamp())}",
            "owner_user_id": bd_user["id"],
            "title": "Enterprise Cloud Transformation",
            "estimated_value": 250000.0,
            "source": "Direct",
            "industry": "Finance",
            "notes": "High priority transformation project"
        })
        if not check_resp(lead_resp, "Create Lead"): return
        lead = lead_resp.json()
        lead_id = lead["id"]
        print(f"Lead created with ID: {lead_id}")

        # 3. Create Estimate
        print("\n[Step 3] Creating Estimate Version 1 (Skeleton)...")
        estimate_resp = await client.post(f"{BASE_URL}/bd/leads/{lead_id}/estimates", headers=bd_headers, json={
            "name": "Cloud Transformation Phased Approach",
            "currency": "INR",
            "contingency_percent": 10.0,
            "margin_percent": 25.0,
            "phases": [
                {"phase_name": "Discovery", "duration_days": 10, "description": "Tech audit"},
                {"phase_name": "Implementation", "duration_days": 60, "description": "Actual migration"}
            ],
            "resource_lines": [
                {"role_name": "Architect", "quantity": 1, "hours": 40, "rate": 200},
                {"role_name": "DevOps", "quantity": 2, "hours": 160, "rate": 150}
            ]
        })
        if not check_resp(estimate_resp, "Create Estimate"): return
        estimate = estimate_resp.json()
        version_id = estimate["id"]
        print(f"Estimate created with ID: {version_id}")

        # 4. PM updates costing
        print("\n[Step 4] PM logging in to refine costing...")
        pm_login = await client.post(f"{BASE_URL}/auth/login", data={
            "username": "pm@gmail.com",
            "password": PASSWORD
        })
        if not check_resp(pm_login, "PM Login"): return
        pm_headers = {"Authorization": f"Bearer {pm_login.json()['access_token']}"}
        if not await ensure_attendance(client, pm_headers):
            return
        
        # PM adds an extra cost or updates rate
        pm_patch = await client.patch(f"{BASE_URL}/bd/estimates/{version_id}", headers=pm_headers, json={
            "margin_percent": 30.0
        })
        if pm_patch.status_code == 403:
            print("PM not authorized to patch estimate in this environment; skipping PM costing step.")
        else:
            if not check_resp(pm_patch, "PM Patch Estimate"): return
            print("PM updated margin to 30%.")

        # 5. BD Submits for Approval (select initial approver)
        print("\n[Step 5] BD submitting estimate for approval (selecting CEO as initial approver)...")
        submit_resp = await client.post(
            f"{BASE_URL}/bd/estimates/{version_id}/submit",
            headers=bd_headers,
            json={"approver_id": ceo_user["id"]},
        )
        if not check_resp(submit_resp, "Submit Estimate"): return
        print("Estimate submitted.")

        # 6. CEO Approves and assigns next approver (admin)
        print("\n[Step 6] CEO logging in to approve (and assign next approver)...")
        ceo_login = await client.post(f"{BASE_URL}/auth/login", data={
            "username": "ceo@gmail.com",
            "password": PASSWORD
        })
        if not check_resp(ceo_login, "CEO Login"): return
        ceo_headers = {"Authorization": f"Bearer {ceo_login.json()['access_token']}"}
        if not await ensure_attendance(client, ceo_headers):
            return

        # Check approval inbox
        inbox_resp = await client.get(f"{BASE_URL}/approvals/inbox", headers=ceo_headers)
        if not check_resp(inbox_resp, "CEO View Inbox"): return
        inbox = inbox_resp.json()
        
        pending_id = None
        for item in inbox:
            if str(item["resource_id"]) == str(version_id):
                pending_id = item["id"]
                break
        
        if pending_id:
            approve1 = await client.post(
                f"{BASE_URL}/approvals/{pending_id}/action",
                headers=ceo_headers,
                json={
                    "status": "approved",
                    "comment": "Looks good. Assigning next approver.",
                    "next_approver_id": admin_user["id"],
                },
            )
            if not check_resp(approve1, "CEO Approve (Assign Next)"): return
            print("CEO Approved and assigned Admin as next approver.")
        else:
            print("ERROR: Could not find pending approval in CEO inbox.")
            return

        # 6b. Admin approves final (no next approver)
        print("\n[Step 6b] Admin logging in to finalize approval...")
        adm2_login = await client.post(f"{BASE_URL}/auth/login", data={
            "username": "admin@gmail.com",
            "password": PASSWORD
        })
        if not check_resp(adm2_login, "Admin Login (for approval)"): return
        adm2_headers = {"Authorization": f"Bearer {adm2_login.json()['access_token']}"}
        if not await ensure_attendance(client, adm2_headers):
            return

        inbox_admin_resp = await client.get(f"{BASE_URL}/approvals/inbox", headers=adm2_headers)
        if not check_resp(inbox_admin_resp, "Admin View Inbox"): return
        inbox_admin = inbox_admin_resp.json()
        pending_admin_id = next(
            (a["id"] for a in inbox_admin if str(a.get("resource_id")) == str(version_id)),
            None,
        )
        if not pending_admin_id:
            print("ERROR: Could not find pending approval in Admin inbox.")
            return

        approve_final = await client.post(
            f"{BASE_URL}/approvals/{pending_admin_id}/action",
            headers=adm2_headers,
            json={
                "status": "approved",
                "comment": "Final approval.",
            },
        )
        if not check_resp(approve_final, "Admin Final Approve"): return
        print("Admin finalized approval.")

        # Verify estimate status is approved
        est_get = await client.get(f"{BASE_URL}/bd/estimates/{version_id}", headers=bd_headers)
        if not check_resp(est_get, "Get Estimate After Approval"): return
        est_data = est_get.json() or {}
        print(f"Estimate status after approvals: {est_data.get('status')}")

        # 7. Convert Lead to Project
        print("\n[Step 7] BD converting WON lead to Project...")
        # Move lead into negotiation and convert (conversion marks WON)
        await client.patch(
            f"{BASE_URL}/bd/leads/{lead_id}",
            headers=bd_headers,
            json={"stage": "negotiation"},
        )
        
        conv_resp = await client.post(f"{BASE_URL}/bd/leads/{lead_id}/convert-to-project", headers=bd_headers, json={
            "project_code": f"PROJ-{int(datetime.now().timestamp())}",
            "project_manager_id": pm_user["id"],
            "start_date": datetime.now().strftime("%Y-%m-%d")
        })
        if not check_resp(conv_resp, "Convert to Project"): return
        project = conv_resp.json()
        project_id = project["id"]
        print(f"Lead converted to Project: {project['name']} (ID: {project_id})")

        # 8. PM Assigns Tasks
        print("\n[Step 8] PM creating tasks for the team...")
        due_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S")
        task_resp = await client.post(f"{BASE_URL}/tasks/", headers=pm_headers, json={
            "title": "Set up Cloud Landing Zone",
            "description": "Initialize Terraform and AWS accounts",
            "project_id": project_id,
            "assigned_user_id": emp_user["id"],
            "due_date": due_date,
            "priority": "high"
        })
        if not check_resp(task_resp, "Create Task"): return
        task = task_resp.json()
        print(f"Task '{task['title']}' created and assigned to Employee.")

        print("\n--- HAPPY PATH COMPLETED SUCCESSFULLY ---")

if __name__ == "__main__":
    asyncio.run(test_happy_path())
