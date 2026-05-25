import pytest
from httpx import AsyncClient
from app.core.config import settings


@pytest.mark.asyncio
async def test_create_milestone(
    client: AsyncClient, admin_token_headers: dict
):
    projects = await client.get(
        f"{settings.API_V1_STR}/admin/projects",
        headers=admin_token_headers,
    )
    assert projects.status_code == 200
    items = projects.json() or []
    if not items:
        pytest.skip("No projects available to test milestones")

    project_id = int(items[-1]["id"])

    # Create milestone
    milestone_data = {
        "title": "Phase 1",
        "description": "Initial Setup",
        "due_date": "2026-02-15T00:00:00Z",
        "status": "pending"
    }
    response = await client.post(
        f"{settings.API_V1_STR}/projects/{project_id}/milestones",
        json=milestone_data,
        headers=admin_token_headers
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Phase 1"


@pytest.mark.asyncio
async def test_cost_change_threshold(
    client: AsyncClient, admin_token_headers: dict
):
    projects = await client.get(
        f"{settings.API_V1_STR}/admin/projects",
        headers=admin_token_headers,
    )
    assert projects.status_code == 200
    items = projects.json() or []
    if not items:
        pytest.skip("No projects available to test cost changes")

    project_id = int(items[-1]["id"])

    # 2. Set baseline
    response = await client.post(
        f"{settings.API_V1_STR}/projects/{project_id}/cost-baseline",
        json={"amount": 1000, "description": "Initial"},
        headers=admin_token_headers
    )
    assert response.status_code == 200

    # 3. Request change (15% increase > 10% threshold)
    change_data = {
        "proposed_amount": 1150,
        "reason": "Scope creep",
        "impact": "None"
    }
    response = await client.post(
        f"{settings.API_V1_STR}/projects/{project_id}/cost-change",
        json=change_data,
        headers=admin_token_headers
    )
    assert response.status_code == 200
    request_id = response.json()["id"]

    # 4. Check inbox
    response = await client.get(
        f"{settings.API_V1_STR}/projects/cost-approvals/inbox",
        headers=admin_token_headers
    )
    assert response.status_code == 200
    # Should be in inbox because admin has all permissions
    assert any(r["id"] == request_id for r in response.json())
