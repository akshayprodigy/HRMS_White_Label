import enum
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING, Any
from sqlalchemy import String, Integer, ForeignKey, DateTime, Enum, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base_class import Base

if TYPE_CHECKING:
    from .user import User, Role


SET_NULL = "SET NULL"


class ApprovalStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CHANGES_REQUESTED = "changes_requested"


class ApprovalItem(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    resource_type: Mapped[str] = mapped_column(String(50), index=True)
    resource_id: Mapped[str] = mapped_column(String(50), index=True)
    status: Mapped[ApprovalStatus] = mapped_column(
        Enum(ApprovalStatus), default=ApprovalStatus.PENDING, index=True
    )
    current_step_number: Mapped[int] = mapped_column(Integer, default=1)
    
    requested_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete=SET_NULL), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    due_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )

    requested_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[requested_by_id]
    )
    steps: Mapped[list["ApprovalStep"]] = relationship(
        back_populates="approval_item", cascade="all, delete-orphan"
    )


class ApprovalStep(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    approval_item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("approvalitem.id", ondelete="CASCADE"), index=True
    )
    step_number: Mapped[int] = mapped_column(Integer, nullable=False)
    approver_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user.id", ondelete=SET_NULL), nullable=True
    )
    role_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("role.id", ondelete=SET_NULL), nullable=True
    )
    status: Mapped[ApprovalStatus] = mapped_column(
        Enum(ApprovalStatus), default=ApprovalStatus.PENDING
    )
    comment: Mapped[Optional[str]] = mapped_column(String(500))
    actioned_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )

    approval_item: Mapped[ApprovalItem] = relationship(back_populates="steps")
    approver: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[approver_id]
    )
    role: Mapped[Optional["Role"]] = relationship("Role")
