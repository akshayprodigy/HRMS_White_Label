"""Designation + Grade master.

Replaces free-text `Employee.designation` / `Employee.grade`. The legacy
string columns are kept during the transition so existing data and
payslips do not break — the canonical truth becomes the FK.

Backfill strategy (in the migration):
- Build Grade from distinct existing employee.grade strings.
- Build Designation from distinct existing employee.designation strings.
- Best-effort match employee.designation_id / grade_id; unmatched rows
  are left NULL for HR to clean up — never hard-fail.
"""
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional, List

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer, String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


if TYPE_CHECKING:
    from .user import User


class Grade(Base):
    __tablename__ = "grade"  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(
        String(40), unique=True, nullable=False, index=True
    )
    rank: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, index=True,
    )
    min_salary: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_salary: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    designations: Mapped[List["Designation"]] = relationship(
        back_populates="grade",
    )


class Designation(Base):
    __tablename__ = "designation"  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(
        String(120), unique=True, nullable=False, index=True
    )
    grade_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("grade.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    grade: Mapped[Optional[Grade]] = relationship(back_populates="designations")
