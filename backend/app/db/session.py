from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncEngine,
)
from sqlalchemy.pool import NullPool
import sys
from app.core.config import settings


def create_engine() -> AsyncEngine:
    engine_kwargs: dict = {
        "pool_pre_ping": True,
        "pool_recycle": 3600,
        "pool_size": 10,
        "max_overflow": 20,
    }

    # Pytest often uses different event loops between tests/threads.
    # Reusing aiomysql pooled connections across loops can cause:
    # "got Future attached to a different loop".
    if "pytest" in sys.modules:
        engine_kwargs = {
            "poolclass": NullPool,
            "pool_pre_ping": False,
        }

    return create_async_engine(
        str(settings.SQLALCHEMY_DATABASE_URI),
        **engine_kwargs,
    )


engine = create_engine()
SessionLocal = async_sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False,
)
