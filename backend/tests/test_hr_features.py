import pytest
from httpx import AsyncClient, ASGITransport
from app.main import create_app
from app.core.config import settings
from app.models.attendance import (
    AttendanceCorrectionRequest, Attendance
)
from app.models.audit import AuditLog
from sqlalchemy import select
from app.api.deps import get_db


@pytest.fixture
def app():
    return create_app()


@pytest.mark.asyncio
async def test_approve_attendance_correction_creates_audit(app):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # 1. Login as admin (using seed credentials)
        login_resp = await client.post(
            f"{settings.API_V1_STR}/auth/login",
            data={
                "username": "admin@example.com",
                "password": "admin123"
            }
        )
        if login_resp.status_code != 200:
            pytest.skip("Admin user not found for testing")
            
        token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Create a correction request
        resp = await client.post(
            f"{settings.API_V1_STR}/hr/attendance-corrections",
            json={
                "date": "2026-02-13",
                "requested_mode": "Office",
                "reason": "Forgot to punch in",
                "requested_remarks": "At desk since 9 AM"
            },
            headers=headers
        )
        assert resp.status_code == 200
        corr_id = resp.json()["id"]

        # 3. Approve the request
        path = (
            f"/api/v1/hr/attendance-corrections/{corr_id}/action"
        )
        resp = await client.post(
            path,
            json={"status": "approved"},
            headers=headers
        )
        assert resp.status_code == 200

        # Now verify audit log and attendance
        # We need to get a DB session to check the state
        async for db in get_db():
            # 4. Verify audit log
            result = await db.execute(
                select(AuditLog).where(
                    AuditLog.action == "APPROVE_ATTENDANCE_CORRECTION",
                    AuditLog.resource_id == str(corr_id)
                )
            )
            audit = result.scalar_one_or_none()
            assert audit is not None
            assert audit.resource_type == "attendance_correction"

            # 5. Verify attendance record was created/updated
            corr_result = await db.get(AttendanceCorrectionRequest, corr_id)
            assert corr_result.attendance_id is not None

            att_id = corr_result.attendance_id
            attendance_record = await db.get(Attendance, att_id)
            assert attendance_record is not None
            assert attendance_record.mode == "Office"
            break
