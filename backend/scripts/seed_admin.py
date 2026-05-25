import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from app.models.user import User, Role, Permission
from app.core.config import settings


async def seed_admin():
    engine = create_async_engine(settings.SQLALCHEMY_DATABASE_URI)
    AsyncSessionLocal = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    try:
        async with AsyncSessionLocal() as session:
            # Create default permissions
            permissions_data = [
                {
                    "name": "admin access",
                    "description": "Full access to admin module",
                },
                {
                    "name": "view dashboard",
                    "description": "Access to main dashboard",
                },
                {
                    "name": "manage tasks",
                    "description": "Create and edit any task",
                },
                {
                    "name": "employee time read",
                    "description": "Read own time logs",
                },
                {
                    "name": "employee time write",
                    "description": "Write own time logs",
                },
                {
                    "name": "employee leave read",
                    "description": "View own leaves",
                },
                {
                    "name": "employee leave write",
                    "description": "Apply/Cancel own leaves",
                },
                {
                    "name": "leave approve",
                    "description": "Approve/Reject leaves",
                },
            ]

            db_permissions = []
            for p_data in permissions_data:
                result = await session.execute(
                    select(Permission).where(Permission.name == p_data["name"])
                )
                perm = result.scalars().first()
                if not perm:
                    perm = Permission(**p_data)
                    session.add(perm)
                    db_permissions.append(perm)
                else:
                    db_permissions.append(perm)

            await session.flush()

            # Create Super Admin Role
            result = await session.execute(
                select(Role).where(Role.name == "Super Admin")
            )
            role = result.scalars().first()
            if not role:
                role = Role(
                    name="Super Admin",
                    description="Unrestricted access to all system functions",
                )
                role.permissions = db_permissions
                session.add(role)
            else:
                # Add missing permissions to existing role
                current_perms = {p.name for p in role.permissions}
                for p in db_permissions:
                    if p.name not in current_perms:
                        role.permissions.append(p)

            await session.flush()

            # Assign to admin@gmail.com
            result = await session.execute(
                select(User).where(User.email == "admin@gmail.com")
            )
            user = result.scalars().first()
            if user:
                # Ensure Super Admin role is present
                if role not in user.roles:
                    user.roles.append(role)
                user.is_superuser = True  # Ensure they are also DB superuser

            await session.commit()
            print("Successfully seeded admin roles and permissions.")
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(seed_admin())
