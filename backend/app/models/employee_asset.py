from datetime import datetime, date, timezone
from typing import Optional, TYPE_CHECKING
from sqlalchemy import String, Integer, ForeignKey, DateTime, Date, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base_class import Base

if TYPE_CHECKING:
    from .employee import Employee
    from .user import User
    from .asset import Asset


class EmployeeAsset(Base):
    """Hardware / software assets issued to an employee (laptops, monitors,
    phones, software licences). One row per asset; status moves from
    `allocated` to `returned` (or `lost`) at separation."""
    __tablename__ = "employee_asset"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("employee.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    asset_type: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(150), nullable=False)
    identifier: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    serial_no: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    issued_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    returned_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="allocated"
    )
    condition: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    remarks: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    created_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )

    asset_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("asset.id", ondelete="RESTRICT"),
        nullable=True, index=True,
    )
    allocated_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    returned_condition: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )
    returned_to_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )

    employee: Mapped["Employee"] = relationship("Employee")
    created_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[created_by_id])
    allocated_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[allocated_by_id])
    returned_to: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[returned_to_id])
    asset: Mapped[Optional["Asset"]] = relationship(
        "Asset", back_populates="allocations", foreign_keys=[asset_id])
