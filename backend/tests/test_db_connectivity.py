import os

import pytest
from sqlalchemy import text

from app.core.database import SessionLocal, engine


@pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="Set RUN_DB_TESTS=1 to run integration DB connectivity tests.",
)
def test_database_connectivity_select_1() -> None:
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1")).scalar_one()
        assert result == 1


@pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="Set RUN_DB_TESTS=1 to run integration DB connectivity tests.",
)
def test_get_db_session_works() -> None:
    db = SessionLocal()
    try:
        result = db.execute(text("SELECT 1")).scalar_one()
        assert result == 1
    finally:
        db.close()
