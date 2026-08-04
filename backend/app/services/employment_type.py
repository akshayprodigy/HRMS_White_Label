"""Employment-type resolution (F2).

The employment_type master is keyed by `code`, which matches the free-string
`Employee.employment_type`. These helpers let payroll read the per-type
payroll profile with a legacy fallback so unseeded/unknown codes reproduce
the historical string-based behaviour.
"""
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employment_type import EmploymentType

# Legacy codes that historically skipped statutory deductions.
_LEGACY_NON_STATUTORY = ("contractual", "advisor")
DEFAULT_FLAT_TDS_RATE = 0.10


async def get_employment_type(db: AsyncSession, code: Optional[str]) -> Optional[EmploymentType]:
    if not code:
        return None
    return (
        await db.execute(select(EmploymentType).where(EmploymentType.code == code))
    ).scalars().first()


def _is_statutory(code: Optional[str], et: Optional[EmploymentType]) -> bool:
    if et is None:
        return (code or "permanent") not in _LEGACY_NON_STATUTORY
    return et.statutory_enabled


def _flat_tds_rate(et: Optional[EmploymentType]) -> float:
    if et is not None and et.flat_tds_rate is not None:
        return et.flat_tds_rate
    return DEFAULT_FLAT_TDS_RATE


async def load_map(db: AsyncSession) -> dict:
    """Prefetch all employment types into a {code: row} dict — for batch
    loops (e.g. payroll draft) that would otherwise do N+1 lookups."""
    rows = (await db.execute(select(EmploymentType))).scalars().all()
    return {r.code: r for r in rows}


def is_statutory_for(code: Optional[str], et_map: dict) -> bool:
    """Map-based variant of is_statutory_employee (no DB call)."""
    return _is_statutory(code, et_map.get(code) if code else None)


def flat_tds_for(code: Optional[str], et_map: dict) -> float:
    """Map-based variant of flat_tds_rate_for (no DB call)."""
    return _flat_tds_rate(et_map.get(code) if code else None)


async def is_statutory_employee(db: AsyncSession, code: Optional[str]) -> bool:
    """True if PF/ESI/PT/regular-TDS apply. Falls back to the legacy string
    rule when no master row exists for `code`."""
    return _is_statutory(code, await get_employment_type(db, code))


async def flat_tds_rate_for(db: AsyncSession, code: Optional[str]) -> float:
    """Flat TDS rate for a non-statutory type; default 0.10 when unset."""
    return _flat_tds_rate(await get_employment_type(db, code))
