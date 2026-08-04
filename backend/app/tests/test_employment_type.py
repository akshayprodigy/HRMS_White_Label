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
