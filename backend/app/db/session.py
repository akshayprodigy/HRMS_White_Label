"""Compatibility module.

Prefer importing database utilities from `app.core.database`.
"""

from __future__ import annotations

from app.core.database import SessionLocal, engine, get_db

__all__ = ["engine", "SessionLocal", "get_db"]
