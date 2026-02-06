import os

from app.core.config import get_settings


def _maybe_upgrade_db_schema() -> None:
    if os.getenv("RUN_DB_TESTS") != "1":
        return

    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    backend_dir = Path(__file__).resolve().parents[1]
    alembic_ini_path = backend_dir / "alembic.ini"

    cfg = Config(str(alembic_ini_path))
    cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    cfg.set_main_option("prepend_sys_path", str(backend_dir))
    command.upgrade(cfg, "head")


# Ensure JWT is usable in tests that hit auth endpoints.
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")

_maybe_upgrade_db_schema()

get_settings.cache_clear()
