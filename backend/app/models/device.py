"""Mobile push device tokens (Roadmap v2 Phase 3, Task 1)."""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class DeviceToken(Base):
    __tablename__ = "device_token"  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"),
        index=True, nullable=False)
    platform: Mapped[str] = mapped_column(String(10), nullable=False)  # ios|android
    token: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    app_version: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    tenant: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)
