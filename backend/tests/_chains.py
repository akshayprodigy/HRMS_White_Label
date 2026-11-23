"""Test isolation for the two request types that route through approval
chains (work_location, optional_holiday): park every pre-existing active
chain so the dev DB's real chains (or leftovers of a crashed run) can neither
pick up a test request nor win chain selection over the test's own chain."""
from sqlalchemy import select, update

from app.db.session import SessionLocal
from app.models.approval_chain import ApprovalChain

TYPES = ("work_location", "optional_holiday")
LEFTOVER_PREFIXES = ("WlChain ", "WlNoAuto ", "OhChain ", "OhNoAuto ")


async def deactivate_active_chains() -> list:
    """Deactivate active chains of TYPES; return ids to restore. Chains left
    by earlier crashed test runs (test-named) are deactivated but never
    restored."""
    async with SessionLocal() as db:
        rows = (await db.execute(select(ApprovalChain.id, ApprovalChain.name)
                                 .where(ApprovalChain.entity_type.in_(TYPES),
                                        ApprovalChain.is_active.is_(True))
                                 )).all()
        if rows:
            await db.execute(update(ApprovalChain).where(
                ApprovalChain.id.in_([r[0] for r in rows]))
                .values(is_active=False))
            await db.commit()
    return [i for i, n in rows if not (n or "").startswith(LEFTOVER_PREFIXES)]


async def restore_chains(ids) -> None:
    if not ids:
        return
    async with SessionLocal() as db:
        await db.execute(update(ApprovalChain).where(
            ApprovalChain.id.in_(list(ids))).values(is_active=True))
        await db.commit()
