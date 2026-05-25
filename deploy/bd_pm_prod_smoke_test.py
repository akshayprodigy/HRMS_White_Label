"""Targeted production smoke test for BD ↔ PM flow.

This script intentionally creates ONE lead + ONE estimate version assigned to a
PM, then verifies the PM can see/access that lead+estimate (RLS via assigned
phases).
Finally it marks the lead LOST and archives the estimate to keep prod tidy.

Run it inside the backend container (recommended) so it can hit:
  http://127.0.0.1:8000/api/v1

Env overrides:
  ERP_BASE_URL   (default: http://127.0.0.1:8000/api/v1)
  ERP_BD_USER / ERP_BD_PASS
  ERP_PM_USER / ERP_PM_PASS

Defaults assume demo creds; override on real prod if different.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request


BASE = os.environ.get(
    "ERP_BASE_URL", "http://127.0.0.1:8000/api/v1"
).rstrip("/")
BD_USER = os.environ.get("ERP_BD_USER", "bd@gmail.com")
BD_PASS = os.environ.get("ERP_BD_PASS", "test@12345")
PM_USER = os.environ.get("ERP_PM_USER", "pm@gmail.com")
PM_PASS = os.environ.get("ERP_PM_PASS", "test@12345")


def req(
    method: str,
    path: str,
    token: str | None = None,
    *,
    data: dict | None = None,
    json_body: dict | None = None,
):
    url = f"{BASE}{path}"
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    body = None
    if json_body is not None:
        body = json.dumps(json_body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    elif data is not None:
        body = urllib.parse.urlencode(data).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"

    request = urllib.request.Request(
        url, data=body, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
            ctype = resp.headers.get("Content-Type", "")
            if "application/json" in ctype and raw:
                return resp.status, json.loads(raw)
            return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw


def must_ok(name: str, status: int, payload):
    if status >= 400:
        raise RuntimeError(f"{name} failed: {status} {payload}")


def login(username: str, password: str) -> str:
    status, payload = req(
        "POST",
        "/auth/login",
        data={"username": username, "password": password},
    )
    must_ok(f"login {username}", status, payload)
    token = (payload or {}).get("access_token")
    if not token:
        raise RuntimeError(
            f"login missing access_token for {username}: {payload}"
        )
    return token


def ensure_attendance(token: str, label: str) -> None:
    status, payload = req("GET", "/attendance/today", token)
    must_ok(f"attendance/today {label}", status, payload)

    if (payload or {}).get("is_marked"):
        print(f"OK: attendance already marked ({label})")
        return

    status, payload = req(
        "POST",
        "/attendance/mark",
        token,
        json_body={"mode": "office", "remarks": f"prod smoke test ({label})"},
    )
    must_ok(f"attendance/mark {label}", status, payload)
    print(f"OK: attendance marked ({label})")


def main() -> None:
    print("Smoke test starting...")

    # BD session
    bd_token = login(BD_USER, BD_PASS)
    print("OK: login bd")
    ensure_attendance(bd_token, "bd")

    status, pms = req("GET", "/bd/users/project-managers", bd_token)
    must_ok("GET /bd/users/project-managers (bd)", status, pms)
    if not isinstance(pms, list) or not pms:
        raise RuntimeError(f"No PMs returned: {pms}")

    pm_id = (pms[0] or {}).get("id")
    if not isinstance(pm_id, int):
        raise RuntimeError(f"PM id missing/invalid: {pms[0]}")
    print(f"OK: BD can list PMs (pm_id={pm_id})")

    lead_title = (
        "PROD SMOKE BD-PM RLS "
        f"{time.strftime('%Y%m%d-%H%M%S', time.gmtime())}"
    )
    status, lead = req(
        "POST",
        "/bd/leads",
        bd_token,
        json_body={
            "title": lead_title,
            "account_name": "PROD SMOKE ACCOUNT",
            "estimated_value": 1234.0,
            "expected_close_date": time.strftime("%Y-%m-%d", time.gmtime()),
            "source": "smoke_test",
            "notes": (
                "Created by automated production smoke test. Safe to ignore."
            ),
        },
    )
    must_ok("POST /bd/leads", status, lead)

    lead_id = (lead or {}).get("id")
    if not isinstance(lead_id, int):
        raise RuntimeError(f"Lead create missing id: {lead}")
    created_lead_id = (lead or {}).get("lead_id")
    print(f"OK: BD created lead id={lead_id} lead_id={created_lead_id}")

    status, est = req(
        "POST",
        f"/bd/leads/{lead_id}/estimates",
        bd_token,
        json_body={
            "name": "Smoke Estimate v1",
            "assumptions": "Smoke test estimate",
            "currency": "INR",
            "contingency_percent": 0.0,
            "margin_percent": 10.0,
            "phases": [
                {
                    "phase_name": "Phase 1",
                    "duration_days": 5,
                    "start_offset_days": 0,
                    "description": "Smoke phase",
                    "assigned_user_id": pm_id,
                }
            ],
            "resource_lines": [
                {
                    "role_name": "Engineer",
                    "quantity": 1,
                    "hours": 10,
                    "rate": 50,
                    "cost_decimal": 500,
                }
            ],
        },
    )
    must_ok("POST /bd/leads/{id}/estimates", status, est)

    version_id = (est or {}).get("id")
    if not isinstance(version_id, int):
        raise RuntimeError(f"Estimate create missing id: {est}")
    print(f"OK: BD created estimate version_id={version_id}")

    # PM session
    pm_token = login(PM_USER, PM_PASS)
    print("OK: login pm")
    ensure_attendance(pm_token, "pm")

    status, pm_leads = req("GET", "/bd/leads", pm_token)
    must_ok("GET /bd/leads (pm)", status, pm_leads)
    if not any(
        isinstance(item, dict) and item.get("id") == lead_id
        for item in (pm_leads or [])
    ):
        raise RuntimeError(
            "PM cannot see the newly assigned lead in /bd/leads"
        )
    print("OK: PM can see assigned lead in /bd/leads")

    status, payload = req("GET", f"/bd/leads/{lead_id}", pm_token)
    must_ok("GET /bd/leads/{id} (pm)", status, payload)
    print("OK: PM can open lead detail")

    status, payload = req("GET", f"/bd/leads/{lead_id}/estimates", pm_token)
    must_ok("GET /bd/leads/{id}/estimates (pm)", status, payload)
    print("OK: PM can list lead estimates")

    status, payload = req("GET", f"/bd/estimates/{version_id}", pm_token)
    must_ok("GET /bd/estimates/{version_id} (pm)", status, payload)
    print("OK: PM can open estimate detail")

    # Cleanup-ish: keep prod tidy
    status, payload = req(
        "PATCH",
        f"/bd/leads/{lead_id}",
        bd_token,
        json_body={
            "stage": "lost",
            "notes": "PROD SMOKE TEST (auto) - marked lost",
        },
    )
    must_ok("PATCH /bd/leads/{id} stage=lost", status, payload)

    status, payload = req(
        "POST", f"/bd/estimates/{version_id}/archive", bd_token
    )
    must_ok("POST /bd/estimates/{id}/archive", status, payload)

    print("OK: cleanup applied (lead marked lost, estimate archived)")
    print("SMOKE TEST PASSED")


if __name__ == "__main__":
    main()
