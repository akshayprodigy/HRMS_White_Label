import asyncio
import httpx
from app.core.config import settings

async def test_login():
    url = "http://127.0.0.1:8001/api/v1/auth/login"
    data = {
        "username": "admin@gmail.com",
        "password": "test@12345"
    }
    print(f"Attempting login to {url}")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, data=data)
            print(f"Status: {response.status_code}")
            print(f"Body: {response.text}")
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    # Note: This assumes the server is running on port 8001 (my temporary instance)
    asyncio.run(test_login())
