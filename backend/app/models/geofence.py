"""SQLAlchemy models for the geo-fencing layer."""
from datetime import datetime, timezone
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer, String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base

if TYPE_CHECKING:
    from .user import User


class GeoFenceLocation(Base):
    """A site / location an employee may be punched-in from.

    The fence is a circle defined by (latitude, longitude, radius_meters).
    Radius lower bound of 100m is enforced at the Pydantic + API layer
    so consumer-GPS noise doesn't cause false rejections.
    """
    __tablename__ = "geofence_location"  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(
        String(120), unique=True, index=True, nullable=False
    )
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    radius_meters: Mapped[int] = mapped_column(Integer, nullable=False)

    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    created_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )

    created_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[created_by_id]
    )


class EmployeeGeoConfig(Base):
    """Per-employee geo-fencing config.

    Existence of a row means "this employee has been onboarded into geo
    fencing". `geo_enabled = False` keeps the row but turns enforcement
    off in real time without losing the fence allowlist.

    Employees with NO row in this table behave exactly as today — no
    geo checks, no regression.
    """
    __tablename__ = "employee_geo_config"  # type: ignore[assignment]

    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("user.id", ondelete="CASCADE"),
        primary_key=True,
    )
    # 'strict' | 'allow_with_flag' — mirrors EnforcementMode in
    # app.services.geofence. Stored as string for indexing simplicity.
    enforcement_mode: Mapped[str] = mapped_column(
        String(32), nullable=False, default="strict"
    )
    geo_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )

    user: Mapped["User"] = relationship(
        "User", foreign_keys=[user_id]
    )
    fences: Mapped[List["EmployeeGeoFenceLink"]] = relationship(
        back_populates="config",
        cascade="all, delete-orphan",
    )


class EmployeeGeoFenceLink(Base):
    """Many-to-many between employees and the fences they are allowed at.

    Lives separately from EmployeeGeoConfig because the mode + toggle
    are per-employee, not per-fence; only the allowlist is many-many.
    """
    __tablename__ = "employee_geo_fence_link"  # type: ignore[assignment]

    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("employee_geo_config.user_id", ondelete="CASCADE"),
        primary_key=True,
    )
    geofence_location_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("geofence_location.id", ondelete="CASCADE"),
        primary_key=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    config: Mapped["EmployeeGeoConfig"] = relationship(
        back_populates="fences",
        foreign_keys=[user_id],
    )
    fence: Mapped["GeoFenceLocation"] = relationship(
        foreign_keys=[geofence_location_id]
    )
