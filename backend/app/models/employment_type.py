from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class EmploymentType(Base):
    __tablename__ = "employment_type"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    # `code` matches the free-string Employee.employment_type value.
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    # Informational: is this worker paid through payroll at all.
    is_on_payroll: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Behaviour: do PF/ESI/PT/regular-TDS apply (True) or is this a flat-TDS
    # contractual/advisor profile (False).
    statutory_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Flat TDS rate (fraction, e.g. 0.10) used when statutory_enabled is False.
    flat_tds_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc), nullable=False,
    )
