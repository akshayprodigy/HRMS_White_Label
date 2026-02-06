from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.database import get_db
from app.main import app


class _ScalarOne:
    def scalar_one(self) -> int:
        return 1


class _FakeSession:
    def execute(self, _query):
        return _ScalarOne()


def test_db_ping_ok_with_dependency_override() -> None:
    def _override_get_db():
        yield _FakeSession()

    app.dependency_overrides[get_db] = _override_get_db
    try:
        client = TestClient(app)
        resp = client.get("/api/v1/db/ping")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
    finally:
        app.dependency_overrides.clear()
