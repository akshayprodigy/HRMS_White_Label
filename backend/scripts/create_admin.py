import asyncio
import os
import secrets

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from app.models.user import User, Role
from app.core.security import get_password_hash
from app.core.config import settings


async def create_admin():
    engine = create_async_engine(settings.SQLALCHEMY_DATABASE_URI)
    AsyncSessionLocal = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    try:
        async with AsyncSessionLocal() as session:
            # Check if Admin Role exists
            result = await session.execute(
                select(Role).where(Role.name == "Super Admin")
            )
            role = result.scalars().first()

            if not role:
                print(
                    "Super Admin role not found. "
                    "Please run seed_admin.py first."
                )
                return

            # Check if admin user exists
            email = os.getenv("ADMIN_EMAIL", "admin@gmail.com")
            password_env = os.getenv("ADMIN_PASSWORD")

            result = await session.execute(
                select(User).where(User.email == email)
            )
            user = result.scalars().first()

            if not user:
                password = password_env or secrets.token_urlsafe(18)
                if not password_env:
                    print(f"Generated admin password for {email}: {password}")
                user = User(
                    email=email,
                    hashed_password=get_password_hash(password),
                    full_name="System Administrator",
                    is_active=True,
                    is_superuser=True,
                )
                user.roles = [role]
                session.add(user)
                print(f"Created admin user: {email}")
            else:
                user.is_superuser = True
                user.roles = [role]
                if password_env:
                    user.hashed_password = get_password_hash(password_env)
                    print(f"Updated existing user {email} to Super Admin")
                else:
                    print(
                        f"Updated existing user {email} to Super Admin "
                        "(password unchanged; set ADMIN_PASSWORD to rotate)"
                    )

            await session.commit()
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(create_admin())
