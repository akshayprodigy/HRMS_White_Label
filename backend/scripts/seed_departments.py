import asyncio
from app.db.session import SessionLocal, engine
from app.models.department import Department
from sqlalchemy import select


DEPARTMENTS = [
    {"name": "Engineering", "description": "Software engineering and development"},
    {"name": "Human Resources", "description": "People operations, hiring, policy"},
    {"name": "Product", "description": "Product management and design"},
    {"name": "Operations", "description": "Business operations and delivery"},
    {"name": "Information Technology", "description": "IT infrastructure, devices, access"},
    {"name": "Administration", "description": "Office administration, identity, facilities"},
    {"name": "Accounts", "description": "Finance, accounts, settlements"},
    {"name": "Sales", "description": "Sales and business development"},
]


async def seed():
    try:
        async with SessionLocal() as session:
            print("Seeding departments referenced by existing employee/clearance data...")

            for dept_data in DEPARTMENTS:
                name = dept_data["name"]
                res = await session.execute(
                    select(Department).filter(Department.name == name)
                )
                existing = res.scalars().first()

                if existing:
                    if not existing.is_active:
                        existing.is_active = True
                        print(f"  Reactivated: {name}")
                    else:
                        print(f"  Exists: {name}")
                    if not existing.description and dept_data.get("description"):
                        existing.description = dept_data["description"]
                else:
                    dept = Department(
                        name=name,
                        description=dept_data.get("description"),
                        is_active=True,
                    )
                    session.add(dept)
                    print(f"  Added: {name}")

            await session.commit()
            print("Done.")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
