import pytest
from app.services import employment_type as et_svc


@pytest.mark.asyncio
async def test_seeded_types_drive_statutory(db):
    assert await et_svc.is_statutory_employee(db, "permanent") is True
    assert await et_svc.is_statutory_employee(db, "contractual") is False
    assert await et_svc.is_statutory_employee(db, "advisor") is False


@pytest.mark.asyncio
async def test_flat_tds_rate_from_master(db):
    assert await et_svc.flat_tds_rate_for(db, "contractual") == 0.10
    assert await et_svc.flat_tds_rate_for(db, "advisor") == 0.10
    # permanent has no flat rate -> default
    assert await et_svc.flat_tds_rate_for(db, "permanent") == 0.10


@pytest.mark.asyncio
async def test_legacy_fallback_for_unknown_code(db):
    # Unknown/None code must reproduce the old string-based behaviour.
    assert await et_svc.is_statutory_employee(db, "some_new_code") is True
    assert await et_svc.is_statutory_employee(db, None) is True
    assert await et_svc.is_statutory_employee(db, "contractual") is False
    assert await et_svc.flat_tds_rate_for(db, "unknown") == 0.10


@pytest.mark.asyncio
async def test_validate_employment_type_rejects_unknown_and_inactive(db):
    from fastapi import HTTPException
    from app.api.v1.endpoints.hr import _validate_employment_type
    from app.models.employment_type import EmploymentType

    # valid active seeded code and None -> no raise
    await _validate_employment_type(db, "permanent")
    await _validate_employment_type(db, None)

    # unknown code -> 400
    with pytest.raises(HTTPException) as ei:
        await _validate_employment_type(db, "nope_not_real")
    assert ei.value.status_code == 400

    # inactive code -> 400
    db.add(EmploymentType(code="temp_inactive", name="Temp", is_active=False))
    await db.flush()
    with pytest.raises(HTTPException) as ei2:
        await _validate_employment_type(db, "temp_inactive")
    assert ei2.value.status_code == 400
