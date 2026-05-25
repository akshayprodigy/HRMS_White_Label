import asyncio
from app.db.session import SessionLocal
from app.models.leave import LeaveType
from sqlalchemy import select

async def check_leaves():
    async with SessionLocal() as db:
        result = await db.execute(select(LeaveType))
        types = result.scalars().all()
        print(f"Leave Types: {[t.name for t in types]}")

if __name__ == "__main__":
    asyncio.run(check_leaves())
