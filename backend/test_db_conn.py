import asyncio
from app.core.config import settings
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def test_connection():
    uri = str(settings.SQLALCHEMY_DATABASE_URI)
    print(f"Testing connection to: {uri}")
    try:
        engine = create_async_engine(uri)
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            print(f"Result: {result.scalar()}")
            print("Successfully connected to the database!")
    except Exception as e:
        print(f"Connection failed: {e}")
        print(f"Type: {type(e).__name__}")

if __name__ == "__main__":
    asyncio.run(test_connection())
