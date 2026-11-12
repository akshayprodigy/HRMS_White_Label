"""HR-granted scheduling delegations (Roadmap v2 Phase 1A).

Lets any employee be given roster-planning rights over a scope (explicit
employees, a department, a location, or their own direct reports), optionally
with publish / change-approval rights and a validity window. `employee_ids`
and every `*_id` pointing at an employee are User ids.
"""
from datetime import datetime, date as pydate, timezone
from typing import Any, List, Optional

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Integer, JSON, String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class DelegationScope:
    EMPLOYEES = "employees"
    DEPARTMENT = "department"
    LOCATION = "location"
    TEAM = "team"

    ALL = (EMPLOYEES, DEPARTMENT, LOCATION, TEAM)


class ScheduleDelegation(Base):
    __tablename__ = "schedule_delegation"  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    grantee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)
    scope_value: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    employee_ids: Mapped[List[Any]] = mapped_column(JSON, default=list)
    can_publish: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    can_approve_changes: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    valid_from: Mapped[pydate] = mapped_column(Date, nullable=False)
    valid_to: Mapped[Optional[pydate]] = mapped_column(Date, nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    granted_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    note: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc), nullable=False,
    )

    grantee = relationship("User", foreign_keys=[grantee_id])
    granted_by = relationship("User", foreign_keys=[granted_by_id])
