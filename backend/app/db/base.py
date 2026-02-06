from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# Ensure model modules are imported so Alembic autogenerate sees them.
from app.db import models as _models  # noqa: E402,F401
