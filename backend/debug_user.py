import asyncio
from app.db.session import SessionLocal
from app.models.user import User
from sqlalchemy import select

from app.models.employee import Employee

async def check():
    async with SessionLocal() as session:
        emails = ["admin@gmail.com", "hr@gmail.com", "employee@gmail.com"]
        for email in emails:
            print(f"\n--- Checking {email} ---")
            res = await session.execute(select(User).where(User.email == email))
            u = res.scalar_one_or_none()
            if u:
                print(f"User: {u.email}, ID: {u.id}")
                print(f"Superuser: {u.is_superuser}")
                print(f"Roles: {[r.name for r in u.roles]}")
                for r in u.roles:
                    perms = [p.name for p in r.permissions]
                    print(f"Role {r.name} perms: {perms}")
            else:
                print(f"User {email} not found")

        print("\n--- Checking Employees ---")
        res = await session.execute(select(Employee))
        emps = res.scalars().all()
        print(f"Total Employees: {len(emps)}")
        for e in emps:
            print(f"Emp ID: {e.employee_id}, User ID: {e.user_id}, Status: {e.status}")

if __name__ == "__main__":
    asyncio.run(check())
