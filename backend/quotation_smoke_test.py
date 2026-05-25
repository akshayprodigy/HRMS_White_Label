"""Quotation PDF generation smoke test.

Goal: Validate BD estimate quotation PDF generation + versioning + download.

This script WILL create (or reuse) a deterministic "SMOKE" lead and
(at most) one estimate version for that lead, then generate a new
quotation PDF version and download it.

Run inside backend container (recommended):
  ERP_BASE_URL=http://backend:8000/api/v1 \
  ERP_USERNAME=bd@gmail.com \
  ERP_PASSWORD=test@12345 \
  python quotation_smoke_test.py

Notes:
- BD routes are attendance-gated; this script may mark attendance
  for the smoke-test user if not already marked.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from typing import NoReturn

import httpx


BASE_URL = os.getenv(
    "ERP_BASE_URL",
    "http://localhost:8000/api/v1",
).rstrip("/")
USERNAME = os.getenv("ERP_USERNAME")
PASSWORD = os.getenv("ERP_PASSWORD")


def fail(msg: str) -> NoReturn:
    print(f"FAIL: {msg}")
    sys.exit(1)


def ok(msg: str) -> None:
    print(f"OK: {msg}")


def assert_ok(
    resp: httpx.Response,
    *,
    name: str,
    allow: tuple[int, ...] = (200,),
) -> None:
    if resp.status_code not in allow:
        fail(f"{name} {resp.status_code}: {resp.text}")


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
        json={"mode": "remote", "remarks": "quotation smoke test"},
    )
    if mark.status_code != 200:
        fail(f"attendance/mark {mark.status_code}: {mark.text}")
    ok("attendance/mark (was not marked)")


def _today_tag() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _smoke_lead_id() -> str:
    # Deterministic per day to avoid unbounded lead creation.
    # Keep reasonably short and URL-safe.
    return f"SMOKE-QUOTE-{_today_tag().replace('-', '')}"


def _smoke_lead_title() -> str:
    return f"SMOKE Quotation {_today_tag()}"


async def _find_lead_by_lead_id(
    client: httpx.AsyncClient, *, headers: dict, lead_id: str
) -> dict | None:
    for page in range(0, 5):
        resp = await client.get(
            f"{BASE_URL}/bd/leads",
            headers=headers,
            params={"skip": page * 200, "limit": 200},
        )
        assert_ok(resp, name="bd/leads list")
        leads = resp.json() or []
        for lead in leads:
            if (lead or {}).get("lead_id") == lead_id:
                return lead
        if len(leads) < 200:
            return None
    return None


async def get_or_create_lead(
    client: httpx.AsyncClient, *, headers: dict
) -> dict:
    lead_id = _smoke_lead_id()
    payload = {
        "lead_id": lead_id,
        "title": _smoke_lead_title(),
        "account_name": "SMOKE Account",
        "estimated_value": 12345.0,
        "probability_percent": 10,
    }

    created = await client.post(
        f"{BASE_URL}/bd/leads",
        headers=headers,
        json=payload,
    )
    if created.status_code in (200, 201):
        lead = created.json() or {}
        lead_db_id = lead.get("id")
        if not isinstance(lead_db_id, int):
            fail(f"bd/leads create did not return id: {lead}")
        ok(
            "lead created "
            f"(id={lead_db_id}, lead_id={lead.get('lead_id')})"
        )
        return lead

    # If already exists, fetch from list.
    if created.status_code == 400:
        text = (created.text or "").lower()
        if "already exists" in text:
            target = lead_id
            found = await _find_lead_by_lead_id(
                client,
                headers=headers,
                lead_id=target,
            )
            if found:
                ok(
                    "lead reused "
                    f"(id={found.get('id')}, lead_id={target})"
                )
                return found
            fail(
                f"lead_id {target} already exists "
                "but was not found in list"
            )

    fail(f"bd/leads create {created.status_code}: {created.text}")


async def get_or_create_estimate_version(
    client: httpx.AsyncClient, *, headers: dict, lead_db_id: int
) -> dict:
    # If an estimate exists, reuse the latest. Otherwise create one.
    existing = await client.get(
        f"{BASE_URL}/bd/leads/{lead_db_id}/estimates",
        headers=headers,
    )
    assert_ok(existing, name="bd lead estimates list")
    versions = existing.json() or []
    if versions:
        v0 = versions[0]
        ok(
            "estimate version reused "
            f"(id={v0.get('id')}, v={v0.get('version_number')})"
        )
        return v0

    estimate_payload = {
        "name": f"SMOKE Estimate {_today_tag()}",
        "currency": "INR",
        "contingency_percent": 5.0,
        "margin_percent": 10.0,
        "scope_included": "Smoke scope included",
        "scope_excluded": "Smoke scope excluded",
        "assumptions": "Smoke assumptions",
        "phases": [
            {
                "phase_name": "Discovery",
                "start_offset_days": 0,
                "duration_days": 3,
                "description": "Smoke phase",
            }
        ],
        "resource_lines": [
            {
                "role_name": "Engineer",
                "quantity": 1.0,
                "hours": 10.0,
                "rate": 10.0,
                "cost_decimal": 100.0,
            }
        ],
    }
    created = await client.post(
        f"{BASE_URL}/bd/leads/{lead_db_id}/estimates",
        headers=headers,
        json=estimate_payload,
    )
    assert_ok(created, name="bd estimate create", allow=(200, 201))
    v = created.json() or {}
    if not isinstance(v.get("id"), int):
        fail(f"estimate create did not return id: {v}")
    ok(
        "estimate version created "
        f"(id={v.get('id')}, v={v.get('version_number')})"
    )
    return v


async def main() -> None:
    if not USERNAME or not PASSWORD:
        fail("ERP_USERNAME and ERP_PASSWORD must be set")

    assert USERNAME is not None
    assert PASSWORD is not None
    username: str = USERNAME
    password: str = PASSWORD

    timeout = httpx.Timeout(40.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        headers = await login_and_get_headers(
            client,
            username=username,
            password=password,
        )
        ok("login")

        await ensure_attendance_marked(client, headers=headers)

        lead = await get_or_create_lead(client, headers=headers)
        lead_db_id_any = lead.get("id")
        if not isinstance(lead_db_id_any, int):
            fail(f"lead missing id: {lead}")
        lead_db_id: int = lead_db_id_any

        version = await get_or_create_estimate_version(
            client,
            headers=headers,
            lead_db_id=lead_db_id,
        )
        version_id_any = version.get("id")
        if not isinstance(version_id_any, int):
            fail(f"estimate version missing id: {version}")
        version_id: int = version_id_any

        # Generate a new quotation version.
        gen = await client.post(
            f"{BASE_URL}/bd/estimates/{version_id}/quotations",
            headers=headers,
        )
        assert_ok(gen, name="bd quotation generate", allow=(200, 201))
        q = gen.json() or {}
        quotation_id = q.get("id")
        if not isinstance(quotation_id, int):
            fail(f"quotation generate did not return id: {q}")
        ok(
            "quotation generated "
            f"(id={quotation_id}, qv={q.get('version_number')})"
        )

        # List quotation versions for this estimate.
        qlist = await client.get(
            f"{BASE_URL}/bd/estimates/{version_id}/quotations",
            headers=headers,
        )
        assert_ok(qlist, name="bd quotation list")
        items = qlist.json() or []
        if not any((it or {}).get("id") == quotation_id for it in items):
            fail("quotation list did not include the generated quotation id")
        ok(f"quotation listed (count={len(items)})")

        # Download the PDF and validate basic invariants.
        pdf = await client.get(
            f"{BASE_URL}/bd/quotations/{quotation_id}/pdf",
            headers=headers,
        )
        assert_ok(pdf, name="bd quotation pdf download")

        content_type = (pdf.headers.get("content-type") or "").lower()
        if "application/pdf" not in content_type:
            fail(f"unexpected content-type: {content_type}")

        content_disp = pdf.headers.get("content-disposition") or ""
        if "filename=" not in content_disp.lower():
            fail(f"missing filename in content-disposition: {content_disp}")

        body = pdf.content or b""
        if not body.startswith(b"%PDF"):
            head = body[:16]
            fail(f"response body does not look like a PDF (head={head!r})")

        ok(f"pdf downloaded ({len(body)} bytes)")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
