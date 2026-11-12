"""Out-of-office approval delegation (Roadmap v2 Phase 2, Task 6).

`user_id` delegates their pending approvals to `delegate_id` for the date
range [starts_on, ends_on] (inclusive; ends_on NULL = open ended) until
revoked. With `only_when_on_leave` the delegation is only live on days the
delegator has an APPROVED leave covering the day (standing delegate).

Delegations do NOT chain: A -> B and B -> C never lets C act for A.
"""
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Index, Integer, String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class ApproverDelegation(Base):
    __tablename__ = "approver_delegation"  # type: ignore[assignment]
    __table_args__ = (
        Index("ix_approver_delegation_delegate", "delegate_id", "revoked_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), index=True)
    delegate_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"))
    starts_on: Mapped[date] = mapped_column(Date)
    ends_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    only_when_on_leave: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0")
    note: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)
