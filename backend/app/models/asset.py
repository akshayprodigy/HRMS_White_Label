"""Asset register: categories, assets, maintenance log and employee asset
requests (Roadmap v2 Phase 5, Task 1). Money is stored in paise (int)."""
from datetime import date, datetime, timezone
from typing import List, Optional, TYPE_CHECKING

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Integer, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base

if TYPE_CHECKING:
    from .employee_asset import EmployeeAsset
    from .geofence import GeoFenceLocation


def _now():
    return datetime.now(timezone.utc)


class AssetStatus:
    IN_STOCK = "in_stock"
    ALLOCATED = "allocated"
    IN_REPAIR = "in_repair"
    RETIRED = "retired"
    LOST = "lost"


class AssetRequestStatus:
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    FULFILLED = "fulfilled"
    CANCELLED = "cancelled"


class AssetCategory(Base):
    __tablename__ = "asset_category"  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    code: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    default_useful_life_months: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False)


class Asset(Base):
    __tablename__ = "asset"  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_tag: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    category_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("asset_category.id", ondelete="RESTRICT"),
        nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    model: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    serial_no: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, index=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=AssetStatus.IN_STOCK,
        server_default=AssetStatus.IN_STOCK, index=True)
    location_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("geofence_location.id", ondelete="SET NULL"),
        nullable=True)
    vendor: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    invoice_no: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    purchase_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    purchase_cost_paise: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True)
    salvage_value_paise: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0")
    useful_life_months: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True)
    warranty_expiry: Mapped[Optional[date]] = mapped_column(
        Date, nullable=True, index=True)
    amc_vendor: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    amc_expiry: Mapped[Optional[date]] = mapped_column(
        Date, nullable=True, index=True)
    # dedupe stamps for expiry alerts
    warranty_alert_for: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    amc_alert_for: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    category: Mapped["AssetCategory"] = relationship("AssetCategory")
    location: Mapped[Optional["GeoFenceLocation"]] = relationship(
        "GeoFenceLocation")
    allocations: Mapped[List["EmployeeAsset"]] = relationship(
        "EmployeeAsset", back_populates="asset",
        foreign_keys="EmployeeAsset.asset_id", passive_deletes="all")
    maintenance: Mapped[List["AssetMaintenance"]] = relationship(
        "AssetMaintenance", back_populates="asset",
        cascade="all, delete-orphan", passive_deletes=True)


class AssetMaintenance(Base):
    __tablename__ = "asset_maintenance"  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("asset.id", ondelete="CASCADE"),
        nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    vendor: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    cost_paise: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0")
    started_on: Mapped[date] = mapped_column(Date, nullable=False)
    completed_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    created_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False)

    asset: Mapped["Asset"] = relationship("Asset", back_populates="maintenance")


class AssetRequest(Base):
    __tablename__ = "asset_request"  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("employee.id", ondelete="CASCADE"),
        nullable=False, index=True)
    category_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("asset_category.id", ondelete="RESTRICT"),
        nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    needed_by: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=AssetRequestStatus.PENDING,
        server_default=AssetRequestStatus.PENDING, index=True)
    approval_instance_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("chained_approval_instance.id", ondelete="SET NULL"),
        nullable=True)
    decided_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    decided_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)
    decision_note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    fulfilled_asset_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("asset.id", ondelete="SET NULL"), nullable=True)
    allocation_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("employee_asset.id", ondelete="SET NULL"),
        nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False)

    category: Mapped["AssetCategory"] = relationship("AssetCategory")
    fulfilled_asset: Mapped[Optional["Asset"]] = relationship("Asset")
