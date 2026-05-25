import asyncio
from app.db.session import SessionLocal, engine
from app.models.leave import LeaveType
from sqlalchemy import select

LEAVE_TYPES = [
    {
        "name": "Casual Leave",
        "code": "CL",
        "description": "Casual leave for personal/urgent matters. Non-cumulative, max 2 consecutive days.",
        "unpaid_allowed": False,
        "annual_quota": 10,
        "max_carry_forward": 0,
        "max_accumulation": 10,
        "max_consecutive_days": 2,
        "allow_half_day": True,
        "is_cumulative": False,
    },
    {
        "name": "Privilege Leave",
        "code": "PL",
        "description": "Privilege/earned leave. Accumulates up to 36 days, carries forward. 5 days must be pre-planned.",
        "unpaid_allowed": False,
        "annual_quota": 14,
        "max_carry_forward": 36,
        "max_accumulation": 36,
        "max_consecutive_days": None,
        "allow_half_day": False,
        "is_cumulative": True,
    },
    {
        "name": "Sick Leave",
        "code": "SL",
        "description": "Sick leave for medical reasons. Carries forward max 7 days. Medical certificate required for 2+ consecutive days.",
        "unpaid_allowed": False,
        "annual_quota": 7,
        "max_carry_forward": 7,
        "max_accumulation": 14,
        "max_consecutive_days": None,
        "allow_half_day": True,
        "requires_medical_cert_after": 2,
        "is_cumulative": True,
    },
    {
        "name": "Compensatory Off",
        "code": "CO",
        "description": "Comp-off for working on holidays/weekends. Must be used within 2 months, max 2/month and 24/year.",
        "unpaid_allowed": False,
        "annual_quota": 0,
        "max_carry_forward": 0,
        "max_accumulation": 24,
        "allow_half_day": False,
        "is_cumulative": False,
        "use_within_days": 60,
        "max_per_month": 2,
        "max_per_year": 24,
    },
    {
        "name": "Maternity Leave",
        "code": "ML",
        "description": "Maternity leave as per Maternity Benefit Act 1961. 26 weeks for up to 2 children, 12 weeks for 3+.",
        "unpaid_allowed": False,
        "annual_quota": 0,
        "max_carry_forward": 0,
        "allow_half_day": False,
        "is_cumulative": False,
    },
    {
        "name": "Leave Without Pay",
        "code": "LWP",
        "description": "Unpaid leave when all other leave balances are exhausted.",
        "unpaid_allowed": True,
        "annual_quota": 0,
        "max_carry_forward": 0,
        "allow_half_day": False,
        "is_cumulative": False,
    },
]


async def seed():
    try:
        async with SessionLocal() as session:
            print("Seeding leave types per Time Office Policy v2.0...")

            # Step 1: Remove legacy types that will be replaced
            # by new policy types (to avoid name/code conflicts)
            legacy_delete = {
                "Annual Leave",   # replaced by Privilege Leave (PL)
                "Loss of Pay",    # replaced by Leave Without Pay (LWP)
            }
            new_names = {lt["name"] for lt in LEAVE_TYPES}

            old_res = await session.execute(
                select(LeaveType).filter(
                    LeaveType.code.is_(None)
                )
            )
            for old_lt in old_res.scalars().all():
                if old_lt.name in legacy_delete:
                    print(f"  Removing legacy: {old_lt.name}")
                    await session.delete(old_lt)
                elif old_lt.name not in new_names:
                    print(
                        f"  Note: Legacy '{old_lt.name}' — "
                        f"consider removing manually"
                    )
            await session.flush()

            # Step 2: Upsert policy leave types
            for lt_data in LEAVE_TYPES:
                code = lt_data["code"]
                name = lt_data["name"]

                # Find by code first, then by name
                res = await session.execute(
                    select(LeaveType).filter(
                        LeaveType.code == code
                    )
                )
                existing = res.scalars().first()

                if not existing:
                    res2 = await session.execute(
                        select(LeaveType).filter(
                            LeaveType.name == name
                        )
                    )
                    existing = res2.scalars().first()

                if existing:
                    for key, value in lt_data.items():
                        setattr(existing, key, value)
                    print(f"  Updated: {name} ({code})")
                else:
                    lt = LeaveType(**lt_data)
                    session.add(lt)
                    print(f"  Added: {name} ({code})")

            await session.commit()
            print("Done.")
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(seed())
