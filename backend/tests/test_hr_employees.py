import pytest
from httpx import AsyncClient, ASGITransport
from app.main import create_app
from app.core.config import settings
from app.api.deps import get_current_user, get_db
from app.models.user import User, Role, Permission
from app.models.employee import Employee
from unittest.mock import MagicMock, AsyncMock

# Mock data
mock_role_hr = Role(id=1, name="HR")
mock_role_hr.permissions = [
    Permission(name="hr employee read"),
    Permission(name="hr payroll view")
]

mock_role_staff = Role(id=2, name="Staff")
mock_role_staff.permissions = [
    Permission(name="hr employee read")
]

mock_user_hr = User(
    id=1,
    email="hr@test.com",
    full_name="HR User",
    is_active=True,
    roles=[mock_role_hr]
)

mock_user_staff = User(
    id=2,
    email="staff@test.com",
    full_name="Staff User",
    is_active=True,
    roles=[mock_role_staff]
)

mock_employee = Employee(
    id=1,
    user_id=10,
    employee_id="EMP001",
    department="HR",
    designation="Manager",
    status="active",
    salary=50000.0,
    bank_account="1234567890",
    pan_number="ABCDE1234F",
    date_of_joining="2024-01-01"
)
# Mock the relationship
mock_employee.user = User(
    id=10,
    full_name="John Doe",
    email="john@test.com",
    is_superuser=False,
    is_active=True
)


@pytest.fixture
def app():
    return create_app()


@pytest.mark.asyncio
async def test_hr_employee_list_redaction(app):
    # Setup dependency override for a staff user (no payroll view)
    def override_get_current_user():
        return mock_user_staff

    async def override_get_db():
        db = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = [mock_employee]
        result.scalar_one_or_none.return_value = 1  # For count
        
        db.execute.return_value = result
        return db

    app.dependency_overrides[get_current_user] = (
        override_get_current_user
    )
    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get(f"{settings.API_V1_STR}/hr/employees")

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        # Check that salary is NOT present
        assert "salary" not in data["items"][0]
        assert "bank_account" not in data["items"][0]
        assert data["items"][0]["employee_id"] == "EMP001"

    app.dependency_overrides = {}


@pytest.mark.asyncio
async def test_hr_employee_list_full_access(app):
    # Setup dependency override for an HR user (with payroll view)
    def override_get_current_user():
        return mock_user_hr

    async def override_get_db():
        db = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = [mock_employee]
        result.scalar_one_or_none.return_value = 1  # For count

        db.execute.return_value = result
        return db

    app.dependency_overrides[get_current_user] = (
        override_get_current_user
    )
    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get(f"{settings.API_V1_STR}/hr/employees")

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        # Check that salary IS present
        assert "salary" in data["items"][0]
        assert abs(data["items"][0]["salary"] - 50000.0) < 0.001
        assert data["items"][0]["bank_account"] == "1234567890"

    app.dependency_overrides = {}


@pytest.mark.asyncio
async def test_hr_employee_unauthorized(app):
    # Setup dependency override for a user with NO hr permissions
    mock_user_no_perm = User(
        id=3, email="none@test.com", is_active=True, roles=[]
    )

    def override_get_current_user():
        return mock_user_no_perm

    app.dependency_overrides[get_current_user] = (
        override_get_current_user
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get(f"{settings.API_V1_STR}/hr/employees")
        # Should return 403 Forbidden
        assert response.status_code == 403

    app.dependency_overrides = {}
