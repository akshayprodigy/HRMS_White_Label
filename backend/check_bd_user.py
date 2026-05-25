import asyncio
from app.db.session import SessionLocal
from sqlalchemy import select
from app.models.user import User
from sqlalchemy.orm import selectinload

async def check():
    async with SessionLocal() as s:
        res = await s.execute(
            select(User).options(selectinload(User.roles)).where(User.email == 'bd@gmail.com')
        )
        u = res.scalars().first()
        if u:
            print(f"User: {u.full_name}, Roles: {[r.name for r in u.roles]}")
        else:
            print("User not found")

if __name__ == "__main__":
    asyncio.run(check())
